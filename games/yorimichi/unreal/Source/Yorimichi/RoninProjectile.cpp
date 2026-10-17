#include "RoninProjectile.h"
#include "JapanCombat.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Components/StaticMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"

ARoninProjectile::ARoninProjectile()
{
    PrimaryActorTick.bCanEverTick = true;
    bReplicates = true;
    SetReplicateMovement(true);
    NetUpdateFrequency = 30.f;
    Blade = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("ThrownBlade"));
    SetRootComponent(Blade);
    Blade->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Blade->SetCastShadow(false);
    Blade->SetRelativeScale3D(FVector(.32f));
}

void ARoninProjectile::BeginPlay()
{
    Super::BeginPlay();
    Blade->SetStaticMesh(LoadObject<UStaticMesh>(nullptr, TEXT("/Game/SwordCamp/Assets/SM_RoninWakizashi.SM_RoninWakizashi")));
    if (HasAuthority()) SetLifeSpan(4.f);
}

ARoninProjectile* ARoninProjectile::Throw(AWandererCharacter* Source, AWandererCharacter* Target)
{
    if (!Source || !Target || !Source->HasAuthority()) return nullptr;
    const FVector Aim = Target->GetActorLocation() + FVector(0, 0, 15.f);
    const FVector Muzzle = Source->GetActorLocation() + FVector(0, 0, 25.f);
    const FVector Direction = (Aim - Muzzle).GetSafeNormal();
    const FVector Start = Muzzle +
        Direction * (Source->GetCapsuleComponent()->GetScaledCapsuleRadius() + 25.f);
    FHitResult Wall;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(RoninThrowLOS), false, Source);
    Query.AddIgnoredActor(Target);
    if (Source->GetWorld()->SweepSingleByChannel(Wall, Muzzle, Start, FQuat::Identity, ECC_Pawn,
        FCollisionShape::MakeSphere(7.f), Query) ||
        Source->GetWorld()->LineTraceSingleByChannel(Wall, Muzzle, Aim, ECC_Visibility, Query)) return nullptr;
    FActorSpawnParameters Spawn;
    Spawn.Owner = Source;
    if (auto* Shot = Source->GetWorld()->SpawnActor<ARoninProjectile>(Start, Direction.Rotation(), Spawn))
    {
        Shot->Thrower = Source;
        Shot->Velocity = (Aim - Start).GetSafeNormal() * 1100.f; // No tracking after release.
        return Shot;
    }
    return nullptr;
}

void ARoninProjectile::Tick(float Dt)
{
    Super::Tick(Dt);
    if (!HasAuthority() || bPending) return;
    const FVector Before = GetActorLocation(), After = Before + Velocity * Dt;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(RoninProjectile), false, GetOwner());
    Query.AddIgnoredActor(this);
    TArray<FHitResult> Hits;
    // Online player capsules deliberately overlap Pawn queries. Keep touch contacts as well as cover blocks.
    GetWorld()->SweepMultiByChannel(Hits, Before, After, FQuat::Identity, ECC_Pawn,
        FCollisionShape::MakeSphere(7.f), Query);
    for (const FHitResult& Hit : Hits)
    {
        if (auto* Victim = Cast<AWandererCharacter>(Hit.GetActor()); Victim &&
            ((!bReflected && !Victim->IsNpc()) || (bReflected && Victim == Thrower.Get())))
        {
            SetActorLocation(Hit.Location);
            Contact(Victim, Hit.bStartPenetrating ? Hit.Location : FVector(Hit.ImpactPoint));
        }
        else if (Hit.bBlockingHit) Destroy(); // Cover and other bodies stop the projectile.
        else continue; // Noncombat overlap volumes do not consume a blade.
        return;
    }
    SetActorLocation(After);
    AddActorLocalRotation(FRotator(0, 0, Dt * 900.f));
}

void ARoninProjectile::Contact(AWandererCharacter* Victim, const FVector& At)
{
    bPending = true;
    const FVector From = At - Velocity.GetSafeNormal() * 35.f;
    const TWeakObjectPtr<ARoninProjectile> Weak(this);
    const TWeakObjectPtr<AWandererCharacter> Defender(Victim);
    JapanCombat::Strike(this, Victim, bReflected ? 18.f : 12.f, From,
        [Weak, Defender](int32 Outcome)
        {
            auto* Shot = Weak.Get();
            auto* Player = Defender.Get();
            if (!Shot) return;
            if (Outcome == 1 && !Shot->bReflected && Player && Shot->Thrower.IsValid())
            {
                Shot->bReflected = true;
                Shot->bPending = false;
                Shot->SetOwner(Player);
                const FVector Aim = Shot->Thrower->GetActorLocation() + FVector(0, 0, 15.f);
                const FVector Start = Shot->GetActorLocation(); // Reflect from the contact, never teleport across adjacent cover.
                Shot->Velocity = (Aim - Start).GetSafeNormal() * 1450.f;
                Shot->SetActorLocationAndRotation(Start, Shot->Velocity.Rotation());
                Shot->ForceNetUpdate();
            }
            else Shot->Destroy();
        });
}
