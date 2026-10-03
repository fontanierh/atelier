#include "AnimNode_RideInertialization.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimNodeMessages.h"
#include "Animation/AnimNode_Inertialization.h"
#include "Animation/BlendProfile.h"
#include "Animation/Skeleton.h"
#include "HAL/IConsoleManager.h"

namespace
{
    // The standard request message, answered by this node.
    class FRideInertializationRequester final : public UE::Anim::IInertializationRequester
    {
    public:
        FRideInertializationRequester(const FAnimationBaseContext&, FAnimNode_RideInertialization* InNode) : Node(*InNode) {}
        virtual void RequestInertialization(float Duration, const UBlendProfile* Profile) override { Node.RequestInertialization(Duration, Profile); }
        virtual void RequestInertialization(const FInertializationRequest& Request) override { Node.RequestInertialization(Request.Duration, Request.BlendProfile); }
        virtual void AddDebugRecord(const FAnimInstanceProxy&, int32) override {}
        virtual FName GetTag() const override { return NAME_None; }
    private:
        FAnimNode_RideInertialization& Node;
    };

    // skate.RideTrace (RideTransition.cpp): the node's own line about each recache and each request it cannot start.
    bool Tracing()
    {
        static const IConsoleVariable* Trace = IConsoleManager::Get().FindConsoleVariable(TEXT("skate.RideTrace"));
        return Trace && Trace->GetInt() > 0;
    }

    // A reset that drops a blend in progress or the stored poses, and why (the instance's name only while tracing).
    void TraceReset(bool bLoses, const FAnimInstanceProxy* Proxy, const TCHAR* Why)
    {
        if (bLoses && Tracing()) UE_LOG(LogTemp, Display, TEXT("SKATE trace inertialization f%llu %s: reset, %s"), GFrameCounter,
            Proxy ? *Proxy->GetAnimInstanceName() : TEXT("-"), Why);
    }

    // Where a bone of a local-space pose is in component space.
    FVector ComponentLocation(const FCompactPose& Pose, FCompactPoseBoneIndex Bone)
    {
        const FBoneContainer& Bones = Pose.GetBoneContainer();
        FTransform T = Pose[Bone];
        for (FCompactPoseBoneIndex P = Bones.GetParentBoneIndex(Bone); P.IsValid(); P = Bones.GetParentBoneIndex(P)) T = T * Pose[P];
        return T.GetTranslation();
    }

    constexpr float MinDelta = 1e-4f;
    constexpr float MinOffset = 1e-4f;     // cm, or radians
}

void FAnimNode_RideInertialization::FDecay::Init(float InX0, float InV0, float Duration)
{
    X0 = InX0; V0 = InV0; T1 = FMath::Max(Duration, MinDelta);
    A0 = A = B = C = 0;
    if (X0 < MinOffset) { X0 = V0 = 0; T1 = 0; return; }
    // The offset only shrinks: a pose moving away from the source starts at rest, and one closing in fast enough to
    // overshoot settles sooner.
    V0 = FMath::Min(V0, 0.f);
    if (V0 < 0) T1 = FMath::Max(MinDelta, FMath::Min(T1, -5.f * X0 / V0));
    const float T2 = T1 * T1, T3 = T2 * T1, T4 = T3 * T1, T5 = T4 * T1;
    A0 = FMath::Max(0.f, (-8.f * V0 * T1 - 20.f * X0) / T2);
    A = -(A0 * T2 + 6.f * V0 * T1 + 12.f * X0) / (2.f * T5);
    B = (3.f * A0 * T2 + 16.f * V0 * T1 + 30.f * X0) / (2.f * T4);
    C = -(3.f * A0 * T2 + 12.f * V0 * T1 + 20.f * X0) / (2.f * T3);
}

float FAnimNode_RideInertialization::FDecay::At(float T) const
{
    if (T >= T1) return 0;
    const float T2 = T * T, T3 = T2 * T;
    return A * T3 * T2 + B * T2 * T2 + C * T3 + .5f * A0 * T2 + V0 * T + X0;
}

void FAnimNode_RideInertialization::RequestInertialization(float Duration, const UBlendProfile* BlendProfile)
{
    if (Duration < 0) return;
    if (Pending < 0 || Duration < Pending || (Duration == Pending && BlendProfile)) { Pending = Duration; PendingProfile = BlendProfile; }
}

void FAnimNode_RideInertialization::Reset()
{
    Pending = -1; PendingProfile = nullptr; DeltaTime = 0; PreviousDelta = 0;
    Previous1.Reset(); Previous2.Reset(); Offsets.Reset();
    bActive = false; Elapsed = Longest = 0;
}

