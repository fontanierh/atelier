using UnrealBuildTool;

public class Yorimichi : ModuleRules
{
    public Yorimichi(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "InputCore", "AtelierCore", "AtelierAnimation", "AtelierLive", "AtelierFX", "AtelierSkate", "AtelierStream", "EnhancedInput", "AnimGraphRuntime", "Json", "AssetRegistry", "RenderCore", "Slate", "SlateCore", "ProceduralMeshComponent", "HTTPServer", "GLTFCore", "MeshDescription", "StaticMeshDescription" });
        // The live bridge runs agent Python in uncooked (editor-binary) sessions only.
        if (Target.bBuildEditor) PrivateDependencyModuleNames.Add("PythonScriptPlugin");
        PrivateDependencyModuleNames.Add("AnimationCore");
        PrivateDependencyModuleNames.Add("RHI");
        PrivateDependencyModuleNames.Add("AIModule");
        PrivateDependencyModuleNames.Add("ImageCore");
        PrivateDependencyModuleNames.Add("ApplicationCore");
    }
}
