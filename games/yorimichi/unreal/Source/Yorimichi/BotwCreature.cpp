#include "BotwCreature.h"
#include "JapanNetwork.h"
#include "JapanCombat.h"
#include "JapanEncounters.h"
#include "Net/UnrealNetwork.h"
#include "GameFramework/GameStateBase.h"
#include "AtelierData.h"
#include "Animation/AnimSequence.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Engine/CollisionProfile.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/Pawn.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "BotwMoveSet.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

const TMap<FString, FBotwSpec>& FBotwSpec::All()
{
    static TMap<FString, FBotwSpec> Roster;
    static bool bLoaded = false;
    if (bLoaded) return Roster;
    bLoaded = true;
    const TSharedPtr<FJsonObject> Root = AtelierReadJson(AtelierDataPath(TEXT("botw/roster.json")));
    if (!Root) return Roster;
    for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("characters")))
    {
        const TSharedPtr<FJsonObject>& C = Value->AsObject();
        FBotwSpec S;
        S.Name = C->GetStringField(TEXT("name")); S.Label = C->GetStringField(TEXT("label"));
        S.Mesh = FSoftObjectPath(C->GetStringField(TEXT("mesh")));
        S.MeshYaw = C->GetNumberField(TEXT("mesh_yaw")); C->TryGetNumberField(TEXT("scale"), S.Scale);
        S.HeightCm = C->GetNumberField(TEXT("height_cm")); S.RadiusCm = C->GetNumberField(TEXT("radius_cm"));
        const TSharedPtr<FJsonObject>& Speeds = C->GetObjectField(TEXT("speeds_cm"));
        Speeds->TryGetNumberField(TEXT("walk"), S.WalkSpeed); Speeds->TryGetNumberField(TEXT("run"), S.RunSpeed);
        for (const auto& Clip : C->GetObjectField(TEXT("clips"))->Values)
        {
            const TSharedPtr<FJsonObject>& Entry = Clip.Value->AsObject();
            S.Clips.Add(FName(*Clip.Key), FSoftObjectPath(Entry->GetStringField(TEXT("path"))));
            S.Loops.Add(FName(*Clip.Key), Entry->GetBoolField(TEXT("loop")));
        }
        for (const auto& Role : C->GetObjectField(TEXT("roles"))->Values) S.Roles.Add(FName(*Role.Key), FName(*Role.Value->AsString()));
        const TSharedPtr<FJsonObject>* Moves = nullptr;
        if (C->TryGetObjectField(TEXT("moves"), Moves)) S.Moves = *Moves;
        Roster.Add(S.Name, MoveTemp(S));
    }
    UE_LOG(LogTemp, Display, TEXT("BOTW roster: %d characters"), Roster.Num());
    return Roster;
}

const FBotwSpec* FBotwSpec::Find(const FString& Name) { return All().Find(Name); }

ABotwCreature::ABotwCreature()
{
    PrimaryActorTick.bCanEverTick = true;
    bReplicates = true; SetReplicateMovement(true);
    SetNetUpdateFrequency(20.f); SetMinNetUpdateFrequency(10.f);
    Capsule = CreateDefaultSubobject<UCapsuleComponent>(TEXT("Capsule"));
    RootComponent = Capsule;
    // The sword sweeps on the visibility channel and the player bumps into it, as with the fox hunter's pawn capsule.
    Capsule->SetCollisionProfileName(UCollisionProfile::Pawn_ProfileName);
    Capsule->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Capsule->SetCollisionResponseToChannel(ECC_Visibility, ECR_Block);
    Capsule->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
    Capsule->SetCanEverAffectNavigation(false);
    Mesh = CreateDefaultSubobject<USkeletalMeshComponent>(TEXT("Mesh"));
    Mesh->SetupAttachment(Capsule);
    Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Mesh->SetCanEverAffectNavigation(false);
    Mesh->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
}

