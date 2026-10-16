using System.Security.Cryptography;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace J1AI.SmokeMigration;

public static class Contract
{
    public const string R = "2f19f026b541c5e4cf9d8007847c0032a38c9f1f";
    public const string O = "05c1598f1fa087c39dc1450be65ed075675c1c4c";
    public const string Identity = "8f96edbb39b7d4d47cdad47c";
    public const string OldM = "ce8e230e4deb35b67298f0dcdfecb421cf282125b7ae509de794df91b599cf67";
    public const string OldS = "f7f87885a0b5f66f65e065295bc60a9c989a63ce654b5502dac014a36e1d04a7";
    public const string M = "15d60923e1b3f2f418c47c8d098f1e739aa66520a789c134fd86a8782153a09f";
    public const string S = "cac6b11167c135cc3bd5b70b25ce9f93a4772ad14fdd5ec39c96fd6fa9b9ed58";
    public const string Runner = "300f5512f759fdea25fe12e8be28bb89a8b355d47dd67c4490948a1e61d443fa";
    public const string Product = "f951c61fe1b5c5a214d3e12a7b7d3d134dcd09ac130f19c36e4cc67c57adad57";
    public const string Observer = "ff1882a17745b6c772080d0592fa683b016cd9cc8716d7a78b8b9bd89d991aa0";
    public const string Pending = "refreeze-migration.pending";
    public static readonly JsonSerializerOptions Json = new() { UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow };
    public static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    public static void Require([DoesNotReturnIf(false)] bool condition, string code) { if (!condition) throw new InvalidDataException(code); }
    public static T Parse<T>(byte[] bytes)
    {
        Require(bytes.Length <= 1024 * 1024, "metadata_size");
        using var doc = JsonDocument.Parse(bytes);
        void Unique(JsonElement e)
        {
            if (e.ValueKind == JsonValueKind.Object)
            {
                var seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (var item in e.EnumerateObject()) { Require(seen.Add(item.Name), "duplicate_metadata"); Unique(item.Value); }
            }
            else if (e.ValueKind == JsonValueKind.Array) foreach (var item in e.EnumerateArray()) Unique(item);
        }
        Unique(doc.RootElement);
        return JsonSerializer.Deserialize<T>(bytes, Json) ?? throw new InvalidDataException("metadata_null");
    }
}
public sealed record HashFile(string Path, string SHA256);
public sealed record RunnerFile(string FixedPath, string OldSHA256, string CandidatePath, string CandidateSHA256, bool Changed);
public sealed record Catalog(int Version, string Repository, HashFile[] Fixed, HashFile[] OldObserver, RunnerFile[] Runner, HashFile[] Protected);
public sealed record Manifest(int Version, string Root, string Identity, string Udf, string ProductionIdentity,
    SortedDictionary<string, string> Hashes, string[] BaselineUdfs, string Runtime);
// Property order/names exactly mirror SmokeRecord; State is an integer enum on disk.
public sealed record FrozenState(string ManifestHash, int State, string Run, bool RuntimeEnded, bool ServerEnded,
    bool WindowDisposed, bool InventoryValid, string UdfIdentity, string RootIdentity);
public sealed record PlanFile(int BackupIndex, string SourcePath, string? CandidatePath, string FinalPath,
    string OldSha, string NewSha, bool Rewrite, string Role, string[] Dependencies, string Reason);
public sealed record MigrationPlan(int Version, string RunnerRevision, string ObserverRevision, string Identity,
    PlanFile[] Files, byte[] ManifestBytes, byte[] StateBytes, string ManifestSha, string StateSha,
    string ObserverSha, string PendingMarker, string BackupLayout, string[] Sequence, string[] ExclusionContract,
    bool RealApplyAvailable = false);
