#include "WandererSword.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkinnedAsset.h"
#include "ReferenceSkeleton.h"
#include "Engine/World.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "CollisionQueryParams.h"
#include "UObject/ConstructorHelpers.h"
#include "FoxHunter.h"
#include "EngineUtils.h"
#include "JapanCombatFX.h"

UWandererSwordComponent::UWandererSwordComponent() { PrimaryComponentTick.bCanEverTick = false; }

void UWandererSwordComponent::Initialize(AWandererCharacter* Owner)
{
    Character = Owner;
    const UWandererDefinition* D = Owner ? Owner->GetDefinition() : nullptr;
    if (!D || !D->HasSwordSet() || !Owner->GetMesh()) return;
    Blade = NewObject<UStaticMeshComponent>(Owner, TEXT("Bokken"));
    Blade->SetStaticMesh(D->SwordMesh);
    Blade->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Blade->SetCastShadow(true);
    Blade->SetRenderCustomDepth(true); Blade->SetCustomDepthStencilValue(1);
    Blade->RegisterComponent();
    Blade->AttachToComponent(Owner->GetMesh(), FAttachmentTransformRules::KeepRelativeTransform, D->SwordAttachBone);
    Blade->SetRelativeTransform(D->SwordAttach);
    Blade->SetVisibility(false, true);
    Trail = NewObject<UJapanSwordTrail>(Owner, TEXT("SlashTrail"));
    Trail->RegisterComponent();
    Trail->SetWorldTransform(FTransform::Identity);
    // The FBX skeleton keeps the authoring scale on its root bone (about 148). Root-motion translation comes
    // through that scale, so the applied motion is normalised back to centimetres here.
    if (const USkinnedAsset* Asset = Owner->GetMesh()->GetSkinnedAsset())
    {
        const TArray<FTransform>& Ref = Asset->GetRefSkeleton().GetRefBonePose();
        const float RootScale = Ref.Num() ? Ref[0].GetScale3D().X : 1.f;
        if (RootScale > 1.5f) Owner->SetAnimRootMotionTranslationScale(1.f / RootScale);
        UE_LOG(LogTemp, Display, TEXT("Sword set installed: %d clips, attach %s, root scale %.2f"), D->SwordClips.Num(), *D->SwordAttachBone.ToString(), RootScale);
    }
}

bool UWandererSwordComponent::IsInstalled() const { return Blade && Character && Character->GetDefinition() && Character->GetDefinition()->HasSwordSet(); }
const FWandererSwordClip* UWandererSwordComponent::Clip(FName Role) const { return Character && Character->GetDefinition() ? Character->GetDefinition()->FindSwordClip(Role) : nullptr; }
bool UWandererSwordComponent::OwnsAction(FName Action) const { return Clip(Action) != nullptr || (Action == StandClip() && !Action.IsNone()); }
FName UWandererSwordComponent::StandClip() const
{
    // game-r16: standing armed is the idle with the sword in the hand; older content stands in the two-handed guard.
    const UWandererDefinition* D = Character ? Character->GetDefinition() : nullptr;
    return D && D->FindAction(TEXT("SwordStand")) ? FName(TEXT("SwordStand")) : FName(TEXT("SwordIdle"));
}

void UWandererSwordComponent::SetArmed(bool bArmed)
{
    // No draw or sheathe clip (user direction, 28 Sep): the sword appears in, or leaves, the hand at once, the arm keeps
    // its movement and the carry layer closes or opens the grip quickly.
    if (bArmed == (State != ESwordState::Stowed) || !Character) return;
    const FName Stand = StandClip();
    State = bArmed ? ESwordState::Guard : ESwordState::Stowed; StateTime = 0.f; CurrentClip = NAME_None; bPendingDrawAttack = false; bFastCarry = true;
    if (!bArmed && Character->GetAnimationAction() == Stand) Character->SetAction(NAME_None, false, .12f);
    UpdateSwordVisibility(); SetFeedback(bArmed ? TEXT("sword drawn") : TEXT("sword tucked away"));
    if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character))
        FX->Play(bArmed ? TEXT("sword_draw") : TEXT("sword_sheathe"), Character->GetMesh() ? Character->GetMesh()->GetComponentLocation() + FVector(0, 0, 90) : Character->GetActorLocation(), .8f);
}
float UWandererSwordComponent::LastFeedbackAge() const { return Clock - FeedbackTime; }
void UWandererSwordComponent::SetFeedback(const FString& Text) { Feedback = Text; FeedbackTime = Clock; }
float UWandererSwordComponent::ChargeFraction() const { return State == ESwordState::ChargeHold ? FMath::Clamp(ChargeTime / FullChargeTime, 0.f, 1.f) : State == ESwordState::ChargeUp ? 0.f : -1.f; }

