using System.Text.Json;

namespace J1AI.SmokeNetworkObserver;

internal interface IBlobStore
{
    void CreatePending(string name, byte[] bytes);
    void FlushPending(string name);
    byte[] ReadPending(string name);
    void Commit(string name);
    byte[] ReadCommitted(string name);
    BlobIdentity Identity(string name) => throw new IOException("receipt_identity_unavailable");
}
internal sealed record BlobIdentity(string DirectoryIdentity, string FileIdentity);
public sealed record FileReceipt(J1AI.SmokeCoordination.RunBinding Binding, string Name, string FileSha256,
    string DirectoryIdentity, string VolumeId, string FileId, bool Flushed, bool PendingReadback,
    bool FinalReadback, DateTimeOffset SavedUtc, string? RawSha256, bool Complete = true, string? ResultSha256 = null);

// Shared by real disk writer and value-only fault tests. No swallowed write,
// flush, rename or read-back failures. A result without its verified receipt is
// incomplete, even if the data file happens to contain a PASS word.
internal sealed class VerifiedEvidence(IBlobStore store, J1AI.SmokeCoordination.RunBinding? binding = null) : IEvidence
{
    private long used;
    private readonly Dictionary<string, string> hashes = [];
    public void SaveVerified(string name, object value)
    {
        if (!System.Text.RegularExpressions.Regex.IsMatch(name, "\\A[a-zA-Z0-9-]{1,40}\\z")) throw new IOException("evidence_name");
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value, Approval.Json);
        Save(name, bytes);
        if (binding != null)
        {
            var identity = store.Identity(name);
            if (identity.FileIdentity.Length != 48 || identity.DirectoryIdentity.Length != 48 ||
                !identity.FileIdentity.All(Uri.IsHexDigit) || !identity.DirectoryIdentity.All(Uri.IsHexDigit) ||
                identity.FileIdentity[..16] != identity.DirectoryIdentity[..16])
                throw new IOException("receipt_file_identity");
            string hash = Approval.Hash(bytes); hashes.Add(name, hash);
            string? rawHash = null;
            if (name.EndsWith("-verdict", StringComparison.Ordinal) && !hashes.TryGetValue(name[..^8] + "-raw", out rawHash))
                throw new IOException("receipt_raw_missing");
            var receipt = new FileReceipt(binding, name, hash, identity.DirectoryIdentity,
                identity.FileIdentity[..16], identity.FileIdentity[16..], true, true, true, DateTimeOffset.UtcNow, rawHash,
                ResultSha256: name == "result" ? hash : null);
            Save(name + "-receipt", JsonSerializer.SerializeToUtf8Bytes(receipt, Approval.Json));
        }
        else if (name == "result")
            Save("result-receipt", JsonSerializer.SerializeToUtf8Bytes(new { ResultSha256 = Approval.Hash(bytes), Complete = true }, Approval.Json));
    }
    private void Save(string name, byte[] bytes)
    {
        used = checked(used + bytes.Length);
        if (bytes.Length > 4 * 1024 * 1024 || used > 64 * 1024 * 1024) throw new IOException("evidence_capacity");
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
    public BlobIdentity Identity(string name)
    {
        directory.Validate(); var entry = committed[name];
        string actual = EvidenceNative.Identity(entry.Stream.SafeFileHandle);
        if (actual != entry.Identity) throw new IOException("receipt_file_identity_changed");
        return new(directory.Identity, actual);
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
