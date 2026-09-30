#pragma once
#include "CoreMinimal.h"
#include "GameFramework/SpringArmComponent.h"
#include "JapanCameraArm.generated.h"

class AJapanWorld;

/** The chase camera's arm (docs/CAMERA.md). The engine's arm jumps to every probe hit and straight back; this one
 *  pulls in at once when something solid comes between (the camera never goes through what stops it) and eases back
 *  out once it clears, so a post passing between Cairo and the camera does not snap the view in and out.
 *  While the camera see-through cuts the tree house (AJapanWorld::IsSeeThroughProbeIgnored), the probe passes the
 *  tree house: the arm stays long and the walls, rails and props between are dithered away instead. On the tree
 *  house the camera is kept above the floor Cairo stands on, since that floor no longer stops it. */
UCLASS()
class YORIMICHI_API UJapanCameraArm : public USpringArmComponent
{
    GENERATED_BODY()
public:
    UJapanCameraArm(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    /** The world whose tree house the probe may pass (set by USeeThroughComponent). */
    void SetSeeThroughHouse(AJapanWorld* World) { House = World; }

    /** How fast the arm eases back out after an obstacle clears (1/s). */
    UPROPERTY(EditAnywhere, Category = Camera) float RecoverSpeed = 4.f;
    /** On the tree house, the camera stays this far above the floor under Cairo (cm). */
    UPROPERTY(EditAnywhere, Category = Camera) float FloorClearance = 40.f;

protected:
    virtual FVector BlendLocations(const FVector& DesiredArmLocation, const FVector& TraceHitLocation, bool bHitSomething, float DeltaTime) override;

private:
    TWeakObjectPtr<AJapanWorld> House;
    float Length = -1.f;
    uint64 LastBlendFrame = 0;
    float FloorZ = 0.f;
    float FloorWeight = 0.f;
    bool PassesHouse() const;
};
