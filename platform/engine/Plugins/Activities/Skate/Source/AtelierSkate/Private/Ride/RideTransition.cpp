// USkateComponent getting on and off the board with the Ride backend (RIDE.md, "Transitions"): one continuous
// character. The actor is never moved to a new place: the capsule changes about its centre and settles onto the floor,
// the mesh keeps its world place across each switch and eases back onto the capsule, the pose switch is a standard
// inertialization (FAnimNode_SkateRider), the speed carries over both ways (the excess as a root motion source), and
// the board dissolves in and out rather than popping.
#include "RideTransition.h"
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideSession.h"
#include "RidePhysicalRider.h"
#include "RideTuning.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/RootMotionSource.h"
#include "Materials/MaterialInstanceDynamic.h"

namespace
{
    // The riding capsule (SkateComponent.cpp): the board carries the body, the capsule only holds the camera.
    constexpr float RidingRadius = 22.f, RidingHalf = 55.f;
    // Stepping off settles the standing capsule on a floor up to this far above or below where its centre was.
    constexpr float SettleUp = 25.f, SettleDown = 60.f;
    // Where CharacterMovement keeps a walking capsule above its floor (between MIN_FLOOR_DIST and MAX_FLOOR_DIST).
    constexpr float FloorGap = 2.15f;
    // The loose board's box sits this far below its deck (RidePhysicalRider.cpp), at board scale 1.
    constexpr float LooseBoardDrop = 4.f;
    const FName MomentumName(TEXT("SkateMomentum"));
    const FName DissolveParameter(TEXT("Dissolve"));
}

FRideTransition& USkateComponent::Transit()
{
    if (!Transition) Transition = MakeShared<FRideTransition>();
    return *Transition;
}

bool USkateComponent::WantsGetUpOnFoot() const { return Transition && Transition->bGetUpOnFoot; }

// ---------------------------------------------------------------------------------------------------------------
// Getting on.

bool USkateComponent::RideMount()
{
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (!M || !Capsule || !Mesh || !M->IsMovingOnGround() || Rider->bIsCrouched) return false;
    FRideTransition& T = Transit();
    const FRideTuning& Tune = FRideTuning::Get();
    RiderApi->PrepareToSkate();
    StopMomentum();
    // The on-foot body to return to, without the offset a recent dismount may still be easing away.
    SavedRadius = Capsule->GetUnscaledCapsuleRadius(); SavedHalf = Capsule->GetUnscaledCapsuleHalfHeight();
    SavedMeshLocation = Mesh->GetRelativeLocation() - T.MeshOffset; SavedMeshRotation = Mesh->GetRelativeRotation().Quaternion();
    SavedStep = M->MaxStepHeight;
    T.MeshSettleTime = -1.f;
    // The board starts under the feet along the way the character is moving, at its speed.
    Pos = Rider->GetActorLocation() - FVector(0, 0, Capsule->GetScaledCapsuleHalfHeight() + M->CurrentFloor.FloorDist);
    const FVector Normal = M->CurrentFloor.HitResult.bBlockingHit ? FVector(M->CurrentFloor.HitResult.ImpactNormal) : FVector::UpVector;
    Rot = AlignUp(FRotator(0, Rider->GetActorRotation().Yaw, 0).Quaternion(), Normal, 1.f);
    Vel = FVector::VectorPlaneProject(M->Velocity, Normal);
    if (Vel.SizeSquared() > FMath::Square(30.f)) Rot = FRotationMatrix::MakeFromXZ(Vel.GetSafeNormal(), Normal).ToQuat();
    const FVector MeshWorld = (Mesh->GetRelativeTransform() * Rider->GetActorTransform()).GetLocation();
    bRideBody = true;
    ResetInput(); ShownCombo.Reset(); ComboFade = 0;
    Mode = ESkateMode::Ground;
    // A board left lying elsewhere goes; this one dissolves in under the feet. The board is placed in the world
    // from now on, so it can stay behind when the rider leaves it.
    if (T.Board == ERideBoard::World) { DropLyingBoard(); T.Shown = 0.f; }
    T.Board = ERideBoard::Ride; T.bGetUpOnFoot = false;
    if (!BoardRoot->IsUsingAbsoluteLocation()) { const FTransform Board = BoardRoot->GetComponentTransform(); BoardRoot->SetAbsolute(true, true, true); BoardRoot->SetWorldTransform(Board); }
    if (!StartRetailRuntime()) { StowImmediately(); return false; }
    Capsule->SetCapsuleSize(RidingRadius, RidingHalf);      // about its centre: nothing moves
    M->SetMovementMode(MOVE_Custom, MovementMode);
    // The actor stays where it is: the body's height above the session's root is measured rather than assumed. It
    // turns to the board as the first ride frame would; the mesh keeps its world place over that turn (riding, the
    // pose is anchored on the board, so the offset only matters to the blend into it).
    BodyLift = Rider->GetActorLocation().Z - Ride->Root.GetLocation().Z;
    Rider->SetActorLocationAndRotation(Ride->Root.GetLocation() + FVector(0, 0, BodyLift), Ride->Root.GetRotation(), false, nullptr, ETeleportType::None);
    SetMeshOffset(Rider->GetActorTransform().InverseTransformPosition(MeshWorld) - SavedMeshLocation);
    RequestPoseBlend(Tune.MountBlend);
    ShowBoard(1.f, false);
    return true;
}

