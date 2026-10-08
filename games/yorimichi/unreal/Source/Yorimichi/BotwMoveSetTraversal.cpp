#include "BotwMoveSet.h"
#include "JapanCharacterMovement.h"
#include "JapanNetwork.h"
#include "BotwMoveSetDetail.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "WandererDefinition.h"
#include "JapanWorld.h"
#include "JapanFootsteps.h"
#include "YorimichiCombatFX.h"
#include "BotwCreature.h"
#include "JapanPreferences.h"
#include "FoxHunter.h"
#include "MegaRamp.h"
#include "SuperUltraMegaPark.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/WorldSettings.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

using namespace BotwMoveSetDetail;

// Every timing below is in clip seconds (the action timelines' frames at 30 fps), every distance in game centimetres at
// the character's scale, and BOTW's lengths (metres) and speeds (metres per 30 fps frame) are converted with that scale.

// ------------------------------------------------------------------------------------------------------- Paraglider

bool UBotwMoveSet::CanGlide() const
{
    if (!Character || Mode != EBotwMoveMode::Air || !Has(TEXT("GlideOn")) || !HasStamina() || bDown) return false;
    const FName Name = CurrentName();
    if (IsAttack(Name) || Prefixed(Name, { TEXT("Knock"), TEXT("Hit") })) return false;
    if (SinceGrounded < .15f) return false;
    FFindFloorResult Floor;
    Character->GetCharacterMovement()->FindFloor(Character->GetActorLocation(), Floor, false);
    return !(Floor.bBlockingHit && Floor.FloorDist < 40.f);
}

void UBotwMoveSet::OpenGlider()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    SetArmed(false);
    bLocked = false; bCharging = false;
    const FVector Velocity = Movement->Velocity;
    GlideYaw = Character->GetActorRotation().Yaw;
    GlideSpeed = FMath::Max(0.f, float(Velocity | FRotator(0, GlideYaw, 0).Vector()));
    GlideTurn = 0.f; GlideTime = 0.f; bGlideBrake = false;
    Mode = EBotwMoveMode::Glide;
    Movement->SetMovementMode(MOVE_Custom, MovementMode);
    Movement->Velocity = Velocity;
    Play(Velocity.Z < -500.f && Has(TEXT("GlideOnFall")) ? TEXT("GlideOnFall") : TEXT("GlideOn"), .1f);
    FlipTime = -1.f;
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
    {
        // The canopy catches the air: a whoomp of wind motes thrown up and out, and a ring above his head.
        const FVector Top = Character->GetActorLocation() + FVector(0, 0, HalfHeight() * 1.3f);
        AAtelierFX::FParticle& Ring = FX->Spawn(AAtelierFX::ESprite::Ring, Top); Ring.Size0 = 30.f; Ring.Size1 = 160.f; Ring.Life = .3f;
        Ring.Color = FLinearColor(.86f, .95f, 1.f) * 1.8f;
        FX->Burst(Top, FVector(0, 0, .5f), 22, 420.f, FLinearColor(.9f, .96f, 1.f) * 3.f, .45f, 2.2f);
        FX->Play(TEXT("dash"), Character->GetActorLocation(), .5f, .08f);
    }
}

void UBotwMoveSet::CloseGlider(bool bLanding)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (bLanding)
    {
        Mode = EBotwMoveMode::Ground;
        Movement->SetMovementMode(MOVE_Walking);
        Movement->Velocity = Movement->Velocity.GetSafeNormal2D() * FMath::Min(float(Movement->Velocity.Size2D()), 200.f);
        if (Has(TEXT("GlideOff"))) Play(TEXT("GlideOff"), .1f); else Play(TEXT("Land"), .1f);
        if (UJapanFootstepComponent* Steps = Character->GetFootsteps())
        {
            FHitResult Floor; Floor.ImpactPoint = Character->GetActorLocation() - FVector(0, 0, HalfHeight()); Floor.ImpactNormal = FVector::UpVector;
            Steps->Land(Floor, .6f);
        }
    }
    else
    {
        Mode = EBotwMoveMode::Air;
        Movement->SetMovementMode(MOVE_Falling);
        ShowGlider(false);
        Play(TEXT("Fall"), .25f);
        FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f;
        SinceGrounded = FMath::Max(SinceGrounded, .15f);
    }
    FallStartZ = Character->GetActorLocation().Z;
}

/** Flies on: turns toward the stick, speeds up when it pushes ahead and brakes when it pulls back, sinks at a steady rate,
 *  lands on walkable ground, grabs a climbable wall, swims on water, and drops when the stamina runs out. */
