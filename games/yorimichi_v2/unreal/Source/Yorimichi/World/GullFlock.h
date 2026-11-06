#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "GullFlock.generated.h"

class UStaticMeshComponent;

/** A few gulls circling over the sea: body + two flapping wings each, on offset circles. */
UCLASS()
class YORIMICHI_API AGullFlock : public AActor
{
    GENERATED_BODY()
public:
    AGullFlock();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    struct FGull { USceneComponent* Root; UStaticMeshComponent* WL; UStaticMeshComponent* WR; float Radius, Height, Speed, Phase, Angle; };
    TArray<FGull> Gulls;
    UPROPERTY() TArray<USceneComponent*> Keep;
};
