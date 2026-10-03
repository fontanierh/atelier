#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "AnimNode_RideInertialization.h"
#include "AnimNode_SkateRider.generated.h"

class USkateComponent;

/**
 * The skate pose over the character's own animation, for a native anim instance (README.md, "Adding it to a game").
 * While the skate component drives the body (riding, a bail, a mount or dismount, carrying the board on foot) its pose
 * (USkateComponent::GetRetailPose) replaces OnFoot. Each switch the component asks to conceal (GetPoseBlendSerial) is
 * inertialized above both (FAnimNode_RideInertialization), and OnFoot restarts fresh when it comes back, as a blend
 * list's "reset child on activation" does.
 *
 * Use: link the character's graph to OnFoot, return GetRoot() from GetCustomRootNode() and add GetNodes() to
 * GetCustomNodes(). The skate component is found on the anim instance's owning actor.
 */
USTRUCT()
struct ATELIERSKATE_API FAnimNode_SkateRider : public FAnimNode_Base
{
    GENERATED_BODY()

    /** The character's own pose. */
    UPROPERTY() FPoseLink OnFoot;

    /** The graph's root: the inertialization, with this node as its source. */
    FAnimNode_Base* GetRoot();
    /** The nodes the proxy initializes (both need their pre-update or dynamics reset). */
    void GetNodes(TArray<FAnimNode_Base*>& Nodes);
    /** Whether the last update showed the skate pose. */
    bool IsSkatePose() const { return bSkate; }

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
    virtual bool HasPreUpdate() const override { return true; }
    virtual void PreUpdate(const UAnimInstance* InAnimInstance) override;

private:
    UPROPERTY() FAnimNode_RideInertialization Blend;
    TWeakObjectPtr<const USkateComponent> Skate;
    TArray<FTransform> Pose;             // mesh-indexed local transforms; empty: OnFoot shows
    uint32 BlendSerial = 0, AppliedSerial = 0;
    float BlendTime = 0.f;
    bool bSkate = false, bShowedSkate = false, bSerialKnown = false;
};
