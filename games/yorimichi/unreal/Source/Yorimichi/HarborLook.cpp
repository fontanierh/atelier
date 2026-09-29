#include "HarborLook.h"
#include "JapanWorld.h"
#include "Components/BoxComponent.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/PostProcessComponent.h"
#include "Engine/DirectionalLight.h"
#include "EngineUtils.h"
#include "HAL/IConsoleManager.h"
#include "Camera/PlayerCameraManager.h"
#include "Kismet/GameplayStatics.h"

static TAutoConsoleVariable<int32> HarborFillAuto(TEXT("japan.HarborFillAuto"),0,
    TEXT("Harbor fill shadows: 0 original, 1 skip unreachable cascades, 2 experimental tiled receiver visibility, -1 manual."),ECVF_Cheat);

// Diagnostic controls for pricing the harbor-only fill outside the harbor.
// Neither is called during ordinary play; the authored light stays enabled.
static void SetHarborFill(const TArray<FString>& Args, UWorld* World, bool bShadowsOnly)
{
    if (!World || Args.Num()!=1) return;
    HarborFillAuto->Set(-1,ECVF_SetByConsole);
    const bool bEnabled=FCString::Atoi(*Args[0])!=0;
    int32 Changed=0;
    for (TActorIterator<AJapanWorld> It(World); It; ++It)
    {
        TArray<UDirectionalLightComponent*> Lights;
        It->GetComponents(Lights);
        for (auto* Light:Lights)
            if (Light->GetFName()==TEXT("HarborFill"))
            {
                if (bShadowsOnly) Light->SetCastShadows(bEnabled);
                else Light->SetVisibility(bEnabled);
                ++Changed;
            }
    }
    UE_LOG(LogTemp,Display,TEXT("DIAGNOSTIC harbor fill %s=%d, lights=%d"),bShadowsOnly?TEXT("shadows"):TEXT("visible"),bEnabled,Changed);
}
static FAutoConsoleCommandWithWorldAndArgs HarborFillCommand(TEXT("japan.HarborFill"),
    TEXT("Diagnostic: 0/1 disables/enables the harbor-only directional fill."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World){SetHarborFill(Args,World,false);}));
static FAutoConsoleCommandWithWorldAndArgs HarborFillShadowCommand(TEXT("japan.HarborFillShadows"),
    TEXT("Diagnostic: 0/1 disables/enables shadows on the harbor-only fill."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* World){SetHarborFill(Args,World,true);}));