void UBotwMoveSet::PhysGlide(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    GlideTime += Dt;
    const FVector W = Wish();
    const float Push = W.Size2D();
    float Turn = 0.f, TargetSpeed = GetParam(TEXT("GlideNeutralSpeed"), 240.f);
    bGlideBrake = false;
    if (Push > .15f)
    {
        const float Delta = FMath::FindDeltaAngleDegrees(GlideYaw, W.Rotation().Yaw);
        if (FMath::Abs(Delta) > 150.f) { bGlideBrake = true; TargetSpeed = GetParam(TEXT("GlideBrakeSpeed"), 130.f); }
        else
        {
            Turn = FMath::Clamp(Delta * 3.f, -GetParam(TEXT("GlideTurnRate"), 140.f), GetParam(TEXT("GlideTurnRate"), 140.f)) * Push;
            TargetSpeed = FMath::Lerp(TargetSpeed, GetParam(TEXT("GlideSpeed"), 450.f), Push * FMath::Max(0.f, FMath::Cos(FMath::DegreesToRadians(Delta))));
        }
    }
    GlideTurn = FMath::FInterpTo(GlideTurn, Turn, Dt, 6.f);
    GlideYaw = FRotator::NormalizeAxis(GlideYaw + GlideTurn * Dt);
    GlideSpeed = FMath::FInterpTo(GlideSpeed, TargetSpeed, Dt, 1.2f);
    const float Sink = -GetParam(TEXT("GlideSinkSpeed"), 150.f);
    float Vz = float(Movement->Velocity.Z);
    Vz = FMath::FInterpTo(Vz, Sink, Dt, Vz < Sink ? 4.f : 2.f);
    const FRotator Facing(0, GlideYaw, 0);
    const FVector Velocity = Facing.Vector() * GlideSpeed + FVector(0, 0, Vz);
    Movement->Velocity = Velocity;
    const FVector Delta = Velocity * Dt;
    FHitResult Hit;
    Movement->SafeMoveUpdatedComponent(Delta, Facing.Quaternion(), true, Hit);
    if (Hit.IsValidBlockingHit())
    {
        if (Movement->IsWalkable(Hit)) { CloseGlider(true); return; }
        if (Climbable(Hit) && NoClimb <= 0.f) { StartClimb(Hit, true); return; }
        Slide(Movement, Delta, Facing.Quaternion(), Hit);
        GlideSpeed *= FMath::Clamp(1.f - float(-(Hit.Normal | Facing.Vector())), .3f, 1.f);
    }
    FFindFloorResult Floor;
    Movement->FindFloor(Character->GetActorLocation(), Floor, false);
    if (Floor.IsWalkableFloor() && Floor.FloorDist < 6.f) { CloseGlider(true); return; }
    float Surface = 0.f;
    if (WaterAt(Character->GetActorLocation(), Surface) && Feet() <= Surface) { StartSwim(); return; }
    UseStamina(GetParam(TEXT("PlayerParashawlGlide.EnergyGlide"), 28.f) / 1000.f * Dt);
    if (Character->Stamina.Exhausted) CloseGlider(false);
}

void UBotwMoveSet::AdvanceGlide(float Dt)
{
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (Now && In(Name, { TEXT("GlideOn"), TEXT("GlideOnFall") }) && SourceTime() < (Now->Idle >= 0.f ? Now->Idle : Now->End)) return;
    FName Clip = TEXT("Glide");
    // The turning clips lean the body into the turn, which on a fitted body (Cairo's larger head) brings the inner
    // forearm into the head; there the glider's bank shows the turn and the body keeps the straight glide.
    if (FMath::Abs(GlideTurn) > 40.f && bOwnGlide) Clip = GlideTurn > 0.f ? TEXT("GlideR") : TEXT("GlideL");
    else if (bGlideBrake) Clip = TEXT("GlideB");
    else if (Wish().Size2D() > .3f) Clip = TEXT("GlideF");
    PlayLoop(Has(Clip) ? Clip : FName(TEXT("Glide")), .3f);
}

/** The paraglider is held at one hand, which a body other than Link's holds a little off its handles. On the neutral
 *  glide it is first fitted to both hands (the line between its two grips turned onto the hands' and their middles
 *  matched); that place on the body is then kept, banking about the grips into the turn, and each hand is put on its
 *  grip (the animation graph's IK), so the turning clips' arms (made for Link's smaller head) neither let go nor reach
 *  into Cairo's hair. */
