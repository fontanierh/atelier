#include "NoxCharacter.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "NoxSeatMorph.h"
#include "PlayableCharacter.h"
#include "SkinMorphContactData.h"
#include "AnimationRuntime.h"
#include "Animation/MorphTarget.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    const TCHAR* NoxDefinition = TEXT("/Game/Nox/DA_Nox.DA_Nox");

    /** His move record, read once; null when it has not been built. */
    TSharedPtr<FJsonObject> NoxRecord()
    {
        static TSharedPtr<FJsonObject> Record;
        static bool bLoaded = false;
        if (!bLoaded)
        {
            bLoaded = true;
            Record = AtelierReadJson(AtelierDataPath(TEXT("nox/adventure.json")));
        }
        return Record;
    }
}

static const FPlayableCharacter::FRegister RegisterNox({ANoxCharacter::Name(), &ANoxCharacter::StaticClass, &ANoxCharacter::IsBuilt,
                                                           TEXT("unreal.nox_adventure")});

ANoxCharacter::ANoxCharacter()
{
    DefinitionAssetPath = NoxDefinition;
    SprintSpeedMultiplier = 1.f;   // the reference rig's sprint: the dash clip's own stride speed
    // 1.78 m: the capsule's half height to the crown, the soles 0.65 cm under its bottom as Cairo's (export_unreal.py).
    GetCapsuleComponent()->InitCapsuleSize(24.f, 89.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(77.f);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -89.65f));
    // His export turns Tripo's -Y to +X, the way the game's characters face.
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

bool ANoxCharacter::IsBuilt()
{
    return NoxRecord().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(NoxDefinition)));
}

void ANoxCharacter::BeginPlay()
{
    Super::BeginPlay();
    UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
    if (Set->Initialize(this, NoxRecord())) Moves = Set;
    else
    {
        DisablePlayerMovement();
        UE_LOG(LogTemp, Error, TEXT("Nox: no merged move set (build unreal.nox_adventure)"));
    }
    // The seat correctives follow the pose as finally shown; their targets resolve with the mesh's asset.
    SeatComponent = GetMesh();
    SeatFinalized = GetMesh()->RegisterOnBoneTransformsFinalizedDelegate(
        FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this, &ANoxCharacter::DriveSeat));
}

void ANoxCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    if (USkeletalMeshComponent* Mesh = SeatComponent.Get()) Mesh->UnregisterOnBoneTransformsFinalizedDelegate(SeatFinalized);
    SeatFinalized.Reset();
    Super::EndPlay(Reason);
}

