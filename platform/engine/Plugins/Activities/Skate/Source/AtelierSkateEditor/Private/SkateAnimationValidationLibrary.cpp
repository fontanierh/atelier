#include "SkateAnimationValidationLibrary.h"

#include "AnimNodes/AnimNode_SkatePose.h"
#include "AnimNodes/AnimNode_RefPose.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/SkeletalMesh.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "SkateComponent.h"
#include "SkateCollisionAsset.h"
#include "SkateProfile.h"
#include "SkateRuntimeAsset.h"
#include "UObject/UnrealType.h"
#include <limits>

namespace
{
struct FValidationReport
{
    TSharedRef<FJsonObject> Json = MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Checks;
    TArray<TSharedPtr<FJsonValue>> Issues;
    int32 Passed = 0;
    int32 Containers = 0;

    void Check(const FString& Name, bool bPassed, const FString& Detail = FString())
    {
        TSharedRef<FJsonObject> Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Name);
        Entry->SetBoolField(TEXT("passed"), bPassed);
        if (!Detail.IsEmpty()) Entry->SetStringField(TEXT("detail"), Detail);
        Checks.Add(MakeShared<FJsonValueObject>(Entry));
        if (bPassed) ++Passed;
        else Issues.Add(MakeShared<FJsonValueString>(Name + (Detail.IsEmpty() ? FString() : TEXT(": ") + Detail)));
    }

    FString Serialize()
    {
        Json->SetBoolField(TEXT("valid"), Issues.IsEmpty());
        Json->SetNumberField(TEXT("tests_run"), Checks.Num());
        Json->SetNumberField(TEXT("tests_passed"), Passed);
        Json->SetNumberField(TEXT("tests_failed"), Checks.Num() - Passed);
        Json->SetNumberField(TEXT("bone_containers"), Containers);
        Json->SetArrayField(TEXT("checks"), Checks);
        Json->SetArrayField(TEXT("issues"), Issues);
        FString Result;
        FJsonSerializer::Serialize(Json, TJsonWriterFactory<>::Create(&Result));
        return Result;
    }
};

bool TransformBitsEqual(const FTransform& A, const FTransform& B)
{
    // Compare scalar bits rather than FTransform padding; quaternion sign and signed zero are significant.
    const FVector AT = A.GetTranslation(), AS = A.GetScale3D(), BT = B.GetTranslation(), BS = B.GetScale3D();
    const FQuat AR = A.GetRotation(), BR = B.GetRotation();
    const double AV[] = { AT.X, AT.Y, AT.Z, AR.X, AR.Y, AR.Z, AR.W, AS.X, AS.Y, AS.Z };
    const double BV[] = { BT.X, BT.Y, BT.Z, BR.X, BR.Y, BR.Z, BR.W, BS.X, BS.Y, BS.Z };
    return FMemory::Memcmp(AV, BV, sizeof(AV)) == 0;
}

bool PoseBitsEqual(const FCompactPose& A, const FCompactPose& B)
{
    if (A.GetNumBones() != B.GetNumBones()) return false;
    for (FCompactPoseBoneIndex Bone : A.ForEachBoneIndex())
        if (!TransformBitsEqual(A[Bone], B[Bone])) return false;
    return true;
}

