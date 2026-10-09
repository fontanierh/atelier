#pragma once
// Helpers shared by the RideTransition*.cpp files (one source, split by section).
#include "RideTransition.h"
#include "SkateComponent.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "RideClipPlayer.h"
#include "RideAnimator.h"
#include "RideAnimInstance.h"
#include "RidePhysicalRider.h"
#include "RideTuning.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimSequence.h"
#include "Components/AudioComponent.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/SphereComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/ProjectileMovementComponent.h"
#include "GameFramework/RootMotionSource.h"
#include "HAL/IConsoleManager.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/OverlapResult.h"
#include "PhysicsEngine/BodyInstance.h"

namespace RideTransitionDetail
{
    extern TAutoConsoleVariable<int32> CVarRideTrace;
    // The riding capsule (SkateComponent.cpp): the board carries the body, the capsule only holds the camera.
    constexpr float RidingRadius = 22.f, RidingHalf = 55.f;
    // Stepping off settles the standing capsule on a floor up to this far above or below where its centre was.
    constexpr float SettleUp = 25.f, SettleDown = 60.f;
    // Where CharacterMovement keeps a walking capsule above its floor (between MIN_FLOOR_DIST and MAX_FLOOR_DIST).
    constexpr float FloorGap = 2.15f;
    // The loose board's box sits this far below its deck (RidePhysicalRider.cpp), at board scale 1.
    constexpr float LooseBoardDrop = 4.f;
    // The deck's pivot above the ground contact (SkateRuntime.cpp).
    constexpr float DeckPivot = 9.05f;
    // The mount clip's gait by the character's speed (cm/s): between the carry cycles' own speeds (stand 0, walk
    // ~170, run ~540, sprint ~910), the sprint's from just under the character's own sprint (637), which it reaches.
    constexpr float WalkMount = 80.f, RunMount = 350.f, SprintMount = 620.f;
    // The ride starts on the floor under its deck: a sweep down the deck's normal from this far above finds it (cm).
    constexpr float HandOffReach = 30.f;
    // An air kick-out stands on a floor only when coming down onto it within this time (s).
    constexpr float KickFloorTime = .1f;
    // Stepping off: the fast clip above FastDismount; the run-out above RunDismount or with the stick held; otherwise
    // the step off to a stand.
    constexpr float FastDismount = 600.f, RunDismount = 150.f;
    // The clips' board is held above this height over their trajectory (cm), and on the ground below it.
    constexpr float HeldHeight = 15.f;
    const FName MomentumName(TEXT("SkateMomentum"));
    const FName DriveName(TEXT("SkateDrive"));
    const FName DissolveParameter(TEXT("Dissolve"));
    const FName DeckBone(TEXT("SKATEBOARD_ROOT"));
    const FName CadenceCurve(TEXT("CADENCEENDPERCENT"));
    const FName Trajectory(TEXT("TRAJECTORY"));
    // In the air: the board thrown under the feet finishes in the air above this height (the ride starts airborne),
    // and below it waits for the landing. A jump with less time left than AirChain holds its last frame.
    constexpr float AirMountHeight = 70.f, AirChain = .25f;
    // A take-off this fast upward is a jump (slower is a step off a ledge); a landing this fast or after this long in
    // the air is a big one, and this far below or above the take-off a landing down or up.
    constexpr float JumpSpeed = 150.f, BigFall = -700.f, BigAirTime = .9f, LandDown = -60.f, LandUp = 30.f;
    // The board-carry locomotion, slowest first; the mount clips come from the same gaits at four phases of the step.
    const TCHAR* const CycleNames[4] = {TEXT("BR_STAND_0_CYC"), TEXT("BR_WALK_FWD_CYC"), TEXT("BR_RUN_FWD_CYC"), TEXT("BR_SPRINT_FWD_CYC")};
    const TCHAR* const Gaits[4] = {TEXT("STAND"), TEXT("WALK"), TEXT("RUN"), TEXT("SPRINT")};
    // The drive follows the clip's travel averaged over this long either side of the time shown (s): the simulation
    // trajectories step unevenly from frame to frame.
    constexpr float DriveWindow = .1f;
    // A trajectory held in the world (a step onto a lying board, a get-up) pulls the capsule after it at this rate
    // (1/s), up to AnchorSpeed (cm/s).
    constexpr float AnchorGain = 5.f, AnchorSpeed = 350.f;
    // A kicked or run-out board's launch is its motion over this long (s) at least.
    constexpr float KickWindow = .05f;
    // A board the clip rolls away or kicks off is swept from frame to frame (FitDeck); a clip board farther than this
    // from its last frame (cm at board scale 1) was placed, not moved: it is swept only when its place is not free.
    constexpr float ClipBoardJump = 60.f;
    // A lying board can be stepped onto when the character is this close to it (cm), slower than RunMount, and the board
    // lies wheels down (its up this close to vertical) and still.
    constexpr float StepOnReach = 130.f, StepOnUp = .85f, StepOnBlend = .35f;
    // A kicked board: the sphere it flies as (cm at board scale 1), how it bounces, and how long it may fly before it
    // settles wherever it is. It settles flat over BoardSettle (s); upside down its deck lies this far above the ground.
    constexpr float FlightRadius = 5.f, FlightBounce = .3f, FlightFriction = .5f, FlightStop = 60.f, FlightLimit = 4.f;
    // On the ground it slows by this much each second (cm/s).
    constexpr float FlightRoll = 250.f;
    // Upside down the board rests on its kicks' tips (DeckKickTop over the pivot).
    constexpr float BoardSettle = .2f, UpsideDownDeck = 4.3f;
    // The kick: at least this fast away from the rider (cm/s).
    constexpr float KickSpeed = 250.f;
    // The loose deck's box (cm at board scale 1) holds the simulation's whole board: 45.6 from the pivot to the nose and the
    // tail, 12 to each side, from the wheels' plane (DeckPivot under the pivot) to the kicks' top (DeckKickTop over
    // it). It is checked this much smaller all round, so the ground the board rests on, wheels or kicks down, is not
    // inside it; out of what it starts in it moves at most DeckFitPush.
    constexpr float DeckHalfLength = 45.6f, DeckHalfWidth = 12.f, DeckKickTop = 4.3f, DeckFitInset = 1.5f, DeckFitPush = 45.f;
    // A flying deck stopped by the ground turns toward lying along it at DeckLieRate (1/s: about .3 of the way each
    // 60 Hz frame); one stopped by anything loses its spin at ContactSpinDamp (1/s: about half each frame).
    constexpr float DeckLieRate = 21.f, ContactSpinDamp = 42.f;
    // A get-up on foot waits at most this long (s) for the physical rider to hand its bodies to the animation.
    constexpr float RecoverWait = .3f;
    // The run-outs (RUNOUT_<way>_<HI|LO>_<size><n>_TO_RUN_FWD) by the way the board was going and the bail's energy:
    // small, medium and big variants of each.
    struct FRunOutWay { const TCHAR* Way; const TCHAR* Sizes[3][3]; };
    const FRunOutWay RunOutWays[4] = {
        {TEXT("FWD"), {{TEXT("S1"), TEXT("S2")}, {TEXT("M1"), TEXT("M2"), TEXT("M3")}, {TEXT("B1")}}},
        {TEXT("BWD"), {{TEXT("S2"), TEXT("S3")}, {TEXT("M1"), TEXT("M3")}, {TEXT("B1"), TEXT("B2")}}},
        {TEXT("FF"), {{TEXT("S2")}, {TEXT("M1"), TEXT("M2")}, {}}},
        {TEXT("BF"), {{TEXT("S2")}, {TEXT("M1"), TEXT("M2")}, {TEXT("B1")}}},
    };
    // The get-ups on foot, matched to how the body lies.
    const TCHAR* const Recoveries[] = {TEXT("W_RECOVERY_ONBACKFACE_N_0_N"), TEXT("W_RECOVERY_ONBACKLGUT_N_0_N"),
        TEXT("W_RECOVERY_ONBACKLSPRAWL_N_0_N"), TEXT("W_RECOVERY_ONBACKRFACE_N_0_N"), TEXT("W_RECOVERY_ONBACKRSPRAWL_N_0_N"),
        TEXT("W_RECOVERY_ONBACKSPRAWL_N_0_N"), TEXT("W_RECOVERY_ONFRONT_N_0_N"), TEXT("W_RECOVERY_ONLEFT_N_0_N"),
        TEXT("W_RECOVERY_ONRIGHTHEAD_N_0_N"), TEXT("W_RECOVERY_ONRIGHT_N_0_N")};

