#include "GullFlock.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"

AGullFlock::AGullFlock()
{
    PrimaryActorTick.bCanEverTick = true;
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AGullFlock::BeginPlay()
{
    Super::BeginPlay();
    UStaticMesh* Body = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Japan/Assets/BirdBody.BirdBody"));
    UStaticMesh* WLm = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Japan/Assets/BirdWingL.BirdWingL"));
    UStaticMesh* WRm = LoadObject<UStaticMesh>(nullptr, TEXT("/Game/Japan/Assets/BirdWingR.BirdWingR"));
    if (!Body || !WLm || !WRm) return;
    for (int32 i = 0; i < 7; i++)
    {
        FGull G;
        G.Root = NewObject<USceneComponent>(this); G.Root->SetupAttachment(RootComponent); G.Root->RegisterComponent(); Keep.Add(G.Root);
        auto Make = [&](UStaticMesh* M, const FVector& Off) {
            UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this); C->SetStaticMesh(M); C->SetupAttachment(G.Root);
            C->SetRelativeLocation(Off); C->SetRelativeScale3D(FVector(1.5f)); C->SetCollisionEnabled(ECollisionEnabled::NoCollision); C->RegisterComponent(); Keep.Add(C); return C; };
        Make(Body, FVector::ZeroVector); G.WL = Make(WLm, FVector(0, -8.f, 4.f)); G.WR = Make(WRm, FVector(0, 8.f, 4.f));
        G.Radius = FMath::FRandRange(3500.f, 8000.f); G.Height = FMath::FRandRange(2500.f, 5000.f);
        G.Speed = FMath::FRandRange(0.10f, 0.18f) * (i % 2 ? 1.f : -1.f); G.Phase = FMath::FRandRange(0.f, 10.f); G.Angle = FMath::FRandRange(0.f, 2 * PI);
        Gulls.Add(G);
    }
}

void AGullFlock::Tick(float Dt)
{
    Super::Tick(Dt);
    const float T = GetWorld()->GetTimeSeconds();
    for (FGull& G : Gulls)
    {
        G.Angle += G.Speed * Dt;
        const FVector C = GetActorLocation();
        const FVector P = C + FVector(FMath::Cos(G.Angle) * G.Radius, FMath::Sin(G.Angle) * G.Radius, G.Height + FMath::Sin(T * 0.3f + G.Phase) * 400.f);
        const FVector Tan = FVector(-FMath::Sin(G.Angle), FMath::Cos(G.Angle), 0) * FMath::Sign(G.Speed);
        FRotator R = Tan.Rotation(); R.Roll = -22.f * FMath::Sign(G.Speed); R.Pitch = FMath::Cos(T * 0.3f + G.Phase) * 6.f;
        G.Root->SetWorldLocationAndRotation(P, R);
        const bool bFlap = FMath::Fmod(T * 0.25f + G.Phase, 1.f) < 0.4f;
        const float A = bFlap ? 8.f + FMath::Sin(T * 9.f + G.Phase) * 38.f : 10.f;
        G.WL->SetRelativeRotation(FRotator(0, 0, A)); G.WR->SetRelativeRotation(FRotator(0, 0, -A));
    }
}
