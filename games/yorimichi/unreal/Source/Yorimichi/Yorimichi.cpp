#include "Yorimichi.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/InputSettings.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"
#include "UObject/ObjectSaveContext.h"

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
