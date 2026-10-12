using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using J1AI.SmokeCoordination;

namespace J1AI.SmokeNetworkObserver.Tests;

internal sealed record PeerCommand(string Action, string Value = "");
internal sealed record PeerReply(bool Ok, string Kind, int Pid = 0, long Birth = 0, bool Stopped = false, int Initialized = 0);

// No GUI, collector, backend, files, native events or child creation. EOF and the
// bounded input deadline end this owned peer even if its controller disappears.
internal static class RealPipePeer
{
    internal static async Task<int> Run(string name, string encoded, string challenge, string mode)
    {
        CoordinationPipe? pipe = null;
        NamedPipeClientStream? raw = null;
        try
        {
            Program.Check(name.StartsWith("J1AI.SmokeCoordination.Tests.", StringComparison.Ordinal) &&
                Guid.TryParseExact(name["J1AI.SmokeCoordination.Tests.".Length..], "N", out _), "peer_test_namespace");
            Program.Check(Guid.TryParseExact(challenge, "N", out _) && encoded.Length <= 8192 && mode is "worker" or "raw", "peer_arguments");
            var binding = JsonSerializer.Deserialize<RunBinding>(Convert.FromBase64String(encoded))!;
            using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(30));
            long now = 0; int initialized = 0;
            WorkerGate? gate = null; WorkerMessageReceiver? receiver = null;
            if (mode == "raw")
            {
                raw = new NamedPipeClientStream(".", name, PipeDirection.InOut, PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
                await raw.ConnectAsync(lifetime.Token);
                Reply(new(true, "Connected"));
            }
            else
            {
                pipe = await CoordinationPipe.ConnectForTest(name, binding, lifetime.Token);
                gate = new(binding, () => now, () => pipe.Alive);
                receiver = new(binding, challenge, gate);
                Reply(new(true, "Connected", pipe.PeerPid, pipe.PeerBirth));
            }
            while (await Console.In.ReadLineAsync(lifetime.Token) is { } line)
            {
                Program.Check(line.Length <= 8192, "peer_input_limit");
                var command = JsonSerializer.Deserialize<PeerCommand>(line)!;
                if (command.Action == "exit") return 0;
                try
                {
                    string kind = command.Action;
                    using var deadline = CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token);
                    deadline.CancelAfter(TimeSpan.FromSeconds(4));
                    switch (command.Action)
                    {
                        case "hello":
                            var hello = binding with { Run = "" };
                            if (command.Value == "run") hello = hello with { Run = Guid.NewGuid().ToString("N") };
                            if (command.Value == "identity") hello = hello with { Identity = "test-foreign-identity" };
                            if (command.Value == "manifest") hello = hello with { ManifestSha = new('0', 64) };
                            if (command.Value == "binary") hello = hello with { RunnerSha = new('0', 64) };
                            await pipe!.Send(new("Hello", hello, 0, challenge), deadline.Token);
                            break;
                        case "arm":
                            gate!.Arm();
                            await pipe!.Send(new("Armed", binding, 0, challenge, Guid.NewGuid().ToString("N")), deadline.Token);
                            break;
                        case "backend":
                            await pipe!.Send(new("Backend", binding, 0, challenge, Port: 45678), deadline.Token); break;
                        case "close":
                            await pipe!.Send(new("Close", binding, 0, challenge), deadline.Token); break;
                        case "fault":
                            await pipe!.Send(new("Unexpected", binding, 0, challenge), deadline.Token); break;
                        case "challenge":
                            await pipe!.Send(new("Backend", binding, 0, Guid.NewGuid().ToString("N"), Port: 45678), deadline.Token); break;
                        case "stale":
                            await pipe!.Send(new("Backend", binding with { Run = Guid.NewGuid().ToString("N") }, 0, challenge, Port: 45678), deadline.Token); break;
                        case "read":
                            var message = await pipe!.Read(deadline.Token); kind = message.Kind;
                            if (kind == "Ready")
                            {
                                CoordinationSession.Require(message.Binding == binding && message.Challenge == challenge, "peer_ready_binding");
                                gate!.Ready(binding);
                            }
                            else receiver!.Accept(message);
                            break;
                        case "initialize":
                            await gate!.Initialize(45678, () => { initialized++; return Task.CompletedTask; }); break;
                        case "advance": now += long.Parse(command.Value, System.Globalization.CultureInfo.InvariantCulture); break;
                        case "status": break;
                        case "disconnect": pipe?.Dispose(); raw?.Dispose(); receiver?.Disconnect(); break;
                        case "partial-header":
                            await raw!.WriteAsync(new byte[] { 8, 0 }, deadline.Token); await raw.FlushAsync(deadline.Token); raw.Dispose(); break;
                        case "partial-body":
                            await raw!.WriteAsync(BitConverter.GetBytes(8).Concat(new byte[] { 123 }).ToArray(), deadline.Token);
                            await raw.FlushAsync(deadline.Token); raw.Dispose(); break;
                        default: throw new IOException("peer_command");
                    }
                    Reply(new(true, kind, Stopped: receiver?.StopRequested ?? false, Initialized: initialized));
                }
                catch (Exception error) when (error is IOException or OperationCanceledException)
                {
                    receiver?.Disconnect();
                    Reply(new(false, error.GetType().Name, Stopped: true, Initialized: initialized));
                }
            }
            return 0;
        }
        catch (Exception error)
        {
            Reply(new(false, error.GetType().Name)); return 1;
        }
        finally { pipe?.Dispose(); raw?.Dispose(); }
    }
    private static void Reply(PeerReply reply) { Console.WriteLine(JsonSerializer.Serialize(reply)); Console.Out.Flush(); }
}