ABotwCreature* ABotwCreature::SpawnAt(UWorld* World, const FString& Name, const FVector& Ground, float Yaw, EBotwMode Mode)
{
    const FBotwSpec* Spec = FBotwSpec::Find(Name);
    if (!World || !Spec || World->GetNetMode() == NM_Client) return nullptr;
    FActorSpawnParameters Params; Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    ABotwCreature* Creature = World->SpawnActor<ABotwCreature>(Ground + FVector(0, 0, Spec->HeightCm * .5f), FRotator(0, Yaw, 0), Params);
    if (Creature) Creature->Initialize(*Spec, Mode);
    return Creature;
}

void ABotwCreature::Initialize(const FBotwSpec& Spec, EBotwMode StartMode)
{
    Data = Spec;
    const float HalfHeight = FMath::Max(Data.HeightCm * .5f, Data.RadiusCm);
    Capsule->SetCapsuleSize(Data.RadiusCm, HalfHeight);
    Mesh->SetSkeletalMeshAsset(Cast<USkeletalMesh>(Data.Mesh.TryLoad()));
    Mesh->SetRelativeLocationAndRotation(FVector(0, 0, -HalfHeight), FRotator(0, Data.MeshYaw, 0));
    Mesh->SetRelativeScale3D(FVector(Data.Scale));
    MeshRest = Mesh->GetRelativeTransform();
    for (const auto& Clip : Data.Clips)
        if (UAnimSequence* Sequence = Cast<UAnimSequence>(Clip.Value.TryLoad())) Loaded.Add(Clip.Key, Sequence);
    ShowcaseOrder.Reset();
    for (const FName R : { FName("idle"), FName("walk"), FName("run"), FName("notice"), FName("angry"), FName("battle"), FName("attack"),
                           FName("hit"), FName("down"), FName("getup"), FName("dance"), FName("talk"), FName("sleep") })
        if (Loaded.Contains(Role(R))) ShowcaseOrder.AddUnique(Role(R));
    Home = Target = GetActorLocation();
    if (HasAuthority()) Ground();
    UE_LOG(LogTemp, Display, TEXT("BOTW %s (%s): %d clips, %.0f cm"), *Data.Name, *Data.Label, Loaded.Num(), Data.HeightCm);
    if (HasAuthority()) SetMode(StartMode);
    else Mode = StartMode;
}

UAnimSequence* ABotwCreature::Clip(FName Name) const { const TObjectPtr<UAnimSequence>* S = Loaded.Find(Name); return S ? S->Get() : nullptr; }

float ABotwCreature::Play(const FString& ClipOrRole, bool bLoop, float Rate, float Blend)
{
    const FName Name = ClipOrRole.StartsWith(TEXT("role:")) ? Role(FName(*ClipOrRole.RightChop(5))) : FName(*ClipOrRole);
    UAnimSequence* Sequence = Clip(Name);
    if (!Sequence) return 0.f;
    Mesh->PlayAnimation(Sequence, bLoop);
    Mesh->SetPlayRate(Rate);
    Current = Name; ClipBegan = GetWorld()->GetTimeSeconds(); ClipRate = Rate; bClipLoop = bLoop; ++ClipSerial;
    return Sequence->GetPlayLength() / FMath::Max(Rate, .01f);
}

float ABotwCreature::PlayRole(FName RoleName, bool bLoop, float Rate)
{
    const FName Name = Role(RoleName);
    if (Name == Current && bLoop) return 0.f;
    return Play(Name.ToString(), bLoop, Rate);
}

void ABotwCreature::SetMode(EBotwMode NewMode)
{
    Mode = NewMode; Showcased = 0; Health = 3; bHealthScaled = false;
    if (HasAuthority() && JapanNetwork::IsOnline(GetWorld())) GetWorld()->GetSubsystem<UJapanEncounters>()->End(this);
    Rest();
    if (Mode == EBotwMode::Showcase && ShowcaseOrder.Num()) { Phase = EPhase::Action; PhaseLeft = FMath::Max(Play(ShowcaseOrder[0].ToString(), true), 2.5f); }
}

