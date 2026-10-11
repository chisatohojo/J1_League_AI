using System.Diagnostics;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Win32.SafeHandles;

namespace J1AI.SmokeCoordination;

public sealed record CoordinationMessage(string Kind, RunBinding Binding, long Sequence, string Challenge,
    string? FixtureRun = null, int Port = 0, string? Permit = null);

// Current-user, first-instance local pipe. No stdout/file-existence authorization.
// Same-user malicious code is outside this boundary; a nonce is correlation, not authentication.
public sealed class CoordinationPipe : IDisposable
{
    public static string Name => "J1AI.SmokeCoordination." + CoordinationSession.FixedIdentity;
    private readonly PipeStream stream;
    private readonly Process peer;
    private readonly FileStream image;
    private readonly SemaphoreSlim writing = new(1);
    private long sent, received;
    private int disposed;
    public int PeerPid => peer.Id;
    public long PeerBirth { get; }
    public bool Alive
    {
        get { try { return Volatile.Read(ref disposed) == 0 && !peer.HasExited && peer.StartTime.ToUniversalTime().ToFileTimeUtc() == PeerBirth; } catch { return false; } }
    }
    [DllImport("kernel32", SetLastError = true)] private static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe, out uint pid);
    [DllImport("kernel32", SetLastError = true)] private static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out uint pid);
    private CoordinationPipe(PipeStream stream, bool server, RunBinding expected)
    {
        this.stream = stream;
        bool ok = server ? GetNamedPipeClientProcessId(stream.SafePipeHandle, out uint pid) : GetNamedPipeServerProcessId(stream.SafePipeHandle, out pid);
        CoordinationSession.Require(ok && pid is > 0 and <= int.MaxValue, "coord_peer_pid");
        peer = Process.GetProcessById((int)pid);
        FileStream? held = null;
        try
        {
            _ = peer.SafeHandle; // retain the process object, not merely a reusable PID
            PeerBirth = peer.StartTime.ToUniversalTime().ToFileTimeUtc();
            string executable = peer.MainModule?.FileName ?? throw new IOException("coord_peer_image");
            held = new FileStream(executable, FileMode.Open, FileAccess.Read, FileShare.Read);
            string hash = Convert.ToHexString(SHA256.HashData(held)).ToLowerInvariant();
            CoordinationSession.Require(hash == expected.DotnetSha || server && hash == expected.RunnerExeSha, "coord_peer_image_hash");
            CoordinationSession.Require(Alive, "coord_peer_dead");
            image = held; held = null;
        }
        catch { held?.Dispose(); peer.Dispose(); throw; }
    }
    public static NamedPipeServerStream Listen() => new(Name, PipeDirection.InOut, 1, PipeTransmissionMode.Byte,
        PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly | PipeOptions.FirstPipeInstance);
    public static async Task<CoordinationPipe> Accept(NamedPipeServerStream listener, RunBinding expected, CancellationToken token)
    {
        try { await listener.WaitForConnectionAsync(token); return new(listener, true, expected); }
        catch { listener.Dispose(); throw; }
    }
    public static async Task<CoordinationPipe> Connect(RunBinding expected, CancellationToken token)
    {
        var client = new NamedPipeClientStream(".", Name, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        try { await client.ConnectAsync(token); return new(client, false, expected); }
        catch { client.Dispose(); throw; }
    }
    public async Task Send(CoordinationMessage message, CancellationToken token)
    {
        await writing.WaitAsync(token);
        try
        {
            CoordinationSession.Require(Alive, "coord_peer_dead");
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(message with { Sequence = ++sent });
            CoordinationSession.Require(bytes.Length <= 8192 && sent <= 4096, "coord_message_limit");
            await stream.WriteAsync(BitConverter.GetBytes(bytes.Length), token); await stream.WriteAsync(bytes, token);
            await stream.FlushAsync(token);
        }
        finally { writing.Release(); }
    }
    public async Task<CoordinationMessage> Read(CancellationToken token)
    {
        byte[] length = new byte[4]; await stream.ReadExactlyAsync(length, token);
        int count = BitConverter.ToInt32(length);
        CoordinationSession.Require(count is > 0 and <= 8192, "coord_message_limit");
        byte[] bytes = new byte[count]; await stream.ReadExactlyAsync(bytes, token);
        var message = Decode(bytes, ++received);
        CoordinationSession.Require(Alive, "coord_peer_dead");
        return message;
    }
    internal static CoordinationMessage Decode(byte[] bytes, long sequence)
    {
        CoordinationSession.Require(bytes.Length is > 0 and <= 8192 && sequence is > 0 and <= 4096, "coord_message_limit");
        using var doc = JsonDocument.Parse(bytes);
        void Unique(JsonElement value)
        {
            if (value.ValueKind == JsonValueKind.Object)
            {
                var keys = new HashSet<string>(StringComparer.Ordinal);
                foreach (var item in value.EnumerateObject()) { CoordinationSession.Require(keys.Add(item.Name), "coord_duplicate_field"); Unique(item.Value); }
            }
            else if (value.ValueKind == JsonValueKind.Array) foreach (var item in value.EnumerateArray()) Unique(item);
        }
        Unique(doc.RootElement);
        var message = JsonSerializer.Deserialize<CoordinationMessage>(bytes, new JsonSerializerOptions { UnmappedMemberHandling = System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow })
            ?? throw new IOException("coord_message_missing");
        CoordinationSession.Require(message.Sequence == sequence, "coord_sequence_or_peer");
        return message;
    }
    public void Dispose()
    {
        if (Interlocked.Exchange(ref disposed, 1) != 0) return;
        stream.Dispose(); image.Dispose(); peer.Dispose();
    }
}

// Worker-local latch. Used by the real test-only entry and deterministic Fake tests.
public sealed class WorkerGate(RunBinding binding, Func<long> now, Func<bool> alive)
{
    private readonly object sync = new();
    private bool ready, armed, aborted, initialized;
    private long lastPulse = now();
    private int port;
    public string? Permit { get; private set; }
    public bool Aborted { get { lock (sync) { CheckLease(); return aborted; } } }
    private void CheckLease() { if (!alive() || now() - lastPulse > 1500) aborted = true; }
    public void Ready(RunBinding value) { lock (sync) { CoordinationSession.Require(value == binding && !ready, "worker_ready_binding"); ready = true; lastPulse = now(); } }
    public void Pulse(RunBinding value) { lock (sync) { CoordinationSession.Require(value == binding, "worker_foreign_run"); CheckLease(); lastPulse = now(); } }
    public void Arm() { lock (sync) { CheckLease(); CoordinationSession.Require(ready && !aborted, "worker_not_ready"); armed = true; } }
    public void Grant(RunBinding value, int backendPort, string permit)
    {
        lock (sync)
        {
            CheckLease(); CoordinationSession.Require(value == binding && ready && armed && !aborted && Permit == null &&
                backendPort is > 0 and <= 65535 && Guid.TryParseExact(permit, "N", out _), "worker_bad_permit");
            port = backendPort; Permit = permit;
        }
    }
    public void Abort() { lock (sync) aborted = true; }
    public Task Initialize(int backendPort, Func<Task> call)
    {
        lock (sync)
        {
            CheckLease(); CoordinationSession.Require(ready && armed && !aborted && !initialized && Permit != null && port == backendPort, "worker_initialize_blocked");
            initialized = true; return call();
        }
    }
}