FString UWandererSwordComponent::StateName() const
{
    switch (State)
    {
        case ESwordState::Stowed: return TEXT("Stowed"); case ESwordState::Guard: return TEXT("Guard"); case ESwordState::Draw: return TEXT("Draw");
        case ESwordState::Sheath: return TEXT("Sheath"); case ESwordState::Attack: return FString::Printf(TEXT("Attack%d"), ComboIndex);
        case ESwordState::Parry: return TEXT("Parry"); case ESwordState::ParryHit: return TEXT("ParryHit"); case ESwordState::ChargeUp: return TEXT("ChargeUp");
        case ESwordState::ChargeHold: return TEXT("ChargeHold"); case ESwordState::ChargeRelease: return TEXT("ChargeRelease");
    }
    return TEXT("?");
}

bool UWandererSwordComponent::LocksMovement() const
{
    if (!Character) return false;
    const float T = Character->GetActionSourceTime();
    switch (State)
    {
        case ESwordState::Draw: case ESwordState::Sheath: case ESwordState::ParryHit: case ESwordState::ChargeUp: case ESwordState::ChargeHold: return true;
        case ESwordState::Stowed: case ESwordState::Guard: return bDown;
        case ESwordState::Attack: case ESwordState::ChargeRelease: case ESwordState::Parry:
        {
            const FWandererSwordClip* C = Clip(CurrentClip);
            return C && (C->Cancel < 0.f || T < C->Cancel);
        }
        default: return false;
    }
}

bool UWandererSwordComponent::BlocksActions() const { return bDown || (State != ESwordState::Stowed && State != ESwordState::Guard); }

bool UWandererSwordComponent::IsParryActive() const
{
    if (State != ESwordState::Parry || !Character) return false;
    const float T = Character->GetActionSourceTime();
    return T >= ParryActiveStart && T <= ParryActiveEnd;
}

void UWandererSwordComponent::Enter(ESwordState Next, FName ClipName, float Blend, float Rate, bool bLoop, float StartTime)
{
    State = Next; StateTime = 0.f; CurrentClip = ClipName; HitStop = 0.f; bSwingCue = false;
    if (Character)
        if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character))
        {
            const FVector Hand = Character->GetMesh() ? Character->GetMesh()->GetComponentLocation() + FVector(0, 0, 90) : Character->GetActorLocation();
            if (Next == ESwordState::Draw) FX->Play(TEXT("sword_draw"), Hand, .8f);
            else if (Next == ESwordState::Sheath) FX->Play(TEXT("sword_sheathe"), Hand, .8f);
            else if (Next == ESwordState::ChargeUp) { FX->Play(TEXT("sword_charge"), Hand, .75f, .0f); bChargeReadyCue = false; }
            else if (Next == ESwordState::Parry) FX->Play(TEXT("sword_swing"), Hand, .45f, .1f);
        }
    if (Character)
    {
        if (ClipName.IsNone()) { if (OwnsAction(Character->GetAnimationAction())) Character->SetAction(NAME_None, false, Blend); }
        else
        {
            Character->SetAction(ClipName, bLoop, Blend, true);
            Character->ActionPlayRate = Rate; Character->ActionSourceStartTime = StartTime;
        }
    }
    UpdateSwordVisibility();
    UE_LOG(LogTemp, Verbose, TEXT("Sword state %s (%s)"), *StateName(), *ClipName.ToString());
}

void UWandererSwordComponent::UpdateSwordVisibility() { if (Blade) Blade->SetVisibility(State != ESwordState::Stowed, true); }