void FAnimNode_RideInertialization::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    FAnimNode_Base::Initialize_AnyThread(Context);
    Source.Initialize(Context);
    TraceReset(bActive || Previous1.Num() > 0, Context.AnimInstanceProxy, TEXT("initialized"));
    Reset();
    CachedBones.Reset();
}

void FAnimNode_RideInertialization::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
    FAnimNode_Base::CacheBones_AnyThread(Context);
    Source.CacheBones(Context);
    // The compact pose may have changed (a level of detail): the stored poses no longer line up. The same bones again
    // (a physics asset swapped, a mesh refreshed) keep them, so a switch in the same frame still blends.
    const TArray<FBoneIndexType>& Bones = Context.AnimInstanceProxy->GetRequiredBones().GetBoneIndicesArray();
    if (Tracing()) UE_LOG(LogTemp, Display, TEXT("SKATE trace inertialization f%llu %s: bones recached, %s"), GFrameCounter,
        *Context.AnimInstanceProxy->GetAnimInstanceName(),
        Bones == CachedBones ? TEXT("the same: the blend carries on") : TEXT("changed: the stored poses are dropped"));
    if (Bones == CachedBones) return;
    CachedBones = Bones;
    const float Request = Pending;
    const UBlendProfile* Profile = PendingProfile;
    TraceReset(bActive || Previous1.Num() > 0, Context.AnimInstanceProxy, TEXT("the bones changed"));
    Reset();
    Pending = Request; PendingProfile = Profile;
}

void FAnimNode_RideInertialization::ResetDynamics(ETeleportType Type)
{
    TraceReset(bActive || Previous1.Num() > 0, nullptr, Type == ETeleportType::ResetPhysics ? TEXT("the mesh was teleported (reset physics)") : TEXT("the mesh was teleported"));
    Reset();
}

void FAnimNode_RideInertialization::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    // Coming back after updates without this node: the stored poses are stale.
    if (UpdateCounter.HasEverBeenUpdated() && !UpdateCounter.WasSynchronizedCounter(Context.AnimInstanceProxy->GetUpdateCounter()))
    {
        TraceReset(bActive || Previous1.Num() > 0, Context.AnimInstanceProxy, TEXT("not updated the frame before"));
        Reset();
    }
    UpdateCounter.SynchronizeWith(Context.AnimInstanceProxy->GetUpdateCounter());
    {
        UE::Anim::TScopedGraphMessage<FRideInertializationRequester> Message(Context, Context, this);
        Source.Update(Context);
    }
    DeltaTime += Context.GetDeltaTime();
}

float FAnimNode_RideInertialization::LargestGap(const FCompactPose& Pose) const
{
    const FBoneContainer& Bones = Pose.GetBoneContainer();
    FCompactPoseBoneIndex Root(INDEX_NONE);
    if (!SpeedRoot.IsNone())
    {
        const int32 MeshIndex = Bones.GetPoseBoneIndexForBoneName(SpeedRoot);
        if (MeshIndex != INDEX_NONE) Root = Bones.MakeCompactPoseIndex(FMeshPoseBoneIndex(MeshIndex));
    }
    // Both poses composed to component space, parents first (a compact pose lists every parent before its children).
    const int32 Num = Pose.GetNumBones();
    TArray<FTransform, TInlineAllocator<64>> From, To;
    TArray<bool, TInlineAllocator<64>> Counted;
    From.SetNumUninitialized(Num); To.SetNumUninitialized(Num); Counted.SetNumZeroed(Num);
    float Gap = 0;
    for (const FCompactPoseBoneIndex Bone : Pose.ForEachBoneIndex())
    {
        const int32 I = Bone.GetInt();
        const FCompactPoseBoneIndex Parent = Bones.GetParentBoneIndex(Bone);
        const bool bParent = Parent.IsValid();
        From[I] = bParent ? Previous1[I] * From[Parent.GetInt()] : Previous1[I];
        To[I] = bParent ? Pose[Bone] * To[Parent.GetInt()] : Pose[Bone];
        Counted[I] = !Root.IsValid() || Bone == Root || (bParent && Counted[Parent.GetInt()]);
        if (Counted[I]) Gap = FMath::Max(Gap, float(FVector::Dist(From[I].GetTranslation(), To[I].GetTranslation())));
    }
    return Gap;
}

