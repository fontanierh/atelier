#include "SkiComponent.h"
#include "SkiPark.h"
#include "SkiPhysicalBody.h"
#include "SkiRider.h"
#include "SkiSettings.h"
#include "SkiTerrain.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "InputCoreTypes.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "UObject/ConstructorHelpers.h"

namespace ski = atelier::ski;

namespace
{
TAutoConsoleVariable<int32> CVarPhysical(TEXT("ski.Physical"),
    -1, TEXT("The skier's body as an active ragdoll: 1 on, 0 the pose alone, -1 the project setting (takes effect on the next start)."));

/** The first local player's skis. */
USkiComponent* PlayerSki(UWorld* World)
{
    const APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
    const APawn* Pawn = PC ? PC->GetPawn() : nullptr;
    return Pawn ? Pawn->FindComponentByClass<USkiComponent>() : nullptr;
}

// QA and play: to the top of the first park on skis, scripted controls, and a line of state.
FAutoConsoleCommandWithWorldAndArgs ParkCommand(TEXT("ski.Park"), TEXT("Skis on at the top of the terrain park: ski.Park [speed m/s]"),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        USkiComponent* Ski = PlayerSki(World);
        TActorIterator<ASkiPark> Park(World);
        if (!Ski || !Park) { UE_LOG(LogTemp, Warning, TEXT("SKI no skier or no park")); return; }
        const float Speed = Args.Num() > 0 ? FCString::Atof(*Args[0]) * 100.f : 0.f;
        Ski->StartAt(Park->GetStartLocation(), Park->GetStartYaw(), Speed);
    }));
FAutoConsoleCommandWithWorldAndArgs InputCommand(TEXT("ski.Input"),
    TEXT("Scripted controls until ski.Input off: ski.Input steer lean crouch(0/1) spin grab(0-2) brake(0/1)"),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        USkiComponent* Ski = PlayerSki(World);
        if (!Ski) return;
        if (Args.Num() == 0 || Args[0] == TEXT("off")) { Ski->SetScriptedInput(false, FSkiInput()); return; }
        auto Arg = [&Args](int32 I) { return Args.IsValidIndex(I) ? FCString::Atof(*Args[I]) : 0.f; };
        FSkiInput I;
        I.Steer = Arg(0); I.Lean = Arg(1); I.bCrouch = Arg(2) > .5f; I.Spin = Arg(3); I.Grab = int32(Arg(4)); I.bBrake = Arg(5) > .5f;
        Ski->SetScriptedInput(true, I);
    }));
FAutoConsoleCommandWithWorld DescribeCommand(TEXT("ski.Describe"), TEXT("Logs the skier's state."),
    FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World)
    {
        if (const USkiComponent* Ski = PlayerSki(World)) UE_LOG(LogTemp, Display, TEXT("SKI %s"), *Ski->Describe());
    }));
FAutoConsoleCommandWithWorld OffCommand(TEXT("ski.Off"), TEXT("Skis off at once."),
    FConsoleCommandWithWorldDelegate::CreateLambda([](UWorld* World) { if (USkiComponent* Ski = PlayerSki(World)) Ski->Stop(); }));

constexpr float SkiThickness = 3.f;   // cm
constexpr float SkiLength = 175.f;    // cm

/** The reference pose's component-space transform of a bone. */
FTransform RefComponentSpace(const FReferenceSkeleton& Ref, int32 Index)
{
    FTransform T = Ref.GetRefBonePose()[Index];
    for (int32 Parent = Ref.GetParentIndex(Index); Parent != INDEX_NONE; Parent = Ref.GetParentIndex(Parent))
        T = T * Ref.GetRefBonePose()[Parent];
    return T;
}

ski::Quat SkiRotation(const ski::State& St)
{
    return ski::Multiply(St.q, {FMath::Cos(St.angulation / 2), FMath::Sin(St.angulation / 2), 0, 0});
}
}