void UWandererSwordComponent::FaceInput(float StepToDistance, float YawOffsetDeg)
{
    if (!Character || !Character->Controller) return;
    const FRotationMatrix Basis(FRotator(0, Character->GetControlRotation().Yaw, 0));
    const FVector2D Move = Character->MoveIntent;
    FVector Dir = Move.IsNearlyZero() ? Character->GetActorForwardVector() : (Basis.GetUnitAxis(EAxis::X) * Move.Y + Basis.GetUnitAxis(EAxis::Y) * Move.X).GetSafeNormal();
    // With no stick input keep the current facing unless it points away from the camera; then turn to the camera's forward.
    if (Move.IsNearlyZero() && FVector::DotProduct(Dir, Basis.GetUnitAxis(EAxis::X)) < -.2f) Dir = Basis.GetUnitAxis(EAxis::X);
    // Soft lock: a living fox within reach and roughly ahead of the chosen direction takes the strike.
    float Best = 1e9f; LockDistance = -1.f;
    auto Consider = [&](const AActor* Target)
    {
        FVector To = Target->GetActorLocation() - Character->GetActorLocation(); To.Z = 0;
        const float D = To.Size();
        if (D < 300.f && D < Best && FVector::DotProduct(To.GetSafeNormal(), Dir) > (Move.IsNearlyZero() ? -.3f : .3f)) { Best = D; Dir = To.GetSafeNormal(); LockDistance = D; }
    };
    for (TActorIterator<AFoxHunter> It(Character->GetWorld()); It; ++It) if (It->IsAlive()) Consider(*It);
    for (TActorIterator<ASwordDummy> It(Character->GetWorld()); It; ++It) Consider(*It);
    FacingTarget = Dir.Rotation().Yaw + (LockDistance > 0.f ? YawOffsetDeg : 0.f); FacingBlend = .15f;
    // A locked fox beyond the clip's contact distance gets a step-in during the wind-up: a swept offset, because the strike
    // clips carry root motion that overrides any velocity (and LaunchCharacter would put the character in the air for a
    // frame and let the landing replace the clip).
    StepInRemaining = LockDistance > 0.f && StepToDistance > 0.f ? FMath::Clamp(LockDistance - StepToDistance, 0.f, 70.f) : 0.f; StepInDir = Dir;
}

void UWandererSwordComponent::StartAttack(int32 Combo, float Blend)
{
    ComboIndex = Combo; HitThisStrike.Reset(); PreviousBlade.Reset(); bCharged = false; bFullCharge = false; AttackStartClock = Clock;
    // Aim so the clip's measured contact point (combat-r02 manifest: bearing to the left of the start facing, distance) passes
    // through the target; the strike's recovery then ends facing it.
    const FName Role = *FString::Printf(TEXT("SwordAttack%d"), Combo);
    const FWandererSwordClip* Contact = Clip(Role);
    if (Contact && Contact->ContactDistance > 0.f) FaceInput(Contact->ContactDistance, Contact->ContactYaw);
    else if (Combo == 1) FaceInput(65.f, 25.f); else if (Combo == 2) FaceInput(95.f, 0.f); else FaceInput(90.f, -36.f);
    Enter(ESwordState::Attack, Role, Blend);
    FSwordStrikeEvent E; E.Time = Clock; E.Clip = CurrentClip; E.Combo = Combo; StrikeLog.Add(E);
    SetFeedback(bCounter ? TEXT("counter") : Combo == 1 ? TEXT("strike") : FString::Printf(TEXT("strike %d"), Combo));
    bCounterStrike = bCounter; bCounter = false;
}

void UWandererSwordComponent::AttackPressed()
{
    if (!IsInstalled() || !Character || !Character->IsReady() || Character->bMenuOpen || bDown) return;
    bAttackHeld = true; LastAttackPress = Clock;
    switch (State)
    {
        case ESwordState::Stowed:
            if (Character->CanAct() && Character->StandForAction()) { SetArmed(true); StartAttack(1, .07f); }
            break;
        case ESwordState::Guard:
            if (Character->CanAct() && Character->StandForAction()) StartAttack(1, .07f);
            break;
        default: break;   // buffered: Attack links read LastAttackPress
    }
}

