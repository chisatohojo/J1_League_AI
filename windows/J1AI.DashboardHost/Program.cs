using System.Globalization;

namespace J1AI.DashboardHost;

internal sealed record Options(bool Help, bool Core, bool Gui, bool Stop, string? Root, string? Data, double Timeout)
{
    internal static Options Parse(string[] args)
    {
        bool help = false, core = false, gui = false, stop = false;
        string? root = null, data = null; double timeout = 20;
        var seen = new HashSet<string>();
        for (int i = 0; i < args.Length; i++)
        {
            string arg = args[i];
            if (!seen.Add(arg)) throw new HostError(EventCode.InvalidArguments);
            string Next() => ++i < args.Length ? args[i] : throw new HostError(EventCode.InvalidArguments);
            switch (arg)
            {
                case "--help": help = true; break;
                case "--core": core = true; break;
                case "--gui": gui = true; break;
                case "--stop": stop = true; break;
                case "--repository": root = Path.Combine(Environment.CurrentDirectory, Next()); break;
                case "--data": data = Path.GetFullPath(Next()); break;
                case "--startup-timeout":
                    if (!double.TryParse(Next(), NumberStyles.Float, CultureInfo.InvariantCulture, out timeout) ||
                        !double.IsFinite(timeout) || timeout is <= 0 or > 120) throw new HostError(EventCode.InvalidArguments);
                    break;
                default: throw new HostError(EventCode.InvalidArguments);
            }
        }
        if ((core && gui) || (stop && (core || gui || data != null)) || (data != null && !core && !gui))
            throw new HostError(EventCode.InvalidArguments);
        return new(help, core, gui, stop, root, data, timeout);
    }
}

public static class Program
{
    [STAThread]
    public static Task<int> Main(string[] args) => RunAsync(args);

    // Internal synthetic seam, never configurable by CLI or production data.
    internal static async Task<int> RunAsync(string[] args,
        Func<string?, Task<RepositoryIdentity>>? resolveIdentity = null, Action? reportFailure = null)
    {
        IEvents? events = null;
        bool guiRequested = args.Contains("--gui", StringComparer.Ordinal) &&
            !args.Contains("--help", StringComparer.Ordinal) && !args.Contains("--stop", StringComparer.Ordinal);
        var notification = new GuiFailureNotification(reportFailure);
        try
        {
            var options = Options.Parse(args);
            // No native API, identity helper, IPC, data IO or log on help/default.
            if (options.Help)
            {
                Console.WriteLine("J1AI Dashboard: --gui | --core [--repository PATH] [--data JSON] [--startup-timeout SECONDS] | --stop | --help. No arguments: no action.");
                return 0;
            }
            if (!options.Core && !options.Gui && !options.Stop) return 0;
            if (!OperatingSystem.IsWindows()) return 1;
            var identity = resolveIdentity != null ? await resolveIdentity(options.Root) :
                await RepositoryIdentity.ResolveAsync(options.Root ?? RepositoryIdentity.FindRoot(AppContext.BaseDirectory));
            events = new FileEvents(identity.Id);
            if (options.Stop)
            {
                events.Record(InstanceControls.Signal(identity, true) ? EventCode.StopRequested : EventCode.NotRunning);
                return 0;
            }
            using var controls = new InstanceControls(identity);
            if (options.Gui)
                return await GuiEntry.RunAsync(controls,
                    () => WebViewPreflight.Check(identity.Id),
                    () => OwnedServer.Start(ServerCommand.Dashboard(identity, options.Data), controls),
                    new Readiness(), events, TimeSpan.FromSeconds(options.Timeout), notification.Show);
            // Duplicate owners signal SHOW (legacy has no Show: harmless false).
            // Lifecycle owns acquisition, so no second mutex acquisition here.
            var core = new Lifecycle(controls,
                () => OwnedServer.Start(ServerCommand.Dashboard(identity, options.Data), controls),
                new Readiness(), events);
            return await core.RunAsync(TimeSpan.FromSeconds(options.Timeout));
        }
        catch (Exception error)
        {
            try { events?.Record(error is HostError h ? h.Code : EventCode.UnexpectedFailure); }
            catch { /* Best-effort diagnostics cannot mask the original failure. */ }
            if (guiRequested) notification.Show();
            return 1;
        }
    }
}