/** The simulation and the snow it stands on. */
struct FSkiRuntime
{
    FSkiRuntime(UWorld* World, const AActor* Ignore) : Terrain(World, Ignore) {}
    ski::Settings Settings;
    ski::State State;
    FSkiWorldTerrain Terrain;
    ski::Input Input;
};

USkiComponent::USkiComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
    static ConstructorHelpers::FObjectFinder<UMaterialInterface> Plain(TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
    DefaultSkiMesh = Cube.Object;
    DefaultSkiMaterial = Plain.Object;
}

void FSkiRuntimeDeleter::operator()(FSkiRuntime* Ptr) const { delete Ptr; }

void USkiComponent::Initialize(ACharacter* InCharacter)
{
    if (Character) return;
    Character = InCharacter;
    Rider = Cast<ISkiRider>(InCharacter);
    checkf(Rider, TEXT("USkiComponent: the character must implement ISkiRider"));
    // After the movement step that runs the simulation, before the mesh animates the pose.
    AddTickPrerequisiteComponent(Character->GetCharacterMovement());
    Character->GetMesh()->AddTickPrerequisiteComponent(this);

    const USkiSettings* S = GetDefault<USkiSettings>();
    UStaticMesh* Mesh = S->SkiMesh.IsNull() ? nullptr : S->SkiMesh.LoadSynchronous();
    UMaterialInterface* Material = S->SkiMaterial.IsNull() ? nullptr : S->SkiMaterial.LoadSynchronous();
    if (!Material && DefaultSkiMaterial)
    {
        UMaterialInstanceDynamic* Orange = UMaterialInstanceDynamic::Create(DefaultSkiMaterial, this);
        Orange->SetVectorParameterValue(TEXT("Color"), FLinearColor(.95f, .38f, .05f));
        Material = Orange;
    }
    for (int32 Side = 0; Side < 2; ++Side)
    {
        UStaticMeshComponent* Ski = NewObject<UStaticMeshComponent>(Character, Side == 0 ? TEXT("SkiLeft") : TEXT("SkiRight"));
        Ski->SetStaticMesh(Mesh ? Mesh : DefaultSkiMesh.Get());
        Ski->SetMaterial(0, Material);
        Ski->SetUsingAbsoluteLocation(true); Ski->SetUsingAbsoluteRotation(true); Ski->SetUsingAbsoluteScale(true);
        Ski->SetupAttachment(Character->GetRootComponent());
        Ski->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Ski->SetGenerateOverlapEvents(false);
        Ski->SetCanEverAffectNavigation(false);
        Ski->RegisterComponent();
        // The engine cube is 1 m on a side and centred; a ski mesh is 1 m long with its base at 0.
        Ski->SetWorldScale3D(Mesh ? FVector(SkiLength / 100.f, 1, 1) : FVector(SkiLength / 100.f, .1f, SkiThickness / 100.f));
        Ski->SetVisibility(false);
        Skis[Side] = Ski;
    }
    bCubeSkis = !Mesh;
}

bool USkiComponent::Toggle()
{
    if (!bSkiing) return Start();
    if (bCrashed || IsAirborne()) return false;
    Stop();
    return true;
}

bool USkiComponent::Start()
{
    if (!Character || bSkiing) return false;
    UCharacterMovementComponent* M = Character->GetCharacterMovement();
    if (!M->IsMovingOnGround()) return false;
    const FVector Feet = Character->GetActorLocation()
        - FVector(0, 0, Character->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + M->CurrentFloor.FloorDist);
    const FVector Flat(M->Velocity.X, M->Velocity.Y, 0);
    const float Yaw = Flat.Size() > 30.f ? Flat.Rotation().Yaw : Character->GetActorRotation().Yaw;
    return BeginRide(Feet, Yaw, Flat.Size());
}

