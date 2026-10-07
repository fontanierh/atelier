#include "FoxHunter.h"
#include "JapanCombat.h"
#include "JapanEncounters.h"
#include "JapanNetwork.h"
#include "GameFramework/GameStateBase.h"
#include "Net/UnrealNetwork.h"
#include "FoxHunterAnimInstance.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Engine/SkinnedAsset.h"
#include "ReferenceSkeleton.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Animation/AnimSequence.h"
#include "CollisionQueryParams.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "YorimichiCombatFX.h"

TSharedPtr<FFoxReview> CreateFoxReview(AFoxHunter* Fox);
void AdvanceFoxReview(FFoxReview& Review, float Dt);

UAnimSequence* UFoxHunterDefinition::FindAction(FName Name) const { const TObjectPtr<UAnimSequence>* Found = Actions.Find(Name); return Found ? Found->Get() : nullptr; }
const FFoxHunterClip* UFoxHunterDefinition::FindClip(FName Role) const { return Clips.FindByPredicate([&](const FFoxHunterClip& C) { return C.Role == Role; }); }

AFoxHunter::AFoxHunter(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
    PrimaryActorTick.bCanEverTick = true;
    bReplicates = true; SetReplicateMovement(true); SetNetUpdateFrequency(30.f); SetMinNetUpdateFrequency(10.f);
    AutoPossessAI = EAutoPossessAI::Disabled;
    bUseControllerRotationYaw = false;
    GetCapsuleComponent()->InitCapsuleSize(26.f, 86.f);
    // The player's blade sweeps the Visibility channel, which a Pawn capsule ignores by default; the spring arm
    // probes Camera, which it would block.
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->bOrientRotationToMovement = false;   // facing is explicit: root-motion clips must not be re-oriented by their own velocity
    Movement->bRunPhysicsWithNoController = true;  // no AI controller: the state machine feeds movement input directly
    Movement->RotationRate = FRotator::ZeroRotator;
    Movement->MaxWalkSpeed = ChaseSpeed;
    Movement->MaxAcceleration = 2000.f;
    Movement->BrakingDecelerationWalking = 2400.f;
    Movement->GroundFriction = 8.f;
    Movement->GravityScale = 1.5f;
    Movement->bCanWalkOffLedges = true;
    GetMesh()->SetRelativeLocation(FVector(0, 0, -86.65f));
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);   // the Tripo skeleton faces +X, like the player's
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->SetRenderCustomDepth(true);
    GetMesh()->SetCustomDepthStencilValue(1);
    GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    GetMesh()->bEnableUpdateRateOptimizations = false;
}

void AFoxHunter::BeginPlay()
{
    Super::BeginPlay();
    Definition = LoadObject<UFoxHunterDefinition>(nullptr, TEXT("/Game/FoxHunter/DA_FoxHunter.DA_FoxHunter"));
    if (!IsReady()) { UE_LOG(LogTemp, Error, TEXT("Fox hunter assets incomplete: run Scripts/import_fox_hunter.py after building.")); return; }
    GetCapsuleComponent()->SetCapsuleSize(Definition->CapsuleRadius, Definition->CapsuleHalfHeight);
    GetMesh()->SetRelativeLocation(FVector(0, 0, -(Definition->CapsuleHalfHeight + Definition->SoleHeight)));
    GetMesh()->SetSkeletalMeshAsset(Definition->Mesh);
    GetMesh()->SetAnimInstanceClass(UFoxHunterAnimInstance::StaticClass());
    // The FBX skeleton keeps the export scale on its root bone; root-motion translation arrives through it.
    if (const USkinnedAsset* Asset = GetMesh()->GetSkinnedAsset())
    {
        const TArray<FTransform>& Ref = Asset->GetRefSkeleton().GetRefBonePose();
        const float RootScale = Ref.Num() ? Ref[0].GetScale3D().X : 1.f;
        if (RootScale > 1.5f) RootMotionScale = 1.f / RootScale;
        SetAnimRootMotionTranslationScale(RootMotionScale);
    }
    if (JapanNetwork::IsOnline(GetWorld()) && !HasAuthority())
    {
        GetCharacterMovement()->bRunPhysicsWithNoController = false;
        if (auto* Animation = GetMesh()->GetAnimInstance()) Animation->SetRootMotionMode(ERootMotionMode::IgnoreRootMotion);
    }
    Paint = GetNetMode() == NM_DedicatedServer ? nullptr : GetMesh()->CreateDynamicMaterialInstance(0);
    Home = GetActorLocation(); HomeYaw = GetActorRotation().Yaw;
    Rand.Initialize(int32(FPlatformTime::Cycles() & 0x7fffffff));
    if (FParse::Param(FCommandLine::Get(), TEXT("foxqa"))) Review = CreateFoxReview(this);
    UE_LOG(LogTemp, Display, TEXT("Fox hunter ready: %d clips, capsule %.0f/%.0f, home %s"), Definition->Clips.Num(), Definition->CapsuleRadius, Definition->CapsuleHalfHeight, *Home.ToString());
}