void FAnimNode_RideInertialization::Start(const FCompactPose& Pose, float Duration, const UBlendProfile* Profile)
{
    const int32 Num = Pose.GetNumBones();
    Offsets.SetNum(Num);
    const bool bVelocity = Previous2.Num() == Num && PreviousDelta > MinDelta;
    const FBoneContainer& BoneContainer = Pose.GetBoneContainer();
    // Poses far apart: long enough that no bone crosses the gap faster than MaxSpeed.
    if (MaxSpeed > 0)
    {
        const float Needed = 1.875f * LargestGap(Pose) / MaxSpeed;
        if (Needed > Duration) Duration = FMath::Max(Duration, FMath::Min(Needed, MaxDuration));
    }
    const USkeleton* Skeleton = BoneContainer.GetSkeletonAsset();
    const bool bProfile = Profile && Profile->GetSkeleton() && Skeleton;
    if (bProfile)
    {
        Durations.SetNum(Skeleton->GetReferenceSkeleton().GetNum());
        Profile->FillSkeletonBoneDurationsArray(Durations, Duration, Skeleton);
    }
    Longest = 0;
    for (const FCompactPoseBoneIndex Bone : Pose.ForEachBoneIndex())
    {
        const int32 I = Bone.GetInt();
        const FTransform& Now = Pose[Bone];
        FBoneOffset& O = Offsets[I];
        float BoneDuration = Duration;
        if (bProfile)
        {
            const FSkeletonPoseBoneIndex SkeletonBone = BoneContainer.GetSkeletonPoseIndexFromCompactPoseIndex(Bone);
            if (Durations.IsValidIndex(SkeletonBone.GetInt())) BoneDuration = Durations[SkeletonBone];
        }
        if (BoneDuration <= MinDelta)
        {
            // This bone takes the new pose at once.
            O = FBoneOffset();
            continue;
        }
        // Translation: the offset along its own direction, and how fast it changed over the last frame.
        const FVector Delta = Previous1[I].GetTranslation() - Now.GetTranslation();
        const float X0 = float(Delta.Size());
        O.Direction = X0 > MinOffset ? FVector3f(Delta / X0) : FVector3f::ZeroVector;
        float V0 = 0;
        if (bVelocity && X0 > MinOffset)
            V0 = (X0 - float(FVector::DotProduct(Previous2[I].GetTranslation() - Now.GetTranslation(), FVector(O.Direction)))) / PreviousDelta;
        O.Translation.Init(X0, V0, BoneDuration);
        // Rotation: the offset about its own axis, the shorter way round.
        FQuat Q = Previous1[I].GetRotation() * Now.GetRotation().Inverse();
        Q.Normalize();
        if (Q.W < 0) Q = -Q;
        FVector Axis; float Angle;
        Q.ToAxisAndAngle(Axis, Angle);
        if (Angle > MinOffset)
        {
            O.Axis = FVector3f(Axis);
            float R0 = 0;
            if (bVelocity)
            {
                FQuat P = Previous2[I].GetRotation() * Now.GetRotation().Inverse();
                P.Normalize();
                if (P.W < 0) P = -P;
                const float Before = 2.f * FMath::Atan2(float(FVector::DotProduct(FVector(P.X, P.Y, P.Z), Axis)), float(P.W));
                R0 = (Angle - Before) / PreviousDelta;
            }
            O.Rotation.Init(Angle, R0, BoneDuration);
        }
        else { O.Axis = FVector3f::ZeroVector; O.Rotation.Init(0, 0, BoneDuration); }
        Longest = FMath::Max3(Longest, O.Translation.T1, O.Rotation.T1);
    }
    bActive = Longest > 0;
    Elapsed = 0;
}

