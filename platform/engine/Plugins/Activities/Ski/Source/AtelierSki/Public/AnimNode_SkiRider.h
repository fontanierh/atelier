#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "SkiComponent.h"
#include "AnimNode_SkiRider.generated.h"

/**
 * The skiing pose over the character's own animation, for a native anim instance (README.md, "Adding it to a game").
 * While the ski component has the body (GetPose) the pelvis goes where the simulation carries it, the trunk bends with
 * the crouch and tuck, the legs reach the skis with two-bone IK and the feet turn with them, and the arms reach for
 * balance or a grab. With an active ragdoll this pose is what its joints follow.
 *
 * Use: link it between the character's graph and the next node (its OnFoot) and add GetNodes() to GetCustomNodes().
 * The ski component is found on the anim instance's owning actor.
 */
USTRUCT()
struct ATELIERSKI_API FAnimNode_SkiRider : public FAnimNode_Base
{
    GENERATED_BODY()

    /** The character's own pose. */
    UPROPERTY() FPoseLink OnFoot;

    void GetNodes(TArray<FAnimNode_Base*>& Nodes) { Nodes.Add(this); }

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
    virtual bool HasPreUpdate() const override { return true; }
    virtual void PreUpdate(const UAnimInstance* InAnimInstance) override;

private:
    TWeakObjectPtr<const USkiComponent> Ski;
    FSkiPose Pose;
    bool bActive = false;
};
