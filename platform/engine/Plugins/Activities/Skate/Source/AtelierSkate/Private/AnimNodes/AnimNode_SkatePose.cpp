#include "AnimNodes/AnimNode_SkatePose.h"

#include "Animation/AnimInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/Actor.h"
#include "SkateComponent.h"

namespace
{
float ClampedSkateWeight(float Weight)
{
    return FMath::IsFinite(Weight) ? FMath::Clamp(Weight, 0.f, 1.f) : 0.f;
}

void HashScalar(uint64& Hash, double Value)
{
    uint64 Bits = 0;
    static_assert(sizeof(Bits) == sizeof(Value));
    FMemory::Memcpy(&Bits, &Value, sizeof(Bits));
    // Defined byte order also keeps the diagnostic independent of host endianness.
    for (uint32 Byte = 0; Byte < 8; ++Byte)
    {
        Hash ^= (Bits >> (Byte * 8)) & 0xff;
        Hash *= 1099511628211ull;
    }
}
}

void CaptureSkatePoseSnapshot(const USkateComponent* Component, FSkatePoseSnapshot& OutSnapshot, uint64 Generation)
{
    check(IsInGameThread());
    OutSnapshot = Component ? MakeSkatePoseSnapshot(Component->GetRetailPose(), Component->IsRiding()) : FSkatePoseSnapshot();
    OutSnapshot.CaptureGeneration = Generation;
    OutSnapshot.RuntimeGeneration = Component ? Component->GetPoseGeneration() : 0;
    OutSnapshot.SourceSerial = Component ? Component->GetPoseSerial() : 0;
    OutSnapshot.RiderSerial = Component ? Component->GetSerial() : 0;
}

FSkatePoseSnapshot MakeSkatePoseSnapshot(const TArray<FTransform>& LocalTransforms, bool bRiding)
{
    FSkatePoseSnapshot Result;
    Result.bRiding = bRiding;
    if (!bRiding) return Result;
    for (const FTransform& Transform : LocalTransforms)
        if (Transform.ContainsNaN()) ++Result.RejectedTransforms;
    if (LocalTransforms.IsEmpty() || Result.RejectedTransforms != 0) return Result;
    Result.LocalTransforms = LocalTransforms;
    Result.bValid = true;
    return Result;
}

bool ApplySkatePoseSnapshot(const FSkatePoseSnapshot& Snapshot, FPoseContext& Output, float Weight)
{
    const float Alpha = ClampedSkateWeight(Weight);
    if (!Snapshot.bRiding || !Snapshot.bValid || Snapshot.LocalTransforms.IsEmpty() || Alpha == 0.f) return false;

    const FBoneContainer& Required = Output.Pose.GetBoneContainer();
    if (Alpha == 1.f)
    {
        // This is deliberately the same assignment path as the original game proxy, including missing bones.
        Output.ResetToRefPose();
        for (FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
        {
            const int32 Index = Required.MakeMeshPoseIndex(Bone).GetInt();
            if (Snapshot.LocalTransforms.IsValidIndex(Index)) Output.Pose[Bone] = Snapshot.LocalTransforms[Index];
        }
    }
    else
    {
        FPoseContext Target(Required, Output.ExpectsAdditivePose());
        Target.ResetToRefPose();
        for (FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
        {
            const int32 Index = Required.MakeMeshPoseIndex(Bone).GetInt();
            if (Snapshot.LocalTransforms.IsValidIndex(Index)) Target.Pose[Bone] = Snapshot.LocalTransforms[Index];
            Output.Pose[Bone].BlendWith(Target.Pose[Bone], Alpha);
        }
    }
    return true;
}

uint64 GetSkatePoseSnapshotHash(const FSkatePoseSnapshot& Snapshot)
{
    uint64 Hash = 14695981039346656037ull;
    HashScalar(Hash, Snapshot.LocalTransforms.Num());
    for (const FTransform& Transform : Snapshot.LocalTransforms)
    {
        const FVector Translation = Transform.GetTranslation();
        const FQuat Rotation = Transform.GetRotation();
        const FVector Scale = Transform.GetScale3D();
        HashScalar(Hash, Translation.X); HashScalar(Hash, Translation.Y); HashScalar(Hash, Translation.Z);
        HashScalar(Hash, Rotation.X); HashScalar(Hash, Rotation.Y); HashScalar(Hash, Rotation.Z); HashScalar(Hash, Rotation.W);
        HashScalar(Hash, Scale.X); HashScalar(Hash, Scale.Y); HashScalar(Hash, Scale.Z);
    }
    return Hash;
}

FSkatePoseDebugState GetSkatePoseDebugState(const FSkatePoseSnapshot& Snapshot, float Weight)
{
    FSkatePoseDebugState State;
    State.BoneCount = Snapshot.LocalTransforms.Num();
    State.RejectedTransforms = Snapshot.RejectedTransforms;
    State.CaptureGeneration = static_cast<int64>(Snapshot.CaptureGeneration);
    State.RuntimeGeneration = static_cast<int64>(Snapshot.RuntimeGeneration);
    State.SourceSerial = Snapshot.SourceSerial;
    State.RiderSerial = Snapshot.RiderSerial;
    State.bRiding = Snapshot.bRiding;
    State.bValid = Snapshot.bValid;
    State.EffectiveWeight = Snapshot.bRiding && Snapshot.bValid ? ClampedSkateWeight(Weight) : 0.f;
    State.PoseHash = FString::Printf(TEXT("%016llx"), static_cast<unsigned long long>(GetSkatePoseSnapshotHash(Snapshot)));
    return State;
}

void FAnimNode_SkatePose::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    FAnimNode_Base::Initialize_AnyThread(Context);
    BasePose.Initialize(Context);
}

void FAnimNode_SkatePose::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
    BasePose.CacheBones(Context);
}

