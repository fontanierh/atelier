#include "SkateComponent.h"
#include "Ride/RideTransition.h"
#include "GameFramework/Character.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"

void USkateComponent::InitializeNetworkProxy(ACharacter* Character)
{
    // Role can arrive before possession. Initialize promotes the local owner before any simulation.
    bNetworkProxy = true;
    Initialize(Character);
    SetComponentTickEnabled(false);
    if (Loops.IsEmpty() && GetWorld()->GetNetMode() != NM_DedicatedServer) LoadSounds();
}

bool USkateComponent::ApplyNetworkPose(const TArray<FTransform>& ComponentPose, const FTransform& MeshWorld)
{
    if (!bNetworkProxy || !Rider || !Rider->GetMesh()->GetSkeletalMeshAsset()) return false;
    const FReferenceSkeleton& Skeleton = Rider->GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
    if (ComponentPose.Num() != Skeleton.GetNum()) return false;
    RiderPose.SetNum(ComponentPose.Num());
    for (int32 I = 0; I < ComponentPose.Num(); ++I)
    {
        const int32 Parent = Skeleton.GetParentIndex(I);
        RiderPose[I] = Parent == INDEX_NONE ? ComponentPose[I] : ComponentPose[I].GetRelativeTransform(ComponentPose[Parent]);
        RiderPose[I].NormalizeRotation();
    }
    PoseBlendTime = 0.f;
    auto* Mesh = Rider->GetMesh();
    Mesh->SetAbsolute(true, true, true);
    Mesh->SetWorldTransform(MeshWorld);
    Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    return true;
}

void USkateComponent::ClearNetworkPose()
{
    if (!bNetworkProxy || !Rider || RiderPose.IsEmpty()) return;
    RiderPose.Reset();
    ++PoseBlendSerial; PoseBlendTime = .12f;
    Rider->GetMesh()->SetAbsolute(false, false, false);
    Rider->GetMesh()->SetRelativeLocationAndRotation(Rider->GetBaseTranslationOffset(), Rider->GetBaseRotationOffset());
}

float USkateComponent::GetBoardShown() const
{
    return Transition ? Transition->Shown : BoardRoot && BoardRoot->IsVisible() ? 1.f : 0.f;
}

void USkateComponent::ApplyNetworkBoard(const FTransform& DeckWorld, float Shown)
{
    if (!bNetworkProxy || !BoardRoot || !Deck) return;
    BoardRoot->SetAbsolute(true, true, true);
    BoardRoot->SetWorldTransform(DeckWorld);
    Deck->SetRelativeTransform(FTransform::Identity);
    ShowBoard(FMath::Clamp(Shown, 0.f, 1.f), true);
}

void USkateComponent::ApplyNetworkAudio(uint8 InMode, uint8 InSurface, uint8 Flags, const FVector& Velocity, float Dt)
{
    if (!bNetworkProxy || !BoardRoot || GetWorld()->GetNetMode() == NM_DedicatedServer) return;
    const ESkateMode Next = InMode <= uint8(ESkateMode::Bail) ? ESkateMode(InMode) : ESkateMode::Off;
    Surface = InSurface <= uint8(ESkateSurface::Sand) ? ESkateSurface(InSurface) : ESkateSurface::None;
    if (Next != NetworkAudioMode)
    {
        if (Next == ESkateMode::Air && NetworkAudioMode == ESkateMode::Ground) PlaySurfaceCue(TEXT("pop"), .7f);
        else if (Next == ESkateMode::Ground && NetworkAudioMode == ESkateMode::Air) PlaySurfaceCue(TEXT("land"), .8f);
        else if (Next == ESkateMode::Bail) PlayCue(TEXT("clatter"), .7f);
        NetworkAudioMode = Next;
    }
    // Sound state cannot turn a proxy into an active rider or trigger a simulation lifecycle transition.
    TGuardValue<ESkateMode> SoundMode(Mode, Next);
    Vel = Velocity; RailSpeed = Velocity.Size(); SlideAngle = (Flags & 1) ? 82.f : 0.f;
    bPowerslide = (Flags & 1) != 0; bBraking = (Flags & 2) != 0; bSlide = (Flags & 4) != 0;
    UpdateAudio(Dt);
}

void USkateComponent::SilenceNetworkAudio(float Dt)
{
    if (!bNetworkProxy) return;
    // Keep the last heard mode, so resuming a delayed bail cannot replay its clatter.
    TGuardValue<ESkateMode> SoundMode(Mode, ESkateMode::Off);
    UpdateAudio(Dt);
}