const FFoxHunterClip* AFoxHunter::Clip(FName Role) const { return Definition ? Definition->FindClip(Role) : nullptr; }
void AFoxHunter::Note(const FString& Text) { Event = Text; EventTime = Clock; UE_LOG(LogTemp, Verbose, TEXT("Fox: %s"), *Text); }
void AFoxHunter::Cue(FName Sound, const FVector& At, float Volume) { if (JapanCombat::Publish(this, EJapanCombatCue::Sound, At, FVector::ZeroVector, Volume, this, nullptr, false, Sound)) return; if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(this)) FX->Play(Sound, At, Volume, .06f); }
void AFoxHunter::DashDust()
{
    const FVector Ground = GetActorLocation() - FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    if (JapanCombat::Publish(this, EJapanCombatCue::Dash, Ground, -GetActorForwardVector()*.5f, 0.f, this)) return;
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(this))
    {
        FX->Dust(Ground, 1.f, -GetActorForwardVector() * .5f); FX->Play(TEXT("dash"), Ground, .8f, .06f);
    }
}

FString AFoxHunter::StateName() const
{
    switch (State)
    {
        case EFoxState::Idle: return TEXT("Idle"); case EFoxState::Approach: return TEXT("Approach"); case EFoxState::Stalk: return TEXT("Stalk");
        case EFoxState::Attack: return CurrentClip.ToString(); case EFoxState::Recover: return TEXT("Recover"); case EFoxState::Lunge: return TEXT("Lunge");
        case EFoxState::Retreat: return TEXT("Retreat"); case EFoxState::Turn: return TEXT("Turn"); case EFoxState::Hurt: return TEXT("Hurt");
        case EFoxState::Dead: return TEXT("Dead"); case EFoxState::Withdraw: return TEXT("Withdraw"); case EFoxState::Return: return TEXT("Return");
    }
    return TEXT("?");
}

void AFoxHunter::SetAction(FName Action, bool bLoop, float Blend)
{
    AnimationAction = Action; bActionLoops = bLoop; ActionTime = 0.f; ActionBlendTime = Blend; ++ActionSerial;
    ActionDuration = Action.IsNone() || !Definition->FindAction(Action) ? 0.f : Definition->FindAction(Action)->GetPlayLength();
}

/** Clips end when the state machine moves on; a finished one-shot holds its last frame until then. */
void AFoxHunter::AdvanceAction(float Dt) { ActionTime += Dt; }

void AFoxHunter::Enter(EFoxState Next, FName ClipName, float Blend, bool bLoop)
{
    if (JapanNetwork::IsOnline(GetWorld()) && HasAuthority())
    {
        auto* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>();
        if (Next == EFoxState::Approach) EngageNetworkEncounter();
        if (Next != EFoxState::Attack && Next != EFoxState::Lunge) Encounters->ReleaseAttack(this);
        if (Next == EFoxState::Return || Next == EFoxState::Dead || Next == EFoxState::Idle) Encounters->End(this);
        if (Next == EFoxState::Idle) { Health = MaxHealth; EncounterHealth = MaxHealth; bHealthScaled = false; }
    }
    State = Next; StateTime = 0.f; CurrentClip = ClipName; PreviousStrike.Reset();
    SetAnimRootMotionTranslationScale(RootMotionScale);
    if (ClipName.IsNone()) { if (!AnimationAction.IsNone()) SetAction(NAME_None, false, Blend); }
    else SetAction(ClipName, bLoop, Blend);
}