void UBotwMoveSet::AdvanceGliderGrip(float Dt)
{
    USkeletalMeshComponent* Body = Character->GetMesh();
    if (!Glider || !Body) return;
    const FName Name = CurrentName();
    const bool bGliding = Mode == EBotwMoveMode::Glide && bGliderShown;
    const bool bNeutral = bGliding && In(Name, { TEXT("Glide"), TEXT("GlideF") }) && GlideTime > .5f && FMath::Abs(GlideTurn) < 8.f;
    const FName HandBone[2] = { Character->GetSkateBone(TEXT("hand_R")), Character->GetSkateBone(TEXT("hand_L")) };
    // The import's fit, carried by the root bone as the mesh has it now. It is kept, not fitted again to the hands: by
    // then the hand IK has turned each fist round its handle, and a fit from that hand rolled the canopy about 116 degrees
    // about the bar, standing it up behind his head (the operator, #7296).
    if (bGliderOnRoot) GliderOnBody = GliderOnRoot * Body->GetSocketTransform(Body->GetBoneName(0), RTS_Component);
    if (!bGliderOnBody)
    {
        // Fit the one-handed hold onto both hands, then keep it once it has settled on the neutral glide.
        const FTransform Bone = Body->GetSocketTransform(GliderSocket);
        const FTransform Base = GliderHeld * Bone;
        const FTransform& MeshT = Body->GetComponentTransform();
        if (bOwnGlide && !bPalmKnown)
        {
            // Link's neutral glide holds the handles: each hand's grip is where its handle passes nearest its wrist, kept
            // in the wrist's frame from then on.
            if (!bNeutral) return;
            for (int32 I = 0; I < 2; ++I)
            {
                const FTransform Wrist = Body->GetSocketTransform(HandBone[I], RTS_Component);
                const FVector OnHandle = FMath::ClosestPointOnSegment(Wrist.GetLocation(),
                    MeshT.InverseTransformPosition(Base.TransformPosition(GripEnds[I][0])), MeshT.InverseTransformPosition(Base.TransformPosition(GripEnds[I][1])));
                PalmLocal[I] = Wrist.InverseTransformPosition(OnHandle);
                BarGrip[I] = Base.InverseTransformPosition(MeshT.TransformPosition(OnHandle));
            }
            bPalmKnown = true;
        }
        const FVector BarR = Base.TransformPosition(BarGrip[0]), BarL = Base.TransformPosition(BarGrip[1]);
        const FVector HandR = MeshT.TransformPosition(PalmOf(0)), HandL = MeshT.TransformPosition(PalmOf(1));
        const FQuat Turn = FQuat::FindBetweenNormals((BarL - BarR).GetSafeNormal(), (HandL - HandR).GetSafeNormal());
        const FTransform Fitted(Turn * Base.GetRotation(), (HandR + HandL) * .5f + Turn.RotateVector(Base.GetLocation() - (BarR + BarL) * .5f), Base.GetScale3D());
        if (bNeutral)
        {
            GliderOnBody = Fitted.GetRelativeTransform(Body->GetComponentTransform());
            bGliderOnBody = true;
            for (int32 I = 0; I < 2; ++I)
                ElbowLocal[I] = GliderOnBody.InverseTransformPosition(
                    Body->GetSocketTransform(Character->GetSkateBone(I ? TEXT("forearm_L") : TEXT("forearm_R")), RTS_Component).GetLocation());
        }
        else if (bGliding) { Glider->SetRelativeTransform(Fitted.GetRelativeTransform(Bone)); return; }
        else return;
    }
    // On the body: carried by the mesh itself (no lag behind a moving hand bone), banked into the turn about the bar.
    GlideHands = FMath::FInterpConstantTo(GlideHands, bGliding && !In(Name, { TEXT("GlideOn"), TEXT("GlideOnFall"), TEXT("GlideOff") }) ? 1.f : 0.f, Dt, 6.f);
    if (bGliding && !bGliderBodyAttached)
    {
        Glider->AttachToComponent(Body, FAttachmentTransformRules::KeepRelativeTransform);
        bGliderBodyAttached = true;
    }
    if (!bGliding)
    {
        if (bGliderBodyAttached)
        {
            Glider->AttachToComponent(Body, FAttachmentTransformRules::KeepRelativeTransform, GliderSocket);
            Glider->SetRelativeTransform(GliderHeld);
            bGliderBodyAttached = false;
        }
        GlideHands = 0.f;
        return;
    }
    // A fitted body banks less: its hands, under handles closer together than its head is wide, would bring the inner
    // forearm into the head.
    const float MaxBank = bOwnGlide ? 15.f : 12.f;
    GlideBank = FMath::FInterpTo(GlideBank, FMath::Clamp(GlideTurn * .12f, -MaxBank, MaxBank), Dt, 5.f);
    const FTransform& Mesh = Body->GetComponentTransform();
    const FVector Forward = Mesh.InverseTransformVectorNoScale(Character->GetActorForwardVector());
    const FVector Pivot = GliderOnBody.TransformPosition((BarGrip[0] + BarGrip[1]) * .5f);
    const FQuat Bank(Forward, FMath::DegreesToRadians(-GlideBank));   // into the turn: the inner side down
    FTransform Placed = GliderOnBody * FTransform(-Pivot) * FTransform(Bank) * FTransform(Pivot);
    // Link's is lowered by as much as the bank lifts the higher grip, which his outer arm (straight overhead) could not
    // reach; a fitted body's inner hand would come down beside the head instead.
    const FVector Up = Mesh.InverseTransformVectorNoScale(FVector::UpVector);
    float Rise = 0.f;
    for (int32 I = 0; I < 2 && bOwnGlide; ++I)
        Rise = FMath::Max(Rise, (Placed.TransformPosition(BarGrip[I]) - GliderOnBody.TransformPosition(BarGrip[I])) | Up);
    Placed.AddToTranslation(-Up * Rise);
    Glider->SetRelativeTransform(Placed);
    // Each hand onto its handle where it reaches it: its grip point moved to the nearest point of its grip, the wrist
    // moved with it. A fitted body's hand is a fist turned round the handle: its grip axis along it (thumb forward) and
    // its grip point away from the elbow, the wrist placed under it.
    const bool bFist = GlideFistWeight() > 0.f;
    for (int32 I = 0; I < 2; ++I)
    {
        GlideElbow[I] = Placed.TransformPosition(ElbowLocal[I]);
        const FVector From = Placed.TransformPosition(GripEnds[I][0]), To = Placed.TransformPosition(GripEnds[I][1]);
        const FTransform Hand = Body->GetSocketTransform(HandBone[I], RTS_Component);
        const FVector Grip = PalmOf(I);
        const FVector OnGrip = FMath::ClosestPointOnSegment(Grip, From, To);
        if (!bFist) { GlideHandTarget[I] = Hand.GetLocation() + (OnGrip - Grip); continue; }
        FVector Along = (To - From).GetSafeNormal();
        if ((Along | Forward) < 0.f) Along = -Along;
        const FVector GripLocal = Hand.InverseTransformPosition(Grip);
        const FVector Axis = FistAxis.GetSafeNormal();
        const FVector Out = (GripLocal - Axis * (GripLocal | Axis)).GetSafeNormal();
        const FVector Away = OnGrip - GlideElbow[I];
        const FVector Want = (Away - Along * (Away | Along)).GetSafeNormal();
        const FQuat Onto = FQuat::FindBetweenNormals(Axis, Along);
        const FVector Turned = Onto.RotateVector(Out);
        GlideHandTurn[I] = FQuat(Along, FMath::Atan2((Turned ^ Want) | Along, Turned | Want)) * Onto;
        GlideHandTarget[I] = OnGrip - FTransform(GlideHandTurn[I], FVector::ZeroVector, Hand.GetScale3D()).TransformVector(GripLocal);
    }
}