void ANoxCharacter::ResolveSeat()
{
    USkeletalMeshComponent* Mesh = SeatComponent.Get();
    const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
    // What the previous asset showed goes; nothing shows until this one resolves.
    if (Mesh)
        for (const FName Target : SeatTargets)
            if (!Target.IsNone()) Mesh->SetMorphTarget(Target, 0.f);
    SeatTargets.Init(NAME_None, NoxSeat::Count);
    SeatShown.Init(0.f, NoxSeat::Count);
    SeatMesh = Asset;
    bSeatResolved = true;
    bSeatReady = false;
    if (!Asset) return;
    TArray<FString> Failed, Found;
    TArray<FName> Moving;
    bool bCarries = false;
    for (int32 L = 0; L < NoxSeat::Size; ++L)
        for (int32 R = 0; R < NoxSeat::Size; ++R)
        {
            const FString Wanted = FString::Printf(TEXT("NoxSeat_L%s_R%s"), ANSI_TO_TCHAR(NoxSeat::Labels[L]), ANSI_TO_TCHAR(NoxSeat::Labels[R]));
            // The exact name or the name the FBX importer prefixed with its mesh's: exactly one of them, once.
            const UMorphTarget* Match = Asset->FindMorphTarget(FName(*Wanted));
            int32 Matches = Match ? 1 : 0;
            for (const UMorphTarget* Target : Asset->GetMorphTargets())
                if (Target && Target->GetName().EndsWith(TEXT("_") + Wanted)) { Match = Target; ++Matches; }
            bCarries |= Matches > 0;
            if (Matches > 1) { Failed.Add(Wanted + TEXT(" (ambiguous)")); continue; }
            if (!Match)
            {
                if (NoxSeat::Moves(L, R)) Failed.Add(Wanted + TEXT(" (missing)"));
                continue;
            }
            if (Match->GetNumDeltasForLOD(0) == 0)
            {
                if (NoxSeat::Moves(L, R)) Failed.Add(Wanted + TEXT(" (no deltas)"));
                continue;
            }
            SeatTargets[NoxSeat::Index(L, R)] = Match->GetFName();
            if (NoxSeat::Moves(L, R)) Moving.Add(Match->GetFName());
            Found.Add(Match->GetName());
        }
    // The model opts in: a mesh with no seat target and no contact data is one without the correctives, left as it is.
    const USkinMorphContactData* Contact = USkinMorphContactData::Find(Asset);
    if (!bCarries && !Contact)
    {
        SeatTargets.Init(NAME_None, NoxSeat::Count);
        UE_LOG(LogTemp, Display, TEXT("NOX seat correctives: %s carries none"), *Asset->GetName());
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
        const FName Name = GetSkateBone(Contract);
        const int32 Index = Name.IsNone() ? INDEX_NONE : Ref.FindBoneIndex(Name);
        if (Index == INDEX_NONE) Failed.Add(FString(Contract) + TEXT(" (no bone)"));
        return Index;
    };
    const auto Bind = [&](int32 Index) { return FAnimationRuntime::GetComponentSpaceTransformRefPose(Ref, Index); };
    SeatPelvis = Bone(TEXT("pelvis"));
    const int32 Thighs[2] = {Bone(TEXT("thigh_L")), Bone(TEXT("thigh_R"))}, Shins[2] = {Bone(TEXT("shin_L")), Bone(TEXT("shin_R"))};
    const int32 Feet[2] = {Bone(TEXT("foot_L")), Bone(TEXT("foot_R"))}, Toes[2] = {Bone(TEXT("toe_L")), Bone(TEXT("toe_R"))};
    // His forward and up in component space, from the authored mesh-to-actor rotation (the actor faces +X).
    const FQuat Authored = GetClass()->GetDefaultObject<ANoxCharacter>()->GetMesh()->GetRelativeRotation().Quaternion();
    SeatForward = Authored.UnrotateVector(FVector::ForwardVector);
    SeatUp = Authored.UnrotateVector(FVector::UpVector);
    if (Failed.IsEmpty())
    {
        SeatPelvisBind = Bind(SeatPelvis).GetRotation();
        for (int32 S = 0; S < 2; ++S)
        {
            SeatThighs[S] = Thighs[S];
            SeatThighBinds[S] = Bind(Thighs[S]).GetRotation();
            SeatAxes[S] = (Bind(Shins[S]).GetLocation() - Bind(Thighs[S]).GetLocation()).GetSafeNormal();
            const FVector Foot = Bind(Feet[S]).GetLocation();
            // As export_unreal.py asserts: the toes ahead of the ankles, the hips above them.
            if (((Bind(Toes[S]).GetLocation() - Foot) | SeatForward) <= 0. || ((Bind(SeatPelvis).GetLocation() - Foot) | SeatUp) <= 0.
                || SeatAxes[S].IsZero())
                Failed.Add(FString::Printf(TEXT("%s leg against forward %s, up %s"), S ? TEXT("right") : TEXT("left"), *SeatForward.ToString(), *SeatUp.ToString()));
        }
    }
    if (!Failed.IsEmpty())
    {
        SeatTargets.Init(NAME_None, NoxSeat::Count);
        UE_LOG(LogTemp, Error, TEXT("NOX seat correctives FAILED on %s, left off: %s"), *Asset->GetName(), *FString::Join(Failed, TEXT(", ")));
        return;
    }
    bSeatReady = true;
    UE_LOG(LogTemp, Display, TEXT("NOX seat correctives on %s: %d targets (%s); contact %s"), *Asset->GetName(), Found.Num(),
        *FString::Join(Found, TEXT(",")), *Receipt);
}

