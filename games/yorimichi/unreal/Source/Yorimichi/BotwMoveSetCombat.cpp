#include "BotwMoveSet.h"
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

// ---------------------------------------------------------------------------------------------------------- Combat

bool UBotwMoveSet::Press(FName Button)
{
    if (!Character) return false;
    const FName Name = CurrentName();
    if (Button == TEXT("jump"))
    {
        bJumpHeld = true;
        if (bDown) return true;
        switch (Mode)
        {
        case EBotwMoveMode::Ground:
        {
            // The parry: the shield's, or without it the sword's (the shield's clip when an older build lacks it).
            const FName Parry = !HasShield() && Has(TEXT("SwordParry")) ? FName(TEXT("SwordParry")) : FName(TEXT("Parry"));
            if (IsGuarding() && Has(Parry) && (!Busy() || (IsGuardHit(Name) && Current() && SourceTime() >= Current()->Input)))
            {
                Play(Parry, .03f);
                if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character)) FX->Play(TEXT("sword_swing"), GuardPoint(), .55f, .08f);
                return true;
            }
        }
            if (bLocked && !bArmed) { if (CanDodge()) StartHop(); return true; }
            if (CanJump()) StartJump(); else JumpBuffer = .15f;
            return true;
        case EBotwMoveMode::Air:
            if (CanJump()) { StartJump(); return true; }   // just off an edge
            if (CanDoubleJump()) { StartDoubleJump(); return true; }   // Cairo's double jump first, then the glider
            if (CanGlide()) OpenGlider(); else JumpBuffer = .2f;
            return true;
        case EBotwMoveMode::Glide: CloseGlider(false); return true;
        default: JumpBuffer = .15f; return true;
        }
    }
    if (Button == TEXT("jump_release")) { bJumpHeld = false; return true; }
    if (Button == TEXT("dodge"))
    {
        if (bDown) return true;
        if (Mode == EBotwMoveMode::Ground) { if (CanDodge()) StartHop(); }
        else if (Mode == EBotwMoveMode::Glide) CloseGlider(false);
        else if (Mode == EBotwMoveMode::Climb && !(bDriving && !bDriveSweep)) LeaveClimb(true);   // not while pulling up onto a ledge
        return true;
    }
    if (Button == TEXT("attack"))
    {
        bAttackHeld = true; AttackPressTime = Clock;
        if (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air) AttackBuffer = .35f;
        return true;
    }
    if (Button == TEXT("attack_release")) { bAttackHeld = false; return true; }
    if (Button == TEXT("guard"))
    {
        // Guarding takes the sword in hand (and the shield with it): sheathed, the press draws.
        bGuardHeld = true;
        if (!bLegacy && Mode == EBotwMoveMode::Ground && !bArmed && !bDown && !Busy() && Has(TEXT("DrawSword"))) { Play(TEXT("DrawSword")); bAttackAfterDraw = false; }
        return true;
    }
    if (Button == TEXT("guard_release")) { bGuardHeld = false; return true; }
    if (Button == TEXT("weapon"))
    {
        if (Mode != EBotwMoveMode::Ground || bDown || Busy()) return true;
        if (bArmed && Has(TEXT("SheatheSword"))) Play(TEXT("SheatheSword"));
        else if (!bArmed && Has(TEXT("DrawSword"))) { Play(TEXT("DrawSword")); bAttackAfterDraw = false; }
        else SetArmed(!bArmed);
        return true;
    }
    if (Button == TEXT("crouch")) return Mode != EBotwMoveMode::Ground || bDown || Busy();   // on foot the character crouches as usual
    if (Button == TEXT("dash")) { if (Mode == EBotwMoveMode::Swim) JumpBuffer = .15f; return true; }   // no air dash; the swim's dash
    return false;
}

void UBotwMoveSet::StartCut(int32 Index)
{
    const FName Clip = CutNames[FMath::Clamp(Index, 0, 3)];
    if (!Has(Clip)) return;
    if (Character->bIsCrouched) Character->UnCrouch();
    Face(600.f);
    Combo = Index; AttackBuffer = 0.f; bAttackAfterDraw = false;
    // BOTW homes a cut onto the enemy it is aimed at: a quick step in when it stands beyond the blade's reach. The cuts'
    // clips open mid-swing, so the step is short and the blow keeps landing until it has closed in.
    LungeTime = 0.f; LungeTarget = nullptr;
    if (AActor* Focus = Target.IsValid() ? Target.Get() : FindTarget(Reach() + 250.f, 60.f))
    {
        float Radius = 0.f, Half = 0.f;
        Focus->GetSimpleCollisionCylinder(Radius, Half);
        const float Stand = Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + Radius + BladeLength() * .7f;
        const float Gap = float(FVector::Dist2D(Focus->GetActorLocation(), Character->GetActorLocation())) - Stand;
        if (Gap > 5.f) { LungeTarget = Focus; LungeStand = Stand; LungeTime = FMath::Clamp(Gap / 1100.f, .06f, .16f); }
    }
    if (const FBotwMove* M = Current())
    {
        float End = -1.f;
        for (const FVector2f& W : M->Active) End = FMath::Max(End, W.Y);
        ArcEnd = LungeTime > 0.f ? FMath::Max(End, M->Start + (LungeTime + .08f) * M->Rate) : End;
    }
    Play(Clip, .05f);
}

/** Turns to the nearest enemy in reach and in front (a soft lock), else to the stick. */
void UBotwMoveSet::Face(float Range)
{
    AActor* Focus = Target.IsValid() ? Target.Get() : FindTarget(Range, 70.f);
    FVector Toward = Focus ? FVector(Focus->GetActorLocation() - Character->GetActorLocation()) : Wish();
    Toward.Z = 0.;
    if (Toward.SizeSquared() > 1.) Character->SetActorRotation(FRotator(0, Toward.Rotation().Yaw, 0));
}