void UWandererSwordComponent::AttackReleased()
{
    bAttackHeld = false; LastRelease = Clock;
    if (State == ESwordState::ChargeUp || State == ESwordState::ChargeHold)
    {
        HitThisStrike.Reset(); PreviousBlade.Reset(); bCharged = true; bFullCharge = State == ESwordState::ChargeHold && ChargeTime >= FullChargeTime;
        const FWandererSwordClip* Contact = Clip(TEXT("SwordChargeRelease"));
        if (Contact && Contact->ContactDistance > 0.f) FaceInput(Contact->ContactDistance, Contact->ContactYaw); else FaceInput(90.f, 0.f);
        Enter(ESwordState::ChargeRelease, TEXT("SwordChargeRelease"), .06f, bFullCharge ? 1.05f : 1.f);
        // The strike that turned into this charge already has an event; it becomes the charged one.
        if (!bChargeFromStrike || !StrikeLog.Num()) { FSwordStrikeEvent E; E.Time = Clock; StrikeLog.Add(E); }
        StrikeLog.Last().Clip = CurrentClip; StrikeLog.Last().bCharged = true; StrikeLog.Last().bFull = bFullCharge; bChargeFromStrike = false;
        SetFeedback(bFullCharge ? TEXT("full charge") : TEXT("charged"));
    }
}

void UWandererSwordComponent::ParryPressed()
{
    if (!IsInstalled() || !Character || !Character->IsReady() || Character->bMenuOpen || bDown) return;
    if (State == ESwordState::ChargeUp || State == ESwordState::ChargeHold)
    {
        if (bChargeFromStrike && StrikeLog.Num()) StrikeLog.Pop(); bChargeFromStrike = false;
        Enter(ESwordState::Guard, StandClip(), .22f, 1.f, true); SetFeedback(TEXT("charge cancelled")); return;
    }
    if (State == ESwordState::Guard && Character->CanAct() && Character->StandForAction())
    {
        FaceInput(); Enter(ESwordState::Parry, TEXT("SwordParry"), .05f); SetFeedback(TEXT("parry"));
    }
}

void UWandererSwordComponent::ToggleWeapon()
{
    if (!IsInstalled() || !Character || !Character->IsReady() || Character->bMenuOpen || bDown) return;
    if (State == ESwordState::Stowed) SetArmed(true);
    else if (State == ESwordState::Guard) SetArmed(false);
}

bool UWandererSwordComponent::CancelForInterrupt(bool bStow)
{
    if (bDown) return false;
    if (!IsInstalled()) return true;
    if (State == ESwordState::ChargeUp || State == ESwordState::ChargeHold)
    {
        if (bChargeFromStrike && StrikeLog.Num()) StrikeLog.Pop(); bChargeFromStrike = false;
        Enter(ESwordState::Guard, NAME_None, .18f); SetFeedback(TEXT("charge cancelled"));
    }
    else if (State == ESwordState::Attack || State == ESwordState::ChargeRelease || State == ESwordState::Parry)
    {
        if (LocksMovement()) return false;
        Enter(ESwordState::Guard, NAME_None, .14f);
    }
    else if (State == ESwordState::Draw || State == ESwordState::Sheath || State == ESwordState::ParryHit) return false;
    if (bStow) SetArmed(false);
    return true;
}

/** Drops whatever sword clip is playing back to the armed guard (or stays stowed), keeping the strike log honest. */
void UWandererSwordComponent::ForceGuard()
{
    if (State == ESwordState::Stowed) return;
    if ((State == ESwordState::ChargeUp || State == ESwordState::ChargeHold) && bChargeFromStrike && StrikeLog.Num()) StrikeLog.Pop();
    bChargeFromStrike = false; bPendingDrawAttack = false; HitStop = 0.f;
    State = ESwordState::Guard; CurrentClip = NAME_None;
    if (Character) Character->ActionPlayRate = 1.f;
}