FVector UBotwMoveSet::PalmOf(int32 Side) const
{
    const USkeletalMeshComponent* Body = Character->GetMesh();
    const FName Hand = Character->GetSkateBone(Side ? TEXT("hand_L") : TEXT("hand_R"));
    if (bPalmKnown) return Body->GetSocketTransform(Hand, RTS_Component).TransformPosition(PalmLocal[Side]);
    return FingersOf(Side);
}

FVector UBotwMoveSet::FingersOf(int32 Side) const
{
    // A hand closed round a bar holds it in the middle of its curled fingers: the centroid of the index and middle
    // fingers' joints (base, middle and end), else the hand bone.
    const USkeletalMeshComponent* Body = Character->GetMesh();
    const FName Hand = Character->GetSkateBone(Side ? TEXT("hand_L") : TEXT("hand_R"));
    const TCHAR* S = Side ? TEXT("_L") : TEXT("_R");
    FVector Sum = FVector::ZeroVector; int32 Count = 0;
    for (const TCHAR* Joint : { TEXT("finger_"), TEXT("finger_tip_"), TEXT("finger_end_") })
        for (int32 Finger = 1; Finger <= 2; ++Finger)
        {
            const FName Bone(*FString::Printf(TEXT("%s%d%s"), Joint, Finger, S));
            if (Body->GetBoneIndex(Bone) == INDEX_NONE) continue;
            Sum += Body->GetSocketTransform(Bone, RTS_Component).GetLocation(); ++Count;
        }
    return Count ? Sum / Count : Body->GetSocketTransform(Hand, RTS_Component).GetLocation();
}

void UBotwMoveSet::ShowGlider(bool bShow)
{
    if (!Glider || bGliderShown == bShow) return;
    bGliderShown = bShow;
    Glider->SetVisibility(bShow, true);
    if (bShow && GliderClip) Glider->PlayAnimation(GliderClip, true);
    else if (!bShow) Glider->Stop();
}

// -------------------------------------------------------------------------------------------------------- Climbing

float UBotwMoveSet::BodyHold() const { return GetParam(TEXT("PlayerActionClimb.BodyFixedOffset"), .35f) * 100.f * Scale(); }
float UBotwMoveSet::HoldDistance() const { return FMath::Max(Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + 2.f, BodyHold()); }

void UBotwMoveSet::ClimbBasis(FVector& Forward, FVector& Right, FVector& Up) const
{
    Forward = -WallNormal;
    Up = (FVector::UpVector - WallNormal * (FVector::UpVector | WallNormal)).GetSafeNormal();
    if (Up.IsNearlyZero()) Up = FVector::UpVector;
    Right = FVector::CrossProduct(Up, Forward).GetSafeNormal();
}

void UBotwMoveSet::StartClimb(const FHitResult& Wall, bool bFromAir)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    ShowGlider(false);
    SetArmed(false);
    if (Character->bIsCrouched) Character->UnCrouch();
    bLocked = false; bCharging = false; Target = nullptr;
    Mode = EBotwMoveMode::Climb;
    Movement->SetMovementMode(MOVE_Custom, JapanNetwork::IsOnline(Character->GetWorld()) ? ClimbMovementMode : MovementMode);
    Movement->Velocity = FVector::ZeroVector;
    WallNormal = Wall.ImpactNormal.GetSafeNormal(); WallPoint = Wall.ImpactPoint;
    // Hold the capsule off the wall, facing it; the body leans in to the wall by the rest (the mesh shift).
    const float Gap = float((Character->GetActorLocation() - WallPoint) | WallNormal);
    const FRotator Facing(0, (-WallNormal).GetSafeNormal2D().Rotation().Yaw, 0);
    FHitResult Ignored;
    Movement->SafeMoveUpdatedComponent(WallNormal * (HoldDistance() - Gap), Facing.Quaternion(), true, Ignored);
    ClimbShiftTarget = HoldDistance() - BodyHold();
    ClimbStill = 0.f; ClimbProbe = 0.f; ClimbBlocked = -1;
    if (bFromAir && Has(TEXT("ClimbGrab"))) { Play(TEXT("ClimbGrab"), .08f); BeginDrive(true); }
    else Play(TEXT("ClimbWait"), .25f);
}

void UBotwMoveSet::LeaveClimb(bool bFall)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    ClimbShiftTarget = 0.f;
    bDriving = false;
    if (bFall)
    {
        Mode = EBotwMoveMode::Air;
        Movement->SetMovementMode(MOVE_Falling);
        Movement->Velocity = WallNormal.GetSafeNormal2D() * 80.f;
        FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f; SinceGrounded = .2f;
        NoClimb = FMath::Max(NoClimb, GetParam(TEXT("PlayerFall.NoClimbTime"), 8.f) / 30.f);
        Play(TEXT("Fall"), .2f);
    }
    else
    {
        Mode = EBotwMoveMode::Ground;
        Movement->SetMovementMode(MOVE_Walking);
        Stop(.25f);
    }
}