void UBotwMoveSet::StartAttack()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (Mode == EBotwMoveMode::Air)
    {
        if (IsAttack(Name) || IsHop(Name) || bDown) return;
        AttackBuffer = 0.f;
        if (!bArmed) SetArmed(true);
        FHitResult Below;
        const FVector Here = Character->GetActorLocation();
        const bool bHigh = !Trace(Here, Here - FVector(0, 0, HalfHeight() + GetParam(TEXT("PlungeHeight"), 300.f)), Below);
        if (bHigh && Has(TEXT("Plunge")))
        {
            Play(TEXT("Plunge"), .05f);
            Movement->Velocity = FVector(0, 0, FMath::Min(float(Movement->Velocity.Z), -1200.f));
            FallStartZ = Here.Z;   // no fall damage
        }
        else if (Has(TEXT("JumpCut")))
        {
            Face(500.f);
            const float S = Scale();
            HopVelocity = Character->GetActorForwardVector() * GetParam(TEXT("PlayerCutJump.CutJumpSpeedF"), .16f) * 3000.f * S;
            Movement->Velocity.Z = FMath::Max(float(Movement->Velocity.Z), 250.f);
            Play(TEXT("JumpCut"), .05f);
        }
        return;
    }
    if (Mode != EBotwMoveMode::Ground || bDown) return;
    // The flurry rush: a perfect dodge slowed the world; each press is the next blow of the rush.
    if (InFlurry() && bArmed)
    {
        int32 Next = 0;
        for (int32 I = 0; I < RushCount; ++I) if (Name == RushNames[I]) Next = I + 1;
        if (Next > 0 && Now && SourceTime() < Now->Input) return;   // too early: keep it buffered
        if (Next >= RushCount) return;
        if (Next == RushCount - 1 || FlurryTime < .5f) Next = RushCount - 1;
        if (!Has(RushNames[Next])) return;
        AttackBuffer = 0.f; Face(1200.f);
        Play(RushNames[Next], .04f);
        return;
    }
    // The combo: each cut takes the next press from its input point.
    for (int32 I = 0; I < 4; ++I)
        if (Name == CutNames[I])
        {
            if (!Now || SourceTime() < Now->Input) return;
            if (I == 3 && SourceTime() < FreeAt(*Now)) return;
            StartCut(I == 3 ? 0 : I + 1);
            return;
        }
    if (Name == TEXT("DrawSword"))
    {
        bAttackAfterDraw = true;
        if (Now && SourceTime() >= Now->Input) StartCut(0);
        return;
    }
    if (Busy()) return;
    // Crouched behind an unaware enemy: the sneakstrike, drawing the sword in the same motion.
    if (Character->bIsCrouched && Has(TEXT("Sneakstrike")))
        if (AActor* Victim = FindTarget(Reach() + 120.f, 60.f); Victim && IsUnawareTarget(Victim))
        {
            SetArmed(true);
            Character->UnCrouch();
            Target = Victim; Face(Reach() + 120.f); Target = nullptr;
            AttackBuffer = 0.f;
            Play(TEXT("Sneakstrike"), .06f);
            return;
        }
    // Sprinting: the dash attack, driven along its clip (drawing the sword in the same motion).
    if (Character->Stamina.Sprinting && Has(TEXT("DashCut")))
    {
        SetArmed(true);
        AttackBuffer = 0.f; Face(700.f);
        Play(TEXT("DashCut"), .04f); BeginDrive(true);
        return;
    }
    if (!bArmed)
    {
        // Unarmed, the press draws the sword and cuts as soon as the draw allows.
        if (Has(TEXT("DrawSword"))) { Play(TEXT("DrawSword"), .1f); bAttackAfterDraw = true; AttackBuffer = 0.f; return; }
        SetArmed(true);
    }
    StartCut(0);
}

void UBotwMoveSet::AdvanceCombat(float Dt)
{
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    LungeTime = FMath::Max(0.f, LungeTime - Dt);
    if (!IsAttack(Name)) { LungeTime = 0.f; ArcEnd = -1.f; }
    // The blade hits inside the playing clip's active windows: what it sweeps through, and what stands in its arc; a
    // homing cut's arc lasts until it has closed in.
    const bool bActive = Now && bArmed && Now->Active.Num() && Now->InWindow(Now->Active, SourceTime());
    if (bActive) SweepBlade(); else PreviousBlade.Reset();
    if (bActive || (Now && bArmed && IsAttack(Name) && SourceTime() <= ArcEnd)) SweepArc();
    if (Mode != EBotwMoveMode::Ground && Mode != EBotwMoveMode::Air) { AttackBuffer = 0.f; bCharging = false; return; }
    // The draw that an attack press started cuts from its input point.
    if (Name == TEXT("DrawSword") && bAttackAfterDraw && Now && SourceTime() >= Now->Input && bArmed) StartCut(0);
    // Holding the button through the first cut, or standing armed, charges the spin attack.
    if (bAttackHeld && bArmed && Mode == EBotwMoveMode::Ground && !bCharging && !InFlurry() && Has(TEXT("ChargeStart")) && Has(TEXT("ChargeSpin")) &&
        Clock - AttackPressTime > GetParam(TEXT("ChargeHold"), .35f) && (Name.IsNone() || IsLockLoop(Name) || Name == TEXT("CutS1")))
    {
        bCharging = true; bFullCharge = false; ChargeTime = 0.f; AttackBuffer = 0.f;
        Play(TEXT("ChargeStart"), .12f);
    }
    if (bCharging)
    {
        if (!In(CurrentName(), { TEXT("ChargeStart"), TEXT("ChargeWait") })) bCharging = false;
        else
        {
            ChargeTime += Dt;
            UseStamina(GetParam(TEXT("EnergyCharge"), 250.f) / 1000.f * Dt);
            const float Full = GetParam(TEXT("FullCharge"), .9f);
            AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character);
            TArray<FVector> Blade; BladePoints(Blade);
            if (FX && Blade.Num()) FX->ChargeTick(Blade[0], Blade.Last(), FMath::Clamp(ChargeTime / Full, 0.f, 1.f), Dt);
            if (!bFullCharge && ChargeTime >= Full) { bFullCharge = true; if (FX && Blade.Num()) FX->ChargeReady(Blade.Last()); }
            if (!bAttackHeld || Character->Stamina.Exhausted)
            {
                bCharging = false;
                if (ChargeTime >= GetParam(TEXT("MinCharge"), .5f)) { Play(TEXT("ChargeSpin"), .06f); BeginDrive(true); }
                else Stop(.15f);
            }
        }
        return;
    }
    if (AttackBuffer > 0.f) StartAttack();
}

