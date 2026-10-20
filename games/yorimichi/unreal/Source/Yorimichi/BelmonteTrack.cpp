#include "BelmonteTrack.h"
#include "FoliageSystem.h"
#include "AtelierData.h"
#include "Components/BoxComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/PostProcessComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "Misc/Paths.h"

static FVector TrackVector(const TArray<TSharedPtr<FJsonValue>>& A, int32 First = 0)
{
    if (A.Num() < First + 3) return FVector::ZeroVector;
    return FVector(A[First]->AsNumber(), A[First + 1]->AsNumber(), A[First + 2]->AsNumber());
}

ABelmonteTrack::ABelmonteTrack()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickInterval = 0.f;
    bReplicates = false;
    Tags.Add(TEXT("NoClimb"));   // rails, linings and portals are not climbing holds
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

ABelmonteTrack* ABelmonteTrack::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !FPaths::FileExists(Path)) return nullptr;
    auto* Track = World->SpawnActor<ABelmonteTrack>();
    if (Track && !Track->Initialize(Path)) { Track->Destroy(); return nullptr; }
    return Track;
}

static void Common(UStaticMeshComponent* C, float Cull, bool bCollide, bool bShadow)
{
    C->SetMobility(EComponentMobility::Static);
    C->SetCollisionEnabled(bCollide ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    if (bCollide) C->SetCollisionProfileName(TEXT("BlockAll"));
    C->SetGenerateOverlapEvents(false);
    C->SetCanEverAffectNavigation(bCollide);
    C->SetAffectDistanceFieldLighting(false);
    C->bAffectDynamicIndirectLighting = false;
    C->SetCastShadow(bShadow);
    C->SetCachedMaxDrawDistance(Cull);
    C->LDMaxDrawDistance = Cull;
    C->PrimaryComponentTick.bCanEverTick = false;
}

static FTransform BoxFrame(const TSharedPtr<FJsonObject>& B, FVector& Half)
{
    Half = TrackVector(B->GetArrayField(TEXT("half")));
    return FTransform(FRotator(0., B->GetNumberField(TEXT("yaw")), 0.), TrackVector(B->GetArrayField(TEXT("centre"))));
}

bool ABelmonteTrack::Initialize(const FString& Path)
{
    const TSharedPtr<FJsonObject> Root = AtelierReadJson(Path);
    if (!Root.IsValid()) { UE_LOG(LogTemp, Error, TEXT("BELMONTE TRACK cannot read %s"), *Path); return false; }
    const TSharedPtr<FJsonObject> Cull = Root->GetObjectField(TEXT("cull_cm"));
    TMap<FString, UStaticMesh*> Meshes;
    int32 Missing = 0, Pieces = 0, Instances = 0;
    auto Load = [&](const FString& Asset) -> UStaticMesh*
    {
        UStaticMesh*& Mesh = Meshes.FindOrAdd(Asset);
        if (!Mesh) Mesh = LoadObject<UStaticMesh>(nullptr, *Asset);
        if (!Mesh) { ++Missing; UE_LOG(LogTemp, Warning, TEXT("BELMONTE TRACK missing %s"), *Asset); }
        return Mesh;
    };
    for (const auto& Value : Root->GetArrayField(TEXT("pieces")))
    {
        const auto P = Value->AsObject();
        UStaticMesh* Mesh = Load(P->GetStringField(TEXT("mesh")));
        if (!Mesh) continue;
        auto* C = NewObject<UStaticMeshComponent>(this, *P->GetStringField(TEXT("name")));
        C->SetupAttachment(RootComponent);
        C->SetStaticMesh(Mesh);
        const FString Kind = P->GetStringField(TEXT("kind"));
        // The linings stay inside the hills (no sun shadow worth casting); the viaduct and banks do cast.
        Common(C, float(Cull->GetNumberField(TEXT("piece"))), P->GetIntegerField(TEXT("collision")) >= 0, Kind != TEXT("lining") && Kind != TEXT("chunk") && Kind != TEXT("loop"));
        C->SetWorldLocation(TrackVector(P->GetArrayField(TEXT("at"))));
        C->RegisterComponent();
        Parts.Add(C); ++Pieces;
    }
    for (const auto& Value : Root->GetArrayField(TEXT("instances")))
    {
        const auto G = Value->AsObject();
        UStaticMesh* Mesh = Load(G->GetStringField(TEXT("mesh")));
        if (!Mesh) continue;
        const FString Name = FString::Printf(TEXT("%s_%s_%s"), *G->GetStringField(TEXT("kind")), *Mesh->GetName(), *G->GetStringField(TEXT("key")));
        UInstancedStaticMeshComponent* C = G->GetBoolField(TEXT("hierarchical"))
            ? UYorimichiFoliageSubsystem::NewInstances(this, *Name) : NewObject<UInstancedStaticMeshComponent>(this, *Name);
        C->SetupAttachment(RootComponent);
        C->SetStaticMesh(Mesh);
        const float Distance = float(G->GetNumberField(TEXT("cull_cm")));
        Common(C, Distance, G->GetBoolField(TEXT("collision")), G->GetBoolField(TEXT("shadow")));
        C->InstanceEndCullDistance = int32(Distance);
        for (const auto& Row : G->GetArrayField(TEXT("instances")))
        {
            const auto& A = Row->AsArray();
            if (A.Num() < 5) continue;
            C->AddInstance(FTransform(FRotator(0., A[3]->AsNumber(), 0.), TrackVector(A), FVector(1., A[4]->AsNumber(), 1.)), true);
            ++Instances;
        }
        C->RegisterComponent();
        Parts.Add(C);
    }
    // Tunnels: their zones (lining volumes and the portals' load boxes), their lights and their exposure boxes.
    const TSharedPtr<FJsonObject> Light = Root->GetObjectField(TEXT("light"));
    const TSharedPtr<FJsonObject> Exposure = Root->GetObjectField(TEXT("exposure"));
    LightRange = Root->GetNumberField(TEXT("light_range_cm"));
    double Bias = 0., Indirect = 1.;
    Exposure->TryGetNumberField(TEXT("bias"), Bias);
    Exposure->TryGetNumberField(TEXT("indirect"), Indirect);
    // The lamps make up for the darker exposure inside, so their pools read as the Train Builder lit them.
    const double LampGain = FMath::Pow(2., -FMath::Min(Bias, 0.));
    int32 Looked = 0;
    for (const auto& Value : Root->GetArrayField(TEXT("tunnels")))
    {
        const auto T = Value->AsObject();
        FTunnel& Tunnel = Tunnels.AddDefaulted_GetRef();
        Tunnel.Name = T->GetStringField(TEXT("name"));
        for (const TCHAR* Field : {TEXT("volumes"), TEXT("load_boxes")})
            for (const auto& BoxValue : T->GetArrayField(Field))
            {
                FTunnelBox& Zone = Tunnel.Zone.AddDefaulted_GetRef();
                Zone.Frame = BoxFrame(BoxValue->AsObject(), Zone.Half);
            }
        for (const auto& BoxValue : T->GetArrayField(TEXT("volumes")))
        {
            FVector Half;
            const FTransform Frame = BoxFrame(BoxValue->AsObject(), Half);
            auto* Shape = NewObject<UBoxComponent>(this);
            Shape->SetupAttachment(RootComponent);
            Shape->SetMobility(EComponentMobility::Static);
            Shape->SetWorldTransform(Frame);
            Shape->SetBoxExtent(Half, false);
            // The post-process box measures the camera's distance to its parent shape through a collision query:
            // the shape must answer queries (it blocks nothing).
            Shape->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
            Shape->SetCollisionResponseToAllChannels(ECR_Ignore);
            Shape->SetGenerateOverlapEvents(false);
            Shape->SetCanEverAffectNavigation(false);
            Shape->RegisterComponent();
            auto* Look = NewObject<UPostProcessComponent>(this);
            Look->SetupAttachment(Shape);
            Look->bUnbound = false; Look->BlendRadius = 600.f; Look->Priority = 2.f;
            Look->Settings.bOverride_AutoExposureMinBrightness = true;
            Look->Settings.AutoExposureMinBrightness = float(Exposure->GetNumberField(TEXT("min_ev")));
            Look->Settings.bOverride_AutoExposureMaxBrightness = true;
            Look->Settings.AutoExposureMaxBrightness = float(Exposure->GetNumberField(TEXT("max_ev")));
            Look->Settings.bOverride_AutoExposureBias = true;
            Look->Settings.AutoExposureBias = float(Bias);
            Look->Settings.bOverride_IndirectLightingIntensity = true;
            Look->Settings.IndirectLightingIntensity = float(Indirect);
            Look->RegisterComponent();
            Parts.Add(Shape); Looks.Add(Look); ++Looked;
        }
        for (const auto& PointValue : T->GetArrayField(TEXT("lights")))
        {
            auto* Lamp = NewObject<UPointLightComponent>(this);
            Lamp->SetupAttachment(RootComponent);
            Lamp->SetMobility(EComponentMobility::Movable);
            Lamp->SetWorldLocation(TrackVector(PointValue->AsArray()));
            Lamp->SetIntensityUnits(ELightUnits::Candelas);
            Lamp->SetIntensity(float(Light->GetNumberField(TEXT("candela")) * LampGain));
            Lamp->bUseTemperature = true;
            Lamp->SetTemperature(float(Light->GetNumberField(TEXT("kelvin"))));
            Lamp->SetAttenuationRadius(float(Light->GetNumberField(TEXT("radius_cm"))));
            Lamp->SetSourceRadius(float(Light->GetNumberField(TEXT("source_radius_cm"))));
            Lamp->SetCastShadows(Light->GetBoolField(TEXT("shadows")));
            Lamp->SetAffectTranslucentLighting(false);
            Lamp->SetVisibility(false);
            Lamp->RegisterComponent();
            Tunnel.Lights.Add(Lamp); AllLights.Add(Lamp);
        }
    }
    UE_LOG(LogTemp, Display, TEXT("BELMONTE TRACK ready pieces=%d groups=%d instances=%d tunnels=%d lights=%d exposure_boxes=%d missing=%d"),
        Pieces, Parts.Num() - Pieces - Looked, Instances, Tunnels.Num(), AllLights.Num(), Looked, Missing);
    return Pieces > 0;
}

void ABelmonteTrack::UpdateLights()
{
    const APlayerController* PC = GetWorld()->GetFirstPlayerController();
    if (!PC || !PC->PlayerCameraManager) return;
    const FVector View = PC->PlayerCameraManager->GetCameraLocation();
    FString Now;
    int32 On = 0;
    for (FTunnel& Tunnel : Tunnels)
    {
        bool bIn = false;
        for (const FTunnelBox& Zone : Tunnel.Zone)
            if (FBox(-Zone.Half, Zone.Half).IsInside(Zone.Frame.InverseTransformPosition(View))) { bIn = true; break; }
        if (bIn) Now = Tunnel.Name;
        for (UPointLightComponent* Lamp : Tunnel.Lights)
        {
            const bool bOn = bIn && FVector::DistSquared(Lamp->GetComponentLocation(), View) < FMath::Square(LightRange);
            if (Lamp->IsVisible() != bOn) Lamp->SetVisibility(bOn);
            On += bOn;
        }
    }
    if (Now != Inside || On != LightsOn)
    {
        UE_LOG(LogTemp, Display, TEXT("BELMONTE TRACK tunnel=%s lights_on=%d"), Now.IsEmpty() ? TEXT("-") : *Now, On);
        Inside = Now; LightsOn = On;
    }
}

void ABelmonteTrack::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    // A few times a second is enough: the lights reach 250 m ahead, a train covers 5 m in that time.
    if ((NextUpdate -= DeltaSeconds) > 0.f) return;
    NextUpdate = .2f;
    UpdateLights();
}
