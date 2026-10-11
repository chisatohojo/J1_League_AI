using System.Text.Json;

namespace J1AI.SmokeNetworkObserver;

internal interface IBlobStore
{
    void CreatePending(string name, byte[] bytes);
    void FlushPending(string name);
    byte[] ReadPending(string name);
    void Commit(string name);
    byte[] ReadCommitted(string name);
}

// Shared by real disk writer and value-only fault tests. No swallowed write,
// flush, rename or read-back failures. A result without its verified receipt is
// incomplete, even if the data file happens to contain a PASS word.
internal sealed class VerifiedEvidence(IBlobStore store) : IEvidence
{
    private long used;
    public void SaveVerified(string name, object value)
    {
        if (!System.Text.RegularExpressions.Regex.IsMatch(name, "\\A[a-zA-Z0-9-]{1,40}\\z")) throw new IOException("evidence_name");
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Approval.Json);
        used = checked(used + bytes.Length);
        if (bytes.Length > 4 * 1024 * 1024 || used > 64 * 1024 * 1024) throw new IOException("evidence_capacity");
        Save(name, bytes);
        if (name == "result")
            Save("result-receipt", JsonSerializer.SerializeToUtf8Bytes(new { ResultSha256 = Approval.Hash(bytes), Complete = true }, Approval.Json));
    }
    private void Save(string name, byte[] bytes)
    {
        store.CreatePending(name, bytes);
        store.FlushPending(name);
        if (!store.ReadPending(name).AsSpan().SequenceEqual(bytes)) throw new IOException("evidence_verification");
        store.Commit(name);
        if (!store.ReadCommitted(name).AsSpan().SequenceEqual(bytes)) throw new IOException("evidence_final_verification");
    }
}

internal sealed class DiskBlobs(string directory) : IBlobStore, IDisposable
{
    private FileStream? current;
    private string? pendingName;
    private string Pending(string name) => Path.Combine(directory, name + ".json.pending");
    private string Committed(string name) => Path.Combine(directory, name + ".json");
    public void CreatePending(string name, byte[] bytes)
    {
        current?.Dispose(); current = null;
        pendingName = name;
        current = new(Pending(name), FileMode.CreateNew, FileAccess.ReadWrite, FileShare.None, 4096, FileOptions.WriteThrough);
        current.Write(bytes);
    }
    public void FlushPending(string name)
    { Approval.Require(pendingName == name && current != null, "pending_mismatch"); current!.Flush(true); }
    public byte[] ReadPending(string name)
    {
        Approval.Require(pendingName == name && current != null && current.Length <= 4 * 1024 * 1024, "pending_mismatch");
        current!.Position = 0; var bytes = new byte[current.Length]; current.ReadExactly(bytes); return bytes;
    }
    public void Commit(string name)
    {
        Approval.Require(pendingName == name && current != null, "pending_mismatch");
        current!.Dispose(); current = null;
        File.Move(Pending(name), Committed(name), false); pendingName = null;
    }
    public byte[] ReadCommitted(string name) => File.ReadAllBytes(Committed(name));
    public void Dispose() { current?.Dispose(); current = null; }
}