void AFoxHunter::FaceYaw(float TargetYaw, float RateDegPerSec, float Dt)
{
    const FRotator R = GetActorRotation();
    SetActorRotation(FRotator(0, FMath::FixedTurn(R.Yaw, TargetYaw, RateDegPerSec * Dt), 0));
}

void AFoxHunter::MoveToward(const FVector& Where, float Speed)
{
    GetCharacterMovement()->MaxWalkSpeed = Speed;
    FVector Dir = Where - GetActorLocation(); Dir.Z = 0;
    AddMovementInput(Dir.GetSafeNormal());
}

void AFoxHunter::StartAttack()
{
    if (JapanNetwork::IsOnline(GetWorld()) && !GetWorld()->GetSubsystem<UJapanEncounters>()->ReserveAttack(this, Target, 3.f))
    { Enter(EFoxState::Recover, NAME_None, .16f); Cooldown = .35f; return; }
    FName Role = ForcedAttack; ForcedAttack = NAME_None;
    if (Role.IsNone())
    {
        const float R = Rand.FRand();
        Role = R < .24f ? TEXT("AttackR_A") : R < .48f ? TEXT("AttackL_A") : R < .66f ? TEXT("AttackL_B") : R < .84f ? TEXT("AttackR_B") : TEXT("Kick");
    }
    bComboFollowUp = Role != TEXT("Kick") && Rand.FRand() < .45f;
    bStruckThisAttack = false; bSwipeCue = false; ++Attacks;
    Enter(EFoxState::Attack, Role, .08f);
    Note(Role == TEXT("Kick") ? TEXT("kick") : TEXT("claw"));
}

FVector AFoxHunter::StrikePoint() const
{
    const FFoxHunterClip* C = Clip(CurrentClip);
    return C && !C->StrikeTipBone.IsNone() ? GetMesh()->GetSocketLocation(C->StrikeTipBone) : GetActorLocation();
}

/** Spheres along the striking hand or foot, swept between frames inside the clip's window; one contact per attack. */
void AFoxHunter::SweepStrike()
{
    const FFoxHunterClip* C = Clip(CurrentClip);
    if (!HasAuthority() || !C || bStruckThisAttack || !Target) return;
    const FVector A = GetMesh()->GetSocketLocation(C->StrikeBone), B = GetMesh()->GetSocketLocation(C->StrikeTipBone);
    const FVector Dir = (B - A).GetSafeNormal();
    TArray<FVector> Now = { A, (A + B) * .5f, B, B + Dir * 8.f };
    if (PreviousStrike.Num() == Now.Num())
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(FoxStrike), false, this);
        for (int32 I = 0; I < Now.Num() && !bStruckThisAttack; ++I)
        {
            TArray<FHitResult> Hits;
            GetWorld()->SweepMultiByChannel(Hits, PreviousStrike[I], Now[I], FQuat::Identity, ECC_Pawn, FCollisionShape::MakeSphere(14.f), Params);
            for (const FHitResult& H : Hits)
            {
                if (H.GetActor() != Target) continue;
                bStruckThisAttack = true;
                const float Damage = CurrentClip == TEXT("Kick") ? KickDamage : ClawDamage;
                TWeakObjectPtr<AFoxHunter> WeakSelf(this);
                TWeakObjectPtr<AWandererCharacter> Victim(Target);
                JapanCombat::Strike(this, Target, Damage, GetActorLocation(), [WeakSelf, Victim](int32 Outcome)
                {
                    auto* Self = WeakSelf.Get();
                    if (!Self || !Self->IsAlive()) return;
                    if (Outcome == 1)
                    {
                        ++Self->StrikesParried; Self->Note(TEXT("parried!")); Self->ConsecutiveAttacks = 0;
                        if (Self->State != EFoxState::Hurt) Self->Enter(EFoxState::Hurt, TEXT("Hurt"), .04f);
                        Self->Cooldown = 1.3f;
                        Self->SetAnimRootMotionTranslationScale(Self->RootMotionScale * .25f);
                    }
                    else if (Outcome == 2) { ++Self->StrikesDodged; Self->Note(TEXT("swipes at air")); }
                    else if (Outcome == 3) ++Self->StrikesMissed;
                    else
                    {
                        ++Self->StrikesLanded; Self->Note(TEXT("hits you"));
                        if (Victim.IsValid() && Victim->GetSword() && Victim->GetSword()->IsDown()) Self->bKnockedPlayerDown = true;
                    }
                });
                break;
            }
        }
    }
    PreviousStrike = Now;
}

