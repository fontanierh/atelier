using UnrealBuildTool;
using System;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

public class Yorimichi : ModuleRules
{
    public Yorimichi(ReadOnlyTargetRules Target) : base(Target)
    {
        // Match network_identity.py: relative UTF-8 path, NUL, source SHA1, newline.
        // Normalize CRLF to LF only for source; content identity remains byte-exact.
        // Track every enumerated source so UBT cannot reuse an old compatibility definition.
        string Root = Path.GetFullPath(Path.Combine(ModuleDirectory, "../../../../.."));
        string[] Roots = { Path.Combine(Root, "games/yorimichi/unreal/Source"), Path.Combine(Root, "games/yorimichi/unreal/Config"), Path.Combine(Root, "platform/engine/Plugins") };
        string[] Extensions = { ".h", ".hpp", ".cpp", ".c", ".cs", ".uplugin", ".inl", ".inc", ".mm", ".m", ".ush", ".usf", ".ini", ".uproject" };
        string[] Ignored = { "Binaries", "Intermediate", "Saved", "DerivedDataCache", "__pycache__" };
        var Files = Roots.SelectMany(Dir => Directory.EnumerateFiles(Dir, "*", SearchOption.AllDirectories))
            .Concat(Directory.EnumerateFiles(Path.Combine(Root, "games/yorimichi/unreal"), "*.uproject"))
            .Where(File => Extensions.Contains(Path.GetExtension(File)) &&
                !Path.GetRelativePath(Root, File).Split(Path.DirectorySeparatorChar).Any(Ignored.Contains))
            .OrderBy(File => Path.GetRelativePath(Root, File).Replace('\\', '/'), StringComparer.Ordinal);
        StringBuilder Records = new StringBuilder();
        foreach (string File in Files)
        {
            ExternalDependencies.Add(File);
            byte[] Bytes = System.IO.File.ReadAllBytes(File);
            int Count = 0;
            for (int Index = 0; Index < Bytes.Length; ++Index)
            {
                if (Bytes[Index] == 13 && Index + 1 < Bytes.Length && Bytes[Index + 1] == 10) continue;
                Bytes[Count++] = Bytes[Index];
            }
            using (SHA1 Hash = SHA1.Create())
                Records.Append(Path.GetRelativePath(Root, File).Replace('\\', '/')).Append('\0')
                    .Append(Convert.ToHexString(Hash.ComputeHash(Bytes, 0, Count)).ToLowerInvariant()).Append('\n');
        }
        string Code;
        using (SHA1 Hash = SHA1.Create())
            Code = Convert.ToHexString(Hash.ComputeHash(Encoding.UTF8.GetBytes(Records.ToString()))).ToLowerInvariant();
        PublicDefinitions.Add("YORIMICHI_NETWORK_BUILD_ID=\"" + Code + "\"");
        string BuildTarget = Target.Platform + "/" + Target.Type + "/" + Target.Configuration;
        PublicDefinitions.Add("YORIMICHI_COMPILED_TARGET=\"" + BuildTarget + "\"");
        using (SHA256 Hash = SHA256.Create())
            PublicDefinitions.Add("YORIMICHI_COMPILED_INPUT_DIGEST=\"" +
                Convert.ToHexString(Hash.ComputeHash(Encoding.UTF8.GetBytes(Code + "\n" + BuildTarget + "\n"))).ToLowerInvariant() + "\"");
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Dev/ holds the opt-in review, benchmark and film code; it includes the game headers beside this file.
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "AtelierCore", "AtelierAnimation", "AtelierLive", "AtelierFX", "AtelierSkate", "AtelierStream", "EnhancedInput", "AnimGraphRuntime", "Json", "AssetRegistry", "RenderCore", "Slate", "SlateCore", "ProceduralMeshComponent", "HTTPServer", "Sockets", "GLTFCore", "MeshDescription", "StaticMeshDescription" });
        // The live bridge runs agent Python in uncooked (editor-binary) sessions only.
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("PythonScriptPlugin");
        PublicDependencyModuleNames.Add("OnlineSubsystemUtils");
        // Character cloth is built by editor scripting (YorimichiCloth.cpp, run by Scripts/import_modori.py).
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "ClothingSystemEditorInterface", "ClothingSystemRuntimeCommon", "SkeletalMeshEditor", "ChaosCloth" });
        PrivateDependencyModuleNames.Add("AnimationCore");
        PrivateDependencyModuleNames.Add("ClothingSystemRuntimeInterface");   // YorimichiCloth: the running cloth's data
        PrivateDependencyModuleNames.Add("RHI");
        PrivateDependencyModuleNames.Add("AIModule");
        PrivateDependencyModuleNames.Add("ImageCore");
        PrivateDependencyModuleNames.Add("ApplicationCore");
    }
}