    inline float Length(const UAnimSequence* Clip) { return Clip ? Clip->GetPlayLength() : 0.f; }

    /** The clip's travel velocity about Time (cm/s, level, in its trajectory's frame). */
    inline FVector ClipVelocity(const UAnimSequence* Clip, float Time)
    {
        const float From = FMath::Max(0.f, Time - DriveWindow), To = FMath::Min(Length(Clip), Time + DriveWindow);
        if (To <= From) return FVector::ZeroVector;
        FVector Move = FRideAnimator::RootMotion(Clip, From, To).GetTranslation();
        Move.Z = 0.;
        return Move / (To - From);
    }

    /** The clip's horizontal speed over [From, To] (cm/s). */
    inline float ClipSpeed(const UAnimSequence* Clip, float From, float To)
    {
        From = FMath::Max(0.f, From); To = FMath::Min(Length(Clip), To);
        return To > From ? float(FRideAnimator::RootMotion(Clip, From, To).GetTranslation().Size2D()) / (To - From) : 0.f;
    }

    /** The first time (at 30 Hz) the clip's board is above HeldHeight (bAbove) or below it, or Default. */
    inline float BoardCrossing(const UAnimSequence* Clip, bool bAbove, float Default)
    {
        const float End = Length(Clip);
        for (float Time = 0.f; Time <= End; Time += 1.f / 30.f)
        {
            const float Z = FRideAnimator::Track(Clip, DeckBone, Time).GetLocation().Z;
            if (bAbove ? Z > HeldHeight : Z < HeldHeight) return Time;
        }
        return Default;
    }

