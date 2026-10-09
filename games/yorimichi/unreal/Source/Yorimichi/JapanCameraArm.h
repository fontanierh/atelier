#pragma once
#include "CoreMinimal.h"
#include "GameFramework/SpringArmComponent.h"
#include "JapanCameraArm.generated.h"

class AJapanWorld;

/** The chase camera's arm (docs/CAMERA.md):
 *  - solid things (the terrain, walls, roofs, decks, cliffs, houses, the tree house) stop it: the arm pulls in fast in
 *    front of them and eases back out once they clear;
 *  - thin things (trees, posts, lanterns, props) do not stop it: they ignore the camera channel and fade whole instead
 *    (USeeThroughComponent);
 *  - squeezed against a wall, the camera rises over Cairo and looks down at him rather than going into his head;
 *  - on the tree house it never dives under the floor he stands on.
 *  It sweeps with its own ProbeRadius; the engine's ProbeSize is not used. With japan.SeeThroughHole 1 (the old hole)
 *  the probe passes the tree house (AJapanWorld::IsSeeThroughProbeIgnored). */
UCLASS()
class YORIMICHI_API UJapanCameraArm : public USpringArmComponent
{
    GENERATED_BODY()
public:
    UJapanCameraArm(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    /** The world whose tree house the probe passes in hole mode (set by USeeThroughComponent). */
    void SetSeeThroughHouse(AJapanWorld* World) { House = World; }

    /** Radius of the sphere swept from Cairo to the camera (cm): it keeps the whole near plane off a solid surface. */
    UPROPERTY(EditAnywhere, Category = Camera) float ProbeRadius = 20.f;
    /** How quickly the arm pulls in when something solid comes between (s, the smoothing time). */
    UPROPERTY(EditAnywhere, Category = Camera) float PullInTime = .06f;
    /** How gently it eases back out once the way clears (s, the smoothing time: out in about three times this). */
    UPROPERTY(EditAnywhere, Category = Camera) float EaseOutTime = .3f;
    /** Below this arm length (cm) the camera starts to rise over Cairo, fully at 40% of it. */
    UPROPERTY(EditAnywhere, Category = Camera) float SqueezeLength = 160.f;
    /** How high the camera rises over him when squeezed (cm). */
    UPROPERTY(EditAnywhere, Category = Camera) float LiftHeight = 50.f;
    /** On the tree house, the camera stays this far above the floor under Cairo (cm). */
    UPROPERTY(EditAnywhere, Category = Camera) float FloorClearance = 40.f;

protected:
    virtual void UpdateDesiredArmLocation(bool bDoTrace, bool bDoLocationLag, bool bDoRotationLag, float DeltaTime) override;

private:
    TWeakObjectPtr<AJapanWorld> House;
    float Length = -1.f;
    float Speed = 0.f;
    float Lift = 0.f;
    uint64 LastFrame = 0;
    float FloorZ = 0.f;
    float FloorWeight = 0.f;
    bool PassesHouse() const;
    /** How far a sphere of Radius moves from From along Dir before it hits something solid (at most Dist); -1 if it
     *  starts inside something. */
    float Free(const FVector& From, const FVector& Dir, float Dist, float Radius, const FCollisionQueryParams& Params) const;
};
