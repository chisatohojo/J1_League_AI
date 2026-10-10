using System.Diagnostics;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace J1AI.DashboardHost;

public sealed record RepositoryIdentity(string Root, string Id)
{
    public string Name => @"Local\J1AI.Dashboard." + Id;
    public string Python => Path.Combine(Root, ".venv", "Scripts", "python.exe");
    internal bool ViaSymbolicLink { get; init; }

    // Python, not .NET casing/path heuristics, remains the identity authority.
    // run_path does not run main, discover data, start a server, or create IPC.
    private const string Script = "import json,runpy,sys; from pathlib import Path; " +
        "p=Path(sys.argv[1]).absolute(); s=any(x.is_symlink() for x in (p,*p.parents)); r=p.resolve(); assert r.is_dir(); " +
        "f=runpy.run_path(sys.argv[2],run_name='j1ai_identity_only')['instance_id']; " +
        "print(json.dumps([str(r),f(r),s],ensure_ascii=True))";

    public static string FindRoot(string start)
    {
        for (var current = new DirectoryInfo(Path.GetFullPath(start)); current != null; current = current.Parent)
            if (File.Exists(Path.Combine(current.FullName, "scripts", "launch_dashboard.py")) &&
                File.Exists(Path.Combine(current.FullName, ".venv", "Scripts", "python.exe")))
                return current.FullName;
        throw new HostError(EventCode.IdentityFailed);
    }

    public static async Task<RepositoryIdentity> ResolveAsync(string root)
    {
        var identity = await ResolveAsync(root,
            Path.Combine(Path.GetFullPath(root), ".venv", "Scripts", "python.exe"),
            Path.Combine(Path.GetFullPath(root), "scripts", "launch_dashboard.py"));
        RequireLaunchable(identity);
        return identity;
    }

    internal static void RequireLaunchable(RepositoryIdentity identity)
    {
        // Metadata equivalence is tested, but a full temporary symlink-repo
        // lifecycle cannot be exercised without unavailable privileges here.
        // Do not invent a namespace or silently accept that unproved path shape.
        if (identity.ViaSymbolicLink) throw new HostError(EventCode.IdentityFailed);
    }

    internal static async Task<RepositoryIdentity> ResolveAsync(string root, string python, string launcher)
    {
        // Preserve Python's resolution of dot-dot/reparse components. The
        // helper cwd is trusted implementation code, not an unresolved alias.
        if (!Path.IsPathFullyQualified(root)) root = Path.Combine(Environment.CurrentDirectory, root);
        using var process = new Process();
        process.StartInfo = new ProcessStartInfo(python)
        {
            UseShellExecute = false, CreateNoWindow = true, WorkingDirectory = Path.GetDirectoryName(Path.GetFullPath(launcher))!,
            RedirectStandardOutput = true, RedirectStandardError = true
        };
        foreach (var arg in new[] { "-I", "-S", "-X", "utf8", "-c", Script, root, launcher })
            process.StartInfo.ArgumentList.Add(arg);
        try
        {
            if (!process.Start()) throw new HostError(EventCode.IdentityFailed);
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(10));
            // Both streams are bounded/drained; never forward helper diagnostics.
            var output = ReadBoundedAsync(process.StandardOutput, deadline.Token);
            var errors = ReadBoundedAsync(process.StandardError, deadline.Token);
            await process.WaitForExitAsync(deadline.Token);
            var text = await output;
            await errors;
            if (process.ExitCode != 0) throw new HostError(EventCode.IdentityFailed);
            using var reply = JsonDocument.Parse(text);
            var values = reply.RootElement;
            if (values.ValueKind != JsonValueKind.Array || values.GetArrayLength() != 3 ||
                !Path.IsPathFullyQualified(values[0].GetString()!) ||
                !Regex.IsMatch(values[1].GetString()!, "\\A[0-9a-f]{24}\\z") ||
                values[2].ValueKind is not (JsonValueKind.True or JsonValueKind.False))
                throw new HostError(EventCode.IdentityFailed);
            return new(values[0].GetString()!, values[1].GetString()!) { ViaSymbolicLink = values[2].GetBoolean() };
        }
        catch (Exception)
        {
            // Only the retained, self-created helper handle, never PID/name lookup.
            try { if (!process.HasExited) { process.Kill(); process.WaitForExit(5000); } }
            catch (InvalidOperationException) { }
            throw new HostError(EventCode.IdentityFailed);
        }
    }

    private static async Task<string> ReadBoundedAsync(StreamReader reader, CancellationToken token)
    {
        var buffer = new char[16385];
        int size = 0, read;
        while ((read = await reader.ReadAsync(buffer.AsMemory(size), token)) > 0)
        {
            size += read;
            if (size == buffer.Length) throw new HostError(EventCode.IdentityFailed);
        }
        return new string(buffer, 0, size);
    }
}
