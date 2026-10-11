namespace J1AI.SmokeNetworkObserver;

// Real diagnostics only by separately approved --observe, never --plan. Tests
// use the internal constructor exclusively for owned isolated OS temp paths.
// Pending files are retained on failure. No overwrite/delete/recovery fallback.
public sealed class FileEvidence : IEvidence, IDisposable
{
    private readonly EvidenceDirectory directory;
    private readonly DiskBlobs blobs;
    private readonly VerifiedEvidence writer;
    public FileEvidence(ApprovalPlan plan) : this(ApprovedDirectory(plan), new EvidencePolicy()) { }
    private static string ApprovedDirectory(ApprovalPlan plan)
    { Approval.Validate(plan, true); return plan.EvidenceDirectory; }
    // Isolated native test entry only, not a CLI or arbitrary-profile override.
    internal FileEvidence(string path, EvidencePolicy policy)
    {
        directory = new EvidenceDirectory(path, policy);
        blobs = new DiskBlobs(directory); writer = new VerifiedEvidence(blobs);
    }
    internal string DirectoryIdentity => directory.Identity;
    public void SaveVerified(string name, object value)
    {
        writer.SaveVerified(name, value);
    }
    public void Dispose() { try { blobs.Dispose(); } finally { directory.Dispose(); } }
}
