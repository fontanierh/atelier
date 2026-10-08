#include "AdventureMoveSet.h"
#include "JapanNetwork.h"
#include "JapanCharacterMovement.h"
#include "AdventureMoveSetDetail.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "WandererDefinition.h"
#include "JapanWorld.h"
#include "JapanFootsteps.h"
#include "YorimichiCombatFX.h"
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

using namespace AdventureMoveSetDetail;

// Every timing below is in clip seconds (the action timelines' frames at 30 fps), every distance in game centimetres at
// the character's scale, and the adventure library's lengths (metres) and speeds (metres per 30 fps frame) are converted with that scale.


FVector4f FAdventureMove::PathAt(float SourceTime) const
{
    if (Path.Num() == 0) return FVector4f(0.f, 0.f, 0.f, 0.f);
    if (Path.Num() == 1) return Path[0];
    const float Frame = FMath::Clamp(SourceTime * 30.f, 0.f, float(Path.Num() - 1));
    const int32 I = FMath::Min(int32(Frame), Path.Num() - 2);
    return Path[I] + (Path[I + 1] - Path[I]) * (Frame - I);
}

bool FAdventureMove::InWindow(const TArray<FVector2f>& Windows, float SourceTime) const
{
    for (const FVector2f& W : Windows) if (SourceTime >= W.X && SourceTime <= W.Y) return true;
    return false;
}

// ------------------------------------------------------------------------------------------------------------- Setup