void FAnimNode_RideInertialization::Evaluate_AnyThread(FPoseContext& Output)
{
    Source.Evaluate(Output);
    FCompactPose& Pose = Output.Pose;
    const int32 Num = Pose.GetNumBones();
    const float Dt = DeltaTime;
    DeltaTime = 0;
    if (Previous1.Num() != Num)
    {
        TraceReset(bActive || Previous1.Num() > 0, Output.AnimInstanceProxy, TEXT("the pose has other bones"));
        Previous1.Reset(); Previous2.Reset(); bActive = false;
    }
    if (Pending >= 0 && Previous1.Num() == Num)
    {
        Start(Pose, Pending, PendingProfile);
        // The previous output carries on by one frame: the first frame continues its motion rather than holding it.
        Elapsed = Dt;
    }
    else if (bActive) Elapsed += Dt;
    if (Pending >= 0 && Previous1.Num() != Num && Tracing())
        UE_LOG(LogTemp, Display, TEXT("SKATE trace inertialization f%llu %s: a %.2f s request cut (no previous pose)"), GFrameCounter,
            *Output.AnimInstanceProxy->GetAnimInstanceName(), Pending);
    Pending = -1; PendingProfile = nullptr;
    if (bActive && Elapsed >= Longest) bActive = false;
    // The hips (else the bone that started farthest from the source): its offset now, and where the source and the
    // output put it in component space, so a jump of the shown body can be told from the node's own curve.
    FCompactPoseBoneIndex Traced(INDEX_NONE);
    FVector TracedSource = FVector::ZeroVector;
    FTransform RootSource;
    if (bActive && Tracing())
    {
        RootSource = Pose[FCompactPoseBoneIndex(0)];
        const FBoneContainer& Bones = Pose.GetBoneContainer();
        const FReferenceSkeleton& Reference = Bones.GetReferenceSkeleton();
        float Largest = -1.f;
        for (const FCompactPoseBoneIndex Bone : Pose.ForEachBoneIndex())
        {
            const FString Name = Reference.GetBoneName(Bones.MakeMeshPoseIndex(Bone).GetInt()).ToString();
            if (Name.Equals(TEXT("pelvis"), ESearchCase::IgnoreCase) || Name.Equals(TEXT("hips"), ESearchCase::IgnoreCase)) { Traced = Bone; break; }
            if (Offsets[Bone.GetInt()].Translation.X0 > Largest) { Largest = Offsets[Bone.GetInt()].Translation.X0; Traced = Bone; }
        }
        TracedSource = ComponentLocation(Pose, Traced);
    }
    if (bActive)
    {
        for (const FCompactPoseBoneIndex Bone : Pose.ForEachBoneIndex())
        {
            const FBoneOffset& O = Offsets[Bone.GetInt()];
            FTransform& T = Pose[Bone];
            const float X = O.Translation.At(Elapsed);
            if (X != 0) T.AddToTranslation(FVector(O.Direction) * X);
            const float R = O.Rotation.At(Elapsed);
            if (R != 0) T.SetRotation((FQuat(FVector(O.Axis), R) * T.GetRotation()).GetNormalized());
        }
    }
    if (Traced.IsValid())
    {
        const FBoneOffset& O = Offsets[Traced.GetInt()];
        const FVector Shown = ComponentLocation(Pose, Traced);
        // The root too: a source root that turns or moves carries the bones' local offsets with it.
        const FTransform& Root = Pose[FCompactPoseBoneIndex(0)];
        const FVector RootAt = RootSource.GetTranslation();
        UE_LOG(LogTemp, Display, TEXT("SKATE trace inertialization f%llu %s: t %.3f of %.3f (dt %.3f), bone %d offset %.1f of %.1f cm (v0 %.0f, ends %.3f), turn %.1f of %.1f deg; source (%.1f %.1f %.1f) shown (%.1f %.1f %.1f); root source (%.1f %.1f %.1f) rot (%.1f %.1f %.1f) shown rot (%.1f %.1f %.1f)"),
            GFrameCounter, *Output.AnimInstanceProxy->GetAnimInstanceName(), Elapsed, Longest, Dt, Traced.GetInt(), O.Translation.At(Elapsed),
            O.Translation.X0, O.Translation.V0, O.Translation.T1, FMath::RadiansToDegrees(O.Rotation.At(Elapsed)), FMath::RadiansToDegrees(O.Rotation.X0),
            TracedSource.X, TracedSource.Y, TracedSource.Z, Shown.X, Shown.Y, Shown.Z, RootAt.X, RootAt.Y, RootAt.Z,
            RootSource.Rotator().Pitch, RootSource.Rotator().Yaw, RootSource.Rotator().Roll, Root.Rotator().Pitch, Root.Rotator().Yaw, Root.Rotator().Roll);
    }
    // Keep the output for the next request.
    Swap(Previous1, Previous2);
    Previous1.SetNumUninitialized(Num, EAllowShrinking::No);
    for (const FCompactPoseBoneIndex Bone : Pose.ForEachBoneIndex()) Previous1[Bone.GetInt()] = Pose[Bone];
    PreviousDelta = Dt;
}

void FAnimNode_RideInertialization::GatherDebugData(FNodeDebugData& DebugData)
{
    FString Line = DebugData.GetNodeName(this);
    Line += bActive ? FString::Printf(TEXT("(%.2f / %.2f s)"), Elapsed, Longest) : FString(TEXT("(inactive)"));
    DebugData.AddDebugItem(Line);
    Source.GatherDebugData(DebugData);
}