bool USkiComponent::StartAt(FVector Location, float Yaw, float Speed)
{
    if (!Character) return false;
    if (bSkiing) Stop();
    return BeginRide(Location, Yaw, Speed);
}

bool USkiComponent::BeginRide(const FVector& Feet, float Yaw, float Speed)
{
    Runtime.Reset(new FSkiRuntime(GetWorld(), Character));
    ski::Settings& S = Runtime->Settings;
    const USkiSettings* Project = GetDefault<USkiSettings>();
    S.balanceAssist = Project->BalanceAssist;
    S.airAssist = Project->AirAssist;
    S.spinAssist = Project->SpinAssist;
    const ski::Vec3 At = SkiFrame::FromWorld(Feet);
    Runtime->Terrain.SetHint(At.z);
    if (Runtime->Terrain.Height(At.x, At.y) < FSkiWorldTerrain::Nothing / 2)
    {
        UE_LOG(LogTemp, Warning, TEXT("SKI no snow under %s"), *Feet.ToString());
        Runtime.Reset();
        return false;
    }
    Rider->PrepareToSki();
    Runtime->State = ski::CreateSkier(Runtime->Terrain, At.x, At.y, -FMath::DegreesToRadians(Yaw), Speed / 100.0, S);

    UCharacterMovementComponent* M = Character->GetCharacterMovement();
    UCapsuleComponent* Capsule = Character->GetCapsuleComponent();
    CapsuleHalfHeight = Capsule->GetScaledCapsuleHalfHeight();
    SavedCapsuleToBodies = Capsule->GetCollisionResponseToChannel(ECC_PhysicsBody);
    Capsule->SetCollisionResponseToChannel(ECC_PhysicsBody, ECR_Ignore);
    M->SetMovementMode(MOVE_Custom, MovementMode);
    bSkiing = true;
    bCrashed = false;
    Accumulator = CrashClock = GrabWeight = AirArms = 0.f;
    LastEvent = TEXT("start");
    PlaceActor();
    for (UStaticMeshComponent* Ski : Skis) Ski->SetVisibility(true);
    bSkisOnFeet = false;

    const int32 Physical = CVarPhysical.GetValueOnGameThread();
    if (Physical == 1 || (Physical < 0 && Project->bPhysicalRider))
    {
        Body = NewObject<USkiPhysicalBody>(this);
        const FName Feet2[2] = {Bone(TEXT("foot_L")), Bone(TEXT("foot_R"))};
        const FName Hands[2] = {Bone(TEXT("hand_L")), Bone(TEXT("hand_R"))};
        if (!Body->Begin(Character->GetMesh(), Bone(TEXT("pelvis")), Feet2, Hands)) Body = nullptr;
    }
    UE_LOG(LogTemp, Display, TEXT("SKI start at %s yaw %.0f speed %.0f, body %s"), *Feet.ToString(), Yaw, Speed,
        Body ? TEXT("physical") : TEXT("pose"));
    return true;
}

void USkiComponent::Stop()
{
    if (!bSkiing) return;
    if (Body) { Body->End(); Body = nullptr; }
    UCharacterMovementComponent* M = Character->GetCharacterMovement();
    const FVector Flat(M->Velocity.X, M->Velocity.Y, 0);
    const FVector Feet = Runtime ? SkiFrame::ToWorld(Runtime->State.p + ski::Rotate(Runtime->State.q, ski::BootLocal(Runtime->State)))
                                 : Character->GetActorLocation() - FVector(0, 0, CapsuleHalfHeight);
    Character->GetCapsuleComponent()->SetCollisionResponseToChannel(ECC_PhysicsBody, SavedCapsuleToBodies);
    Character->SetActorLocationAndRotation(Feet + FVector(0, 0, CapsuleHalfHeight + 2.f),
        FRotator(0, Character->GetActorRotation().Yaw, 0), false, nullptr, ETeleportType::TeleportPhysics);
    M->SetMovementMode(MOVE_Falling);
    M->Velocity = Flat.GetClampedToMaxSize(420.f);
    for (UStaticMeshComponent* Ski : Skis) Ski->SetVisibility(false);
    bSkiing = bCrashed = false;
    Runtime.Reset();
    UE_LOG(LogTemp, Display, TEXT("SKI stop, score %d"), Score);
}

