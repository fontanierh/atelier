#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"

/** -sworddummy: a training post 1.3 m ahead of the player, swinging every 3 s so parries can be tried in play. */
void AWandererCharacter::SpawnSwordDummy()
{
    if (SwordDummy || !GetWorld()) return;
    const FVector Where = GetActorLocation() + GetActorForwardVector() * 130.f
        - FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight()) + FVector(0, 0, 70.f);
    SwordDummy = GetWorld()->SpawnActor<ASwordDummy>(Where, FRotator::ZeroRotator);
    if (SwordDummy) { SwordDummy->SetTarget(this); SwordDummy->SetAutoStrike(3.f); }
}