int32 UWandererSwordComponent::IncomingStrike(AActor* Source, float Damage, const FVector& From)
{
    if (!Character) return 0;
    if (IsParryActive())
    {
        ++ParryCount; bCounter = true;
        if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character))
        {
            TArray<FVector> Points; BladePoints(Points);
            FX->Parry(Points.Num() ? Points[3] : Character->GetActorLocation() + FVector(0, 0, 40), Character, Source);
        }
        Enter(ESwordState::ParryHit, TEXT("SwordParryHit"), .03f);
        SetFeedback(TEXT("parried!"));
        return 1;
    }
    const FName Playing = Character->GetAnimationAction();
    if (Damage > 0.f && (Playing == TEXT("Roll") || Playing == TEXT("Dodge")) && Character->GetActionSourceTime() < .9f) { SetFeedback(TEXT("dodged")); return 2; }
    if (Damage > 0.f && (Invulnerable > 0.f || bDown)) return 3;
    ++HitsTakenCount;
    if (Damage <= 0.f) { SetFeedback(TEXT("hit")); return 0; }
    Health = FMath::Max(0.f, Health - Damage);
    ForceGuard();
    Invulnerable = .7f;
    if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character))
    {
        const FVector Chest = Character->GetActorLocation() + FVector(0, 0, 20);
        FX->PlayerHurt(Chest + (From - Chest).GetSafeNormal2D() * 18.f, From, Damage, Character, Source, Health <= 0.f);
    }
    if (Health <= 0.f)
    {
        bDown = true; DownTime = 0.f;
        Character->SetAction(TEXT("SitDown"), false, .08f, true);
        Character->GetCharacterMovement()->StopMovementImmediately();
        SetFeedback(TEXT("knocked down"));
    }
    else
    {
        // A short flinch and a shove away from the striker; movement input ends the flinch, as for any landing.
        Character->SetAction(TEXT("Land"), false, .05f, true);
        FVector Away = Character->GetActorLocation() - From; Away.Z = 0;
        if (Character->GetCharacterMovement()->IsMovingOnGround()) Character->GetCharacterMovement()->Velocity = Away.GetSafeNormal() * 260.f;
        SetFeedback(FString::Printf(TEXT("hit  -%.0f"), Damage));
    }
    return 0;
}

void UWandererSwordComponent::ReviewMove(FVector2D Intent) { if (Character) Character->MoveIntent = Intent; }
void UWandererSwordComponent::ReviewRoll(FVector2D Intent) { if (Character) { Character->MoveIntent = Intent; Character->Dodge(FInputActionValue(true)); } }

FVector UWandererSwordComponent::BladeTipWorld() const
{
    return Blade && Character && Character->GetDefinition() ? Blade->GetComponentTransform().TransformPosition(Character->GetDefinition()->SwordBladeEnd) : FVector::ZeroVector;
}

void UWandererSwordComponent::BladePoints(TArray<FVector>& Out) const
{
    Out.Reset();
    if (!Blade || !Character || !Character->GetDefinition()) return;
    const FTransform& T = Blade->GetComponentTransform();
    const FVector A = Character->GetDefinition()->SwordBladeStart, B = Character->GetDefinition()->SwordBladeEnd;
    for (int32 I = 0; I < 6; ++I) Out.Add(T.TransformPosition(FMath::Lerp(A, B, I / 5.f)));
}

void UWandererSwordComponent::SweepBlade(float Dt)
{
    TArray<FVector> Now; BladePoints(Now);
    if (PreviousBlade.Num() == Now.Num() && Now.Num())
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(SwordSweep), false, Character);
        for (int32 I = 0; I < Now.Num(); ++I)
        {
            TArray<FHitResult> Hits;
            Character->GetWorld()->SweepMultiByChannel(Hits, PreviousBlade[I], Now[I], FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(6.f), Params);
            for (const FHitResult& H : Hits)
            {
                AActor* A = H.GetActor();
                if (!A || A == Character || HitThisStrike.Contains(A)) continue;
                HitThisStrike.Add(A);
                if (StrikeLog.Num()) StrikeLog.Last().Targets.Add(A);
                const int32 Strength = bFullCharge ? 3 : bCharged ? 2 : 1;
                ASwordDummy* Dummy = Cast<ASwordDummy>(A); AFoxHunter* Fox = Cast<AFoxHunter>(A);
                if (Dummy) Dummy->TakeSwordHit(Strength);
                else if (Fox && Fox->IsAlive()) Fox->TakeSwordHit(Strength, Character);
                if (Dummy || Fox)
                {
                    // Hit-stop, sparks, flash and sound live in the combat effects (a short freeze of both fighters, longer when charged).
                    if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character))
                        FX->SwordHit(H.bStartPenetrating ? Now[I] : FVector(H.ImpactPoint), Now[I] - PreviousBlade[I], Strength, Character, A);
                    SetFeedback(Strength == 3 ? TEXT("heavy hit!") : Strength == 2 ? TEXT("charged hit") : TEXT("hit"));
                }
            }
        }
    }
    PreviousBlade = Now;
}