void AFoxHunter::TakeSwordHit(int32 Strength, AActor* From)
{
    if (!HasAuthority() || !IsReady() || !IsAlive()) return;
    if (JapanNetwork::IsOnline(GetWorld()))
    {
        auto* Player = Cast<AWandererCharacter>(From);
        if (!UJapanEncounters::Eligible(Player)) return;
        EngageNetworkEncounter();
        GetWorld()->GetSubsystem<UJapanEncounters>()->AddThreat(this, Player, Strength);
    }
    Health = FMath::Max(0, Health - Strength); ++HitsTaken; Flash = .22f; NoticeBlock = 0.f;
    // The fox's cry is sparing: the first hit, heavy hits and the death always, otherwise every other hit.
    if (Health <= 0 || Strength >= 2 || HitsTaken % 2 == 1) Cue(TEXT("fox_hurt"), GetActorLocation() + FVector(0, 0, 60), Health <= 0 ? 1.f : .8f);
    if (!Target) Target = Cast<AWandererCharacter>(From);
    if (Health <= 0) { Die(); return; }
    const FFoxHunterClip* C = Clip(CurrentClip);
    const bool bWindingUp = State == EFoxState::Attack && C && ActionTime < C->HitStart;
    const bool bArmored = State == EFoxState::Lunge || State == EFoxState::Retreat || State == EFoxState::Withdraw || (State == EFoxState::Attack && (!bWindingUp || Poise < 1.f));
    if (Strength >= 2 || !bArmored)
    {
        if (bWindingUp) Poise -= 1.f;
        ConsecutiveAttacks = 0; bKnockedPlayerDown = false;
        Enter(EFoxState::Hurt, TEXT("Hurt"), .05f);
        Note(Strength >= 3 ? TEXT("reels") : TEXT("staggers"));
    }
    else Note(TEXT("shrugs it off"));
}

void AFoxHunter::SetCollisionAlive(bool bAlive)
{
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Pawn, bAlive ? ECR_Block : ECR_Ignore);
    GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_Visibility, bAlive ? ECR_Block : ECR_Ignore);
}

void AFoxHunter::Die()
{
    ++Deaths; Note(TEXT("falls")); bDeathCues[0] = bDeathCues[1] = bDeathCues[2] = false;
    Enter(EFoxState::Dead, TEXT("Death"), .05f);
    GetCharacterMovement()->StopMovementImmediately();
    GetCharacterMovement()->DisableMovement();
    SetCollisionAlive(false);
}

void AFoxHunter::Respawn()
{
    SetActorHiddenInGame(false);
    if (Paint) Paint->SetScalarParameterValue(TEXT("Dissolve"), 0.f);
    bHealthScaled = false; EncounterHealth = MaxHealth;
    Health = MaxHealth; Poise = 2.f; ConsecutiveAttacks = 0; bKnockedPlayerDown = false;
    SetCollisionAlive(true);
    GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    SetActorLocation(Home, false, nullptr, ETeleportType::TeleportPhysics);
    SetActorRotation(FRotator(0, HomeYaw, 0));
    Enter(EFoxState::Idle, NAME_None, .0f);
    NoticeBlock = 2.f; Note(TEXT("returns"));
}