void USkiComponent::SetScriptedInput(bool bOn, FSkiInput Input)
{
    bScripted = bOn;
    Scripted = Input;
}

void USkiComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (Body) { Body->End(); Body = nullptr; }
    Runtime.Reset();
    bSkiing = false;
    Super::EndPlay(Reason);
}

bool USkiComponent::IsCrashed() const { return bSkiing && bCrashed; }

bool USkiComponent::IsAirborne() const { return Runtime && !bCrashed && !Runtime->State.grounded; }

float USkiComponent::GetSpeed() const
{
    if (!bSkiing) return 0.f;
    if (bCrashed && Body && Body->IsCrashed()) return Body->GetPelvisVelocity().Size();
    return Runtime ? float(ski::Length(Runtime->State.v) * 100.0) : 0.f;
}

FString USkiComponent::GetStatus() const
{
    if (!bSkiing || !Runtime) return TEXT("off");
    if (bCrashed) return TEXT("crash");
    const ski::State& St = Runtime->State;
    if (!St.grounded) return TEXT("air");
    if (Runtime->Input.brake) return TEXT("stopping");
    return St.slip < .4 && FMath::Abs(St.edge) > FMath::DegreesToRadians(8.0) ? TEXT("carving") : TEXT("skidding");
}

FString USkiComponent::GetLastTrick(float& Age) const
{
    Age = GetWorld() ? float(GetWorld()->GetTimeSeconds() - LastTrickTime) : 1e9f;
    return LastTrick;
}

int32 USkiComponent::GetScore() const { return Score; }

FString USkiComponent::Describe() const
{
    if (!Runtime) return TEXT("ski off");
    const ski::State& St = Runtime->State;
    const ski::Report R = ski::Summarize(St, Runtime->Settings);
    const FVector P = SkiFrame::ToWorld(St.p);
    return FString::Printf(TEXT("ski %s speed %.1f m/s edge %.0f roll %.0f h %.2f at (%.0f %.0f %.0f) score %d body %s last %s"),
        *GetStatus(), R.speed, R.edgeDeg, R.rollDeg, St.h, P.X, P.Y, P.Z, Score,
        Body ? (Body->IsCrashed() ? TEXT("ragdoll") : TEXT("active")) : TEXT("pose"), *LastEvent);
}

FName USkiComponent::Bone(const TCHAR* Contract) const { return Rider ? Rider->GetSkiBone(FName(Contract)) : FName(Contract); }

FSkiInput USkiComponent::ReadInput() const
{
    if (bScripted) return Scripted;
    FSkiInput I;
    const APlayerController* PC = Character ? Cast<APlayerController>(Character->GetController()) : nullptr;
    if (!PC || Rider->IsSkiInputBlocked()) return I;
    auto Down = [PC](const FKey& Key) { return PC->IsInputKeyDown(Key); };
    auto Axis = [PC](const FKey& Key) { return PC->GetInputAnalogKeyState(Key); };
    I.Steer = FMath::Clamp(Axis(EKeys::Gamepad_LeftX) + (Down(EKeys::D) ? 1.f : 0.f) - (Down(EKeys::A) ? 1.f : 0.f), -1.f, 1.f);
    I.Lean = FMath::Clamp(Axis(EKeys::Gamepad_LeftY) + (Down(EKeys::W) ? 1.f : 0.f) - (Down(EKeys::S) ? 1.f : 0.f), -1.f, 1.f);
    I.bCrouch = Down(EKeys::SpaceBar) || Down(EKeys::Gamepad_FaceButton_Bottom);
    I.Spin = FMath::Clamp(Axis(EKeys::Gamepad_RightX) + (Down(EKeys::L) ? 1.f : 0.f) - (Down(EKeys::J) ? 1.f : 0.f), -1.f, 1.f);
    if (Down(EKeys::Q) || Axis(EKeys::Gamepad_LeftTriggerAxis) > .5f) I.Grab = 1;
    else if (Down(EKeys::E) || Axis(EKeys::Gamepad_RightTriggerAxis) > .5f) I.Grab = 2;
    I.bBrake = Down(EKeys::LeftShift) || Down(EKeys::Gamepad_FaceButton_Right);
    return I;
}