bool UAdventureMoveSet::Initialize(AWandererCharacter* Owner, const TSharedPtr<FJsonObject>& Record, const TSharedPtr<FJsonObject>& Grips)
{
    Character = Owner;
    const UWandererDefinition* Definition = Owner ? Owner->GetDefinition() : nullptr;
    const TSharedPtr<FJsonObject>* Actions = nullptr;
    if (!Definition || !Record.IsValid() || !Record->TryGetObjectField(TEXT("actions"), Actions)) return false;
    for (const auto& Pair : (*Actions)->Values)
    {
        const TSharedPtr<FJsonObject> O = Pair.Value->AsObject();
        FAdventureMove M; M.Name = FName(*Pair.Key);
        if (!O.IsValid() || !Definition->FindAction(M.Name)) continue;
        auto Number = [&O](const TCHAR* Key, float Default) { double V = 0.; return O->TryGetNumberField(Key, V) ? float(V) : Default; };
        auto Windows = [&O](const TCHAR* Key, TArray<FVector2f>& Out)
        {
            const TArray<TSharedPtr<FJsonValue>>* List = nullptr;
            if (O->TryGetArrayField(Key, List))
                for (const TSharedPtr<FJsonValue>& V : *List)
                {
                    const TArray<TSharedPtr<FJsonValue>>& W = V->AsArray();
                    if (W.Num() == 2) Out.Add(FVector2f(W[0]->AsNumber(), W[1]->AsNumber()));
                }
        };
        M.Length = Number(TEXT("length"), 0.f); M.Rate = FMath::Max(Number(TEXT("rate"), 1.f), .05f);
        M.Start = Number(TEXT("start"), 0.f); M.End = Number(TEXT("end"), M.Length); M.Blend = Number(TEXT("blend"), .1f);
        M.Speed = Number(TEXT("speed"), 0.f);
        M.Input = Number(TEXT("input"), -1.f); M.Cancel = Number(TEXT("cancel"), -1.f); M.Idle = Number(TEXT("idle"), -1.f);
        M.Bind = Number(TEXT("bind"), -1.f); M.Unbind = Number(TEXT("unbind"), -1.f);
        O->TryGetBoolField(TEXT("loop"), M.bLoop);
        Windows(TEXT("active"), M.Active); Windows(TEXT("guard"), M.Guard);
        const TArray<TSharedPtr<FJsonValue>>* Path = nullptr;
        if (O->TryGetArrayField(TEXT("path"), Path))
            for (const TSharedPtr<FJsonValue>& V : *Path)
            {
                const TArray<TSharedPtr<FJsonValue>>& P = V->AsArray();
                if (P.Num() == 4) M.Path.Add(FVector4f(P[0]->AsNumber(), P[1]->AsNumber(), P[2]->AsNumber(), P[3]->AsNumber()));
            }
        Moves.Add(M.Name, MoveTemp(M));
    }
    // The double jump is Cairo's own somersault where the definition has it (DA_CairoAdventure): played whole, at its own rate.
    if (const UAnimSequence* Flip = Definition->FindAction(TEXT("DoubleJump")); Flip && !Moves.Contains(TEXT("DoubleJump")))
    {
        FAdventureMove M; M.Name = TEXT("DoubleJump");
        M.Length = M.End = Flip->GetPlayLength(); M.Blend = .05f;
        Moves.Add(M.Name, MoveTemp(M));
    }
    for (const TCHAR* Needed : { TEXT("Fall"), TEXT("Land"), TEXT("GlideOn"), TEXT("Glide"), TEXT("ClimbWait"), TEXT("SwimWait"), TEXT("Swim") })
        if (!Has(Needed))
        {
            UE_LOG(LogTemp, Warning, TEXT("Adventure move set: %s lacks %s (build unreal.adventure); playing without it"), *Owner->GetName(), Needed);
            return false;
        }
    const TSharedPtr<FJsonObject>* ParamObject = nullptr;
    if (Record->TryGetObjectField(TEXT("params"), ParamObject))
        for (const auto& Pair : (*ParamObject)->Values) { double V = 0.; if (Pair.Value->TryGetNumber(V)) Params.Add(FString(*Pair.Key), float(V)); }

    // Equipment: each piece rests at its back bone and is held at its hand bone (the glider only appears while gliding),
    // as placed by `carry` and `held` (identity when absent: the piece's own origin and axes are the bone's).
    USkeletalMeshComponent* Body = Owner->GetMesh();
    const TSharedPtr<FJsonObject>* Equipment = nullptr;
    if (Body && Record->TryGetObjectField(TEXT("equipment"), Equipment))
        for (const auto& Pair : (*Equipment)->Values)
        {
            const TSharedPtr<FJsonObject> O = Pair.Value->AsObject();
            if (!O.IsValid()) continue;
            FString MeshPath, Hand, Back;
            O->TryGetStringField(TEXT("mesh"), MeshPath); O->TryGetStringField(TEXT("hand"), Hand); O->TryGetStringField(TEXT("back"), Back);
            const FName Slot(*Pair.Key);
            if (Slot == TEXT("glider"))
            {
                USkeletalMesh* Asset = LoadObject<USkeletalMesh>(nullptr, *MeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
                FString ClipPath; O->TryGetStringField(TEXT("clip"), ClipPath);
                GliderClip = ClipPath.IsEmpty() ? nullptr : LoadObject<UAnimSequence>(nullptr, *ClipPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
                if (!Asset || Hand.IsEmpty()) continue;
                Glider = NewObject<USkeletalMeshComponent>(Owner, TEXT("Paraglider"));
                Glider->SetSkeletalMeshAsset(Asset);
                Glider->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                Glider->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
                Glider->RegisterComponent();
                Glider->AttachToComponent(Body, FAttachmentTransformRules::KeepRelativeTransform, FName(*Hand));
                GliderSocket = FName(*Hand);
                FTransform Held; ReadTransform(O, TEXT("held"), Held);
                Glider->SetRelativeTransform(Held);
                GliderHeld = Held;
                // The handles; the reference rig's own glide holds the glider (at his weapon bones), any other body is fitted to it.
                for (int32 I = 0; I < 2; ++I)
                {
                    GripEnds[I][0] = GliderHandles[I][0]; GripEnds[I][1] = GliderHandles[I][1];
                    BarGrip[I] = (GripEnds[I][0] + GripEnds[I][1]) * .5f;
                }
                bOwnGlide = Body->GetBoneIndex(TEXT("Weapon_R")) != INDEX_NONE && Body->GetBoneIndex(TEXT("Weapon_L")) != INDEX_NONE;
                // A fitted body's place for it on the neutral glide, from the import (its first frame, and the elbows
                // there): held there from the first frame of a glide, even one that steers at once.
                const TArray<TSharedPtr<FJsonValue>>* Elbows = nullptr;
                if (!bOwnGlide && O->HasField(TEXT("on_root")) && O->TryGetArrayField(TEXT("elbows_on_root"), Elbows) && Elbows->Num() == 2)
                {
                    ReadTransform(O, TEXT("on_root"), GliderOnRoot);
                    for (int32 I = 0; I < 2; ++I)
                    {
                        const TArray<TSharedPtr<FJsonValue>>& E = (*Elbows)[I]->AsArray();
                        if (E.Num() == 3) ElbowLocal[I] = GliderOnRoot.InverseTransformPosition(FVector(E[0]->AsNumber(), E[1]->AsNumber(), E[2]->AsNumber()));
                    }
                    bGliderOnBody = bGliderOnRoot = true;
                }
                Glider->SetVisibility(false, true);
                continue;
            }
            UStaticMesh* Asset = LoadObject<UStaticMesh>(nullptr, *MeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
            if (!Asset || Back.IsEmpty()) continue;
            FSlot S; S.Hand = Hand.IsEmpty() ? NAME_None : FName(*Hand); S.Back = FName(*Back);
            ReadTransform(O, TEXT("held"), S.Held);
            ReadTransform(O, TEXT("carry"), S.Carry);
            S.bCrouched = O->HasField(TEXT("crouch"));
            if (S.bCrouched) ReadTransform(O, TEXT("crouch"), S.Crouched);
            UStaticMeshComponent* Prop = NewObject<UStaticMeshComponent>(Owner, *(FString(TEXT("Adventure")) + *Pair.Key));
            Prop->SetStaticMesh(Asset);
            Prop->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            Prop->SetCastShadow(true);
            Prop->SetRenderCustomDepth(true); Prop->SetCustomDepthStencilValue(1);
            Prop->RegisterComponent();
            Props.Add(Slot, Prop);
            Slots.Add(Slot, S);
            Attach(Slot);
        }
    ReadGrips(Grips);
    // The blade runs along the sword mesh's longest axis, from its origin (the grip) to the far end of its bounds.
    if (const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword")))
    {
        const FBox Box = (*Sword)->GetStaticMesh()->GetBoundingBox();
        const FVector Size = Box.GetSize();
        const int32 Axis = Size.X >= Size.Y && Size.X >= Size.Z ? 0 : Size.Y >= Size.Z ? 1 : 2;
        const double Far = FMath::Abs(Box.Max[Axis]) >= FMath::Abs(Box.Min[Axis]) ? Box.Max[Axis] : Box.Min[Axis];
        FVector Tip = FVector::ZeroVector; Tip[Axis] = Far;
        BladeBase = Tip * .18; BladeTip = Tip;
        const double Near = Far == Box.Max[Axis] ? Box.Min[Axis] : Box.Max[Axis];
        HiltEnd = FVector::ZeroVector; if (Near * Far < 0.) HiltEnd[Axis] = Near;
        // The blade's width: the middle of the bounds' three sizes.
        const int32 Thin = Size.X <= Size.Y && Size.X <= Size.Z ? 0 : Size.Y <= Size.Z ? 1 : 2;
        SwordMajor = FVector::ZeroVector; SwordMajor[3 - Axis - Thin] = 1.;
        if (const FSlot* S = Slots.Find(TEXT("sword")))
        {
            FistAxis = S->Held.GetRotation().RotateVector(Tip.GetSafeNormal());
            bFistAxis = true;
        }
    }
    // Whatever is too steep to climb can be walked up: the walkable slope meets the climbing angle.
    Owner->GetCharacterMovement()->SetWalkableFloorAngle(GetParam(TEXT("ClimbEnableAngle"), 50.f));
    // The adventure library's stamina: sprinting spends EnergyDash a second, it refills at EnergyAutoRecover a second after a short wait.
    FSprintStamina& Stamina = Owner->Stamina;
    Stamina.SprintSeconds = 1000.f / FMath::Max(GetParam(TEXT("PlayerMove.EnergyDash"), 300.f), 1.f);
    Stamina.RefillSeconds = 1000.f / FMath::Max(GetParam(TEXT("EnergyAutoRecover"), 300.f), 1.f);
    Stamina.Delay = GetParam(TEXT("EnergyAutoRecoverInvalidTime1"), 10.f) / 30.f;
    MeshBase = Body ? Body->GetRelativeLocation() : FVector::ZeroVector;
    MeshBaseRotation = Body ? Body->GetRelativeRotation().Quaternion() : FQuat::Identity;
    // The blade's ribbon through every cut (world space, so it stays where the blade passed).
    if (Props.Contains(TEXT("sword")))
    {
        BladeTrail = NewObject<UAtelierTrail>(Owner, TEXT("AdventureBladeTrail"));
        BladeTrail->RegisterComponent();
    }
    // Retain the network field for compatibility; this move set has no shield prop.
    if (JapanNetwork::IsOnline(Owner->GetWorld()) && !Owner->IsNpc())
    { SetShield(Owner->GetNetworkShield()); }
    else
    {
        SetShield(false);
    }
    Mode = EAdventureMoveMode::Ground;
    UE_LOG(LogTemp, Display, TEXT("Adventure move set: %d actions, %d parameters, %d props%s, scale %.2f, %s, double jump %s"), Moves.Num(), Params.Num(), Props.Num(),
        Glider ? TEXT(" and the paraglider") : TEXT(""), Scale(), bShield ? TEXT("shield") : TEXT("no shield"),
        Has(TEXT("DoubleJump")) ? TEXT("somersault clip") : Has(TEXT("DoubleJumpTuck")) ? TEXT("tucked") : TEXT("none"));
    return true;
}

float UAdventureMoveSet::GetParam(const TCHAR* Key, float Default) const { const float* V = Params.Find(Key); return V ? *V : Default; }

FString UAdventureMoveSet::ModeName() const
{
    switch (Mode)
    {
    case EAdventureMoveMode::Air: return TEXT("air");
    case EAdventureMoveMode::Glide: return TEXT("glide");
    case EAdventureMoveMode::Climb: return TEXT("climb");
    case EAdventureMoveMode::Swim: return TEXT("swim");
    default: return TEXT("ground");
    }
}

// ----------------------------------------------------------------------------------------------------------- Actions

const FAdventureMove* UAdventureMoveSet::Current() const { return Character ? Moves.Find(Character->GetAnimationAction()) : nullptr; }
FName UAdventureMoveSet::CurrentName() const { return Character ? Character->GetAnimationAction() : NAME_None; }
float UAdventureMoveSet::SourceTime() const { return Character ? Character->GetActionSourceTime() : 0.f; }
bool UAdventureMoveSet::Playing(FName Name) const { return Character && Character->GetAnimationAction() == Name; }
bool UAdventureMoveSet::Over() const
{
    const FAdventureMove* M = Current();
    return M && !Character->DoesActionLoop() && SourceTime() >= M->End - .001f;
}
float UAdventureMoveSet::FreeAt(const FAdventureMove& M) { return M.Cancel >= 0.f ? M.Cancel : M.Idle >= 0.f ? M.Idle : M.End; }
bool UAdventureMoveSet::Busy() const
{
    const FAdventureMove* M = Current();
    // A locking loop (the charge, a plunge's fall) holds until something ends it.
    return M && IsLocking(M->Name) && (Character->DoesActionLoop() || SourceTime() < FreeAt(*M));
}

void UAdventureMoveSet::Play(FName Name, float Blend, float StartAt, float Speed)
{
    const FAdventureMove* M = Moves.Find(Name);
    if (!M || !Character) return;
    EndDefenceAction();
    const bool bLoop = M->bLoop || In(Name, { TEXT("Fall"), TEXT("PlungeAir"), TEXT("JumpCutAir") });
    Character->SetAction(Name, bLoop, Blend >= 0.f ? Blend : FMath::Clamp(M->Blend, .06f, .25f), true);
    if (Character->GetAnimationAction() != Name) return;
    Character->ActionSourceStartTime = StartAt >= 0.f ? StartAt : M->Start;
    Character->ActionPlayRate = M->Rate * Speed;
    Character->ActionDuration = FMath::Max(M->End - Character->ActionSourceStartTime, 0.f) / Character->ActionPlayRate;
    bDriving = false; DriveVelocity = FVector::ZeroVector; DriveMesh = FVector::ZeroVector;
    HitThisSwing.Reset(); PreviousBlade.Reset(); bSwung = false;
    Strength = StrengthOf(Name);
    if (Character->HasAuthority() && !Character->IsLocallyControlled())
        if (auto* Movement = Cast<UJapanCharacterMovement>(Character->GetCharacterMovement()))
        {
            const bool FromAttack = IsAttack(Name) || Prefixed(Name, {TEXT("Charge")});
            ReactionActionEdge = FromAttack ? ReactionAttackEdge : TOptional<uint16>();
        }
    LastPlayed = Name;
}

void UAdventureMoveSet::PlayLoop(FName Name, float Blend)
{
    if (Playing(Name)) return;
    const FAdventureMove* From = Current();
    const FAdventureMove* To = Moves.Find(Name);
    if (!To) return;
    float StartAt = -1.f;
    if (From && From->bLoop && From->Length > 0.f && To->Length > 0.f)
        StartAt = FMath::Fmod(FMath::Max(SourceTime(), 0.f), From->Length) / From->Length * To->Length;
    Play(Name, Blend, StartAt);
}

void UAdventureMoveSet::Stop(float Blend)
{
    EndDefenceAction();
    if (Character) Character->SetAction(NAME_None, false, Blend);
    bDriving = false; DriveVelocity = FVector::ZeroVector; DriveMesh = FVector::ZeroVector;
}

int32 UAdventureMoveSet::StrengthOf(FName Name) const
{
    if (Name == TEXT("Sneakstrike")) return 8;
    if (In(Name, { TEXT("PlungeLand"), TEXT("PlungeAir"), TEXT("Plunge") })) return 3;
    if (Name == TEXT("ChargeSpin")) return bFullCharge ? 3 : 2;
    if (In(Name, { TEXT("CutSF"), TEXT("DashCut"), TEXT("JumpCutAir"), TEXT("JumpCutLand"), TEXT("RushFinish") })) return 2;
    return 1;
}

void UAdventureMoveSet::BeginDrive(bool bSweep, const FVector& Fit, const FVector& MeshFrom)
{
    const FAdventureMove* M = Current();
    if (!M || M->Path.IsEmpty() || !Character) return;
    bDriving = true; bDriveSweep = bSweep; DriveScale = Fit; DriveMesh = MeshFrom; MeshDriveLocal = FVector::ZeroVector;
    DriveOrigin = Character->GetActorLocation(); DrivePrevious = SourceTime();
    DriveYaw = Character->GetActorRotation().Yaw;
    if (Mode == EAdventureMoveMode::Climb && bSweep) ClimbBasis(DriveForward, DriveRight, DriveUp);
    else
    {
        DriveForward = FRotator(0, DriveYaw, 0).Vector(); DriveUp = FVector::UpVector;
        DriveRight = FVector::CrossProduct(DriveUp, DriveForward);
    }
}

FVector UAdventureMoveSet::WorldPath(const FVector4f& P) const
{
    return DriveForward * (P.X * DriveScale.X) + DriveRight * (P.Y * DriveScale.Y) + DriveUp * (P.Z * DriveScale.Z);
}

float UAdventureMoveSet::DriveProgress() const
{
    const FAdventureMove* M = Current();
    if (!M || M->End <= M->Start) return 1.f;
    return FMath::Clamp((SourceTime() - M->Start) / (M->End - M->Start), 0.f, 1.f);
}

/** Moves the capsule along the playing clip's root path. On foot the path becomes the velocity (the movement component
 *  still walks it over the ground); in the move set's own movement mode it moves the capsule, swept along a wall, or
 *  placed outright for a ledge climb whose path was fitted to the ledge. */
void UAdventureMoveSet::AdvanceDrive(float Dt)
{
    const FAdventureMove* M = Current();
    if (!bDriving || !M || M->Path.IsEmpty()) { bDriving = false; DriveVelocity = FVector::ZeroVector; return; }
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const float T = SourceTime();
    if (Mode == EAdventureMoveMode::Climb && bDriveSweep) ClimbBasis(DriveForward, DriveRight, DriveUp);
    const FVector4f Now = Travelled(*M, T);
    const FVector Delta = WorldPath(Now) - WorldPath(Travelled(*M, DrivePrevious));
    DrivePrevious = T;
    const FRotator Facing(0, Mode == EAdventureMoveMode::Climb ? Character->GetActorRotation().Yaw : DriveYaw + Now.W, 0);
    if (Mode == EAdventureMoveMode::Ground || Mode == EAdventureMoveMode::Air)
    {
        DriveVelocity = Delta / FMath::Max(Dt, 1e-4f);
        Character->SetActorRotation(Facing);
        return;
    }
    if (!bDriveSweep)
    {
        const float U = DriveProgress();
        Character->SetActorLocationAndRotation(DriveOrigin + DriveMesh * U + WorldPath(Now), Facing, false, nullptr, ETeleportType::TeleportPhysics);
        Movement->Velocity = Delta / FMath::Max(Dt, 1e-4f);
        return;
    }
    FHitResult Hit;
    Movement->SafeMoveUpdatedComponent(Delta, Facing.Quaternion(), true, Hit);
    if (Hit.IsValidBlockingHit()) Slide(Movement, Delta, Facing.Quaternion(), Hit);
    Movement->Velocity = Delta / FMath::Max(Dt, 1e-4f);
}

// ------------------------------------------------------------------------------------------------------- Per frame

void UAdventureMoveSet::Advance(float Dt)
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    Clock += Dt;
    Character->ActionTime += Dt;
    AttackBuffer = FMath::Max(0.f, AttackBuffer - Dt); JumpBuffer = FMath::Max(0.f, JumpBuffer - Dt);
    NoClimb = FMath::Max(0.f, NoClimb - Dt); SinceImpact += Dt; Invulnerable = FMath::Max(0.f, Invulnerable - Dt); JustAvoid = FMath::Max(0.f, JustAvoid - Dt);
    GuardBroken = FMath::Max(0.f, GuardBroken - Dt); SinceHit += Dt;
    if (FlinchTime >= 0.f) { FlinchTime += Dt; if (FlinchTime > FlinchPeak * 9.f) FlinchTime = -1.f; }
    if (Invulnerable <= 0.f) bHopInvulnerability = false;
    AdvanceFlurry(Dt);
    // Leaving the move set's movement mode from outside (travel, the board) ends gliding, climbing and swimming.
    const bool bCustom = Movement->MovementMode == MOVE_Custom && IsTraversalMode(Movement->CustomMovementMode);
    if (Mode == EAdventureMoveMode::Glide || Mode == EAdventureMoveMode::Climb || Mode == EAdventureMoveMode::Swim)
    {
        if (!bCustom) { Mode = Movement->IsMovingOnGround() ? EAdventureMoveMode::Ground : EAdventureMoveMode::Air; ClimbShiftTarget = 0.f; bDriving = false; }
    }
    if (Mode == EAdventureMoveMode::Ground || Mode == EAdventureMoveMode::Air)
    {
        if (Movement->IsMovingOnGround()) { Mode = EAdventureMoveMode::Ground; SinceGrounded = 0.f; }
        else if (Movement->IsFalling())
        {
            if (Mode == EAdventureMoveMode::Ground) { FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f; }
            Mode = EAdventureMoveMode::Air; SinceGrounded += Dt;
        }
    }
    if (bDown) AdvanceDown(Dt);
    else switch (Mode)
    {
    case EAdventureMoveMode::Ground: AdvanceGround(Dt); break;
    case EAdventureMoveMode::Air: AdvanceAir(Dt); break;
    case EAdventureMoveMode::Glide: AdvanceGlide(Dt); break;
    case EAdventureMoveMode::Climb: AdvanceClimb(Dt); break;
    case EAdventureMoveMode::Swim: AdvanceSwim(Dt); break;
    }
    if (bDriving && (Mode == EAdventureMoveMode::Ground || Mode == EAdventureMoveMode::Air)) AdvanceDrive(Dt);
    // Standing, climbing or swimming gives the double jump back.
    if (Mode != EAdventureMoveMode::Air && Mode != EAdventureMoveMode::Glide) bAirJumpUsed = false;
    AdvanceDoubleJump(Dt);
    AdvanceCombat(Dt);
    AdvanceEquipment(Dt);
    AdvanceGliderGrip(Dt);
    AdvanceMeshOffset(Dt);
    if (const auto* MovementComponent = Cast<UJapanCharacterMovement>(Movement); !MovementComponent || !MovementComponent->IsReplaying()) AdvanceEffects(Dt);
}

void UAdventureMoveSet::Phys(float Dt, int32 Iterations)
{
    if (!Character || Dt <= 0.f) return;
    switch (Mode)
    {
    case EAdventureMoveMode::Glide: PhysGlide(Dt); break;
    case EAdventureMoveMode::Climb: PhysClimb(Dt); break;
    case EAdventureMoveMode::Swim: if (bDriving) AdvanceDrive(Dt); else PhysSwim(Dt); break;
    default: Character->GetCharacterMovement()->SetMovementMode(MOVE_Falling); break;
    }
}

bool UAdventureMoveSet::OverrideVelocity(FVector& Velocity) const
{
    if (!Character || (Mode != EAdventureMoveMode::Ground && Mode != EAdventureMoveMode::Air)) return false;
    const FName Name = CurrentName();
    if (bDriving) { Velocity.X = DriveVelocity.X; Velocity.Y = DriveVelocity.Y; return true; }
    if (LungeTime > 0.f && Mode == EAdventureMoveMode::Ground)
    {
        // Toward where the blade reaches the target, stopping there (re-aimed every step as either moves).
        FVector V = FVector::ZeroVector;
        if (const AActor* Focus = LungeTarget.Get(); Focus || (JapanNetwork::IsOnline(Character->GetWorld()) && bLungePoint))
        {
            const FVector To = ((JapanNetwork::IsOnline(Character->GetWorld()) ? LungePoint : Focus->GetActorLocation()) - Character->GetActorLocation()) * FVector(1, 1, 0);
            const float Gap = float(To.Size()) - LungeStand;
            if (Gap > 2.f) V = To.GetSafeNormal() * FMath::Min(Gap / FMath::Max(LungeTime, .03f), 1100.f);
        }
        Velocity.X = V.X; Velocity.Y = V.Y; return true;
    }
    if (Mode == EAdventureMoveMode::Air && (IsHop(Name) || In(Name, { TEXT("JumpCut"), TEXT("JumpCutAir") }))) { Velocity.X = HopVelocity.X; Velocity.Y = HopVelocity.Y; return true; }
    if (Mode == EAdventureMoveMode::Air && In(Name, { TEXT("Plunge"), TEXT("PlungeAir") })) { Velocity.X = Velocity.Y = 0.; return true; }
    // The flurry rush closes in on its target.
    if (InFlurry() && (Target.IsValid() || (JapanNetwork::IsOnline(Character->GetWorld()) && bFlurryPoint)) && Prefixed(Name, { TEXT("Flurry"), TEXT("Rush") }))
    {
        const FVector To = ((JapanNetwork::IsOnline(Character->GetWorld()) ? FlurryPoint : Target->GetActorLocation()) - Character->GetActorLocation()) * FVector(1, 1, 0);
        const FVector V = To.Size() > Reach() ? To.GetSafeNormal() * 900.f : FVector::ZeroVector;
        Velocity.X = V.X; Velocity.Y = V.Y; return true;
    }
    return false;
}

bool UAdventureMoveSet::ControlsRotation() const
{
    if (Mode == EAdventureMoveMode::Glide || Mode == EAdventureMoveMode::Climb || Mode == EAdventureMoveMode::Swim) return true;
    if (FlipTime >= 0.f) return true;   // the somersault keeps the heading it set off on
    if (bLocked || bDriving || bDown) return true;
    return IsLocking(CurrentName());
}

bool UAdventureMoveSet::LocksMovement() const
{
    if (Mode == EAdventureMoveMode::Glide || Mode == EAdventureMoveMode::Climb || Mode == EAdventureMoveMode::Swim || bDown) return true;
    return Busy();
}

float UAdventureMoveSet::GetMaxWalkSpeed(float Default) const
{
    if (Mode != EAdventureMoveMode::Ground || !bLocked) return Default;
    const bool bWalk = Character && (Character->bWalk || Character->bJog);
    const FAdventureMove* M = Moves.Find(bWalk ? TEXT("LockWalkF") : TEXT("LockRunF"));
    return M && M->Speed > 1.f ? M->Speed : bWalk ? 130.f : 300.f;
}

// ------------------------------------------------------------------------------------------------------- On foot

void UAdventureMoveSet::AdvanceGround(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    const FVector W = Wish();
    // Dry land to come back to after drowning; deep water swims.
    float Surface = 0.f;
    const bool bWater = WaterAt(Here, Surface);
    if (!bWater || Feet() > Surface + 5.f) { SafeShore = Here - FVector(0, 0, HalfHeight()); bHasSafeShore = true; }
    if (bWater && Feet() < Surface - HalfHeight() * 1.1f) { StartSwim(); return; }

    // Lock-on while the guard button is held: face the target (or the way he faced), strafe, the camera behind.
    const bool bWantLock = bGuardHeld && !Character->bIsCrouched;
    if (bWantLock != bLocked)
    {
        bLocked = bWantLock;
        if (bLocked) { Target = !JapanNetwork::IsOnline(Character->GetWorld()) || Character->HasAuthority() ? FindTarget(1500.f, 70.f) : nullptr; LockYaw = Character->GetActorRotation().Yaw; }
        else { Target = nullptr; bLockPoint = false; }
    }
    const FAdventureMove* Now = Current();
    FName Name = Now ? Now->Name : NAME_None;
    if (bLocked)
    {
        // Locked on with nothing to face (nothing was in front at the press): look again a few times a second.
        if ((!JapanNetwork::IsOnline(Character->GetWorld()) || Character->HasAuthority()) && !Target.IsValid() && FMath::FloorToInt(Clock * 4.f) != FMath::FloorToInt((Clock - Dt) * 4.f)) Target = FindTarget(1500.f, 70.f);
        AActor* Focus = Target.Get();
        if (Focus && (FVector::Dist2D(Focus->GetActorLocation(), Here) > 2500.f || !IsTargetable(Focus))) { Target = nullptr; Focus = nullptr; }
        if (Focus && (!JapanNetwork::IsOnline(Character->GetWorld()) || Character->HasAuthority())) { LockPoint = Focus->GetActorLocation(); bLockPoint = true; }
        else if (Character->HasAuthority()) bLockPoint = false;
        const float FaceYaw = JapanNetwork::IsOnline(Character->GetWorld())
            ? (bLockPoint ? (LockPoint - Here).Rotation().Yaw : LockYaw)
            : (Focus ? (Focus->GetActorLocation() - Here).Rotation().Yaw : LockYaw);
        if (!Busy() || IsLockLoop(Name))
            Character->SetActorRotation(FRotator(0, FMath::FixedTurn(Character->GetActorRotation().Yaw, FaceYaw, 720.f * Dt), 0));
        if (!JapanNetwork::IsOnline(Character->GetWorld()) && Character->Controller && Character->LookGrace <= 0.f)
        {
            const FRotator View = Character->Controller->GetControlRotation();
            Character->Controller->SetControlRotation(FMath::RInterpTo(View, FRotator(View.Pitch, FaceYaw, 0), Dt, Focus ? 5.f : 3.f));
        }
        if (Name.IsNone() || IsLockLoop(Name))
        {
            const FVector Local = Character->GetActorRotation().UnrotateVector(W);
            FName Clip = TEXT("LockWait");
            if (W.Size2D() > .1f && Movement->Velocity.Size2D() > 15.f)
            {
                const bool bRun = !(Character->bWalk || Character->bJog) && W.Size2D() > .6f;
                const TCHAR* Dir = FMath::Abs(Local.X) >= FMath::Abs(Local.Y) ? (Local.X > 0 ? TEXT("F") : TEXT("B")) : (Local.Y > 0 ? TEXT("R") : TEXT("L"));
                Clip = FName(*FString::Printf(TEXT("Lock%s%s"), bRun ? TEXT("Run") : TEXT("Walk"), Dir));
            }
            if (Has(Clip)) PlayLoop(Clip, .2f);
        }
    }
    else if (IsLockLoop(Name)) Stop(.2f);

    // Actions that end, and what follows them.
    Now = Current(); Name = Now ? Now->Name : NAME_None;
    if (Now && Over())
    {
        if (Name == TEXT("HardLand") && Has(TEXT("HardLandUp"))) Play(TEXT("HardLandUp"));
        else if (Name == TEXT("ChargeStart") && Has(TEXT("ChargeWait"))) Play(TEXT("ChargeWait"));
        else if (In(Name, { TEXT("Jump"), TEXT("RunJumpL"), TEXT("RunJumpR"), TEXT("Fall") })) Play(TEXT("Land"));
        else if (!In(Name, { TEXT("ChargeWait") })) Stop(Name == TEXT("Land") ? .12f : .2f);
        Now = Current(); Name = Now ? Now->Name : NAME_None;
    }
    // Moving ends a finished action early: a landing at once, anything else from its cancel point.
    if (Now && !Character->DoesActionLoop() && !W.IsNearlyZero() && !In(Name, { TEXT("ChargeStart"), TEXT("ChargeWait"), TEXT("HardLand") }))
    {
        const float Free = In(Name, { TEXT("Land"), TEXT("GlideOff") }) ? 0.f : FreeAt(*Now);
        if (SourceTime() >= Free && !In(Name, { TEXT("RunLandL"), TEXT("RunLandR") })) Stop(.2f);
    }
    // A jump pressed during a landing or a cut goes as soon as it can.
    if (JumpBuffer > 0.f && CanJump()) StartJump();
    if (Mode != EAdventureMoveMode::Ground) return;

    // Walking into a steep wall for a moment grabs it: the nearest of its faces at the waist, chest and head, so a sill
    // or a beam standing out of the wall still counts; pressed against something, the reach is longer.
    if (NoClimb <= 0.f && !Busy() && W.Size2D() > .5f && !Character->bIsCrouched && Has(TEXT("ClimbWait")))
    {
        const FVector Along = W.GetSafeNormal2D();
        const bool bPressed = Character->GetCharacterMovement()->Velocity.Size2D() < 60.f;
        const float Reach = Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + (bPressed ? 50.f : 30.f);
        FHitResult Wall;
        int32 Faces = 0;
        for (const float Up : { 0.f, HalfHeight() * .5f, HalfHeight() * .8f })
        {
            FHitResult Face;
            if (!FindWall(Along, Face, Up, 0.f, Reach) || !Climbable(Face) || (Along | -Face.ImpactNormal.GetSafeNormal2D()) <= .6f) continue;
            if (!Faces++ || Face.Distance < Wall.Distance) Wall = Face;
        }
        // A slope too steep to walk keeps the probes off it at the waist: what the capsule ran into is the wall.
        if (Faces < 2 && SinceImpact < .1f && Climbable(LastImpact) && (Along | -LastImpact.ImpactNormal.GetSafeNormal2D()) > .5f)
        {
            Wall = LastImpact; Faces = 2;
        }
        if (Faces >= 2)
        {
            PushTime += Dt;
            if (PushTime > .12f) { PushTime = 0.f; StartClimb(Wall, false); return; }
        }
        else PushTime = 0.f;
    }
    else PushTime = 0.f;
}

void UAdventureMoveSet::AdvanceAir(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    FallStartZ = FMath::Max(FallStartZ, Here.Z);
    FallSpeed = Movement->Velocity.Z > 0.f ? 0.f : FMath::Max(FallSpeed, float(-Movement->Velocity.Z));
    float Surface = 0.f;
    if (WaterAt(Here, Surface) && Feet() < Surface - 10.f) { StartSwim(); return; }
    bLocked = false;
    const FAdventureMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (In(Name, { TEXT("Jump"), TEXT("RunJumpL"), TEXT("RunJumpR") })) { if (Over()) Play(TEXT("Fall"), .2f); }
    else if (Name == TEXT("JumpCut")) { if (Over() && Has(TEXT("JumpCutAir"))) Play(TEXT("JumpCutAir"), .05f); }
    else if (Name == TEXT("Plunge")) { if (Over() && Has(TEXT("PlungeAir"))) Play(TEXT("PlungeAir"), .05f); }
    else if (IsDoubleJump(Name)) { if (FlipTime < 0.f && (Name == TEXT("DoubleJumpTuck") || Over())) Play(TEXT("Fall"), .2f); }   // AdvanceDoubleJump times it
    else if (IsHop(Name) || In(Name, { TEXT("Fall"), TEXT("JumpCutAir"), TEXT("PlungeAir"), TEXT("ClimbOff") }) || Prefixed(Name, { TEXT("Hit"), TEXT("Knock") })) {}
    else if (SinceGrounded > .15f || bJumped) Play(TEXT("Fall"), .2f);   // walked off an edge, or whatever played on the ground
    // A hop, jump cut or plunge held up on a bank too steep to stand on (its steering pushes into it): let go and slide off.
    if (Mode == EAdventureMoveMode::Air && Movement->Velocity.Z > -10.f && SinceGrounded > .2f &&
        (IsHop(Name) || In(Name, { TEXT("JumpCut"), TEXT("JumpCutAir"), TEXT("Plunge"), TEXT("PlungeAir") })))
    {
        FFindFloorResult Floor;
        Movement->FindFloor(Here, Floor, false);
        if (Floor.bBlockingHit && !Floor.bWalkableFloor && Floor.FloorDist < 10.f) { HopVelocity = FVector::ZeroVector; Play(TEXT("Fall"), .2f); }
    }
    // A jump pressed just after leaving the ground opens the glider as soon as it may.
    if (JumpBuffer > 0.f && CanGlide()) { JumpBuffer = 0.f; OpenGlider(); return; }
    // Falling or jumping into a steep wall grabs it.
    if (NoClimb <= 0.f && !IsAttack(Name) && !IsHop(Name) && Has(TEXT("ClimbWait")))
    {
        FHitResult Wall;
        const FVector Facing = Character->GetActorForwardVector();
        const FVector Toward = Movement->Velocity.Size2D() > 50.f ? FVector(Movement->Velocity.GetSafeNormal2D()) : Wish().GetSafeNormal2D();
        if (FindWall(Facing, Wall) && Climbable(Wall) && (Toward | -Wall.ImpactNormal.GetSafeNormal2D()) > .4f) { StartClimb(Wall, true); return; }
    }
}

void UAdventureMoveSet::Impact(const FHitResult& Hit)
{
    if (Mode == EAdventureMoveMode::Ground && Hit.IsValidBlockingHit()) { LastImpact = Hit; SinceImpact = 0.f; }
}

void UAdventureMoveSet::Landed(const FHitResult& Hit)
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const float Height = FMath::Max(0.f, FallStartZ - float(Character->GetActorLocation().Z));
    if (UJapanFootstepComponent* Steps = Character->GetFootsteps())
        Steps->Land(Hit, FMath::GetMappedRangeValueClamped(FVector2f(200.f, 1100.f), FVector2f(.55f, 1.4f), FallSpeed));
    if (FlipTime >= 0.f) FlipSettle = .2f;
    bJumped = false; bAirJumpUsed = false; FlipTime = -1.f; HopVelocity = FVector::ZeroVector; SinceGrounded = 0.f; FallSpeed = 0.f; FallStartZ = Character->GetActorLocation().Z;
    if (Mode != EAdventureMoveMode::Ground && Mode != EAdventureMoveMode::Air) return;
    Mode = EAdventureMoveMode::Ground;
    if (bDown) return;
    const FName Name = CurrentName();
    if (Name == TEXT("HopL") || Name == TEXT("HopR"))
    {
        Play(Name == TEXT("HopL") ? TEXT("HopLandL") : TEXT("HopLandR"));
        Movement->Velocity *= FVector(.2, .2, 1.);
        return;
    }
    if (Name == TEXT("BackFlip")) { Play(TEXT("BackFlipLand")); Movement->Velocity *= FVector(.2, .2, 1.); return; }
    if (In(Name, { TEXT("JumpCut"), TEXT("JumpCutAir") }) && Has(TEXT("JumpCutLand"))) { Play(TEXT("JumpCutLand")); Movement->StopMovementImmediately(); return; }
    if (In(Name, { TEXT("Plunge"), TEXT("PlungeAir") }) && Has(TEXT("PlungeLand")))
    {
        // The plunge lands on everything within reach of the impact, and takes no fall damage.
        Play(TEXT("PlungeLand")); Movement->StopMovementImmediately();
        const FVector Ground = Character->GetActorLocation() - FVector(0, 0, HalfHeight());
        if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character)) { FX->Dust(Ground, 1.6f); FX->Shake(.45f); }
        for (TActorIterator<AActor> It(Character->GetWorld()); It; ++It)
            if (IsTargetable(*It) && FVector::Dist(It->GetActorLocation(), Ground) < 320.f)
                Strike(*It, 3, It->GetActorLocation(), FVector::DownVector);
        return;
    }
    const float Hard = GetParam(TEXT("HardLandHeight"), 450.f), Hurt = GetParam(TEXT("FallDamageHeight"), 900.f);
    if (Height > Hard && Has(TEXT("HardLand")))
    {
        Play(TEXT("HardLand"), .05f); Movement->StopMovementImmediately();
        if (Height > Hurt) TakeHit((Height - Hurt) / 12.f, Character->GetActorLocation() + Character->GetActorForwardVector() * 100.f, false, nullptr, false);
        return;
    }
    if (Movement->Velocity.Size2D() > 250.f && Has(TEXT("RunLandL"))) { Play(bRunFoot ? TEXT("RunLandL") : TEXT("RunLandR"), .06f); bRunFoot = !bRunFoot; }
    else Play(TEXT("Land"), .06f);
}