    /** A bone in the clip's trajectory space (the parent chain composed up to the trajectory). */
    inline FTransform ClipBoneTransform(const UAnimSequence* Clip, FName Bone, float Time)
    {
        const USkeleton* Skeleton = Clip ? Clip->GetSkeleton() : nullptr;
        if (!Skeleton) return FTransform::Identity;
        const FReferenceSkeleton& Ref = Skeleton->GetReferenceSkeleton();
        FTransform Space = FTransform::Identity;
        for (int32 I = Ref.FindBoneIndex(Bone); I != INDEX_NONE && Ref.GetBoneName(I) != Trajectory; I = Ref.GetParentIndex(I))
            Space = Space * FRideAnimator::Track(Clip, Ref.GetBoneName(I), Time);
        return Space;
    }

    inline FVector ClipBone(const UAnimSequence* Clip, FName Bone, float Time) { return ClipBoneTransform(Clip, Bone, Time).GetLocation(); }

    /** The clip trajectory's own yaw at Time (degrees). */
    inline float ClipYaw(const UAnimSequence* Clip, float Time) { return float(FRideAnimator::Track(Clip, Trajectory, Time).GetRotation().Rotator().Yaw); }

    /** A direction's yaw in the clip (degrees) as seen in the world, the clip's trajectory facing Yaw. */
    inline float ClipYawToWorld(float Local, bool bMirror, float Yaw) { return Yaw + (bMirror ? -Local : Local); }

    /** The yaw of the clip's board (its nose) in its trajectory space at Time. */
    inline float ClipDeckYaw(const UAnimSequence* Clip, float Time)
    {
        return float(ClipBoneTransform(Clip, DeckBone, Time).GetRotation().GetForwardVector().Rotation().Yaw);
    }

    /** A bone of a published pose (parent-relative, the mesh's bone order) in the world. */
    inline bool PoseBoneTransform(const USkeletalMeshComponent* Mesh, const FTransform& MeshWorld, const TArray<FTransform>& Pose, FName Bone, FTransform& Out)
    {
        const USkeletalMesh* Asset = Mesh ? Mesh->GetSkeletalMeshAsset() : nullptr;
        if (!Asset || Bone.IsNone()) return false;
        const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
        int32 I = Ref.FindBoneIndex(Bone);
        if (I == INDEX_NONE || Pose.Num() != Ref.GetNum()) return false;
        FTransform Space = FTransform::Identity;
        for (; I != INDEX_NONE; I = Ref.GetParentIndex(I)) Space = Space * Pose[I];
        Out = Space * MeshWorld;
        return true;
    }