void UWandererSwordComponent::Advance(float Dt)
{
    Clock += Dt;
    if (!IsInstalled() || !Character) return;
    // Carry layer: armed and not inside a sword clip. Fades so locomotion entries stay smooth.
    const bool bClipPlaying = OwnsAction(Character->GetAnimationAction());
    // An armed version of the action (the roll, the double jump) holds the sword itself.
    const bool bArmedClip = Character->GetAnimationClip() != Character->GetAnimationAction();
    const float CarryTarget = (State != ESwordState::Stowed && !bClipPlaying && !bArmedClip && !bDown) ? 1.f : 0.f;
    // Leaving an armed clip, the base pose is already back on the unarmed locomotion arm: bring the carry back quickly.
    if (bArmedClip) bFastCarry = true; else if (Carry >= 1.f) bFastCarry = false;
    Carry = FMath::FInterpConstantTo(Carry, CarryTarget, Dt, bFastCarry ? 12.f : 5.f);
    Invulnerable = FMath::Max(0.f, Invulnerable - Dt);
    Effects(Dt);
    if (bDown)
    {
        // Knocked down: sit, stay dazed, stand up restored. Nothing else runs meanwhile.
        DownTime += Dt;
        if (DownTime < 1.2f) Character->SetAction(TEXT("SitDown"), false, .08f);
        else if (DownTime < 3.f) Character->SetAction(TEXT("SitIdle"), true, .2f);
        else if (DownTime < 4.1f) Character->SetAction(TEXT("StandUp"), false, .12f);
        else { bDown = false; Health = MaxHealth; Invulnerable = 1.5f; Character->SetAction(NAME_None, false, .16f); SetFeedback(TEXT("back on your feet")); }
        return;
    }
    if (FacingBlend > 0.f)
    {
        FacingBlend -= Dt;
        const FRotator R = Character->GetActorRotation();
        Character->SetActorRotation(FRotator(R.Pitch, FMath::FixedTurn(R.Yaw, FacingTarget, 900.f * Dt), R.Roll));
    }
    if (State == ESwordState::Stowed) return;
    const FName Playing = Character->GetAnimationAction();
    const bool bGroundIdle = Character->GetCharacterMovement()->IsMovingOnGround() && !Character->HasMovementIntent() && Character->GetVelocity().Size2D() < 12.f && !Character->bIsCrouched;
    const float T = Character->GetActionSourceTime();
    const FWandererSwordClip* C = Clip(CurrentClip);
    if (StepInRemaining > 0.f)
    {
        if ((State == ESwordState::Attack || State == ESwordState::ChargeRelease) && C && T < C->ActiveStart + .05f && Character->GetCharacterMovement()->IsMovingOnGround())
        { const float Step = FMath::Min(StepInRemaining, 350.f * Dt); Character->AddActorWorldOffset(StepInDir * Step, true); StepInRemaining -= Step; }
        else StepInRemaining = 0.f;
    }
    // Something outside the sword (a fall, a roll, a landing) replaced the clip: return to the guard quietly.
    if (!CurrentClip.IsNone() && Playing != CurrentClip && State != ESwordState::Guard)
    {
        State = ESwordState::Guard; CurrentClip = NAME_None; bPendingDrawAttack = false;
    }
    switch (State)
    {
        case ESwordState::Guard:
            // Standing still plays the armed stand (the guard on older content); any movement hands the body to locomotion with
            // the right-arm carry layer.
            if (bGroundIdle && Playing.IsNone() && !Character->bPendingTakeoff) { Character->SetAction(StandClip(), true, .2f); CurrentClip = StandClip(); }
            else if (!bGroundIdle && Playing == StandClip()) { Character->SetAction(NAME_None, false, .14f); CurrentClip = NAME_None; }
            else if (Playing == StandClip()) CurrentClip = StandClip();
            break;
        case ESwordState::Draw:
            if (C && T >= C->Duration)
            {
                Enter(ESwordState::Guard, NAME_None, .12f);
                if (bPendingDrawAttack) { bPendingDrawAttack = false; if (Character->CanAct()) StartAttack(1, .07f); }
            }
            break;
        case ESwordState::Sheath:
            if (C && T >= C->Duration) { State = ESwordState::Stowed; CurrentClip = NAME_None; Character->SetAction(NAME_None, false, .12f); UpdateSwordVisibility(); }
            break;
        case ESwordState::Attack:
        {
            if (!C) { Enter(ESwordState::Guard, NAME_None, .14f); break; }
            // The first cut is too quick to charge before it lands: a press still held once it has landed winds up the charge
            // from the follow-through (the cut stays a strike of its own).
            if (ComboIndex == 1 && bAttackHeld && Clock - AttackStartClock >= HoldThreshold && T >= C->ActiveEnd && !bCounterStrike)
            {
                Enter(ESwordState::ChargeUp, TEXT("SwordChargeUp"), .12f); ChargeTime = 0.f; bChargeFromStrike = false; SetFeedback(TEXT("charging")); break;
            }
            if (T >= C->ActiveStart && T <= C->ActiveEnd) SweepBlade(Dt); else PreviousBlade.Reset();
            if (C->LinkStart >= 0.f && T >= C->LinkStart && ComboIndex < 3 && LastAttackPress > Clock - BufferWindow && LastAttackPress > AttackStartClock + .02f)
            {
                LastAttackPress = -100.f; StartAttack(ComboIndex + 1, .1f); break;
            }
            if (T >= C->Duration) Enter(ESwordState::Guard, NAME_None, .14f);
            else if (C->Cancel >= 0.f && T >= C->Cancel && Character->HasMovementIntent()) Enter(ESwordState::Guard, NAME_None, .16f);
            break;
        }
        case ESwordState::ChargeUp:
            if (!bAttackHeld) { AttackReleased(); break; }
            if (C && T >= C->Duration) { Enter(ESwordState::ChargeHold, TEXT("SwordChargeHold"), .1f, 1.f, true); ChargeTime = 0.f; }
            break;
        case ESwordState::ChargeHold:
            ChargeTime += Dt;
            if (!bAttackHeld) { AttackReleased(); break; }
            if (ChargeTime >= FullChargeTime && !bFullCharge)
            {
                bFullCharge = true; SetFeedback(TEXT("charged: full"));
                if (AJapanCombatFX* FX = AJapanCombatFX::Get(Character)) FX->ChargeReady(BladeTipWorld());
            }
            break;
        case ESwordState::ChargeRelease:
        {
            if (!C) { Enter(ESwordState::Guard, NAME_None, .14f); break; }
            if (T >= C->ActiveStart && T <= C->ActiveEnd) SweepBlade(Dt); else PreviousBlade.Reset();
            // A full charge lands heavier: a hit-stop on contact, and a slower settle after the cut.
            if (bFullCharge && T > C->ActiveEnd && Character->ActionPlayRate > .85f)
            {
                const float Old = Character->ActionPlayRate; Character->ActionSourceStartTime += Character->ActionTime * (Old - .8f); Character->ActionPlayRate = .8f;
            }
            if (T >= C->Duration) Enter(ESwordState::Guard, NAME_None, .16f);
            else if (C->Cancel >= 0.f && T >= C->Cancel && Character->HasMovementIntent()) Enter(ESwordState::Guard, NAME_None, .16f);
            break;
        }
        case ESwordState::Parry:
            if (!C || T >= C->Duration) Enter(ESwordState::Guard, NAME_None, .14f);
            else if (C->Cancel >= 0.f && T >= C->Cancel && Character->HasMovementIntent()) Enter(ESwordState::Guard, NAME_None, .16f);
            break;
        case ESwordState::ParryHit:
            if (C && T >= (C->Counter >= 0.f ? C->Counter : C->Duration)) StartAttack(1, .08f);
            break;
        default: break;
    }
}