bool UAdventureMoveSet::CanJump() const
{
    return Character && (Mode == EAdventureMoveMode::Ground || (Mode == EAdventureMoveMode::Air && !bJumped && SinceGrounded < .12f)) && !Busy() && !bDown;
}

void UAdventureMoveSet::StartJump()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (Character->bIsCrouched) Character->UnCrouch();
    // A sprinting jump costs stamina (EnergyDashJump).
    if (Character->Stamina.Sprinting) UseStamina(GetParam(TEXT("PlayerJump.EnergyDashJump"), 300.f) / 1000.f);
    const float Speed = Movement->Velocity.Size2D();
    Character->LaunchCharacter(FVector(0, 0, Movement->JumpZVelocity), false, true);
    bJumped = true; JumpBuffer = 0.f; FallSpeed = 0.f; FallStartZ = Character->GetActorLocation().Z;
    Mode = EAdventureMoveMode::Air;
    if (Speed > 250.f && Has(TEXT("RunJumpL"))) { Play(bRunFoot ? TEXT("RunJumpL") : TEXT("RunJumpR"), .08f); bRunFoot = !bRunFoot; }
    else Play(TEXT("Jump"), .08f);
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
        FX->Dust(Character->GetActorLocation() - FVector(0, 0, HalfHeight()), Speed > 250.f ? .55f : .35f, -FVector(Movement->Velocity.GetSafeNormal2D()) * .3f);
}

