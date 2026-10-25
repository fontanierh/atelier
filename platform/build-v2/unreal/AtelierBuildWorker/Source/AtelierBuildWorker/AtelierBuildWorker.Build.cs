using UnrealBuildTool;
using System.IO;
using System;
using System.Linq;
using System.Text;
using System.Security.Cryptography;

public class AtelierBuildWorker : ModuleRules
{
    public AtelierBuildWorker(ReadOnlyTargetRules Target) : base(Target)
    {
        // Bind the loaded native implementation to its exact portable source closure.
        string PluginRoot = Path.GetFullPath(Path.Combine(ModuleDirectory, "../.."));
        string[] SourceFiles = Directory.GetFiles(Path.Combine(PluginRoot, "Source"), "*", SearchOption.AllDirectories)
            .Where(File => new[] { ".cs", ".cpp", ".h" }.Contains(Path.GetExtension(File), StringComparer.Ordinal))
            .Append(Path.Combine(PluginRoot, "AtelierBuildWorker.uplugin"))
            .OrderBy(File => Path.GetRelativePath(PluginRoot, File).Replace('\\', '/'), StringComparer.Ordinal).ToArray();
        StringBuilder Manifest = new StringBuilder();
        foreach (string File in SourceFiles)
        {
            ExternalDependencies.Add(File);
            Manifest.Append(Path.GetRelativePath(PluginRoot, File).Replace('\\', '/')).Append('\0')
                .Append(Convert.ToHexString(SHA256.HashData(System.IO.File.ReadAllBytes(File))).ToLowerInvariant()).Append('\n');
        }
        string SourceDigest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Manifest.ToString()))).ToLowerInvariant();
        PrivateDefinitions.Add("ATELIER_BUILD_WORKER_SOURCE_DIGEST=\"" + SourceDigest + "\"");
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Developer/IoStoreUtilities/Internal"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Developer/Zen/Internal"));
        PrivateIncludePaths.Add(Path.Combine(EngineDirectory, "Source/Runtime/RenderCore/Internal"));
        // Each native verifier owns file-local helpers; keep translation units separate.
        bUseUnity = false;
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine" });
        PrivateDependencyModuleNames.AddRange(new string[] { "AssetRegistry", "DerivedDataCache", "InterchangeEngine", "Json", "IoStoreUtilities", "Zen", "RenderCore", "TargetPlatform", "CookMetadata", "Projects", "RHI", "UnrealEd" });
    }
}