    inline bool PoseBoneWorld(const USkeletalMeshComponent* Mesh, const FTransform& MeshWorld, const TArray<FTransform>& Pose, FName Bone, FVector& Out)
    {
        FTransform World;
        if (!PoseBoneTransform(Mesh, MeshWorld, Pose, Bone, World)) return false;
        Out = World.GetLocation();
        return true;
    }

    /** The way a body faces (degrees): level, across its thighs. */
    inline float FacingYaw(const FVector& Left, const FVector& Right) { return float(FVector::CrossProduct(Right - Left, FVector::UpVector).Rotation().Yaw); }

    /** The way the player is pushing the move stick or keys, in the world (zero without). */
    inline FVector MoveWish(const ACharacter* Rider)
    {
        const APlayerController* PC = Rider ? Cast<APlayerController>(Rider->GetController()) : nullptr;
        if (!PC) return FVector::ZeroVector;
        auto Down = [&](const FKey& Key) { return PC->IsInputKeyDown(Key) ? 1.f : 0.f; };
        const float X = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX) + Down(EKeys::D) - Down(EKeys::A);
        const float Y = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftY) + Down(EKeys::W) - Down(EKeys::S);
        if (FVector2D(X, Y).Size() < .3f) return FVector::ZeroVector;
        return FRotator(0, PC->GetControlRotation().Yaw, 0).RotateVector(FVector(Y, X, 0.f)).GetSafeNormal();
    }

    /** What the kicked board's flight sphere collides with (as a WorldDynamic object): everything but pawns, bodies,
     *  the camera and visibility. */
    inline FCollisionResponseParams FlightResponses()
    {
        FCollisionResponseParams Responses(ECR_Block);
        for (const ECollisionChannel Channel : {ECC_Pawn, ECC_PhysicsBody, ECC_Camera, ECC_Visibility})
            Responses.CollisionResponse.SetResponse(Channel, ECR_Ignore);
        return Responses;
    }

    /** A loose deck's box (Deck: its pivot, scaled as shown): its centre and rotation, half extents in Extent. */
    inline FTransform DeckFitBox(const FTransform& Deck, FVector& Extent)
    {
        const float Scale = float(Deck.GetScale3D().X);
        const FQuat Rotation = Deck.GetRotation().GetNormalized();
        Extent = ((FVector(DeckHalfLength, DeckHalfWidth, (DeckPivot + DeckKickTop) * .5f) - FVector(DeckFitInset)) * Scale).ComponentMax(FVector(.5f));
        return FTransform(Rotation, Deck.GetLocation() + Rotation.GetUpVector() * (DeckKickTop - DeckPivot) * .5f * Scale);
    }
    /** The deck whose box is Box. */
    inline FTransform DeckOfBox(const FTransform& Box, float Scale)
    {
        const FQuat Rotation = Box.GetRotation();
        return FTransform(Rotation, Box.GetLocation() - Rotation.GetUpVector() * (DeckKickTop - DeckPivot) * .5f * Scale, FVector(Scale));
    }

    /** The way a loose deck's box leaves what it is inside: each body it overlaps (each instance of an instanced mesh)
     *  gives the whole box's own way out of it, summed, for up to four rounds, within the plane of Plane when given (a
     *  board lying on the ground slides along it). True with the push (zero when it was free) once the box is free
     *  within DeckFitPush; false when it is not. */
    inline bool LeaveInside(const UWorld& World, const FTransform& Box, const FVector& Extent, float Scale, const FCollisionQueryParams& Params, const FVector& Plane,
        FVector& Push)
    {
        const FCollisionShape Shape = FCollisionShape::MakeBox(Extent);
        const FCollisionResponseParams Responses = FlightResponses();
        Push = FVector::ZeroVector;
        for (int32 Try = 0; Try < 4; ++Try)
        {
            const FVector At = Box.GetLocation() + Push;
            TArray<FOverlapResult> Overlaps;
            World.OverlapMultiByChannel(Overlaps, At, Box.GetRotation(), ECC_WorldDynamic, Shape, Params, Responses);
            FVector Out = FVector::ZeroVector;
            bool bInside = false;
            for (const FOverlapResult& Overlap : Overlaps)
            {
                const UPrimitiveComponent* Other = Overlap.GetComponent();
                if (!Other || !Overlap.bBlockingHit) continue;
                FMTDResult Way;
                const FBodyInstance* Body = Other->GetBodyInstance(NAME_None, true, Overlap.ItemIndex);
                if (!Body || !Body->OverlapTest(At, Box.GetRotation(), Shape, &Way) || Way.Distance <= 0.f) continue;
                bInside = true;
                Out += Way.Direction * Way.Distance;
            }
            if (!bInside) return true;
            if (!Plane.IsNearlyZero()) Out = FVector::VectorPlaneProject(Out, Plane);
            if (Out.IsNearlyZero()) return false;
            Push += Out + Out.GetSafeNormal() * .2f;
            if (Push.Size() > DeckFitPush * Scale) return false;
        }
        return false;
    }

    /** FitDeck: how a loose deck moves from From (where it was last shown) to To (where its flight, its settling or its
     *  owner puts it). Its whole box is swept, turned in steps (FRideClipPlayer::SweepBox), through what the flight sphere
     *  collides with. Clear: To is free. Corrected: To is changed to where the box met a face (Normal its normal), or,
     *  when the move starts inside something, to To pushed out of it (whole box, within Plane when given) if its centre
     *  gets there without crossing anything, else to the last free pose on the way. Unresolved: no free pose; To is
     *  From. It never hands back a pose it found inside something, other than From itself. */
    enum class EDeckFit : uint8 { Clear, Corrected, Unresolved };
    inline EDeckFit FitDeck(const UWorld& World, const FTransform& From, FTransform& To, const FCollisionQueryParams& Params, FVector& Normal,
        const FVector& Plane = FVector::ZeroVector)
    {
        Normal = FVector::ZeroVector;
        const float Scale = float(To.GetScale3D().X);
        FVector Extent;
        const FTransform A = DeckFitBox(From, Extent), B = DeckFitBox(To, Extent);
        FHitResult Hit; FTransform Reached;
        if (!FRideClipPlayer::SweepBox(World, A, B, Extent, ECC_WorldDynamic, Params, FlightResponses(), Hit, &Reached)) return EDeckFit::Clear;
        Normal = Hit.Normal;
        if (!Hit.bStartPenetrating)
        {
            // Touching the face, a hair off it.
            Reached.AddToTranslation(Hit.Normal * .1f);
            To = DeckOfBox(Reached, Scale);
            return EDeckFit::Corrected;
        }
        // Inside something: out of it where the move ends, when the way there crosses nothing.
        FVector Push; FHitResult Between;
        if (LeaveInside(World, B, Extent, Scale, Params, Plane, Push) &&
            !World.LineTraceSingleByChannel(Between, A.GetLocation(), B.GetLocation() + Push, ECC_WorldDynamic, Params, FlightResponses()))
        {
            To.AddToTranslation(Push);
            if (Normal.IsNearlyZero()) Normal = Push.GetSafeNormal();
            return EDeckFit::Corrected;
        }
        // Else as far as it went free.
        if (Hit.Time > 0.f)
        {
            To = DeckOfBox(FTransform(FQuat::Slerp(A.GetRotation(), B.GetRotation(), Hit.Time).GetNormalized(),
                FMath::Lerp(A.GetLocation(), B.GetLocation(), double(Hit.Time))), Scale);
            return EDeckFit::Corrected;
        }
        To = From;
        return EDeckFit::Unresolved;
    }

    /** Whether a loose deck's box at Deck is free, its centre reached from Reach without crossing anything. */
    inline bool DeckFreeFrom(const UWorld& World, const FTransform& Deck, const FVector& Reach, const FCollisionQueryParams& Params)
    {
        FVector Extent;
        const FTransform Box = DeckFitBox(Deck, Extent);
        FHitResult Between;
        return !World.OverlapBlockingTestByChannel(Box.GetLocation(), Box.GetRotation(), ECC_WorldDynamic, FCollisionShape::MakeBox(Extent), Params,
                FlightResponses()) &&
            !World.LineTraceSingleByChannel(Between, Reach, Box.GetLocation(), ECC_WorldDynamic, Params, FlightResponses());
    }

    /** A clip's local translation in the world: the clips are authored goofy, a mirrored clip runs along -Y. */
    inline FVector ClipToWorld(FVector Local, bool bMirror, float Yaw)
    {
        if (bMirror) Local.Y = -Local.Y;
        return FRotator(0, Yaw, 0).RotateVector(Local);
    }
}
