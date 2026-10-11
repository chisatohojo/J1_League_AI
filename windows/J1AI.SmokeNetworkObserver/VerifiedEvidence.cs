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

internal sealed class DiskBlobs(EvidenceDirectory directory) : IBlobStore, IDisposable
{
    private readonly Dictionary<string, (FileStream Stream, string Identity)> committed = [];
    private FileStream? current;
    private string? pendingName;
    private string? currentIdentity;
    private static string Pending(string name) => name + ".json.pending";
    private static string Committed(string name) => name + ".json";
    private void At(string stage, string name)
    { directory.Validate(); directory.Policy.At(stage, name, current?.SafeFileHandle); }
    public void CreatePending(string name, byte[] bytes)
    {
        if (committed.Count >= 4096) throw new IOException("evidence_file_capacity");
        current?.Dispose(); current = null;
        pendingName = name;
        var h = directory.File(Pending(name), true);
        try { current = new FileStream(h, FileAccess.ReadWrite); }
        catch { h.Dispose(); throw; }
        currentIdentity = EvidenceNative.Identity(current.SafeFileHandle);
        At("write", name);
        int first = bytes.Length / 2; current.Write(bytes.AsSpan(0, first));
        At("write_partial", name); current.Write(bytes.AsSpan(first));
    }
    public void FlushPending(string name)
    { Approval.Require(pendingName == name && current != null, "pending_mismatch"); At("flush", name); current!.Flush(true); }
    public byte[] ReadPending(string name)
    {
        Approval.Require(pendingName == name && current != null && current.Length <= 4 * 1024 * 1024, "pending_mismatch");
        At("read_pending", name);
        if (directory.Policy.IdentityCheck && directory.Policy.SampleIdentity(current!.SafeFileHandle) != currentIdentity)
            throw new IOException("evidence_pending_identity");
        current!.Position = 0; var bytes = new byte[current.Length]; current.ReadExactly(bytes); return bytes;
    }
    public void Commit(string name)
    {
        Approval.Require(pendingName == name && current != null, "pending_mismatch");
        At("commit", name);
        EvidenceNative.Rename(current!.SafeFileHandle, directory.Handle, Committed(name));
        current.Flush(true);
        committed.Add(name, (current, currentIdentity!)); current = null; pendingName = null;
    }
    public byte[] ReadCommitted(string name)
    {
        At("read_committed", name);
        var entry = committed[name];
        using var h = directory.File(Committed(name), false);
        if (directory.Policy.IdentityCheck && directory.Policy.SampleIdentity(h) != entry.Identity)
            throw new IOException("evidence_committed_identity");
        using var file = new FileStream(h, FileAccess.Read);
        if (file.Length > 4 * 1024 * 1024) throw new IOException("evidence_size");
        var bytes = new byte[file.Length]; file.ReadExactly(bytes); return bytes;
    }
    public void Dispose()
    {
        var streams = committed.Values.Select(entry => entry.Stream).ToList();
        if (current != null) streams.Add(current);
        current = null; pendingName = null; committed.Clear();
        Exception? failure = null;
        foreach (var stream in streams)
        {
            try
            {
                try { directory.Policy.At("close_file", "", stream.SafeFileHandle); }
                finally { stream.Dispose(); }
            }
            catch (Exception e) { failure ??= e; }
        }
        if (failure != null) throw new IOException("evidence_cleanup_failed", failure);
    }
}
