using System.Collections;
using System.Runtime.InteropServices;
using System.Text;
using J1AI.SmokeMigration;

namespace J1AI.SmokeMigration.Tests;

// Test-only boundary C. This is NOT a bootstrap protecting the supervisor
// before CLR startup. A separately trusted pre-CLR launcher is still required.
internal static class WorkerEnvironment
{
    private static readonly string[] runtimePrefixes = ["DOTNET_", "CORECLR_", "COMPlus_", "COR_", "COREHOST_"];
    internal static SortedDictionary<string, string> Expected(string windows, string local, string root) => new(StringComparer.OrdinalIgnoreCase)
    {
        ["SystemRoot"] = windows, ["windir"] = windows, ["LOCALAPPDATA"] = local,
        ["TEMP"] = Path.Combine(root, "temp"), ["TMP"] = Path.Combine(root, "temp"),
        ["DOTNET_CLI_HOME"] = Path.Combine(root, "cli"),
        ["DOTNET_CLI_TELEMETRY_OPTOUT"] = "1", ["DOTNET_NOLOGO"] = "1",
        ["DOTNET_SKIP_FIRST_TIME_EXPERIENCE"] = "1", ["DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE"] = "true",
        ["DOTNET_ADD_GLOBAL_TOOLS_TO_PATH"] = "0", ["DOTNET_EnableDiagnostics"] = "0"
    };
    internal static SortedDictionary<string, string> ValidatedExpected()
    {
        string windows = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        string local = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var expected = Expected(windows, local, ObservationPaths.Root);
        // OS-known folders, not parent-supplied arbitrary paths. Ancestors and
        // final canonical paths are pinned/reparse-checked by ReadPin.
        foreach (string path in new[] { windows, local, expected["TEMP"], expected["DOTNET_CLI_HOME"] })
        { using var pin = new ReadPin(path, true); if (path.StartsWith(ObservationPaths.Root + "\\", StringComparison.OrdinalIgnoreCase)) ReadPin.RequirePrivate(pin.Handle, false); }
        using var root = ObservationPaths.PinRoot();
        return expected;
    }
    private static Dictionary<string, string> Unique(IEnumerable<KeyValuePair<string, string>> pairs)
    {
        var result = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var p in pairs)
        {
            Contract.Require(p.Key.Length > 0 && p.Key.All(c => char.IsAsciiLetterOrDigit(c) || c == '_') && !char.IsAsciiDigit(p.Key[0]), "environment_key_format");
            Contract.Require(!p.Value.Contains('\0'), "environment_value_format");
            Contract.Require(result.TryAdd(p.Key, p.Value), "environment_duplicate_key");
        }
        return result;
    }
    internal static void ValidateExact(IEnumerable<KeyValuePair<string, string>> actual, IReadOnlyDictionary<string, string> expected)
    {
        var values = Unique(actual);
        foreach (var p in values)
        {
            Contract.Require(expected.TryGetValue(p.Key, out var value), "environment_key_denied");
            Contract.Require(p.Value == value, "environment_value_denied");
        }
        Contract.Require(values.Count == expected.Count, "environment_missing_key");
    }
    internal static string Build(IEnumerable<KeyValuePair<string, string>> pairs, IReadOnlyDictionary<string, string> expected)
    {
        var values = Unique(pairs); ValidateExact(values, expected);
        string block = string.Concat(values.OrderBy(p => p.Key, StringComparer.OrdinalIgnoreCase).Select(p => p.Key + "=" + p.Value + '\0')) + '\0';
        Contract.Require(block.Length <= 32767, "environment_block_limit");
        _ = Parse(block); return block;
    }
    internal static IReadOnlyList<KeyValuePair<string, string>> Parse(string block)
    {
        Contract.Require(block.Length is >= 2 and <= 32767 && block.EndsWith("\0\0", StringComparison.Ordinal), "environment_block_terminator");
        try { _ = new UnicodeEncoding(false, false, true).GetBytes(block); }
        catch (EncoderFallbackException) { throw new InvalidDataException("environment_unicode"); }
        string[] entries = block[..^2].Split('\0');
        var result = new List<KeyValuePair<string, string>>(); string? prior = null;
        foreach (string entry in entries)
        {
            int equals = entry.IndexOf('='); Contract.Require(equals > 0, "environment_block_entry");
            string key = entry[..equals];
            result.Add(new(key, entry[(equals + 1)..]));
            if (prior != null) Contract.Require(StringComparer.OrdinalIgnoreCase.Compare(prior, key) <= 0, "environment_block_order");
            prior = key;
        }
        _ = Unique(result); return result;
    }
    internal static IReadOnlyList<KeyValuePair<string, string>> Current() => Environment.GetEnvironmentVariables().Cast<DictionaryEntry>()
        .Select(p => new KeyValuePair<string, string>((string)p.Key, (string?)p.Value ?? "")).ToArray();
    internal static void SupervisorPreflight(IEnumerable<KeyValuePair<string, string>> actual, IReadOnlyDictionary<string, string> expected)
    {
        // Boundary A only: hooks may ALREADY have run before this check.
        var values = Unique(actual);
        foreach (var p in values)
            if (runtimePrefixes.Any(prefix => p.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)))
                Contract.Require(expected.TryGetValue(p.Key, out var value) && p.Value == value, "supervisor_runtime_environment_denied");
        foreach (string key in new[] { "TEMP", "TMP", "DOTNET_CLI_HOME", "LOCALAPPDATA", "SystemRoot", "windir" })
            Contract.Require(values.TryGetValue(key, out var value) && value == expected[key], "supervisor_environment_value");
    }
    internal static void RequireCurrentWorker(string block, IReadOnlyDictionary<string, string> expected)
    {
        var parsed = Parse(block); ValidateExact(parsed, expected); ValidateExact(Current(), expected);
        Contract.Require(Build(Current(), expected) == block, "worker_environment_binding");
    }
}
