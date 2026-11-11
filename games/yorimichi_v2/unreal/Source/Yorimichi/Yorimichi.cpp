#include "Yorimichi.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/InputSettings.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"
#include "UObject/ObjectSaveContext.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

class FYorimichiModule : public FDefaultGameModuleImpl
{
#if WITH_EDITOR
    FDelegateHandle CookedWithoutNavigation;
#endif

    virtual void StartupModule() override
    {
#if WITH_EDITOR
        // Yorimichi has no navigation: no navmesh, and nothing finds paths (the village and the sword trainer steer
        // themselves). The engine would still cook each static mesh with a copy of its collision triangles for a navmesh
        // builder, half a GiB the packaged game loads for nothing (the Crater Park memory report, NavCollision). The cook
        // drops it as it saves each mesh; drawing and physics collision are untouched.
        CookedWithoutNavigation = FCoreUObjectDelegates::OnObjectPreSave.AddLambda([](UObject* Object, FObjectPreSaveContext Context)
        {
            if (UStaticMesh* Mesh = Cast<UStaticMesh>(Object); Mesh && Context.IsCooking()) Mesh->MarkAsNotHavingNavigationData();
        });
#endif

#if !UE_BUILD_SHIPPING
        // Default Performance mode streams a 896 m local detail bubble (91% fewer cells than 3 km Quality mode) while
        // always_loaded island terrain, far hills, roads and sea preserve the full horizon silhouette. JapanPreferences::Apply
        // updates this dynamically if the player selects Laptop (576 m) or Quality (full 3 km) in settings.txt.
        if (!GIsEditor && !IsRunningCommandlet() && FApp::IsGame())
        {
            UWorldPartitionSubsystem::SetOverrideLoadingRange(TEXT("MainPartition"), 89600);
        }
#endif

        // An offscreen run (-RenderOffscreen: the captures, films and QA runs driven over the live bridge) has no window to
        // play in, so it never takes the mouse: no capture at launch and no lock to the hidden viewport, and the cursor stays
        // free on the whole screen while it renders. AWandererCharacter::SetMouseReleased keeps it so once the player spawns.
        if (!FParse::Param(FCommandLine::Get(), TEXT("RenderOffscreen"))) return;
        UInputSettings* Input = GetMutableDefault<UInputSettings>();
        Input->bCaptureMouseOnLaunch = false;
        Input->DefaultViewportMouseCaptureMode = EMouseCaptureMode::NoCapture;
        Input->DefaultViewportMouseLockMode = EMouseLockMode::DoNotLock;
    }

    virtual void ShutdownModule() override
    {
#if WITH_EDITOR
        FCoreUObjectDelegates::OnObjectPreSave.Remove(CookedWithoutNavigation);
#endif
    }
};

IMPLEMENT_PRIMARY_GAME_MODULE(FYorimichiModule, Yorimichi, "Yorimichi");
