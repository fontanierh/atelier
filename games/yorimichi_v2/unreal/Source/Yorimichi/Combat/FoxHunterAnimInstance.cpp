#include "FoxHunterAnimInstance.h"
#include "FoxHunter.h"
#include "JapanNetwork.h"
#include "WandererAnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNode_SequencePlayer.h"
#include "Animation/AnimSequence.h"
#include "AnimNodes/AnimNode_BlendSpacePlayer.h"

struct FFoxHunterAnimProxy final : public FAnimInstanceProxy
{
    FAnimNode_BlendSpacePlayer_Standalone Moving;
    FAnimNode_SequencePlayer_Standalone Action;
    FWandererStateNode State;
    float Speed = 0.f, TopSpeed = 591.f;
    uint32 AppliedSerial = MAX_uint32;

    explicit FFoxHunterAnimProxy(UAnimInstance* Owner) : FAnimInstanceProxy(Owner)
    {
        State.Ground.SetLinkNode(&Moving); State.Action.SetLinkNode(&Action);
    }
    virtual FAnimNode_Base* GetCustomRootNode() override { return &State; }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override { Nodes = { &Moving, &Action, &State }; }
    virtual void Initialize(UAnimInstance* Instance) override
    {
        if (const AFoxHunter* Fox = Cast<AFoxHunter>(Instance->TryGetPawnOwner()))
            if (const UFoxHunterDefinition* D = Fox->GetDefinition())
            {
                Moving.SetBlendSpace(D->Locomotion);
                Action.SetSequence(D->FindAction(TEXT("Idle")));
                TopSpeed = FMath::Max(1.f, D->RunSpeed);
            }
        FAnimInstanceProxy::Initialize(Instance);
    }
    virtual void PreUpdate(UAnimInstance* Instance, float Dt) override
    {
        FAnimInstanceProxy::PreUpdate(Instance, Dt);
        const AFoxHunter* Fox = Cast<AFoxHunter>(Instance->TryGetPawnOwner());
        if (!Fox || !Fox->GetDefinition()) return;
        Speed = Fox->GetVelocity().Size2D();
        State.bAction = !Fox->GetAnimationAction().IsNone();
        State.Serial = Fox->GetActionSerial();
        State.BlendDuration = Fox->GetActionBlendTime();
        if (State.bAction && AppliedSerial != State.Serial)
        {
            if (UAnimSequence* Clip = Fox->GetDefinition()->FindAction(Fox->GetAnimationAction()))
            {
                Action.SetSequence(Clip); Action.SetAccumulatedTime(0.f); Action.SetLoopAnimation(Fox->DoesActionLoop()); Action.SetPlayRate(1.f);
            }
        }
        if (State.bAction && JapanNetwork::IsOnline(Fox->GetWorld()) && !Fox->HasAuthority())
        {
            Action.SetAccumulatedTime(Fox->GetActionTime()); Action.SetPlayRate(0.f);
        }
        AppliedSerial = State.Serial;
    }
    virtual void Update(float Dt) override
    {
        // The blend space scales its clips to the speed; beyond the run sample only the cycle speeds up.
        Moving.SetPosition(FVector(FMath::Min(Speed, TopSpeed), 0, 0));
        Moving.SetPlayRate(FMath::Max(1.f, Speed / TopSpeed));
    }
};

UFoxHunterAnimInstance::UFoxHunterAnimInstance() { RootMotionMode = ERootMotionMode::RootMotionFromEverything; }
FAnimInstanceProxy* UFoxHunterAnimInstance::CreateAnimInstanceProxy() { return new FFoxHunterAnimProxy(this); }
void UFoxHunterAnimInstance::DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) { delete static_cast<FFoxHunterAnimProxy*>(Proxy); }
