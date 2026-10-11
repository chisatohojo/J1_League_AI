namespace J1AI.SmokeNetworkObserver;

public sealed record IdentityContract(string Udf, string Root, string Runner, string Backend,
    string PythonArgument, string Dotnet, string RunnerExe, string PythonExecutable, string RuntimeExecutable);

public static class OwnershipRules
{
    public static bool PathEquals(string a, string b) => string.Equals(a, b, StringComparison.OrdinalIgnoreCase);
    public static bool ExactUdf(string[] argv, string udf)
    {
        var values = new List<string>();
        for (int i = 1; i < argv.Length; i++)
        {
            if (argv[i] == "--user-data-dir") { if (++i == argv.Length) return false; values.Add(argv[i]); }
            else if (argv[i].StartsWith("--user-data-dir=", StringComparison.Ordinal)) values.Add(argv[i][16..]);
        }
        return values.Count == 1 && PathEquals(values[0], udf);
    }
    public static bool Runner(ProcessFact p, IdentityContract c, string mode)
    {
        if (!p.HandleVerified) return false;
        if (PathEquals(p.Executable, c.Dotnet))
            return p.Arguments.Length == 3 && PathEquals(p.Arguments[1], c.Runner) && p.Arguments[2] == mode;
        return PathEquals(p.Executable, c.RunnerExe) && p.Arguments.Length == 2 && p.Arguments[1] == mode;
    }
    public static bool Backend(ProcessFact p, IdentityContract c) =>
        p.HandleVerified && (PathEquals(p.Executable, c.PythonExecutable) || PathEquals(p.Executable, c.PythonArgument)) &&
        p.Arguments.Length == 9 && p.Arguments.Skip(1).SequenceEqual(new[]
        { "-I", "-S", "-B", "-u", c.Backend, c.Root, "--data", Path.Combine(c.Root, "must-not-be-read.json") },
            StringComparer.OrdinalIgnoreCase);

    public static Ownership Resolve(ProcessFact[] facts, IdentityContract c)
    {
        var errors = new List<string>();
        if (facts.GroupBy(p => p.Key.Pid).Any(g => g.Count() != 1))
            return new([], [], null, ["duplicate_pid"]);
        var byPid = facts.ToDictionary(p => p.Key.Pid);
        bool Parent(ProcessFact child, ProcessFact parent) => child.ParentPid == parent.Key.Pid &&
            child.Key.CreatedFileTime >= parent.Key.CreatedFileTime && child.Key != parent.Key;
        var workers = facts.Where(p => Runner(p, c, "--smoke-worker")).ToArray();
        ProcessFact? worker = workers.Length == 1 ? workers[0] : null;
        if (workers.Length > 1) errors.Add("multiple_workers");
        if (worker != null && (!byPid.TryGetValue(worker.ParentPid, out var supervisor) ||
            !Runner(supervisor, c, "--smoke-run") || !Parent(worker, supervisor)))
        { errors.Add("worker_parent_unverified"); worker = null; }

        var candidates = facts.Where(p => ExactUdf(p.Arguments, c.Udf)).ToArray();
        var owned = new List<ProcessFact>();
        if (worker != null)
        {
            var browsers = candidates.Where(p => PathEquals(p.Executable, c.RuntimeExecutable) && p.HandleVerified &&
                Parent(p, worker) && !p.Arguments.Any(a => a.StartsWith("--type=", StringComparison.Ordinal))).ToArray();
            if (browsers.Length > 1) errors.Add("multiple_browser_roots");
            if (browsers.Length == 1) owned.Add(browsers[0]);
            bool changed;
            do
            {
                changed = false;
                foreach (var p in candidates.Except(owned))
                    if (p.HandleVerified && PathEquals(p.Executable, c.RuntimeExecutable) && owned.Any(parent => Parent(p, parent)))
                    { owned.Add(p); changed = true; }
            } while (changed);
        }
        foreach (var p in candidates.Except(owned)) errors.Add("runtime_identity_or_lineage_unverified");
        // A descendant lacking an exact UDF argument cannot silently disappear from scope.
        foreach (var p in facts.Where(p => owned.Any(parent => Parent(p, parent)) && !owned.Contains(p)))
            errors.Add("runtime_descendant_unidentified");
        var backends = new List<ProcessFact>();
        if (worker != null)
        {
            foreach (var p in facts.Where(p => Backend(p, c) && Parent(p, worker))) backends.Add(p);
            foreach (var p in facts.Where(p => Backend(p, c) && backends.Any(parent => Parent(p, parent))).ToArray())
                if (!backends.Contains(p)) backends.Add(p);
        }
        return new(owned.Select(p => p.Key).ToArray(), backends.Select(p => p.Key).ToArray(), worker?.Key, errors.Distinct().ToArray());
    }

    public static Endpoint? DiscoverBackend(TcpRow[] rows, Ownership owner)
    {
        var listeners = rows.Where(r => owner.Backend.Contains(new ProcessKey(r.Pid, r.CreatedFileTime ?? -1)) &&
            r.State == "LISTEN").ToArray();
        if (listeners.Length != 1) return null;
        var row = listeners[0];
        // Existing synthetic backend binds exactly 127.0.0.1, not any loopback host.
        if (row.LocalAddress != "127.0.0.1" || row.LocalPort is not (> 0 and <= 65535)) return null;
        return new(row.LocalAddress, row.LocalPort.Value, new(row.Pid, row.CreatedFileTime!.Value));
    }
}
