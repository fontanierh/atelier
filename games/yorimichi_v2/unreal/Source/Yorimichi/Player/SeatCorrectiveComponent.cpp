#include "SeatCorrectiveComponent.h"
#include "SeatCorrectiveGrid.h"
#include "SkinMorphContactData.h"
#include "WandererCharacter.h"
#include "AnimationRuntime.h"
#include "Animation/MorphTarget.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"

void USeatCorrectiveComponent::BeginPlay()
{
    Super::BeginPlay();
    // The correctives follow the pose as finally shown; their targets resolve with the mesh's asset.
    Component = CastChecked<AWandererCharacter>(GetOwner())->GetMesh();
    Finalized = Component->RegisterOnBoneTransformsFinalizedDelegate(
        FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this, &USeatCorrectiveComponent::Drive));
}

void USeatCorrectiveComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (USkeletalMeshComponent* Mesh = Component.Get()) Mesh->UnregisterOnBoneTransformsFinalizedDelegate(Finalized);
    Finalized.Reset();
    Super::EndPlay(Reason);
}

void USeatCorrectiveComponent::Resolve()
{
    const AWandererCharacter* Owner = CastChecked<AWandererCharacter>(GetOwner());
    USkeletalMeshComponent* Mesh = Component.Get();
    const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
    // What the previous asset showed goes; nothing shows until this one resolves.
    if (Mesh)
        for (const FName Target : Targets)
            if (!Target.IsNone()) Mesh->SetMorphTarget(Target, 0.f);
    Targets.Init(NAME_None, SeatGrid::Count);
    Shown.Init(0.f, SeatGrid::Count);
    Resolved = Asset;
    bResolved = true;
    bReady = false;
    if (!Asset) return;
    TArray<FString> Failed, Found;
    TArray<FName> Moving;
    bool bCarries = false;
    for (int32 L = 0; L < SeatGrid::Size; ++L)
        for (int32 R = 0; R < SeatGrid::Size; ++R)
        {
            const FString Wanted = FString::Printf(TEXT("%s_L%s_R%s"), *Prefix, ANSI_TO_TCHAR(SeatGrid::Labels[L]), ANSI_TO_TCHAR(SeatGrid::Labels[R]));
            // The exact name or the name the FBX importer prefixed with its mesh's: exactly one of them, once.
            const UMorphTarget* Match = Asset->FindMorphTarget(FName(*Wanted));
            int32 Matches = Match ? 1 : 0;
            for (const UMorphTarget* Target : Asset->GetMorphTargets())
                if (Target && Target->GetName().EndsWith(TEXT("_") + Wanted)) { Match = Target; ++Matches; }
            bCarries |= Matches > 0;
            if (Matches > 1) { Failed.Add(Wanted + TEXT(" (ambiguous)")); continue; }
            if (!Match)
            {
                if (SeatGrid::Moves(L, R)) Failed.Add(Wanted + TEXT(" (missing)"));
                continue;
            }
            if (Match->GetNumDeltasForLOD(0) == 0)
            {
                if (SeatGrid::Moves(L, R)) Failed.Add(Wanted + TEXT(" (no deltas)"));
                continue;
            }
            Targets[SeatGrid::Index(L, R)] = Match->GetFName();
            if (SeatGrid::Moves(L, R)) Moving.Add(Match->GetFName());
            Found.Add(Match->GetName());
        }
    // The model opts in: a mesh with no seat target and no contact data is one without the correctives, left as it is.
    const USkinMorphContactData* Contact = USkinMorphContactData::Find(Asset);
    if (!bCarries && !Contact)
    {
        Targets.Init(NAME_None, SeatGrid::Count);
        UE_LOG(LogTemp, Display, TEXT("%s seat correctives: %s carries none"), *Owner->GetName(), *Asset->GetName());
        return;
    }
    // One that does needs them all, and their deltas captured for the skin readers (FSkinMorphOffsets): a cooked
    // build keeps none on the CPU.
    FString Receipt = TEXT("no contact data (USkinMorphContactLibrary::CaptureSkinMorphContacts)");
    if (!Contact || !Contact->Validate(Asset, Moving, Receipt)) Failed.Add(Receipt);
    // Bones by the humanoid contract; the neutral pose through the reference hierarchy.
    const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
    const auto Bone = [&](const TCHAR* Contract)
    {
        const FName Name = Owner->GetSkateBone(Contract);
        const int32 Index = Name.IsNone() ? INDEX_NONE : Ref.FindBoneIndex(Name);
        if (Index == INDEX_NONE) Failed.Add(FString(Contract) + TEXT(" (no bone)"));
        return Index;
    };
    const auto Bind = [&](int32 Index) { return FAnimationRuntime::GetComponentSpaceTransformRefPose(Ref, Index); };
    Pelvis = Bone(TEXT("pelvis"));
    const int32 ThighBones[2] = {Bone(TEXT("thigh_L")), Bone(TEXT("thigh_R"))}, Shins[2] = {Bone(TEXT("shin_L")), Bone(TEXT("shin_R"))};
    const int32 Feet[2] = {Bone(TEXT("foot_L")), Bone(TEXT("foot_R"))}, Toes[2] = {Bone(TEXT("toe_L")), Bone(TEXT("toe_R"))};
    // The body's forward and up in component space, from the authored mesh-to-actor rotation (the actor faces +X).
    const FQuat Authored = Owner->GetClass()->GetDefaultObject<AWandererCharacter>()->GetMesh()->GetRelativeRotation().Quaternion();
    Forward = Authored.UnrotateVector(FVector::ForwardVector);
    Up = Authored.UnrotateVector(FVector::UpVector);
    if (Failed.IsEmpty())
    {
        PelvisBind = Bind(Pelvis).GetRotation();
        for (int32 S = 0; S < 2; ++S)
        {
            Thighs[S] = ThighBones[S];
            ThighBinds[S] = Bind(ThighBones[S]).GetRotation();
            Axes[S] = (Bind(Shins[S]).GetLocation() - Bind(ThighBones[S]).GetLocation()).GetSafeNormal();
            const FVector Foot = Bind(Feet[S]).GetLocation();
            // As the body export asserts (pipeline/rig.py): the toes ahead of the ankles, the hips above them.
            if (((Bind(Toes[S]).GetLocation() - Foot) | Forward) <= 0. || ((Bind(Pelvis).GetLocation() - Foot) | Up) <= 0.
                || Axes[S].IsZero())
                Failed.Add(FString::Printf(TEXT("%s leg against forward %s, up %s"), S ? TEXT("right") : TEXT("left"), *Forward.ToString(), *Up.ToString()));
        }
    }
    if (!Failed.IsEmpty())
    {
        Targets.Init(NAME_None, SeatGrid::Count);
        UE_LOG(LogTemp, Error, TEXT("%s seat correctives FAILED on %s, left off: %s"), *Owner->GetName(), *Asset->GetName(), *FString::Join(Failed, TEXT(", ")));
        return;
    }
    bReady = true;
    UE_LOG(LogTemp, Display, TEXT("%s seat correctives on %s: %d targets (%s); contact %s"), *Owner->GetName(), *Asset->GetName(), Found.Num(),
        *FString::Join(Found, TEXT(",")), *Receipt);
}

