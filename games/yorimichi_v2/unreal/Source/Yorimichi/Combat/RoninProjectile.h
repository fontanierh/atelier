#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "RoninProjectile.generated.h"

class UStaticMeshComponent;
class AWandererCharacter;

/** A committed thrown blade. Only authority sweeps or resolves damage; clients receive its movement. */
UCLASS()
class YORIMICHI_API ARoninProjectile : public AActor
{
    GENERATED_BODY()
public:
    ARoninProjectile();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    static ARoninProjectile* Throw(AWandererCharacter* Source, AWandererCharacter* Target);
private:
    friend class FSwordCombatContactTest;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Blade;
    FVector Velocity = FVector::ZeroVector;
    TWeakObjectPtr<AWandererCharacter> Thrower;
    bool bReflected = false, bPending = false;
    void Contact(AWandererCharacter* Victim, const FVector& At);
};