void AFoxHunter::Tick(float Dt)
{
    Super::Tick(Dt);
    if (!IsReady()) return;
    if (JapanNetwork::IsOnline(GetWorld()) && !HasAuthority()) { PresentNetworkState(); return; }
    Clock += Dt;
    if (JapanNetwork::IsOnline(GetWorld()))
    {
        auto* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>();
        Encounters->Refresh(this, ForgetRadius);
        if (Encounters->Identity(this))
        {
            if ((State != EFoxState::Attack && State != EFoxState::Lunge) || !UJapanEncounters::Eligible(Target))
            {
                if (!UJapanEncounters::Eligible(Target)) Encounters->ReleaseAttack(this);
                Target = Encounters->Select(this, Target);
            }
        }
        else Target = JapanCombat::FindPlayer(this, Target, ForgetRadius);
    }
    else if (!IsValid(Target)) Target = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0));   // also after a character switch
    if (Review) AdvanceFoxReview(*Review, Dt);
    if (Target && !Target->IsReady()) return;
    AdvanceAction(Dt);
    StateTime += Dt; Cooldown = FMath::Max(0.f, Cooldown - Dt); NoticeBlock = FMath::Max(0.f, NoticeBlock - Dt);
    Flash = FMath::Max(0.f, Flash - Dt); Poise = FMath::Min(2.f, Poise + Dt / 2.5f);
    if (Paint) Paint->SetScalarParameterValue(TEXT("HitFlash"), Flash > 0.f ? .5f * Flash / .22f : 0.f);
    const FFoxHunterClip* C = Clip(CurrentClip);
    const bool bClipDone = C && !C->Loop && ActionTime >= C->Duration;
    FVector ToTarget = Target ? Target->GetActorLocation() - GetActorLocation() : FVector::ZeroVector; ToTarget.Z = 0;
    const float Dist = Target ? ToTarget.Size() : 1e9f;
    const float TargetYaw = Target ? ToTarget.Rotation().Yaw : GetActorRotation().Yaw;
    const float YawError = FRotator::NormalizeAxis(TargetYaw - GetActorRotation().Yaw);
    const bool bTargetDown = Target && Target->GetSword() && Target->GetSword()->IsDown();
    const float Speed = GetVelocity().Size2D();
    switch (State)
    {
        case EFoxState::Idle:
            if (Target && Dist < NoticeRadius && NoticeBlock <= 0.f && !bTargetDown) { Note(TEXT("notices you")); Cue(TEXT("fox_alert"), GetActorLocation() + FVector(0, 0, 60)); Enter(EFoxState::Approach, NAME_None, .2f); }
            break;
        case EFoxState::Approach:
            if (Dist > ForgetRadius || bTargetDown) { Enter(EFoxState::Return, NAME_None, .2f); Note(TEXT("loses interest")); break; }
            if (Dist <= RunUntil) { Enter(EFoxState::Stalk, NAME_None, .2f); StalkClock = 0.f; break; }
            // A closing dive from mid range: the authored dash carries the fox about three metres.
            if (!bPassive && Cooldown <= 0.f && Dist >= 300.f && Dist <= 380.f && FMath::Abs(YawError) < 12.f && Rand.FRand() < Dt * 1.5f &&
                (!JapanNetwork::IsOnline(GetWorld()) || GetWorld()->GetSubsystem<UJapanEncounters>()->ReserveAttack(this, Target, 2.f)))
            { Enter(EFoxState::Lunge, TEXT("DashForward"), .08f); Note(TEXT("lunges")); DashDust(); break; }
            FaceYaw(TargetYaw, 420.f, Dt); MoveToward(Target->GetActorLocation(), ChaseSpeed);
            break;
        case EFoxState::Stalk:
            if (Dist > ForgetRadius || bTargetDown) { Enter(EFoxState::Return, NAME_None, .2f); Note(TEXT("loses interest")); break; }
            if (Dist > RunUntil + 130.f) { Enter(EFoxState::Approach, NAME_None, .2f); break; }
            if (FMath::Abs(YawError) > 130.f && Speed < 30.f)
            { Enter(EFoxState::Turn, YawError > 0.f ? TEXT("TurnRight") : TEXT("TurnLeft"), .1f); Note(TEXT("turns")); break; }
            StalkClock += Dt;
            FaceYaw(TargetYaw, 360.f, Dt);
            if (Dist > StopDistance) MoveToward(Target->GetActorLocation(), StalkSpeed);
            if (!bPassive && Dist <= AttackRange && FMath::Abs(YawError) < 30.f && Cooldown <= 0.f) StartAttack();
            break;
        case EFoxState::Attack:
        {
            if (!C) { Enter(EFoxState::Stalk, NAME_None, .15f); break; }
            if (ActionTime < C->HitStart - .15f) FaceYaw(TargetYaw, 150.f, Dt);   // tracks a little during the wind-up only
            if (!bSwipeCue && ActionTime >= C->HitStart - .07f) { bSwipeCue = true; Cue(CurrentClip == TEXT("Kick") ? TEXT("kick_swing") : TEXT("claw_swipe"), StrikePoint(), .9f); }
            if (ActionTime >= C->HitStart && ActionTime <= C->HitEnd) SweepStrike();
            else if (ActionTime > C->HitEnd && !bStruckThisAttack) { bStruckThisAttack = true; ++StrikesMissed; Note(TEXT("misses")); }
            if (State != EFoxState::Attack) break;   // a parry inside the sweep already moved the state on
            if (bClipDone)
            {
                ++ConsecutiveAttacks;
                if (bKnockedPlayerDown) { bKnockedPlayerDown = false; Enter(EFoxState::Withdraw, TEXT("DashBackward"), .1f); Note(TEXT("withdraws")); DashDust(); }
                else if (!bPassive && bComboFollowUp && Dist <= AttackRange + 25.f && ConsecutiveAttacks < 3 && FMath::Abs(YawError) < 40.f) StartAttack();
                else if (Dist < 220.f && Rand.FRand() < .3f) { Enter(EFoxState::Retreat, TEXT("DashBackward"), .1f); Cooldown = 1.f; Note(TEXT("springs back")); DashDust(); }
                else { Enter(EFoxState::Recover, NAME_None, .16f); Cooldown = Rand.FRandRange(.9f, 1.8f); }
            }
            break;
        }
        case EFoxState::Recover:
            FaceYaw(TargetYaw, 240.f, Dt);
            if (StateTime >= .3f) { Enter(EFoxState::Stalk, NAME_None, .12f); }
            break;
        case EFoxState::Lunge: if (bClipDone) { Enter(EFoxState::Stalk, NAME_None, .14f); Cooldown = .15f; ConsecutiveAttacks = 0; } break;
        case EFoxState::Retreat: if (bClipDone) { Enter(EFoxState::Stalk, NAME_None, .14f); ConsecutiveAttacks = 0; } break;
        case EFoxState::Turn: if (bClipDone) Enter(EFoxState::Stalk, NAME_None, .14f); break;
        case EFoxState::Hurt: if (bClipDone) { Enter(EFoxState::Stalk, NAME_None, .14f); Cooldown = FMath::Max(Cooldown, .5f); } break;
        case EFoxState::Dead:
        {
            PresentDeath();
            if (StateTime >= DeadBodyTime && !IsHidden()) SetActorHiddenInGame(true);
            if (StateTime >= DeadBodyTime + RespawnTime) Respawn();
            break;
        }
        case EFoxState::Withdraw: if (bClipDone) { Enter(EFoxState::Return, NAME_None, .14f); Cooldown = 1.f; } break;
        case EFoxState::Return:
        {
            FVector ToHome = Home - GetActorLocation(); ToHome.Z = 0;
            if (ToHome.Size() < 60.f) { Enter(EFoxState::Idle, NAME_None, .2f); NoticeBlock = 4.f; }
            else { FaceYaw(ToHome.Rotation().Yaw, 420.f, Dt); MoveToward(Home, ChaseSpeed * .7f); }
            break;
        }
    }
    PublishNetworkState();
}

