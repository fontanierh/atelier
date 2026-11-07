#include "JapanWorld.h"
#include "Components/SpotLightComponent.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"

// A forward-compatible replacement for the authored second directional fill.
// Opt-in only; the existing main sun and production harbor light are untouched.
static FAutoConsoleCommandWithWorldAndArgs ForwardHarborFillCommand(TEXT("japan.ForwardHarborFill"),
    TEXT("Experimental harbor fill in forward: intensity in lux at the district center, 0 disables (0..8)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        const auto* Forward=IConsoleManager::Get().FindConsoleVariable(TEXT("r.ForwardShading"));
        float Lux=0.f;
        if (!Game || Args.Num()!=1 || !LexTryParseString(Lux,*Args[0]) || !FMath::IsFinite(Lux) || Lux<0 || Lux>8 || !Forward || Forward->GetInt()!=1)
        { UE_LOG(LogTemp,Error,TEXT("FORWARD FILL requires forward renderer and intensity 0..8")); return; }
        int32 Count=0;
        for (TActorIterator<AJapanWorld> It(Game);It;++It)
        {
            USpotLightComponent* Fill=nullptr;
            TArray<USpotLightComponent*> Lights; It->GetComponents(Lights);
            for (auto* Light:Lights) if (Light->GetFName()==TEXT("ForwardHarborFill")) Fill=Light;
            if (!Fill && Lux>0)
            {
                Fill=NewObject<USpotLightComponent>(*It,TEXT("ForwardHarborFill"));
                It->AddInstanceComponent(Fill);
                Fill->SetupAttachment(It->GetRootComponent());
                Fill->SetMobility(EComponentMobility::Movable);
                // Distant broad source approximates the original 28-degree warm
                // fill over the district. Channel 1 excludes the rest of the world.
                const FRotator Direction(-28,15,0);
                Fill->SetRelativeLocation(AJapanWorld::ToUE(655,-175,4)-Direction.Vector()*70000.f);
                Fill->SetRelativeRotation(Direction);
                Fill->SetIntensityUnits(ELightUnits::Candelas);
                Fill->SetAttenuationRadius(140000.f);
                Fill->SetInnerConeAngle(35.f);
                Fill->SetOuterConeAngle(55.f);
                Fill->SetLightColor(FLinearColor(1.f,.81f,.55f),false);
                Fill->SetLightingChannels(false,true,false);
                Fill->SetCastShadows(false);
                Fill->RegisterComponent();
            }
            if (Fill)
            {
                // Inverse-square light units are meters, actor coordinates cm.
                Fill->SetIntensity(Lux*700.f*700.f);
                Fill->SetVisibility(Lux>0);
                ++Count;
            }
        }
        UE_LOG(LogTemp,Display,TEXT("FORWARD FILL nominal_lux=%.3f lights=%d"),Lux,Count);
    }));

#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "UnrealClient.h"
#include "TimerManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "SceneTexturesConfig.h"
static FAutoConsoleCommandWithWorld PreviewInfoCommand(TEXT("japan.PreviewInfo"),
    TEXT("Report the fullscreen viewport after startup; desktopnative1440 fixes its render height at native window aspect."),
    FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
    {
        if (!World) return;
        FTimerHandle Timer;
        World->GetTimerManager().SetTimer(Timer,FTimerDelegate::CreateWeakLambda(World,[World]()
        {
            if (!GEngine || !GEngine->GameViewport || !GEngine->GameViewport->Viewport) return;
            auto* Viewport=GEngine->GameViewport->Viewport;
            const auto WindowSize=Viewport->GetSizeXY();
            const double Aspect=double(WindowSize.X)/FMath::Max(1,WindowSize.Y);
            // macOS native fullscreen can replace -resx/-resy with its scaled
            // desktop dimensions. Fix the game's render size independently of
            // the OS window, preserving its aspect instead of stretching 16:9.
            if (FParse::Param(FCommandLine::Get(),TEXT("desktopnative1440")))
            {
                const uint32 Width=FMath::RoundToInt(1440*Aspect/2)*2;
                // DesktopPreviewViewportClient creates a separate scene target
                // before startup. The OS drawable keeps its own native size.
                Viewport->SetFixedViewportSize(Width,1440);
            }
            const auto Size=Viewport->GetSizeXY();
            UE_LOG(LogTemp,Display,TEXT("DESKTOP PREVIEW viewport=%dx%d fullscreen=%d window_aspect=%.6f"),Size.X,Size.Y,Viewport->IsFullscreen(),Aspect);
            if (const auto* PC=World->GetFirstPlayerController())
                UE_LOG(LogTemp,Display,TEXT("DESKTOP PREVIEW hud=%s shown=%d"),*GetNameSafe(PC->GetHUD()),PC->GetHUD()?PC->GetHUD()->bShowHUD:0);
            ENQUEUE_RENDER_COMMAND(PreviewBuffer)([](FRHICommandListImmediate&)
            {
                const auto& Config=FSceneTexturesConfig::Get();
                UE_LOG(LogTemp,Display,TEXT("DESKTOP PREVIEW scene_buffer=%dx%d"),Config.Extent.X,Config.Extent.Y);
            });
            FTimerHandle Capture;
            World->GetTimerManager().SetTimer(Capture,FTimerDelegate::CreateWeakLambda(World,[]()
            {
                FString Path;
                if (FParse::Value(FCommandLine::Get(),TEXT("previewcapture="),Path) && !Path.IsEmpty())
                    // Read the actual game buffer; a Slate/window capture on
                    // macOS reports logical desktop pixels instead.
                    FScreenshotRequest::RequestScreenshot(Path,false,false);
            }),1.f,false);
        }),3.f,false);
    }));
