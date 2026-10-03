#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "Animation/AnimTypes.h"
#include "BoneIndices.h"
#include "CustomBoneIndexArray.h"
#include "AnimNode_RideInertialization.generated.h"

class UBlendProfile;

/**
 * Inertialization for animation graphs built in C++ (an anim instance proxy's own nodes). A request makes the pose
 * carry on from where the previous frames left it, with their velocity, and settle onto the source pose over the
 * request's duration: each bone's offset from the source decays on a quintic curve (Bollo, "Inertialization:
 * High-Performance Animation Transitions in Gears of War", GDC 2018), in local space.
 *
 * It does the job of FAnimNode_Inertialization, which only runs inside an Anim Blueprint: outside shipping builds the
 * engine node reports to Animation Insights through its Anim Blueprint node data, and a node built in C++ has none.
 * Requests arrive the standard way, through the UE::Anim::IInertializationRequester graph message (blend nodes,
 * FAnimNode_Mirror's stance blend, Context.GetMessage<IInertializationRequester>()), or by RequestInertialization.
 * A request's blend profile (time factor) scales each bone's duration; a bone at 0 takes the new pose at once.
 * Curves and attributes pass through. With MaxSpeed set, poses far apart blend for longer than asked.
 */
USTRUCT()
struct ATELIERSKATE_API FAnimNode_RideInertialization : public FAnimNode_Base
{
    GENERATED_BODY()

    UPROPERTY() FPoseLink Source;

    /** Blend from the current pose over Duration seconds at the next evaluation (the shortest request of an update
     *  wins). BlendProfile, if given, scales the duration per bone (time factors); it must outlive the evaluation. */
    void RequestInertialization(float Duration, const UBlendProfile* BlendProfile = nullptr);
    bool IsActive() const { return bActive; }

    /** The fastest a bone may cross its offset (cm/s; 0: every request keeps its duration). A request lasts at least
     *  1.875 times the largest component-space gap between the two poses over MaxSpeed (the quintic's fastest point),
     *  and is stretched to at most MaxDuration. Only SpeedRoot and the bones under it count (all bones if None). */
    float MaxSpeed = 0.f;
    float MaxDuration = .25f;
    FName SpeedRoot;

    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
    virtual void GatherDebugData(FNodeDebugData& DebugData) override;
    virtual bool NeedsDynamicReset() const override { return true; }
    virtual void ResetDynamics(ETeleportType InTeleportType) override;

private:
    /** One channel's offset: x(t) = A t^5 + B t^4 + C t^3 + A0/2 t^2 + V0 t + X0, zero from T1 on. */
    struct FDecay
    {
        float X0 = 0, V0 = 0, A0 = 0, A = 0, B = 0, C = 0, T1 = 0;
        void Init(float InX0, float InV0, float Duration);
        float At(float T) const;
    };
    struct FBoneOffset
    {
        FVector3f Direction = FVector3f::ZeroVector;   // translation offset direction
        FVector3f Axis = FVector3f::ZeroVector;        // rotation offset axis
        FDecay Translation, Rotation;
    };

    void Reset();
    void Start(const FCompactPose& Pose, float Duration, const UBlendProfile* Profile);
    /** The farthest a counted bone is, in component space, between the last output and Pose (cm). */
    float LargestGap(const FCompactPose& Pose) const;

    float Pending = -1.f;            // the request for the next evaluation, -1 for none
    const UBlendProfile* PendingProfile = nullptr;
    TCustomBoneIndexArray<float, FSkeletonPoseBoneIndex> Durations;    // per skeleton bone, from a profile
    float DeltaTime = 0.f;           // accumulated by updates since the last evaluation
    // The node's output at the last two evaluations (local space, by compact pose index), and the time between them.
    TArray<FTransform> Previous1, Previous2;
    float PreviousDelta = 0.f;
    bool bActive = false;
    float Elapsed = 0.f, Longest = 0.f;
    TArray<FBoneOffset> Offsets;
    FGraphTraversalCounter UpdateCounter;
    // The mesh bones of the compact pose the stored poses were taken with: a recache that keeps them (a physics asset
    // swapped in or out re-requires the bones) keeps the stored poses and a blend in progress.
    TArray<FBoneIndexType> CachedBones;
};