void UpdateHarborLook(AJapanWorld* World)
{
    const int32 Mode=HarborFillAuto.GetValueOnGameThread();
    if (Mode<0) return;
    auto* Key=World->FindComponentByClass<UDirectionalLightComponent>();
    if (!Key || Key->GetFName()!=TEXT("HarborFill")) return;
    auto* Camera=UGameplayStatics::GetPlayerCameraManager(World,0);
    bool Shadows=true;
    static const auto* VirtualShadows=IConsoleManager::Get().FindConsoleVariable(TEXT("r.Shadow.Virtual.Enable"));
    static const auto* RayTracing=IConsoleManager::Get().FindConsoleVariable(TEXT("r.RayTracing"));
    static const auto* DistanceFields=IConsoleManager::Get().FindConsoleVariable(TEXT("r.DistanceFieldShadowing"));
    const auto Enabled=[](const IConsoleVariable* V){ return V && V->GetInt()>0; };
    // This bound proves absence of CSM receivers only. Other shadow methods can
    // reach farther, so retain their original behavior if the player enables them.
    const bool OnlyCascades=!Enabled(VirtualShadows) &&
        !Enabled(RayTracing) && Key->FarShadowCascadeCount==0 &&
        !(Key->bUseRayTracedDistanceFieldShadows && Enabled(DistanceFields));
    if (Mode>=1 && Camera && OnlyCascades)
    {
        // CSMs are camera-centred. They cannot affect a channel-1 receiver beyond
        // their maximum range. Keep a 100 m safety margin for the cascade fade,
        // bounds changes and rapid camera movement; never gate the actual fill.
        // Do not use LastRenderTime: the huge sea plane is often counted visible
        // behind land. Its world bounds still give a conservative distance test.
        static const auto* DistanceScale=IConsoleManager::Get().FindConsoleVariable(TEXT("r.Shadow.DistanceScale"));
        const float Scale=DistanceScale?FMath::Max(1.f,DistanceScale->GetFloat()):2.f;
        const auto& View=Camera->GetCameraCacheView();
        const float TanH=FMath::Tan(FMath::DegreesToRadians(FMath::Clamp(View.FOV,1.f,179.f)*.5f));
        const float TanV=TanH/FMath::Max(.1f,View.AspectRatio);
        // Cascade distance is view depth, not radial distance. Include the far
        // frustum corners and player-adjustable shadow scale / field of view.
        const float Range=Key->DynamicShadowDistanceMovableLight*Scale*FMath::Sqrt(1.f+TanH*TanH+TanV*TanV)+10000.f;
        Shadows=false;
        for (auto* Group:World->Groups)
            if (Group && Group->LightingChannels.bChannel1 &&
                Group->Bounds.GetBox().ComputeSquaredDistanceToPoint(Camera->GetCameraLocation())<=FMath::Square(Range))
            { Shadows=true; break; }
    }
    const bool Visible=Mode!=2 || ExperimentalHarborFillVisible(World);
    if (Key->IsVisible()!=Visible)
    {
        Key->SetVisibility(Visible);
        UE_LOG(LogTemp,Display,TEXT("HARBOR tiled visibility fill=%d"),Visible);
    }

    if (bool(Key->CastShadows)!=Shadows)
    {
        Key->SetCastShadows(Shadows);
        UE_LOG(LogTemp,Display,TEXT("HARBOR receiver range shadows=%d"),Shadows);
    }
}

void InitializeGardenBridgeLook(AJapanWorld* World)
{
    UBoxComponent* Bounds = NewObject<UBoxComponent>(World, TEXT("GardenBridgeLookBounds"));
    Bounds->SetupAttachment(World->GetRootComponent());
    Bounds->SetRelativeLocation(AJapanWorld::ToUE(1030, 284, 38));
    Bounds->SetBoxExtent(FVector(8000, 6000, 3000));
    Bounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Bounds->SetCollisionResponseToAllChannels(ECR_Ignore);
    Bounds->SetGenerateOverlapEvents(false);
    Bounds->SetCanEverAffectNavigation(false);
    Bounds->RegisterComponent();

    UPostProcessComponent* Look = NewObject<UPostProcessComponent>(World, TEXT("GardenBridgeLook"));
    Look->SetupAttachment(Bounds);
    Look->bUnbound = false;
    Look->BlendRadius = 1000;
    Look->Priority = 3;
    // UE 5.8's short-range Lumen AO projects the slender timber posts into
    // black stripes on masonry below. Disable only this pass around the pond;
    // retain irradiance GI, mesh distance fields, direct shadows and regular AO.
    Look->Settings.bOverride_LumenAmbientOcclusionIntensity = true;
    Look->Settings.LumenAmbientOcclusionIntensity = 0;
    Look->RegisterComponent();
    float Distance = 0;
    const bool bIncludesPier = Look->EncompassesPoint(AJapanWorld::ToUE(1004, 277, 30.2), 0, &Distance);
    const bool bIncludesStation = Look->EncompassesPoint(AJapanWorld::ToUE(1185, 251, 33), 0, &Distance);
    ensureMsgf(bIncludesPier && !bIncludesStation, TEXT("Garden bridge lighting must stay bounded to the pond"));
    UE_LOG(LogTemp, Display, TEXT("Garden bridge lighting bounds: pier=%d station=%d"), bIncludesPier, bIncludesStation);
}

