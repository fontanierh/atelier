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
        // Match network_identity.py: relative UTF-8 path, NUL, file SHA1, newline.
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
            using (SHA1 Hash = SHA1.Create())
            using (FileStream Stream = System.IO.File.OpenRead(File))
                Records.Append(Path.GetRelativePath(Root, File).Replace('\\', '/')).Append('\0')
                    .Append(Convert.ToHexString(Hash.ComputeHash(Stream)).ToLowerInvariant()).Append('\n');
        }
        string Code;
        using (SHA1 Hash = SHA1.Create())
            Code = Convert.ToHexString(Hash.ComputeHash(Encoding.UTF8.GetBytes(Records.ToString()))).ToLowerInvariant();
        // The digest changes with every source edit: as a module definition it would recompile every file, so it goes to
        // a generated header that only the network files include, rewritten only when it changes.
        string BuildTarget = Target.Platform + "/" + Target.Type + "/" + Target.Configuration;
        string InputDigest;
        using (SHA256 Hash = SHA256.Create())
            InputDigest = Convert.ToHexString(Hash.ComputeHash(Encoding.UTF8.GetBytes(Code + "\n" + BuildTarget + "\n"))).ToLowerInvariant();
        string Generated = Path.Combine(ModuleDirectory, "../../Intermediate/BuildIdentity", BuildTarget.Replace('/', '_'));
        Directory.CreateDirectory(Generated);
        string Header = Path.Combine(Generated, "YorimichiBuildIdentity.h");
        string Contents = "#pragma once\n#define YORIMICHI_NETWORK_BUILD_ID \"" + Code + "\"\n#define YORIMICHI_COMPILED_TARGET \"" +
            BuildTarget + "\"\n#define YORIMICHI_COMPILED_INPUT_DIGEST \"" + InputDigest + "\"\n";
        if (!System.IO.File.Exists(Header) || System.IO.File.ReadAllText(Header) != Contents)
            System.IO.File.WriteAllText(Header, Contents);
        PrivateIncludePaths.Add(Generated);
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Dev/ holds the opt-in review, benchmark and film code; it includes the game headers beside this file.
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "AtelierCore", "AtelierAnimation", "AtelierLive", "AtelierFX", "AtelierSkate", "AtelierStream", "EnhancedInput", "AnimGraphRuntime", "Json", "AssetRegistry", "RenderCore", "Slate", "SlateCore", "ProceduralMeshComponent", "Sockets" });
        PublicDependencyModuleNames.Add("OnlineSubsystemUtils");
        // Character cloth is built by editor scripting (YorimichiCloth.cpp, run by Scripts/import_modori.py).
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "ClothingSystemEditorInterface", "ClothingSystemRuntimeCommon", "SkeletalMeshEditor", "ChaosCloth" });
        PrivateDependencyModuleNames.Add("AnimationCore");
        PrivateDependencyModuleNames.Add("ClothingSystemRuntimeInterface");   // YorimichiCloth: the running cloth's data
        PrivateDependencyModuleNames.Add("RHI");
        PrivateDependencyModuleNames.Add("GeometryCore");
        PrivateDependencyModuleNames.Add("AIModule");
        PrivateDependencyModuleNames.Add("ImageCore");
        PrivateDependencyModuleNames.Add("ApplicationCore");
    }
}
