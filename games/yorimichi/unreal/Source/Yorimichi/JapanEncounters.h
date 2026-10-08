#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "JapanEncounters.generated.h"

class AWandererCharacter;

/** Server-owned encounter membership and attack leases. No viewport or local player is required. */
UCLASS()
class YORIMICHI_API UJapanEncounters : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    static bool Eligible(const AWandererCharacter* Player);
    int32 Engage(AActor* Enemy, float Range, int32 BaseHealth);
    void Refresh(AActor* Enemy, float Range);
    void End(AActor* Enemy);
    void AddThreat(AActor* Enemy, AWandererCharacter* Player, float Amount);
    AWandererCharacter* Select(AActor* Enemy, AWandererCharacter* Current) const;
    bool ReserveAttack(AActor* Enemy, AWandererCharacter* Player, float Seconds);
    void ReleaseAttack(AActor* Enemy);
    bool HoldsPlayer(AWandererCharacter* Player) const;
    uint32 Identity(AActor* Enemy) const;
    int32 FrozenHealth(AActor* Enemy, int32 Fallback) const;
private:
    struct FMember
    {
        float Threat = 0.f;
        bool bCommitted = false;
    };
    struct FEncounter
    {
        uint32 Id = 0;
        FVector Origin = FVector::ZeroVector;
        TMap<TWeakObjectPtr<AWandererCharacter>, FMember> Members;
        TWeakObjectPtr<AWandererCharacter> Attacking;
        double Updated = 0., AttackUntil = 0.;
        int32 FrozenHealth = 0;
    };
    TMap<TWeakObjectPtr<AActor>, FEncounter> Encounters;
    uint32 NextIdentity = 0;
    void Prune();
};