void UBotwMoveSet::BladePoints(TArray<FVector>& Out) const
{
    Out.Reset();
    const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword"));
    if (!Sword || !*Sword || BladeTip.IsNearlyZero()) return;
    const FTransform& T = (*Sword)->GetComponentTransform();
    for (int32 I = 0; I < 6; ++I) Out.Add(T.TransformPosition(FMath::Lerp(BladeBase, BladeTip, I / 5.f)));
}

void UBotwMoveSet::SweepBlade()
{
    TArray<FVector> Now; BladePoints(Now);
    if (Now.IsEmpty()) return;
    if (!bSwung) { bSwung = true; if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character)) FX->SwordSwing(Now.Last(), FMath::Min(Strength, 3)); }
    if (PreviousBlade.Num() == Now.Num())
    {
        FCollisionQueryParams Query(SCENE_QUERY_STAT(BotwBlade), false, Character);
        for (int32 I = 0; I < Now.Num(); ++I)
        {
            TArray<FHitResult> Hits;
            Character->GetWorld()->SweepMultiByChannel(Hits, PreviousBlade[I], Now[I], FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(8.f), Query);
            for (const FHitResult& H : Hits)
            {
                AActor* A = H.GetActor();
                if (!A || A == Character || HitThisSwing.Contains(A) || !IsTargetable(A)) continue;
                HitThisSwing.Add(A);
                Strike(A, Strength, H.bStartPenetrating ? Now[I] : FVector(H.ImpactPoint), Now[I] - PreviousBlade[I]);
            }
        }
    }
    PreviousBlade = Now;
}

void UBotwMoveSet::SweepArc()
{
    const FVector Here = Character->GetActorLocation();
    const FVector Forward = Character->GetActorForwardVector();
    const float Range = Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + BladeLength() + 20.f;
    auto Consider = [&](AActor* A)
    {
        if (!A || A == Character || HitThisSwing.Contains(A) || !IsTargetable(A)) return;
        float Radius = 0.f, Half = 0.f;
        A->GetSimpleCollisionCylinder(Radius, Half);
        const FVector To = (A->GetActorLocation() - Here) * FVector(1, 1, 0);
        if (To.Size() - Radius > Range || (Forward | To.GetSafeNormal()) < FMath::Cos(FMath::DegreesToRadians(75.f))) return;
        if (FMath::Abs(A->GetActorLocation().Z - Here.Z) > Half + HalfHeight()) return;
        HitThisSwing.Add(A);
        const FVector At = A->GetActorLocation() - To.GetSafeNormal() * Radius + FVector(0, 0, HalfHeight() * .3f);
        Strike(A, Strength, At, Forward);
    };
    // The few things a blade can strike (IsTargetable), found directly rather than through a collision channel.
    UWorld* World = Character->GetWorld();
    for (TActorIterator<ABotwCreature> It(World); It; ++It) Consider(*It);
    for (TActorIterator<AFoxHunter> It(World); It; ++It) Consider(*It);
    for (TActorIterator<ASwordDummy> It(World); It; ++It) Consider(*It);
    for (TActorIterator<AWandererCharacter> It(World); It; ++It) Consider(*It);
}

float UBotwMoveSet::BladeLength() const
{
    const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword"));
    return Sword && *Sword ? float((BladeTip * (*Sword)->GetComponentScale()).Size()) : 60.f;
}

void UBotwMoveSet::Strike(AActor* Victim, int32 Power, const FVector& At, const FVector& Direction)
{
    // A sparring partner meets the blow with its own move set: its guard, parry and dodges answer it as they answer a
    // fox's claw, and only a blow that lands counts (the guard, parry and dodge make their own effects).
    if (AWandererCharacter* Other = Cast<AWandererCharacter>(Victim))
    {
        UBotwMoveSet* Theirs = Other->GetMoves();
        if (!Theirs || Theirs->IncomingStrike(Character, Character->SparringDamage(Power), Character->GetActorLocation()) != 0) return;
        ++HitCount;
        if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character)) FX->SwordHit(At, Direction, FMath::Clamp(Power, 1, 3), Character, Victim);
        return;
    }
    if (ASwordDummy* Dummy = Cast<ASwordDummy>(Victim)) Dummy->TakeSwordHit(FMath::Min(Power, 3));
    else if (AFoxHunter* Fox = Cast<AFoxHunter>(Victim)) Fox->TakeSwordHit(FMath::Min(Power, 3), Character);
    else if (ABotwCreature* Creature = Cast<ABotwCreature>(Victim)) Creature->TakeSwordHit(Power, Character);
    else return;
    ++HitCount;
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character)) FX->SwordHit(At, Direction, FMath::Clamp(Power, 1, 3), Character, Victim);
}