void ABotwCreature::Rest()
{
    Phase = EPhase::Rest; bRunning = false;
    PhaseLeft = FMath::FRandRange(3.f, 7.f);
    PlayRole(Mode == EBotwMode::Camp && AttackCooldown > 0.f ? FName("battle") : FName("idle"), true);
    if (!Clip(Current)) Play(Loaded.Num() ? Loaded.CreateConstIterator()->Key.ToString() : FString(), true);
}

void ABotwCreature::MoveTo(const FVector& Ground, bool bRun)
{
    Target = Ground; bRunning = bRun; Phase = EPhase::Moving;
    PlayRole(bRun && Clip(Role("run")) ? FName("run") : FName("walk"), true);
}

void ABotwCreature::TakeSwordHit(int32 Strength, AActor* From)
{
    if (!HasAuthority()) return;
    if (JapanNetwork::IsOnline(GetWorld()))
    {
        auto* Player = Cast<AWandererCharacter>(From);
        if (!UJapanEncounters::Eligible(Player)) return;
        EngageNetworkEncounter(); GetWorld()->GetSubsystem<UJapanEncounters>()->AddThreat(this, Player, Strength);
    }
    if (Phase == EPhase::Down || Phase == EPhase::GetUp)
    {
        // Struck where it lies or rising: it still takes the blow (the striker's sparks and sound) and slides back.
        Health -= Strength;
        if (From) Knockback = ((GetActorLocation() - From->GetActorLocation()) * FVector(1, 1, 0)).GetSafeNormal() * (160.f + 60.f * FMath::Min(Strength, 3));
        return;
    }
    Health -= Strength;
    if (From)
    {
        const FVector Away = (GetActorLocation() - From->GetActorLocation()) * FVector(1, 1, 0);
        SetActorRotation(FRotator(0, (-Away).Rotation().Yaw, 0));
        // Every blow shoves it back a step, harder the heavier the blow, so a hit reads even mid-attack.
        Knockback = Away.GetSafeNormal() * (260.f + 120.f * FMath::Min(Strength, 3));
    }
    if (Health <= 0 && Clip(Role("down"))) { Phase = EPhase::Down; PhaseLeft = 4.f; Play(Role("down").ToString(), true); return; }
    Phase = EPhase::Hit;
    PhaseLeft = FMath::Max(Play(Role("hit").ToString(), false), .4f);
    if (Mode == EBotwMode::Idle || Mode == EBotwMode::Wander) Mode = EBotwMode::Camp;
}

void ABotwCreature::AdvanceLying(float Dt)
{
    static const FName HeadBone(TEXT("Head"));
    if (Mesh->GetBoneIndex(HeadBone) == INDEX_NONE) return;
    const float Head = float(Mesh->GetSocketTransform(HeadBone, RTS_Component).GetLocation().Z);
    const bool bDown = Phase == EPhase::Down || Phase == EPhase::GetUp;
    if (!bDown && Phase != EPhase::Hit && Current == Role("idle")) StandHead = StandHead > 0.f ? FMath::FInterpTo(StandHead, Head, Dt, 2.f) : Head;
    const float Want = bDown && StandHead > 0.f ? FMath::Clamp((Head - StandHead) / (.35f * StandHead), 0.f, 1.f) : 0.f;
    const float Was = LieWeight;
    LieWeight = FMath::FInterpTo(LieWeight, Want, Dt, 14.f);
    if (LieWeight < .001f) { LieWeight = 0.f; if (Was > 0.f) Mesh->SetRelativeTransform(MeshRest); return; }
    // On its back: up turned to backward (a pitch about the capsule's right axis), about the mesh's origin at its feet.
    const FVector Feet = MeshRest.GetLocation();
    Mesh->SetRelativeTransform(MeshRest * FTransform(-Feet) * FTransform(FRotator(90.f * LieWeight, 0.f, 0.f).Quaternion()) * FTransform(Feet));
}