// ---------------------------------------------------------------------------------------------------------------
// Getting off.

bool USkateComponent::RideDismount()
{
    FRideTransition& T = Transit();
    // During a bail the button asks to get up on foot: the physical rider reads WantsGetUpOnFoot when the body settles.
    const bool bDown = Mode == ESkateMode::Bail || (Ride && (Ride->IsBailing() || Ride->GetMode() == ERideState::GetUp)) ||
        (PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
    if (bDown) { T.bGetUpOnFoot = true; return true; }
    if (Mode != ESkateMode::Ground) return false;           // off from the ground only
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FRideTuning& Tune = FRideTuning::Get();
    const FVector MeshWorld = (Mesh->GetRelativeTransform() * Rider->GetActorTransform()).GetLocation();
    const FVector Carried = Vel;
    // From this frame the pose is the character's own, blended from the riding pose.
    SuspendRetailRuntime();
    RequestPoseBlend(Tune.DismountBlend);
    ShownCombo.Reset(); ComboFade = 0;
    Mode = ESkateMode::Off;
    bManual = bPowerslide = bPushing = bBraking = false;
    for (int32 I = 0; I < Loops.Num(); ++I) { if (Loops[I]) Loops[I]->Stop(); LoopVolume[I] = 0.f; }
    ++Serial;
    // Standing: the capsule grows about its centre, turns upright facing the board's way and settles onto the floor
    // under it when there is one close by; otherwise the character falls from where it is.
    Capsule->SetCapsuleSize(SavedRadius, SavedHalf);
    M->MaxStepHeight = SavedStep;
    const FVector Centre = Rider->GetActorLocation();
    FVector Stand = Centre;
    bool bFloor = false;
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideDismount), false, Rider);
        FCollisionResponseParams Response;
        Capsule->InitSweepCollisionParams(Params, Response);
        const FCollisionShape Shape = Capsule->GetCollisionShape();
        for (const float Up : {SettleUp, 0.f})
        {
            FHitResult Hit;
            if (!GetWorld()->SweepSingleByChannel(Hit, Centre + FVector(0, 0, Up), Centre - FVector(0, 0, SettleDown), FQuat::Identity,
                Capsule->GetCollisionObjectType(), Shape, Params, Response)) break;
            if (Hit.bStartPenetrating) continue;              // a ceiling close above: try again from the centre
            if (M->IsWalkable(Hit)) { Stand = Hit.Location + FVector(0, 0, FloorGap); bFloor = true; }
            break;
        }
    }
    Rider->SetActorLocationAndRotation(Stand, FRotator(0, Rider->GetActorRotation().Yaw, 0), false, nullptr, ETeleportType::None);
    M->SetMovementMode(bFloor ? MOVE_Walking : MOVE_Falling);
    // The character takes the speed it can run at; the rest carries on as momentum that fades.
    const FVector Flat(Carried.X, Carried.Y, 0.f);
    const FVector Own = Flat.GetClampedToMaxSize(M->GetMaxSpeed());
    M->Velocity = bFloor ? Own : FVector(Own.X, Own.Y, Carried.Z);
    StartMomentum(Flat - Own);
    // The body keeps its world place while the capsule moved under it, then eases back onto it.
    SetMeshOffset(Rider->GetActorTransform().InverseTransformPosition(MeshWorld) - SavedMeshLocation);
    T.MeshOffsetStart = T.MeshOffset; T.MeshSettleTime = 0.f;
    // The board (not carried yet): it stays where it is and dissolves. A board already lying (a bail) stays.
    if (T.Board == ERideBoard::Ride) { T.Board = ERideBoard::World; T.BoardTime = 0.f; ShowBoard(0.f, false); }
    T.bGetUpOnFoot = false;
    UE_LOG(LogTemp, Display, TEXT("SKATE ride dismount at %.0f cm/s (%.0f carried as momentum), %s, settled %.1f cm"),
        Flat.Size(), (Flat - Own).Size(), bFloor ? TEXT("walking") : TEXT("falling"), Stand.Z - Centre.Z);
    return true;
}