bool USeatCorrectiveComponent::Flexion(TConstArrayView<FTransform> Pose, float& FlexL, float& FlexR) const
{
    if (!bReady || !Pose.IsValidIndex(Pelvis) || !Pose.IsValidIndex(Thighs[0]) || !Pose.IsValidIndex(Thighs[1])) return false;
    // Skin rotations (the current component rotation times the inverse neutral one), as the garment candidate
    // measures them: the thigh's relative to the pelvis's turns its neutral head-to-shin axis, and the flexion is
    // that axis's sagittal angle less the neutral one.
    const FQuat PelvisRotation = Pose[Pelvis].GetRotation() * PelvisBind.Inverse();
    const auto Sagittal = [&](const FVector& Axis) { return FMath::Atan2(Axis | Forward, -(Axis | Up)); };
    float* Flex[2] = {&FlexL, &FlexR};
    for (int32 S = 0; S < 2; ++S)
    {
        const FQuat Thigh = Pose[Thighs[S]].GetRotation() * ThighBinds[S].Inverse();
        const FVector Axis = (PelvisRotation.Inverse() * Thigh).RotateVector(Axes[S]);
        *Flex[S] = float(FMath::RadiansToDegrees(Sagittal(Axis) - Sagittal(Axes[S])));
    }
    return true;
}

void USeatCorrectiveComponent::Drive()
{
    USkeletalMeshComponent* Mesh = Component.Get();
    if (!Mesh) return;
    const USkeletalMesh* Asset = Mesh->GetSkeletalMeshAsset();
    if (!bResolved || Resolved.Get() != Asset) Resolve();
    float FlexL = 0.f, FlexR = 0.f, Next[SeatGrid::Count];
    if (!Flexion(Mesh->GetComponentSpaceTransforms(), FlexL, FlexR)) FlexL = FlexR = 0.f;
    SeatGrid::Weights(FlexL, FlexR, Next);
    bool bChanged = false;
    for (int32 I = 0; I < SeatGrid::Count; ++I) bChanged |= Next[I] != Shown[I];
    // Below the gate every weight was and stays 0: the neutral mesh, untouched.
    if (!bChanged || !Asset) return;
    TMap<FName, float> Curves;
    for (int32 I = 0; I < SeatGrid::Count; ++I)
        if (!Targets[I].IsNone())
        {
            Mesh->SetMorphTarget(Targets[I], Next[I]);
            Curves.Add(Targets[I], Next[I]);
        }
    // SetMorphTarget reaches the mesh at its next evaluation. This pose is already final, so show its weights now
    // too: the skin drawn and sampled this frame belongs to this pose.
    FAnimationRuntime::AppendActiveMorphTargets(Asset, Curves, Mesh->ActiveMorphTargets, Mesh->MorphTargetWeights);
    Mesh->MarkRenderDynamicDataDirty();
    for (int32 I = 0; I < SeatGrid::Count; ++I) Shown[I] = Next[I];
}

void USeatCorrectiveComponent::PoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose,
                                          TArray<TPair<FName, float>>& Morphs) const
{
    float FlexL = 0.f, FlexR = 0.f, Cells[SeatGrid::Count];
    if (!Mesh || Mesh->GetSkeletalMeshAsset() != Resolved.Get()) return;
    // As Drive sets them for this pose: 0 for every target when the flexion cannot be read.
    if (!Flexion(Pose, FlexL, FlexR)) FlexL = FlexR = 0.f;
    SeatGrid::Weights(FlexL, FlexR, Cells);
    for (int32 I = 0; I < SeatGrid::Count; ++I)
        if (!Targets[I].IsNone()) Morphs.Emplace(Targets[I], Cells[I]);
}