/** At the top of a wall, climb onto the ledge: the clip's root path is fitted to the real ledge (BOTW warps it too). */
bool UBotwMoveSet::TryClimbTop()
{
    const FBotwMove* Top = Moves.Find(TEXT("ClimbTop"));
    if (!Top || Top->Path.IsEmpty()) return false;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    const float Half = HalfHeight(), Radius = Character->GetCapsuleComponent()->GetScaledCapsuleRadius();
    const FVector Forward = (-WallNormal).GetSafeNormal2D();
    // The ledge: straight down just beyond the wall's edge, with room to stand.
    const FVector Probe = Here + Forward * (HoldDistance() + Radius + 20.f) + FVector(0, 0, Half + 90.f);
    FHitResult Ledge;
    if (!Trace(Probe, Probe - FVector(0, 0, Half * 2.f + 140.f), Ledge) || !Movement->IsWalkable(Ledge)) return false;
    // On a sloping ledge the capsule's round foot rests above the point straight below its centre.
    const FVector Stand(Probe.X, Probe.Y, Ledge.ImpactPoint.Z + Half - Radius + Radius / FMath::Max(.5f, float(Ledge.ImpactNormal.Z)) + 2.f);
    if (Stand.Z < Here.Z - Half * .5f || Blocked(Stand)) return false;
    const FVector4f End = Top->PathAt(Top->End);
    const float Ahead = float((Stand - Here) | Forward), Rise = float(Stand.Z - Here.Z);
    // A ledge far above the clip's own climb is not reached yet: keep climbing.
    if (End.Z > 1.f && Rise > 3.f * End.Z) return false;
    const FVector Fit(End.X > 1.f ? FMath::Clamp(Ahead / End.X, .2f, 3.f) : 1.f, 1.f, End.Z > 1.f ? FMath::Clamp(Rise / End.Z, .2f, 3.f) : 1.f);
    Character->SetActorRotation(FRotator(0, Forward.Rotation().Yaw, 0));
    Play(TEXT("ClimbTop"), .1f);
    // The body's lean into the wall eases out over the climb; what the fitted path misses of the stand (its fit is
    // clamped) is made up along the way, so the capsule ends standing on the ledge, not inside it.
    BeginDrive(false, Fit, FVector::ZeroVector);
    DriveMesh = (Stand - Here) - WorldPath(End);
    MeshDriveLocal = FVector(ClimbShift, 0, 0); ClimbShift = ClimbShiftTarget = 0.f;
    return true;
}

void UBotwMoveSet::PhysClimb(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FName Name = CurrentName();
    if (bDriving && !bDriveSweep) { AdvanceDrive(Dt); return; }   // a ledge climb follows its fitted path alone
    if (Name == TEXT("ClimbOff") || Name == TEXT("ClimbTired")) { Movement->Velocity = FVector::ZeroVector; return; }
    // Keep to the wall: find it again straight ahead, and around a bend.
    FHitResult Wall;
    const bool bWall = FindWall(-WallNormal, Wall, 0.f, 0.f, HoldDistance() + 45.f) && Climbable(Wall);
    const bool bFlat = !bWall && Wall.bBlockingHit && Movement->IsWalkable(Wall);
    if (bFlat)
    {
        // The wall has flattened out: stand on it once the feet are on it. Until then climb over its edge, or on up the
        // slope (letting go with no floor under the feet dropped the climber back down it).
        FFindFloorResult Floor;
        Movement->FindFloor(Character->GetActorLocation(), Floor, false);
        if (Floor.IsWalkableFloor()) { LeaveClimb(false); return; }
        if (TryClimbTop()) return;
    }
    if (bWall || bFlat)
    {
        WallNormal = (WallNormal * .5f + Wall.ImpactNormal * .5f).GetSafeNormal(); WallPoint = Wall.ImpactPoint;
    }
    else
    {
        if (!TryClimbTop()) LeaveClimb(true);
        return;
    }
    if (bDriving) AdvanceDrive(Dt); else Movement->Velocity = FVector::ZeroVector;
    const FVector Here = Character->GetActorLocation();
    const float Gap = float((Here - WallPoint) | WallNormal);
    const FRotator Facing(0, FMath::FixedTurn(Character->GetActorRotation().Yaw, (-WallNormal).GetSafeNormal2D().Rotation().Yaw, 360.f * Dt), 0);
    FHitResult Ignored;
    Movement->SafeMoveUpdatedComponent(WallNormal * (HoldDistance() - Gap) * FMath::Min(1.f, Dt * 12.f), Facing.Quaternion(), true, Ignored);
}