// ------------------------------------------------------------------------------------------------------- Double jump

bool UAdventureMoveSet::CanDoubleJump() const
{
    if (!Character || Mode != EAdventureMoveMode::Air || bAirJumpUsed || bDown || CanJump()) return false;
    if (!Has(TEXT("DoubleJump")) && !Has(TEXT("DoubleJumpTuck"))) return false;
    // As Cairo's: after a jump at once, after walking off an edge a moment later.
    if (!bJumped && SinceGrounded < .10f) return false;
    const FName Name = CurrentName();
    return !IsAttack(Name) && !IsHop(Name) && !Prefixed(Name, { TEXT("Hit"), TEXT("Knock"), TEXT("Climb") });
}

/** Cairo's double jump: a fresh 650 cm/s upward launch, the ground speed turned once toward the stick (all of it, even
 *  backward; the stick at rest keeps the heading), and one forward somersault: his own clip, or a tuck the game turns. */
void UAdventureMoveSet::StartDoubleJump()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    FVector Velocity = Movement->Velocity;
    const FVector W = Wish();
    if (W.Size2D() > .1f)
    {
        const FVector Direction = W.GetSafeNormal2D();
        Velocity = Direction * Velocity.Size2D();
        Character->SetActorRotation(FRotator(0, Direction.Rotation().Yaw, 0));
    }
    Velocity.Z = GetParam(TEXT("DoubleJumpSpeed"), 650.f);
    Character->LaunchCharacter(Velocity, true, true);
    bAirJumpUsed = true; bJumped = true; JumpBuffer = 0.f; FallSpeed = 0.f; HopVelocity = FVector::ZeroVector;
    FallStartZ = Character->GetActorLocation().Z;
    ++DoubleJumpCount;
    const bool bClip = Has(TEXT("DoubleJump"));
    Play(bClip ? TEXT("DoubleJump") : TEXT("DoubleJumpTuck"), bClip ? .05f : .08f);
    FlipTime = 0.f; FlipAngle = 0.f; FlipPivot = FVector::ZeroVector; FlipLift = 0.f; FlipSettle = 0.f;
    if (const USkeletalMeshComponent* Body = Character->GetMesh())
        FlipHips = Body->GetSocketTransform(Character->GetSkateBone(TEXT("pelvis")), RTS_Component).GetLocation().Z;
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
    {
        // A burst of air pushed down from the feet: a pale shock ring, a puff of wind motes and a soft whoosh.
        const FVector Feet = Character->GetActorLocation() - FVector(0, 0, HalfHeight() * .9f);
        AAtelierFX::FParticle& Ring = FX->Spawn(AAtelierFX::ESprite::Ring, Feet); Ring.Size0 = 18.f; Ring.Size1 = 130.f; Ring.Life = .26f;
        Ring.Color = FLinearColor(.78f, .9f, 1.f) * 2.4f;
        AAtelierFX::FParticle& Inner = FX->Spawn(AAtelierFX::ESprite::Ring, Feet); Inner.Size0 = 8.f; Inner.Size1 = 70.f; Inner.Life = .16f;
        Inner.Color = FLinearColor(1.f, 1.f, 1.f) * 2.8f;
        FX->Burst(Feet, FVector(0, 0, -.6f), 18, 520.f, FLinearColor(.85f, .93f, 1.f) * 4.f, .32f, 2.4f);
        FX->Flash(Feet, 60.f, FLinearColor(.8f, .9f, 1.f) * 2.2f, .1f);
        FX->Play(TEXT("dash"), Feet, .5f, .1f);
    }
}