/** Cosmetic per-frame feedback: the slash trail while the blade cuts, the whoosh just before contact, charge embers. */
void UWandererSwordComponent::Effects(float Dt)
{
    if (!Trail || !Character) return;
    const FWandererSwordClip* C = Clip(CurrentClip);
    const float T = Character->GetActionSourceTime();
    const bool bCutting = (State == ESwordState::Attack || State == ESwordState::ChargeRelease) && C && C->ActiveStart >= 0.f && T >= C->ActiveStart - .05f && T <= C->ActiveEnd + .04f;
    const int32 Strength = State == ESwordState::ChargeRelease ? (bFullCharge ? 3 : 2) : 1;
    TArray<FVector> Points; BladePoints(Points);
    if (Points.Num() == 6 && Blade && Blade->IsVisible())
    {
        const FVector Tip = Points[5] + (Points[5] - Points[4]) * .5f;
        Trail->Sample(FMath::Lerp(Points[0], Points[5], .55f), Tip, bCutting, Strength, Dt);
    }
    else Trail->Sample(FVector::ZeroVector, FVector::ZeroVector, false, 1, Dt);
    AJapanCombatFX* FX = AJapanCombatFX::Get(Character);
    if (!FX) return;
    if ((State == ESwordState::Attack || State == ESwordState::ChargeRelease) && C && !bSwingCue && T >= C->ActiveStart - .06f)
    {
        bSwingCue = true; FX->SwordSwing(Points.Num() ? Points[3] : Character->GetActorLocation(), Strength);
    }
    if ((State == ESwordState::ChargeUp || State == ESwordState::ChargeHold) && Points.Num() == 6)
        FX->ChargeTick(Points[0], Points[5], State == ESwordState::ChargeHold ? FMath::Clamp(ChargeTime / FullChargeTime, 0.f, 1.f) : 0.f, Dt);
}

