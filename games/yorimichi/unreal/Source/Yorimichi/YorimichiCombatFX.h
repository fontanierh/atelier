#pragma once
#include "CoreMinimal.h"
#include "AtelierFX.h"
#include "YorimichiCombatFX.generated.h"

/**
 * Yorimichi's combat feedback on top of the platform's effects (AAtelierFX, spawned as this class through the FX
 * settings in DefaultGame.ini): the sword's swing, hit, parry and charge, the player getting hurt and knocked down,
 * and the spirit embers of a defeated fox.
 */
UCLASS()
class YORIMICHI_API AYorimichiCombatFX : public AAtelierFX
{
    GENERATED_BODY()
public:
    static AYorimichiCombatFX* Get(const UObject* WorldContext);

    void SwordSwing(const FVector& At, int32 Strength);
    void SwordHit(const FVector& At, const FVector& SwingDir, int32 Strength, AActor* Wielder, AActor* Victim);
    void Parry(const FVector& At, AActor* Defender, AActor* Attacker);
    void PlayerHurt(const FVector& At, const FVector& From, float Damage, AActor* Victim, AActor* Attacker, bool bKnockDown);
    void ChargeTick(const FVector& Base, const FVector& Tip, float Fraction, float Dt);
    void ChargeReady(const FVector& At);
    void SpiritEmbers(const FVector& At, int32 Count, float Radius, float Rise);

private:
    float ChargeAccumulator = 0.f;
};
