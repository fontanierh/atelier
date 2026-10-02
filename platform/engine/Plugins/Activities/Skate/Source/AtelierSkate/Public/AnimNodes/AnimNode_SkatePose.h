#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "AnimNode_SkatePose.generated.h"

class USkateComponent;

/** A game-thread copy of the native rider's local transforms, indexed by mesh bone (not compact bone). */
struct ATELIERSKATE_API FSkatePoseSnapshot
{
    TArray<FTransform> LocalTransforms;
    uint64 CaptureGeneration = 0;
    uint64 RuntimeGeneration = 0;
    uint32 SourceSerial = 0;
    uint32 RiderSerial = 0;
    int32 RejectedTransforms = 0;
    bool bRiding = false;
    bool bValid = false;
};

/** Value-only node telemetry; safe to expose after the animation proxy finishes its worker tasks. */
USTRUCT(BlueprintType)
struct ATELIERSKATE_API FSkatePoseDebugState
{
    GENERATED_BODY()

    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int32 BoneCount = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int32 RejectedTransforms = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int64 CaptureGeneration = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int64 RuntimeGeneration = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int64 SourceSerial = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") int64 RiderSerial = 0;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") bool bRiding = false;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") bool bValid = false;
    /** Native hosts can report their root and input wiring along with the node values. */
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") bool bNativeGraphRoot = false;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") bool bBasePoseLinked = false;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") float EffectiveWeight = 0.f;
    UPROPERTY(BlueprintReadOnly, Category = "Skate|Pose") FString PoseHash;
};

/** Game thread only. Never retains the component or any other UObject in the copied snapshot. */
ATELIERSKATE_API void CaptureSkatePoseSnapshot(const USkateComponent* Component, FSkatePoseSnapshot& OutSnapshot,
    uint64 CaptureGeneration = 0);

/** Value-only snapshot construction for native hosts with their own pose source; rejects non-finite transforms. */
ATELIERSKATE_API FSkatePoseSnapshot MakeSkatePoseSnapshot(const TArray<FTransform>& LocalTransforms, bool bRiding = true);

/** Worker-safe. Zero weight or an inactive/invalid snapshot leaves Output untouched and returns false.
 *  Full weight matches the native skate pose: reset to reference pose, then copy by mesh bone index.
 *  Partial weight blends that same target into Output; curves and attributes keep their base values. */
ATELIERSKATE_API bool ApplySkatePoseSnapshot(const FSkatePoseSnapshot& Snapshot, FPoseContext& Output, float Weight = 1.f);

/** Worker-safe hash of transform values only, without object pointers, allocator state or struct padding. */
ATELIERSKATE_API uint64 GetSkatePoseSnapshotHash(const FSkatePoseSnapshot& Snapshot);
ATELIERSKATE_API FSkatePoseDebugState GetSkatePoseDebugState(const FSkatePoseSnapshot& Snapshot, float Weight = 1.f);

/** Feed the native skating pose into any local-space animation graph. UObject reads occur only in PreUpdate.
 *  With no live skate pose the base graph passes through; Weight=1 preserves the original skating output. */
USTRUCT(BlueprintInternalUseOnly)
struct ATELIERSKATE_API FAnimNode_SkatePose : public FAnimNode_Base
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Links")
    FPoseLink BasePose;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skate", meta = (PinShownByDefault, ClampMin = "0", ClampMax = "1"))
    float Weight = 1.f;

    /** Optional explicit source; otherwise discover the skate component on the animation instance's owner. */
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Transient, Category = "Skate", meta = (PinHiddenByDefault))
    TWeakObjectPtr<USkateComponent> SourceComponent;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "Skate", meta = (NeverAsPin))
    bool bFindComponentOnOwner = true;

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
    virtual void GatherDebugData(FNodeDebugData& DebugData) override;
    virtual bool HasPreUpdate() const override { return true; }
    virtual void PreUpdate(const UAnimInstance* InAnimInstance) override;

    /** For native graph hosts that perform their own game-thread source selection. */
    void CaptureFromComponent(const USkateComponent* Component);
    /** Game thread only. Copies and validates a value snapshot supplied by a native host. */
    void SetPoseSnapshot(const FSkatePoseSnapshot& InSnapshot);
    /** Read only after the proxy has completed any worker tasks, or from that proxy's worker task. */
    const FSkatePoseSnapshot& GetSnapshot() const { return Snapshot; }
    float GetEffectiveWeight() const;
    FSkatePoseDebugState GetDebugState() const { return GetSkatePoseDebugState(Snapshot, Weight); }

private:
    FSkatePoseSnapshot Snapshot;
    uint64 CaptureGeneration = 0;
};