bool ANoxCharacter::SeatFlexion(TConstArrayView<FTransform> Pose, float& FlexL, float& FlexR) const
{
    if (!bSeatReady || !Pose.IsValidIndex(SeatPelvis) || !Pose.IsValidIndex(SeatThighs[0]) || !Pose.IsValidIndex(SeatThighs[1])) return false;
    // Skin rotations (the current component rotation times the inverse neutral one), as the garment candidate
    // measures them: the thigh's relative to the pelvis's turns its neutral head-to-shin axis, and the flexion is
    // that axis's sagittal angle less the neutral one.
    const FQuat Pelvis = Pose[SeatPelvis].GetRotation() * SeatPelvisBind.Inverse();
    const auto Sagittal = [&](const FVector& Axis) { return FMath::Atan2(Axis | SeatForward, -(Axis | SeatUp)); };
    float* Flex[2] = {&FlexL, &FlexR};
    for (int32 S = 0; S < 2; ++S)
    {
        const FQuat Thigh = Pose[SeatThighs[S]].GetRotation() * SeatThighBinds[S].Inverse();
        const FVector Axis = (Pelvis.Inverse() * Thigh).RotateVector(SeatAxes[S]);
        *Flex[S] = float(FMath::RadiansToDegrees(Sagittal(Axis) - Sagittal(SeatAxes[S])));
    }
    return true;
}

void ANoxCharacter::DriveSeat()
{
    USkeletalMeshComponent* Mesh = SeatComponent.Get();
    if (!Mesh) return;
    const USkeletalMesh* Asset = Mesh->GetSkeletalMeshAsset();
    if (!bSeatResolved || SeatMesh.Get() != Asset) ResolveSeat();
    float FlexL = 0.f, FlexR = 0.f, Next[NoxSeat::Count];
    if (!SeatFlexion(Mesh->GetComponentSpaceTransforms(), FlexL, FlexR)) FlexL = FlexR = 0.f;
    NoxSeat::Weights(FlexL, FlexR, Next);
    bool bChanged = false;
    for (int32 I = 0; I < NoxSeat::Count; ++I) bChanged |= Next[I] != SeatShown[I];
    // Below the gate every weight was and stays 0: the neutral mesh, untouched.
    if (!bChanged || !Asset) return;
    TMap<FName, float> Curves;
    for (int32 I = 0; I < NoxSeat::Count; ++I)
        if (!SeatTargets[I].IsNone())
        {
            Mesh->SetMorphTarget(SeatTargets[I], Next[I]);
            Curves.Add(SeatTargets[I], Next[I]);
        }
    // SetMorphTarget reaches the mesh at its next evaluation. This pose is already final, so show its weights now
    // too: the skin drawn and sampled this frame belongs to this pose.
    FAnimationRuntime::AppendActiveMorphTargets(Asset, Curves, Mesh->ActiveMorphTargets, Mesh->MorphTargetWeights);
    Mesh->MarkRenderDynamicDataDirty();
    for (int32 I = 0; I < NoxSeat::Count; ++I) SeatShown[I] = Next[I];
}

void ANoxCharacter::GetSkatePoseMorphs(const USkeletalMeshComponent* Mesh, TConstArrayView<FTransform> Pose,
                                       TArray<TPair<FName, float>>& Morphs) const
{
    float FlexL = 0.f, FlexR = 0.f, Cells[NoxSeat::Count];
    if (!Mesh || Mesh->GetSkeletalMeshAsset() != SeatMesh.Get()) return;
    // As DriveSeat sets them for this pose: 0 for every target when the flexion cannot be read.
    if (!SeatFlexion(Pose, FlexL, FlexR)) FlexL = FlexR = 0.f;
    NoxSeat::Weights(FlexL, FlexR, Cells);
    for (int32 I = 0; I < NoxSeat::Count; ++I)
        if (!SeatTargets[I].IsNone()) Morphs.Emplace(SeatTargets[I], Cells[I]);
}