void USkiComponent::PhysSki(float Dt)
{
    if (!bSkiing || !Runtime) return;
    if (bCrashed && Body && Body->IsCrashed())
    {
        // The ragdoll has the body: the character follows its pelvis.
        const FVector Pelvis = Body->GetPelvisLocation();
        Character->SetActorLocation(Pelvis, false, nullptr, ETeleportType::None);
        Character->GetCharacterMovement()->Velocity = Body->GetPelvisVelocity();
        return;
    }
    const FSkiInput In = ReadInput();
    StepSimulation(Dt, In);
    HandleEvents();
    PlaceActor();
}

void USkiComponent::StepSimulation(float Dt, const FSkiInput& In)
{
    ski::Input& I = Runtime->Input;
    I.steer = In.Steer;
    I.lean = In.Lean;
    I.crouch = In.bCrouch;
    I.spin = In.Spin;
    I.grab = ski::Grab(FMath::Clamp(In.Grab, 0, ski::GrabCount - 1));
    I.brake = In.bBrake;
    const ski::Settings& S = Runtime->Settings;
    Accumulator += FMath::Min(Dt, .1f);
    const int32 Steps = FMath::FloorToInt32(Accumulator / S.dt);
    Accumulator -= float(Steps * S.dt);
    for (int32 N = 0; N < Steps; ++N)
    {
        Runtime->Terrain.SetHint(Runtime->State.p.z);
        ski::Step(Runtime->State, I, Runtime->Terrain, S);
    }
}

void USkiComponent::HandleEvents()
{
    ski::State& St = Runtime->State;
    const double Now = GetWorld()->GetTimeSeconds();
    for (const ski::Event& E : St.events)
    {
        const FString Trick = UTF8_TO_TCHAR(E.trick.c_str());
        switch (E.type)
        {
        case ski::EventType::Takeoff: LastEvent = TEXT("takeoff"); break;
        case ski::EventType::Land:
            LastEvent = FString::Printf(TEXT("land %s %.1fs"), *Trick, E.air);
            LastTrick = Trick; LastTrickTime = Now;
            break;
        case ski::EventType::Trick:
            LastEvent = FString::Printf(TEXT("%s +%d"), *Trick, E.points);
            LastTrick = LastEvent; LastTrickTime = Now;
            break;
        case ski::EventType::Bail:
            LastTrick = FString::Printf(TEXT("%s (bailed)"), *Trick); LastTrickTime = Now;
            break;
        case ski::EventType::Crash:
            LastEvent = FString::Printf(TEXT("crash: %s"), UTF8_TO_TCHAR(E.why.c_str()));
            bCrashed = true;
            CrashClock = 0.f;
            if (Body)
            {
                // The skis stay where they are on the feet; the body takes the skier's momentum.
                for (int32 Side = 0; Side < 2; ++Side)
                    SkiOnFoot[Side] = Skis[Side]->GetComponentTransform().GetRelativeTransform(
                        Character->GetMesh()->GetSocketTransform(Pose.Foot[Side]));
                bSkisOnFeet = true;
                Body->Crash(SkiFrame::ToWorld(St.v));
            }
            break;
        }
        UE_LOG(LogTemp, Display, TEXT("SKI %s"), *LastEvent);
    }
    St.events.clear();
    Score = St.score;
}

