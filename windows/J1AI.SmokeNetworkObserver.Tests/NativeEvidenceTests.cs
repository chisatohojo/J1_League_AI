using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Text;
using System.Text.Json;
using J1AI.SmokeNetworkObserver;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeNetworkObserver.Tests;

// Only fresh OS temp directories. Never Approval.Control, diagnostics, or UDFs.
internal static class NativeEvidenceTests
{
    internal sealed class CleanupBlocked(string path, Exception cause) : IOException("native_temp_cleanup_blocked: " + path, cause);
    internal sealed class NotAvailable(string reason) : Exception(reason);
    internal static readonly string[] Mutations = ["skip-reparse", "skip-file-id", "allow-replacement", "path-only", "other-destination"];
    private static string? mutation;
    private static void Check(bool value, string code) => Program.Check(value, code);
    private sealed class TracedEvidence(FileEvidence disk, List<string> trace) : IEvidence
    {
        public void SaveVerified(string name, object value)
        { disk.SaveVerified(name, value); trace.Add("durable:" + name); }
    }
    private sealed class Temp : IDisposable
    {
        internal readonly string Root = Directory.CreateTempSubdirectory("J1AI-observer-native-").FullName;
        internal string Session => Path.Combine(Root, "session");
        internal string Child(string name) => Path.Combine(Root, name);
        internal readonly List<string> Links = [];
        public void Dispose()
        {
            // Targets are always siblings inside this exact owned temporary root.
            try
            {
                foreach (string link in Links) if (Directory.Exists(link)) Directory.Delete(link);
                Directory.Delete(Root, true); // single attempt; no deletion-policy bypass
                Check(!Directory.Exists(Root), "temp_cleanup");
            }
            catch (Exception e) { throw new CleanupBlocked(Root, e); }
        }
    }
    private sealed class Policy : EvidencePolicy
    {
        internal Action<string, string, SafeHandle?>? Hook;
        internal Func<SafeHandle, string>? Id;
        internal Func<SafeHandle, uint>? QueryAttributes;
        internal Action<WinHandle, byte[]>? SetAcl;
        internal WinHandle? Redirect;
        internal readonly HashSet<SafeHandle> Handles = [];
        internal override bool ReparseCheck => mutation != "skip-reparse";
        internal override bool IdentityCheck => mutation != "skip-file-id";
        internal override bool DestinationCheck => mutation != "other-destination";
        internal override bool PathOnly => mutation == "path-only";
        internal override uint DirectoryShare => mutation == "allow-replacement" ? 7u : 3u;
        internal override void At(string stage, string path, SafeHandle? h)
        { if (h != null) Handles.Add(h); Hook?.Invoke(stage, path, h); }
        internal override string SampleIdentity(SafeHandle h) => Id?.Invoke(h) ?? base.SampleIdentity(h);
        internal override uint Attributes(SafeHandle h) => QueryAttributes?.Invoke(h) ?? base.Attributes(h);
        internal override void ApplySecurity(WinHandle h, byte[] security)
        { if (SetAcl != null) SetAcl(h, security); else base.ApplySecurity(h, security); }
        internal override SafeFileHandle OpenFile(WinHandle parent, string name, bool create) =>
            base.OpenFile(create && Redirect != null ? Redirect : parent, name, create);
        internal void Released() => Check(Handles.All(h => h.IsClosed), "all_observed_handles_closed");
    }
    private static void Rejected(Action action, string code)
    {
        Exception? error = null; try { action(); } catch (IOException e) { error = e; }
        Check(error != null && error.Message.Contains(code, StringComparison.Ordinal), "expected_rejection_" + code);
    }
    private static bool RenameDenied(string source, string target)
    {
        try { Directory.Move(source, target); return false; }
        catch (IOException e) { Check((e.HResult & 0xffff) is 5 or 32, "rename_denied_reason"); return true; }
    }
    private static WinHandle OpenDirectory(string path) => Win.CreateFileW(path, 0x20080, 7, 0, 3, 0x02200000, 0);
    private static string FileId(string path)
    { using var h = Win.CreateFileW(path, 0x80, 7, 0, 3, 0x02200000, 0); Check(!h.IsInvalid, "test_handle_open"); return EvidenceNative.Identity(h); }
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(WinHandle handle, uint code, byte[] input, uint length,
        nint output, uint outputLength, out uint returned, nint overlapped);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)] [return: MarshalAs(UnmanagedType.U1)]
    private static extern bool CreateSymbolicLinkW(string link, string target, uint flags);
    [StructLayout(LayoutKind.Sequential)] private struct AttributeTag
    { internal uint Attributes, ReparseTag; }
    [DllImport("kernel32", SetLastError = true)] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandleEx(WinHandle handle, int kind, out AttributeTag info, uint size);
    private static void Junction(Temp temp, string link, string target)
    {
        Check(Path.GetDirectoryName(link) == temp.Root && Path.GetDirectoryName(target) == temp.Root, "junction_scope");
        Directory.CreateDirectory(link); temp.Links.Add(link);
        using var h = Win.CreateFileW(link, 0x40000000, 3, 0, 3, 0x02200000, 0);
        Check(!h.IsInvalid, "junction_handle");
        byte[] substitute = Encoding.Unicode.GetBytes(@"\??\" + target), print = Encoding.Unicode.GetBytes(target);
        byte[] data = new byte[16 + substitute.Length + 2 + print.Length + 2];
        BitConverter.GetBytes(0xa0000003u).CopyTo(data, 0);
        BitConverter.GetBytes(checked((ushort)(data.Length - 8))).CopyTo(data, 4);
        BitConverter.GetBytes(checked((ushort)substitute.Length)).CopyTo(data, 10);
        BitConverter.GetBytes(checked((ushort)(substitute.Length + 2))).CopyTo(data, 12);
        BitConverter.GetBytes(checked((ushort)print.Length)).CopyTo(data, 14);
        substitute.CopyTo(data, 16); print.CopyTo(data, 18 + substitute.Length);
        Check(DeviceIoControl(h, 0x900a4, data, (uint)data.Length, 0, 0, out _, 0), "junction_create_error_" + Marshal.GetLastWin32Error());
    }
    internal static void Register(Action<string, Action> add, Action<string, Func<Task>> async, string? selectedMutation)
    {
        mutation = selectedMutation;
        add("native_new_directory_acl_and_identity", () =>
        {
            using var t = new Temp(); var p = new Policy(); string id;
            using (var store = new FileEvidence(t.Session, p))
            {
                id = store.DirectoryIdentity; Check(id == FileId(t.Session), "created_same_object");
                using var h = OpenDirectory(t.Session); var acl = EvidenceNative.ReadSecurity(h);
                Check(acl.ControlFlags.HasFlag(ControlFlags.DiscretionaryAclProtected) && acl.DiscretionaryAcl?.Count == 2, "private_acl");
                store.SaveVerified("raw", new { Value = "synthetic" }); store.SaveVerified("verdict", new { Allowed = false });
                Check(store.DirectoryIdentity == id && File.Exists(Path.Combine(t.Session, "raw.json")) && File.Exists(Path.Combine(t.Session, "verdict.json")), "exact_destination");
            }
            p.Released(); Check(FileId(t.Session) == id, "same_object_after_dispose");
        });
        add("native_existing_ancestors_verified", () =>
        {
            using var t = new Temp(); string before = FileId(t.Root); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p)) Check(FileId(t.Root) == before, "ancestor_file_id");
            p.Released();
        });
        add("native_existing_session_never_adopted", () =>
        {
            using var t = new Temp(); Directory.CreateDirectory(t.Session); string id = FileId(t.Session); var p = new Policy();
            Rejected(() => { using var s = new FileEvidence(t.Session, p); }, "evidence_native_open");
            Check(FileId(t.Session) == id && !Directory.EnumerateFileSystemEntries(t.Session).Any(), "existing_untouched"); p.Released();
        });
        add("native_competing_create_before_atomic_create", () =>
        {
            using var t = new Temp(); var p = new Policy { Hook = (s, path, _) => { if (s == "before_create") Directory.CreateDirectory(path); } };
            Rejected(() => { using var store = new FileEvidence(t.Session, p); }, "evidence_native_open");
            Check(!Directory.EnumerateFileSystemEntries(t.Session).Any(), "competitor_not_used"); p.Released();
        });
        foreach (string stage in new[] { "created_owned", "before_acl", "after_acl" })
            add("native_no_create_open_gap_" + stage, () =>
            {
                using var t = new Temp(); var p = new Policy(); bool reached = false;
                p.Hook = (s, path, h) => { if (s != stage) return; reached = true;
                    Check(h != null && !h.IsClosed && EvidenceNative.Identity(h) == FileId(path), "handle_already_owned");
                    Check(RenameDenied(path, t.Child("replaced")), "directory_rename_prevented"); };
                using (var store = new FileEvidence(t.Session, p)) Check(reached, "barrier_reached");
                p.Released();
            });
        foreach (string stage in new[] { "before_file", "write", "write_partial", "flush", "read_pending", "commit", "read_committed" })
            add("native_rename_delete_denied_" + stage, () =>
            {
                using var t = new Temp(); var p = new Policy(); int reached = 0;
                using (var store = new FileEvidence(t.Session, p))
                {
                    p.Hook = (s, _, _) => { if (s != stage) return; reached++;
                        Check(RenameDenied(t.Session, t.Child("moved")), "directory_rename_prevented");
                        try { Directory.Delete(t.Session); throw new InvalidOperationException("directory_delete_allowed"); }
                        catch (IOException) { Check(Directory.Exists(t.Session), "directory_still_exists"); } };
                    store.SaveVerified("raw", new { Value = "barrier" });
                    Check(reached > 0 && File.Exists(Path.Combine(t.Session, "raw.json")), "stage_and_saved");
                }
                p.Released(); Directory.Move(t.Session, t.Child("after_dispose"));
            });
        add("native_ancestor_rename_denied", () =>
        {
            using var t = new Temp(); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p)) Check(RenameDenied(t.Root, t.Root + "-moved"), "ancestor_locked");
            p.Released();
        });
        add("native_junction_before_ancestor_open_rejected", () =>
        {
            using var t = new Temp(); string target = t.Child("target"), link = t.Child("link"); Directory.CreateDirectory(target);
            var p = new Policy { Hook = (s, path, _) => { if (s == "before_open" && path == link) Junction(t, link, target); } };
            Rejected(() => { using var store = new FileEvidence(Path.Combine(link, "session"), p); }, "evidence_reparse");
            Check(!Directory.EnumerateFileSystemEntries(target).Any(), "junction_target_untouched"); p.Released();
        });
        add("native_junction_competing_session_rejected", () =>
        {
            using var t = new Temp(); string target = t.Child("target"); Directory.CreateDirectory(target);
            var p = new Policy { Hook = (s, _, _) => { if (s == "before_create") Junction(t, t.Session, target); } };
            Rejected(() => { using var store = new FileEvidence(t.Session, p); }, "evidence_native_open");
            Check(!Directory.EnumerateFileSystemEntries(target).Any(), "junction_not_adopted"); p.Released();
        });
        add("native_path_check_to_open_junction_replacement_rejected", () =>
        {
            using var t = new Temp(); string target = t.Child("target"), link = t.Child("link"), old = t.Child("old");
            Directory.CreateDirectory(target); Directory.CreateDirectory(link);
            Approval.CheckPath(link); string originalId = FileId(link); bool reached = false;
            var p = new Policy { Hook = (s, path, _) =>
            {
                if (s != "before_open" || path != link) return;
                reached = true; Directory.Move(link, old); Junction(t, link, target);
            } };
            Rejected(() => { using var store = new FileEvidence(Path.Combine(link, "session"), p); }, "evidence_reparse");
            Check(reached && FileId(old) == originalId && !Directory.EnumerateFileSystemEntries(target).Any(),
                "path_validation_not_authority_after_replacement"); p.Released();
        });
        add("native_junction_after_handle_open_rejected", () =>
        {
            using var t = new Temp(); string target = t.Child("target"), link = t.Child("link");
            Directory.CreateDirectory(target); Directory.CreateDirectory(link); string id = FileId(link); bool reached = false;
            var p = new Policy { Hook = (s, path, h) =>
            {
                if (s != "opened" || path != link) return;
                reached = true; Check(h != null && EvidenceNative.Identity(h) == id, "normal_directory_opened_first");
                Junction(t, link, target);
                Check((EvidenceNative.AttributeBits(h!) & 0x400) != 0 && EvidenceNative.Identity(h!) == id, "held_object_reparse_changed");
            } };
            Rejected(() => { using var store = new FileEvidence(Path.Combine(link, "session"), p); }, "evidence_reparse");
            Check(reached && !Directory.EnumerateFileSystemEntries(target).Any(), "held_reparse_no_write"); p.Released();
        });
        add("native_symlink_ancestor_rejected", () =>
        {
            using var t = new Temp(); string target = t.Child("target"), link = t.Child("link"); Directory.CreateDirectory(target);
            bool made = CreateSymbolicLinkW(link, target, 3); int error = Marshal.GetLastWin32Error();
            if (!made) throw new NotAvailable("symlink_creation_privilege_or_policy_error_" + error);
            t.Links.Add(link); var p = new Policy();
            string linkId, targetId = FileId(target); bool openedSymlink = false;
            using (var h = OpenDirectory(link))
            {
                Check(!h.IsInvalid, "symlink_handle_open");
                Check(GetFileInformationByHandleEx(h, 9, out var tag, 8), "symlink_tag_query");
                Check(tag.ReparseTag == 0xa000000cu && (tag.Attributes & 0x410u) == 0x410u, "actual_directory_symlink_tag");
                linkId = EvidenceNative.Identity(h);
                Check(linkId != targetId, "symlink_not_target_identity");
            }
            p.Hook = (stage, path, h) =>
            {
                if (stage != "opened" || path != link) return;
                openedSymlink = true;
                Check(h != null && EvidenceNative.Identity(h) == linkId, "observer_opened_exact_symlink_object");
            };
            Rejected(() => { using var store = new FileEvidence(Path.Combine(link, "session"), p); }, "evidence_reparse");
            Check(openedSymlink && FileId(link) == linkId && FileId(target) == targetId, "symlink_target_identity_unchanged");
            Check(!Directory.EnumerateFileSystemEntries(target).Any(), "symlink_target_untouched"); p.Released();
        });
        add("native_file_id_mismatch_rejected", () =>
        {
            using var t = new Temp(); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p))
            {
                using var other = OpenDirectory(t.Root);
                p.Id = _ => EvidenceNative.Identity(other);
                Rejected(() => store.SaveVerified("raw", new { Value = 1 }), "evidence_directory_identity");
                Check(!Directory.EnumerateFileSystemEntries(t.Session).Any(), "id_mismatch_no_write");
            }
            p.Released();
        });
        add("native_open_removed_ancestor_fails_closed", () =>
        {
            using var t = new Temp(); string parent = t.Child("parent"), moved = t.Child("moved");
            Directory.CreateDirectory(parent); string id = FileId(parent); var p = new Policy();
            p.Hook = (s, path, _) => { if (s == "before_open" && path == parent) Directory.Move(parent, moved); };
            Rejected(() => { using var store = new FileEvidence(Path.Combine(parent, "session"), p); }, "evidence_native_open");
            Check(FileId(moved) == id && !Directory.EnumerateFileSystemEntries(moved).Any(), "removed_ancestor_never_used");
            p.Released();
        });
        add("native_attribute_query_error_releases_handles", () =>
        {
            using var t = new Temp(); var p = new Policy();
            // Real GetFileInformationByHandleEx failure on an invalid injected handle,
            // not a manufactured successful attribute response or managed-only throw.
            p.QueryAttributes = _ => { using var invalid = new WinHandle(-1); return EvidenceNative.AttributeBits(invalid); };
            Rejected(() => { using var store = new FileEvidence(t.Session, p); }, "evidence_attributes:6");
            Check(!Directory.Exists(t.Session), "attribute_error_no_directory"); p.Released();
        });
        add("native_acl_access_denied_releases_handles", () =>
        {
            using var t = new Temp(); var p = new Policy();
            p.SetAcl = (held, security) =>
            {
                using var readOnly = OpenDirectory(t.Session);
                Check(EvidenceNative.Identity(readOnly) == EvidenceNative.Identity(held), "acl_same_object");
                // This actual handle lacks WRITE_DAC. SetSecurityInfo must fail;
                // no machine/user policy or real destination ACL is modified.
                EvidenceNative.ApplySecurity(readOnly, security);
            };
            Rejected(() => { using var store = new FileEvidence(t.Session, p); }, "evidence_acl:5");
            Check(!Directory.EnumerateFileSystemEntries(t.Session).Any(), "acl_failure_no_evidence");
            p.Released(); Directory.Move(t.Session, t.Child("released"));
        });
        add("native_wrong_file_destination_rejected", () =>
        {
            using var t = new Temp(); string other = t.Child("other"); Directory.CreateDirectory(other);
            var p = new Policy();
            using (var store = new FileEvidence(t.Session, p))
            using (var redirect = OpenDirectory(other))
            {
                p.Redirect = redirect;
                Rejected(() => store.SaveVerified("raw", new { Value = 1 }), "evidence_native_open");
                Check(!File.Exists(Path.Combine(t.Session, "raw.json")) && File.Exists(Path.Combine(other, "raw.json.pending")), "wrong_destination_not_committed");
            }
            p.Released();
        });
        foreach (string stage in new[] { "before_open", "attributes", "created_owned", "before_acl", "after_acl" })
            add("native_setup_fault_releases_handles_" + stage, () =>
            {
                using var t = new Temp(); var p = new Policy { Hook = (s, _, _) => { if (s == stage) throw new IOException("injected_" + stage); } };
                Rejected(() => { using var store = new FileEvidence(t.Session, p); }, "injected_" + stage);
                p.Released();
                string moved = t.Child("moved"); if (Directory.Exists(t.Session)) Directory.Move(t.Session, moved);
            });
        foreach (string stage in new[] { "write_partial", "flush", "read_pending", "commit", "read_committed" })
            foreach (string document in new[] { "raw", "verdict" })
                async("native_io_fault_" + document + "_" + stage, async () =>
                {
                    using var t = new Temp(); var p = new Policy(); var stop = new FakeStop([]); Summary result;
                    using (var store = new FileEvidence(t.Session, p))
                    {
                        p.Hook = (s, name, _) => { if (s == stage && name.EndsWith(document, StringComparison.Ordinal)) throw new IOException("injected_" + stage); };
                        var observer = new Observation(Values.Contract, store, stop);
                        await observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")]));
                        result = await observer.Complete(false);
                        Check(stop.Calls == 1 && result.Result == Result.INCONCLUSIVE, "failed_io_still_stops");
                    }
                    p.Released();
                    using var json = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(t.Session, "result.json")));
                    Check(json.RootElement.GetProperty("Result").GetInt32() == (int)Result.INCONCLUSIVE, "no_success_result");
                });
        add("native_committed_file_held_and_readback", () =>
        {
            using var t = new Temp(); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p))
            {
                store.SaveVerified("raw", new { Value = "synthetic" }); string path = Path.Combine(t.Session, "raw.json");
                string id = FileId(path);
                using var read = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                using var json = JsonDocument.Parse(read);
                Check(json.RootElement.GetProperty("Value").GetString() == "synthetic", "raw_readback");
                try { File.Move(path, path + ".moved"); throw new InvalidOperationException("committed_file_rename_allowed"); }
                catch (IOException) { Check(FileId(path) == id, "committed_same_object"); }
            }
            p.Released();
        });
        add("native_no_overwrite_existing_file", () =>
        {
            using var t = new Temp(); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p))
            {
                store.SaveVerified("raw", new { Value = 1 }); string id = FileId(Path.Combine(t.Session, "raw.json"));
                Rejected(() => store.SaveVerified("raw", new { Value = 2 }), "evidence_rename");
                Check(FileId(Path.Combine(t.Session, "raw.json")) == id, "committed_not_overwritten");
            }
            p.Released();
        });
        async("native_all_writes_fail_still_stops_without_receipt", async () =>
        {
            using var t = new Temp(); var p = new Policy(); var stop = new FakeStop([]);
            using (var store = new FileEvidence(t.Session, p))
            {
                p.Hook = (stage, _, _) => { if (stage == "write_partial") throw new IOException("injected_all_writes"); };
                var observer = new Observation(Values.Contract, store, stop);
                await observer.Accept(Values.Snapshot()); var result = await observer.Complete(false);
                Check(stop.Calls == 1 && result.Result == Result.INCONCLUSIVE &&
                    result.Reasons.Contains("failure_evidence_write_failed"), "all_writes_failed_stop_and_inconclusive");
            }
            p.Released();
            Check(!File.Exists(Path.Combine(t.Session, "result.json")) &&
                !File.Exists(Path.Combine(t.Session, "result-receipt.json")) &&
                Directory.EnumerateFiles(t.Session).All(f => f.EndsWith(".pending", StringComparison.Ordinal)), "no_complete_evidence");
        });
        async("native_disk_raw_verdict_verified_before_fake_stop", async () =>
        {
            using var t = new Temp(); var p = new Policy(); var trace = new List<string>(); var stop = new FakeStop(trace);
            using (var store = new FileEvidence(t.Session, p))
            {
                var observer = new Observation(Values.Contract, new TracedEvidence(store, trace), stop);
                await observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")]));
                Check(trace.SequenceEqual(["durable:000001-raw", "durable:000001-verdict", "stop"]), "disk_durability_before_stop");
                Check(stop.Calls == 1 && stop.Identity == Observation.Identity, "fixed_identity_fake_stop");
                await observer.Accept(Values.End());
                Check((await observer.Complete(true)).Result == Result.BLOCKED, "denial_not_success");
            }
            p.Released();
            using var raw = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(t.Session, "000001-raw.json")));
            using var verdict = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(t.Session, "000001-verdict.json")));
            Check(raw.RootElement.ValueKind == JsonValueKind.Object && verdict.RootElement.ValueKind == JsonValueKind.Object,
                "actual_raw_verdict_documents");
        });
        add("native_cleanup_error_still_releases_all_handles", () =>
        {
            using var t = new Temp(); var p = new Policy();
            using (var store = new FileEvidence(t.Session, p))
            {
                store.SaveVerified("raw", new { Value = 1 }); store.SaveVerified("verdict", new { Value = 2 });
                int closed = 0;
                p.Hook = (stage, _, _) => { if (stage == "close_file" && ++closed == 1) throw new IOException("injected_cleanup"); };
                Rejected(store.Dispose, "evidence_cleanup_failed");
                Check(closed == 2, "all_file_closes_attempted"); p.Released();
                File.Move(Path.Combine(t.Session, "raw.json"), Path.Combine(t.Session, "raw-released.json"));
                Directory.Move(t.Session, t.Child("released"));
            }
            p.Released();
        });
    }
}
