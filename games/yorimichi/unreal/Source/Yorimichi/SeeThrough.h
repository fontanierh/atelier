#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "SeeThrough.generated.h"

class AJapanWorld;
class UMaterialParameterCollection;

/** Camera see-through (docs/CAMERA.md). The shared switches: japan.SeeThrough and japan.SeeThroughRadius. */
namespace JapanSeeThrough
{
    YORIMICHI_API bool IsEnabled();
    YORIMICHI_API float Radius();
    /** On the tree house's instance groups: the camera probe passes them and the materials cut them instead. */
    extern YORIMICHI_API const FName Tag;
}

/** Feeds /Game/SeeThrough/MPC_SeeThrough every frame from the player's pawn: where Cairo stands, the cut round him,
 *  the tree house room he is in, and the trail of where he walked in the last second. The materials that read it
 *  (unreal/Scripts/see_through.py) dither away what stands between the camera and him, cut the room's near walls
 *  and roof, fade him out when the camera comes too close, and part the noren round him and let them swing back
 *  along the trail he walked. With the tree house's cut built, it also lets the camera probe pass through the tree
 *  house (AJapanWorld::SetSeeThroughProbe). */
UCLASS()
class YORIMICHI_API USeeThroughComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    USeeThroughComponent();
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;

private:
    UPROPERTY() TObjectPtr<UMaterialParameterCollection> Collection;
    TWeakObjectPtr<AJapanWorld> House;
    bool bLookedUp = false;
    bool bHouseCut = false;
    bool bLogged = false;
    float Strength = 0.f;
    int32 Room = INDEX_NONE;
    float RoomBlend = 0.f;
    FVector Trail[4] = {FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector, FVector::ZeroVector};
    double TrailTime[4] = {0., 0., 0., 0.};
    int32 TrailFilled = 0;
    FVector LastAt = FVector::ZeroVector;
};
