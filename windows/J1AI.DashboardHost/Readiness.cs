using System.Net;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace J1AI.DashboardHost;

public interface IReadiness
{
    Task<string> WaitAsync(IServer server, CancellationToken token);
}

public sealed class Readiness : IReadiness
{
    public const int MaxBytes = 1024 * 1024;
    public const string ChampionVersion = "operational_champion_20260922_v1";
    private const string Prefix = "J1AI dashboard: ";

    public static string ValidateUrl(string url)
    {
        var match = Regex.Match(url, @"\Ahttp://127\.0\.0\.1:([0-9]{1,5})/\z", RegexOptions.CultureInvariant);
        if (!match.Success || !int.TryParse(match.Groups[1].Value, out int port) || port is < 1 or > 65535)
            throw new HostError(EventCode.InvalidUrl);
        return url;
    }

    internal static async Task<string> ReadUrlAsync(TextReader reader, CancellationToken token)
    {
        var buffer = new char[1];
        for (int line = 0; line < 16; line++)
        {
            var text = new System.Text.StringBuilder();
            while (true)
            {
                int size = await reader.ReadAsync(buffer.AsMemory(), token);
                if (size == 0) throw new HostError(EventCode.InvalidUrl);
                if (buffer[0] == '\n') break;
                text.Append(buffer[0]);
                if (text.Length > 4096) throw new HostError(EventCode.InvalidUrl);
            }
            var value = text.ToString().TrimEnd('\r');
            if (value.StartsWith(Prefix, StringComparison.Ordinal)) return ValidateUrl(value[Prefix.Length..]);
        }
        throw new HostError(EventCode.InvalidUrl);
    }

    public async Task<string> WaitAsync(IServer server, CancellationToken token)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(token);
        var operation = ProbeAsync(server, lifetime.Token);
        try
        {
            // Total deadline, even if a TextReader or socket ignores cancellation.
            while (!operation.IsCompleted)
            {
                token.ThrowIfCancellationRequested();
                if (server.Exited) throw new HostError(EventCode.ServerExited);
                await Task.WhenAny(operation, Task.Delay(20, token));
            }
            var url = await operation;
            if (server.Exited) throw new HostError(EventCode.ServerExited);
            return url;
        }
        finally
        {
            lifetime.Cancel();
            // Observe a late fault without logging it. Closing the owned Job
            // breaks a blocked stdout read on timeout/STOP.
            _ = operation.ContinueWith(t => { _ = t.Exception; }, CancellationToken.None,
                TaskContinuationOptions.OnlyOnFaulted, TaskScheduler.Default);
        }
    }

    private static async Task<string> ProbeAsync(IServer server, CancellationToken token)
    {
        string url = await ReadUrlAsync(server.Output, token);
        using var handler = CreateHandler();
        using var client = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        while (true)
        {
            token.ThrowIfCancellationRequested();
            if (server.Exited) throw new HostError(EventCode.ServerExited);
            try
            {
                using var response = await client.GetAsync(url + "api/dashboard", HttpCompletionOption.ResponseHeadersRead, token);
                await ValidateResponseAsync(response, token);
                return url;
            }
            catch (HttpRequestException) { await Task.Delay(50, token); }
        }
    }

    internal static SocketsHttpHandler CreateHandler() => new()
    { UseProxy = false, AllowAutoRedirect = false, UseCookies = false, ConnectTimeout = TimeSpan.FromSeconds(1) };

    internal static async Task ValidateResponseAsync(HttpResponseMessage response, CancellationToken token)
    {
        if (response.StatusCode != HttpStatusCode.OK ||
            !string.Equals(response.Content.Headers.ContentType?.MediaType, "application/json", StringComparison.OrdinalIgnoreCase) ||
            response.Content.Headers.ContentLength > MaxBytes)
            throw new HostError(EventCode.InvalidResponse);
        using var stream = await response.Content.ReadAsStreamAsync(token);
        using var memory = new MemoryStream();
        var buffer = new byte[8192];
        int size;
        while ((size = await stream.ReadAsync(buffer, token)) != 0)
        {
            if (memory.Length + size > MaxBytes) throw new HostError(EventCode.InvalidResponse);
            memory.Write(buffer, 0, size);
        }
        ValidatePayload(memory.ToArray());
    }

    public static void ValidatePayload(byte[] bytes)
    {
        try
        {
            using var document = JsonDocument.Parse(bytes);
            var root = document.RootElement;
            RejectDuplicates(root);
            Exact(root, "schemaVersion", "mode", "model", "updatedAt", "previousRound", "nextRound");
            if (root.GetProperty("schemaVersion").GetRawText() != "1" ||
                root.GetProperty("mode").GetString() != "operational") Fail();
            var model = root.GetProperty("model");
            Exact(model, "name", "version");
            if (model.GetProperty("name").GetString() != "Champion A" ||
                model.GetProperty("version").GetString() != ChampionVersion) Fail();
            if (root.GetProperty("updatedAt").ValueKind is not (JsonValueKind.Null or JsonValueKind.String)) Fail();
            foreach (var name in new[] { "previousRound", "nextRound" })
            {
                var section = root.GetProperty(name);
                Exact(section, "label", "matches");
                if (string.IsNullOrWhiteSpace(section.GetProperty("label").GetString()) ||
                    section.GetProperty("matches").ValueKind != JsonValueKind.Array) Fail();
            }
        }
        catch (Exception) { throw new HostError(EventCode.InvalidResponse); }
    }
    private static void Exact(JsonElement value, params string[] keys)
    {
        if (value.ValueKind != JsonValueKind.Object ||
            !value.EnumerateObject().Select(p => p.Name).Order().SequenceEqual(keys.Order())) Fail();
    }
    private static void RejectDuplicates(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            { if (!names.Add(property.Name)) Fail(); RejectDuplicates(property.Value); }
        }
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var item in value.EnumerateArray()) RejectDuplicates(item);
    }
    private static void Fail() => throw new HostError(EventCode.InvalidResponse);
}