/** The somersault under way. A tucked one turns the mesh one full turn forward about the ball's middle on Cairo's timing
 *  (his DoubleJump: the turn from .08 s to .6 s, upright by .63 s), lifted so the hips stay where they were. */
void UAdventureMoveSet::AdvanceDoubleJump(float Dt)
{
    if (FlipTime < 0.f) return;
    const FName Name = CurrentName();
    if (!IsDoubleJump(Name) || Mode != EAdventureMoveMode::Air) { FlipTime = -1.f; return; }   // a glider, a wall, the ground
    FlipTime += Dt;
    USkeletalMeshComponent* Body = Character->GetMesh();
    const float S = Scale();
    if (Name == TEXT("DoubleJumpTuck"))
    {
        constexpr float Start = .08f, Turn = .52f, Done = .63f;
        FlipAngle = 360.f * Smooth((FlipTime - Start) / Turn);
        // While the tuck blends in the mesh rises as the hips draw up; then the ball's middle (its hips, a little up, in
        // the capsule's frame) is fixed as the pivot.
        if (FlipPivot.IsZero()) FlipLift = HipLift();
        if (FlipPivot.IsZero() && FlipTime >= Start && Body)
        {
            const FVector Local = Body->GetSocketTransform(Character->GetSkateBone(TEXT("pelvis")), RTS_Component).GetLocation();
            FlipPivot = FTransform(MeshBaseRotation, MeshBase + FVector(0, 0, FlipLift), Body->GetRelativeScale3D()).TransformPosition(Local) + FVector(0, 0, 8.f * S);
        }
        if (FlipTime >= Done) { FlipTime = -1.f; FlipSettle = .3f; Play(TEXT("Fall"), .2f); return; }
    }
    else if (Over()) { FlipTime = -1.f; Play(TEXT("Fall"), .15f); return; }
    // A wind swirl around the turning body.
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character); FX && FlipTime > .06f && FlipTime < .6f)
    {
        const FVector Center = Character->GetActorLocation() + Character->GetActorRotation().RotateVector(FlipPivot.IsZero() ? FVector::ZeroVector : FlipPivot);
        const FVector Forward = Character->GetActorForwardVector();
        for (int32 I = 0; I < 2; ++I)
        {
            const float A = FMath::DegreesToRadians(FlipAngle + 180.f * I);
            const FVector Offset = (Forward * FMath::Sin(A) + FVector::UpVector * FMath::Cos(A)) * 55.f * FMath::Max(S, .6f);
            AAtelierFX::FParticle& P = FX->Spawn(AAtelierFX::ESprite::Glow, Center + Offset);
            P.V = FVector::CrossProduct(Character->GetActorRightVector(), Offset).GetSafeNormal() * 160.f;
            P.Life = .22f; P.Size0 = 7.f; P.Size1 = 2.f; P.Drag = 3.f; P.Color = FLinearColor(.82f, .92f, 1.f) * 3.2f; P.FadeIn = .03f;
        }
    }
}