void FormerProxyAssignment(const FSkatePoseSnapshot& Snapshot, FPoseContext& Output)
{
    Output.ResetToRefPose();
    const FBoneContainer& Required = Output.Pose.GetBoneContainer();
    for (FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
    {
        const int32 Index = Required.MakeMeshPoseIndex(Bone).GetInt();
        if (Snapshot.LocalTransforms.IsValidIndex(Index)) Output.Pose[Bone] = Snapshot.LocalTransforms[Index];
    }
}

struct FValidationBaseNode : public FAnimNode_RefPose
{
    int32 Updates = 0;
    int32 Evaluations = 0;
    float LastDelta = 0.f;

    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override
    {
        ++Updates;
        LastDelta = Context.GetDeltaTime();
    }

    virtual void Evaluate_AnyThread(FPoseContext& Output) override
    {
        ++Evaluations;
        FAnimNode_RefPose::Evaluate_AnyThread(Output);
        for (FCompactPoseBoneIndex Bone : Output.Pose.ForEachBoneIndex())
            Output.Pose[Bone].AddToTranslation(FVector(1., -2., .5));
        Output.Curve.Set(TEXT("SkateValidationCurve"), .375f);
    }
};

struct FValidationProxy : public FAnimInstanceProxy
{
    FValidationBaseNode Base;
    FAnimNode_SkatePose Skate;

    explicit FValidationProxy(UAnimInstance* Instance) : FAnimInstanceProxy(Instance)
    {
        Skate.BasePose.SetLinkNode(&Base);
        Skate.bFindComponentOnOwner = false;
    }

    virtual FAnimNode_Base* GetCustomRootNode() override { return &Skate; }
    virtual void GetCustomNodes(TArray<FAnimNode_Base*>& Nodes) override { Nodes = { &Base, &Skate }; }

    void Setup(UAnimInstance* Instance, const TArray<FBoneIndexType>& Indices, UObject& Asset)
    {
        Initialize(Instance);
        GetRequiredBones().InitializeTo(Indices, UE::Anim::FCurveFilterSettings(), Asset);
        InitializeRootNode();
    }

    void Advance(float Delta = 1.f / 60.f)
    {
        UpdateAnimationNode(FAnimationUpdateContext(this, Delta));
    }

    void Capture(UAnimInstance* Instance)
    {
        PreUpdate(Instance, 1.f / 60.f);
    }

    void EvaluatePose(FPoseContext& Output)
    {
        EvaluateAnimation_WithRoot(Output, &Skate);
    }
};

TArray<FTransform> DistinctPose(const FReferenceSkeleton& Skeleton)
{
    TArray<FTransform> Pose = Skeleton.GetRefBonePose();
    for (int32 Index = 0; Index < Pose.Num(); ++Index)
    {
        Pose[Index].AddToTranslation(FVector(Index * .23, Index * -.07, Index * .11));
        Pose[Index].SetRotation((FQuat(FVector::UpVector, Index * .015) * Pose[Index].GetRotation()).GetNormalized());
    }
    return Pose;
}

void ValidateContainer(FValidationReport& Report, const FString& Name, USkeletalMesh* Mesh, UObject& Asset,
    const TArray<FBoneIndexType>& Indices, const FSkatePoseSnapshot& Snapshot)
{
    FMemMark Mark(FMemStack::Get());
    FBoneContainer Required(Indices, UE::Anim::FCurveFilterSettings(), Asset);
    Report.Check(Name + TEXT(".container_valid"), Required.IsValid() && Required.GetCompactPoseNumBones() == Indices.Num());
    if (!Required.IsValid()) return;
    ++Report.Containers;

    FPoseContext Expected(Required), Actual(Required);
    FormerProxyAssignment(Snapshot, Expected);
    Actual.ResetToRefPose();
    Report.Check(Name + TEXT(".full_weight_applied"), ApplySkatePoseSnapshot(Snapshot, Actual));
    Report.Check(Name + TEXT(".full_weight_bit_parity"), PoseBitsEqual(Expected.Pose, Actual.Pose));

    FSkatePoseSnapshot Truncated = Snapshot;
    Truncated.LocalTransforms.SetNum(FMath::Max(1, Snapshot.LocalTransforms.Num() / 2));
    FormerProxyAssignment(Truncated, Expected);
    ApplySkatePoseSnapshot(Truncated, Actual);
    Report.Check(Name + TEXT(".missing_bones_ref_pose_parity"), PoseBitsEqual(Expected.Pose, Actual.Pose));

    Actual.ResetToRefPose();
    for (FCompactPoseBoneIndex Bone : Actual.Pose.ForEachBoneIndex()) Actual.Pose[Bone].AddToTranslation(FVector(2., 3., -1.));
    Expected.Pose = Actual.Pose;
    Actual.Curve.Set(TEXT("SkateValidationCurve"), .625f);
    Report.Check(Name + TEXT(".zero_weight_passthrough"), !ApplySkatePoseSnapshot(Snapshot, Actual, 0.f) && PoseBitsEqual(Expected.Pose, Actual.Pose));
    Report.Check(Name + TEXT(".nonfinite_weight_passthrough"), !ApplySkatePoseSnapshot(Snapshot, Actual, std::numeric_limits<float>::quiet_NaN()) && PoseBitsEqual(Expected.Pose, Actual.Pose));
    FSkatePoseSnapshot Inactive = Snapshot;
    Inactive.bRiding = false;
    Report.Check(Name + TEXT(".inactive_passthrough"), !ApplySkatePoseSnapshot(Inactive, Actual) && PoseBitsEqual(Expected.Pose, Actual.Pose));
    FSkatePoseSnapshot Invalid = Snapshot;
    Invalid.bValid = false;
    Report.Check(Name + TEXT(".invalid_passthrough"), !ApplySkatePoseSnapshot(Invalid, Actual) && PoseBitsEqual(Expected.Pose, Actual.Pose));

    FPoseContext Target(Required);
    FormerProxyAssignment(Snapshot, Target);
    const FVector BaseRoot = Actual.Pose[FCompactPoseBoneIndex(0)].GetTranslation();
    const FVector TargetRoot = Target.Pose[FCompactPoseBoneIndex(0)].GetTranslation();
    Report.Check(Name + TEXT(".partial_applied"), ApplySkatePoseSnapshot(Snapshot, Actual, .5f));
    Report.Check(Name + TEXT(".partial_finite_normalized"), !Actual.ContainsNaN() && Actual.IsNormalized());
    Report.Check(Name + TEXT(".partial_translation_midpoint"), Actual.Pose[FCompactPoseBoneIndex(0)].GetTranslation().Equals((BaseRoot + TargetRoot) * .5, 1.e-8));
    Report.Check(Name + TEXT(".curve_preserved"), Actual.Curve.Get(TEXT("SkateValidationCurve")) == .625f);

    USkeletalMeshComponent* Component = NewObject<USkeletalMeshComponent>();
    Component->SetSkeletalMesh(Mesh, false);
    UAnimInstance* Instance = NewObject<UAnimInstance>(Component);
    FValidationProxy Proxy(Instance);
    Proxy.Setup(Instance, Indices, Asset);
    FPoseContext NodePose(&Proxy), BasePose(&Proxy);
    Proxy.Base.Evaluate_AnyThread(BasePose);
    Proxy.Base.Evaluations = 0;
    Proxy.Skate.SetPoseSnapshot(Snapshot);
    Proxy.Skate.Weight = 0.f;
    Proxy.Advance();
    Proxy.EvaluatePose(NodePose);
    Report.Check(Name + TEXT(".node_zero_passthrough"), PoseBitsEqual(BasePose.Pose, NodePose.Pose) && NodePose.Curve.Get(TEXT("SkateValidationCurve")) == .375f);
    Proxy.Skate.SetPoseSnapshot(Inactive);
    Proxy.Skate.Weight = 1.f;
    Proxy.Advance();
    Proxy.EvaluatePose(NodePose);
    Report.Check(Name + TEXT(".node_inactive_passthrough"), PoseBitsEqual(BasePose.Pose, NodePose.Pose));
    Proxy.Skate.SetPoseSnapshot(Snapshot);
    const int32 EvaluationsBefore = Proxy.Base.Evaluations;
    const int32 UpdatesBefore = Proxy.Base.Updates;
    Proxy.Advance();
    Proxy.EvaluatePose(NodePose);
    FormerProxyAssignment(Snapshot, Expected);
    Report.Check(Name + TEXT(".node_full_weight_bit_parity"), PoseBitsEqual(Expected.Pose, NodePose.Pose));
    Report.Check(Name + TEXT(".node_full_weight_skips_base_evaluation"), Proxy.Base.Evaluations == EvaluationsBefore);
    Report.Check(Name + TEXT(".node_full_weight_keeps_base_clock"), Proxy.Base.Updates == UpdatesBefore + 1 && Proxy.Base.LastDelta == 1.f / 60.f);
    Proxy.Skate.Weight = .5f;
    Proxy.Advance();
    Proxy.EvaluatePose(NodePose);
    Report.Check(Name + TEXT(".node_partial_finite"), !NodePose.ContainsNaN() && NodePose.IsNormalized() && NodePose.Curve.Get(TEXT("SkateValidationCurve")) == .375f);

    FSkatePoseSnapshot Poisoned = Snapshot;
    const double Infinity = std::numeric_limits<double>::infinity();
    FMemory::Memcpy(&Poisoned.LocalTransforms[0], &Infinity, sizeof(Infinity));
    Proxy.Skate.SetPoseSnapshot(Poisoned);
    Proxy.Skate.Weight = 1.f;
    Proxy.Advance();
    Proxy.EvaluatePose(NodePose);
    Report.Check(Name + TEXT(".node_nonfinite_snapshot_rejected"), !Proxy.Skate.GetSnapshot().bValid && Proxy.Skate.GetSnapshot().RejectedTransforms == 1 && PoseBitsEqual(BasePose.Pose, NodePose.Pose));

    USkateComponent* Source = NewObject<USkateComponent>();
    Proxy.Skate.SourceComponent = Source;
    const uint64 CaptureBefore = Proxy.Skate.GetSnapshot().CaptureGeneration;
    Proxy.Capture(Instance);
    const FSkatePoseSnapshot& Captured = Proxy.Skate.GetSnapshot();
    Report.Check(Name + TEXT(".proxy_preupdate_registered"), Captured.CaptureGeneration == CaptureBefore + 1);
    Report.Check(Name + TEXT(".off_component_capture_clears_active_pose"), !Captured.bRiding && !Captured.bValid && Captured.LocalTransforms.IsEmpty());
    Report.Check(Name + TEXT(".source_generations_captured"), Captured.RuntimeGeneration == Source->GetPoseGeneration() && Captured.SourceSerial == Source->GetPoseSerial() && Captured.RiderSerial == Source->GetSerial());
}

void ValidateProfile(FValidationReport& Report, const FString& ProfilePath)
{
    USkateProfile* Profile = ProfilePath.IsEmpty() ? nullptr : LoadObject<USkateProfile>(nullptr, *ProfilePath);
    if (!ProfilePath.IsEmpty())
    {
        Report.Check(TEXT("profile.loaded"), Profile != nullptr, ProfilePath);
        if (Profile)
        {
            TArray<FString> Errors;
            const bool bValid = Profile->ValidateProfile(Errors);
            Report.Check(TEXT("profile.asset_valid"), bValid, FString::Join(Errors, TEXT("; ")));
        }
    }

    USkateProfile* Fixture = NewObject<USkateProfile>();
    Fixture->RuntimeData = TSoftObjectPtr<USkateRuntimeAsset>(FSoftObjectPath(TEXT("/Game/Validation/Runtime.Runtime")));
    TArray<FString> Errors;
    Report.Check(TEXT("profile.stock_defaults"), Fixture->Difficulty == ESkateDifficulty::Normal && !Fixture->bGoofy &&
        Fixture->TruckTightness == .5f && Fixture->PopHeightScale == 1.f && Fixture->AirSpinScale == 1.f &&
        Fixture->PushSpeedScale == 1.f && Fixture->PushPowerScale == 1.f && Fixture->VertAssist == 0.f && Fixture->CollisionScanPeriodSeconds == .25f);
    const bool bStockValid = Fixture->ValidateProfile(Errors);
    Report.Check(TEXT("profile.stock_structural_valid"), bStockValid, FString::Join(Errors, TEXT("; ")));
    Fixture->Difficulty = ESkateDifficulty::Easy;
    Report.Check(TEXT("profile.easy_preset"), Fixture->GetDifficultyPreset() == TEXT("easy"));
    Fixture->Difficulty = ESkateDifficulty::Normal;
    Report.Check(TEXT("profile.normal_preset"), Fixture->GetDifficultyPreset() == TEXT("normal"));
    Fixture->Difficulty = ESkateDifficulty::Hardcore;
    Report.Check(TEXT("profile.hardcore_preset"), Fixture->GetDifficultyPreset() == TEXT("hardcore"));

    Fixture->Difficulty = static_cast<ESkateDifficulty>(255);
    Fixture->TruckTightness = std::numeric_limits<float>::quiet_NaN();
    Fixture->PopHeightScale = 3.f;
    Fixture->AirSpinScale = 0.f;
    Fixture->PushSpeedScale = 3.f;
    Fixture->PushPowerScale = 0.f;
    Fixture->VertAssist = 2.f;
    Fixture->CollisionScanPeriodSeconds = 0.f;
    Fixture->RuntimeData.Reset();
    Fixture->CollisionDataCatalog = {
        TSoftObjectPtr<USkateCollisionAsset>(),
        TSoftObjectPtr<USkateCollisionAsset>(FSoftObjectPath(TEXT("/Game/Validation/Collision.Collision"))),
        TSoftObjectPtr<USkateCollisionAsset>(FSoftObjectPath(TEXT("/Game/Validation/Collision.Collision")))
    };
    const bool bInvalidAccepted = Fixture->ValidateProfile(Errors);
    Report.Check(TEXT("profile.invalid_values_rejected"), !bInvalidAccepted);
    Report.Check(TEXT("profile.independent_errors_accumulated"), Errors.Num() == 11, FString::Printf(TEXT("%d issues: %s"), Errors.Num(), *FString::Join(Errors, TEXT("; "))));
}

bool ReadHostDebugState(UAnimInstance* Instance, FSkatePoseDebugState& OutState)
{
    UFunction* Function = Instance->FindFunction(TEXT("GetSkatePoseDebugState"));
    FStructProperty* ReturnProperty = Function ? CastField<FStructProperty>(Function->GetReturnProperty()) : nullptr;
    if (!ReturnProperty || ReturnProperty->Struct != FSkatePoseDebugState::StaticStruct() || Function->NumParms != 1) return false;
    struct FParameters { FSkatePoseDebugState ReturnValue; } Parameters;
    Instance->ProcessEvent(Function, &Parameters);
    OutState = MoveTemp(Parameters.ReturnValue);
    return true;
}

void ValidateNativeHost(FValidationReport& Report, USkeletalMesh* Mesh, const FString& ClassPath)
{
    if (ClassPath.IsEmpty()) return;
    UClass* Class = LoadClass<UAnimInstance>(nullptr, *ClassPath);
    Report.Check(TEXT("host.class_loaded"), Class != nullptr, ClassPath);
    if (!Class || !Mesh) return;
    USkeletalMeshComponent* Component = NewObject<USkeletalMeshComponent>();
    Component->SetSkeletalMesh(Mesh, false);
    // Unregistered components skip InitAnim's LOD bone setup. Populate the shared container directly;
    // this preview needs no actor, render registration or physics-asset discovery.
    for (int32 Index = 0; Index < Mesh->GetRefSkeleton().GetNum(); ++Index)
        Component->RequiredBones.Add(static_cast<FBoneIndexType>(Index));
    Component->GetSharedRequiredBones()->InitializeTo(Component->RequiredBones, UE::Anim::FCurveFilterSettings(), *Mesh);
    UAnimInstance* Instance = NewObject<UAnimInstance>(Component, Class);
    Instance->InitializeAnimation(false);
    FSkatePoseDebugState Before, After;
    const bool bReadable = ReadHostDebugState(Instance, Before);
    Report.Check(TEXT("host.diagnostics_exposed"), bReadable);
    if (bReadable)
    {
        Report.Check(TEXT("host.skate_node_is_graph_root"), Before.bNativeGraphRoot);
        Report.Check(TEXT("host.base_pose_linked"), Before.bBasePoseLinked);
        // Force the graph update to remain deferred so this checks the actual game-thread PreUpdate boundary.
        Instance->UpdateAnimation(1.f / 60.f, false, UAnimInstance::EUpdateAnimationFlag::ForceParallelUpdate);
        ReadHostDebugState(Instance, After);
        Report.Check(TEXT("host.actual_proxy_preupdate_captures_once"), After.CaptureGeneration == Before.CaptureGeneration + 1);
        Report.Check(TEXT("host.ownerless_preview_passthrough"), !After.bRiding && !After.bValid && After.BoneCount == 0 && After.EffectiveWeight == 0.f);
        Instance->ParallelUpdateAnimation();
        Instance->PostUpdateAnimation();
    }
    Instance->UninitializeAnimation();
}
}

