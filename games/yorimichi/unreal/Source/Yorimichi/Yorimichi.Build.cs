using UnrealBuildTool;

public class Yorimichi : ModuleRules
{
    public Yorimichi(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        // Dev/ holds the opt-in review, benchmark and film code; it includes the game headers beside this file.
        PrivateIncludePaths.Add(ModuleDirectory);
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "AtelierCore", "AtelierAnimation", "AtelierLive", "AtelierFX", "AtelierSkate", "AtelierStream", "EnhancedInput", "AnimGraphRuntime", "Json", "AssetRegistry", "RenderCore", "Slate", "SlateCore", "ProceduralMeshComponent", "HTTPServer", "GLTFCore", "MeshDescription", "StaticMeshDescription" });
        // The live bridge runs agent Python in uncooked (editor-binary) sessions only.
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("PythonScriptPlugin");
        // Character cloth is built by editor scripting (YorimichiCloth.cpp, run by Scripts/import_modori.py).
        if (Target.bBuildEditor) PrivateDependencyModuleNames.AddRange(new string[] { "UnrealEd", "ClothingSystemEditorInterface", "ClothingSystemRuntimeCommon", "ClothingSystemRuntimeInterface", "SkeletalMeshEditor", "ChaosCloth" });
        PrivateDependencyModuleNames.Add("AnimationCore");
        PrivateDependencyModuleNames.Add("RHI");
        PrivateDependencyModuleNames.Add("AIModule");
        PrivateDependencyModuleNames.Add("ImageCore");
        PrivateDependencyModuleNames.Add("ApplicationCore");
    }
}
