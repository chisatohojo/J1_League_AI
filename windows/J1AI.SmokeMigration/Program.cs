using System.Text;
using System.Text.Json;

namespace J1AI.SmokeMigration;

public static class Program
{
    public static int Main(string[] args)
    {
        try
        {
            if (args is [] or ["--help"])
            {
                Console.WriteLine("Phase A read-only migration planner. --inspect prints an in-memory plan and its SHA. No apply, backup, state-write, GUI or IPC entry exists."); return 0;
            }
            Contract.Require(args is ["--inspect"], "arguments");
            using var inspection = new Inspector(); var plan = inspection.Inspect();
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(plan, Contract.Json);
            Console.WriteLine(Encoding.UTF8.GetString(bytes)); Console.WriteLine("PLAN_SHA256=" + Contract.Hash(bytes)); return 0;
        }
        catch (Exception e)
        {
            string code = e is InvalidDataException && System.Text.RegularExpressions.Regex.IsMatch(e.Message, "\\A[a-z0-9_]+(:[0-9]+)?\\z") ? e.Message : "unexpected_failure";
            Console.Error.WriteLine("MIGRATION_PHASE_A_BLOCKED " + code + ": read-only inspection failed; no real environment changes made."); return 1;
        }
    }
}
