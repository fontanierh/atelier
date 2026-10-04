#include "BotwMoveSet.h"
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

// Every timing below is in clip seconds (the action timelines' frames at 30 fps), every distance in game centimetres at
// the character's scale, and BOTW's lengths (metres) and speeds (metres per 30 fps frame) are converted with that scale.

namespace
{
    bool In(FName Name, std::initializer_list<const TCHAR*> Names)
    {
        for (const TCHAR* N : Names) if (Name == FName(N)) return true;
        return false;
    }
    bool Prefixed(FName Name, std::initializer_list<const TCHAR*> Prefixes)
    {
        if (Name.IsNone()) return false;
        const FString S = Name.ToString();
        for (const TCHAR* P : Prefixes) if (S.StartsWith(P, ESearchCase::CaseSensitive)) return true;
        return false;
    }
    /** Blade work: the clip itself moves the arms, so the carry layers stay off. */
    bool IsSwordAction(FName N)
    {
        return Prefixed(N, { TEXT("Cut"), TEXT("Charge"), TEXT("Rush"), TEXT("Plunge"), TEXT("JumpCut"), TEXT("Guard"), TEXT("Parry"),
            TEXT("DashCut"), TEXT("Sneakstrike"), TEXT("Flurry"), TEXT("DrawSword"), TEXT("SheatheSword"), TEXT("SwordParry"),
            TEXT("SwordGuard") });
    }
    bool IsAttack(FName N)
    {
        return Prefixed(N, { TEXT("Cut"), TEXT("Rush"), TEXT("Plunge"), TEXT("JumpCut"), TEXT("DashCut"), TEXT("Sneakstrike"), TEXT("Flurry") }) ||
            N == FName(TEXT("ChargeSpin"));
    }
    /** A record's {location, rotation (x, y, z, w), scale} into Out; Out is left alone when Key is absent. */
    void ReadTransform(const TSharedPtr<FJsonObject>& O, const TCHAR* Key, FTransform& Out)
    {
        const TSharedPtr<FJsonObject>* T = nullptr;
        if (!O->TryGetObjectField(Key, T)) return;
        const TArray<TSharedPtr<FJsonValue>>* L = nullptr; const TArray<TSharedPtr<FJsonValue>>* R = nullptr;
        if ((*T)->TryGetArrayField(TEXT("location"), L) && L->Num() == 3)
            Out.SetLocation(FVector((*L)[0]->AsNumber(), (*L)[1]->AsNumber(), (*L)[2]->AsNumber()));
        if ((*T)->TryGetArrayField(TEXT("rotation"), R) && R->Num() == 4)
            Out.SetRotation(FQuat((*R)[0]->AsNumber(), (*R)[1]->AsNumber(), (*R)[2]->AsNumber(), (*R)[3]->AsNumber()).GetNormalized());
        double Scale = 1.;
        if ((*T)->TryGetNumberField(TEXT("scale"), Scale)) Out.SetScale3D(FVector(Scale));
    }
    /** The rest of a blocked move, along the surface it hit (the movement component keeps its own slide protected). */
    void Slide(UCharacterMovementComponent* Movement, const FVector& Delta, const FQuat& Rotation, FHitResult& Hit)
    {
        const FVector Along = FVector::VectorPlaneProject(Delta * (1.f - Hit.Time), Hit.Normal);
        if (!Along.IsNearlyZero()) Movement->SafeMoveUpdatedComponent(Along, Rotation, true, Hit);
    }
    bool IsHop(FName N) { return In(N, { TEXT("HopL"), TEXT("HopR"), TEXT("BackFlip") }); }
    bool IsDoubleJump(FName N) { return In(N, { TEXT("DoubleJump"), TEXT("DoubleJumpTuck") }); }
    bool IsParry(FName N) { return In(N, { TEXT("Parry"), TEXT("SwordParry") }); }
    bool IsGuardHit(FName N) { return In(N, { TEXT("GuardHit"), TEXT("SwordGuardHit") }); }
    bool IsLockLoop(FName N) { return Prefixed(N, { TEXT("Lock") }); }
    bool IsClimbMove(FName N) { return In(N, { TEXT("ClimbU"), TEXT("ClimbD"), TEXT("ClimbL"), TEXT("ClimbR"), TEXT("ClimbUL"), TEXT("ClimbUR"), TEXT("ClimbDL"), TEXT("ClimbDR") }); }
    /** Actions the stick does not steer until their cancel point (or their idle point, or their end). */
    bool IsLocking(FName N)
    {
        return IsAttack(N) || IsHop(N) || Prefixed(N, { TEXT("HopLand"), TEXT("BackFlipLand"), TEXT("HardLand"), TEXT("Charge"), TEXT("Hit"),
            TEXT("Knock"), TEXT("Guard"), TEXT("Parry"), TEXT("SwordParry"), TEXT("SwordGuard"), TEXT("Swim"), TEXT("Climb"), TEXT("Glide") });
    }
    float Smooth(float U) { U = FMath::Clamp(U, 0.f, 1.f); return U * U * (3.f - 2.f * U); }
    const TCHAR* const CutNames[] = { TEXT("CutS1"), TEXT("CutS2"), TEXT("CutS3"), TEXT("CutSF") };
    const TCHAR* const RushNames[] = { TEXT("Flurry"), TEXT("Rush1"), TEXT("Rush2"), TEXT("Rush3"), TEXT("Rush4"), TEXT("Rush5"), TEXT("RushFinish") };
    constexpr int32 RushCount = UE_ARRAY_COUNT(RushNames);
}

FVector4f FBotwMove::PathAt(float SourceTime) const
{
    if (Path.Num() == 0) return FVector4f(0.f, 0.f, 0.f, 0.f);
    if (Path.Num() == 1) return Path[0];
    const float Frame = FMath::Clamp(SourceTime * 30.f, 0.f, float(Path.Num() - 1));
    const int32 I = FMath::Min(int32(Frame), Path.Num() - 2);
    return Path[I] + (Path[I + 1] - Path[I]) * (Frame - I);
}