void USkateComponent::BeginGetUpOnFoot(const FVector& Ground, float Yaw, bool bFaceUp)
{
    FRideTransition& T = Transit();
    T.bGetUpOnFoot = true;
    // The board stays where it came to rest, a body of its own.
    if (PhysicalRider)
        if (UBoxComponent* Loose = PhysicalRider->TakeLooseBoard())
        {
            if (T.Board == ERideBoard::World) DropLyingBoard();
            T.LooseBoard = Loose; T.Board = ERideBoard::World; T.BoardTime = 0.f;
            ShowBoard(1.f, true);
        }
    // Until the on-foot recovery clips play off the board, the session's get-up stands the rider up where the body
    // lies (the pose rising out of the fallen body's snapshot, TickTransition) and the rider steps off once up.
    if (Ride && Ride->IsBailing()) Ride->GetUp(Ground, Yaw);
}

// ---------------------------------------------------------------------------------------------------------------
// Every frame, after the ride's step and before the mesh animates.

void USkateComponent::TickTransition(float Dt)
{
    if (!Transition || !Rider) return;
    FRideTransition& T = *Transition;
    const FRideTuning& Tune = FRideTuning::Get();

    // A bail left on foot: the pose rises out of the fallen body, and the rider steps off once up. Without the
    // physical rider (or after it gave up) the session gets up by itself and the rider steps off then.
    if (T.bGetUpOnFoot)
    {
        if (Mode == ESkateMode::Off) T.bGetUpOnFoot = false;
        else
        {
            if (PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpExit() == ERideGetUpExit::OnFoot && !RetailPose.IsEmpty())
                PhysicalRider->BlendFromSnapshot(RetailPose, PhysicalRider->GetGetUpAlpha());
            const bool bUp = Ride && Mode == ESkateMode::Ground && !Ride->IsBailing() && Ride->GetMode() != ERideState::GetUp &&
                !(PhysicalRider && (PhysicalRider->IsBailing() || PhysicalRider->IsGettingUp()));
            if (bUp) RideDismount();
        }
    }

    // A board lying in the world follows its own body, and dissolves once the rider has been out of reach for a while.
    if (T.Board == ERideBoard::World)
    {
        if (const UPrimitiveComponent* Loose = T.LooseBoard.Get())
        {
            const FTransform Body = Loose->GetComponentTransform();
            const float Scale = BoardScale();
            BoardRoot->SetWorldTransform(FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * Scale, FVector(Scale)));
        }
        const bool bNear = FVector::Dist(BoardRoot->GetComponentLocation(), Rider->GetActorLocation()) < Tune.BoardReach;
        T.BoardTime = bNear ? 0.f : T.BoardTime + Dt;
        if (T.BoardTime > Tune.BoardLyingTime && T.ShownTarget > 0.f) ShowBoard(0.f, false);
    }

    // The dissolve.
    if (T.Shown != T.ShownTarget)
    {
        T.Shown = FMath::FInterpConstantTo(T.Shown, T.ShownTarget, Dt, 1.f / FMath::Max(.01f, Tune.BoardDissolveTime));
        ApplyBoardShown();
        if (T.Shown <= 0.f && T.Board == ERideBoard::World) DropLyingBoard();
    }

    // On foot, the body eases back onto the capsule that moved under it.
    if (T.MeshSettleTime >= 0.f)
    {
        T.MeshSettleTime += Dt;
        const float A = FMath::SmoothStep(0.f, 1.f, T.MeshSettleTime / FMath::Max(.01f, Tune.MeshSettle));
        SetMeshOffset(T.MeshOffsetStart * (1.f - A));
        if (A >= 1.f) T.MeshSettleTime = -1.f;
    }

    // The speed carried off the board fades, slowly while the stick keeps the way, fast without it. It follows the
    // character's travel, so turning takes it along.
    if (T.MomentumId)
    {
        UCharacterMovementComponent* M = Movement();
        const TSharedPtr<FRootMotionSource> Source = M ? M->GetRootMotionSourceByID(T.MomentumId) : nullptr;
        if (!Source.IsValid() || Source->GetScriptStruct() != FRootMotionSource_ConstantForce::StaticStruct() || Mode != ESkateMode::Off) StopMomentum();
        else
        {
            const FVector Travel = M->Velocity.GetSafeNormal2D();
            if (!Travel.IsNearlyZero()) T.MomentumDirection = Travel;
            const bool bHeld = FVector::DotProduct(M->GetCurrentAcceleration().GetSafeNormal2D(), T.MomentumDirection) > .5f;
            T.Momentum = FMath::Max(0.f, T.Momentum - (bHeld ? Tune.MomentumDecay : Tune.MomentumBrake) * Dt);
            if (T.Momentum <= 1.f) StopMomentum();
            else static_cast<FRootMotionSource_ConstantForce*>(Source.Get())->Force = T.MomentumDirection * T.Momentum;
        }
    }
}