int32 UBotwMoveSet::IncomingStrike(AActor* Source, float Damage, const FVector& From)
{
    if (!Character) return 0;
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character);
    const FVector Here = Character->GetActorLocation();
    const FVector Toward = (From - Here).GetSafeNormal2D();
    // The parry, shield or sword: the strike bounces off and the striker staggers.
    if (Now && IsParry(Name) && Now->InWindow(Now->Guard, SourceTime()))
    {
        ++ParryCount;
        if (FX)
        {
            const FVector At = GuardPoint();
            FX->Parry(At, Character, Source);
            if (Name == TEXT("SwordParry"))
            {
                // Steel on steel: a fan of hot sparks off the blade toward the striker, and a second, brighter ring.
                FX->Burst(At, Toward, 26, 1700.f, FLinearColor(1.f, .7f, .3f) * 9.f, .3f, 2.6f);
                AAtelierFX::FParticle& Ring = FX->Spawn(AAtelierFX::ESprite::Ring, At); Ring.Size0 = 12.f; Ring.Size1 = 200.f; Ring.Life = .24f;
                Ring.Color = FLinearColor(1.f, .82f, .5f) * 3.f;
                FX->Play(TEXT("hit_heavy"), At, .45f, .06f);
            }
        }
        if (ABotwCreature* Creature = Cast<ABotwCreature>(Source)) Creature->TakeSwordHit(0, Character);
        else if (AWandererCharacter* Other = Cast<AWandererCharacter>(Source); Other && Other->GetMoves()) Other->GetMoves()->Deflected(Character);
        return 1;
    }
    // A hop or backflip in the air: dodged; just as the strike lands, a perfect dodge and the flurry rush.
    if (IsHop(Name) && Invulnerable > 0.f)
    {
        ++DodgeCount;
        if (JustAvoid > 0.f && (bArmed || Has(TEXT("DrawSword"))) && Has(TEXT("Flurry")))
        {
            FlurryTime = GetParam(TEXT("PlayerCutAfterJust.ForceSlowTime"), 80.f) / 30.f;
            Invulnerable = FlurryTime;
            Target = Source;
            // A character the game drives rushes without slowing the world (the person it fights keeps their own time).
            if (!Character->IsPlayerControlled()) FlurryTime = FMath::Min(FlurryTime, 1.4f);
            else if (FX)
            {
                FX->SlowMotion(FlurryTime, GetParam(TEXT("FlurryDilation"), .25f));
                // The perfect dodge: a cold flash and a wide ring where he was, and a chime.
                const FVector Chest = Here + FVector(0, 0, HalfHeight() * .3f);
                FX->Flash(Chest, 110.f, FLinearColor(.6f, .82f, 1.f) * 3.f, .2f);
                AAtelierFX::FParticle& Ring = FX->Spawn(AAtelierFX::ESprite::Ring, Chest); Ring.Size0 = 30.f; Ring.Size1 = 260.f; Ring.Life = .4f;
                Ring.Color = FLinearColor(.55f, .78f, 1.f) * 2.6f;
                FX->LightFlash(Chest, FLinearColor(.6f, .8f, 1.f), 9000.f, 500.f, .25f);
                FX->Play(TEXT("charge_ready"), Chest, .8f, .02f);
            }
            if (!bArmed) SetArmed(true);
        }
        return 2;
    }
    if (bDown || Invulnerable > 0.f || InFlurry()) return 3;
    // Guarding with the shield toward the strike: absorbed, pushed back a little.
    const float Guardable = GetParam(TEXT("GuardableAngle"), 120.f) * .5f;
    if (IsGuarding() && Mode == EBotwMoveMode::Ground && (Character->GetActorForwardVector() | Toward) >= FMath::Cos(FMath::DegreesToRadians(Guardable)))
    {
        const float Side = Character->GetActorRotation().UnrotateVector(From - Here).Y;
        // A heavy blow (a full charge, full power) breaks the guard: the arms thrown wide, the guard down for a moment.
        if (Damage >= GetParam(TEXT("GuardBreakDamage"), 25.f))
        {
            const FName Break = !HasShield() && Has(TEXT("SwordGuardBreak")) ? FName(TEXT("SwordGuardBreak")) : FName(TEXT("GuardBreak"));
            if (Has(Break)) Play(Break, .04f);
            GuardBroken = GetParam(TEXT("GuardBreakTime"), 1.f); ++GuardBreakCount;
            bCharging = false; AttackBuffer = 0.f;
            Character->GetCharacterMovement()->Velocity = -Toward * 380.f;
            Flinch(-Toward, 18.f, .09f, Side);
            if (FX)
            {
                const FVector At = GuardPoint();
                FX->Burst(At, -Toward, 26, 1100.f, FLinearColor(1.f, .8f, .45f) * 7.f, .3f, 3.f);
                FX->Flash(At, 70.f, FLinearColor(1.f, .8f, .5f) * 3.f, .12f);
                FX->Play(TEXT("hit_heavy"), At, .8f, .05f);
                FX->Shake(.6f);
            }
            return 3;
        }
        const FName Hit = !HasShield() && Has(TEXT("SwordGuardHit")) ? FName(TEXT("SwordGuardHit")) : FName(TEXT("GuardHit"));
        if (Has(Hit)) Play(Hit, .03f);
        Character->GetCharacterMovement()->Velocity = -Toward * 220.f;
        Flinch(-Toward, 7.f, .06f, Side);
        if (FX)
        {
            const FVector At = GuardPoint();
            FX->Burst(At, -Toward, 14, 700.f, FLinearColor(1.f, .85f, .55f) * 4.f, .25f, 3.f);
            FX->Play(TEXT("parry"), At, .6f, .06f);
            FX->Shake(.2f);
        }
        return 3;
    }
    TakeHit(Damage, From, Damage >= GetParam(TEXT("HeavyDamage"), 25.f), Source, true);
    return 0;
}

FVector UBotwMoveSet::GuardPoint() const
{
    if (HasShield())
        if (const TObjectPtr<UStaticMeshComponent>* Shield = Props.Find(TEXT("shield")); Shield && *Shield) return (*Shield)->Bounds.Origin;
    TArray<FVector> Blade; BladePoints(Blade);
    if (Blade.Num()) return Blade[Blade.Num() / 2];
    return Character->GetActorLocation() + Character->GetActorForwardVector() * 30.f + FVector(0, 0, 30.f);
}