bool UAdventureMoveSet::CanDodge() const { return Mode == EAdventureMoveMode::Ground && !Busy() && !bDown && Has(TEXT("BackFlip")); }

/** The side hop (stick to the side) or the backflip (anything else), launched with the adventure library's speeds and heights. Both are
 *  invulnerable while airborne; a strike that arrives in their first moments is a perfect dodge (the flurry rush). */
void UAdventureMoveSet::StartHop()
{
    const FRotator Facing(0, Character->GetActorRotation().Yaw, 0);
    const FVector Local = Facing.UnrotateVector(Wish());
    const float S = Scale(), G = Gravity();
    const bool bSide = FMath::Abs(Local.Y) > .3f && FMath::Abs(Local.Y) >= FMath::Abs(Local.X) && Has(TEXT("HopL")) && Has(TEXT("HopR"));
    FVector V; FName Clip;
    if (bSide)
    {
        const float Sign = Local.Y > 0.f ? 1.f : -1.f;
        const float Speed = GetParam(TEXT("PlayerSideStep.SpeedF"), .18f) * 3000.f * S, Height = GetParam(TEXT("PlayerSideStep.Height"), .8f) * 100.f * S;
        V = Facing.RotateVector(FVector(0, Sign * Speed, 0)) + FVector(0, 0, FMath::Sqrt(2.f * G * Height));
        Clip = Sign > 0.f ? TEXT("HopR") : TEXT("HopL");
    }
    else
    {
        const float Speed = GetParam(TEXT("PlayerBackJump.BJSpeedF"), .15f) * 3000.f * S, Height = GetParam(TEXT("PlayerBackJump.BJHeight"), 1.11f) * 100.f * S;
        V = Facing.RotateVector(FVector(-Speed, 0, 0)) + FVector(0, 0, FMath::Sqrt(2.f * G * Height));
        Clip = TEXT("BackFlip");
    }
    if (Character->bIsCrouched) Character->UnCrouch();
    Character->LaunchCharacter(V, true, true);
    HopVelocity = FVector(V.X, V.Y, 0.f);
    Mode = EAdventureMoveMode::Air; bJumped = true; JumpBuffer = 0.f; FallStartZ = Character->GetActorLocation().Z;
    const float Flight = 2.f * float(V.Z) / FMath::Max(G, 1.f);
    Invulnerable = FMath::Min(GetParam(TEXT("PlayerSideStep.NoDamageTime"), 40.f) / 30.f, Flight + .1f);
    JustAvoid = .25f; bHopInvulnerability = true;
    Play(Clip, .05f);
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
    {
        // Kicked-up dust, speed lines streaming away from the leap and a quick whoosh.
        const FVector Ground = Character->GetActorLocation() - FVector(0, 0, HalfHeight());
        const FVector Away = -HopVelocity.GetSafeNormal();
        FX->Dust(Ground, .75f, Away * .5f);
        for (int32 I = 0; I < 9; ++I)
        {
            AAtelierFX::FParticle& P = FX->Spawn(AAtelierFX::ESprite::Spark, Character->GetActorLocation() + FVector(0, 0, FMath::FRandRange(-.6f, .6f) * HalfHeight()) + Away * 20.f);
            P.V = Away * FMath::FRandRange(500.f, 900.f) + FVector(0, 0, FMath::FRandRange(-40.f, 40.f));
            P.Stretch = .035f; P.Drag = 4.f; P.Life = FMath::FRandRange(.16f, .26f); P.Size0 = 2.6f; P.Size1 = 1.f;
            P.Color = FLinearColor(.9f, .95f, 1.f) * 3.5f;
        }
        FX->Play(TEXT("dash"), Ground, .55f, .1f);
    }
}