void USkateComponent::ResetTransition()
{
    if (!Transition) return;
    FRideTransition& T = *Transition;
    StopMomentum();
    DropLyingBoard();
    T.Board = ERideBoard::Away; T.bGetUpOnFoot = false;
    T.Shown = T.ShownTarget = 0.f; ApplyBoardShown();
    T.MeshSettleTime = -1.f; SetMeshOffset(FVector::ZeroVector);
}

// ---------------------------------------------------------------------------------------------------------------
// The body and the speed.

void USkateComponent::SetMeshOffset(const FVector& Offset)
{
    FRideTransition& T = Transit();
    // Applied as a change, so whatever else places the mesh (a crouch) keeps its part.
    USkeletalMeshComponent* Mesh = Rider ? Rider->GetMesh() : nullptr;
    if (Mesh && Mesh->GetAttachParent() == Rider->GetRootComponent() && !Offset.Equals(T.MeshOffset))
        Mesh->SetRelativeLocation(Mesh->GetRelativeLocation() + Offset - T.MeshOffset);
    T.MeshOffset = Offset;
}

void USkateComponent::StartMomentum(const FVector& Excess)
{
    StopMomentum();
    UCharacterMovementComponent* M = Movement();
    if (!M || Excess.Size() < 10.f) return;
    FRideTransition& T = Transit();
    // Additive: CharacterMovement steers and brakes the character's own velocity as usual, and adds this on top.
    TSharedPtr<FRootMotionSource_ConstantForce> Source = MakeShared<FRootMotionSource_ConstantForce>();
    Source->InstanceName = MomentumName;
    Source->AccumulateMode = ERootMotionAccumulateMode::Additive;
    Source->Priority = 5;
    Source->Force = Excess;
    Source->Duration = -1.f;                                 // until the momentum is spent (TickTransition)
    Source->Settings.SetFlag(ERootMotionSourceSettingsFlags::IgnoreZAccumulate);
    T.MomentumId = M->ApplyRootMotionSource(Source);
    T.Momentum = Excess.Size(); T.MomentumDirection = Excess.GetSafeNormal();
}