void UBotwMoveSet::AdvanceClimb(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    const FVector2D Stick = Character->GetMoveIntent().GetClampedToMaxSize(1.f);   // up the wall and to its right
    if (Name == TEXT("ClimbTop"))
    {
        if (Over() || (Now->Idle >= 0.f && SourceTime() >= Now->Idle && !Stick.IsNearlyZero()))
        {
            Mode = EBotwMoveMode::Ground; bDriving = false; MeshDriveLocal = FVector::ZeroVector;
            Movement->SetMovementMode(MOVE_Walking);
            Stop(.25f);
        }
        return;
    }
    if (Name == TEXT("ClimbOff"))
    {
        if (Over())
        {
            // Pushed off backwards: turn away from the wall and fall clear of it.
            const FVector Away = WallNormal.GetSafeNormal2D();
            LeaveClimb(true);
            Character->SetActorRotation(FRotator(0, Away.Rotation().Yaw, 0));
            Movement->Velocity = Away * 260.f + FVector(0, 0, 250.f);
            NoClimb = .4f;
        }
        return;
    }
    if (Name == TEXT("ClimbTired"))
    {
        if (Over()) { LeaveClimb(true); NoClimb = GetParam(TEXT("PlayerFall.NoClimbTimeTired"), 20.f) / 30.f; }
        return;
    }
    if (Now && (Name == TEXT("ClimbGrab") || Prefixed(Name, { TEXT("ClimbJump") })) && SourceTime() < (Now->Idle >= 0.f ? Now->Idle : Now->End)) return;
    if (Character->Stamina.Exhausted && Has(TEXT("ClimbTired"))) { Play(TEXT("ClimbTired"), .1f); return; }
    if (JumpBuffer > 0.f)
    {
        JumpBuffer = 0.f;
        if (Stick.Y < -.5f && FMath::Abs(Stick.X) < .5f && Has(TEXT("ClimbOff"))) { Play(TEXT("ClimbOff"), .08f); return; }
        if (!HasStamina()) return;
        const TCHAR* Dir = TEXT("U");
        if (Stick.Size() > .3f)
        {
            const float Angle = FMath::RadiansToDegrees(FMath::Atan2(Stick.X, Stick.Y));
            Dir = Angle > 67.5f ? TEXT("R") : Angle > 22.5f ? TEXT("UR") : Angle < -67.5f ? TEXT("L") : Angle < -22.5f ? TEXT("UL") : TEXT("U");
        }
        const FName Jump(*FString::Printf(TEXT("ClimbJump%s"), Dir));
        if (!Has(Jump)) return;
        UseStamina(GetParam(TEXT("PlayerActionClimb.StaminaDownTriggerJump"), 310.f) / 1000.f);
        Play(Jump, .1f); BeginDrive(true);
        return;
    }
    if (Stick.Size() > .2f)
    {
        static const TCHAR* const Dirs[8] = { TEXT("U"), TEXT("UR"), TEXT("R"), TEXT("DR"), TEXT("D"), TEXT("DL"), TEXT("L"), TEXT("UL") };
        const float Angle = FMath::RadiansToDegrees(FMath::Atan2(Stick.X, Stick.Y));
        const int32 Index = (FMath::RoundToInt(Angle / 45.f) + 8) % 8;
        const FName Clip(*FString::Printf(TEXT("Climb%s"), Dirs[Index]));
        // Climbing down onto the ground stands up.
        FFindFloorResult Floor;
        if (Stick.Y < -.3f)
        {
            Movement->FindFloor(Character->GetActorLocation(), Floor, false);
            if (Floor.IsWalkableFloor() && Floor.FloorDist < 10.f) { LeaveClimb(false); return; }
        }
        // Climbing that gets nowhere for a moment (into an overhang, say) holds on until the stick turns another way.
        const FVector Here = Character->GetActorLocation();
        if (Index != ClimbBlocked) ClimbBlocked = -1;
        if (ClimbBlocked < 0 && Playing(Clip) && (ClimbProbe += Dt) >= .6f)
        {
            if (FVector::Dist(Here, ClimbProbeFrom) < 5.f) ClimbBlocked = Index;
            ClimbProbe = 0.f; ClimbProbeFrom = Here;
        }
        if (ClimbBlocked >= 0) { if (!Playing(TEXT("ClimbWait"))) Play(TEXT("ClimbWait"), .25f); return; }
        if (!Playing(Clip) && Has(Clip)) { PlayLoop(Clip, .2f); BeginDrive(true); ClimbProbe = 0.f; ClimbProbeFrom = Here; }
        const float Rate = Stick.Y > .3f ? GetParam(TEXT("PlayerActionClimb.StaminaRateMovingUp"), 1.f)
            : Stick.Y < -.3f ? GetParam(TEXT("PlayerActionClimb.StaminaRateMovingDown"), .5f) : GetParam(TEXT("PlayerActionClimb.StaminaRateMovingSide"), .5f);
        UseStamina(GetParam(TEXT("PlayerActionClimb.StaminaDownAlways"), 36.5f) / 1000.f * Rate * Dt);
        // The hands have passed the top of the wall: up onto the ledge.
        if (Stick.Y > .3f)
        {
            const float Hands = float(Character->GetActorLocation().Z) - HalfHeight() + 1.12f * 100.f * Scale();
            FHitResult Wall;
            if (!FindWall(-WallNormal, Wall, Hands - float(Character->GetActorLocation().Z), 0.f, HoldDistance() + 45.f)) TryClimbTop();
        }
    }
    else if (!Playing(TEXT("ClimbWait"))) { Play(TEXT("ClimbWait"), .25f); ClimbStill = 0.f; }
    else ClimbStill += Dt;
}

// -------------------------------------------------------------------------------------------------------- Swimming

