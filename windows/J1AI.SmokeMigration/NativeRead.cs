using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeMigration;

// This assembly contains no filesystem-write P/Invoke or transaction engine.
// Every CreateFile call below is OPEN_EXISTING with read-only access.
public sealed class ReadPin : IDisposable
{
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern SafeFileHandle CreateFileW(string path, uint access, uint share, nint security, uint disposition, uint flags, nint template);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(SafeFileHandle handle, int kind, byte[] data, uint length);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern uint GetFinalPathNameByHandleW(SafeFileHandle handle, StringBuilder path, uint length, uint flags);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(SafeFileHandle handle, byte[] data);
    [DllImport("advapi32")] private static extern uint GetSecurityInfo(SafeFileHandle handle, int type, uint info,
        out nint owner, out nint group, out nint dacl, out nint sacl, out nint descriptor);
    [DllImport("advapi32")] private static extern uint GetSecurityDescriptorLength(nint sd);
    [DllImport("kernel32")] private static extern nint LocalFree(nint pointer);
    private readonly List<SafeFileHandle> ancestors = [];
    public SafeFileHandle Handle { get; }
    public string Path { get; }
    public string ObjectId { get; }
    public string LegacyId { get; }
    private bool disposed;
    public static void Canonical(string path)
    {
        Contract.Require(System.IO.Path.IsPathFullyQualified(path) && !path.StartsWith(@"\\", StringComparison.Ordinal) &&
            path == System.IO.Path.GetFullPath(path) && path.IndexOf(':', 2) < 0 && !path.Contains('/') &&
            path.Split('\\').All(p => !p.EndsWith(' ') && !p.EndsWith('.')), "path_canonical");
    }
    public ReadPin(string path, bool directory, bool denyFileChanges = true)
    {
        Canonical(path); Path = path;
        try
        {
            var stack = new Stack<string>();
            for (var d = new DirectoryInfo(directory ? path : System.IO.Path.GetDirectoryName(path)!); d != null; d = d.Parent) stack.Push(d.FullName);
            while (stack.Count > 0)
            {
                var h = Open(stack.Pop(), true, 3); ancestors.Add(h);
            }
            Handle = directory ? ancestors[^1] : Open(path, false, denyFileChanges ? 1u : 7u);
            ObjectId = Identity(Handle);
            var data = new byte[52]; Contract.Require(GetFileInformationByHandle(Handle, data), "legacy_identity");
            LegacyId = $"{BitConverter.ToUInt32(data, 28):x8}:{BitConverter.ToUInt32(data, 44):x8}{BitConverter.ToUInt32(data, 48):x8}";
            Verify();
        }
        catch { Dispose(); throw; }
    }
    private static SafeFileHandle Open(string path, bool directory, uint share)
    {
        var h = CreateFileW(path, directory ? 0x20081u : 0x20089u, share, 0, 3, 0x02200000, 0);
        try
        {
            Contract.Require(!h.IsInvalid, "read_handle:" + Marshal.GetLastWin32Error()); Check(h, directory);
            var final = new StringBuilder(32768);
            uint n = GetFinalPathNameByHandleW(h, final, (uint)final.Capacity, 0);
            Contract.Require(n > 0 && n < final.Capacity && final.ToString().TrimEnd('\\').Equals((@"\\?\" + path).TrimEnd('\\'), StringComparison.OrdinalIgnoreCase), "final_path");
            return h;
        }
        catch { h.Dispose(); throw; }
    }
    public static void Check(SafeFileHandle h, bool directory)
    {
        var data = new byte[8]; Contract.Require(GetFileInformationByHandleEx(h, 9, data, 8), "attributes");
        uint bits = BitConverter.ToUInt32(data);
        Contract.Require((bits & 0x400) == 0 && BitConverter.ToUInt32(data, 4) == 0, "reparse");
        Contract.Require(((bits & 0x10) != 0) == directory, "object_type");
    }
    public static string Identity(SafeFileHandle h)
    {
        var data = new byte[24]; Contract.Require(GetFileInformationByHandleEx(h, 18, data, 24), "file_identity");
        return Convert.ToHexString(data).ToLowerInvariant();
    }
    public static RawSecurityDescriptor Security(SafeFileHandle h)
    {
        uint error = GetSecurityInfo(h, 1, 5, out _, out _, out _, out _, out nint sd);
        try
        {
            Contract.Require(error == 0 && sd != 0, "security_query"); uint length = GetSecurityDescriptorLength(sd);
            Contract.Require(length is > 0 and <= 65536, "security_size");
            var bytes = new byte[length]; Marshal.Copy(sd, bytes, 0, bytes.Length); return new(bytes, 0);
        }
        finally { if (sd != 0) LocalFree(sd); }
    }
    public static void RequirePrivate(SafeFileHandle h, bool requireProtected = true, string? expectedSid = null)
    {
        var sd = Security(h); string user = expectedSid ?? WindowsIdentity.GetCurrent().User!.Value;
        Contract.Require(sd.Owner?.Value == user, "owner_sid");
        Contract.Require(!requireProtected || sd.ControlFlags.HasFlag(ControlFlags.DiscretionaryAclProtected), "dacl_protected");
        var acl = sd.DiscretionaryAcl; Contract.Require(acl != null && acl.Count == 2, "dacl_count");
        var seen = new HashSet<string>();
        foreach (GenericAce entry in acl!)
        {
            Contract.Require(entry is CommonAce { AceQualifier: AceQualifier.AccessAllowed }, "dacl_ace");
            var ace = (CommonAce)entry; string sid = ace.SecurityIdentifier.Value;
            Contract.Require((sid == user || sid == "S-1-5-18") && ace.AccessMask == 0x1f01ff && seen.Add(sid), "dacl_access");
        }
    }
    public void Verify()
    {
        Contract.Require(!disposed && Identity(Handle) == ObjectId, "object_replaced");
        foreach (var h in ancestors) Check(h, true);
    }
    public byte[] Bytes()
    {
        Verify(); using var borrowed = new SafeFileHandle(Handle.DangerousGetHandle(), false);
        using var stream = new FileStream(borrowed, FileAccess.Read); stream.Position = 0;
        Contract.Require(stream.Length <= 32 * 1024 * 1024, "file_size");
        var data = new byte[checked((int)stream.Length)]; stream.ReadExactly(data); Verify(); return data;
    }
    public void Dispose()
    {
        if (disposed) return; disposed = true;
        if (Handle != null && !ancestors.Contains(Handle)) Handle.Dispose();
        foreach (var h in ancestors.AsEnumerable().Reverse()) h.Dispose(); ancestors.Clear();
    }
}