void UBotwMoveSet::Deflected(AActor* By)
{
    if (!Character || bDown || Mode != EBotwMoveMode::Ground) return;
    bCharging = false; AttackBuffer = 0.f; LungeTime = 0.f;
    // Thrown back off the guard: the front stagger, a step back, the next blow from scratch.
    const FVector Away = By ? FVector((Character->GetActorLocation() - By->GetActorLocation()).GetSafeNormal2D()) : -Character->GetActorForwardVector();
    if (Has(TEXT("HitMF"))) Play(TEXT("HitMF"), .04f);
    else if (Has(TEXT("HitF"))) Play(TEXT("HitF"), .04f);
    Character->GetCharacterMovement()->Velocity = Away * 320.f;
    Flinch(Away, 16.f, .08f, 0.f);
    Combo = 0;
}

bool UBotwMoveSet::IsAttacking() const { return IsAttack(CurrentName()) || bCharging; }
bool UBotwMoveSet::IsHopping() const { return IsHop(CurrentName()); }

float UBotwMoveSet::NextCutIn() const
{
    const FBotwMove* M = Current();
    if (!M) return -1.f;
    for (int32 I = 0; I < 3; ++I)
        if (M->Name == CutNames[I]) return FMath::Max(0.f, (M->Input - SourceTime()) / FMath::Max(Character->GetActionPlayRate(), .05f));
    return -1.f;
}

float UBotwMoveSet::NextBlowIn() const
{
    const FBotwMove* M = Current();
    if (!M || !IsAttack(M->Name) || M->Active.IsEmpty()) return -1.f;
    const float T = SourceTime();
    float Next = -1.f;
    for (const FVector2f& W : M->Active)
    {
        if (T >= W.X && T <= W.Y) return 0.f;
        if (W.X > T && (Next < 0.f || W.X < Next)) Next = W.X;
    }
    const float Rate = FMath::Max(Character->GetActionPlayRate(), .05f);
    return Next < 0.f ? -1.f : (Next - T) / Rate;
}

void UBotwMoveSet::TakeHit(float Damage, const FVector& From, bool bHeavy, AActor* Source, bool bReact)
{
    UWandererSwordComponent* Sword = Character->GetSword();
    if (!Sword) return;
    ++Sword->HitsTakenCount;
    Sword->Health = FMath::Max(0.f, Sword->Health - Damage);
    Invulnerable = FMath::Max(Invulnerable, .7f);
    const bool bKnock = bHeavy || Sword->Health <= 0.f;
    if (AYorimichiCombatFX* FX = Character->IsNpc() ? nullptr : AYorimichiCombatFX::Get(Character))   // the striker's blade made the NPC's
    {
        const FVector Chest = Character->GetActorLocation() + FVector(0, 0, 20);
        FX->PlayerHurt(Chest + (From - Chest).GetSafeNormal2D() * 18.f, From, Damage, Character, Source, bKnock);
    }
    if (!bReact) return;
    bCharging = false; AttackBuffer = 0.f;
    if (Mode == EBotwMoveMode::Glide) CloseGlider(false);
    else if (Mode == EBotwMoveMode::Climb) LeaveClimb(true);
    if (Mode == EBotwMoveMode::Swim) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Local = Character->GetActorRotation().UnrotateVector(From - Character->GetActorLocation());
    const bool bFront = Local.X >= 0.f;
    const bool bSide = FMath::Abs(Local.X) < FMath::Abs(Local.Y);
    const FVector Away = (Character->GetActorLocation() - From).GetSafeNormal2D();
    // The way the blow came: front, back, or the side it struck (R: from his right).
    const TCHAR* Dir = bSide ? (Local.Y > 0 ? TEXT("R") : TEXT("L")) : (bFront ? TEXT("F") : TEXT("B"));
    HitStreak = SinceHit < GetParam(TEXT("StaggerStreakTime"), 1.2f) ? HitStreak + 1 : 1;
    SinceHit = 0.f;
    if (bKnock && Has(TEXT("KnockF")) && Has(TEXT("KnockB")))
    {
        bDown = true; DownTime = 0.f; HitStreak = 0;
        const FName Knock(*(FString(TEXT("Knock")) + Dir));
        Play(Has(Knock) ? Knock : FName(bFront ? TEXT("KnockF") : TEXT("KnockB")), .05f);
        Flinch(Away, 12.f, .06f, Local.Y);
        Character->LaunchCharacter(Away * 380.f + FVector(0, 0, 280.f), true, true);
        return;
    }
    // A strong blow, or the third hit in quick succession, staggers: BOTW's medium reaction, a bigger recoil, pushed
    // further. Anything lighter flinches.
    const bool bStagger = (Damage >= GetParam(TEXT("StaggerDamage"), 15.f) || HitStreak >= 3) && Has(TEXT("HitMF"));
    const FName Clip(*(FString(bStagger ? TEXT("HitM") : TEXT("Hit")) + Dir));
    if (Has(Clip)) Play(Clip, .05f);
    if (bStagger) { ++StaggerCount; HitStreak = 0; }
    Flinch(Away, bStagger ? 24.f : 15.f, bStagger ? .09f : .07f, Local.Y);
    if (Movement->IsMovingOnGround()) Movement->Velocity = Away * (bStagger ? 380.f : 160.f);   // a flinch leaves him in reach of the next cut
}

void UBotwMoveSet::Flinch(const FVector& Away, float Degrees, float Peak, float Side)
{
    // Bent away from the blow (about the horizontal axis across it), twisted a little away from the struck side.
    FlinchAxis = FVector::CrossProduct(FVector::UpVector, Away.GetSafeNormal2D());
    if (FlinchAxis.IsNearlyZero()) FlinchAxis = -Character->GetActorRightVector();
    FlinchAngle = Degrees * GetParam(TEXT("FlinchScale"), 1.f);
    FlinchPeak = FMath::Max(Peak, .02f);
    FlinchTwist = FMath::Sign(Side) * .45f;
    FlinchTime = 0.f;
}

