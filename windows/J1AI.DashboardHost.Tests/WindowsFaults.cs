using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class WindowsFaults
{
    private sealed class Calls : SpawnCalls, IDisposable
    {
        internal string? Collision;
        internal bool FailConfiguration, InvalidJob, OmitJob;
        internal int Creations;
        internal KernelHandle? Retained;
        internal override KernelHandle CreateJob() => Native.CreateJobObjectW(0, Collision);
        internal override bool ConfigureJob(KernelHandle job, ref Native.ExtendedLimits limits) =>
            !FailConfiguration && base.ConfigureJob(job, ref limits);
        internal override void AddJob(Attributes attributes, KernelHandle job)
        {
            if (!OmitJob) attributes.Add(Native.JobList, InvalidJob ? 0 : job.DangerousGetHandle());
        }
        internal override bool CreateProcess(ServerCommand command, ref Native.StartupEx startup, out Native.ProcessInfo info)
        {
            Creations++;
            bool success = base.CreateProcess(command, ref startup, out info);
            if (success) Retained = Native.Duplicate(info.Process, false);
            return success;
        }
        public void Dispose() => Retained?.Dispose();
    }

    private static ServerCommand Child(string python, string script, string root) =>
        new(python, ["-I", "-S", "-u", script, "silent"], root);
    private static void Fails(Action run)
    {
        try { run(); }
        catch (HostError error) { Program.Check(error.Code == EventCode.SpawnFailed); return; }
        throw new InvalidOperationException("expected_spawn_failure");
    }
    private static InstanceControls Gate(TempRepository temp)
    { var gate = new InstanceControls(temp.Identity); Program.Check(gate.Acquire()); return gate; }
    private static void Restart(TempRepository temp, InstanceControls gate)
    {
        gate.Dispose(); using var next = Gate(temp);
    }

    internal static Task JobCreation(string python, string script)
    {
        using var temp = new TempRepository(); using var gate = Gate(temp);
        string name = @"Local\J1AI.Test.Collision." + Guid.NewGuid();
        using var collision = Native.CreateEventW(0, true, false, name);
        using var calls = new Calls { Collision = name };
        Fails(() => OwnedServer.Start(Child(python, script, temp.Root), gate, null, calls));
        Program.Check(calls.Creations == 0 && !collision.IsInvalid);
        Restart(temp, gate); return Task.CompletedTask;
    }
    internal static Task JobConfiguration(string python, string script)
    {
        using var temp = new TempRepository(); using var gate = Gate(temp);
        using var calls = new Calls { FailConfiguration = true };
        Fails(() => OwnedServer.Start(Child(python, script, temp.Root), gate, null, calls));
        Program.Check(calls.Creations == 0);
        Restart(temp, gate); return Task.CompletedTask;
    }
    internal static Task Assignment(string python, string script)
    {
        using var temp = new TempRepository(); using var gate = Gate(temp);
        using var calls = new Calls { InvalidJob = true };
        Fails(() => OwnedServer.Start(Child(python, script, temp.Root), gate, null, calls));
        // Win32 rejects the invalid JOB_LIST at attribute update or CreateProcess;
        // there is no retry without assignment and no resumed child.
        Program.Check(calls.Creations <= 1 && calls.Retained == null);
        Restart(temp, gate); return Task.CompletedTask;
    }
    internal static Task MissingAssignment(string python, string script)
    {
        using var temp = new TempRepository(); using var gate = Gate(temp);
        using var calls = new Calls { OmitJob = true };
        Fails(() => OwnedServer.Start(Child(python, script, temp.Root), gate, null, calls));
        // Real suspended child deliberately created without the Job by the test
        // seam: the non-overridable pre-Resume check rejects and reclaims it.
        Program.Check(calls.Creations == 1 && calls.Retained != null);
        Program.Check(Native.WaitForSingleObject(calls.Retained!, 0) == Native.WaitObject);
        Restart(temp, gate); return Task.CompletedTask;
    }
    internal static Task Inheritance(string python, string script, bool job)
    {
        using var temp = new TempRepository(); using var gate = Gate(temp);
        using var calls = new Calls();
        Fails(() => OwnedServer.Start(Child(python, script, temp.Root), gate,
            (jobHandle, gateHandle, output, nul) =>
            {
                using var wrapper = new KernelHandle(job ? jobHandle : gateHandle);
                bool changed = Native.SetHandleInformation(wrapper, 1, job ? 1u : 0u);
                wrapper.Detach(); // observer borrows; factory still owns it
                Program.Check(changed);
                return Child(python, script, temp.Root);
            }, calls));
        Program.Check(calls.Creations == 0);
        Restart(temp, gate); return Task.CompletedTask;
    }
}