// --------------------------------------------------------------------------------------------------------- Queries

float UAdventureMoveSet::Scale() const
{
    // A retargeted body (Cairo's) states its own: its mesh is at full scale, the body smaller than the adventure library's.
    if (const float* Body = Params.Find(TEXT("BodyScale"))) return *Body;
    return Character && Character->GetMesh() ? float(Character->GetMesh()->GetRelativeScale3D().X) : 1.f;
}
float UAdventureMoveSet::Gravity() const { return Character ? -Character->GetCharacterMovement()->GetGravityZ() : 980.f; }
float UAdventureMoveSet::HalfHeight() const { return Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight(); }
float UAdventureMoveSet::Feet() const { return float(Character->GetActorLocation().Z) - HalfHeight(); }
float UAdventureMoveSet::Reach() const { return Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + 110.f; }
void UAdventureMoveSet::UseStamina(float Rings) { if (Character && Rings > 0.f) Character->Stamina.Use(Rings); }
bool UAdventureMoveSet::HasStamina() const { return Character && !Character->Stamina.Exhausted && Character->Stamina.Units > 0.f; }

FVector UAdventureMoveSet::Wish() const
{
    const FVector2D Intent = Character->GetMoveIntent();
    const FRotationMatrix Basis(FRotator(0, Character->GetControlRotation().Yaw, 0));
    return (Basis.GetUnitAxis(EAxis::X) * Intent.Y + Basis.GetUnitAxis(EAxis::Y) * Intent.X).GetClampedToMaxSize(1.f);
}

bool UAdventureMoveSet::Trace(const FVector& From, const FVector& To, FHitResult& Hit) const
{
    UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(AdventureMoves), false, Character);
    FCollisionResponseParams Response;
    Capsule->InitSweepCollisionParams(Query, Response);
    return Character->GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, Capsule->GetCollisionObjectType(), FCollisionShape::MakeSphere(4.f), Query, Response);
}

bool UAdventureMoveSet::Blocked(const FVector& Center) const
{
    UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(AdventureRoom), false, Character);
    FCollisionResponseParams Response;
    Capsule->InitSweepCollisionParams(Query, Response);
    const FCollisionShape Shape = FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius() - 2.f, HalfHeight() - 2.f);
    return Character->GetWorld()->OverlapBlockingTestByChannel(Center, FQuat::Identity, Capsule->GetCollisionObjectType(), Shape, Query, Response);
}

bool UAdventureMoveSet::FindWall(const FVector& Direction, FHitResult& Hit, float Up, float Side, float Distance) const
{
    const FVector Along = Direction.GetSafeNormal();
    const FVector Right = FVector::CrossProduct(FVector::UpVector, Along).GetSafeNormal();
    const FVector From = Character->GetActorLocation() + FVector(0, 0, Up) + Right * Side;
    const float Length = Distance > 0.f ? Distance : Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + 30.f;
    return Trace(From, From + Along * Length, Hit);
}

bool UAdventureMoveSet::Climbable(const FHitResult& Hit) const
{
    if (!Hit.bBlockingHit || Hit.bStartPenetrating) return false;
    const float Steep = FMath::Cos(FMath::DegreesToRadians(GetParam(TEXT("ClimbEnableAngle"), 50.f)));
    if (Hit.ImpactNormal.Z >= Steep || Hit.ImpactNormal.Z < -.35f) return false;
    // Not people, creatures or props, and not the skate parks' ramps and rails.
    const AActor* A = Hit.GetActor();
    return !(A && (A->IsA<APawn>() || A->IsA<ASwordDummy>() || A->IsA<AMegaRamp>() ||
        A->IsA<ASuperUltraMegaPark>() || A->ActorHasTag(TEXT("SkatePark"))));
}