void AFoxHunter::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AFoxHunter, NetworkState);
}

void AFoxHunter::PublishNetworkState()
{
    if (!JapanNetwork::IsOnline(GetWorld()) || !HasAuthority()) return;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - LastNetworkPublication < .05 && NetworkState.Serial == ActionSerial && NetworkState.Health == Health) return;
    LastNetworkPublication = Now;
    NetworkState.Target = Target; NetworkState.Encounter = GetWorld()->GetSubsystem<UJapanEncounters>()->Identity(this);
    NetworkState.MaximumHealth = EncounterHealth;
    NetworkState.Action = AnimationAction; NetworkState.Serial = ActionSerial; NetworkState.Time = ActionTime;
    NetworkState.StateTime = StateTime; NetworkState.Blend = ActionBlendTime; NetworkState.bLoop = bActionLoops;
    NetworkState.Health = Health; NetworkState.State = uint8(State); NetworkState.Flash = Flash;
    NetworkState.ServerTime = Now;
    ForceNetUpdate();
}

void AFoxHunter::OnRep_NetworkState() { PresentNetworkState(); }

void AFoxHunter::PresentNetworkState()
{
    if (HasAuthority() || !IsReady()) return;
    const auto* Time = GetWorld()->GetGameState();
    const float Age = Time ? FMath::Clamp(float(Time->GetServerWorldTimeSeconds() - NetworkState.ServerTime), 0.f, .25f) : 0.f;
    AnimationAction = NetworkState.Action; ActionSerial = NetworkState.Serial;
    ActionTime = NetworkState.Time + Age; ActionBlendTime = NetworkState.Blend; bActionLoops = NetworkState.bLoop;
    ActionDuration = Definition->FindAction(AnimationAction) ? Definition->FindAction(AnimationAction)->GetPlayLength() : 0.f;
    if (State != EFoxState::Dead && EFoxState(NetworkState.State) == EFoxState::Dead)
        bDeathCues[0] = bDeathCues[1] = bDeathCues[2] = false;
    State = EFoxState(NetworkState.State); StateTime = NetworkState.StateTime + Age;
    Target = NetworkState.Target; EncounterHealth = NetworkState.MaximumHealth;
    Health = NetworkState.Health;
    SetCollisionAlive(Health > 0);
    if (State == EFoxState::Dead) PresentDeath();
    if (Paint)
    {
        Paint->SetScalarParameterValue(TEXT("HitFlash"), FMath::Max(0.f, NetworkState.Flash - Age) / .22f * .5f);
        Paint->SetScalarParameterValue(TEXT("Dissolve"), State == EFoxState::Dead ? FMath::Clamp((StateTime - DissolveStart) / DissolveTime, 0.f, 1.f) : 0.f);
    }
}