// ------------------------------------------------------------------ training dummy
ASwordDummy::ASwordDummy()
{
    PrimaryActorTick.bCanEverTick = true;
    Post = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Post"));
    SetRootComponent(Post);
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    if (Cylinder.Succeeded()) Post->SetStaticMesh(Cylinder.Object);
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Basic(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    if (Basic.Succeeded()) Post->SetMaterial(0, Basic.Object);
    Post->SetRelativeScale3D(FVector(.5f, .5f, 1.4f));
    Post->SetCollisionProfileName(TEXT("BlockAll"));
    Post->SetCastShadow(true);
}

void ASwordDummy::Tick(float Dt)
{
    Super::Tick(Dt);
    Clock += Dt;
    if (!Paint && Post && Post->GetMaterial(0)) { Paint = Post->CreateDynamicMaterialInstance(0); }
    if (Stagger > 0.f) Stagger -= Dt;
    if (Flash > 0.f) Flash -= Dt;
    if (AutoPeriod > 0.f && Windup < 0.f && Stagger <= 0.f) { AutoClock += Dt; if (AutoClock >= AutoPeriod) { AutoClock = 0.f; StrikeIn(.6f); } }
    if (Windup >= 0.f)
    {
        Windup -= Dt;
        // Telegraph: the post leans toward the player during the wind-up and snaps back when the swing lands.
        Post->SetRelativeScale3D(FVector(.5f, .5f, 1.4f + .25f * FMath::Sin(PI * FMath::Clamp(1.f - Windup / .6f, 0.f, 1.f))));
        if (Windup < 0.f)
        {
            Post->SetRelativeScale3D(FVector(.5f, .5f, 1.4f));
            if (Target && Target->GetSword() && FVector::Dist2D(Target->GetActorLocation(), GetActorLocation()) <= Reach)
            {
                if (Target->GetSword()->IncomingStrike(this)) { ++StrikesParried; Stagger = 1.2f; }
                else ++StrikesLanded;
            }
            else ++StrikesMissed;
        }
    }
    if (Paint)
    {
        const FLinearColor Base(.55f, .38f, .2f);
        const FLinearColor Color = Flash > 0.f ? FLinearColor(1.f, .25f, .15f) : Stagger > 0.f ? FLinearColor(.3f, .55f, 1.f) : Windup >= 0.f ? FLinearColor(1.f, .85f, .3f) : Base;
        Paint->SetVectorParameterValue(TEXT("Color"), Color);
    }
}

void ASwordDummy::TakeSwordHit(int32 Strength)
{
    ++HitsTaken; LastHitTime = Clock; Flash = .15f + .05f * Strength;
    if (Strength >= 3) { Windup = -1.f; Stagger = FMath::Max(Stagger, .8f); }
    UE_LOG(LogTemp, Display, TEXT("SWORD DUMMY hit strength=%d total=%d"), Strength, HitsTaken);
}

void ASwordDummy::StrikeIn(float WindupSeconds) { if (Stagger <= 0.f) Windup = WindupSeconds; }