FQuat UBotwMoveSet::FlinchRotation(int32 Bone) const
{
    if (FlinchTime < 0.f || !Character || !Character->GetMesh()) return FQuat::Identity;
    // An impulse response: up to its peak in FlinchPeak, then easing back (t/T e^(1 - t/T)); each bone further up the
    // chain peaks a little later, so the head whips after the chest.
    static const float Share[4] = { .3f, .35f, .15f, .2f };
    static const float Lag[4] = { 1.f, 1.15f, 1.35f, 1.55f };
    const float T = FlinchPeak * Lag[Bone & 3];
    const float U = FlinchTime / T;
    const float Amount = FlinchAngle * Share[Bone & 3] * U * FMath::Exp(1.f - U);
    const FTransform& Mesh = Character->GetMesh()->GetComponentTransform();
    const FVector Axis = Mesh.InverseTransformVectorNoScale(FlinchAxis).GetSafeNormal();
    const FVector Up = Mesh.InverseTransformVectorNoScale(FVector::UpVector).GetSafeNormal();
    return FQuat(Up, FMath::DegreesToRadians(Amount * FlinchTwist)) * FQuat(Axis, FMath::DegreesToRadians(Amount));
}

void UBotwMoveSet::AdvanceDown(float Dt)
{
    DownTime += Dt;
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (In(Name, { TEXT("KnockF"), TEXT("KnockB"), TEXT("KnockL"), TEXT("KnockR") }))
    {
        // BOTW's knockdowns end mid-tumble, curled in the air: once on the ground he falls flat into the first frame of
        // the get-up the way he fell, and lies there.
        if (DownTime > .3f && Character->GetCharacterMovement()->IsMovingOnGround())
        {
            const FName Up(*(FString(TEXT("KnockUp")) + Name.ToString().RightChop(5)));
            Play(Has(Up) ? Up : FName(TEXT("KnockUpF")), .22f, -1.f, .001f);
        }
        return;
    }
    if (In(Name, { TEXT("KnockUpF"), TEXT("KnockUpB"), TEXT("KnockUpL"), TEXT("KnockUpR") }))
    {
        // Lying (the get-up held on its first frame) until the down time is up, then he gets up.
        if (Character->GetActionPlayRate() < .01f)
        {
            if (DownTime > GetParam(TEXT("KnockDownTime"), 1.4f)) Play(Name, .1f);
            return;
        }
        if (Over() || (Now->Idle >= 0.f && SourceTime() >= Now->Idle))
        {
            bDown = false; Invulnerable = 1.f;
            if (UWandererSwordComponent* Sword = Character->GetSword(); Sword && Sword->Health <= 0.f) Sword->Health = UWandererSwordComponent::MaxHealth;
            Stop(.25f);
        }
        return;
    }
    bDown = false;
}

void UBotwMoveSet::AdvanceFlurry()
{
    if (FlurryTime <= 0.f) return;
    FlurryTime -= FApp::GetDeltaTime();
    // The world is slowed; the player is not (a hit-stop freeze, far below one, is left alone).
    if (Character->CustomTimeDilation > .1f)
    {
        const float World = Character->GetWorldSettings() ? Character->GetWorldSettings()->GetEffectiveTimeDilation() : 1.f;
        Character->CustomTimeDilation = FlurryTime > 0.f ? 1.f / FMath::Max(World, .05f) : 1.f;
    }
    if (FlurryTime <= 0.f) { FlurryTime = 0.f; Character->CustomTimeDilation = 1.f; Target = nullptr; }
}

// ------------------------------------------------------------------------------------------------------- Equipment

void UBotwMoveSet::Attach(FName Slot)
{
    const FSlot* S = Slots.Find(Slot);
    const TObjectPtr<UStaticMeshComponent>* Prop = Props.Find(Slot);
    if (!S || !Prop || !*Prop || !Character->GetMesh()) return;
    (*Prop)->AttachToComponent(Character->GetMesh(), FAttachmentTransformRules::KeepRelativeTransform, S->bInHand ? S->Hand : S->Back);
    (*Prop)->SetRelativeTransform(S->bInHand ? S->Held : S->Carry);
}

void UBotwMoveSet::SetArmed(bool bNow)
{
    if (bArmed == bNow || !Character) return;
    bArmed = bNow;
    for (auto& Pair : Slots)
    {
        const bool bHand = bNow && !Pair.Value.Hand.IsNone();
        if (bHand != Pair.Value.bInHand) { Pair.Value.bInHand = bHand; Attach(Pair.Key); }
    }
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
        FX->Play(bNow ? TEXT("sword_draw") : TEXT("sword_sheathe"), Character->GetActorLocation() + FVector(0, 0, 30), .8f);
}

void UBotwMoveSet::SetShield(bool bOn)
{
    bShield = bOn;
    if (const TObjectPtr<UStaticMeshComponent>* Shield = Props.Find(TEXT("shield")); Shield && *Shield) (*Shield)->SetVisibility(HasShield(), true);
}

void UBotwMoveSet::SetLegacy(bool bOn)
{
    bLegacy = bOn;
    if (bLegacy) { bAirJumpUsed = false; FlipTime = -1.f; }
    SetShield(bShield);   // the legacy set always carries the shield
}

int32 UBotwMoveSet::Chosen()
{
    FString Name;
    if (FParse::Value(FCommandLine::Get(), TEXT("moveset="), Name))
        return Name == TEXT("cairo") ? LegacyCairo : Name == TEXT("botw") ? LegacyBotw : Merged;
    return FMath::Clamp(FMath::RoundToInt(UJapanPreferences::Saved(TEXT("moveset"), 0.f)), 0, 2);
}