void ABotwCreature::Strike(APawn* Player)
{
    if (!HasAuthority()) return;
    // Only a player with a move set (its guard, parry and dodges) is struck; the others keep the old sparring.
    AWandererCharacter* Wanderer = Cast<AWandererCharacter>(Player);
    if (!Wanderer || !Wanderer->GetMoves() || !Wanderer->GetSword()) return;
    const FVector To = (Player->GetActorLocation() - GetActorLocation()) * FVector(1, 1, 0);
    if (To.Size() > Data.RadiusCm + 170.f || (GetActorForwardVector() | To.GetSafeNormal()) < .4f) return;
    if (FMath::Abs(Player->GetActorLocation().Z - GetActorLocation().Z) > Data.HeightCm) return;
    JapanCombat::Strike(this, Wanderer, 12.f, GetActorLocation() + FVector(0, 0, Data.HeightCm * .3f));
}

void ABotwCreature::Steer(const FVector& Goal, float Speed, float Dt)
{
    FVector To = Goal - GetActorLocation(); To.Z = 0.f;
    if (To.IsNearlyZero()) return;
    const FRotator Facing(0, To.Rotation().Yaw, 0);
    SetActorRotation(FMath::RInterpTo(GetActorRotation(), Facing, Dt, 6.f));
    const float Step = FMath::Min(Speed * Dt, To.Size());
    AddActorWorldOffset(GetActorForwardVector() * Step);
}

void ABotwCreature::Ground()
{
    const float HalfHeight = Capsule->GetScaledCapsuleHalfHeight();
    const FVector At = GetActorLocation();
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(BotwGround), false, this);
    FCollisionObjectQueryParams Objects; Objects.AddObjectTypesToQuery(ECC_WorldStatic); Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    if (GetWorld()->LineTraceSingleByObjectType(Hit, At + FVector(0, 0, HalfHeight), At - FVector(0, 0, HalfHeight + 400.f), Objects, Params))
        SetActorLocation(FVector(At.X, At.Y, Hit.ImpactPoint.Z + HalfHeight + 1.f));
}

void ABotwCreature::Tick(float Dt)
{
    Super::Tick(Dt);
    if (JapanNetwork::IsOnline(GetWorld()) && !HasAuthority())
    {
        PresentNetworkState(); AdvanceLying(Dt); return;
    }
    if (!Mesh->GetSkeletalMeshAsset()) return;
    Clock += Dt; AttackCooldown = FMath::Max(0.f, AttackCooldown - Dt);
    Think(Dt);
    if (JapanNetwork::IsOnline(GetWorld()))
    {
        auto* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>();
        if (Phase != EPhase::Attack) Encounters->ReleaseAttack(this);
        // Down/get-up is still the same encounter: its difficulty, threat and membership survive.
    }
    Ground();
    if (GetWorld()->GetNetMode() != NM_DedicatedServer) AdvanceLying(Dt);
    PublishNetworkState();
}