bool UBotwMoveSet::WaterAt(const FVector& Where, float& Surface) const
{
    const AJapanWorld* World = Character ? Character->GetLandscape() : nullptr;
    if (!World) return false;
    // The woodland lake: the same shoreline as the character's own lake recovery.
    if (World->bForestLakeLoaded)
    {
        const FVector Relative = Where - World->ForestLakeCenter;
        const double X = Relative.X / World->ForestLakeRadii.X, Y = -Relative.Y / World->ForestLakeRadii.Y;
        const double Angle = FMath::Atan2(Y, X), Shore = 1. + .045 * FMath::Sin(3. * Angle) + .035 * FMath::Cos(5. * Angle);
        if (X * X + Y * Y < Shore * Shore) { Surface = float(World->ForestLakeCenter.Z); return true; }
    }
    // The sea off the coast: its surface is at zero, wherever the ground lies below it.
    if (Where.X <= 30000. && FMath::Abs(Where.X) < 220000. && Where.Y > 4000. && Where.Y < 150000.) { Surface = 0.f; return true; }
    return false;
}

float UBotwMoveSet::SwimHang() const { return GetParam(TEXT("SwimHang"), 1.4f * 100.f * Scale()); }

void UBotwMoveSet::StartSwim()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    float Surface = 0.f;
    if (!WaterAt(Character->GetActorLocation(), Surface)) return;
    ShowGlider(false);
    SetArmed(false);
    if (Character->bIsCrouched) Character->UnCrouch();
    bLocked = false; bCharging = false; Target = nullptr; ClimbShiftTarget = 0.f; ClimbShift = 0.f;
    const float FeetBefore = Feet();
    const FVector Here = Character->GetActorLocation();
    SwimYaw = Character->GetActorRotation().Yaw;
    SwimSpeed = FMath::Min(float(Movement->Velocity.Size2D()) * .5f, 200.f);
    Mode = EBotwMoveMode::Swim;
    Movement->SetMovementMode(MOVE_Custom, JapanNetwork::IsOnline(Character->GetWorld()) ? SwimMovementMode : MovementMode);
    Movement->Velocity = FVector::ZeroVector;
    WaterSurface = Surface;
    // The mesh's origin floats at the surface and the swimming body hangs below it; the body keeps its height a moment.
    Character->SetActorLocation(FVector(Here.X, Here.Y, Surface + HalfHeight()), false, nullptr, ETeleportType::TeleportPhysics);
    EaseMesh(FVector(0, 0, FMath::Clamp(FeetBefore - Surface, -SwimHang(), 0.f)), .35f);
    Play(SwimSpeed > 25.f ? TEXT("Swim") : TEXT("SwimWait"), .3f);
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
        FX->Burst(FVector(Here.X, Here.Y, Surface), FVector::UpVector, 18, 380.f, FLinearColor(.75f, .85f, 1.f) * 1.4f, .5f, 4.f);
}

void UBotwMoveSet::LeaveSwim(const FVector& Stand)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const float From = Feet();
    Mode = EBotwMoveMode::Ground;
    Character->SetActorLocation(Stand + FVector(0, 0, HalfHeight() + 1.f), false, nullptr, ETeleportType::TeleportPhysics);
    Movement->SetMovementMode(MOVE_Walking);
    EaseMesh(FVector(0, 0, From - float(Stand.Z)), .3f);
    Stop(.3f);
}

/** At a wall whose top is just above the water: haul out onto it along the clip's path, fitted to the ledge. */
bool UBotwMoveSet::TrySwimOut(const FHitResult& Wall)
{
    if (!Has(TEXT("SwimOut"))) return false;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Normal = Wall.ImpactNormal.GetSafeNormal2D();
    if (Normal.IsNearlyZero() || (FRotator(0, SwimYaw, 0).Vector() | -Normal) < .5f) return false;
    const float Half = HalfHeight(), Radius = Character->GetCapsuleComponent()->GetScaledCapsuleRadius();
    const FVector Probe = FVector(Wall.ImpactPoint.X, Wall.ImpactPoint.Y, WaterSurface) - Normal * (Radius + 25.f) + FVector(0, 0, 160.f);
    FHitResult Top;
    if (!Trace(Probe, Probe - FVector(0, 0, 220.f), Top) || !Movement->IsWalkable(Top)) return false;
    const float Ledge = float(Top.ImpactPoint.Z) - WaterSurface;
    if (Ledge < -30.f || Ledge > .9f * 100.f * Scale()) return false;
    const FVector Stand(Probe.X, Probe.Y, Top.ImpactPoint.Z + Half + 2.f);
    if (Blocked(Stand)) return false;
    const FName Clip = Ledge > .25f * 100.f * Scale() && Has(TEXT("SwimOutHigh")) ? TEXT("SwimOutHigh") : TEXT("SwimOut");
    const FBotwMove* Out = Moves.Find(Clip);
    if (!Out || Out->Path.IsEmpty()) return false;
    const FVector Here = Character->GetActorLocation();
    Character->SetActorRotation(FRotator(0, (-Normal).Rotation().Yaw, 0));
    Play(Clip, .12f);
    // The clip starts from the hanging body (the mesh origin a hang below the surface) and ends standing on the ledge.
    const FVector4f End = Out->Path.Last();
    const float Ahead = float((Stand - Here) | -Normal), Rise = float(Top.ImpactPoint.Z) - (WaterSurface - SwimHang());
    const FVector Fit(End.X > 1.f ? FMath::Clamp(Ahead / End.X, .2f, 3.f) : 1.f, 1.f, End.Z > 1.f ? FMath::Clamp(Rise / End.Z, .2f, 3.f) : 1.f);
    BeginDrive(false, Fit, FVector(0, 0, -SwimHang()));
    MeshDriveLocal = FVector(0, 0, -SwimHang());
    return true;
}

