#include "LeafStorm.h"
#include "AtelierData.h"
#include "JapanWorld.h"
#include "SkatePark.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

ALeafStorm::ALeafStorm()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Leaves = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Leaves"));
    Leaves->SetupAttachment(RootComponent);
    Leaves->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Leaves->SetCanEverAffectNavigation(false);
    Leaves->bAffectDistanceFieldLighting = false;
    Leaves->SetCastShadow(false);
    Leaves->SetCullDistances(9000, 11000);
}

void ALeafStorm::LoadTerrainHeightmap()
{
    TerrainHeights.Reset();
    TerrainResolution = 0;
    TerrainBounds = FBox2D(ForceInit);
    const FString BinPath = AtelierDataPath(TEXT("terrain/heightmap.bin"));
    TArray<uint8> Bytes;
    if (!FPaths::FileExists(BinPath) || !FFileHelper::LoadFileToArray(Bytes, *BinPath) || Bytes.Num() < int32(4 * sizeof(float)) || (Bytes.Num() % sizeof(float)) != 0)
        return;
    const int32 SampleCount = Bytes.Num() / sizeof(float);
    int32 N = FMath::RoundToInt(FMath::Sqrt(double(SampleCount)));
    FBox2D Bounds(FVector2D(-358400.f, -716800.f), FVector2D(358400.f, 153600.f));
    if (const TSharedPtr<FJsonObject> Meta = AtelierReadJson(AtelierDataPath(TEXT("terrain/heightmap.json"))))
    {
        if (Meta->HasField(TEXT("n"))) N = Meta->GetIntegerField(TEXT("n"));
        const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
        if (Meta->TryGetArrayField(TEXT("bounds_cm"), B) && B->Num() >= 4)
            Bounds = FBox2D(FVector2D((*B)[0]->AsNumber(), (*B)[1]->AsNumber()), FVector2D((*B)[2]->AsNumber(), (*B)[3]->AsNumber()));
        else if (Meta->HasField(TEXT("size")))
        {
            const float HalfCm = float(Meta->GetNumberField(TEXT("size")) * 50.0);
            Bounds = FBox2D(FVector2D(-HalfCm, -HalfCm), FVector2D(HalfCm, HalfCm));
        }
    }
    if (N < 2 || N > 8192 || int64(N) * int64(N) != SampleCount) return;
    TerrainHeights.SetNumUninitialized(SampleCount);
    FMemory::Memcpy(TerrainHeights.GetData(), Bytes.GetData(), Bytes.Num());
    for (float H : TerrainHeights)
        if (!FMath::IsFinite(H)) { TerrainHeights.Reset(); return; }
    TerrainResolution = N;
    TerrainBounds = Bounds;
}

