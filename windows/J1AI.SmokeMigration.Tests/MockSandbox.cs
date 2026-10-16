using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;
using J1AI.SmokeMigration;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeMigration.Tests;

internal sealed class NativeFailure(string api, int status, uint win32) : IOException(api + ":" + win32)
{
    internal string Api => api;
    internal uint Status => unchecked((uint)status);
    internal uint Win32 => win32;
}

// ALL mutation APIs live in the test assembly. Private construction grants a
// capability for ONE generated child of the exact authorized artifacts root.
// There is no constructor accepting an arbitrary root, source or target path.
internal sealed class MockSandbox : IDisposable
{
    internal static readonly string Allowed = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "J1AI", "BuildCandidates", "coordination-migration-tests-observability-01");
    internal readonly string Root, Identity = "migration-test-" + Guid.NewGuid().ToString("N");
    private readonly ReadPin container;
    private readonly SafeFileHandle root = null!;
    private readonly Dictionary<string, SafeFileHandle> areas = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> directoryIds = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> fileIds = new(StringComparer.Ordinal);
    private readonly Dictionary<string, string> ownedFileIds = new(StringComparer.Ordinal);
    private bool disposed;
    private string? lockId;
    internal static int LiveHandles;
    internal static bool CleanupFailed;
    internal Action<string, string> IoFault = (_, _) => { };
    [StructLayout(LayoutKind.Sequential)] private struct Unicode { internal ushort Length, Maximum; internal nint Buffer; }
    [StructLayout(LayoutKind.Sequential)] private struct Attributes { internal int Length; internal nint Root, Name; internal uint Flags; internal nint Security, Quality; }
    [StructLayout(LayoutKind.Sequential)] private struct Io { internal nint Status; internal nuint Information; }
    [DllImport("ntdll")] private static extern int NtCreateFile(out nint h, uint access, ref Attributes a, out Io io, nint allocation, uint attrs, uint share, uint disposition, uint options, nint ea, uint length);
    [DllImport("ntdll")] private static extern uint RtlNtStatusToDosError(int status);
    [DllImport("ntdll")] private static extern int NtSetInformationFile(SafeFileHandle h, out Io io, byte[] info, uint size, int kind);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool FlushFileBuffers(SafeFileHandle h);
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetFileInformationByHandleEx(SafeFileHandle h, int kind, byte[] info, uint size);
    [DllImport("advapi32", SetLastError = true)] private static extern uint SetSecurityInfo(SafeFileHandle h, int type, uint info, nint owner, nint group, nint dacl, nint sacl);
    [DllImport("advapi32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)] private static extern bool GetSecurityDescriptorDacl(nint sd, out bool present, out nint acl, out bool defaulted);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateSymbolicLinkW(string path, string target, uint flags);
    private static void CheckStatus(int status, string code)
    { if (status < 0) throw new NativeFailure(code, status, RtlNtStatusToDosError(status)); }
    private static void Component(string name)
    { Contract.Require(name.Length > 0 && name is not "." and not ".." && name.IndexOfAny(['\\', '/', ':', '\0']) < 0 && !name.EndsWith('.') && !name.EndsWith(' '), "mock_component"); }
    private static byte[] PrivateSecurity()
    {
        var sid = WindowsIdentity.GetCurrent().User!; var sd = new DirectorySecurity();
        sd.SetOwner(sid); sd.SetAccessRuleProtection(true, false);
        foreach (var s in new[] { sid, new SecurityIdentifier("S-1-5-18") })
            sd.AddAccessRule(new(s, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
                PropagationFlags.None, AccessControlType.Allow));
        return sd.GetSecurityDescriptorBinaryForm();
    }
    internal static SafeFileHandle Open(SafeFileHandle parent, string name, bool directory, bool create, bool delete = false, bool write = false, uint? shareOverride = null)
    {
        Component(name); nint txt = 0, u = 0, sd = 0; bool held = false;
        try
        {
            parent.DangerousAddRef(ref held); txt = Marshal.StringToHGlobalUni(name);
            var unicode = new Unicode { Length = checked((ushort)(name.Length * 2)), Maximum = checked((ushort)(name.Length * 2 + 2)), Buffer = txt };
            u = Marshal.AllocHGlobal(Marshal.SizeOf<Unicode>()); Marshal.StructureToPtr(unicode, u, false);
            if (create && directory) { byte[] security = PrivateSecurity(); sd = Marshal.AllocHGlobal(security.Length); Marshal.Copy(security, 0, sd, security.Length); }
            var a = new Attributes { Length = Marshal.SizeOf<Attributes>(), Root = parent.DangerousGetHandle(), Name = u, Flags = 0x40, Security = sd };
            uint access = directory ? 0x1200a0u | (create ? 0x40000u : 0) : create ? 0x130083u : 0x120081u;
            if (delete) access |= 0x10000;
            if (write && !directory) access |= 2;
            uint options = 0x200000u | 0x20 | (directory ? 1u : 0x40u | (create ? 2u : 0));
            int status = NtCreateFile(out nint raw, access, ref a, out var io, 0, directory ? 0x10u : 0x80u, shareOverride ?? (directory ? 3u : 7u),
                create ? 2u : 1u, options, 0, 0);
            var handle = new SafeFileHandle(raw, true);
            try
            {
                CheckStatus(status, "mock_open"); Contract.Require(!handle.IsInvalid && io.Information == (create ? 2u : 1u), "mock_disposition");
                if (!delete) ReadPin.Check(handle, directory);
                return handle;
            }
            catch { handle.Dispose(); throw; }
        }
        finally { if (held) parent.DangerousRelease(); if (txt != 0) Marshal.FreeHGlobal(txt); if (u != 0) Marshal.FreeHGlobal(u); if (sd != 0) Marshal.FreeHGlobal(sd); }
    }
    private MockSandbox()
    {
        ReadPin.Canonical(Allowed); container = new(Allowed, true);
        try
        {
            ReadPin.RequirePrivate(container.Handle);
            Contract.Require(container.ObjectId == ObservationPaths.RootId, "authorized_container_identity");
            ObservationSession.Require().Intent("directory", Identity);
            Root = Path.Combine(Allowed, Identity); root = Open(container.Handle, Identity, true, true);
            LiveHandles++; directoryIds[""] = ReadPin.Identity(root);
            ReadPin.RequirePrivate(root);
            ObservationSession.Require().Created("directory", Identity, root);
            foreach (string name in new[] { "active", "candidate", "backup" })
            {
                ObservationSession.Require().Intent("directory", Identity + "/" + name);
                var h = Open(root, name, true, true); areas.Add(name, h); LiveHandles++; directoryIds[name] = ReadPin.Identity(h); ReadPin.RequirePrivate(h);
                ObservationSession.Require().Created("directory", Identity + "/" + name, h);
            }
            ObservationSession.Require().Intent("file", Identity + "/smoke.lock");
            using var lockFile = Open(root, "smoke.lock", false, true); lockId = ReadPin.Identity(lockFile);
            ObservationSession.Require().Created("file", Identity + "/smoke.lock", lockFile);
        }
        catch { if (root != null) Dispose(); else container.Dispose(); throw; }
    }
    internal static MockSandbox Create() => new();
    internal FileStream AcquireLock()
    {
        Validate(); var h = Open(root, "smoke.lock", false, false, write: true, shareOverride: 0);
        try { Contract.Require(ReadPin.Identity(h) == lockId, "mock_lock_replaced"); return new FileStream(h, FileAccess.ReadWrite); }
        catch { h.Dispose(); throw; }
    }
    internal void Validate()
    {
        Contract.Require(!disposed, "mock_disposed"); container.Verify();
        Contract.Require(ReadPin.Identity(root) == directoryIds[""], "mock_root_changed"); ReadPin.Check(root, true); ReadPin.RequirePrivate(root);
        foreach (var item in areas) { Contract.Require(ReadPin.Identity(item.Value) == directoryIds[item.Key], "mock_directory_changed"); ReadPin.Check(item.Value, true); ReadPin.RequirePrivate(item.Value); }
    }
    internal void Put(string area, string name, byte[] bytes)
    {
        Validate(); Contract.Require(areas.ContainsKey(area), "mock_area");
        ObservationSession.Require().Intent("file", Identity + "/" + area + "/" + name);
        using var h = Open(areas[area], name, false, true); LiveHandles++;
        try
        {
            fileIds[area + "/" + name] = ReadPin.Identity(h);
            ownedFileIds[area + "/" + name] = fileIds[area + "/" + name];
            ObservationSession.Require().Created("file", Identity + "/" + area + "/" + name, h);
            using var borrowed = new SafeFileHandle(h.DangerousGetHandle(), false); using var stream = new FileStream(borrowed, FileAccess.ReadWrite);
            stream.Write(bytes); IoFault("flush", area + "/" + name); stream.Flush(true); Contract.Require(FlushFileBuffers(h), "mock_flush");
            IoFault("readback", area + "/" + name);
            stream.Position = 0; var read = new byte[bytes.Length]; stream.ReadExactly(read); Contract.Require(read.SequenceEqual(bytes), "mock_write_readback");
            using var named = Open(areas[area], name, false, false); Contract.Require(ReadPin.Identity(named) == fileIds[area + "/" + name], "mock_named_identity");
        }
        finally { LiveHandles--; }
    }
    internal byte[] Read(string area, string name)
    {
        Validate(); using var h = Open(areas[area], name, false, false); string id = ReadPin.Identity(h);
        Contract.Require(fileIds.TryGetValue(area + "/" + name, out var expected) && id == expected, "mock_file_replaced");
        using var borrowed = new SafeFileHandle(h.DangerousGetHandle(), false); using var stream = new FileStream(borrowed, FileAccess.Read);
        Contract.Require(stream.Length <= 1024 * 1024, "mock_read_limit"); var bytes = new byte[(int)stream.Length]; stream.ReadExactly(bytes); return bytes;
    }
    internal bool Exists(string area, string name) => File.Exists(Path.Combine(Root, area, name)) || Directory.Exists(Path.Combine(Root, area, name)) || new FileInfo(Path.Combine(Root, area, name)).LinkTarget != null;
    internal string[] Names(string area) => Directory.EnumerateFileSystemEntries(Path.Combine(Root, area)).Select(Path.GetFileName).Select(n => n!).Order(StringComparer.Ordinal).ToArray();
    internal void Replace(string name, byte[] bytes, string oldHash)
    {
        Validate(); Contract.Require(Contract.Hash(Read("active", name)) == oldHash, "mock_target_changed");
        string stage = "stage-" + Guid.NewGuid().ToString("N"); Put("active", stage, bytes);
        using var h = Open(areas["active"], stage, false, false, true);
        string id = ReadPin.Identity(h); Contract.Require(id == fileIds["active/" + stage], "mock_stage_changed");
        // Stage creation/readback completed BEFORE the last target identity check.
        Contract.Require(Contract.Hash(Read("active", name)) == oldHash, "mock_target_changed");
        byte[] text = Encoding.Unicode.GetBytes(name), info = new byte[20 + text.Length];
        info[0] = 1; BitConverter.GetBytes(areas["active"].DangerousGetHandle().ToInt64()).CopyTo(info, 8);
        BitConverter.GetBytes(text.Length).CopyTo(info, 16); text.CopyTo(info, 20);
        CheckStatus(NtSetInformationFile(h, out _, info, (uint)info.Length, 10), "mock_atomic_replace");
        ObservationSession.Require().Renamed(Identity + "/active/" + stage, Identity + "/active/" + name, h);
        fileIds.Remove("active/" + stage); fileIds["active/" + name] = id;
        ownedFileIds.Remove("active/" + stage); ownedFileIds["active/" + name] = id;
        Contract.Require(Contract.Hash(Read("active", name)) == Contract.Hash(bytes), "mock_replace_readback");
    }
    internal void Remove(string area, string name)
    {
        Validate();
        using (var h = Open(areas[area], name, false, false, true))
        {
            Contract.Require(ReadPin.Identity(h) == fileIds[area + "/" + name], "mock_cleanup_identity");
            ObservationSession.Require().VerifyOwned(Identity + "/" + area + "/" + name, h);
            IoFault("remove_before", area + "/" + name);
            CheckStatus(NtSetInformationFile(h, out _, [1], 1, 13), "mock_delete"); fileIds.Remove(area + "/" + name); ownedFileIds.Remove(area + "/" + name);
        } // Delete-on-close completed before the after-removal fault injection.
        IoFault("remove_after", area + "/" + name);
    }
    internal void ChangeFileForTest(string area, string name, bool sameBytes)
    {
        byte[] bytes = Read(area, name); string before = fileIds[area + "/" + name];
        Remove(area, name); Put(area, name, sameBytes ? bytes : Encoding.UTF8.GetBytes("tampered"));
        Contract.Require(ownedFileIds[area + "/" + name] != before, "test_replacement_object_not_distinct");
        fileIds[area + "/" + name] = before;
    }
    internal void FaultSecurity(string mode)
    {
        // Same handle/owned mock only. No real ACL/owner/settings mutation.
        var current = ReadPin.Security(root);
        if (mode == "owner") ReadPin.RequirePrivate(root, true, "S-1-5-18");
        else
        {
            ObservationSession.Require().VerifyOwned(Identity, root);
            byte[] raw = new byte[current.BinaryLength]; current.GetBinaryForm(raw, 0); nint sd = Marshal.AllocHGlobal(raw.Length);
            try
            {
                Marshal.Copy(raw, 0, sd, raw.Length); Contract.Require(GetSecurityDescriptorDacl(sd, out bool present, out nint acl, out _) && present, "test_acl");
                Contract.Require(SetSecurityInfo(root, 1, 0x20000004, 0, 0, acl, 0) == 0, "test_acl_set");
                ObservationSession.Require().RecordTestDaclMutation(Identity, root);
            }
            finally { Marshal.FreeHGlobal(sd); }
        }
    }
    internal void RestoreForCleanup() // Test tampering never changes the cleanup object's recorded actual IDs.
    {
        foreach (var item in ownedFileIds) fileIds[item.Key] = item.Value;
    }
    internal void CorruptForTest(string area, string name)
    {
        Validate(); using var h = Open(areas[area], name, false, false, write: true);
        Contract.Require(ReadPin.Identity(h) == ownedFileIds[area + "/" + name], "test_corrupt_identity");
        using var borrowed = new SafeFileHandle(h.DangerousGetHandle(), false); using var stream = new FileStream(borrowed, FileAccess.ReadWrite);
        int b = stream.ReadByte(); Contract.Require(b >= 0, "test_empty_file"); stream.Position = 0; stream.WriteByte((byte)(b ^ 255)); stream.Flush(true);
    }
    internal uint SymlinkTagForTest(string name)
    {
        using var h = Open(areas["active"], name, true, false, true); byte[] tag = new byte[8];
        Contract.Require(GetFileInformationByHandleEx(h, 9, tag, 8), "test_tag_query");
        ObservationSession.Require().Created("symlink", Identity + "/active/" + name, h);
        return BitConverter.ToUInt32(tag, 4);
    }
    internal void RemoveTestSymlink(string name)
    {
        Contract.Require(name == "link" && ObservationSession.Require().Request.Test == "real_symlink_reparse_rejected", "test_symlink_scope");
        using var h = Open(areas["active"], name, true, false, true);
        ObservationSession.Require().VerifyOwned(Identity + "/active/" + name, h);
        CheckStatus(NtSetInformationFile(h, out _, [1], 1, 13), "test_symlink_delete");
    }
    public void Dispose()
    {
        if (disposed) return;
        try { ObservationSession.Require().CleanupStart(Identity); Cleanup(); ObservationSession.Require().CleanupEnd(Identity); }
        catch { CleanupFailed = true; throw; }
        finally
        {
            // Even an identity-query/delete failure releases owned handles
            // synchronously. The residue is NOT adopted, retried or reused.
            foreach (var h in areas.Values) if (!h.IsClosed) { h.Dispose(); LiveHandles--; }
            if (!root.IsClosed) { root.Dispose(); LiveHandles--; }
            container.Dispose(); disposed = true;
        }
    }
    private void Cleanup()
    {
        if (disposed) return;
        ObservationSession.Require().VerifyOwned(Identity, root);
        foreach (var area in areas) ObservationSession.Require().VerifyOwned(Identity + "/" + area.Key, area.Value);
        // Close own directory handles, then reopen each child relative to the
        // pinned parent and compare recorded IDs before deletion. No recursive
        // path-based delete, no retries, no ACL repairs, no target expansion.
        foreach (var item in areas)
        {
            foreach (string name in Names(item.Key))
            {
                using var h = Open(item.Value, name, false, false, true);
                Contract.Require(ownedFileIds.TryGetValue(item.Key + "/" + name, out var id) && ReadPin.Identity(h) == id, "cleanup_unknown_object");
                ObservationSession.Require().VerifyOwned(Identity + "/" + item.Key + "/" + name, h);
                CheckStatus(NtSetInformationFile(h, out _, [1], 1, 13), "cleanup_file");
            }
            item.Value.Dispose(); LiveHandles--;
            using var dir = Open(root, item.Key, true, false, true); Contract.Require(ReadPin.Identity(dir) == directoryIds[item.Key], "cleanup_directory_id");
            CheckStatus(NtSetInformationFile(dir, out _, [1], 1, 13), "cleanup_directory");
        }
        areas.Clear();
        if (lockId != null)
        {
            using var lockFile = Open(root, "smoke.lock", false, false, true);
            Contract.Require(ReadPin.Identity(lockFile) == lockId, "cleanup_lock_id");
            ObservationSession.Require().VerifyOwned(Identity + "/smoke.lock", lockFile);
            CheckStatus(NtSetInformationFile(lockFile, out _, [1], 1, 13), "cleanup_lock");
        }
        root.Dispose(); LiveHandles--;
        using (var dir = Open(container.Handle, Identity, true, false, true))
        { Contract.Require(ReadPin.Identity(dir) == directoryIds[""], "cleanup_root_id"); CheckStatus(NtSetInformationFile(dir, out _, [1], 1, 13), "cleanup_root"); }
        disposed = true; container.Dispose(); Contract.Require(!Directory.Exists(Root), "cleanup_root_remains");
    }
}
