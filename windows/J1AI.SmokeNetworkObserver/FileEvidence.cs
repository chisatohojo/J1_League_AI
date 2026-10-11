using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace J1AI.SmokeNetworkObserver;

// Created only by a separately approved --observe invocation, never --plan or tests.
// Pending files are retained on failure. No overwrite/delete/recovery fallback.
public sealed class FileEvidence : IEvidence, IDisposable
{
    private readonly string directory;
    private readonly List<WinHandle> pins = [];
    private readonly DiskBlobs blobs;
    private readonly VerifiedEvidence writer;
    public FileEvidence(ApprovalPlan plan)
    {
        Approval.Validate(plan, true); directory = plan.EvidenceDirectory;
        blobs = new DiskBlobs(directory); writer = new VerifiedEvidence(blobs);
        try
        {
            var ancestry = new Stack<string>();
            for (var d = new DirectoryInfo(Path.GetDirectoryName(directory)!); d != null; d = d.Parent) ancestry.Push(d.FullName);
            // Diagnostics ancestors must already exist under separately approved preparation.
            // Do not manufacture an unreviewed hierarchy here.
            foreach (string path in ancestry) Pin(path);
            if (!Win.CreateDirectoryW(directory, 0)) throw new IOException("evidence_create_failed");
            var security = new DirectorySecurity(); security.SetAccessRuleProtection(true, false);
            var sid = WindowsIdentity.GetCurrent().User ?? throw new IOException("evidence_sid");
            foreach (var owner in new[] { sid, new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null) })
                security.AddAccessRule(new FileSystemAccessRule(owner, FileSystemRights.FullControl,
                    InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
            new DirectoryInfo(directory).SetAccessControl(security);
            Pin(directory);
        }
        catch { Dispose(); throw; }
    }
    private void Pin(string path)
    {
        Approval.CheckPath(path);
        var h = Win.CreateFileW(path, 0x80, 3, 0, 3, 0x02000000 | 0x00200000, 0);
        if (h.IsInvalid) { h.Dispose(); throw new IOException("evidence_directory_pin"); }
        pins.Add(h);
        var final = new StringBuilder(32768);
        uint n = Win.GetFinalPathNameByHandleW(h, final, 32768, 0);
        if (n == 0 || n >= 32768 || !OwnershipRules.PathEquals(final.ToString().TrimEnd('\\'), (@"\\?\" + path).TrimEnd('\\')))
            throw new IOException("evidence_directory_identity");
    }
    public void SaveVerified(string name, object value)
    {
        writer.SaveVerified(name, value);
    }
    public void Dispose() { blobs.Dispose(); foreach (var h in pins.AsEnumerable().Reverse()) h.Dispose(); pins.Clear(); }
}
