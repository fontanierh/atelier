#include "RideAnimator.h"
#include "RideAnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Animation/MirrorDataTable.h"
#include "Animation/Skeleton.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "GameFramework/Actor.h"

namespace
{
    const TCHAR* RigPath = TEXT("/Game/SkateRide/SK_SkateRider.SK_SkateRider");
    const TCHAR* MirrorPath = TEXT("/Game/SkateRide/MDT_SkateRider.MDT_SkateRider");
    const TCHAR* ClipFolders[] = {TEXT("/Game/SkateRide/Clips/B0/"), TEXT("/Game/SkateRide/Clips/B1/")};
}

FRideAnimator::FRideAnimator() = default;

// The pose mesh belongs to its owner actor and goes with it; the animator may outlive neither.
FRideAnimator::~FRideAnimator() = default;

UAnimSequence* FRideAnimator::Load(const TCHAR* Name)
{
    if (!Name) return nullptr;
    const FName Key(Name);
    if (const TStrongObjectPtr<UAnimSequence>* Found = Library.Find(Key)) return Found->Get();
    UAnimSequence* Sequence = nullptr;
    for (const TCHAR* Folder : ClipFolders)
    {
        const FString Path = FString::Printf(TEXT("%s%s.%s"), Folder, Name, Name);
        Sequence = LoadObject<UAnimSequence>(nullptr, *Path, nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (Sequence) break;
    }
    if (!Sequence) UE_LOG(LogTemp, Warning, TEXT("SKATE ride: no clip %s"), Name);
    Library.Add(Key, TStrongObjectPtr<UAnimSequence>(Sequence));
    return Sequence;
}

UAnimSequence* FRideAnimator::Clip(FName Name)
{
    if (!bRig || Name.IsNone()) return nullptr;
    UAnimSequence* Sequence = Load(*Name.ToString());
    if (Sequence && Instance.IsValid()) Instance->Hold({Sequence});
    return Sequence;
}

void FRideAnimator::Preload()
{
    if (bTried) return;
    bTried = true;
    USkeletalMesh* Rig = LoadObject<USkeletalMesh>(nullptr, RigPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
    UMirrorDataTable* Table = LoadObject<UMirrorDataTable>(nullptr, MirrorPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
    if (!Rig)
    {
        UE_LOG(LogTemp, Display, TEXT("SKATE ride: no rider rig in this build; no transition clips"));
        return;
    }
    // The published names and reference: the rig's bones in its own order, in its reference pose (RIG_TPOSE)
    // composed to root space.
    const FReferenceSkeleton& Skeleton = Rig->GetRefSkeleton();
    const TArray<FTransform>& Local = Skeleton.GetRefBonePose();
    TArray<FName> RigNames; TArray<FTransform> RigReference;
    for (int32 I = 0; I < Skeleton.GetNum(); ++I)
    {
        const int32 Parent = Skeleton.GetParentIndex(I);
        RigNames.Add(Skeleton.GetBoneName(I));
        RigReference.Add(Parent == INDEX_NONE ? Local[I] : Local[I] * RigReference[Parent]);
    }
    Names = MoveTemp(RigNames); Reference = MoveTemp(RigReference);
    RigMesh.Reset(Rig); MirrorTable.Reset(Table);
    bRig = true;
    const int32 Hips = Names.IndexOfByKey(FName(TEXT("HIPS")));
    UE_LOG(LogTemp, Display, TEXT("SKATE ride: rider rig with %d bones (hips %.1f cm; mirror %s)"),
        Names.Num(), Hips != INDEX_NONE ? Reference[Hips].GetLocation().Z : 0.f, Table ? TEXT("yes") : TEXT("no"));
}

FTransform FRideAnimator::Track(const UAnimSequence* Sequence, FName Bone, float Time)
{
    const USkeleton* Skeleton = Sequence ? Sequence->GetSkeleton() : nullptr;
    const int32 Index = Skeleton ? Skeleton->GetReferenceSkeleton().FindBoneIndex(Bone) : INDEX_NONE;
    if (Index == INDEX_NONE) return FTransform::Identity;
    FTransform Out;
    Sequence->GetBoneTransform(Out, FSkeletonPoseBoneIndex(Index), FAnimExtractContext(double(Time)), false);
    return Out;
}

FTransform FRideAnimator::RootMotion(const UAnimSequence* Sequence, float From, float To)
{
    return Sequence ? Sequence->ExtractRootMotionFromRange(From, To, FAnimExtractContext()) : FTransform::Identity;
}

// ---------------------------------------------------------------------------------------------------------------
// The pose mesh.

void FRideAnimator::Attach(AActor* Owner)
{
    if (!bRig || !Owner) return;
    if (Mesh.IsValid() && Mesh->GetOwner() == Owner && Instance.IsValid()) return;
    Detach();
    // A hidden, unattached, stationary mesh: the caller moves the rider, so the graph (and its inertialization) only
    // ever sees the clips' own root space.
    USkeletalMeshComponent* M = NewObject<USkeletalMeshComponent>(Owner, MakeUniqueObjectName(Owner, USkeletalMeshComponent::StaticClass(), TEXT("RidePose")), RF_Transient);
    M->SetUsingAbsoluteLocation(true); M->SetUsingAbsoluteRotation(true); M->SetUsingAbsoluteScale(true);
    M->PrimaryComponentTick.bCanEverTick = false;
    M->SetSkeletalMeshAsset(RigMesh.Get());
    M->SetAnimationMode(EAnimationMode::AnimationBlueprint);
    M->SetAnimInstanceClass(USkateRideAnimInstance::StaticClass());
    M->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    M->bEnableUpdateRateOptimizations = false;
    M->SetHiddenInGame(true); M->SetVisibility(false); M->SetCastShadow(false);
    M->SetCollisionEnabled(ECollisionEnabled::NoCollision); M->SetGenerateOverlapEvents(false);
    M->SetCanEverAffectNavigation(false);
    M->SetForcedLOD(1);
    M->RegisterComponent();
    USkateRideAnimInstance* I = Cast<USkateRideAnimInstance>(M->GetAnimInstance());
    if (!I)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKATE ride: the rider's anim instance did not start; no transition clips"));
        M->DestroyComponent();
        return;
    }
    I->SetMirrorTable(Cast<UMirrorDataTable>(MirrorTable.Get()));
    TArray<UAnimSequence*> Clips;
    for (const TPair<FName, TStrongObjectPtr<UAnimSequence>>& Pair : Library) if (Pair.Value) Clips.Add(Pair.Value.Get());
    I->Hold(Clips);
    Mesh = M; Instance = I;
    bFirst = true; LastKey = nullptr; Last = FRideAnimLayers();
}

void FRideAnimator::Detach()
{
    if (USkeletalMeshComponent* M = Mesh.Get()) if (!M->IsBeingDestroyed()) M->DestroyComponent();
    Mesh.Reset(); Instance.Reset();
}

void FRideAnimator::Run(const FRideAnimLayers& Layers, float Inertialize, float Dt)
{
    FRideAnimFrame Frame;
    Frame.Layers = Layers; Frame.Inertialize = Inertialize;
    Instance->SetFrame(Frame);
    USkeletalMeshComponent* M = Mesh.Get();
    M->TickAnimation(FMath::Max(Dt, 0.f), false);
    M->RefreshBoneTransforms(nullptr);
    Last = Layers;
}

void FRideAnimator::SetOverride(const FRideAnimLayers& Layers, float BlendIn)
{
    if (!bOverride || Layers.Main() != Override.Main()) PendingBlend = FMath::Max(PendingBlend, BlendIn);
    bOverride = true; Override = Layers; OverrideBlend = BlendIn;
}

void FRideAnimator::ClearOverride()
{
    if (!bOverride) return;
    bOverride = false;
    bCutNext = true; PendingBlend = 0;
}

// ---------------------------------------------------------------------------------------------------------------
// Evaluation.

void FRideAnimator::EvaluateFree(float Dt, TArray<FTransform>& Bones)
{
    if (!HasRig())
    {
        Bones.Reset();
        return;
    }
    FRideAnimLayers Layers = bOverride ? Override : Last;
    const UAnimSequence* Key = Layers.Main();
    float Inertialize = bCutNext ? 0.f : PendingBlend;
    if (Inertialize <= 0 && !bCutNext && !bFirst && Key != LastKey && bOverride) Inertialize = OverrideBlend;
    PendingBlend = 0; bCutNext = false;
    Run(Layers, Inertialize, Dt);
    LastKey = Key;
    const TArray<FTransform>& Pose = Mesh->GetComponentSpaceTransforms();
    Bones = Pose.Num() == Names.Num() ? Pose : Reference;
    bFirst = false;
}