bool FBotwMove::InWindow(const TArray<FVector2f>& Windows, float SourceTime) const
{
    for (const FVector2f& W : Windows) if (SourceTime >= W.X && SourceTime <= W.Y) return true;
    return false;
}

/** A looping clip's path continues cycle after cycle (SourceTime is unwrapped: it keeps growing while the clip loops). */
static FVector4f Travelled(const FBotwMove& M, float SourceTime)
{
    if (!M.bLoop || M.Length <= 0.f) return M.PathAt(SourceTime);
    const float Cycles = FMath::FloorToFloat(SourceTime / M.Length);
    return M.PathAt(M.Length) * Cycles + M.PathAt(SourceTime - Cycles * M.Length);
}

// ------------------------------------------------------------------------------------------------------------- Setup

bool UBotwMoveSet::Initialize(AWandererCharacter* Owner, const TSharedPtr<FJsonObject>& Record)
{
    Character = Owner;
    const UWandererDefinition* Definition = Owner ? Owner->GetDefinition() : nullptr;
    const TSharedPtr<FJsonObject>* Actions = nullptr;
    if (!Definition || !Record.IsValid() || !Record->TryGetObjectField(TEXT("actions"), Actions)) return false;
    for (const auto& Pair : (*Actions)->Values)
    {
        const TSharedPtr<FJsonObject> O = Pair.Value->AsObject();
        FBotwMove M; M.Name = FName(*Pair.Key);
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
    // The double jump is Cairo's own somersault where the definition has it (DA_CairoBotw): played whole, at its own rate.
    if (const UAnimSequence* Flip = Definition->FindAction(TEXT("DoubleJump")); Flip && !Moves.Contains(TEXT("DoubleJump")))
    {
        FBotwMove M; M.Name = TEXT("DoubleJump");
        M.Length = M.End = Flip->GetPlayLength(); M.Blend = .05f;
        Moves.Add(M.Name, MoveTemp(M));
    }
    for (const TCHAR* Needed : { TEXT("Fall"), TEXT("Land"), TEXT("GlideOn"), TEXT("Glide"), TEXT("ClimbWait"), TEXT("SwimWait"), TEXT("Swim") })
        if (!Has(Needed))
        {
            UE_LOG(LogTemp, Warning, TEXT("BOTW move set: %s lacks %s (build unreal.botw); playing without it"), *Owner->GetName(), Needed);
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
                FTransform Held; ReadTransform(O, TEXT("held"), Held);
                Glider->SetRelativeTransform(Held);
                GliderHeld = Held;
                Glider->SetVisibility(false, true);
                continue;
            }
            UStaticMesh* Asset = LoadObject<UStaticMesh>(nullptr, *MeshPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
            if (!Asset || Back.IsEmpty()) continue;
            FSlot S; S.Hand = Hand.IsEmpty() ? NAME_None : FName(*Hand); S.Back = FName(*Back);
            ReadTransform(O, TEXT("held"), S.Held);
            ReadTransform(O, TEXT("carry"), S.Carry);
            UStaticMeshComponent* Prop = NewObject<UStaticMeshComponent>(Owner, *(FString(TEXT("Botw")) + *Pair.Key));
            Prop->SetStaticMesh(Asset);
            Prop->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            Prop->SetCastShadow(true);
            Prop->SetRenderCustomDepth(true); Prop->SetCustomDepthStencilValue(1);
            Prop->RegisterComponent();
            Props.Add(Slot, Prop);
            Slots.Add(Slot, S);
            Attach(Slot);
        }
    // The blade runs along the sword mesh's longest axis, from its origin (the grip) to the far end of its bounds.
    if (const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword")))
    {
        const FBox Box = (*Sword)->GetStaticMesh()->GetBoundingBox();
        const FVector Size = Box.GetSize();
        const int32 Axis = Size.X >= Size.Y && Size.X >= Size.Z ? 0 : Size.Y >= Size.Z ? 1 : 2;
        const double Far = FMath::Abs(Box.Max[Axis]) >= FMath::Abs(Box.Min[Axis]) ? Box.Max[Axis] : Box.Min[Axis];
        FVector Tip = FVector::ZeroVector; Tip[Axis] = Far;
        BladeBase = Tip * .18; BladeTip = Tip;
    }
    // Whatever is too steep to climb can be walked up: the walkable slope meets the climbing angle.
    Owner->GetCharacterMovement()->SetWalkableFloorAngle(GetParam(TEXT("ClimbEnableAngle"), 50.f));
    // BOTW's stamina: sprinting spends EnergyDash a second, it refills at EnergyAutoRecover a second after a short wait.
    FSprintStamina& Stamina = Owner->Stamina;
    Stamina.SprintSeconds = 1000.f / FMath::Max(GetParam(TEXT("PlayerMove.EnergyDash"), 300.f), 1.f);
    Stamina.RefillSeconds = 1000.f / FMath::Max(GetParam(TEXT("EnergyAutoRecover"), 300.f), 1.f);
    Stamina.Delay = GetParam(TEXT("EnergyAutoRecoverInvalidTime1"), 10.f) / 30.f;
    MeshBase = Body ? Body->GetRelativeLocation() : FVector::ZeroVector;
    MeshBaseRotation = Body ? Body->GetRelativeRotation().Quaternion() : FQuat::Identity;
    // The blade's ribbon through every cut (world space, so it stays where the blade passed).
    if (Props.Contains(TEXT("sword")))
    {
        BladeTrail = NewObject<UAtelierTrail>(Owner, TEXT("BotwBladeTrail"));
        BladeTrail->RegisterComponent();
    }
    // The shield is the "Shield" setting's (off by default); -shield / -noshield decide for a scripted session.
    const TCHAR* Line = FCommandLine::Get();
    SetShield(FParse::Param(Line, TEXT("shield")) || (!FParse::Param(Line, TEXT("noshield")) && UJapanPreferences::Saved(TEXT("shield"), 0.f) > .5f));
    SetLegacy(Chosen() == LegacyBotw);
    Mode = EBotwMoveMode::Ground;
    UE_LOG(LogTemp, Display, TEXT("BOTW move set: %d actions, %d parameters, %d props%s, scale %.2f, %s, double jump %s"), Moves.Num(), Params.Num(), Props.Num(),
        Glider ? TEXT(" and the paraglider") : TEXT(""), Scale(), bLegacy ? TEXT("legacy BOTW") : bShield ? TEXT("shield") : TEXT("no shield"),
        Has(TEXT("DoubleJump")) ? TEXT("somersault clip") : Has(TEXT("DoubleJumpTuck")) ? TEXT("tucked") : TEXT("none"));
    return true;
}

float UBotwMoveSet::GetParam(const TCHAR* Key, float Default) const { const float* V = Params.Find(Key); return V ? *V : Default; }

FString UBotwMoveSet::ModeName() const
{
    switch (Mode)
    {
    case EBotwMoveMode::Air: return TEXT("air");
    case EBotwMoveMode::Glide: return TEXT("glide");
    case EBotwMoveMode::Climb: return TEXT("climb");
    case EBotwMoveMode::Swim: return TEXT("swim");
    default: return TEXT("ground");
    }
}

// ----------------------------------------------------------------------------------------------------------- Actions

const FBotwMove* UBotwMoveSet::Current() const { return Character ? Moves.Find(Character->GetAnimationAction()) : nullptr; }
FName UBotwMoveSet::CurrentName() const { return Character ? Character->GetAnimationAction() : NAME_None; }
float UBotwMoveSet::SourceTime() const { return Character ? Character->GetActionSourceTime() : 0.f; }
bool UBotwMoveSet::Playing(FName Name) const { return Character && Character->GetAnimationAction() == Name; }
bool UBotwMoveSet::Over() const
{
    const FBotwMove* M = Current();
    return M && !Character->DoesActionLoop() && SourceTime() >= M->End - .001f;
}
float UBotwMoveSet::FreeAt(const FBotwMove& M) { return M.Cancel >= 0.f ? M.Cancel : M.Idle >= 0.f ? M.Idle : M.End; }
bool UBotwMoveSet::Busy() const
{
    const FBotwMove* M = Current();
    // A locking loop (the charge, a plunge's fall) holds until something ends it.
    return M && IsLocking(M->Name) && (Character->DoesActionLoop() || SourceTime() < FreeAt(*M));
}

void UBotwMoveSet::Play(FName Name, float Blend, float StartAt, float Speed)
{
    const FBotwMove* M = Moves.Find(Name);
    if (!M || !Character) return;
    const bool bLoop = M->bLoop || In(Name, { TEXT("Fall"), TEXT("PlungeAir"), TEXT("JumpCutAir") });
    Character->SetAction(Name, bLoop, Blend >= 0.f ? Blend : FMath::Clamp(M->Blend, .06f, .25f), true);
    if (Character->GetAnimationAction() != Name) return;
    Character->ActionSourceStartTime = StartAt >= 0.f ? StartAt : M->Start;
    Character->ActionPlayRate = M->Rate * Speed;
    Character->ActionDuration = FMath::Max(M->End - Character->ActionSourceStartTime, 0.f) / Character->ActionPlayRate;
    bDriving = false; DriveVelocity = FVector::ZeroVector; DriveMesh = FVector::ZeroVector;
    HitThisSwing.Reset(); PreviousBlade.Reset(); bSwung = false;
    Strength = StrengthOf(Name);
    LastPlayed = Name;
}

void UBotwMoveSet::PlayLoop(FName Name, float Blend)
{
    if (Playing(Name)) return;
    const FBotwMove* From = Current();
    const FBotwMove* To = Moves.Find(Name);
    if (!To) return;
    float StartAt = -1.f;
    if (From && From->bLoop && From->Length > 0.f && To->Length > 0.f)
        StartAt = FMath::Fmod(FMath::Max(SourceTime(), 0.f), From->Length) / From->Length * To->Length;
    Play(Name, Blend, StartAt);
}

void UBotwMoveSet::Stop(float Blend)
{
    if (Character) Character->SetAction(NAME_None, false, Blend);
    bDriving = false; DriveVelocity = FVector::ZeroVector; DriveMesh = FVector::ZeroVector;
}

int32 UBotwMoveSet::StrengthOf(FName Name) const
{
    if (Name == TEXT("Sneakstrike")) return 8;
    if (In(Name, { TEXT("PlungeLand"), TEXT("PlungeAir"), TEXT("Plunge") })) return 3;
    if (Name == TEXT("ChargeSpin")) return bFullCharge ? 3 : 2;
    if (In(Name, { TEXT("CutSF"), TEXT("DashCut"), TEXT("JumpCutAir"), TEXT("JumpCutLand"), TEXT("RushFinish") })) return 2;
    return 1;
}

void UBotwMoveSet::BeginDrive(bool bSweep, const FVector& Fit, const FVector& MeshFrom)
{
    const FBotwMove* M = Current();
    if (!M || M->Path.IsEmpty() || !Character) return;
    bDriving = true; bDriveSweep = bSweep; DriveScale = Fit; DriveMesh = MeshFrom; MeshDriveLocal = FVector::ZeroVector;
    DriveOrigin = Character->GetActorLocation(); DrivePrevious = SourceTime();
    DriveYaw = Character->GetActorRotation().Yaw;
    if (Mode == EBotwMoveMode::Climb && bSweep) ClimbBasis(DriveForward, DriveRight, DriveUp);
    else
    {
        DriveForward = FRotator(0, DriveYaw, 0).Vector(); DriveUp = FVector::UpVector;
        DriveRight = FVector::CrossProduct(DriveUp, DriveForward);
    }
}

FVector UBotwMoveSet::WorldPath(const FVector4f& P) const
{
    return DriveForward * (P.X * DriveScale.X) + DriveRight * (P.Y * DriveScale.Y) + DriveUp * (P.Z * DriveScale.Z);
}

float UBotwMoveSet::DriveProgress() const
{
    const FBotwMove* M = Current();
    if (!M || M->End <= M->Start) return 1.f;
    return FMath::Clamp((SourceTime() - M->Start) / (M->End - M->Start), 0.f, 1.f);
}

/** Moves the capsule along the playing clip's root path. On foot the path becomes the velocity (the movement component
 *  still walks it over the ground); in the move set's own movement mode it moves the capsule, swept along a wall, or
 *  placed outright for a ledge climb whose path was fitted to the ledge. */
void UBotwMoveSet::AdvanceDrive(float Dt)
{
    const FBotwMove* M = Current();
    if (!bDriving || !M || M->Path.IsEmpty()) { bDriving = false; DriveVelocity = FVector::ZeroVector; return; }
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const float T = SourceTime();
    if (Mode == EBotwMoveMode::Climb && bDriveSweep) ClimbBasis(DriveForward, DriveRight, DriveUp);
    const FVector4f Now = Travelled(*M, T);
    const FVector Delta = WorldPath(Now) - WorldPath(Travelled(*M, DrivePrevious));
    DrivePrevious = T;
    const FRotator Facing(0, Mode == EBotwMoveMode::Climb ? Character->GetActorRotation().Yaw : DriveYaw + Now.W, 0);
    if (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air)
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

void UBotwMoveSet::Advance(float Dt)
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    Clock += Dt;
    Character->ActionTime += Dt;
    AttackBuffer = FMath::Max(0.f, AttackBuffer - Dt); JumpBuffer = FMath::Max(0.f, JumpBuffer - Dt);
    NoClimb = FMath::Max(0.f, NoClimb - Dt); SinceImpact += Dt; Invulnerable = FMath::Max(0.f, Invulnerable - Dt); JustAvoid = FMath::Max(0.f, JustAvoid - Dt);
    AdvanceFlurry();
    // Leaving the move set's movement mode from outside (travel, the board) ends gliding, climbing and swimming.
    const bool bCustom = Movement->MovementMode == MOVE_Custom && Movement->CustomMovementMode == MovementMode;
    if (Mode == EBotwMoveMode::Glide || Mode == EBotwMoveMode::Climb || Mode == EBotwMoveMode::Swim)
    {
        if (!bCustom) { Mode = Movement->IsMovingOnGround() ? EBotwMoveMode::Ground : EBotwMoveMode::Air; ClimbShiftTarget = 0.f; bDriving = false; }
    }
    if (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air)
    {
        if (Movement->IsMovingOnGround()) { Mode = EBotwMoveMode::Ground; SinceGrounded = 0.f; }
        else if (Movement->IsFalling())
        {
            if (Mode == EBotwMoveMode::Ground) { FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f; }
            Mode = EBotwMoveMode::Air; SinceGrounded += Dt;
        }
    }
    if (bDown) AdvanceDown(Dt);
    else switch (Mode)
    {
    case EBotwMoveMode::Ground: AdvanceGround(Dt); break;
    case EBotwMoveMode::Air: AdvanceAir(Dt); break;
    case EBotwMoveMode::Glide: AdvanceGlide(Dt); break;
    case EBotwMoveMode::Climb: AdvanceClimb(Dt); break;
    case EBotwMoveMode::Swim: AdvanceSwim(Dt); break;
    }
    if (bDriving && (Mode == EBotwMoveMode::Ground || Mode == EBotwMoveMode::Air)) AdvanceDrive(Dt);
    // Standing, climbing or swimming gives the double jump back.
    if (Mode != EBotwMoveMode::Air && Mode != EBotwMoveMode::Glide) bAirJumpUsed = false;
    AdvanceDoubleJump(Dt);
    AdvanceCombat(Dt);
    AdvanceEquipment(Dt);
    AdvanceGliderGrip(Dt);
    AdvanceMeshOffset(Dt);
    AdvanceEffects(Dt);
}

void UBotwMoveSet::Phys(float Dt, int32 Iterations)
{
    if (!Character || Dt <= 0.f) return;
    switch (Mode)
    {
    case EBotwMoveMode::Glide: PhysGlide(Dt); break;
    case EBotwMoveMode::Climb: PhysClimb(Dt); break;
    case EBotwMoveMode::Swim: if (bDriving) AdvanceDrive(Dt); else PhysSwim(Dt); break;
    default: Character->GetCharacterMovement()->SetMovementMode(MOVE_Falling); break;
    }
}

bool UBotwMoveSet::OverrideVelocity(FVector& Velocity) const
{
    if (!Character || (Mode != EBotwMoveMode::Ground && Mode != EBotwMoveMode::Air)) return false;
    const FName Name = CurrentName();
    if (bDriving) { Velocity.X = DriveVelocity.X; Velocity.Y = DriveVelocity.Y; return true; }
    if (LungeTime > 0.f && Mode == EBotwMoveMode::Ground)
    {
        // Toward where the blade reaches the target, stopping there (re-aimed every step as either moves).
        FVector V = FVector::ZeroVector;
        if (const AActor* Focus = LungeTarget.Get())
        {
            const FVector To = (Focus->GetActorLocation() - Character->GetActorLocation()) * FVector(1, 1, 0);
            const float Gap = float(To.Size()) - LungeStand;
            if (Gap > 2.f) V = To.GetSafeNormal() * FMath::Min(Gap / FMath::Max(LungeTime, .03f), 1100.f);
        }
        Velocity.X = V.X; Velocity.Y = V.Y; return true;
    }
    if (Mode == EBotwMoveMode::Air && (IsHop(Name) || In(Name, { TEXT("JumpCut"), TEXT("JumpCutAir") }))) { Velocity.X = HopVelocity.X; Velocity.Y = HopVelocity.Y; return true; }
    if (Mode == EBotwMoveMode::Air && In(Name, { TEXT("Plunge"), TEXT("PlungeAir") })) { Velocity.X = Velocity.Y = 0.; return true; }
    // The flurry rush closes in on its target.
    if (InFlurry() && Target.IsValid() && Prefixed(Name, { TEXT("Flurry"), TEXT("Rush") }))
    {
        const FVector To = (Target->GetActorLocation() - Character->GetActorLocation()) * FVector(1, 1, 0);
        const FVector V = To.Size() > Reach() ? To.GetSafeNormal() * 900.f : FVector::ZeroVector;
        Velocity.X = V.X; Velocity.Y = V.Y; return true;
    }
    return false;
}

bool UBotwMoveSet::ControlsRotation() const
{
    if (Mode == EBotwMoveMode::Glide || Mode == EBotwMoveMode::Climb || Mode == EBotwMoveMode::Swim) return true;
    if (FlipTime >= 0.f) return true;   // the somersault keeps the heading it set off on
    if (bLocked || bDriving || bDown) return true;
    return IsLocking(CurrentName());
}

bool UBotwMoveSet::LocksMovement() const
{
    if (Mode == EBotwMoveMode::Glide || Mode == EBotwMoveMode::Climb || Mode == EBotwMoveMode::Swim || bDown) return true;
    return Busy();
}

float UBotwMoveSet::GetMaxWalkSpeed(float Default) const
{
    if (Mode != EBotwMoveMode::Ground || !bLocked) return Default;
    const bool bWalk = Character && (Character->bWalk || Character->bJog);
    const FBotwMove* M = Moves.Find(bWalk ? TEXT("LockWalkF") : TEXT("LockRunF"));
    return M && M->Speed > 1.f ? M->Speed : bWalk ? 130.f : 300.f;
}

// ------------------------------------------------------------------------------------------------------- On foot

void UBotwMoveSet::AdvanceGround(float Dt)
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
        if (bLocked) { Target = FindTarget(1500.f, 70.f); LockYaw = Character->GetActorRotation().Yaw; }
        else Target = nullptr;
    }
    const FBotwMove* Now = Current();
    FName Name = Now ? Now->Name : NAME_None;
    if (bLocked)
    {
        AActor* Focus = Target.Get();
        if (Focus && (FVector::Dist2D(Focus->GetActorLocation(), Here) > 2500.f || !IsTargetable(Focus))) { Target = nullptr; Focus = nullptr; }
        const float FaceYaw = Focus ? (Focus->GetActorLocation() - Here).Rotation().Yaw : LockYaw;
        if (!Busy() || IsLockLoop(Name))
            Character->SetActorRotation(FRotator(0, FMath::FixedTurn(Character->GetActorRotation().Yaw, FaceYaw, 720.f * Dt), 0));
        if (Character->Controller && Character->LookGrace <= 0.f)
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
    if (Mode != EBotwMoveMode::Ground) return;

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

void UBotwMoveSet::AdvanceAir(float Dt)
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const FVector Here = Character->GetActorLocation();
    FallStartZ = FMath::Max(FallStartZ, Here.Z);
    FallSpeed = Movement->Velocity.Z > 0.f ? 0.f : FMath::Max(FallSpeed, float(-Movement->Velocity.Z));
    float Surface = 0.f;
    if (WaterAt(Here, Surface) && Feet() < Surface - 10.f) { StartSwim(); return; }
    bLocked = false;
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (In(Name, { TEXT("Jump"), TEXT("RunJumpL"), TEXT("RunJumpR") })) { if (Over()) Play(TEXT("Fall"), .2f); }
    else if (Name == TEXT("JumpCut")) { if (Over() && Has(TEXT("JumpCutAir"))) Play(TEXT("JumpCutAir"), .05f); }
    else if (Name == TEXT("Plunge")) { if (Over() && Has(TEXT("PlungeAir"))) Play(TEXT("PlungeAir"), .05f); }
    else if (IsDoubleJump(Name)) { if (FlipTime < 0.f && (Name == TEXT("DoubleJumpTuck") || Over())) Play(TEXT("Fall"), .2f); }   // AdvanceDoubleJump times it
    else if (IsHop(Name) || In(Name, { TEXT("Fall"), TEXT("JumpCutAir"), TEXT("PlungeAir"), TEXT("ClimbOff") }) || Prefixed(Name, { TEXT("Hit"), TEXT("Knock") })) {}
    else if (SinceGrounded > .15f || bJumped) Play(TEXT("Fall"), .2f);   // walked off an edge, or whatever played on the ground
    // A hop, jump cut or plunge held up on a bank too steep to stand on (its steering pushes into it): let go and slide off.
    if (Mode == EBotwMoveMode::Air && Movement->Velocity.Z > -10.f && SinceGrounded > .2f &&
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

void UBotwMoveSet::Impact(const FHitResult& Hit)
{
    if (Mode == EBotwMoveMode::Ground && Hit.IsValidBlockingHit()) { LastImpact = Hit; SinceImpact = 0.f; }
}

void UBotwMoveSet::Landed(const FHitResult& Hit)
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    const float Height = FMath::Max(0.f, FallStartZ - float(Character->GetActorLocation().Z));
    if (UJapanFootstepComponent* Steps = Character->GetFootsteps())
        Steps->Land(Hit, FMath::GetMappedRangeValueClamped(FVector2f(200.f, 1100.f), FVector2f(.55f, 1.4f), FallSpeed));
    if (FlipTime >= 0.f) FlipSettle = .2f;
    bJumped = false; bAirJumpUsed = false; FlipTime = -1.f; HopVelocity = FVector::ZeroVector; SinceGrounded = 0.f; FallSpeed = 0.f; FallStartZ = Character->GetActorLocation().Z;
    if (Mode != EBotwMoveMode::Ground && Mode != EBotwMoveMode::Air) return;
    Mode = EBotwMoveMode::Ground;
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

bool UBotwMoveSet::CanJump() const
{
    return Character && (Mode == EBotwMoveMode::Ground || (Mode == EBotwMoveMode::Air && !bJumped && SinceGrounded < .12f)) && !Busy() && !bDown;
}

void UBotwMoveSet::StartJump()
{
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (Character->bIsCrouched) Character->UnCrouch();
    // A sprinting jump costs stamina (EnergyDashJump).
    if (Character->Stamina.Sprinting) UseStamina(GetParam(TEXT("PlayerJump.EnergyDashJump"), 300.f) / 1000.f);
    const float Speed = Movement->Velocity.Size2D();
    Character->LaunchCharacter(FVector(0, 0, Movement->JumpZVelocity), false, true);
    bJumped = true; JumpBuffer = 0.f; FallSpeed = 0.f; FallStartZ = Character->GetActorLocation().Z;
    Mode = EBotwMoveMode::Air;
    if (Speed > 250.f && Has(TEXT("RunJumpL"))) { Play(bRunFoot ? TEXT("RunJumpL") : TEXT("RunJumpR"), .08f); bRunFoot = !bRunFoot; }
    else Play(TEXT("Jump"), .08f);
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
        FX->Dust(Character->GetActorLocation() - FVector(0, 0, HalfHeight()), Speed > 250.f ? .55f : .35f, -FVector(Movement->Velocity.GetSafeNormal2D()) * .3f);
}

// ------------------------------------------------------------------------------------------------------- Double jump

bool UBotwMoveSet::CanDoubleJump() const
{
    if (!Character || bLegacy || Mode != EBotwMoveMode::Air || bAirJumpUsed || bDown || CanJump()) return false;
    if (!Has(TEXT("DoubleJump")) && !Has(TEXT("DoubleJumpTuck"))) return false;
    // As Cairo's: after a jump at once, after walking off an edge a moment later.
    if (!bJumped && SinceGrounded < .10f) return false;
    const FName Name = CurrentName();
    return !IsAttack(Name) && !IsHop(Name) && !Prefixed(Name, { TEXT("Hit"), TEXT("Knock"), TEXT("Climb") });
}

/** Cairo's double jump: a fresh 650 cm/s upward launch, the ground speed turned once toward the stick (all of it, even
 *  backward; the stick at rest keeps the heading), and one forward somersault: his own clip, or a tuck the game turns. */
void UBotwMoveSet::StartDoubleJump()
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
void UBotwMoveSet::AdvanceDoubleJump(float Dt)
{
    if (FlipTime < 0.f) return;
    const FName Name = CurrentName();
    if (!IsDoubleJump(Name) || Mode != EBotwMoveMode::Air) { FlipTime = -1.f; return; }   // a glider, a wall, the ground
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

bool UBotwMoveSet::CanDodge() const { return Mode == EBotwMoveMode::Ground && !Busy() && !bDown && Has(TEXT("BackFlip")); }

/** The side hop (stick to the side) or the backflip (anything else), launched with BOTW's speeds and heights. Both are
 *  invulnerable while airborne; a strike that arrives in their first moments is a perfect dodge (the flurry rush). */
void UBotwMoveSet::StartHop()
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
    Mode = EBotwMoveMode::Air; bJumped = true; JumpBuffer = 0.f; FallStartZ = Character->GetActorLocation().Z;
    const float Flight = 2.f * float(V.Z) / FMath::Max(G, 1.f);
    Invulnerable = FMath::Min(GetParam(TEXT("PlayerSideStep.NoDamageTime"), 40.f) / 30.f, Flight + .1f);
    JustAvoid = .25f;
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
    if (FMath::Abs(GlideTurn) > 40.f) Clip = GlideTurn > 0.f ? TEXT("GlideR") : TEXT("GlideL");
    else if (bGlideBrake) Clip = TEXT("GlideB");
    else if (Wish().Size2D() > .3f) Clip = TEXT("GlideF");
    PlayLoop(Has(Clip) ? Clip : FName(TEXT("Glide")), .3f);
}

/** The paraglider is held at one hand; turning, the glide clips move the hands apart and the other let go of the bar.
 *  Gliding, it is placed in the frame of both hands instead (between them, across from left to right, up the body), at
 *  the place it has in that frame in the neutral glide, so it banks with the hands and both stay on the bar. */
void UBotwMoveSet::AdvanceGliderGrip(float Dt)
{
    USkeletalMeshComponent* Body = Character->GetMesh();
    if (!Glider || !Body) return;
    const FVector Left = Body->GetSocketLocation(Character->GetSkateBone(TEXT("hand_L")));
    const FVector Right = Body->GetSocketLocation(Character->GetSkateBone(TEXT("hand_R")));
    FVector Across = Right - Left;
    if (Across.Size() < 5.f) return;
    Across.Normalize();
    const FTransform Hands(FRotationMatrix::MakeFromXZ(Across, Character->GetActorUpVector()).ToQuat(), (Left + Right) * .5f);
    const FName Name = CurrentName();
    const bool bSteady = Mode == EBotwMoveMode::Glide && bGliderShown && Prefixed(Name, { TEXT("Glide") }) && !In(Name, { TEXT("GlideOn"), TEXT("GlideOnFall"), TEXT("GlideOff") });
    if (bSteady && !bGliderGrip && In(Name, { TEXT("Glide"), TEXT("GlideF") }) && GlideTime > .5f && FMath::Abs(GlideTurn) < 8.f)
    {
        GliderGrip = Glider->GetComponentTransform().GetRelativeTransform(Hands);
        bGliderGrip = true;
    }
    const float Was = GliderGripWeight;
    GliderGripWeight = FMath::FInterpConstantTo(GliderGripWeight, bSteady && bGliderGrip ? 1.f : 0.f, Dt, 5.f);
    if (GliderGripWeight <= 0.f)
    {
        if (Was > 0.f) Glider->SetRelativeTransform(GliderHeld);
        return;
    }
    const FTransform Bone = Body->GetSocketTransform(Glider->GetAttachSocketName());
    FTransform Placed;
    Placed.Blend(GliderHeld, (GliderGrip * Hands).GetRelativeTransform(Bone), Smooth(GliderGripWeight));
    Glider->SetRelativeTransform(Placed);
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
    Movement->SetMovementMode(MOVE_Custom, MovementMode);
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
    Movement->SetMovementMode(MOVE_Custom, MovementMode);
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
        if (Over())
        {
            // Out of stamina in deep water: back to the last dry ground, a little hurt.
            if (UWandererSwordComponent* Sword = Character->GetSword()) Sword->Health = FMath::Max(1.f, Sword->Health - GetParam(TEXT("DrownDamage"), 10.f));
            const FVector Shore = bHasSafeShore ? SafeShore : Character->GetActorLocation();
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
}

float UBotwMoveSet::BladeLength() const
{
    const TObjectPtr<UStaticMeshComponent>* Sword = Props.Find(TEXT("sword"));
    return Sword && *Sword ? float((BladeTip * (*Sword)->GetComponentScale()).Size()) : 60.f;
}

void UBotwMoveSet::Strike(AActor* Victim, int32 Power, const FVector& At, const FVector& Direction)
{
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
            if (FX)
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
        const FName Hit = !HasShield() && Has(TEXT("SwordGuardHit")) ? FName(TEXT("SwordGuardHit")) : FName(TEXT("GuardHit"));
        if (Has(Hit)) Play(Hit, .03f);
        Character->GetCharacterMovement()->Velocity = -Toward * 220.f;
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

void UBotwMoveSet::TakeHit(float Damage, const FVector& From, bool bHeavy, AActor* Source, bool bReact)
{
    UWandererSwordComponent* Sword = Character->GetSword();
    if (!Sword) return;
    ++Sword->HitsTakenCount;
    Sword->Health = FMath::Max(0.f, Sword->Health - Damage);
    Invulnerable = FMath::Max(Invulnerable, .7f);
    const bool bKnock = bHeavy || Sword->Health <= 0.f;
    if (AYorimichiCombatFX* FX = AYorimichiCombatFX::Get(Character))
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
    const FVector Away = (Character->GetActorLocation() - From).GetSafeNormal2D();
    if (bKnock && Has(TEXT("KnockF")) && Has(TEXT("KnockB")))
    {
        bDown = true; DownTime = 0.f;
        Play(bFront ? TEXT("KnockF") : TEXT("KnockB"), .05f);
        Character->LaunchCharacter(Away * 380.f + FVector(0, 0, 280.f), true, true);
        return;
    }
    const TCHAR* Clip = FMath::Abs(Local.X) >= FMath::Abs(Local.Y) ? (bFront ? TEXT("HitF") : TEXT("HitB")) : (Local.Y > 0 ? TEXT("HitR") : TEXT("HitL"));
    if (Has(Clip)) Play(Clip, .05f);
    if (Movement->IsMovingOnGround()) Movement->Velocity = Away * 220.f;
}

void UBotwMoveSet::AdvanceDown(float Dt)
{
    DownTime += Dt;
    const FBotwMove* Now = Current();
    const FName Name = Now ? Now->Name : NAME_None;
    if (Name == TEXT("KnockF") || Name == TEXT("KnockB"))
    {
        // He lies where he fell (the clip holds its last frame), then gets up.
        if (DownTime > GetParam(TEXT("KnockDownTime"), 1.4f) && Character->GetCharacterMovement()->IsMovingOnGround())
            Play(Name == TEXT("KnockF") ? TEXT("KnockUpF") : TEXT("KnockUpB"), .15f);
        return;
    }
    if (Name == TEXT("KnockUpF") || Name == TEXT("KnockUpB"))
    {
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

// --------------------------------------------------------------------------------------------------------- Queries

float UBotwMoveSet::Scale() const
{
    // A retargeted body (Cairo's) states its own: its mesh is at full scale, the body smaller than BOTW's.
    if (const float* Body = Params.Find(TEXT("BodyScale"))) return *Body;
    return Character && Character->GetMesh() ? float(Character->GetMesh()->GetRelativeScale3D().X) : 1.f;
}
float UBotwMoveSet::Gravity() const { return Character ? -Character->GetCharacterMovement()->GetGravityZ() : 980.f; }
float UBotwMoveSet::HalfHeight() const { return Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight(); }
float UBotwMoveSet::Feet() const { return float(Character->GetActorLocation().Z) - HalfHeight(); }
float UBotwMoveSet::Reach() const { return Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + 110.f; }
void UBotwMoveSet::UseStamina(float Rings) { if (Character && Rings > 0.f) Character->Stamina.Use(Rings); }
bool UBotwMoveSet::HasStamina() const { return Character && !Character->Stamina.Exhausted && Character->Stamina.Units > 0.f; }

FVector UBotwMoveSet::Wish() const
{
    const FVector2D Intent = Character->GetMoveIntent();
    const FRotationMatrix Basis(FRotator(0, Character->GetControlRotation().Yaw, 0));
    return (Basis.GetUnitAxis(EAxis::X) * Intent.Y + Basis.GetUnitAxis(EAxis::Y) * Intent.X).GetClampedToMaxSize(1.f);
}

bool UBotwMoveSet::Trace(const FVector& From, const FVector& To, FHitResult& Hit) const
{
    UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(BotwMoves), false, Character);
    FCollisionResponseParams Response;
    Capsule->InitSweepCollisionParams(Query, Response);
    return Character->GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, Capsule->GetCollisionObjectType(), FCollisionShape::MakeSphere(4.f), Query, Response);
}

bool UBotwMoveSet::Blocked(const FVector& Center) const
{
    UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    FCollisionQueryParams Query(SCENE_QUERY_STAT(BotwRoom), false, Character);
    FCollisionResponseParams Response;
    Capsule->InitSweepCollisionParams(Query, Response);
    const FCollisionShape Shape = FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius() - 2.f, HalfHeight() - 2.f);
    return Character->GetWorld()->OverlapBlockingTestByChannel(Center, FQuat::Identity, Capsule->GetCollisionObjectType(), Shape, Query, Response);
}

bool UBotwMoveSet::FindWall(const FVector& Direction, FHitResult& Hit, float Up, float Side, float Distance) const
{
    const FVector Along = Direction.GetSafeNormal();
    const FVector Right = FVector::CrossProduct(FVector::UpVector, Along).GetSafeNormal();
    const FVector From = Character->GetActorLocation() + FVector(0, 0, Up) + Right * Side;
    const float Length = Distance > 0.f ? Distance : Character->GetCapsuleComponent()->GetScaledCapsuleRadius() + 30.f;
    return Trace(From, From + Along * Length, Hit);
}

bool UBotwMoveSet::Climbable(const FHitResult& Hit) const
{
    if (!Hit.bBlockingHit || Hit.bStartPenetrating) return false;
    const float Steep = FMath::Cos(FMath::DegreesToRadians(GetParam(TEXT("ClimbEnableAngle"), 50.f)));
    if (Hit.ImpactNormal.Z >= Steep || Hit.ImpactNormal.Z < -.35f) return false;
    // Not people, creatures or props, and not the skate parks' ramps and rails.
    const AActor* A = Hit.GetActor();
    return !(A && (A->IsA<APawn>() || A->IsA<ABotwCreature>() || A->IsA<ASwordDummy>() || A->IsA<AMegaRamp>() ||
        A->IsA<ASuperUltraMegaPark>() || A->ActorHasTag(TEXT("SkatePark"))));
}

bool UBotwMoveSet::IsTargetable(AActor* Actor) const
{
    if (!Actor || Actor == Character) return false;
    if (const ABotwCreature* Creature = Cast<ABotwCreature>(Actor)) return !Creature->IsDown();
    if (const AFoxHunter* Fox = Cast<AFoxHunter>(Actor)) return Fox->IsAlive();
    return Actor->IsA<ASwordDummy>();
}

bool UBotwMoveSet::IsUnawareTarget(AActor* Actor) const
{
    if (const ABotwCreature* Creature = Cast<ABotwCreature>(Actor)) return !Creature->IsAlerted();
    return Actor && Actor->IsA<ASwordDummy>();
}

AActor* UBotwMoveSet::FindTarget(float Range, float Cone) const
{
    if (!Character) return nullptr;
    const FVector Here = Character->GetActorLocation(), Forward = Character->GetActorForwardVector();
    AActor* Best = nullptr; float BestScore = TNumericLimits<float>::Max();
    for (TActorIterator<AActor> It(Character->GetWorld()); It; ++It)
    {
        if (!It->IsA<ABotwCreature>() && !It->IsA<AFoxHunter>() && !It->IsA<ASwordDummy>()) continue;
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

void UBotwMoveSet::Reset()
{
    if (!Character) return;
    UCharacterMovementComponent* Movement = Character->GetCharacterMovement();
    if (Movement->MovementMode == MOVE_Custom && Movement->CustomMovementMode == MovementMode) Movement->SetMovementMode(MOVE_Falling);
    Mode = Movement->IsMovingOnGround() ? EBotwMoveMode::Ground : EBotwMoveMode::Air;
    ShowGlider(false);
    SetArmed(false);
    bLocked = bGuardHeld = bAttackHeld = bJumpHeld = bCharging = bDown = bDriving = bJumped = false;
    Target = nullptr; HopVelocity = DriveVelocity = FVector::ZeroVector;
    JumpBuffer = AttackBuffer = NoClimb = Invulnerable = JustAvoid = SwimDashTime = 0.f;
    if (FlurryTime > 0.f) { FlurryTime = 0.f; Character->CustomTimeDilation = 1.f; }
    ClimbShift = ClimbShiftTarget = 0.f; MeshOffsetLength = 0.f; MeshDriveLocal = DriveMesh = FVector::ZeroVector;
    FlipTime = -1.f; FlipAngle = FlipLift = FlipSettle = 0.f; bAirJumpUsed = false;
    if ((bMeshOffset || bMeshTurned) && Character->GetMesh())
    {
        Character->GetMesh()->SetRelativeLocationAndRotation(MeshBase, MeshBaseRotation);
        bMeshOffset = bMeshTurned = false;
    }
    FallStartZ = Character->GetActorLocation().Z; FallSpeed = 0.f;
}

FString UBotwMoveSet::Describe() const
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
    O->SetNumberField(TEXT("dodges"), DodgeCount);
    O->SetNumberField(TEXT("double_jumps"), DoubleJumpCount);
    O->SetBoolField(TEXT("air_jump_used"), bAirJumpUsed);
    O->SetNumberField(TEXT("flip"), FlipAngle);
    O->SetBoolField(TEXT("shield"), HasShield());
    O->SetBoolField(TEXT("legacy"), bLegacy);
    O->SetBoolField(TEXT("sword_guard"), IsSwordGuarding());
    O->SetNumberField(TEXT("sword_guard_carry"), SwordGuardCarry);
    O->SetNumberField(TEXT("sword_carry"), SwordCarry);
    O->SetNumberField(TEXT("guard_carry"), GuardCarry);
    O->SetNumberField(TEXT("speed"), Movement->Velocity.Size2D());
    O->SetNumberField(TEXT("vz"), Movement->Velocity.Z);
    O->SetNumberField(TEXT("glide_speed"), GlideSpeed);
    O->SetNumberField(TEXT("glide_yaw"), GlideYaw);
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