FString USkateAnimationValidationLibrary::ValidateSkateAnimation(const FString& MeshPath, const FString& ProfilePath,
    const FString& AnimInstanceClassPath)
{
    check(IsInGameThread());
    FValidationReport Report;
    Report.Json->SetStringField(TEXT("mesh"), MeshPath);
    Report.Json->SetStringField(TEXT("profile"), ProfilePath);
    Report.Json->SetStringField(TEXT("anim_instance_class"), AnimInstanceClassPath);
    ValidateProfile(Report, ProfilePath);

    USkeletalMesh* Mesh = LoadObject<USkeletalMesh>(nullptr, *MeshPath);
    Report.Check(TEXT("mesh.loaded"), Mesh != nullptr, MeshPath);
    if (Mesh && Mesh->GetSkeleton() && Mesh->GetRefSkeleton().GetNum() > 0)
    {
        const FReferenceSkeleton& Reference = Mesh->GetRefSkeleton();
        const TArray<FTransform> Pose = DistinctPose(Reference);
        const FSkatePoseSnapshot Snapshot = MakeSkatePoseSnapshot(Pose);
        Report.Check(TEXT("snapshot.finite_source_accepted"), Snapshot.bValid && Snapshot.LocalTransforms.Num() == Pose.Num());
        FSkatePoseSnapshot Copy = Snapshot;
        Report.Check(TEXT("snapshot.hash_copy_stable"), GetSkatePoseSnapshotHash(Snapshot) == GetSkatePoseSnapshotHash(Copy));
        Copy.LocalTransforms.Last().AddToTranslation(FVector(.125, 0., 0.));
        Report.Check(TEXT("snapshot.hash_detects_change"), GetSkatePoseSnapshotHash(Snapshot) != GetSkatePoseSnapshotHash(Copy));
        TArray<FTransform> Poisoned = Pose;
        const double NaN = std::numeric_limits<double>::quiet_NaN();
        // Inject into transform storage so UE's diagnostic setters cannot silently repair the test input.
        FMemory::Memcpy(&Poisoned[0], &NaN, sizeof(NaN));
        if (Poisoned.Num() > 1) FMemory::Memcpy(&Poisoned[1], &NaN, sizeof(NaN));
        const FSkatePoseSnapshot Rejected = MakeSkatePoseSnapshot(Poisoned);
        Report.Check(TEXT("snapshot.nonfinite_source_rejected"), !Rejected.bValid && Rejected.LocalTransforms.IsEmpty() && Rejected.RejectedTransforms == FMath::Min(2, Poisoned.Num()));
        Report.Check(TEXT("snapshot.inactive_source_not_retained"), MakeSkatePoseSnapshot(Pose, false).LocalTransforms.IsEmpty());
        FSkatePoseSnapshot Cleared = Snapshot;
        CaptureSkatePoseSnapshot(nullptr, Cleared, 17);
        Report.Check(TEXT("snapshot.missing_component_clears_stale_pose"), !Cleared.bValid && !Cleared.bRiding && Cleared.LocalTransforms.IsEmpty() && Cleared.CaptureGeneration == 17 && Cleared.RuntimeGeneration == 0 && Cleared.SourceSerial == 0);

        TArray<FBoneIndexType> All, Sparse, Root;
        for (int32 Index = 0; Index < Reference.GetNum(); ++Index) All.Add(static_cast<FBoneIndexType>(Index));
        for (int32 Index = 0; Index < Reference.GetNum(); ++Index)
            if (Index == 0 || Reference.GetBoneName(Index) == TEXT("foot_L") || Reference.GetBoneName(Index) == TEXT("hand_R"))
                Sparse.Add(static_cast<FBoneIndexType>(Index));
        Reference.EnsureParentsExistAndSort(Sparse);
        Root.Add(0);
        ValidateContainer(Report, TEXT("mesh_all"), Mesh, *Mesh, All, Snapshot);
        ValidateContainer(Report, TEXT("mesh_sparse"), Mesh, *Mesh, Sparse, Snapshot);
        ValidateContainer(Report, TEXT("mesh_root"), Mesh, *Mesh, Root, Snapshot);
        TArray<FBoneIndexType> SkeletonIndices;
        const FReferenceSkeleton& SkeletonReference = Mesh->GetSkeleton()->GetReferenceSkeleton();
        for (int32 Index = 0; Index < SkeletonReference.GetNum(); ++Index) SkeletonIndices.Add(static_cast<FBoneIndexType>(Index));
        ValidateContainer(Report, TEXT("skeleton_all"), Mesh, *Mesh->GetSkeleton(), SkeletonIndices,
            MakeSkatePoseSnapshot(DistinctPose(SkeletonReference)));
    }
    else if (Mesh) Report.Check(TEXT("mesh.skeleton_and_bones_present"), false);
    ValidateNativeHost(Report, Mesh, AnimInstanceClassPath);
    return Report.Serialize();
}
