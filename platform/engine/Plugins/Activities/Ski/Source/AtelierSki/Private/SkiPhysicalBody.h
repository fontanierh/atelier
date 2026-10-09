// The skier's body as an active ragdoll (README.md, "Body"). The mesh's own physics bodies simulate; Physics Control
// drives every joint toward the skiing pose and holds the feet and hands from the pelvis, whose body follows the pose
// kinematically, so the body keeps up at any speed and only its limbs swing, absorb and lag. While skiing the bodies
// pass through the snow (the simulation already stands the skis on it); in a crash the pelvis lets go, gravity and
// collision come on, the drives drop to muscle tone and the body tumbles with the skier's momentum.
#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "SkiPhysicalBody.generated.h"

class UPhysicsControlComponent;
class USkeletalMeshComponent;
class USkiSettings;

UCLASS(Transient)
class USkiPhysicalBody : public UObject
{
    GENERATED_BODY()
public:
    /** Sets up on the mesh; false (and nothing changed) when it has fewer than six bodies. */
    bool Begin(USkeletalMeshComponent* InMesh, FName Pelvis, const FName (&Feet)[2], const FName (&Hands)[2]);
    void End();
    bool IsActive() const { return Control != nullptr; }
    bool IsCrashed() const { return bCrashed; }
    /** Lets the body go with a velocity (cm/s). */
    void Crash(const FVector& Velocity);
    /** Takes the body back onto the pose. */
    void Recover();
    /** Each frame after the pose: applies a pending crash velocity. */
    void Update();
    /** The pelvis body's location and velocity (cm, cm/s). */
    FVector GetPelvisLocation() const;
    FVector GetPelvisVelocity() const;

private:
    void ApplyRiding();
    void ApplyCrash();

    UPROPERTY() TObjectPtr<USkeletalMeshComponent> Mesh;
    UPROPERTY() TObjectPtr<UPhysicsControlComponent> Control;
    FName Root;
    FName SavedProfile;
    uint8 SavedUpdateMode = 0;
    FVector PendingVelocity = FVector::ZeroVector;
    int32 PendingFrames = 0;
    bool bCrashed = false;
};
