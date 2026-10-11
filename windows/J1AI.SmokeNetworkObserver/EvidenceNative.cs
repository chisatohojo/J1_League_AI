using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeNetworkObserver;

// User-mode NtCreateFile creates AND returns ownership in one operation. No
// CreateDirectory/open fallback. All relative names below are single components.
internal static class EvidenceNative
{
    [StructLayout(LayoutKind.Sequential)] private struct UnicodeName
    { internal ushort Length, MaximumLength; internal nint Buffer; }
    [StructLayout(LayoutKind.Sequential)] private struct Attributes
    { internal int Length; internal nint Root, Name; internal uint Flags; internal nint Security, Quality; }
    [StructLayout(LayoutKind.Sequential)] private struct IoStatus
    { internal nint Status; internal nuint Information; }
    [DllImport("ntdll", ExactSpelling = true)] private static extern int NtCreateFile(out nint handle, uint access,
        ref Attributes attributes, out IoStatus io, nint allocation, uint fileAttributes, uint share,
        uint disposition, uint options, nint ea, uint eaLength);
    [DllImport("ntdll", ExactSpelling = true)] private static extern uint RtlNtStatusToDosError(int status);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(SafeHandle handle, int kind, byte[] information, uint size);
    [DllImport("ntdll", ExactSpelling = true)] private static extern int NtSetInformationFile(SafeFileHandle handle,
        out IoStatus io, byte[] information, uint size, int kind);
    [DllImport("advapi32", SetLastError = true)] private static extern uint SetSecurityInfo(SafeHandle handle,
        int kind, uint information, nint owner, nint group, nint dacl, nint sacl);
    [DllImport("advapi32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSecurityDescriptorDacl(nint descriptor, out bool present, out nint acl, out bool defaulted);
    [DllImport("advapi32")] private static extern uint GetSecurityDescriptorLength(nint descriptor);
    [DllImport("advapi32", SetLastError = true)] private static extern uint GetSecurityInfo(SafeHandle handle,
        int kind, uint information, out nint owner, out nint group, out nint dacl, out nint sacl, out nint descriptor);

    internal static IOException Error(string code, int error) => new(code + ":" + error, new Win32Exception(error));
    internal static byte[] Security()
    {
        var security = new DirectorySecurity(); security.SetAccessRuleProtection(true, false);
        var user = WindowsIdentity.GetCurrent().User ?? throw new IOException("evidence_sid");
        foreach (var sid in new[] { user, new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null) })
            security.AddAccessRule(new FileSystemAccessRule(sid, FileSystemRights.FullControl,
                InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
        return security.GetSecurityDescriptorBinaryForm();
    }
    internal static nint Open(WinHandle? parent, string name, bool directory, bool create, uint share, byte[]? security = null)
    {
        if (parent != null && (name.Length == 0 || name is "." or ".." || name.IndexOfAny(['\\', '/', ':', '\0']) >= 0))
            throw new IOException("evidence_component");
        nint text = 0, unicode = 0, sd = 0; bool added = false;
        try
        {
            parent?.DangerousAddRef(ref added);
            text = Marshal.StringToHGlobalUni(name);
            var u = new UnicodeName { Length = checked((ushort)(name.Length * 2)), MaximumLength = checked((ushort)(name.Length * 2 + 2)), Buffer = text };
            unicode = Marshal.AllocHGlobal(Marshal.SizeOf<UnicodeName>()); Marshal.StructureToPtr(u, unicode, false);
            if (security != null) { sd = Marshal.AllocHGlobal(security.Length); Marshal.Copy(security, 0, sd, security.Length); }
            var a = new Attributes { Length = Marshal.SizeOf<Attributes>(), Root = parent?.DangerousGetHandle() ?? 0,
                Name = unicode, Flags = 0x40, Security = sd };
            uint access = directory ? 0x1000a0u | (create ? 0x60000u : 0) : (create ? 0x110083u : 0x100081u);
            uint options = 0x200000u | 0x20u | (directory ? 1u : 0x40u | 2u);
            int status = NtCreateFile(out nint h, access, ref a, out var io, 0, directory ? 0x10u : 0x80u,
                share, create ? 2u : 1u, options, 0, 0);
            if (status < 0) { if (h != 0 && h != -1) Win.CloseHandle(h); throw Error("evidence_native_open", (int)RtlNtStatusToDosError(status)); }
            if (h == 0 || h == -1 || io.Information != (create ? 2u : 1u))
            { if (h != 0 && h != -1) Win.CloseHandle(h); throw new IOException("evidence_create_identity"); }
            return h;
        }
        finally
        {
            if (added) parent!.DangerousRelease();
            if (text != 0) Marshal.FreeHGlobal(text);
            if (unicode != 0) Marshal.FreeHGlobal(unicode);
            if (sd != 0) Marshal.FreeHGlobal(sd);
        }
    }
    internal static uint AttributeBits(SafeHandle handle)
    {
        byte[] bytes = new byte[8];
        if (!GetFileInformationByHandleEx(handle, 9, bytes, 8)) throw Error("evidence_attributes", Marshal.GetLastWin32Error());
        return BitConverter.ToUInt32(bytes);
    }
    internal static string Identity(SafeHandle handle)
    {
        byte[] bytes = new byte[24];
        if (!GetFileInformationByHandleEx(handle, 18, bytes, 24)) throw Error("evidence_file_id", Marshal.GetLastWin32Error());
        return Convert.ToHexString(bytes);
    }
    internal static string FinalPath(WinHandle handle)
    {
        var b = new StringBuilder(32768); uint n = Win.GetFinalPathNameByHandleW(handle, b, 32768, 0);
        if (n == 0 || n >= 32768) throw new IOException("evidence_final_path");
        return b.ToString();
    }
    internal static void ApplySecurity(WinHandle handle, byte[] security)
    {
        nint sd = Marshal.AllocHGlobal(security.Length);
        try
        {
            Marshal.Copy(security, 0, sd, security.Length);
            if (!GetSecurityDescriptorDacl(sd, out bool present, out nint acl, out _) || !present || acl == 0)
                throw new IOException("evidence_dacl_missing");
            uint error = SetSecurityInfo(handle, 1, 0x80000004, 0, 0, acl, 0);
            if (error != 0) throw Error("evidence_acl", (int)error);
            var actual = ReadSecurity(handle);
            var expected = new RawSecurityDescriptor(security, 0);
            if (!actual.ControlFlags.HasFlag(ControlFlags.DiscretionaryAclProtected) ||
                !AclBytes(actual).AsSpan().SequenceEqual(AclBytes(expected))) throw new IOException("evidence_acl_readback");
        }
        finally { Marshal.FreeHGlobal(sd); }
    }
    private static byte[] AclBytes(RawSecurityDescriptor sd)
    {
        var acl = sd.DiscretionaryAcl ?? throw new IOException("evidence_null_dacl");
        var bytes = new byte[acl.BinaryLength]; acl.GetBinaryForm(bytes, 0); return bytes;
    }
    internal static RawSecurityDescriptor ReadSecurity(WinHandle handle)
    {
        uint error = GetSecurityInfo(handle, 1, 4, out _, out _, out _, out _, out nint sd);
        try
        {
            if (error != 0 || sd == 0) throw Error("evidence_acl_query", (int)error);
            uint length = GetSecurityDescriptorLength(sd);
            if (length is 0 or > 65536) throw new IOException("evidence_acl_size");
            var bytes = new byte[length]; Marshal.Copy(sd, bytes, 0, bytes.Length);
            return new RawSecurityDescriptor(bytes, 0);
        }
        finally { if (sd != 0) Win.LocalFree(sd); }
    }
    internal static void Rename(SafeFileHandle file, WinHandle directory, string name)
    {
        if (nint.Size != 8) throw new IOException("evidence_requires_x64");
        byte[] text = Encoding.Unicode.GetBytes(name);
        byte[] info = new byte[20 + text.Length];
        bool added = false;
        try
        {
            directory.DangerousAddRef(ref added);
            BitConverter.GetBytes(directory.DangerousGetHandle().ToInt64()).CopyTo(info, 8);
            BitConverter.GetBytes(text.Length).CopyTo(info, 16); text.CopyTo(info, 20);
            int status = NtSetInformationFile(file, out _, info, (uint)info.Length, 10);
            if (status < 0) throw Error("evidence_rename", (int)RtlNtStatusToDosError(status));
        }
        finally { if (added) directory.DangerousRelease(); }
    }
}

// Internal deterministic fault/barrier seam. Production has no mutation switch.
internal class EvidencePolicy
{
    internal virtual bool ReparseCheck => true;
    internal virtual bool IdentityCheck => true;
    internal virtual bool DestinationCheck => true;
    internal virtual bool PathOnly => false;
    internal virtual uint DirectoryShare => 3; // allow child creation/rename; never directory delete sharing
    internal virtual void At(string stage, string path, SafeHandle? handle) { }
    internal virtual uint Attributes(SafeHandle handle) => EvidenceNative.AttributeBits(handle);
    internal virtual void ApplySecurity(WinHandle handle, byte[] security) => EvidenceNative.ApplySecurity(handle, security);
    internal virtual string SampleIdentity(SafeHandle handle) => EvidenceNative.Identity(handle);
    internal virtual SafeFileHandle OpenFile(WinHandle parent, string name, bool create) =>
        new(EvidenceNative.Open(parent, name, false, create, create ? 1u : 7u), true);
}

internal sealed class EvidenceDirectory : IDisposable
{
    private readonly List<(WinHandle Handle, string Identity, string Path)> pins = [];
    internal readonly string Path;
    internal readonly EvidencePolicy Policy;
    internal WinHandle Handle => pins.Count > 0 ? pins[^1].Handle : throw new ObjectDisposedException(nameof(EvidenceDirectory));
    internal string Identity => pins.Count > 0 ? pins[^1].Identity : throw new ObjectDisposedException(nameof(EvidenceDirectory));
    internal EvidenceDirectory(string path, EvidencePolicy policy)
    {
        Path = path; Policy = policy;
        Approval.CheckCanonical(path);
        string drive = System.IO.Path.GetPathRoot(path) ?? throw new IOException("evidence_drive");
        byte[] security = EvidenceNative.Security();
        try
        {
            var root = new WinHandle(EvidenceNative.Open(null, @"\??\" + drive, true, false, 3));
            Pin(root, drive);
            string current = drive;
            string[] components = path[drive.Length..].Split('\\');
            for (int i = 0; i < components.Length; i++)
            {
                string component = components[i]; bool create = i == components.Length - 1;
                current = System.IO.Path.Combine(current, component);
                Validate(); policy.At(create ? "before_create" : "before_open", current, Handle);
                var h = new WinHandle(EvidenceNative.Open(Handle, component, true, create,
                    create ? policy.DirectoryShare : 3, create ? security : null));
                try { policy.At(create ? "created_owned" : "opened", current, h); }
                catch { h.Dispose(); throw; }
                Pin(h, current);
                if (create)
                {
                    policy.At("before_acl", current, Handle); Validate();
                    policy.ApplySecurity(Handle, security);
                    policy.At("after_acl", current, Handle); Validate();
                }
            }
        }
        catch { Dispose(); throw; }
    }
    private void Pin(WinHandle handle, string path)
    {
        try
        {
            CheckAttributes(handle, true);
            string id = Policy.SampleIdentity(handle);
            if (!OwnershipRules.PathEquals(EvidenceNative.FinalPath(handle).TrimEnd('\\'), (@"\\?\" + path).TrimEnd('\\')))
                throw new IOException("evidence_directory_path");
            pins.Add((handle, id, path));
        }
        catch { handle.Dispose(); throw; }
    }
    internal void CheckAttributes(SafeHandle handle, bool directory)
    {
        Policy.At("attributes", Path, handle);
        uint bits = Policy.Attributes(handle);
        if (((bits & 0x10) != 0) != directory) throw new IOException("evidence_object_type");
        if (Policy.ReparseCheck && !Policy.PathOnly && (bits & 0x400) != 0) throw new IOException("evidence_reparse");
    }
    internal void Validate()
    {
        if (pins.Count == 0) throw new ObjectDisposedException(nameof(EvidenceDirectory));
        foreach (var pin in pins)
        {
            CheckAttributes(pin.Handle, true);
            if (Policy.IdentityCheck && Policy.SampleIdentity(pin.Handle) != pin.Identity) throw new IOException("evidence_directory_identity");
        }
    }
    internal SafeFileHandle File(string name, bool create)
    {
        Validate(); Policy.At("before_file", name, Handle);
        var h = Policy.OpenFile(Handle, name, create);
        try
        {
            CheckAttributes(h, false); Policy.At("file_opened", name, h);
            if (Policy.DestinationCheck)
            {
                using var check = new SafeFileHandle(EvidenceNative.Open(Handle, name, false, false, 7), true);
                CheckAttributes(check, false);
                if (Policy.SampleIdentity(check) != EvidenceNative.Identity(h)) throw new IOException("evidence_file_identity");
            }
            Validate(); return h;
        }
        catch { h.Dispose(); throw; }
    }
    public void Dispose()
    { foreach (var pin in pins.AsEnumerable().Reverse()) pin.Handle.Dispose(); pins.Clear(); }
}
