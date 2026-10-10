using System.Runtime.InteropServices;
using System.Text;
using J1AI.DashboardHost;

namespace J1AI.DashboardHost.Tests;

internal static class TestLinks
{
    [DllImport("kernel32", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool DeviceIoControl(KernelHandle handle, uint code, byte[] input,
        uint inputSize, nint output, uint outputSize, out uint bytes, nint overlapped);
    [DllImport("kernel32", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.U1)]
    private static extern bool CreateSymbolicLinkW(string link, string target, uint flags);

    internal static void Junction(string link, string target)
    {
        Directory.CreateDirectory(link);
        var security = new Native.Security { Length = Marshal.SizeOf<Native.Security>() };
        using var handle = Native.CreateFileW(link, 0x40000000, 3, ref security, 3, 0x02200000, 0);
        Program.Check(!handle.IsInvalid);
        var substitute = Encoding.Unicode.GetBytes(@"\??\" + target);
        var printable = Encoding.Unicode.GetBytes(target);
        int dataSize = 8 + substitute.Length + 2 + printable.Length + 2;
        var buffer = new byte[8 + dataSize];
        BitConverter.GetBytes(0xa0000003u).CopyTo(buffer, 0);
        BitConverter.GetBytes(checked((ushort)dataSize)).CopyTo(buffer, 4);
        BitConverter.GetBytes(checked((ushort)substitute.Length)).CopyTo(buffer, 10);
        BitConverter.GetBytes(checked((ushort)(substitute.Length + 2))).CopyTo(buffer, 12);
        BitConverter.GetBytes(checked((ushort)printable.Length)).CopyTo(buffer, 14);
        substitute.CopyTo(buffer, 16); printable.CopyTo(buffer, 16 + substitute.Length + 2);
        Program.Check(DeviceIoControl(handle, 0x000900a4, buffer, (uint)buffer.Length, 0, 0, out _, 0));
    }
    internal static void TrySymlink(string link, string target)
    {
        if (CreateSymbolicLinkW(link, target, 3)) return;
        // No privilege/policy changes. A true pre-existing OS symlink is used
        // for read-only identity validation when link creation is not allowed.
        Program.Check(Marshal.GetLastWin32Error() is 1314 or 5);
    }
}