void UBotwMoveSet::AdvanceEquipment(float Dt)
{
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    const float T = SourceTime();
    if (Name == TEXT("DrawSword") && T >= FMath::Max(Now->Bind, 0.f)) SetArmed(true);
    if (Name == TEXT("SheatheSword") && T >= (Now->Unbind >= 0.f ? Now->Unbind : Now->End * .5f)) SetArmed(false);
    // The paraglider is in the hands from the opening's bind point until the closing's unbind point.
    bool bGlider = Mode == EBotwMoveMode::Glide;
    if (Now && In(Name, { TEXT("GlideOn"), TEXT("GlideOnFall") }) && T < FMath::Max(Now->Bind, 0.f)) bGlider = false;
    if (Now && Name == TEXT("GlideOff") && T < (Now->Unbind >= 0.f ? Now->Unbind : .1f)) bGlider = true;
    ShowGlider(bGlider);
    // The carry layers: the sword arm over everything but blade work, and while guarding on foot the raised shield, or
    // without it the sword raised across the body (both arms).
    const bool bGuardPose = IsGuarding() && Mode == EBotwMoveMode::Ground && (Name.IsNone() || IsLockLoop(Name));
    const bool bSwordGuard = bGuardPose && !HasShield();
    const bool bCarry = bArmed && !IsSwordAction(Name) && (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air) && !bDown && !bSwordGuard;
    SwordCarry = FMath::FInterpConstantTo(SwordCarry, bCarry ? 1.f : 0.f, Dt, 8.f);
    GuardCarry = FMath::FInterpConstantTo(GuardCarry, bGuardPose && HasShield() ? 1.f : 0.f, Dt, 10.f);
    SwordGuardCarry = FMath::FInterpConstantTo(SwordGuardCarry, bSwordGuard ? 1.f : 0.f, Dt, 10.f);
    // Without the shield the off hand holds nothing: over sword work and the lock-on strafe its arm swings free rather
    // than holding the shield pose the BOTW clips give it (not in Cairo's two-handed guard, parry and recoil, nor
    // drawing and sheathing).
    // Strafing in a one-handed guard the arm swings free too; a two-handed guard keeps both hands on the grip.
    const bool bTwoHanded = GetParam(TEXT("TwoHandedGuard")) > .5f;
    const bool bFree = !HasShield() && bArmed && (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air) && !bDown &&
        !(bSwordGuard && bTwoHanded) && !In(Name, { TEXT("SwordParry"), TEXT("SwordGuardHit"), TEXT("DrawSword"), TEXT("SheatheSword") });
    FreeArm = FMath::FInterpConstantTo(FreeArm, bFree ? 1.f : 0.f, Dt, 8.f);
    // Cairo's own two-handed clips were made for his longer bokken: on this sword the off hand is moved onto the handle.
    const bool bTwoHand = bTwoHanded && bArmed && !bDown && (bSwordGuard || In(Name, { TEXT("SwordParry"), TEXT("SwordGuardHit") }));
    TwoHandGrip = FMath::FInterpConstantTo(TwoHandGrip, bTwoHand ? 1.f : 0.f, Dt, 12.f);
    // The off hand closed round the handle: the middle of its curled fingers on the sword's axis, one hand's width
    // (BOTW's 13 cm) toward the pommel from where the sword hand closes round it; its wrist moved with it.
    const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword"));
    USkeletalMeshComponent* Body = Character->GetMesh();
    if (TwoHandGrip > 0.f && Sword && *Sword && Body && !BladeTip.IsNearlyZero())
    {
        const FTransform& MeshT = Body->GetComponentTransform();
        const FTransform& SwordT = (*Sword)->GetComponentTransform();
        const FVector Origin = MeshT.InverseTransformPosition(SwordT.GetLocation());
        const FVector Pommel = MeshT.InverseTransformVectorNoScale(SwordT.TransformVectorNoScale(-BladeTip)).GetSafeNormal();
        const FVector SwordHand = Origin + Pommel * ((FingersOf(0) - Origin) | Pommel);
        const FVector Wrist = Body->GetSocketTransform(Character->GetSkateBone(TEXT("hand_L")), RTS_Component).GetLocation()
            + (SwordHand + Pommel * 13.f * Scale() - FingersOf(1));
        // Kept in the sword hand's frame, so it goes with that hand in the frame it is evaluated (the strafe's bob).
        GripOffset = Body->GetSocketTransform(Character->GetSkateBone(TEXT("hand_R")), RTS_Component).InverseTransformPosition(Wrist);
    }
}

void UBotwMoveSet::EaseMesh(const FVector& From, float Seconds)
{
    MeshOffsetStart = From; MeshOffsetLength = FMath::Max(Seconds, .01f); MeshOffsetTime = 0.f;
}

/** The mesh's offset from its place in the capsule: the lean into a climbed wall, a pose and capsule that disagree for a
 *  moment (into and out of the water), and a fitted ledge climb's start, each eased out. */
