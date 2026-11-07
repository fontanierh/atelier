#pragma once
#include "Components/ActorComponent.h"
#include "SeatCorrectiveComponent.generated.h"

class USkeletalMesh;
class USkeletalMeshComponent;

/** Seat correctives (SeatCorrectiveGrid.h): the morph targets <Prefix>_L.._R.. set from both hips' flexion each time the
 *  owner's mesh finalizes its pose (animation, the skating retarget, physics or a streamed pose), so the skin drawn and
 *  the skin the readers sample belong to the same pose. A mesh with no such target and no contact data has none (logged
 *  once). One with either needs every moving target, unambiguous, its bones, and valid USkinMorphContactData holding
 *  those targets; otherwise it logs FAILED and leaves them off (every weight 0). */
UCLASS()
class YORIMICHI_API USeatCorrectiveComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UPROPERTY() FString Prefix;
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    /** The targets' weights for a component-space pose, as Drive sets them (ISkateRider::GetSkatePoseMorphs). */
    void PoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose, TArray<TPair<FName, float>>& Morphs) const;
private:
    void Resolve();
    void Drive();
    /** Both hips' flexion (degrees, forward positive) in a component-space pose of the resolved asset. */
    bool Flexion(TConstArrayView<FTransform> Pose, float& FlexL, float& FlexR) const;

    FDelegateHandle Finalized;
    TWeakObjectPtr<USkeletalMeshComponent> Component;
    TWeakObjectPtr<const USkeletalMesh> Resolved;
    /** The native target of each grid cell (SeatGrid::Index); NAME_None for a zero cell the model does not carry. */
    TArray<FName> Targets;
    /** The weights last set, per grid cell. */
    TArray<float> Shown;
    int32 Pelvis = INDEX_NONE;
    int32 Thighs[2] = {INDEX_NONE, INDEX_NONE};
    FQuat PelvisBind = FQuat::Identity;
    FQuat ThighBinds[2] = {FQuat::Identity, FQuat::Identity};
    /** Each thigh's neutral head-to-shin direction, and the body's forward and up, in component space. */
    FVector Axes[2] = {FVector::DownVector, FVector::DownVector};
    FVector Forward = FVector::ForwardVector;
    FVector Up = FVector::UpVector;
    bool bResolved = false;
    bool bReady = false;
};