bool ALeafStorm::SampleGroundHeight(const FVector& P, float& OutHeight) const
{
    if (World && World->SampleGroundHeight(P, OutHeight)) return true;
    if (TerrainResolution >= 2 && TerrainHeights.Num() == TerrainResolution * TerrainResolution && TerrainBounds.bIsValid)
    {
        const FVector2D Span = TerrainBounds.GetSize();
        if (Span.X > 0.f && Span.Y > 0.f && TerrainBounds.IsInside(FVector2D(P.X, P.Y)))
        {
            const float U = ((P.X - TerrainBounds.Min.X) / Span.X) * (TerrainResolution - 1);
            const float V = ((TerrainBounds.Max.Y - P.Y) / Span.Y) * (TerrainResolution - 1);
            const int32 I = FMath::Clamp(FMath::FloorToInt(U), 0, TerrainResolution - 2);
            const int32 J = FMath::Clamp(FMath::FloorToInt(V), 0, TerrainResolution - 2);
            const int32 K = J * TerrainResolution + I;
            const float Fx = U - I, Fy = V - J;
            OutHeight = 100.f * FMath::Lerp(
                FMath::Lerp(TerrainHeights[K], TerrainHeights[K + 1], Fx),
                FMath::Lerp(TerrainHeights[K + TerrainResolution], TerrainHeights[K + TerrainResolution + 1], Fx), Fy) + 6.f;
            return true;
        }
    }
    // Analytical region height fallback (sea = 0 cm offshore) outside the committed [-300m, +300m] heightfield.
    const float X = float(P.X), Y = float(P.Y);
    float RegionZ = 0.f;
    if (X >= -51200.f && X <= 204800.f && Y >= -716800.f && Y <= -358400.f)
    {
        // Belmonte valley & racecourse plateau (210m piazza rising northward to 240.2m).
        RegionZ = FMath::Lerp(21000.f, 24020.f, (1.f - FMath::SmoothStep(-485000.f, -450000.f, Y)));
    }
    else if (X >= -51200.f && X <= 153600.f && Y > -358400.f && Y <= -89600.f)
    {
        if (X < 25600.f && Y > -179200.f)
        {
            // Super Ultra Mega Park & northern approach.
            RegionZ = FMath::Lerp(2200.f, 14000.f, (1.f - FMath::SmoothStep(-125000.f, -38400.f, Y)));
        }
        else
        {
            // Volcano flanks & Crater Park caldera (centre (85000, -240000) at 680m).
            const float DistToCaldera = FVector2D::Distance(FVector2D(X, Y), FVector2D(85000.f, -240000.f));
            RegionZ = FMath::Lerp(68000.f, 6000.f, FMath::SmoothStep(45000.f, 150000.f, DistToCaldera));
        }
    }
    else if (X >= 25600.f && X <= 153600.f && Y > -89600.f && Y <= 38400.f)
    {
        // Hidamari harbour, station yard, hippodrome & south volcano foot.
        const float CoastFade = 1.f - FMath::SmoothStep(14000.f, 28000.f, Y);
        const float EastRise = FMath::Lerp(420.f, 2200.f, FMath::SmoothStep(40000.f, 125000.f, X));
        const float NorthRise = FMath::Lerp(0.f, 4200.f, (1.f - FMath::SmoothStep(-75000.f, -30000.f, Y)));
        RegionZ = (EastRise + NorthRise) * CoastFade;
    }
    else if (X >= -252600.f && X <= -70700.f && Y >= -57300.f && Y <= 104400.f)
    {
        // Brinecove pirate port quay around (-150000, 4500) at ~5.9m tapering to sea level.
        const float DistQuay = FVector2D::Distance(FVector2D(X, Y), FVector2D(-150000.f, 4500.f));
        RegionZ = FMath::Lerp(586.f, 0.f, FMath::SmoothStep(25000.f, 95000.f, DistQuay));
    }
    else if (X >= -51200.f && X <= 25600.f && Y > -89600.f && Y <= 102400.f)
    {
        // West woods, southwest terrace & southwest island; open sea beyond shoreline stays at 0.
        if (Y <= 12800.f)
            RegionZ = FMath::Lerp(900.f, 0.f, FMath::SmoothStep(2000.f, 14000.f, Y));
        else
        {
            const float DistIsle = FVector2D::Distance(FVector2D(X, Y), FVector2D(-15000.f, 53000.f));
            RegionZ = FMath::Lerp(650.f, 0.f, FMath::SmoothStep(8000.f, 18000.f, DistIsle));
        }
    }
    if (bHasCachedPlayerFootZ && CachedPlayerFootZ > -50.f && FMath::Abs(CachedPlayerFootZ - RegionZ) < 6000.f)
    {
        const float DistPlayer = FVector2D::Distance(FVector2D(X, Y), FVector2D(CachedPlayerPos.X, CachedPlayerPos.Y));
        const float LocalWeight = 1.f - FMath::SmoothStep(1200.f, 4800.f, DistPlayer);
        RegionZ = FMath::Lerp(RegionZ, CachedPlayerFootZ + 6.f, LocalWeight);
    }
    OutHeight = RegionZ;
    return true;
}

