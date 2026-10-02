#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimNodeBase.h"
#include "AnimNodes/AnimNode_SkatePose.h"
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
    /** Captured skating pose values; waits for any in-flight animation evaluation before reading the proxy. */
    UFUNCTION(BlueprintPure, Category = "Skate|Debug")
    FSkatePoseDebugState GetSkatePoseDebugState() const;
protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};