void USkiComponent::PlaceActor()
{
    const ski::State& St = Runtime->State;
    const FVector Boot = SkiFrame::ToWorld(St.p + ski::Rotate(St.q, ski::BootLocal(St)));
    const FVector Forward = SkiFrame::DirectionToWorld(ski::Rotate(St.q, {1, 0, 0}));
    const FVector Flat(Forward.X, Forward.Y, 0);
    const float Yaw = Flat.SizeSquared() > .01f ? Flat.Rotation().Yaw : Character->GetActorRotation().Yaw;
    Character->SetActorLocationAndRotation(Boot + FVector(0, 0, CapsuleHalfHeight), FRotator(0, Yaw, 0), false, nullptr, ETeleportType::None);
    Character->GetCharacterMovement()->Velocity = SkiFrame::ToWorld(St.v);
}

void USkiComponent::GetUp()
{
    // Back on the skis where the body lies (or the simulation tumbled to), standing still, facing the way it slid.
    FVector At = Body && Body->IsCrashed() ? Body->GetPelvisLocation() : SkiFrame::ToWorld(Runtime->State.p);
    const FVector Slide = Body && Body->IsCrashed() ? Body->GetPelvisVelocity() : SkiFrame::ToWorld(Runtime->State.v);
    const FVector Flat(Slide.X, Slide.Y, 0);
    const float Yaw = Flat.Size() > 30.f ? Flat.Rotation().Yaw : Character->GetActorRotation().Yaw;
    const ski::Vec3 P = SkiFrame::FromWorld(At);
    Runtime->Terrain.SetHint(P.z + 2.0);
    const double Ground = Runtime->Terrain.Height(P.x, P.y);
    if (Ground < FSkiWorldTerrain::Nothing / 2) { Stop(); return; }
    Runtime->State = ski::CreateSkier(Runtime->Terrain, P.x, P.y, -FMath::DegreesToRadians(Yaw), 0, Runtime->Settings);
    if (Body) Body->Recover();
    bCrashed = false;
    bSkisOnFeet = false;
    CrashClock = 0.f;
    Accumulator = 0.f;
    LastEvent = TEXT("up");
    PlaceActor();
}

void USkiComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    PoseWeight = FMath::FInterpConstantTo(PoseWeight, bSkiing ? 1.f : 0.f, DeltaTime, 6.f);
    if (!bSkiing || !Runtime) { Pose.Weight = PoseWeight; return; }
    if (bCrashed)
    {
        CrashClock += DeltaTime;
        // A body that fell through the snow ends its crash at once.
        bool bLost = false;
        if (Body && Body->IsCrashed())
        {
            const ski::Vec3 P = SkiFrame::FromWorld(Body->GetPelvisLocation());
            Runtime->Terrain.SetHint(P.z + 3.0);
            bLost = P.z < Runtime->Terrain.Height(P.x, P.y) - 3.0;
        }
        if (CrashClock > GetDefault<USkiSettings>()->CrashTime || bLost) GetUp();
        if (!bSkiing) return;
    }
    UpdatePose(DeltaTime);
    PlaceSkis();
    if (Body) Body->Update();

    // The view turns toward the direction of travel.
    const float Follow = GetDefault<USkiSettings>()->CameraFollow;
    APlayerController* PC = Cast<APlayerController>(Character->GetController());
    const FVector V = Character->GetCharacterMovement()->Velocity;
    const FVector Flat(V.X, V.Y, 0);
    if (PC && PC->IsLocalController() && Follow > 0.f && Flat.Size() > 200.f)
    {
        FRotator View = PC->GetControlRotation();
        View.Yaw = FMath::RInterpTo(FRotator(0, View.Yaw, 0), FRotator(0, Flat.Rotation().Yaw, 0), DeltaTime, Follow).Yaw;
        PC->SetControlRotation(View);
    }
}