void ABotwCreature::Think(float Dt)
{
    const float Walk = Data.WalkSpeed > 1.f ? Data.WalkSpeed : 150.f, Run = Data.RunSpeed > 1.f ? Data.RunSpeed : Walk * 2.f;
    PhaseLeft -= Dt;
    if (!Knockback.IsNearlyZero(1.f))
    {
        AddActorWorldOffset(Knockback * Dt, true);
        Knockback = FMath::VInterpTo(Knockback, FVector::ZeroVector, Dt, 7.f);
    }
    if (JapanNetwork::IsOnline(GetWorld()))
    {
        auto* Encounters = GetWorld()->GetSubsystem<UJapanEncounters>();
        Encounters->Refresh(this, 3000.f);
        if (Encounters->Identity(this))
        {
            if (Phase != EPhase::Attack || !UJapanEncounters::Eligible(CombatTarget)) CombatTarget = Encounters->Select(this, CombatTarget);
        }
        else CombatTarget = JapanCombat::FindPlayer(this, CombatTarget, 3000.f);
    }
    APawn* Player = JapanNetwork::IsOnline(GetWorld()) ? CombatTarget.Get() : UGameplayStatics::GetPlayerPawn(this, 0);
    const float PlayerDistance = Player ? FVector::Dist2D(Player->GetActorLocation(), GetActorLocation()) : 1e9f;
    switch (Phase)
    {
    case EPhase::Moving:
        Steer(Target, bRunning ? Run : Walk, Dt);
        if (FVector::Dist2D(Target, GetActorLocation()) < 20.f)
        {
            if (bReturningFromEncounter) { Health = 3; bHealthScaled = false; bReturningFromEncounter = false; }
            Rest();
        }
        return;
    case EPhase::Action:
        if (PhaseLeft > 0.f) return;
        if (Mode == EBotwMode::Showcase && ShowcaseOrder.Num())
        {
            Showcased = (Showcased + 1) % ShowcaseOrder.Num();
            const FName Next = ShowcaseOrder[Showcased];
            const bool* Loop = Data.Loops.Find(Next);
            PhaseLeft = FMath::Max(Play(Next.ToString(), true) * (Loop && *Loop ? 2.f : 1.f), 2.5f);
            return;
        }
        Rest();
        return;
    case EPhase::Hit:
        if (PhaseLeft <= 0.f) { Phase = EPhase::Chase; PlayRole("run", true); }
        return;
    case EPhase::Down:
        if (PhaseLeft <= 0.f) { Phase = EPhase::GetUp; PhaseLeft = FMath::Max(Play(Role("getup").ToString(), false), .5f); }
        return;
    case EPhase::GetUp:
        if (PhaseLeft <= 0.f)
        {
            Health = JapanNetwork::IsOnline(GetWorld()) ? GetWorld()->GetSubsystem<UJapanEncounters>()->FrozenHealth(this, 3) : 3;
            Phase = EPhase::Chase; PlayRole("run", true);
        }
        return;
    case EPhase::Notice:
        if (PhaseLeft <= 0.f) { Phase = EPhase::Chase; PlayRole("run", true); }
        return;
    case EPhase::Attack:
        // The blow lands a little before the middle of the clip.
        if (!bStruck && PhaseLeft <= PhaseTotal * .55f) { bStruck = true; Strike(Player); if (Phase != EPhase::Attack) return; }
        if (PhaseLeft <= 0.f) { AttackCooldown = 1.2f; Phase = EPhase::Chase; PlayRole("battle", true); }
        return;
    case EPhase::Chase:
        if (!Player || PlayerDistance > 3000.f) { if (JapanNetwork::IsOnline(GetWorld())) { GetWorld()->GetSubsystem<UJapanEncounters>()->End(this); bReturningFromEncounter = true; } MoveTo(Home, false); return; }
        if (PlayerDistance < Data.RadiusCm + 150.f)
        {
            SetActorRotation(FRotator(0, (Player->GetActorLocation() - GetActorLocation()).Rotation().Yaw, 0));
            if (AttackCooldown <= 0.f && (!JapanNetwork::IsOnline(GetWorld()) || GetWorld()->GetSubsystem<UJapanEncounters>()->ReserveAttack(this, CombatTarget, 5.f))) { Phase = EPhase::Attack; PhaseLeft = PhaseTotal = FMath::Max(Play(Role("attack").ToString(), false), .5f); bStruck = false; }
            else PlayRole(Clip(Role("battle")) ? FName("battle") : FName("idle"), true);
            return;
        }
        PlayRole(Clip(Role("run")) ? FName("run") : FName("walk"), true);
        Steer(Player->GetActorLocation(), Clip(Role("run")) ? Run : Walk, Dt);
        return;
    case EPhase::Rest:
        if (Mode == EBotwMode::Scripted) return;
        // A crouching player is noticed only close by, and from behind only within arm's reach.
        const bool bSneaking = Player && Player->IsA<ACharacter>() && Cast<ACharacter>(Player)->bIsCrouched;
        const bool bInFront = Player && (GetActorForwardVector() | (Player->GetActorLocation() - GetActorLocation()).GetSafeNormal2D()) > .3f;
        if (Mode == EBotwMode::Camp && Player && (bSneaking ? PlayerDistance < 200.f || (bInFront && PlayerDistance < 450.f) : PlayerDistance < 1400.f))
        {
            SetActorRotation(FRotator(0, (Player->GetActorLocation() - GetActorLocation()).Rotation().Yaw, 0));
            EngageNetworkEncounter();
            Phase = EPhase::Notice; PhaseLeft = FMath::Max(Play(Role("notice").ToString(), false), .3f);
            return;
        }
        if (PhaseLeft > 0.f) return;
        if (Mode == EBotwMode::Wander)
        {
            const FVector2D Offset = FVector2D(FMath::FRandRange(-1.f, 1.f), FMath::FRandRange(-1.f, 1.f)).GetSafeNormal() * FMath::FRandRange(200.f, 700.f);
            MoveTo(Home + FVector(Offset, 0.f), false);
        }
        else if (Mode == EBotwMode::Camp && Clip(Role("dance")) && FMath::RandBool())
        {
            Phase = EPhase::Action; PhaseLeft = FMath::Max(Play(Role("dance").ToString(), true), 4.f);
        }
        else Rest();
        return;
    }
}


