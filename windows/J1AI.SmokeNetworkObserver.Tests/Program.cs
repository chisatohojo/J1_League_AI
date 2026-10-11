using System.Text.Json;
using J1AI.SmokeNetworkObserver;

namespace J1AI.SmokeNetworkObserver.Tests;

internal static class Program
{
    private static readonly List<(string Name, Func<Task> Test)> Cases = [];
    private static ObservationPolicy policy = new();
    internal static void Check(bool value, string reason = "assertion") { if (!value) throw new InvalidOperationException(reason); }
    private static void Add(string name, Action test) => Cases.Add((name, () => { test(); return Task.CompletedTask; }));
    private static void Async(string name, Func<Task> test) => Cases.Add((name, test));
    private static (Observation Observer, MemoryEvidence Store, FakeStop Stop, List<string> Trace) Session()
    {
        var trace = new List<string>(); var store = new MemoryEvidence(trace); var stop = new FakeStop(trace);
        return (new Observation(Values.Contract, store, stop, policy), store, stop, trace);
    }
    public static async Task<int> Main(string[] args)
    {
        if (args is ["--negative-control", var mutation] && new[] { "private-allowed", "all-loopback-allowed", "pid-only",
            "gap-as-empty", "stop-before-raw", "unknown-backend-pass" }.Contains(mutation)) policy = new MutantPolicy(mutation);
        else if (args.Length != 0) { Console.Error.WriteLine("Unknown runner arguments"); return 2; }
        Register(); int passed = 0, failed = 0;
        foreach (var (name, test) in Cases)
        {
            try { await test(); Console.WriteLine("PASS " + name); passed++; }
            catch (Exception e) { Console.WriteLine("FAIL " + name + " " + e.GetType().Name); failed++; }
        }
        Console.WriteLine($"Executed={Cases.Count} PASS={passed} FAIL={failed}; fake/value-only; no GUI/OS collector/files/Stop");
        return failed == 0 ? 0 : 1;
    }