void InitializeHarborLook(AJapanWorld* World)
{
    // The map sun owns forward/translucent/water lighting. The harbor's
    // channel-specific fill must not compete with it at the default priority.
    // Apply at runtime as well so existing generated maps receive the fix.
    for (TActorIterator<ADirectionalLight> It(World->GetWorld()); It; ++It)
        It->GetComponentByClass<UDirectionalLightComponent>()->SetForwardShadingPriority(1);
    // A warm, lower key supplements the shared sun on harbor channel 1.
    // Harbor meshes retain channel 0 so players and nearby objects cast shadows.
    UDirectionalLightComponent* Key = NewObject<UDirectionalLightComponent>(World,TEXT("HarborFill"));
    Key->SetupAttachment(World->GetRootComponent());
    Key->SetMobility(EComponentMobility::Movable);
    Key->SetRelativeRotation(FRotator(-28, 15, 0));
    Key->SetIntensity(6.0f);
    Key->SetLightColor(FLinearColor(1.0, .81, .55), false);
    Key->SetLightingChannels(false, true, false);
    Key->SetForwardShadingPriority(0);
    Key->DynamicShadowDistanceMovableLight = 14000;
    Key->DynamicShadowCascades = 2;
    Key->LightSourceAngle = 3;
    Key->RegisterComponent();

    UBoxComponent* Bounds = NewObject<UBoxComponent>(World);
    Bounds->SetupAttachment(World->GetRootComponent());
    Bounds->SetRelativeLocation(AJapanWorld::ToUE(655, -175, 18));
    Bounds->SetBoxExtent(FVector(26000, 8500, 2600));
    // UE 5.8 requires a valid query shape for bounded post-process distance.
    // Ignore every channel so this volume cannot block players or audit traces.
    Bounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Bounds->SetCollisionResponseToAllChannels(ECR_Ignore);
    Bounds->SetGenerateOverlapEvents(false);
    Bounds->SetCanEverAffectNavigation(false);
    Bounds->RegisterComponent();

    UPostProcessComponent* Look = NewObject<UPostProcessComponent>(World);
    Look->SetupAttachment(Bounds);
    Look->bUnbound = false;
    Look->BlendRadius = 1200;
    Look->Priority = 2;
    // Screen-space reflections give the moored hulls and piles a water contact.
    // They fade for off-screen objects; this is intentionally not a planar pass.
    Look->Settings.bOverride_ReflectionMethod = true;
    Look->Settings.ReflectionMethod = EReflectionMethod::ScreenSpace;
    Look->Settings.bOverride_ScreenSpaceReflectionIntensity = true;
    Look->Settings.ScreenSpaceReflectionIntensity = 100;
    Look->Settings.bOverride_ScreenSpaceReflectionQuality = true;
    Look->Settings.ScreenSpaceReflectionQuality = 50;
    Look->Settings.bOverride_ScreenSpaceReflectionMaxRoughness = true;
    Look->Settings.ScreenSpaceReflectionMaxRoughness = .65;
    Look->Settings.bOverride_SceneColorTint = true;
    Look->Settings.SceneColorTint = FLinearColor(1.10, .99, .80);
    Look->Settings.bOverride_ColorContrast = true;
    Look->Settings.ColorContrast = FVector4(1.18, 1.18, 1.18, 1);
    Look->Settings.bOverride_IndirectLightingIntensity = true;
    Look->Settings.IndirectLightingIntensity = 1.0;
    Look->Settings.bOverride_ColorGain = true;
    Look->Settings.ColorGain = FVector4(.78, .78, .78, 1);
    Look->Settings.bOverride_AmbientOcclusionIntensity = true;
    Look->Settings.AmbientOcclusionIntensity = .85;
    Look->RegisterComponent();
    float Distance = 0;
    const bool bInside = Look->EncompassesPoint(AJapanWorld::ToUE(620, -116, 5), 0, &Distance);
    UE_LOG(LogTemp, Display, TEXT("Harbor look reference point: inside=%d distance=%.1f"), bInside, Distance);
}