void AFoxHunter::EngageNetworkEncounter()
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    const int32 Scaled = GetWorld()->GetSubsystem<UJapanEncounters>()->Engage(this, NoticeRadius, MaxHealth);
    if (!bHealthScaled) { EncounterHealth = Scaled; Health += Scaled - MaxHealth; bHealthScaled = true; }
}

void AFoxHunter::PresentDeath()
{
    if (GetNetMode() == NM_DedicatedServer) return;
    AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(this);
    const FVector Ground = GetActorLocation() - FVector(0, 0, GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    if (!bDeathCues[0] && StateTime >= DeathFallTime) { bDeathCues[0] = true; if (FX) FX->Play(TEXT("body_fall"), Ground, 1.f, .06f); if (FX) FX->Dust(Ground + GetActorForwardVector() * 60.f, 1.3f); }
    if (!bDeathCues[1] && StateTime >= DissolveStart) { bDeathCues[1] = true; if (FX) FX->Play(TEXT("fox_death"), Ground + FVector(0, 0, 40), 1.f, .06f); }
    const float Burn = FMath::Clamp((StateTime - DissolveStart) / DissolveTime, 0.f, 1.f);
    if (Paint) Paint->SetScalarParameterValue(TEXT("Dissolve"), Burn);
    if (FX && Burn > 0.f && Burn < 1.f && !IsHidden())
    {
        // Embers rise from the body while it burns away: a few per frame from random bones.
        static const FName Bones[] = { TEXT("pelvis"), TEXT("spine"), TEXT("chest"), TEXT("head"), TEXT("hand_L"), TEXT("hand_R"), TEXT("foot_L"), TEXT("foot_R"), TEXT("thigh_L"), TEXT("thigh_R") };
        const int32 Count = FMath::RoundToInt(2 + 5 * FMath::Sin(PI * Burn));
        for (int32 I = 0; I < Count; ++I)
        {
            const FName Bone = Bones[Rand.RandHelper(UE_ARRAY_COUNT(Bones))];
            FX->SpiritEmbers(GetMesh()->GetBoneLocation(Bone), 1, 18.f, 140.f);
        }
        if (!bDeathCues[2] && Burn > .82f) { bDeathCues[2] = true; FX->SpiritEmbers(GetMesh()->GetBoneLocation(TEXT("chest")), 40, 40.f, 220.f); FX->Flash(GetMesh()->GetBoneLocation(TEXT("chest")), 120.f, FLinearColor(1.f, .45f, .18f) * 4.f, .35f); }
    }
}