bool UAdventureMoveSet::IsTargetable(AActor* Actor) const
{
    if (!Actor || Actor == Character) return false;
    if (const AWandererCharacter* Other = Cast<AWandererCharacter>(Actor))
        return Other->GetMoves() && (Character->IsSparringWith(Other) || Other->IsSparringWith(Character));
    if (const AFoxHunter* Fox = Cast<AFoxHunter>(Actor)) return Fox->IsAlive();
    return Actor->IsA<ASwordDummy>();
}

bool UAdventureMoveSet::IsUnawareTarget(AActor* Actor) const
{
    return Actor && Actor->IsA<ASwordDummy>();
}

AActor* UAdventureMoveSet::FindTarget(float Range, float Cone) const
{
    if (!Character) return nullptr;
    const FVector Here = Character->GetActorLocation(), Forward = Character->GetActorForwardVector();
    AActor* Best = nullptr; float BestScore = TNumericLimits<float>::Max();
    for (TActorIterator<AActor> It(Character->GetWorld()); It; ++It)
    {
        if (!It->IsA<AFoxHunter>() && !It->IsA<ASwordDummy>() && !It->IsA<AWandererCharacter>()) continue;
        if (!IsTargetable(*It)) continue;
        const FVector To = (It->GetActorLocation() - Here) * FVector(1, 1, 0);
        const float Distance = float(To.Size());
        if (Distance > Range) continue;
        const float Angle = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(To.GetSafeNormal() | Forward), -1.f, 1.f)));
        if (Angle > Cone && Distance > 200.f) continue;
        const float Score = Distance * (1.f + Angle / 90.f);
        if (Score < BestScore) { BestScore = Score; Best = *It; }
    }
    return Best;
}

// ----------------------------------------------------------------------------------------------------------- Reset

void UAdventureMoveSet::Reset()
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (Movement->MovementMode == MOVE_Custom && IsTraversalMode(Movement->CustomMovementMode)) Movement->SetMovementMode(MOVE_Falling);
    Mode = Movement->IsMovingOnGround() ? EAdventureMoveMode::Ground : EAdventureMoveMode::Air;
    ShowGlider(false);
    SetArmed(false);
    bLocked = bGuardHeld = bAttackHeld = bJumpHeld = bCharging = bDown = bDriving = bJumped = false;
    Target = nullptr; bLockPoint = false; HopVelocity = DriveVelocity = FVector::ZeroVector;
    // An activity reset cannot retain an old cut's lunge or actor reference.
    LungeTarget = nullptr; LungeTime = 0.f; bLungePoint = false;
    JumpBuffer = AttackBuffer = NoClimb = Invulnerable = JustAvoid = SwimDashTime = GuardBroken = 0.f;
    FlinchTime = -1.f; HitStreak = 0; SinceHit = 99.f;
    if (FlurryTime > 0.f) { FlurryTime = 0.f; if (!JapanNetwork::IsOnline(Character->GetWorld())) Character->CustomTimeDilation = 1.f; }
    ClimbShift = ClimbShiftTarget = 0.f; MeshOffsetLength = 0.f; MeshDriveLocal = DriveMesh = FVector::ZeroVector;
    FlipTime = -1.f; FlipAngle = FlipLift = FlipSettle = 0.f; bAirJumpUsed = false;
    if ((bMeshOffset || bMeshTurned) && Character->GetMesh())
    {
        Character->GetMesh()->SetRelativeLocationAndRotation(MeshBase, MeshBaseRotation);
        bMeshOffset = bMeshTurned = false;
    }
    FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f;
}

FString UAdventureMoveSet::Describe() const
{
    TSharedRef<FJsonObject> O = MakeShared<FJsonObject>();
    if (!Character) return TEXT("{}");
    const UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    O->SetStringField(TEXT("mode"), ModeName());
    O->SetNumberField(TEXT("scale"), Scale());
    O->SetStringField(TEXT("action"), Character->GetAnimationAction().ToString());
    O->SetNumberField(TEXT("source_time"), SourceTime());
    O->SetBoolField(TEXT("armed"), bArmed);
    O->SetBoolField(TEXT("locked"), bLocked);
    O->SetBoolField(TEXT("guarding"), IsGuarding());
    O->SetBoolField(TEXT("down"), bDown);
    O->SetBoolField(TEXT("glider"), bGliderShown);
    O->SetBoolField(TEXT("driving"), bDriving);
    O->SetBoolField(TEXT("charging"), bCharging);
    O->SetNumberField(TEXT("flurry"), FlurryTime);
    O->SetStringField(TEXT("target"), Target.IsValid() ? Target->GetName() : FString());
    O->SetNumberField(TEXT("stamina"), Character->Stamina.Units);
    O->SetBoolField(TEXT("exhausted"), Character->Stamina.Exhausted);
    O->SetNumberField(TEXT("health"), Character->GetSword() ? Character->GetSword()->GetHealth() : 0.f);
    O->SetNumberField(TEXT("hits"), HitCount);
    O->SetNumberField(TEXT("parries"), ParryCount);
    O->SetNumberField(TEXT("staggers"), StaggerCount);
    O->SetNumberField(TEXT("guard_breaks"), GuardBreakCount);
    O->SetBoolField(TEXT("guard_broken"), GuardBroken > 0.f);
    O->SetBoolField(TEXT("flinching"), FlinchTime >= 0.f);
    O->SetNumberField(TEXT("dodges"), DodgeCount);
    O->SetNumberField(TEXT("double_jumps"), DoubleJumpCount);
    O->SetBoolField(TEXT("air_jump_used"), bAirJumpUsed);
    O->SetNumberField(TEXT("flip"), FlipAngle);
    O->SetBoolField(TEXT("shield"), HasShield());
    O->SetBoolField(TEXT("legacy"), false);
    O->SetBoolField(TEXT("sword_guard"), IsSwordGuarding());
    O->SetNumberField(TEXT("sword_guard_carry"), SwordGuardCarry);
    O->SetNumberField(TEXT("sword_carry"), SwordCarry);
    O->SetNumberField(TEXT("sword_hold"), SwordHold);
    {
        TArray<TSharedPtr<FJsonValue>> Pose;
        for (int32 I = 0; I < 2; ++I) Pose.Add(MakeShared<FJsonValueNumber>(GripPose(I).Weight));
        O->SetArrayField(TEXT("grip_pose"), Pose);
    }
    O->SetNumberField(TEXT("guard_carry"), GuardCarry);
    O->SetNumberField(TEXT("speed"), Movement->Velocity.Size2D());
    O->SetNumberField(TEXT("vz"), Movement->Velocity.Z);
    O->SetNumberField(TEXT("glide_speed"), GlideSpeed);
    O->SetNumberField(TEXT("glide_yaw"), GlideYaw);
    O->SetNumberField(TEXT("glide_bank"), GlideBank);
    O->SetNumberField(TEXT("glide_hands"), GlideHands);
    if (USkeletalMeshComponent* Body = Character->GetMesh(); Body && GlideHands > 0.f)
    {
        // How far each wrist is from its target on the glider (cm), after the IK.
        TArray<TSharedPtr<FJsonValue>> Miss;
        for (int32 I = 0; I < 2; ++I)
        {
            const FName Hand = Character->GetSkateBone(I ? TEXT("hand_L") : TEXT("hand_R"));
            Miss.Add(MakeShared<FJsonValueNumber>(FVector::Dist(Body->GetSocketTransform(Hand, RTS_Component).GetLocation(), GlideHandTarget[I])));
        }
        O->SetArrayField(TEXT("glide_hand_miss"), Miss);
    }
    O->SetNumberField(TEXT("feet"), Feet());
    O->SetNumberField(TEXT("fall_height"), FMath::Max(0.f, FallStartZ - float(Here.Z)));
    O->SetNumberField(TEXT("water"), WaterSurface);
    auto Vector = [](const FVector& V)
    {
        TArray<TSharedPtr<FJsonValue>> Out;
        for (int32 I = 0; I < 3; ++I) Out.Add(MakeShared<FJsonValueNumber>(V[I]));
        return Out;
    };
    O->SetArrayField(TEXT("location"), Vector(Here));
    O->SetArrayField(TEXT("wall"), Vector(WallNormal));
    O->SetNumberField(TEXT("yaw"), Character->GetActorRotation().Yaw);
    FString Out;
    const TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
    FJsonSerializer::Serialize(O, Writer);
    return Out;
}
