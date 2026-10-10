using Microsoft.Win32;
using Microsoft.Web.WebView2.Core;
using System.Collections;
using System.Text.RegularExpressions;

namespace J1AI.DashboardHost;

internal sealed record PolicyValue(string Path, string Name, RegistryValueKind Kind, object? Value);
internal sealed record WebViewConfiguration(string Profile, string Runtime);

internal static class WebViewPreflight
{
    internal const string PolicyRoot = @"SOFTWARE\Policies\Microsoft\Edge\WebView2";
    // Loader override names include historical API overrides not listed as GPOs.
    private static readonly HashSet<string> Overrides = new(StringComparer.OrdinalIgnoreCase)
    { "BrowserExecutableFolder", "UserDataFolder", "AdditionalBrowserArguments", "ReleaseChannelPreference",
        "ReleaseChannels", "ChannelSearchKind", "DowngradeVersion" };

    internal static WebViewConfiguration Check(string id)
    {
        CheckInputs(Environment.GetEnvironmentVariables(), ReadPolicies());
        string runtime;
        try { runtime = CoreWebView2Environment.GetAvailableBrowserVersionString(); }
        catch { throw new HostError(EventCode.WebViewFailed); }
        RequireRuntime(runtime);
        string profile = ProfilePath(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), id);
        CheckProfile(profile);
        return new(profile, runtime);
    }

    internal static void RequireRuntime(string runtime)
    {
        // This release was validated against Evergreen 154, not an Edge preview channel.
        if (!Version.TryParse(runtime, out var version) || version.Major < 154)
            throw new HostError(EventCode.WebViewFailed);
    }

    internal static string ProfilePath(string local, string id)
    {
        if (!Path.IsPathFullyQualified(local) || !Regex.IsMatch(id, "\\A[0-9a-f]{24}\\z"))
            throw new HostError(EventCode.ProfileFailed);
        return Path.Combine(local, "J1AI", "Dashboard", id, "webview2-profile");
    }

    internal static void CheckProfile(string profile)
    {
        try
        {
            // Never follow a profile junction/symlink into a personal browser profile.
            for (var part = new DirectoryInfo(profile); part != null; part = part.Parent)
                if (part.Exists && (part.Attributes & FileAttributes.ReparsePoint) != 0)
                    throw new HostError(EventCode.ProfileFailed);
            Directory.CreateDirectory(profile);
            // Test only our newly created random file, never profile contents. No profile deletion.
            using var probe = new FileStream(Path.Combine(profile, ".j1ai-write-" + Guid.NewGuid().ToString("N")),
                FileMode.CreateNew, FileAccess.Write, FileShare.None, 1, FileOptions.DeleteOnClose);
        }
        catch { throw new HostError(EventCode.ProfileFailed); }
    }

    internal static void CheckInputs(IDictionary environment, IEnumerable<PolicyValue> policies)
    {
        // Reject, rather than sanitize or override, ALL nonempty WEBVIEW2 overrides,
        // including debugger variables and future unclassified loader variables.
        foreach (DictionaryEntry entry in environment)
            if (entry.Key is string name && name.StartsWith("WEBVIEW2_", StringComparison.OrdinalIgnoreCase) &&
                !string.IsNullOrEmpty(entry.Value?.ToString())) throw new HostError(EventCode.UnsafeWebViewOverride);
        foreach (var policy in policies)
        {
            bool root = policy.Path.Equals(PolicyRoot, StringComparison.OrdinalIgnoreCase);
            // Explicit, narrowly reviewed legacy-entry exception. NOT a proof of an
            // internal mitigation; this is classification by Microsoft's supported scope.
            if (root && policy.Name.Equals("RendererCodeIntegrityEnabled", StringComparison.OrdinalIgnoreCase) &&
                policy.Kind == RegistryValueKind.DWord && policy.Value is int n && n is 0 or 1) continue;
            string category = policy.Path[(PolicyRoot.Length)..].TrimStart('\\').Split('\\')[0];
            if (root && Overrides.Contains(policy.Name) || Overrides.Contains(category))
            {
                // Conservatively reject all configured loader entries, including other
                // app IDs: no attempt to defeat HKLM/HKCU/AppId/EXE/* precedence.
                if (!string.IsNullOrEmpty(policy.Value?.ToString())) throw new HostError(EventCode.UnsafeWebViewOverride);
                continue;
            }
            // Unknown configured WebView2 policy cannot silently weaken this boundary.
            throw new HostError(EventCode.UnsafeWebViewOverride);
        }
    }

    internal static IEnumerable<PolicyValue> ReadPolicies()
    {
        var values = new List<PolicyValue>();
        foreach (var hive in new[] { RegistryHive.LocalMachine, RegistryHive.CurrentUser })
        foreach (var view in new[] { RegistryView.Registry64, RegistryView.Registry32 })
        {
            using var root = RegistryKey.OpenBaseKey(hive, view);
            Read(root, PolicyRoot, values);
        }
        return values;
    }
    private static void Read(RegistryKey hive, string path, List<PolicyValue> values)
    {
        using var key = hive.OpenSubKey(path, writable: false);
        if (key == null) return;
        foreach (string name in key.GetValueNames()) values.Add(new(path, name, key.GetValueKind(name),
            key.GetValue(name, null, RegistryValueOptions.DoNotExpandEnvironmentNames)));
        foreach (string child in key.GetSubKeyNames()) Read(hive, path + "\\" + child, values);
    }
}