void ALeafStorm::BeginPlay()
{
    Super::BeginPlay();
    TActorIterator<AJapanWorld> It(GetWorld()); if (It) World = *It;
    LoadTerrainHeightmap();
    if (UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Japan/Assets/Leaf.Leaf"))) Leaves->SetStaticMesh(M);
    TActorIterator<ASkatePark> Park(GetWorld()); if (Park) SkatePark=*Park;
    L.SetNum(Count); Xf.SetNum(Count);
    const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
    const FVector Player = P ? P->GetActorLocation() : FVector::ZeroVector;
    if (const ACharacter* Ch = Cast<ACharacter>(P))
        if (Ch->GetCharacterMovement() && Ch->GetCharacterMovement()->IsMovingOnGround())
        {
            CachedPlayerPos = Player;
            CachedPlayerFootZ = float(Player.Z) - Ch->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
            bHasCachedPlayerFootZ = true;
        }
    for (int32 i = 0; i < Count; i++) { Respawn(L[i], Player, true); Xf[i] = FTransform(L[i].R, L[i].P, FVector(L[i].Size)); }
    Leaves->AddInstances(Xf, false, true, false);
    Leaves->SetVisibility(!SkatePark.IsValid() || !SkatePark->ContainsPlanar(Player));
}

float ALeafStorm::GroundZ(const FVector& P) const
{
    float Height = 0.f;
    SampleGroundHeight(P, Height);
    return Height;
}

void ALeafStorm::Respawn(FStormLeaf& Leaf, const FVector& Player, bool bInitial)
{
    const FVector W = World ? World->WindDir : FVector(0, -1, 0);
    const FVector Perp(-W.Y, W.X, 0);
    // upwind of the player (or all around at start), between 1.5 and 14 m up: they read as blown off the trees
    const float Along = bInitial ? FMath::FRandRange(-3500.f, 3500.f) : FMath::FRandRange(-4500.f, -1200.f);
    FVector P = Player + W * Along + Perp * FMath::FRandRange(-3500.f, 3500.f);
    const float G = GroundZ(P);
    P.Z = G + FMath::FRandRange(150.f, 1400.f);
    Leaf.P = P; Leaf.V = W * 200.f; Leaf.Phase = FMath::FRandRange(0.f, 100.f); Leaf.RestT = -1.f;
    Leaf.R = FRotator(FMath::FRandRange(0.f, 360.f), FMath::FRandRange(0.f, 360.f), FMath::FRandRange(0.f, 360.f));
    Leaf.Spin = FVector(FMath::FRandRange(-260.f, 260.f), FMath::FRandRange(-320.f, 320.f), FMath::FRandRange(-200.f, 200.f));
    Leaf.Size = FMath::FRandRange(0.8f, 1.3f); Leaf.Tick = FMath::RandRange(0, 7);
}

void ALeafStorm::Tick(float Dt)
{
    Super::Tick(Dt);
    if (!Leaves->GetStaticMesh()) return;
    Frame++;
    const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
    if (!P) return;
    const FVector Player = P->GetActorLocation(); const FVector PlayerVel = P->GetVelocity();
    if (const ACharacter* Ch = Cast<ACharacter>(P))
        if (Ch->GetCharacterMovement() && Ch->GetCharacterMovement()->IsMovingOnGround())
        {
            CachedPlayerPos = Player;
            CachedPlayerFootZ = float(Player.Z) - Ch->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
            bHasCachedPlayerFootZ = true;
        }
    const bool bOnPier = SkatePark.IsValid() && SkatePark->ContainsPlanar(Player);
    Leaves->SetVisibility(!bOnPier);
    if (bOnPier) return; // No drifting leaves or simulation work while skating the pier.
    const APlayerController* PC = GetWorld()->GetFirstPlayerController();
    const FVector ViewLoc = PC && PC->PlayerCameraManager ? PC->PlayerCameraManager->GetCameraLocation() : Player;
    DistantUpdateAccum += Dt;
    const bool bUpdateDistant = DistantUpdateAccum >= (1.f / 30.f);
    if (bUpdateDistant) DistantUpdateAccum = FMath::Fmod(DistantUpdateAccum, 1.f / 30.f);
    bool bAnyNearUpdated = false;
    constexpr double NearLeafDistSq = 3500. * 3500.;
    const float T = GetWorld()->GetTimeSeconds();
    Dt = FMath::Min(Dt, 0.05f);
    for (int32 i = 0; i < Count; i++)
    {
        FStormLeaf& f = L[i];
        bool bRespawned = false;
        const float Gust = World ? World->WindStrength(f.P, T) : 1.f;
        const FVector Wind = World ? World->WindDir * World->WindSpeed * Gust : FVector::ZeroVector;
        if (f.RestT >= 0.f)
        {
            // lying on the ground: lift off on a strong gust or when the player brushes past
            f.RestT -= Dt;
            const float d = FVector::Dist2D(f.P, Player);
            if (Gust > 1.35f || d < 140.f) { f.RestT = -1.f; f.V = Wind * 0.8f + FVector(0, 0, FMath::FRandRange(120.f, 260.f)); f.Spin = FVector(FMath::FRandRange(-260.f, 260.f), FMath::FRandRange(-320.f, 320.f), 0); }
            else if (f.RestT <= 0.f) { Respawn(f, Player, false); bRespawned = true; }
        }
        else
        {
            const FVector Flutter(FMath::Sin(T * 2.3f + f.Phase) * 110.f, FMath::Cos(T * 1.7f + f.Phase * 2.f) * 110.f, FMath::Sin(T * 3.4f + f.Phase) * 70.f);
            FVector Target = Wind + Flutter; Target.Z += -95.f;                      // slow, fluttering fall
            f.V += (Target - f.V) * FMath::Min(1.f, 2.2f * Dt);
            const FVector D = f.P - Player; const float d = D.Size();
            if (d < 260.f) { f.V += D.GetSafeNormal() * (260.f - d) * 5.0f * Dt + PlayerVel * 0.6f * (1.f - d / 260.f) * FMath::Min(1.f, 6.f * Dt); }
            f.P += f.V * Dt;
            f.R += FRotator(f.Spin.X * Dt, f.Spin.Z * Dt, f.Spin.Y * Dt);
            if (((Frame + f.Tick) & 7) == 0)
            {
                const float G = GroundZ(f.P);
                if (f.P.Z < G + 6.f) { f.P.Z = G + 3.f; f.RestT = FMath::FRandRange(2.5f, 7.f); f.R = FRotator(0, f.R.Yaw, 0); f.V = FVector::ZeroVector; }
                if (FVector::Dist2D(f.P, Player) > 5600.f || f.P.Z < -60.f) { Respawn(f, Player, false); bRespawned = true; }
            }
        }
        const bool bNear = FVector::DistSquared(f.P, ViewLoc) <= NearLeafDistSq;
        if (!bUpdateDistant && !bNear && !bRespawned) continue;
        // The covered arcade admits a few windblown leaves, not a forest storm.
        // Fade at all shelter boundaries so crossing its entrance never pops.
        const float ArcadeInterior=FMath::Min(FMath::Min((f.P.X-60600.f)/600.f,(71000.f-f.P.X)/600.f),
            FMath::Min((f.P.Y+8450.f)/250.f,(-6550.f-f.P.Y)/250.f));
        const float PlazaInterior=FMath::Min(FMath::Min((f.P.X-66000.f)/1000.f,(80200.f-f.P.X)/1000.f),
            FMath::Min((f.P.Y+21800.f)/1000.f,(-12200.f-f.P.Y)/1000.f));
        const float Shelter=FMath::Max(FMath::Clamp(ArcadeInterior,0.f,1.f)*FMath::Clamp((2300.f-f.P.Z)/200.f,0.f,1.f),
            FMath::Clamp(PlazaInterior,0.f,1.f)*.85f);
        const float ShelterScale=SkatePark.IsValid() && SkatePark->ContainsPlanar(f.P,150.f) ? 0.f : FMath::Lerp(1.f,i%5==0?.85f:0.f,Shelter);
        Xf[i] = FTransform(f.R, f.P, FVector(f.Size*ShelterScale));
        if (!bUpdateDistant)
        {
            Leaves->UpdateInstanceTransform(i, Xf[i], true, false, true);
            bAnyNearUpdated = true;
        }
    }
    if (bUpdateDistant) Leaves->BatchUpdateInstancesTransforms(0, Xf, true, true, true);
    else if (bAnyNearUpdated) Leaves->MarkRenderStateDirty();
}