void USkiComponent::UpdatePose(float Dt)
{
    const ski::State& St = Runtime->State;
    const ski::Settings& S = Runtime->Settings;
    USkeletalMeshComponent* Mesh = Character->GetMesh();
    const USkeletalMesh* Asset = Mesh->GetSkeletalMeshAsset();
    if (!Asset) return;
    const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
    auto RefCS = [&Ref](FName Name)
    {
        const int32 Index = Ref.FindBoneIndex(Name);
        return Index == INDEX_NONE ? FTransform::Identity : RefComponentSpace(Ref, Index);
    };

    Pose.Pelvis = Bone(TEXT("pelvis"));
    Pose.Spine[0] = Bone(TEXT("spine")); Pose.Spine[1] = Bone(TEXT("spine_mid")); Pose.Spine[2] = Bone(TEXT("chest"));
    Pose.Neck = Bone(TEXT("neck")); Pose.Head = Bone(TEXT("head"));
    static const TCHAR* Suffix[2] = {TEXT("_L"), TEXT("_R")};
    for (int32 Side = 0; Side < 2; ++Side)
    {
        auto Limb = [&](const TCHAR* Name) { return Bone(*(FString(Name) + Suffix[Side])); };
        Pose.Thigh[Side] = Limb(TEXT("thigh")); Pose.Shin[Side] = Limb(TEXT("shin")); Pose.Foot[Side] = Limb(TEXT("foot"));
        Pose.UpperArm[Side] = Limb(TEXT("upperarm")); Pose.Forearm[Side] = Limb(TEXT("forearm")); Pose.Hand[Side] = Limb(TEXT("hand"));
    }

    const FTransform Component = Mesh->GetComponentTransform();
    const FQuat MeshQ = Component.GetRotation();
    const FQuat ActorQ = Character->GetActorQuat();
    // A world rotation of the upright skier, as a delta in component space, applied to a reference bone.
    auto ToComponent = [&](const FQuat& World, const FQuat& RefBone) { return MeshQ.Inverse() * (World * ActorQ.Inverse()) * MeshQ * RefBone; };

    const FQuat BodyQ = SkiFrame::RotationToWorld(St.q);
    const FQuat SkiQ = SkiFrame::RotationToWorld(SkiRotation(St));
    const FVector F = BodyQ.GetForwardVector(), U = BodyQ.GetUpVector(), L = -BodyQ.GetRightVector();
    const FVector SkiF = SkiQ.GetForwardVector(), SkiU = SkiQ.GetUpVector(), SkiL = -SkiQ.GetRightVector();
    const FVector Boot = SkiFrame::ToWorld(St.p + ski::Rotate(St.q, ski::BootLocal(St)));

    // The character's legs are not the simulation's: scale the pelvis's height over the boots to them.
    const FTransform RefPelvis = RefCS(Pose.Pelvis);
    const FTransform RefFoot = RefCS(Pose.Foot[0]);
    const float MeshScale = Component.GetScale3D().Z;
    const float PelvisHeight = FMath::Max(40.f, float(RefPelvis.GetLocation().Z) * MeshScale);
    const float AnkleHeight = FMath::Max(4.f, float(RefFoot.GetLocation().Z) * MeshScale);
    const float LegScale = PelvisHeight / float(S.standHeight * 100.0);
    const FVector Pelvis = Boot + SkiU * SkiThickness + (SkiFrame::ToWorld(St.p) - Boot) * LegScale;
    Pose.PelvisTarget = FTransform(ToComponent(BodyQ, RefPelvis.GetRotation()), Component.InverseTransformPosition(Pelvis));

    const float Half = GetDefault<USkiSettings>()->StanceWidth / 2.f;
    FVector SkiCentre[2];
    for (int32 Side = 0; Side < 2; ++Side)
    {
        SkiCentre[Side] = Boot + SkiL * (Side == 0 ? Half : -Half);
        const FVector Ankle = SkiCentre[Side] + SkiU * (SkiThickness + AnkleHeight);
        Pose.Ankle[Side] = Component.InverseTransformPosition(Ankle);
        Pose.Knee[Side] = Component.InverseTransformPosition(Ankle + SkiF * 60.f + SkiU * 40.f + SkiL * (Side == 0 ? 8.f : -8.f));
        Pose.FootRotation[Side] = ToComponent(SkiQ, RefCS(Pose.Foot[Side]).GetRotation());
        SkiWorld[Side] = FTransform(SkiQ, SkiCentre[Side]);
    }

    // Arms: forward and wide for balance, out in the air; a grab takes one hand to its ski.
    const bool bAir = !St.grounded && !bCrashed;
    AirArms = FMath::FInterpTo(AirArms, bAir ? 1.f : 0.f, Dt, 5.f);
    const int32 Grab = Runtime->Input.grab == ski::Grab::Mute ? 1 : Runtime->Input.grab == ski::Grab::Safety ? 2 : 0;
    if (bAir && Grab) GrabSide = Grab;
    GrabWeight = FMath::FInterpTo(GrabWeight, bAir && Grab ? 1.f : 0.f, Dt, 9.f);
    const float S2 = LegScale;
    for (int32 Side = 0; Side < 2; ++Side)
    {
        const float Out = Side == 0 ? 1.f : -1.f;
        const FVector Ride = Pelvis + F * (28.f * S2) + L * (Out * 32.f * S2) + U * (18.f * S2);
        const FVector Air = Pelvis + F * (10.f * S2) + L * (Out * 55.f * S2) + U * (35.f * S2);
        FVector Hand = FMath::Lerp(Ride, Air, AirArms);
        if (GrabSide == 1 && Side == 0) Hand = FMath::Lerp(Hand, SkiCentre[0] + SkiF * 30.f + SkiU * 10.f, GrabWeight);
        if (GrabSide == 2 && Side == 1) Hand = FMath::Lerp(Hand, SkiCentre[1] - SkiL * 10.f + SkiU * 10.f, GrabWeight);
        Pose.HandTarget[Side] = Component.InverseTransformPosition(Hand);
        Pose.Elbow[Side] = Component.InverseTransformPosition(Pelvis + L * (Out * 50.f * S2) - F * (25.f * S2) + U * (10.f * S2));
    }

    const float Crouch = FMath::Clamp(float((S.standHeight - St.h) / S.crouchDrop), 0.f, 1.f);
    Pose.Bend = bCrashed ? .6f : .15f + .35f * Crouch + .35f * float(St.tuck);
    Pose.Look = Pose.Bend * .8f;
    Pose.BendAxis = MeshQ.Inverse().RotateVector(FVector::CrossProduct(U, F)).GetSafeNormal();
    Pose.Weight = PoseWeight;
}

void USkiComponent::PlaceSkis()
{
    for (int32 Side = 0; Side < 2; ++Side)
    {
        FTransform Ski = SkiWorld[Side];
        // In a crash with a body the skis stay on its feet; otherwise on the snow under the simulated boots.
        if (bSkisOnFeet && Body && Body->IsCrashed())
            Ski = SkiOnFoot[Side] * Character->GetMesh()->GetSocketTransform(Pose.Foot[Side]);
        const FVector Lift = bCubeSkis ? Ski.GetRotation().GetUpVector() * (SkiThickness / 2.f) : FVector::ZeroVector;
        Skis[Side]->SetWorldLocationAndRotation(Ski.GetLocation() + Lift, Ski.GetRotation());
    }
}

bool USkiComponent::GetPose(FSkiPose& Out) const
{
    if (Pose.Weight <= 0.f || Pose.Pelvis.IsNone()) return false;
    Out = Pose;
    return true;
}
