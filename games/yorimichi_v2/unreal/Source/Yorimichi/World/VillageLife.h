#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "VillageLife.generated.h"

class USkeletalMeshComponent;
class UWandererDefinition;
class AJapanWorld;

/** Cosmetic residents share existing rigs/clips. No AI, navigation or blocking bodies. */
UCLASS()
class YORIMICHI_API AVillageLife : public AActor
{
    GENERATED_BODY()
public:
    AVillageLife();
    void Initialize(AJapanWorld* Landscape,const TSharedPtr<class FJsonObject>& Village);
    virtual void Tick(float Dt) override;
private:
    UPROPERTY() TArray<TObjectPtr<USkeletalMeshComponent>> Residents;
    UPROPERTY() TObjectPtr<UWandererDefinition> Definition;
    UPROPERTY() TObjectPtr<AJapanWorld> Ground;
    FVector WalkA,WalkB;
    float Elapsed=0.f;
    bool bActive=true;
};