void FAnimNode_SkatePose::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    GetEvaluateGraphExposedInputs().Execute(Context);
    // Keep the host graph's gait/action clocks advancing exactly as they did beneath the native proxy override.
    BasePose.Update(Context);
}

void FAnimNode_SkatePose::Evaluate_AnyThread(FPoseContext& Output)
{
    const float Alpha = GetEffectiveWeight();
    if (Alpha == 1.f && ApplySkatePoseSnapshot(Snapshot, Output, Alpha)) return;
    BasePose.Evaluate(Output);
    ApplySkatePoseSnapshot(Snapshot, Output, Alpha);
}

void FAnimNode_SkatePose::PreUpdate(const UAnimInstance* InAnimInstance)
{
    check(IsInGameThread());
    const USkateComponent* Component = SourceComponent.Get();
    if (!Component && bFindComponentOnOwner && InAnimInstance)
    {
        const USkeletalMeshComponent* Mesh = InAnimInstance->GetSkelMeshComponent();
        const AActor* Owner = Mesh ? Mesh->GetOwner() : nullptr;
        if (Owner) Component = Owner->FindComponentByClass<USkateComponent>();
    }
    CaptureFromComponent(Component);
}

void FAnimNode_SkatePose::CaptureFromComponent(const USkateComponent* Component)
{
    CaptureSkatePoseSnapshot(Component, Snapshot, ++CaptureGeneration);
}

void FAnimNode_SkatePose::SetPoseSnapshot(const FSkatePoseSnapshot& InSnapshot)
{
    check(IsInGameThread());
    Snapshot = MakeSkatePoseSnapshot(InSnapshot.LocalTransforms, InSnapshot.bRiding);
    Snapshot.CaptureGeneration = ++CaptureGeneration;
    Snapshot.RuntimeGeneration = InSnapshot.RuntimeGeneration;
    Snapshot.SourceSerial = InSnapshot.SourceSerial;
    Snapshot.RiderSerial = InSnapshot.RiderSerial;
    Snapshot.RejectedTransforms = FMath::Max(Snapshot.RejectedTransforms, InSnapshot.RejectedTransforms);
    // An explicitly invalid upstream snapshot must remain invalid even if its transform array is finite.
    Snapshot.bValid = Snapshot.bValid && InSnapshot.bValid && Snapshot.RejectedTransforms == 0;
}

float FAnimNode_SkatePose::GetEffectiveWeight() const
{
    return Snapshot.bRiding && Snapshot.bValid ? ClampedSkateWeight(Weight) : 0.f;
}

void FAnimNode_SkatePose::GatherDebugData(FNodeDebugData& DebugData)
{
    const float Alpha = GetEffectiveWeight();
    DebugData.AddDebugItem(FString::Printf(TEXT("%s (Skate: %.1f%%, Bones: %d, Capture: %llu, Runtime: %llu, Serial: %u, Rejected: %d)"),
        *DebugData.GetNodeName(this), Alpha * 100.f, Snapshot.LocalTransforms.Num(),
        static_cast<unsigned long long>(Snapshot.CaptureGeneration), static_cast<unsigned long long>(Snapshot.RuntimeGeneration),
        Snapshot.SourceSerial, Snapshot.RejectedTransforms));
    BasePose.GatherDebugData(DebugData.BranchFlow(1.f - Alpha));
}