    private static void Register()
    {
        foreach (var (raw, category) in new (string, string)[]
        {
            ("127.0.0.1", "Loopback"), ("127.0.0.2", "Loopback"), ("::1", "Loopback"), ("0:0:0:0:0:0:0:1", "Loopback"),
            ("::ffff:127.0.0.1", "Loopback"), ("::ffff:7f00:1", "Loopback"), ("fe80::1%12", "LinkLocal"),
            ("::1%12", "Loopback"), ("10.1.2.3", "PrivateIPv4"), ("172.16.0.1", "PrivateIPv4"), ("172.31.255.254", "PrivateIPv4"),
            ("192.168.1.1", "PrivateIPv4"), ("169.254.1.1", "LinkLocal"), ("fe80::1", "LinkLocal"), ("fd00::1", "ULA"), ("fc00::1", "ULA"),
            ("8.8.8.8", "Public"), ("2001:4860::1", "Public"), ("0.0.0.0", "Unspecified"), ("::", "Unspecified"),
            ("::ffff:0.0.0.0", "Unspecified"), ("127.1", "NonCanonicalIPv4"), ("0177.0.0.1", "NonCanonicalIPv4"),
            ("0x7f000001", "NonCanonicalIPv4"), ("127.000.0.1", "NonCanonicalIPv4"), ("::ffff:127.1", "InvalidAddress"),
            ("garbage", "InvalidAddress"), ("127.0.0.1 ", "InvalidAddress"), ("", "MissingAddress"),
            ("224.0.0.1", "ReservedOrMulticast"), ("ff02::1", "ReservedOrMulticast")
        }) Add("ip_" + raw, () => Check(AddressRules.Parse(raw).Category == category));

        foreach (var (raw, disposition) in new (string, Disposition)[]
        {
            ("127.0.0.1", Disposition.Allowed), ("::ffff:127.0.0.1", Disposition.Allowed), ("127.0.0.2", Disposition.Denied),
            ("::1", Disposition.Denied), ("10.1.2.3", Disposition.Denied), ("fd00::1", Disposition.Denied),
            ("fe80::1%12", Disposition.Denied), ("8.8.8.8", Disposition.Denied), ("2001:4860::1", Disposition.Denied),
            ("0.0.0.0", Disposition.Unknown), ("::", Disposition.Unknown), ("invalid", Disposition.Unknown), ("127.1", Disposition.Unknown)
        }) Add("endpoint_" + raw, () => Check(policy.Classify(Values.Row(raw), Values.Endpoint).Disposition == disposition));
        Add("endpoint_wrong_port", () => Check(policy.Classify(Values.Row(port: 45679), Values.Endpoint).Disposition == Disposition.Denied));
        Add("endpoint_backend_missing", () => Check(policy.Classify(Values.Row(), null).Disposition == Disposition.Unknown));
        Add("endpoint_remote_missing", () => Check(AddressRules.Classify(Values.Row() with { RemoteAddress = null }, Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_port_missing", () => Check(AddressRules.Classify(Values.Row(port: null), Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_port_zero", () => Check(AddressRules.Classify(Values.Row(port: 0), Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_port_overflow", () => Check(AddressRules.Classify(Values.Row(port: 65536), Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_local_missing", () => Check(AddressRules.Classify(Values.Row() with { LocalAddress = null }, Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_local_port_missing", () => Check(AddressRules.Classify(Values.Row() with { LocalPort = null }, Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_family_missing", () => Check(AddressRules.Classify(Values.Row() with { AddressFamily = 0 }, Values.Endpoint).Disposition == Disposition.Unknown));
        Add("endpoint_birth_missing", () => Check(AddressRules.Classify(Values.Row() with { CreatedFileTime = null }, Values.Endpoint).Category == "OwnershipUnknown"));
        Add("mapped_normalized_raw_preserved", () =>
        { var row = Values.Row("::ffff:127.0.0.1"); var d = AddressRules.Classify(row, Values.Endpoint); Check(d.NormalizedAddress == "127.0.0.1" && row.RemoteAddress == "::ffff:127.0.0.1"); });
        Add("scope_preserved", () => Check(AddressRules.Classify(Values.Row("fe80::1%12"), Values.Endpoint).ScopeId == 12));
        foreach (string state in new[] { "LISTEN", "BOUND", "CLOSED", "UNKNOWN" })
            Add("state_" + state, () => Check(AddressRules.Classify(Values.Row(state: state), Values.Endpoint).Disposition == Disposition.Unknown));
        foreach (string state in new[] { "SYN_SENT", "SYN_RECEIVED", "ESTABLISHED", "FIN_WAIT1", "FIN_WAIT2", "CLOSE_WAIT", "CLOSING", "LAST_ACK", "TIME_WAIT", "DELETE_TCB" })
            Add("state_" + state, () => { var d = AddressRules.Classify(Values.Row(state: state), Values.Endpoint); Check(d.Disposition == Disposition.Allowed && d.TransportMeaning!.Contains("no", StringComparison.OrdinalIgnoreCase)); });
        OwnershipTests(); ObservationTests(); DecoderTests(); EvidenceTests();
    }

    private static void OwnershipTests()
    {
        var c = Values.Contract;
        Add("ownership_full_chain", () => { var o = OwnershipRules.Resolve(Values.Facts(), c); Check(o.Runtime.Length == 2 && o.Backend.Length == 2 && o.Worker?.Pid == 101 && o.Errors.Length == 0); });
        Add("ownership_udf_separate_arg", () => Check(OwnershipRules.ExactUdf(["exe", "--user-data-dir", c.Udf], c.Udf)));
        Add("ownership_udf_partial_rejected", () => Check(!OwnershipRules.ExactUdf(["exe", "--user-data-dir=" + c.Udf + "-other"], c.Udf)));
        Add("ownership_udf_duplicate_rejected", () => Check(!OwnershipRules.ExactUdf(["exe", "--user-data-dir=" + c.Udf, "--user-data-dir=" + c.Udf], c.Udf)));
        Add("ownership_udf_missing_value", () => Check(!OwnershipRules.ExactUdf(["exe", "--user-data-dir"], c.Udf)));
        Add("ownership_wrong_parent", () => { var f = Values.Facts(); f[2] = f[2] with { ParentPid = 999 }; Check(OwnershipRules.Resolve(f, c).Errors.Length > 0); });
        Add("ownership_parent_younger", () => { var f = Values.Facts(); f[2] = f[2] with { Key = new(102, 500) }; Check(OwnershipRules.Resolve(f, c).Errors.Length > 0); });
        Add("ownership_wrong_executable", () => { var f = Values.Facts(); f[2] = f[2] with { Executable = @"C:\wrong.exe" }; Check(OwnershipRules.Resolve(f, c).Errors.Length > 0); });
        Add("ownership_unverified_handle", () => { var f = Values.Facts(); f[3] = f[3] with { HandleVerified = false }; Check(OwnershipRules.Resolve(f, c).Errors.Length > 0); });
        Add("ownership_worker_parent", () => { var f = Values.Facts(); f[1] = f[1] with { ParentPid = 999 }; Check(OwnershipRules.Resolve(f, c).Worker == null); });
        Add("ownership_duplicate_pid", () => Check(OwnershipRules.Resolve([.. Values.Facts(), Values.Facts()[3]], c).Errors.Contains("duplicate_pid")));
        Add("ownership_unidentified_descendant", () => { var f = Values.Facts(); f[3] = f[3] with { Arguments = [c.RuntimeExecutable, "--type=renderer"] }; Check(OwnershipRules.Resolve(f, c).Errors.Contains("runtime_descendant_unidentified")); });
        Add("ownership_unrelated_ignored", () => { var f = Values.Facts(); var o = OwnershipRules.Resolve([.. f, new(new(999, 2000), 1, @"C:\personal\browser.exe", ["personal"], false)], c); Check(o.Errors.Length == 0 && o.Runtime.Length == 2); });
        Add("backend_dynamic_port", () => Check(OwnershipRules.DiscoverBackend([Values.Listener with { LocalPort = 31001 }], OwnershipRules.Resolve(Values.Facts(), c))?.Port == 31001));
        Add("backend_missing", () => Check(OwnershipRules.DiscoverBackend([], OwnershipRules.Resolve(Values.Facts(), c)) == null));
        Add("backend_two_listeners", () => Check(OwnershipRules.DiscoverBackend([Values.Listener, Values.Listener with { LocalPort = 31001 }], OwnershipRules.Resolve(Values.Facts(), c)) == null));
        Add("backend_wildcard_denied", () => Check(OwnershipRules.DiscoverBackend([Values.Listener with { LocalAddress = "0.0.0.0" }], OwnershipRules.Resolve(Values.Facts(), c)) == null));
        Add("backend_unrelated_listener", () => Check(OwnershipRules.DiscoverBackend([Values.Listener with { Pid = 999 }], OwnershipRules.Resolve(Values.Facts(), c)) == null));
        Add("backend_wrong_birth", () => Check(OwnershipRules.DiscoverBackend([Values.Listener with { CreatedFileTime = 999 }], OwnershipRules.Resolve(Values.Facts(), c)) == null));
        Add("backend_wrong_script", () => { var p = Values.Facts()[5]; var argv = p.Arguments.ToArray(); argv[5] = @"C:\fake\production.py"; Check(!OwnershipRules.Backend(p with { Arguments = argv }, c)); });
        Add("backend_wrong_data", () => { var p = Values.Facts()[5]; var argv = p.Arguments.ToArray(); argv[8] = @"C:\fake\feed.json"; Check(!OwnershipRules.Backend(p with { Arguments = argv }, c)); });
        foreach (string path in new[] { "relative", @"\\server\share\x", @"C:\fake\..\udf", @"C:\fake\state:stream", @"C:\fake\dir.", @"C:\fake\dir ", "C:/fake/udf" })
            Add("canonical_path_reject_" + path, () => { bool failed = false; try { Approval.CheckCanonical(path); } catch (InvalidDataException) { failed = true; } Check(failed); });
        Add("canonical_unicode_path", () => Approval.CheckCanonical(@"C:\検証\固定-profile"));
    }

    private static void ObservationTests()
    {
        Async("observation_normal_end", async () =>
        { var s = Session(); s.Observer.Ready(); await s.Observer.Accept(Values.Snapshot()); await s.Observer.Accept(Values.End()); var r = await s.Observer.Complete(true); Check(r.Result == Result.PASS_OBSERVED_SCOPE && s.Stop.Calls == 0); });
        Async("observation_single_snapshot_not_pass", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        Async("caller_cannot_invent_end_proof", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); await s.Observer.Accept(Values.Snapshot(2)); Check((await s.Observer.Complete(true)).Result == Result.INCONCLUSIVE); });
        Async("terminal_result_immutable", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); var first = await s.Observer.Complete(false); Check(await s.Observer.Complete(true) == first && !first.RuntimeEndConfirmed); });
        foreach (string ip in new[] { "10.1.2.3", "127.0.0.2", "8.8.8.8", "fd00::1" })
            Async("observation_denied_" + ip, async () =>
            {
                var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row(ip)]));
                Check(s.Stop.Calls == 1 && s.Stop.Identity == Observation.Identity && s.Stop.Timeout == TimeSpan.FromSeconds(10));
                Check(s.Trace.IndexOf("durable:000001-raw") < s.Trace.IndexOf("durable:000001-verdict") &&
                    s.Trace.IndexOf("durable:000001-verdict") < s.Trace.IndexOf("stop"));
                await s.Observer.Accept(Values.End()); Check((await s.Observer.Complete(true)).Result == Result.BLOCKED);
            });
        Async("observation_unknown_backend", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Row()])); Check(s.Stop.Calls == 1); await s.Observer.Accept(Values.End()); Check((await s.Observer.Complete(true)).Result == Result.INCONCLUSIVE); });
        Async("observation_pid_birth_mismatch", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row() with { CreatedFileTime = 999 }])); Check(s.Stop.Calls == 1); var raw = (RawSnapshot)s.Store.Saved["000001-raw"]; Check(raw.Rows.Length == 0 && raw.Errors.Contains("tcp_birth_mismatch")); });
        Async("observation_pid_reuse", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); var f = Values.Facts(); f[3] = f[3] with { Key = new(103, 1310) }; await s.Observer.Accept(Values.Snapshot(2) with { Processes = f }); Check(s.Stop.Calls == 1); Check(((RawSnapshot)s.Store.Saved["000002-raw"]).Errors.Contains("pid_reuse")); });
        foreach (var (name, snapshot) in new (string, Snapshot)[]
        {
            ("gap", Values.Snapshot(2, start: 2000)), ("backward_clock", Values.Snapshot(2, start: 100)),
            ("sequence_gap", Values.Snapshot(4)), ("long_query", Values.Snapshot(2) with { MonotonicEndMs = 3000 }),
            ("collector_error", Values.Snapshot(2) with { CollectionErrors = ["query_failed"] }),
            ("utc_backward", Values.Snapshot(2) with { QueryEndUtc = DateTimeOffset.UnixEpoch }),
            ("run_changed", Values.Snapshot(2) with { Run = "different-run" })
            , ("nonfinite_time", Values.Snapshot(2) with { MonotonicStartMs = double.NaN })
        }) Async("observation_" + name, async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); await s.Observer.Accept(snapshot); Check(s.Stop.Calls == 1); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        foreach (string stage in new[] { "write", "flush", "verify" })
        {
            Async("raw_failure_" + stage, async () =>
            { var s = Session(); s.Store.FailName = "raw"; s.Store.FailStage = stage; await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")])); Check(s.Observer.State == Phase.WRITE_FAILED && s.Stop.Calls == 1 && !s.Store.Saved.Keys.Any(k => k.EndsWith("verdict"))); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
            Async("verdict_failure_" + stage, async () =>
            { var s = Session(); s.Store.FailName = "verdict"; s.Store.FailStage = stage; await s.Observer.Accept(Values.Snapshot()); Check(s.Store.Saved.ContainsKey("000001-raw") && s.Stop.Calls == 1); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
            Async("result_partial_" + stage, async () =>
            { var s = Session(); s.Store.FailName = "result"; s.Store.FailStage = stage; await s.Observer.Accept(Values.Snapshot()); await s.Observer.Accept(Values.End()); Check((await s.Observer.Complete(true)).Result == Result.INCONCLUSIVE && !s.Store.Saved.ContainsKey("result")); });
        }
        Async("collector_stopped_before_raw", async () =>
        { var s = Session(); await s.Observer.Fail(Phase.GAP, "collector_stopped"); Check(s.Trace.IndexOf("durable:000000-failure") < s.Trace.IndexOf("stop")); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        Async("observer_crash", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); await s.Observer.Fail(Phase.CRASH, "injected_crash"); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        Async("stop_failure", async () =>
        { var s = Session(); s.Stop.Result = false; await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")])); Check((await s.Observer.Complete(false)).Reasons.Contains("formal_stop_unconfirmed")); });
        Async("stop_exception", async () =>
        { var s = Session(); s.Stop.Throw = true; await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")])); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        Async("stop_coalesced", async () =>
        { var s = Session(); for (int n = 1; n <= 3; n++) await s.Observer.Accept(Values.Snapshot(n, [Values.Listener, Values.Row("8.8.8.8")])); Check(s.Stop.Calls == 1); });
        Async("stop_ack_not_exit", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")])); Check(!(await s.Observer.Complete(false)).RuntimeEndConfirmed); });
        Async("sdk_event_missing", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot()); await s.Observer.Accept(Values.End() with { RuntimeEventConfirmed = false }); Check((await s.Observer.Complete(false)).Result == Result.INCONCLUSIVE); });
        Async("unrelated_sockets_not_saved", async () =>
        { var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row(), Values.Row("8.8.8.8") with { Pid = 999 }])); string json = JsonSerializer.Serialize(s.Store.Saved); Check(!json.Contains("8.8.8.8") && !json.Contains("C:\\fake") && s.Stop.Calls == 0); });
        Async("ownership_unknown_no_socket_disclosure", async () =>
        { var s = Session(); var f = Values.Facts(); f[3] = f[3] with { HandleVerified = false }; await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")]) with { Processes = f }); Check(s.Stop.Calls == 1 && !JsonSerializer.Serialize(s.Store.Saved).Contains("8.8.8.8")); });
        Async("ready_only_no_success", async () =>
        { var s = Session(); s.Observer.Ready(); Check(s.Store.Saved.Keys.SequenceEqual(["ready"]) && s.Stop.Calls == 0); });
        Async("partial_family_preserves_candidate_before_stop", async () =>
        {
            var s = Session(); await s.Observer.Accept(Values.Snapshot(rows: [Values.Listener, Values.Row("8.8.8.8")]) with { CollectionErrors = ["tcp_family_23_query_failed"] });
            Check(((RawSnapshot)s.Store.Saved["000001-raw"]).Rows.Single().RemoteAddress == "8.8.8.8" &&
                s.Trace.IndexOf("durable:000001-raw") < s.Trace.IndexOf("stop"));
        });
    }

    private static void DecoderTests()
    {
        Add("tcp_decode_ipv4", () =>
        {
            var bytes = new byte[28]; BitConverter.GetBytes(1u).CopyTo(bytes, 0); BitConverter.GetBytes(5u).CopyTo(bytes, 4);
            new byte[] { 127, 0, 0, 1 }.CopyTo(bytes, 8); bytes[12] = 0x12; bytes[13] = 0x34;
            new byte[] { 8, 8, 8, 8 }.CopyTo(bytes, 16); bytes[20] = 1; bytes[21] = 0xbb; BitConverter.GetBytes(103u).CopyTo(bytes, 24);
            var row = WindowsCollector.DecodeTable(bytes, 2).Single();
            Check(row.LocalAddress == "127.0.0.1" && row.LocalPort == 4660 && row.RemoteAddress == "8.8.8.8" && row.RemotePort == 443 && row.State == "ESTABLISHED" && row.Pid == 103);
        });
        Add("tcp_decode_ipv6_scope", () =>
        {
            var bytes = new byte[60]; BitConverter.GetBytes(1u).CopyTo(bytes, 0); bytes[19] = 1;
            bytes[28] = 0xfe; bytes[29] = 0x80; bytes[43] = 1; bytes[47] = 12;
            bytes[24] = 0x12; bytes[25] = 0x34; bytes[48] = 1; bytes[49] = 0xbb;
            BitConverter.GetBytes(3u).CopyTo(bytes, 52); BitConverter.GetBytes(103u).CopyTo(bytes, 56);
            var row = WindowsCollector.DecodeTable(bytes, 23).Single();
            Check(row.LocalAddress == "::1" && row.RemoteAddress == "fe80::1%12" && row.State == "SYN_SENT" && row.RemotePort == 443);
        });
        Add("tcp_decode_truncated", () => { bool failed = false; try { WindowsCollector.DecodeTable([1, 0, 0, 0], 2); } catch (InvalidDataException) { failed = true; } Check(failed); });
        Add("tcp_decode_empty", () => Check(WindowsCollector.DecodeTable([0, 0, 0, 0], 23).Length == 0));
        Add("command_quote_unicode_backslashes", () => Check(OwnedStopCommand.Quote(@"C:\日本語\") == "\"C:\\日本語\\\\\""));
        Add("wmi_birth_utc", () => Check(WindowsCollector.WmiBirth("20261011123000.123456+000") == new DateTime(2026, 10, 11, 12, 30, 0, DateTimeKind.Utc).AddTicks(1234560).ToFileTimeUtc()));
        Add("wmi_birth_timezone", () => Check(WindowsCollector.WmiBirth("20261011213000.123456+540") == WindowsCollector.WmiBirth("20261011123000.123456+000")));
    }

    private static void EvidenceTests()
    {
        Add("evidence_shared_algorithm_order", () =>
        {
            var blobs = new FakeBlobs(); new VerifiedEvidence(blobs).SaveVerified("raw", new { Value = "isolated" });
            Check(blobs.Trace.SequenceEqual(["create:raw", "flush:raw", "read_pending:raw", "commit:raw", "read_committed:raw"]));
        });
        foreach (string stage in new[] { "create", "flush", "read_pending", "commit", "read_committed", "partial_pending", "partial_committed" })
            Add("evidence_shared_failure_" + stage, () =>
            {
                var blobs = new FakeBlobs { Fault = stage }; bool failed = false;
                try { new VerifiedEvidence(blobs).SaveVerified("result", new { Result = "PASS_OBSERVED_SCOPE" }); }
                catch (IOException) { failed = true; }
                Check(failed && !blobs.Committed.ContainsKey("result-receipt"));
            });
        Add("evidence_result_receipt", () =>
        {
            var blobs = new FakeBlobs(); new VerifiedEvidence(blobs).SaveVerified("result", new { Result = "PASS_OBSERVED_SCOPE" });
            using var receipt = JsonDocument.Parse(blobs.Committed["result-receipt"]);
            Check(receipt.RootElement.GetProperty("ResultSha256").GetString() == Approval.Hash(blobs.Committed["result"]));
        });
        Add("evidence_receipt_failure", () =>
        {
            var blobs = new FakeBlobs { Fault = "commit", FaultName = "result-receipt" }; bool failed = false;
            try { new VerifiedEvidence(blobs).SaveVerified("result", new { Result = "PASS_OBSERVED_SCOPE" }); }
            catch (IOException) { failed = true; }
            Check(failed && !blobs.Committed.ContainsKey("result-receipt"));
        });
        Add("evidence_no_overwrite", () =>
        {
            var blobs = new FakeBlobs(); var writer = new VerifiedEvidence(blobs); writer.SaveVerified("raw", new { Value = 1 });
            bool failed = false; try { writer.SaveVerified("raw", new { Value = 2 }); } catch (ArgumentException) { failed = true; } Check(failed);
        });
        Add("evidence_path_name_rejected", () =>
        {
            var blobs = new FakeBlobs(); bool failed = false;
            try { new VerifiedEvidence(blobs).SaveVerified("../state", new { Value = 1 }); } catch (IOException) { failed = true; }
            Check(failed && blobs.Trace.Count == 0);
        });
        Add("evidence_capacity_rejected", () =>
        {
            var blobs = new FakeBlobs(); bool failed = false;
            try { new VerifiedEvidence(blobs).SaveVerified("raw", new { Value = new string('x', 4 * 1024 * 1024) }); } catch (IOException) { failed = true; }
            Check(failed && blobs.Trace.Count == 0);
        });
    }
}
