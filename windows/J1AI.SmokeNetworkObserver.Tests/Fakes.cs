using J1AI.SmokeNetworkObserver;

namespace J1AI.SmokeNetworkObserver.Tests;

internal sealed class MemoryEvidence(List<string> trace) : IEvidence
{
    internal readonly Dictionary<string, object> Saved = [];
    internal string? FailName, FailStage;
    public void SaveVerified(string name, object value)
    {
        trace.Add("write:" + name);
        if (name.Contains(FailName ?? "NEVER", StringComparison.Ordinal) && FailStage == "write") throw new IOException("injected_write");
        trace.Add("flush:" + name);
        if (name.Contains(FailName ?? "NEVER", StringComparison.Ordinal) && FailStage == "flush") throw new IOException("injected_flush");
        trace.Add("verify:" + name);
        if (name.Contains(FailName ?? "NEVER", StringComparison.Ordinal) && FailStage == "verify") throw new IOException("injected_partial_readback");
        Saved.Add(name, value); trace.Add("durable:" + name);
    }
}
internal sealed class FakeStop(List<string> trace) : IStop
{
    internal bool Result = true, Throw;
    internal int Calls;
    internal string? Identity;
    internal TimeSpan? Timeout;
    public Task<bool> RequestAsync(string identity, TimeSpan timeout)
    {
        trace.Add("stop"); Calls++; Identity = identity; Timeout = timeout;
        if (Throw) throw new IOException("injected_stop");
        return Task.FromResult(Result);
    }
}
internal sealed class MutantPolicy(string mutation) : ObservationPolicy
{
    internal override Decision Classify(TcpRow row, Endpoint? endpoint)
    {
        var d = base.Classify(row, endpoint);
        if (mutation == "private-allowed" && d.Category == "PrivateIPv4" ||
            mutation == "all-loopback-allowed" && d.Category == "OtherLoopback" ||
            mutation == "unknown-backend-pass" && endpoint == null)
            return d with { Disposition = Disposition.Allowed };
        return d;
    }
    internal override bool Gap(bool detected) => mutation == "gap-as-empty" ? false : detected;
    internal override bool KeyMatches(ProcessKey key, TcpRow row) => mutation == "pid-only" ? key.Pid == row.Pid : base.KeyMatches(key, row);
    internal override bool BackendRequired => mutation != "unknown-backend-pass";
    internal override Task BeforeRaw(IStop stop) => mutation == "stop-before-raw" ? stop.RequestAsync(Observation.Identity, TimeSpan.FromSeconds(10)) : Task.CompletedTask;
}

internal static class Values
{
    internal static readonly IdentityContract Contract = new(@"C:\fake\udf", @"C:\fake\root", @"C:\fake\runner.dll",
        @"C:\fake\synthetic_gui_server.py", @"C:\fake\venv\python.exe", @"C:\fake\dotnet.exe", @"C:\fake\runner.exe",
        @"C:\fake\python.exe", @"C:\fake\msedgewebview2.exe");
    internal static ProcessFact[] Facts()
    {
        var c = Contract;
        return [
            new(new(100, 1000), 1, c.Dotnet, [c.Dotnet, c.Runner, "--smoke-run"], true),
            new(new(101, 1100), 100, c.Dotnet, [c.Dotnet, c.Runner, "--smoke-worker"], true),
            new(new(102, 1200), 101, c.RuntimeExecutable, [c.RuntimeExecutable, "--user-data-dir=" + c.Udf], true),
            new(new(103, 1300), 102, c.RuntimeExecutable, [c.RuntimeExecutable, "--type=renderer", "--user-data-dir=" + c.Udf], true),
            new(new(104, 1400), 101, c.PythonArgument, [c.PythonArgument, "-I", "-S", "-B", "-u", c.Backend, c.Root, "--data", Path.Combine(c.Root, "must-not-be-read.json")], true),
            new(new(105, 1500), 104, c.PythonExecutable, [c.PythonArgument, "-I", "-S", "-B", "-u", c.Backend, c.Root, "--data", Path.Combine(c.Root, "must-not-be-read.json")], true)
        ];
    }
    internal static TcpRow Row(string address = "127.0.0.1", int? port = 45678, string state = "ESTABLISHED") =>
        new(103, 1300, "127.0.0.1", 54321, address, port, state, address.Contains(':') ? 23 : 2);
    internal static TcpRow Listener => new(105, 1500, "127.0.0.1", 45678, "0.0.0.0", 0, "LISTEN", 2);
    internal static Endpoint Endpoint => new("127.0.0.1", 45678, new(105, 1500));
    internal static Snapshot Snapshot(long sequence = 1, TcpRow[]? rows = null, double? start = null) =>
        new(sequence, DateTimeOffset.UnixEpoch.AddMilliseconds(sequence * 250), DateTimeOffset.UnixEpoch.AddMilliseconds(sequence * 250 + 5),
            start ?? sequence * 250, (start ?? sequence * 250) + 5, Facts(), rows ?? [Listener, Row()], [], false, "fake-run", false);
    internal static Snapshot End(long sequence = 2) => Snapshot(sequence, []) with { Processes = [], EndConfirmed = true, RuntimeEventConfirmed = true };
}

internal sealed class FakeBlobs : IBlobStore
{
    internal readonly List<string> Trace = [];
    internal readonly Dictionary<string, byte[]> Pending = [], Committed = [];
    internal string? Fault, FaultName;
    private void Step(string name, string stage)
    {
        Trace.Add(stage + ":" + name);
        if (stage == Fault && (FaultName == null || FaultName == name)) throw new IOException("injected_blob_failure");
    }
    public void CreatePending(string name, byte[] bytes) { Step(name, "create"); Pending.Add(name, bytes.ToArray()); }
    public void FlushPending(string name) => Step(name, "flush");
    public byte[] ReadPending(string name) { Step(name, "read_pending"); return Fault == "partial_pending" ? Pending[name][..^1] : Pending[name].ToArray(); }
    public void Commit(string name) { Step(name, "commit"); Committed.Add(name, Pending[name]); Pending.Remove(name); }
    public byte[] ReadCommitted(string name) { Step(name, "read_committed"); return Fault == "partial_committed" ? Committed[name][..^1] : Committed[name].ToArray(); }
}
