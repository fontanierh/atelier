#include "LeafStorm.h"
#include "JapanWorld.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"

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

void ALeafStorm::BeginPlay()
{
    Super::BeginPlay();
    TActorIterator<AJapanWorld> It(GetWorld()); if (It) World = *It;
    if (UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Japan/Assets/Leaf.Leaf"))) Leaves->SetStaticMesh(M);
    L.SetNum(Count); Xf.SetNum(Count);
    const APawn* P = UGameplayStatics::GetPlayerPawn(this, 0);
    const FVector Player = P ? P->GetActorLocation() : FVector::ZeroVector;
    for (int32 i = 0; i < Count; i++) { Respawn(L[i], Player, true); Xf[i] = FTransform(L[i].R, L[i].P, FVector(L[i].Size)); }
    Leaves->AddInstances(Xf, false, true, false);
}

float ALeafStorm::GroundZ(const FVector& P) const
{
    float Height;
    if (World && World->SampleGroundHeight(P, Height)) return Height;
    FHitResult H; FCollisionQueryParams Q(SCENE_QUERY_STAT(LeafGround), false);
    if (World) Q.AddIgnoredActor(World);
    if (GetWorld()->LineTraceSingleByChannel(H, P + FVector(0, 0, 4000.f), P - FVector(0, 0, 4000.f), ECC_Visibility, Q)) return H.Location.Z;
    return -1000.f;
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
    const float T = GetWorld()->GetTimeSeconds();
    Dt = FMath::Min(Dt, 0.05f);
    for (int32 i = 0; i < Count; i++)
    {
        FStormLeaf& f = L[i];
        const float Gust = World ? World->WindStrength(f.P, T) : 1.f;
        const FVector Wind = World ? World->WindDir * World->WindSpeed * Gust : FVector::ZeroVector;
        if (f.RestT >= 0.f)
        {
            // lying on the ground: lift off on a strong gust or when the player brushes past
            f.RestT -= Dt;
            const float d = FVector::Dist2D(f.P, Player);
            if (Gust > 1.35f || d < 140.f) { f.RestT = -1.f; f.V = Wind * 0.8f + FVector(0, 0, FMath::FRandRange(120.f, 260.f)); f.Spin = FVector(FMath::FRandRange(-260.f, 260.f), FMath::FRandRange(-320.f, 320.f), 0); }
            else if (f.RestT <= 0.f) Respawn(f, Player, false);
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
                if (FVector::Dist2D(f.P, Player) > 5600.f || f.P.Z < -60.f) Respawn(f, Player, false);
            }
        }
        // The covered arcade admits a few windblown leaves, not a forest storm.
        // Fade at all shelter boundaries so crossing its entrance never pops.
        const float ArcadeInterior=FMath::Min(FMath::Min((f.P.X-60600.f)/600.f,(71000.f-f.P.X)/600.f),
            FMath::Min((f.P.Y+8450.f)/250.f,(-6550.f-f.P.Y)/250.f));
        const float PlazaInterior=FMath::Min(FMath::Min((f.P.X-66000.f)/1000.f,(80200.f-f.P.X)/1000.f),
            FMath::Min((f.P.Y+21800.f)/1000.f,(-12200.f-f.P.Y)/1000.f));
        const float Shelter=FMath::Max(FMath::Clamp(ArcadeInterior,0.f,1.f)*FMath::Clamp((2300.f-f.P.Z)/200.f,0.f,1.f),
            FMath::Clamp(PlazaInterior,0.f,1.f)*.85f);
        const float ShelterScale=FMath::Lerp(1.f,i%5==0?.85f:0.f,Shelter);
        Xf[i] = FTransform(f.R, f.P, FVector(f.Size*ShelterScale));
    }
    Leaves->BatchUpdateInstancesTransforms(0, Xf, true, true, true);
}