void UBotwMoveSet::PhysSwim(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    float Surface = 0.f;
    if (!WaterAt(Here, Surface)) { Mode = EBotwMoveMode::Air; Movement->SetMovementMode(MOVE_Falling); Play(TEXT("Fall"), .2f); return; }
    WaterSurface = Surface;
    if (CurrentName() == TEXT("SwimDie")) { Movement->Velocity = FVector::ZeroVector; return; }
    const FVector W = Wish();
    const float S = Scale();
    const float Cruise = GetParam(TEXT("PlayerSwimMove.MaxSpeedF"), .052f) * 3000.f * S, Dash = GetParam(TEXT("SwimDashSpeed"), 290.f);
    const float Goal = SwimDashTime > 0.f ? Dash : W.Size2D() * Cruise;
    if (W.Size2D() > .1f) SwimYaw = FMath::FixedTurn(SwimYaw, W.Rotation().Yaw, 240.f * Dt);
    SwimSpeed = FMath::FInterpConstantTo(SwimSpeed, Goal, Dt, SwimDashTime > 0.f ? 700.f : 260.f);
    const FRotator Facing(0, SwimYaw, 0);
    FVector Velocity = Facing.Vector() * SwimSpeed;
    Velocity.Z = FMath::Clamp((Surface + HalfHeight() - float(Here.Z)) / Dt, -300.f, 300.f);
    Movement->Velocity = FVector(Velocity.X, Velocity.Y, 0.);
    const FVector Delta = Velocity * Dt;
    FHitResult Hit;
    Movement->SafeMoveUpdatedComponent(Delta, Facing.Quaternion(), true, Hit);
    if (Hit.IsValidBlockingHit())
    {
        if (TrySwimOut(Hit)) return;
        if (Climbable(Hit) && NoClimb <= 0.f && (Facing.Vector() | -Hit.ImpactNormal.GetSafeNormal2D()) > .5f && SwimSpeed > 20.f) { StartClimb(Hit, false); return; }
        Slide(Movement, Delta, Facing.Quaternion(), Hit);
    }
    // Shallow enough to stand: walk out.
    FHitResult Floor;
    const float Shallow = GetParam(TEXT("NoSquatWaterHeight"), .6f) * 100.f * S;
    const FVector Now = Character->GetActorLocation();
    if (Trace(Now, FVector(Now.X, Now.Y, Surface - Shallow), Floor) && Movement->IsWalkable(Floor)) LeaveSwim(Floor.ImpactPoint);
}

void UBotwMoveSet::AdvanceSwim(float Dt)
{
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    SwimDashTime = FMath::Max(0.f, SwimDashTime - Dt);
    if (Name == TEXT("SwimOut") || Name == TEXT("SwimOutHigh"))
    {
        if (Over())
        {
            Mode = EBotwMoveMode::Ground; bDriving = false; MeshDriveLocal = FVector::ZeroVector;
            Character->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
            Stop(.2f);
        }
        return;
    }
    if (Name == TEXT("SwimDie"))
    {
        if (Over() && (!JapanNetwork::IsOnline(Character->GetWorld()) || Character->HasAuthority()))
        {
            // Out of stamina in deep water: back to the last dry ground, a little hurt.
            const FVector Shore = bHasSafeShore ? SafeShore : Character->GetActorLocation();
            const bool Online = JapanNetwork::IsOnline(Character->GetWorld());
            if (Online)
            {
                // Several moves may run before recovery. The queue applies drowning damage once.
                CastChecked<UJapanCharacterMovement>(Character->GetCharacterMovement())->QueueAuthoritativeRecovery(
                    Shore, Character->GetActorRotation().Yaw, GetParam(TEXT("DrownDamage"), 10.f));
                return;
            }
            if (UWandererSwordComponent* Sword = Character->GetSword()) Sword->Health = FMath::Max(1.f, Sword->Health - GetParam(TEXT("DrownDamage"), 10.f));
            // The shore is a spot he stood on: land on it, not on a canopy above it.
            Character->TravelTo(Shore, Character->GetActorRotation().Yaw, TEXT("swim recovery"), 100.f);
        }
        return;
    }
    if (Character->Stamina.Exhausted && Has(TEXT("SwimDie"))) { Play(TEXT("SwimDie"), .2f); SwimSpeed = 0.f; return; }
    if (JumpBuffer > 0.f)
    {
        JumpBuffer = 0.f;
        if (HasStamina() && Has(TEXT("SwimDash")))
        {
            UseStamina(GetParam(TEXT("PlayerSwimDash.EnergyDash"), 125.f) / 1000.f);
            SwimDashTime = .6f; Play(TEXT("SwimDash"), .15f);
            return;
        }
    }
    if (Name == TEXT("SwimDash") && Now && SourceTime() < FreeAt(*Now)) return;
    if (SwimSpeed > 20.f) UseStamina(GetParam(TEXT("PlayerSwimMove.EnergyMove"), 30.f) / 1000.f * Dt);
    PlayLoop(SwimSpeed > 25.f ? TEXT("Swim") : TEXT("SwimWait"), .3f);
}
