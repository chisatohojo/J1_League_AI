namespace J1AI.DashboardHost;

public enum EventCode
{
    Starting, Running, Closing, Cleanup, Stopped, AlreadyRunning, ShowPending,
    StopRequested, NotRunning, IdentityFailed, IpcFailed, SpawnFailed,
    InvalidUrl, InvalidResponse, StartupTimeout, ServerExited, CleanupFailed,
    UnexpectedFailure, CoreOnly, InvalidArguments, UnsafeWebViewOverride,
    ProfileFailed, WebViewFailed, RendererFailed, BrowserFailed, NavigationBlocked
}

public sealed class HostError(EventCode code) : Exception(code.ToString())
{
    public EventCode Code { get; } = code;
}

public interface IEvents { void Record(EventCode code); }

public sealed class FileEvents(string instanceId) : IEvents
{
    public void Record(EventCode code)
    {
        // No arbitrary strings, exception text, stdout, URLs or response content.
        if (!Enum.IsDefined(code)) throw new ArgumentOutOfRangeException(nameof(code));
        if (!System.Text.RegularExpressions.Regex.IsMatch(instanceId, "\\A[0-9a-f]{24}\\z"))
            throw new HostError(EventCode.IdentityFailed);
        var directory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "J1AI", "Dashboard", instanceId);
        try
        {
            Directory.CreateDirectory(directory);
            File.AppendAllText(Path.Combine(directory, "native-core.log"),
                $"{DateTimeOffset.UtcNow:O} {code}\n");
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }
    }
}