void ABotwCreature::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(ABotwCreature, NetworkState);
}

void ABotwCreature::PublishNetworkState()
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    NetworkState.SpecName = Data.Name; NetworkState.Clip = Current; NetworkState.Serial = ClipSerial;
    NetworkState.Began = ClipBegan; NetworkState.Rate = ClipRate; NetworkState.bLoop = bClipLoop;
    NetworkState.Mode = uint8(Mode); NetworkState.Phase = uint8(Phase); NetworkState.Health = Health;
}

void ABotwCreature::OnRep_NetworkState() { PresentNetworkState(); }

void ABotwCreature::PresentNetworkState()
{
    if (HasAuthority() || NetworkState.SpecName.IsEmpty()) return;
    if (Data.Name != NetworkState.SpecName)
    {
        const auto* Spec = FBotwSpec::Find(NetworkState.SpecName);
        if (!Spec) return;
        Initialize(*Spec, EBotwMode(NetworkState.Mode));
    }
    auto* Animation = Clip(NetworkState.Clip);
    if (!Animation) return;
    if (AppliedClipSerial != NetworkState.Serial || Current != NetworkState.Clip)
    {
        Mesh->PlayAnimation(Animation, NetworkState.bLoop);
        Mesh->SetPlayRate(NetworkState.Rate);
        AppliedClipSerial = NetworkState.Serial; Current = NetworkState.Clip;
    }
    const auto* ClockSource = GetWorld()->GetGameState();
    const double Now = ClockSource ? ClockSource->GetServerWorldTimeSeconds() : GetWorld()->GetTimeSeconds();
    float At = FMath::Max(0.f, float(Now - NetworkState.Began)) * NetworkState.Rate;
    if (NetworkState.bLoop && Animation->GetPlayLength() > 0.f) At = FMath::Fmod(At, Animation->GetPlayLength());
    else At = FMath::Clamp(At, 0.f, Animation->GetPlayLength());
    Mesh->SetPosition(At, false);
    Phase = EPhase(NetworkState.Phase); Mode = EBotwMode(NetworkState.Mode); Health = NetworkState.Health;
}


void ABotwCreature::EngageNetworkEncounter()
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    if (bReturningFromEncounter) { Health = 3; bHealthScaled = false; bReturningFromEncounter = false; }
    const int32 Scaled = GetWorld()->GetSubsystem<UJapanEncounters>()->Engage(this, 1400.f, 3);
    if (!bHealthScaled) { Health += Scaled - 3; bHealthScaled = true; }
}