void UBotwMoveSet::AdvanceMeshOffset(float Dt)
{
    USkeletalMeshComponent* Body = Character->GetMesh();
    if (!Body) return;
    ClimbShift = FMath::FInterpConstantTo(ClimbShift, ClimbShiftTarget, Dt, 60.f);
    MeshOffsetTime += Dt;
    FVector Offset(ClimbShift, 0, 0);
    if (MeshOffsetLength > 0.f) Offset += MeshOffsetStart * (1.f - Smooth(MeshOffsetTime / MeshOffsetLength));
    if (MeshOffsetTime >= MeshOffsetLength) MeshOffsetLength = 0.f;
    if (bDriving && !MeshDriveLocal.IsZero()) Offset += MeshDriveLocal * (1.f - DriveProgress());
    // A tucked somersault: after it (or a landing that cut it short) the turn finishes to upright and the lift fades as
    // the hips come back down.
    if (FlipTime < 0.f && FlipAngle != 0.f)
    {
        FlipAngle = FMath::FInterpConstantTo(FlipAngle, FlipAngle > 180.f ? 360.f : 0.f, Dt, 900.f);
        if (FlipAngle < .01f || FlipAngle > 359.99f) FlipAngle = 0.f;
    }
    if (FlipTime < 0.f && FlipSettle > 0.f)
    {
        FlipSettle = FMath::Max(0.f, FlipSettle - Dt);
        FlipLift = FlipSettle > 0.f ? FMath::Min(FlipLift, HipLift()) * FMath::Min(1.f, FlipSettle / .15f) : 0.f;
    }
    else if (FlipTime < 0.f) FlipLift = 0.f;
    if (FlipAngle != 0.f || FlipLift != 0.f)
    {
        FTransform Placed(MeshBaseRotation, MeshBase + Offset + FVector(0, 0, FlipLift), Body->GetRelativeScale3D());
        if (FlipAngle != 0.f)
        {
            // About the capsule's right axis, head first: forward.
            const FVector Pivot = FlipPivot.IsZero() ? FVector(0, 0, FlipLift) : FlipPivot;
            Placed = Placed * FTransform(-Pivot) * FTransform(FQuat(FVector::YAxisVector, FMath::DegreesToRadians(FlipAngle))) * FTransform(Pivot);
        }
        Body->SetRelativeTransform(Placed);
        bMeshTurned = bMeshOffset = true;
        return;
    }
    if (bMeshTurned) { Body->SetRelativeRotation(MeshBaseRotation); bMeshTurned = false; bMeshOffset = true; }
    if (Offset.IsNearlyZero(.01) && !bMeshOffset) return;
    Body->SetRelativeLocation(MeshBase + Offset);
    bMeshOffset = !Offset.IsNearlyZero(.01);
}

/** Cosmetic only: the sprint's dust and speed lines, the glider's wind off its tips and the blade's ribbon. */
void UBotwMoveSet::AdvanceEffects(float Dt)
{
    AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character);
    // The blade's ribbon: through every cut's active windows, a little either side, at the blow's strength.
    if (BladeTrail)
    {
        const FBotwMove* Now = Current();
        bool bEmit = false;
        if (Now && bArmed && IsAttack(Now->Name))
            for (const FVector2f& W : Now->Active) bEmit |= SourceTime() >= W.X - .05f && SourceTime() <= W.Y + .04f;
        TArray<FVector> Blade; BladePoints(Blade);
        if (Blade.Num()) BladeTrail->Sample(Blade[0], Blade.Last(), bEmit, FMath::Clamp(Strength, 1, 3), Dt);
    }
    if (!FX) return;
    const UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    const FVector Velocity = Movement->Velocity;
    // Sprinting: a burst of dust as it starts, then puffs at the heels and pale speed lines streaming past.
    const bool bSprinting = Mode == EBotwMoveMode::Ground && Character->Stamina.Sprinting && Velocity.Size2D() > 300.f;
    if (bSprinting)
    {
        const FVector Ground = Here - FVector(0, 0, HalfHeight());
        const FVector Back = -FVector(Velocity.GetSafeNormal2D());
        if (!bWasSprinting) { FX->Dust(Ground, .8f, Back * .6f); FX->Play(TEXT("dash"), Ground, .3f, .1f); SprintFX = 0.f; }
        SprintFX += Dt;
        while (SprintFX >= .09f)
        {
            SprintFX -= .09f;
            FX->Dust(Ground + Back * 25.f, .22f, Back * .5f);
            for (int32 I = 0; I < 2; ++I)
            {
                const FVector Side = FVector::CrossProduct(FVector::UpVector, Back) * FMath::FRandRange(-45.f, 45.f);
                AAtelierFX::FParticle& P = FX->Spawn(AAtelierFX::ESprite::Spark, Here + Side + FVector(0, 0, FMath::FRandRange(-.7f, .5f) * HalfHeight()) - Back * 40.f);
                P.V = Back * FMath::FRandRange(700.f, 1100.f); P.Stretch = .04f; P.Drag = 2.f;
                P.Life = FMath::FRandRange(.12f, .2f); P.Size0 = 1.8f; P.Size1 = .8f; P.Color = FLinearColor(.95f, .97f, 1.f) * 2.f;
            }
        }
    }
    bWasSprinting = bSprinting;
    // Gliding: wind streaming off the canopy's tips, more of it the faster he flies.
    if (Mode == EBotwMoveMode::Glide && bGliderShown && Glider)
    {
        GlideFX += Dt * FMath::GetMappedRangeValueClamped(FVector2f(150.f, 600.f), FVector2f(10.f, 34.f), GlideSpeed);
        const FBoxSphereBounds Canopy = Glider->Bounds;
        const FVector Right = Character->GetActorRightVector(), Back = -Character->GetActorForwardVector();
        while (GlideFX >= 1.f)
        {
            GlideFX -= 1.f;
            const float Sign = FMath::RandBool() ? 1.f : -1.f;
            const FVector Tip = Canopy.Origin + Right * Sign * Canopy.BoxExtent.Size2D() * .85f + Back * FMath::FRandRange(0.f, 20.f);
            AAtelierFX::FParticle& P = FX->Spawn(AAtelierFX::ESprite::Spark, Tip);
            P.V = Back * FMath::FRandRange(250.f, 420.f) + Velocity * .2f; P.Stretch = .06f; P.Drag = 1.2f;
            P.Life = FMath::FRandRange(.25f, .45f); P.Size0 = 1.6f; P.Size1 = .5f; P.Color = FLinearColor(.92f, .96f, 1.f) * 1.8f; P.FadeIn = .05f;
        }
    }
    else GlideFX = 0.f;
}

float UBotwMoveSet::HipLift() const
{
    const USkeletalMeshComponent* Body = Character ? Character->GetMesh() : nullptr;
    if (!Body) return 0.f;
    const float Now = Body->GetSocketTransform(Character->GetSkateBone(TEXT("pelvis")), RTS_Component).GetLocation().Z;
    return FMath::Max(0.f, (FlipHips - Now) * float(Body->GetRelativeScale3D().Z));
}