void USkateComponent::StopMomentum()
{
    if (!Transition) return;
    FRideTransition& T = *Transition;
    if (T.MomentumId) if (UCharacterMovementComponent* M = Movement()) M->RemoveRootMotionSourceByID(T.MomentumId);
    T.MomentumId = 0; T.Momentum = 0.f;
}

// ---------------------------------------------------------------------------------------------------------------
// The board's dissolve: a masked material whose Dissolve parameter eats the parts away through a noise
// (USkateSettings::BoardDissolveMaterial). Whole or gone, the parts wear their own materials again.

void USkateComponent::ShowBoard(float Target, bool bInstant)
{
    FRideTransition& T = Transit();
    T.ShownTarget = Target;
    if (bInstant || FRideTuning::Get().BoardDissolveTime <= 0.f) T.Shown = Target;
    ApplyBoardShown();
}

void USkateComponent::ApplyBoardShown()
{
    FRideTransition& T = Transit();
    const bool bPartial = T.Shown > 0.f && T.Shown < 1.f;
    if (bPartial && !BoardFade)
    {
        const FSoftObjectPath& Path = GetDefault<USkateSettings>()->BoardDissolveMaterial;
        if (UMaterialInterface* Base = Path.IsNull() ? nullptr : Cast<UMaterialInterface>(Path.TryLoad()))
            BoardFade = UMaterialInstanceDynamic::Create(Base, this);
    }
    // Without the material the board shows whole until it is gone.
    const bool bFade = bPartial && BoardFade;
    if (bFade != T.bFadeMaterial)
    {
        TArray<UStaticMeshComponent*> Parts{Deck};
        for (UStaticMeshComponent* Part : Trucks) Parts.Add(Part);
        for (UStaticMeshComponent* Part : Wheels) Parts.Add(Part);
        for (UStaticMeshComponent* Part : Parts)
            if (Part) for (int32 I = 0; I < Part->GetNumMaterials(); ++I) Part->SetMaterial(I, bFade ? BoardFade.Get() : nullptr);
        T.bFadeMaterial = bFade;
    }
    if (bFade) BoardFade->SetScalarParameterValue(DissolveParameter, 1.f - T.Shown);
    BoardRoot->SetVisibility(T.Shown > 0.f, true);
}

void USkateComponent::DropLyingBoard()
{
    FRideTransition& T = Transit();
    if (UPrimitiveComponent* Loose = T.LooseBoard.Get()) Loose->DestroyComponent();
    T.LooseBoard.Reset();
    if (T.Board == ERideBoard::World) T.Board = ERideBoard::Away;
}

FString USkateComponent::DescribeTransition() const
{
    if (!Transition || !Rider) return FString();
    const FRideTransition& T = *Transition;
    static const TCHAR* Places[] = {TEXT("away"), TEXT("ride"), TEXT("hand"), TEXT("world")};
    FVector Hip = FVector::ZeroVector;
    const USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const FName Pelvis = RiderApi ? RiderApi->GetSkateBone(TEXT("pelvis")) : NAME_None;
    if (Mesh && !Pelvis.IsNone() && Mesh->GetBoneIndex(Pelvis) != INDEX_NONE) Hip = Mesh->GetBoneLocation(Pelvis);
    const FVector Board = BoardRoot ? BoardRoot->GetComponentLocation() : FVector::ZeroVector;
    const UCharacterMovementComponent* M = Movement();
    const FVector V = M ? M->Velocity : FVector::ZeroVector;
    return FString::Printf(TEXT(" board=%s shown=%.2f vis=%d hip=%.1f,%.1f,%.1f deck=%.1f,%.1f,%.1f vel=%.0f,%.0f,%.0f offset=%.1f,%.1f,%.1f momentum=%.0f getup_on_foot=%d"),
        Places[uint8(T.Board)], T.Shown, BoardRoot && BoardRoot->IsVisible() ? 1 : 0, Hip.X, Hip.Y, Hip.Z, Board.X, Board.Y, Board.Z, V.X, V.Y, V.Z,
        T.MeshOffset.X, T.MeshOffset.Y, T.MeshOffset.Z, T.Momentum, T.bGetUpOnFoot ? 1 : 0);
}
