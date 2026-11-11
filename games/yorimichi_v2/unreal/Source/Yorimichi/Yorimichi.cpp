#include "Yorimichi.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/InputSettings.h"
#include "HAL/IConsoleManager.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Modules/ModuleManager.h"
#include "UObject/ObjectSaveContext.h"
#include "WorldPartition/WorldPartitionSubsystem.h"

#if PLATFORM_MAC
#include <CoreFoundation/CoreFoundation.h>
#include <objc/message.h>
#include <objc/runtime.h>
#endif

class FYorimichiModule : public FDefaultGameModuleImpl
{
#if WITH_EDITOR
    FDelegateHandle CookedWithoutNavigation;
#endif
#if PLATFORM_MAC
    id MacGameActivity = nullptr;
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

#if PLATFORM_MAC
        // UE 5.8 only disables macOS App Nap for dedicated servers and cook commandlets (MacPlatformApplicationMisc.cpp).
        // Without NSActivityLatencyCritical, macOS coalesces UpdateTimeAndHandleMaxTickRate's 60 fps frame-cap usleep() to
        // ~100 ms (~10 fps) whenever a game window is unfocused, hosting a listen server in the background, or offscreen.
        if (!GIsEditor && !IsRunningCommandlet() && FApp::IsGame())
        {
            const Class ProcInfoCls = objc_getClass("NSProcessInfo");
            const SEL ProcInfoSel = sel_registerName("processInfo");
            const SEL BeginSel = sel_registerName("beginActivityWithOptions:reason:");
            const SEL RetainSel = sel_registerName("retain");
            if (ProcInfoCls && ProcInfoSel && BeginSel && RetainSel)
            {
                const id ProcInfo = ((id(*)(Class, SEL))objc_msgSend)(ProcInfoCls, ProcInfoSel);
                // NSActivityUserInitiatedAllowingIdleSystemSleep (0x00FFFFFFULL) | NSActivityLatencyCritical (0xFF00000000ULL)
                constexpr uint64 LatencyCriticalGameOptions = 0x00FFFFFFULL | 0xFF00000000ULL;
                CFStringRef Reason = CFSTR("Yorimichi V2 60Hz game loop");
                if (ProcInfo && Reason)
                {
                    const id Token = ((id(*)(id, SEL, uint64, CFStringRef))objc_msgSend)(
                        ProcInfo, BeginSel, LatencyCriticalGameOptions, Reason);
                    if (Token) MacGameActivity = ((id(*)(id, SEL))objc_msgSend)(Token, RetainSel);
                }
                if (Reason) CFRelease(Reason);
            }
        }
#endif

#if !UE_BUILD_SHIPPING
        // Default Performance mode streams a 1,344 m detail bubble (preserving cross-bay town and headland vistas in Brine Cove
        // and Hidamari while cutting streamed cells ~80% vs 3 km Quality mode). JapanPreferences::Apply updates this dynamically
        // for Laptop (640 m) or Quality (3 km) across editor -game and Development packaged builds.
        if (!GIsEditor && !IsRunningCommandlet() && FApp::IsGame())
        {
            UWorldPartitionSubsystem::SetOverrideLoadingRange(TEXT("MainPartition"), 134400);
        }
#endif

        // An offscreen run (-RenderOffscreen: the captures, films and QA runs driven over the live bridge) has no window to
        // play in, so it never takes the mouse: no capture at launch and no lock to the hidden viewport, and the cursor stays
        // free on the whole screen while it renders. AWandererCharacter::SetMouseReleased keeps it so once the player spawns.
        if (!FParse::Param(FCommandLine::Get(), TEXT("RenderOffscreen"))) return;
        if (IConsoleVariable* IdleCVar = IConsoleManager::Get().FindConsoleVariable(TEXT("t.IdleWhenNotForeground")))
        {
            IdleCVar->Set(0, ECVF_SetByCode);
        }
        UInputSettings* Input = GetMutableDefault<UInputSettings>();
        Input->bCaptureMouseOnLaunch = false;
        Input->DefaultViewportMouseCaptureMode = EMouseCaptureMode::NoCapture;
        Input->DefaultViewportMouseLockMode = EMouseLockMode::DoNotLock;
    }

    virtual void ShutdownModule() override
    {
#if PLATFORM_MAC
        if (MacGameActivity)
        {
            const Class ProcInfoCls = objc_getClass("NSProcessInfo");
            const SEL ProcInfoSel = sel_registerName("processInfo");
            const SEL EndSel = sel_registerName("endActivity:");
            const SEL ReleaseSel = sel_registerName("release");
            if (ProcInfoCls && ProcInfoSel && EndSel)
            {
                const id ProcInfo = ((id(*)(Class, SEL))objc_msgSend)(ProcInfoCls, ProcInfoSel);
                if (ProcInfo) ((void(*)(id, SEL, id))objc_msgSend)(ProcInfo, EndSel, MacGameActivity);
            }
            if (ReleaseSel) ((void(*)(id, SEL))objc_msgSend)(MacGameActivity, ReleaseSel);
            MacGameActivity = nullptr;
        }
#endif
#if WITH_EDITOR
        FCoreUObjectDelegates::OnObjectPreSave.Remove(CookedWithoutNavigation);
#endif
    }
};

IMPLEMENT_PRIMARY_GAME_MODULE(FYorimichiModule, Yorimichi, "Yorimichi");
