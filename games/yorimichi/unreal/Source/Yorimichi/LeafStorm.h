#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LeafStorm.generated.h"

class UInstancedStaticMeshComponent; class AJapanWorld;

struct FStormLeaf { FVector P = FVector::ZeroVector, V = FVector::ZeroVector; FRotator R = FRotator::ZeroRotator; FVector Spin = FVector::ZeroVector; float Phase = 0.f; float RestT = -1.f; float Size = 1.f; int32 Tick = 0; };

/** Wind-blown autumn leaves simulated on the CPU around the player: gusts, flutter, tumbling, pushed by the traveler
 *  and the bird, settle on the ground and take off again on the next gust. */
UCLASS()
class YORIMICHI_API ALeafStorm : public AActor
{
    GENERATED_BODY()
public:
    ALeafStorm();
    virtual void BeginPlay() override;
    virtual void Tick(float Dt) override;
    UPROPERTY() UInstancedStaticMeshComponent* Leaves = nullptr;
    UPROPERTY() AJapanWorld* World = nullptr;
    TArray<FStormLeaf> L; TArray<FTransform> Xf; int32 Count = 900; int32 Frame = 0;
    void Respawn(FStormLeaf& Leaf, const FVector& Player, bool bInitial);
    float GroundZ(const FVector& P) const;
};
