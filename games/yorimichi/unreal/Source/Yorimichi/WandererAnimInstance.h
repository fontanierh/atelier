#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimNodeBase.h"
#include "WandererAnimInstance.generated.h"

/** Transition poses retain outgoing joint velocity and fade it with a quintic blend. */
USTRUCT()
struct FWandererStateNode : public FAnimNode_Base
{
    GENERATED_BODY()
    UPROPERTY() FPoseLink Ground;
    UPROPERTY() FPoseLink Action;
    bool bAction = false;
    uint32 Serial = 0, PreviousSerial = 0;
    float BlendDuration = 0.16f;
    float RecoveryAlpha = 0.f;
    bool bAdvanceGround = false;
    float DeltaSeconds = 0.f, PreviousDelta = 0.f, BlendTime = 0.f;
    bool bCaptureTransition = false;
    TArray<FTransform> LastPose, PreviousPose, TransitionPose;
    TArray<FVector> TranslationVelocity, RotationVelocity;
    FBlendedHeapCurve LastCurve, TransitionCurve;
    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
};

/** Native animation graph: blend spaces -> velocity-preserving action transitions -> skinned mesh. */
UCLASS(Transient, Blueprintable)
class YORIMICHI_API UWandererAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    UWandererAnimInstance();
    /** The finger wrap's last evaluation, as JSON for the live probe (#7633): per hand (sword hand, off hand) the weight
     *  it was evaluated at and, per digit (index to little, thumb), its state (unmeasured, straight, solved), deepest
     *  overlap with the handle (cm), nearest approach on the usable span (cm; 100: none) and the thumb-to-index skin gap.
     *  Copied before each update, so it is the previous frame's: Evaluations and Frame tell a fresh one from a stale one. */
    UFUNCTION(BlueprintCallable, Category = "Animation") FString GripReport() const;
    struct FGripDigits
    {
        uint32 Evaluations = 0;
        uint64 Frame = 0;   // the frame it was copied in
        float Evaluated[2] = { 0.f, 0.f }, Pinch[2] = { 100.f, 100.f };
        uint8 State[2][5] = {};
        float Residual[2][5] = {}, Grip[2][5] = {};
    } GripDigits;
protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};
