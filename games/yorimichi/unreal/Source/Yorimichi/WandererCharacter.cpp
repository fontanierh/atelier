#include "WandererCharacter.h"
#include "AtelierData.h"
#include "YorimichiCombatFX.h"
#include "LiveLibrary.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundWave.h"
TSharedPtr<struct FFightFilm> CreateFightFilm(AWandererCharacter* P);
void AdvanceFightFilm(struct FFightFilm& F, float Dt);
#include "JapanFootsteps.h"
#include "WandererSword.h"
#include "BotwMoveSet.h"
#include "Algo/Find.h"
#include "YorimichiPhone.h"
#include "AtelierStream.h"
#include "Misc/App.h"
#include "WandererDefinition.h"
#include "WandererAnimInstance.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "JapanCharacterMovement.h"
#include "JapanWorld.h"
#include "JapanCameraArm.h"
#include "SeeThrough.h"
#include "ZeppelinService.h"
#include "JapanPreferences.h"
#include "JapanMap.h"
#include "Animation/AnimSequence.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "InputKeyEventArgs.h"
#include "GameFramework/RootMotionSource.h"
#include "Curves/CurveFloat.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Components/BoxComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "InputMappingContext.h"
#include "InputAction.h"
#include "InputModifiers.h"
#include "Engine/LocalPlayer.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "HighResScreenshot.h"
#include "Misc/CommandLine.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "HAL/FileManager.h"
#include "Framework/Application/SlateApplication.h"

float AWandererCharacter::GetSprintSpeed() const
{
    if (!Definition) return 0.f;
    return Definition->UseAuthoredMovement ? Definition->SprintSpeed*SprintSpeedMultiplier : Definition->RunSpeed*2.5f;
}

AWandererCharacter::AWandererCharacter(const FObjectInitializer& ObjectInitializer)
    : Super(ObjectInitializer.SetDefaultSubobjectClass<UJapanCharacterMovement>(ACharacter::CharacterMovementComponentName))
{
    PrimaryActorTick.bCanEverTick = true;
    SkateRide = CreateDefaultSubobject<USkateComponent>(TEXT("Skate"));
    Sailboat = CreateDefaultSubobject<USailboatComponent>(TEXT("EquippedSailboat"));
    Footsteps = CreateDefaultSubobject<UJapanFootstepComponent>(TEXT("Footsteps"));
    Sword = CreateDefaultSubobject<UWandererSwordComponent>(TEXT("Sword"));
    GetCapsuleComponent()->InitCapsuleSize(22.f, 75.5f);
    bUseControllerRotationYaw = false;
    UCharacterMovementComponent* Movement = GetCharacterMovement();
    Movement->bOrientRotationToMovement = true;
    Movement->RotationRate = FRotator(0, 540, 0);
    Movement->MaxWalkSpeed = 300.f;
    Movement->MaxWalkSpeedCrouched = 50.f;
    Movement->MaxAcceleration = 1400.f;
    Movement->BrakingDecelerationWalking = 1600.f;
    Movement->GroundFriction = 7.f;
    Movement->JumpZVelocity = 490.f;
    Movement->GravityScale = 1.5f;
    Movement->AirControl = .32f;
    Movement->GetNavAgentPropertiesRef().bCanCrouch = true;
    Movement->SetCrouchedHalfHeight(65.5f);
    JumpMaxHoldTime = 0.f;
    GetMesh()->SetRelativeLocation(FVector(0,0,-76.15f));
    GetMesh()->SetRelativeRotation(FRotator(0,-90,0));
    GetMesh()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    GetMesh()->SetRenderCustomDepth(true);
    GetMesh()->SetCustomDepthStencilValue(1);
    GetMesh()->VisibilityBasedAnimTickOption = EVisibilityBasedAnimTickOption::AlwaysTickPoseAndRefreshBones;
    GetMesh()->bEnableUpdateRateOptimizations = false;
    // The arm stops on solid things only, pulls in fast and eases back out; thin things fade whole (docs/CAMERA.md).
    CameraArm = CreateDefaultSubobject<UJapanCameraArm>(TEXT("FollowArm"));
    CameraArm->SetupAttachment(GetRootComponent());
    CameraArm->TargetOffset = FVector(0,0,35);
    CameraArm->TargetArmLength = 420.f;
    CameraArm->bUsePawnControlRotation = true;
    CameraArm->bEnableCameraLag = true;
    CameraArm->CameraLagSpeed = 14.f;
    CameraArm->CameraLagMaxDistance = 40.f;
    CameraArm->bUseCameraLagSubstepping = true;
    CameraArm->CameraLagMaxTimeStep = 1.f/120.f;
    CameraArm->bEnableCameraRotationLag = false;
    CameraArm->AddTickPrerequisiteComponent(Movement);
    FollowCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("FollowCamera"));
    FollowCamera->SetupAttachment(CameraArm, USpringArmComponent::SocketName);
    FollowCamera->FieldOfView = PreferredFOV;
    SeeThrough = CreateDefaultSubobject<USeeThroughComponent>(TEXT("SeeThrough"));
}

void AWandererCharacter::BeginPlay()
{
    Super::BeginPlay();
    if (FParse::Param(FCommandLine::Get(),TEXT("controllertrace")))
    {
#if WITH_EDITOR
        FSlateApplication::Get().OnApplicationPreInputKeyDownListener().AddWeakLambda(this,[](const FKeyEvent& Event)
        {
            if (Event.GetKey().IsGamepadKey() || Event.GetKey()==EKeys::Escape)
                UE_LOG(LogTemp,Display,TEXT("CONTROLLER TRACE slate key=%s repeat=%d device=%d"),*Event.GetKey().ToString(),Event.IsRepeat(),Event.GetInputDeviceId().GetId());
        });
#endif
        GetWorld()->GetGameViewport()->OnInputKey().AddWeakLambda(this,[](const FInputKeyEventArgs& Event)
        {
            if (Event.Key.IsGamepadKey() || Event.Key==EKeys::Escape)
                UE_LOG(LogTemp,Display,TEXT("CONTROLLER TRACE viewport key=%s event=%d value=%.2f device=%d"),*Event.Key.ToString(),int32(Event.Event),Event.AmountDepressed,Event.InputDevice.GetId());
        });
    }
    if (FAtelierStream::IsRequested()) PhoneInput=MakeShared<FYorimichiPhone>(this);
    Definition = LoadObject<UWandererDefinition>(nullptr,*DefinitionAssetPath);
    if (Definition && Definition->Mesh && Definition->Locomotion && Definition->Crouching)
    {
        GetCharacterMovement()->MaxWalkSpeedCrouched = Definition->CrouchSpeed;
        CameraArm->TargetOffset.Z = Definition->CameraHeight;
        GetMesh()->SetSkeletalMeshAsset(Definition->Mesh);
        GetMesh()->SetAnimInstanceClass(UWandererAnimInstance::StaticClass());
        UE_LOG(LogTemp,Display,TEXT("Character ready: %s, skeletal mesh and %d actions"),*DefinitionAssetPath,Definition->Actions.Num());
        Sword->Initialize(this);
    }
    else UE_LOG(LogTemp,Error,TEXT("Character assets incomplete: %s. Run the matching character importer after building."),*DefinitionAssetPath);
    SkateRide->Initialize(this);
    Preferences = NewObject<UJapanPreferences>(this);
    Preferences->Initialize(this);
    Map = NewObject<UJapanMap>(this);
    Map->Initialize(this);
    bMapReview = FParse::Param(FCommandLine::Get(),TEXT("mapqa"));
    // Countryside ambience under everything (birdsong, breeze, a distant sea); combat sounds sit on top of it. It
    // outlives the character, so a switched-in one keeps it and is ready almost at once.
    if (bSwitchedIn) ReadyTime = 1.3f;
    else if (USoundWave* Ambience = LoadObject<USoundWave>(nullptr, TEXT("/Game/Audio/Combat/ambience_countryside_01.ambience_countryside_01"), nullptr, LOAD_NoWarn | LOAD_Quiet))
        UGameplayStatics::SpawnSound2D(this, Ambience, .5f);
    bSwordReview = FParse::Param(FCommandLine::Get(),TEXT("swordqa"));
    if (FParse::Param(FCommandLine::Get(),TEXT("fightfilm")))
    { FightFilm = CreateFightFilm(this); FApp::SetFixedDeltaTime(1.0/60.0); FApp::SetUseFixedTimeStep(true); }
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        PC->PlayerCameraManager->ViewPitchMin = -65.f;
        PC->PlayerCameraManager->ViewPitchMax = 45.f;
    }
    bSailboatReview=FParse::Param(FCommandLine::Get(),TEXT("sailboatqa"));
    bCairoReview = FParse::Param(FCommandLine::Get(),TEXT("cairoqa"));
    bFixedView = FParse::Param(FCommandLine::Get(),TEXT("fixedview"));
    FParse::Value(FCommandLine::Get(),TEXT("benchmarkview="),BenchmarkView);
    FParse::Value(FCommandLine::Get(),TEXT("trailershot="),TrailerSpecPath);
    FParse::Value(FCommandLine::Get(),TEXT("buildingreview="),BuildingReviewSpecPath);
    // Explicit capture clock: command-line -FPS alone does not set fixed delta.
    if (!TrailerSpecPath.IsEmpty())
    { FApp::SetFixedDeltaTime(1.0/60.0);FApp::SetUseFixedTimeStep(true); }
    FParse::Value(FCommandLine::Get(),TEXT("benchmarkdir="),BenchmarkDirectory);
    FParse::Value(FCommandLine::Get(),TEXT("benchmarkseconds="),BenchmarkSeconds);
    // Up to half an hour so a capped soak can run in the same harness as a 20 s capture.
    BenchmarkSeconds = FMath::Clamp(BenchmarkSeconds,10.f,1800.f);
    if (!BenchmarkView.IsEmpty() || !TrailerSpecPath.IsEmpty())
    {
        bFixedView = true;
        DisableInput(Cast<APlayerController>(Controller));
    }
    if (bCairoReview || bMapReview || bSwordReview || !TrailerSpecPath.IsEmpty())
    {
        FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory);
        if (ReviewDirectory.IsEmpty()) ReviewDirectory = FPaths::ProjectSavedDir()/TEXT("Screenshots/Wanderer")/FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
        IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
    }
    SetMouseReleased(!BenchmarkView.IsEmpty() || !TrailerSpecPath.IsEmpty());
}

void AWandererCharacter::EndPlay(const EEndPlayReason::Type Reason)
{
    PhoneInput.Reset();
    UGameViewportClient::OnScreenshotCaptured().RemoveAll(this);   // review and trailer frame capture
    if (Preferences) Preferences->CloseMenu();
    if (Map) Map->Close();
    if (APlayerController* PC = Cast<APlayerController>(Controller))
        if (ULocalPlayer* LP = PC->GetLocalPlayer())
            if (auto* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
                Subsystem->RemoveMappingContext(Mapping);
    Super::EndPlay(Reason);
}

void AWandererCharacter::EnterWorld(AJapanWorld* World)
{
    Landscape = World;
    if (!World || !World->bLoaded) return;
    Sailboat->Initialize(this,World);
    if (!bSwitchedIn)
    {
        SetActorLocation(World->PlayerStart.GetLocation()+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3.f),false,nullptr,ETeleportType::TeleportPhysics);
        SetActorRotation(World->PlayerStart.Rotator());
        if (Controller) Controller->SetControlRotation(FRotator(-8,World->PlayerStart.Rotator().Yaw,0));
    }
    ReviewForward = GetActorForwardVector();
    if (Preferences) Preferences->Apply();
    if (!bSwitchedIn && FParse::Param(FCommandLine::Get(),TEXT("sworddummy"))) SpawnSwordDummy();
}

void AWandererCharacter::Leave()
{
    if (Preferences) Preferences->CloseMenu();
    if (Map) Map->Close();
    if (Moves) Moves->Reset();
    SkateRide->StowImmediately();
    Sailboat->StowImmediately();
    if (APlayerController* PC = Cast<APlayerController>(Controller))
        if (ULocalPlayer* LP = PC->GetLocalPlayer())
            if (auto* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>())
                Subsystem->RemoveMappingContext(Mapping);
}

void AWandererCharacter::ReturnToSpawn()
{
    if (!bReady || !Landscape || !Landscape->bLoaded) return;
    TravelTo(Landscape->PlayerStart.GetLocation(),Landscape->PlayerStart.Rotator().Yaw,TEXT("spawn"));
    UE_LOG(LogTemp,Display,TEXT("PHONE STREAM returned to spawn"));
}

bool AWandererCharacter::TravelTo(FVector Target, float Yaw, const TCHAR* Reason, float Above)
{
    if (!bReady || !Landscape || !Landscape->bLoaded) return false;
    if(GetZeppelin())GetZeppelin()->Cancel(this);
    auto* Movement = GetCharacterMovement();
    // Leave custom ramp physics before restoring the ordinary character pose.
    Movement->SetMovementMode(MOVE_Falling);
    SkateRide->StowImmediately();
    Sailboat->StowImmediately();
    MoveIntent = FVector2D::ZeroVector;
    bJog = bWalk = bSprintHeld = false;
    JumpBuffer = FallSpeed = SinceGrounded = DashCooldown = RollCooldown = RollBuffer = 0.f; bPendingTakeoff = bGroundJumped = bAirJumpUsed = bAirDashUsed = false;
    if (Sword) Sword->CancelForInterrupt(false);
    StopJumping(); UnCrouch(); SetAction(NAME_None);
    Movement->StopMovementImmediately();
    Movement->ClearAccumulatedForces();
    Movement->CurrentRootMotion.Clear();
    // Land on whatever is actually built there (paving, sand, the island stair, a quay), not on the recorded height.
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(MapTeleport),false,this);
    if (GetWorld()->LineTraceSingleByChannel(Hit,Target+FVector(0,0,Above),Target-FVector(0,0,2500),ECC_Visibility,Params)) Target.Z = Hit.ImpactPoint.Z;
    else { float Ground = 0.f; if (Landscape->SampleGroundHeight(Target,Ground)) Target.Z = Ground; }
    SetActorLocationAndRotation(Target+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3.f),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
    Movement->bForceNextFloorCheck = true;
    if (Moves) Moves->Reset();   // after the move, so a fall is measured from the new place
    bHasSafeCityLocation = bHasSafeCoastLocation = false;
    if (Controller) Controller->SetControlRotation(FRotator(-8,Yaw,0));
    UE_LOG(LogTemp,Display,TEXT("Travelled to %s: (%.0f, %.0f, %.0f) yaw %.0f%s"),Reason,Target.X,Target.Y,Target.Z,Yaw,Hit.bBlockingHit ? TEXT("") : TEXT(" (no ground hit)"));
    return true;
}

void AWandererCharacter::BuildInput()
{
    Mapping = NewObject<UInputMappingContext>(this);
    auto Axis = [&](FName Name, EInputActionValueType Type)
    {
        UInputAction* A = NewObject<UInputAction>(this,Name); A->ValueType = Type; Inputs.Add(Name,A); return A;
    };
    auto Key = [&](UInputAction* Action,FKey K,bool Negate=false,bool YAxis=false)
    {
        FEnhancedActionKeyMapping& M = Mapping->MapKey(Action,K);
        if (Negate) M.Modifiers.Add(NewObject<UInputModifierNegate>(Mapping));
        if (YAxis) { auto* Swizzle = NewObject<UInputModifierSwizzleAxis>(Mapping); Swizzle->Order = EInputAxisSwizzle::YXZ; M.Modifiers.Add(Swizzle); }
    };
    UInputAction* MoveAxis = Axis(TEXT("Move"),EInputActionValueType::Axis2D);
    Key(MoveAxis,EKeys::W,false,true); Key(MoveAxis,EKeys::S,true,true);
    Key(MoveAxis,EKeys::A,true); Key(MoveAxis,EKeys::D);
    Key(MoveAxis,EKeys::Up,false,true); Key(MoveAxis,EKeys::Down,true,true);
    Key(MoveAxis,EKeys::Left,true); Key(MoveAxis,EKeys::Right);
    auto& LeftStick = Mapping->MapKey(MoveAxis,EKeys::Gamepad_Left2D);
    LeftStick.Modifiers.Add(NewObject<UInputModifierDeadZone>(Mapping));
    UInputAction* Mouse = Axis(TEXT("Mouse"),EInputActionValueType::Axis2D);
    Key(Mouse,EKeys::MouseX); Key(Mouse,EKeys::MouseY,false,true);
    auto& RightStick = Mapping->MapKey(Axis(TEXT("Stick"),EInputActionValueType::Axis2D),EKeys::Gamepad_Right2D);
    RightStick.Modifiers.Add(NewObject<UInputModifierDeadZone>(Mapping));
    for (const auto& Pair : TArray<TPair<FName,FKey>>{
        {TEXT("Jog"),EKeys::J},{TEXT("Sprint"),EKeys::LeftShift},{TEXT("Walk"),EKeys::LeftAlt},{TEXT("Jump"),EKeys::SpaceBar},
        {TEXT("Crouch"),EKeys::C},{TEXT("Dodge"),EKeys::LeftControl},{TEXT("Wave"),EKeys::Q},
        {TEXT("Interact"),EKeys::E},{TEXT("Skateboard"),EKeys::B},{TEXT("Dash"),EKeys::F},{TEXT("Sailboat"),EKeys::K},{TEXT("Map"),EKeys::M},{TEXT("Menu"),EKeys::Escape},{TEXT("MouseRelease"),EKeys::Tab},{TEXT("Screenshot"),EKeys::F12},
        {TEXT("FlightSlower"),EKeys::LeftBracket},{TEXT("FlightFaster"),EKeys::RightBracket},
        {TEXT("Attack"),EKeys::LeftMouseButton},{TEXT("Parry"),EKeys::RightMouseButton},{TEXT("Weapon"),EKeys::R}})
        Key(Axis(Pair.Key,EInputActionValueType::Boolean),Pair.Value);
    // The top face button always mounts/steps off; interaction uses D-pad Down.
    Key(Inputs[TEXT("Attack")],EKeys::Gamepad_RightTrigger);
    Key(Inputs[TEXT("Parry")],EKeys::Gamepad_LeftTrigger);
    Key(Inputs[TEXT("Weapon")],EKeys::Gamepad_DPad_Left);
    Key(Inputs[TEXT("Dash")],EKeys::Gamepad_FaceButton_Left);
    Key(Inputs[TEXT("Interact")],EKeys::Gamepad_DPad_Down);
    Key(Inputs[TEXT("Jump")],EKeys::Gamepad_FaceButton_Bottom);
    Key(Inputs[TEXT("Sprint")],EKeys::Gamepad_LeftThumbstick);
    Key(Inputs[TEXT("Dodge")],EKeys::Gamepad_FaceButton_Right);
    Key(Inputs[TEXT("Crouch")],EKeys::Gamepad_RightThumbstick);
    Key(Inputs[TEXT("Map")],EKeys::Gamepad_Special_Left);
    Key(Inputs[TEXT("Menu")],EKeys::Gamepad_Special_Right);
    Key(Inputs[TEXT("Sailboat")],EKeys::Gamepad_DPad_Up);
    Key(Inputs[TEXT("Skateboard")],EKeys::Gamepad_FaceButton_Top);
    // The board button on foot: a board to the hand, or put away (the Ride backend's carry).
    Key(Axis(TEXT("SkateboardHand"),EInputActionValueType::Boolean),EKeys::G);
    Key(Inputs[TEXT("SkateboardHand")],EKeys::Gamepad_DPad_Right);
    Key(Inputs[TEXT("FlightSlower")],EKeys::Gamepad_LeftShoulder);
    Key(Inputs[TEXT("FlightFaster")],EKeys::Gamepad_RightShoulder);
    if (APlayerController* PC = Cast<APlayerController>(Controller))
        if (ULocalPlayer* LP = PC->GetLocalPlayer())
            if (auto* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>()) Subsystem->AddMappingContext(Mapping,0);
}

void AWandererCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input); BuildInput();
    if (auto* E = Cast<UEnhancedInputComponent>(Input))
    {
        for (const auto& Binding : TArray<TPair<FName,void(AWandererCharacter::*)(const FInputActionValue&)>>{
            {TEXT("Move"),&AWandererCharacter::Move},{TEXT("Mouse"),&AWandererCharacter::MouseLook},
            {TEXT("Stick"),&AWandererCharacter::StickLook},{TEXT("Sprint"),&AWandererCharacter::Sprint},{TEXT("Jog"),&AWandererCharacter::Jog},{TEXT("Walk"),&AWandererCharacter::Walk}})
        {
            E->BindAction(Inputs[Binding.Key],ETriggerEvent::Triggered,this,Binding.Value);
            E->BindAction(Inputs[Binding.Key],ETriggerEvent::Completed,this,Binding.Value);
            E->BindAction(Inputs[Binding.Key],ETriggerEvent::Canceled,this,Binding.Value);
        }
        for (const auto& Binding : TArray<TPair<FName,void(AWandererCharacter::*)(const FInputActionValue&)>>{
            {TEXT("Jump"),&AWandererCharacter::RequestJump},{TEXT("Crouch"),&AWandererCharacter::ToggleCrouch},
            {TEXT("Dodge"),&AWandererCharacter::Dodge},{TEXT("Wave"),&AWandererCharacter::Wave},{TEXT("Interact"),&AWandererCharacter::Interact},
            {TEXT("Skateboard"),&AWandererCharacter::ToggleSkateboard},{TEXT("Dash"),&AWandererCharacter::Dash},{TEXT("Sailboat"),&AWandererCharacter::ToggleSailboat},{TEXT("Map"),&AWandererCharacter::ToggleMap},{TEXT("Menu"),&AWandererCharacter::ToggleMenu},{TEXT("MouseRelease"),&AWandererCharacter::ToggleMouse},{TEXT("Screenshot"),&AWandererCharacter::Screenshot},
            {TEXT("FlightSlower"),&AWandererCharacter::FlightSlower},{TEXT("FlightFaster"),&AWandererCharacter::FlightFaster},
            {TEXT("Attack"),&AWandererCharacter::AttackPressed},{TEXT("Parry"),&AWandererCharacter::ParryPressed},{TEXT("Weapon"),&AWandererCharacter::ToggleWeapon}})
            E->BindAction(Inputs[Binding.Key],ETriggerEvent::Started,this,Binding.Value);
        E->BindAction(Inputs[TEXT("SkateboardHand")],ETriggerEvent::Started,this,&AWandererCharacter::SkateboardHand);
        E->BindAction(Inputs[TEXT("Jump")],ETriggerEvent::Completed,this,&AWandererCharacter::ReleaseJump);
        E->BindAction(Inputs[TEXT("Attack")],ETriggerEvent::Completed,this,&AWandererCharacter::AttackReleased);
        E->BindAction(Inputs[TEXT("Attack")],ETriggerEvent::Canceled,this,&AWandererCharacter::AttackReleased);
        E->BindAction(Inputs[TEXT("Parry")],ETriggerEvent::Completed,this,&AWandererCharacter::ParryReleased);
        E->BindAction(Inputs[TEXT("Parry")],ETriggerEvent::Canceled,this,&AWandererCharacter::ParryReleased);
        if (FParse::Param(FCommandLine::Get(),TEXT("controllertrace")))
            for (const auto& Pair : Inputs)
                if (Pair.Value->ValueType==EInputActionValueType::Boolean)
                    for (ETriggerEvent Event : {ETriggerEvent::Started,ETriggerEvent::Completed})
                        E->BindActionValueLambda(Pair.Value,Event,[this,Name=Pair.Key,Event](const FInputActionValue& Value)
                        {
                            UE_LOG(LogTemp,Display,TEXT("CONTROLLER TRACE action=%s event=%d value=%d ready=%d menu=%d locked=%d"),*Name.ToString(),int32(Event),Value.Get<bool>(),bReady,bMenuOpen,MovementLocked());
                        });
    }
}

void AWandererCharacter::Move(const FInputActionValue& V) { MoveIntent = (bMenuOpen || bFixedView) ? FVector2D::ZeroVector : V.Get<FVector2D>(); }
void AWandererCharacter::MouseLook(const FInputActionValue& V)
{
    if (!bReady || bMenuOpen || bMouseReleased || bFixedView) return;
    // Riding: holding the left button turns the mouse into the right stick (Flick-It), not the camera.
    if (SkateRide->IsRiding()) if (const APlayerController* PC = Cast<APlayerController>(Controller); PC && PC->IsInputKeyDown(EKeys::LeftMouseButton)) return;
    const FVector2D Delta = V.Get<FVector2D>()*MouseSensitivity;
    // MouseY is positive upward. Legacy pitch scaling is explicitly disabled in config.
    if(!Delta.IsNearlyZero())LookGrace=2.f;
    AddControllerYawInput(Delta.X); AddControllerPitchInput(Delta.Y);
}
void AWandererCharacter::StickLook(const FInputActionValue& V)
{
    if (!bReady || bMenuOpen || bFixedView || SkateRide->IsRiding()) return;   // riding: the right stick is Flick-It
    const FVector2D Delta = V.Get<FVector2D>()*145.f*GetWorld()->GetDeltaSeconds();
    if(!Delta.IsNearlyZero())LookGrace=2.f;
    // SceneViewport negates Gamepad_RightY. Restore up-is-look-up with legacy scales disabled.
    AddControllerYawInput(Delta.X); AddControllerPitchInput(-Delta.Y);
}
void AWandererCharacter::Sprint(const FInputActionValue& V)
{
    // A sprint pressed on foot with the skateboard takes over from it on the ground, as soon as the skate component lets
    // it while the button is held (only the press: a board taken while sprinting stays in hand).
    const bool bHeld = V.Get<bool>();
    if (bHeld && !bSprintHeld) bSprintTakeOver = true;
    bSprintHeld = bHeld;
    if (bSprintTakeOver && (!bHeld || (bReady && !bMenuOpen && GetCharacterMovement()->IsMovingOnGround() && TakeOverFromSkate(false))))
        bSprintTakeOver = false;
}
void AWandererCharacter::Jog(const FInputActionValue& V) { bJog = V.Get<bool>(); }
void AWandererCharacter::Walk(const FInputActionValue& V) { bWalk = V.Get<bool>(); }
bool AWandererCharacter::IsPhoneTouchActive() const { return PhoneInput && PhoneInput->IsTouchActive(); }
bool AWandererCharacter::IsSkateInputBlocked() const { return bMenuOpen || (Map && Map->IsOpen()); }
FName AWandererCharacter::GetSkateBone(FName Contract) const
{
    const FName* Bone = Definition ? Definition->SkateBones.Find(Contract) : nullptr;
    return Bone ? *Bone : Contract;
}
float AWandererCharacter::GetSkateBoardScale() const { return Definition ? Definition->SkateBoardScale : 1.f; }
void AWandererCharacter::PrepareToSkate()
{
    if (Sword && Sword->IsArmed()) Sword->SetArmed(false);
    if (Moves) Moves->Reset();
    SetAction(NAME_None);
}
bool AWandererCharacter::CanAct(bool bOverBoard) const { return bReady && !bMenuOpen && (!SkateRide->IsRiding() || (bOverBoard && SkateRide->CanYieldToCharacter())) && !Sailboat->IsEquipped() && GetCharacterMovement()->IsMovingOnGround() && !MovementLocked() && !bPendingTakeoff; }
bool AWandererCharacter::TakeOverFromSkate(bool bOwnVelocity)
{
    // The skate component ends a clip where it is and puts a board in hand away; the game's action left from before the
    // clip (a landing the clip played instead) is dropped.
    const bool bClip = SkateRide->IsRiding();
    if (!SkateRide->YieldToCharacter(bOwnVelocity)) return false;
    if (bClip) SetAction(NAME_None);
    return true;
}
bool AWandererCharacter::StandForAction()
{
    UnCrouch();
    // Only a crouched character stands up: CharacterMovement's UnCrouch gives back the class default capsule whenever
    // the capsule differs from it, crouched or not, which would undo a fitted one (a BotW rider's).
    if (bIsCrouched) GetCharacterMovement()->UnCrouch(); // Checks overhead clearance before a standing clip.
    return !bIsCrouched;
}
bool AWandererCharacter::MovementLocked() const
{
    return IsZeppelinPassenger() || (Sword && Sword->LocksMovement()) || (Moves && Moves->LocksMovement()) || AnimationAction == TEXT("Dodge") ||
        (AnimationAction == TEXT("Roll") && !IsRollRecovering()) || AnimationAction == TEXT("HardLand") ||
        AnimationAction == TEXT("DashGround") || AnimationAction == TEXT("DashAir");
}
bool AWandererCharacter::IsRollRecovering() const
{
    // The approved dive-roll has completed its rotation and planted its feet
    // by source second .94. The remaining rise is visual, not a movement lock.
    return AnimationAction==TEXT("Roll") && Definition && Definition->RollDiveTouchdown>0.f &&
        GetActionSourceTime()>=.94f && GetCharacterMovement()->IsMovingOnGround();
}
void AWandererCharacter::RequestJump(const FInputActionValue&)
{
    // Space loads and pops the board (read by the skate component); on foot the jump with the board in hand is the
    // skate component's too, and a double jump takes over from it.
    const bool bSkating = SkateRide->IsRiding();
    if (bSkating && !(GetCharacterMovement()->IsFalling() && SkateRide->CanYieldToCharacter())) return;
    if (Sailboat->IsEquipped()) return;
    if (Moves) { PressMove(TEXT("jump")); return; }
    if (bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(false)) return;   // a draw, sheathe or deflection finishes first
    if (!bReady || bMenuOpen || MovementLocked() || bPendingTakeoff) return;
    UCharacterMovementComponent* M = GetCharacterMovement();
    if (M->IsFalling() && (bGroundJumped || SinceGrounded >= .10f))
    {
        if (bAirJumpUsed || !Definition || !Definition->FindAction(TEXT("DoubleJump")) || !TakeOverFromSkate(true)) return;
        bAirJumpUsed = true;
        JumpBuffer = FallSpeed = 0.f;
        StopJumping();
        FVector LaunchVelocity=M->Velocity;
        if(!MoveIntent.IsNearlyZero())
        {
            const FRotationMatrix Basis(FRotator(0,GetControlRotation().Yaw,0));
            const FVector Direction=(Basis.GetUnitAxis(EAxis::X)*MoveIntent.Y+Basis.GetUnitAxis(EAxis::Y)*MoveIntent.X).GetSafeNormal();
            // Redirect existing speed once at the second press, including a
            // full reversal. Diagonal input adds no speed; neutral keeps XY.
            LaunchVelocity=Direction*LaunchVelocity.Size2D();
            SetActorRotation(Direction.Rotation()); // Face the flip without rotating the camera.
        }
        LaunchVelocity.Z=650.f;
        LaunchCharacter(LaunchVelocity,true,true);
        SetAction(TEXT("DoubleJump"),false,.05f);
        return;
    }
    if (bSkating) return;
    if (!bGroundJumped && !bAirJumpUsed) JumpBuffer = .16f;
}
void AWandererCharacter::ReleaseJump(const FInputActionValue&) { StopJumping(); if (Moves) Moves->Press(TEXT("jump_release")); }
bool AWandererCharacter::PressMove(FName Button)
{
    return Moves && bReady && !bMenuOpen && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger() && Moves->Press(Button);
}
void AWandererCharacter::ToggleSailboat(const FInputActionValue&)
{
    if (!bReady || bMenuOpen || IsZeppelinPassenger() || SkateRide->IsRiding()) return;
    if (Sailboat->IsEquipped()) { Sailboat->Toggle(); return; }
    if (Sword && !Sword->CancelForInterrupt(true)) return;
    if (CanAct() && StandForAction() && Sailboat->Toggle()) { if (Moves) Moves->Reset(); SetAction(NAME_None); JumpBuffer = 0.f; bPendingTakeoff = false; StopJumping(); }
}
void AWandererCharacter::ToggleSkateboard(const FInputActionValue&)
{
    if (SkateRide->IsAvailable())
    {
        if (!bReady || bMenuOpen || IsZeppelinPassenger() || Sailboat->IsEquipped()) return;
        if (SkateRide->IsRiding()) { SkateRide->Toggle(); return; }
        if (Sword && !Sword->CancelForInterrupt(true)) return;
        if (CanAct() && StandForAction() && SkateRide->Toggle()) { SetAction(NAME_None); JumpBuffer = 0.f; bPendingTakeoff = false; StopJumping(); }
        // Mid-jump the board goes under the feet (Ride backend: a caveman).
        else if (bReady && !bMenuOpen && GetCharacterMovement()->IsFalling() && !MovementLocked() && SkateRide->Toggle()) { SetAction(NAME_None); JumpBuffer = 0.f; StopJumping(); }
    }
}
void AWandererCharacter::SkateboardHand(const FInputActionValue&)
{
    if (bReady && !bMenuOpen && SkateRide->IsAvailable() && !SkateRide->IsRiding()) SkateRide->RecallBoard();
}
bool AWandererCharacter::CanCarrySkateBoard() const
{
    // The hands are needed: the sword out, the sail, the zeppelin's rail, swimming, an interaction or a wave.
    return !(Sword && Sword->IsArmed()) && !Sailboat->IsEquipped() && !IsZeppelinPassenger() && !GetCharacterMovement()->IsSwimming() &&
        AnimationAction != TEXT("Interact") && AnimationAction != TEXT("Wave");
}
void AWandererCharacter::ToggleCrouch(const FInputActionValue&)
{
    if (PressMove(TEXT("crouch"))) return;   // gliding, climbing, swimming or busy: no crouch
    if (CanAct()) { if (bIsCrouched) UnCrouch(); else Crouch(); SetAction(NAME_None); }
}
FName AWandererCharacter::GetAnimationClip() const
{
    static const FName WithArmedCopy[] = { TEXT("Roll"), TEXT("DoubleJump"), TEXT("JumpStart"), TEXT("JumpRise"), TEXT("Fall"), TEXT("Land"), TEXT("HardLand"), TEXT("DashAir"), TEXT("DashGround"),
        TEXT("SitDown"), TEXT("SitIdle"), TEXT("StandUp") };
    if (Sword && Sword->IsArmed() && Definition && Algo::Find(WithArmedCopy, AnimationAction))
    {
        const FName Armed(*(TEXT("Sword") + AnimationAction.ToString()));
        if (Definition->FindAction(Armed)) return Armed;
    }
    return AnimationAction;
}

bool AWandererCharacter::Live_Press(FName Button)
{
    if (Button == TEXT("jump")) RequestJump(FInputActionValue(true));
    else if (Button == TEXT("jump_release")) ReleaseJump(FInputActionValue(false));
    else if (Button == TEXT("roll")) Dodge(FInputActionValue(true));
    else if (Button == TEXT("crouch")) ToggleCrouch(FInputActionValue(true));
    else if (Button == TEXT("interact")) Interact(FInputActionValue(true));
    else if (Button == TEXT("stop_previous")) ZeppelinStep(-1);
    else if (Button == TEXT("stop_next")) ZeppelinStep(1);
    else if (Button == TEXT("dodge")) Dodge(FInputActionValue(true));
    else if (Button == TEXT("dash")) Dash(FInputActionValue(true));
    else if (Button == TEXT("attack")) AttackPressed(FInputActionValue(true));
    else if (Button == TEXT("attack_release")) AttackReleased(FInputActionValue(false));
    else if (Button == TEXT("guard")) ParryPressed(FInputActionValue(true));
    else if (Button == TEXT("guard_release")) ParryReleased(FInputActionValue(false));
    else if (Button == TEXT("weapon")) ToggleWeapon(FInputActionValue(true));
    else return false;
    return true;
}

void AWandererCharacter::Dodge(const FInputActionValue&)
{
    if (SkateRide->IsRiding() && !SkateRide->CanYieldToCharacter()) return;   // on foot the roll takes over from the board
    if (Moves) { if (SkateRide->IsRiding() && !TakeOverFromSkate(true)) return; PressMove(TEXT("dodge")); return; }   // the side hop or backflip
    // With an armed roll (game-r16) the sword stays in hand; without one, rolling tucks it away and the next attack draws it.
    if(bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(!(Definition && Definition->FindAction(TEXT("SwordRoll"))))) return;
    if(!CanAct(true))
    {
        // A press near the end of the tuck can chain at the first supported
        // frame. Earlier presses expire rather than queuing an eventual roll.
        if(bReady && !bMenuOpen && AnimationAction==TEXT("Roll") && Definition && Definition->RollDiveTouchdown>0.f)
            RollBuffer=.18f;
        return;
    }
    if (RollCooldown>0.f || !StandForAction() || !TakeOverFromSkate(true)) return;
    RollBuffer=0.f;
    const bool bRoll=Definition && Definition->FindAction(TEXT("Roll")) && !Definition->RollProfile.IsEmpty();
    const bool bChaining=bRoll && IsRollRecovering();
    auto* Movement=GetCharacterMovement();
    const float EntrySpeed=Movement->Velocity.Size2D();
    const bool bMovingRoll=bRoll && EntrySpeed>40.f;
    const FRotationMatrix Basis(FRotator(0,GetControlRotation().Yaw,0));
    DodgeDirection = (Basis.GetUnitAxis(EAxis::X)*MoveIntent.Y+Basis.GetUnitAxis(EAxis::Y)*MoveIntent.X).GetSafeNormal();
    if (DodgeDirection.IsNearlyZero()) DodgeDirection = GetActorForwardVector();
    JumpBuffer=0.f;
    if(bChaining)Movement->RemoveRootMotionSource(TEXT("GroundRoll"));
    SetActorRotation(DodgeDirection.Rotation()); SetAction(bRoll?TEXT("Roll"):TEXT("Dodge"),false,bMovingRoll?.035f:.045f,bChaining);
    if(bRoll && Definition->RollDiveTouchdown>0.f)
    {
        ActionPlayRate=1.15f;
        ActionDuration/=ActionPlayRate;
    }
    if(bMovingRoll && Definition->RollDiveTouchdown<=0.f)
    {
        // Enter the existing clothed clip at its compression pose. A runner
        // already has forward momentum and does not need the standing wind-up.
        const float SourceDuration=ActionDuration;
        ActionSourceStartTime=SourceDuration*(.10f/.85f);
        ActionPlayRate=1.4f;
        ActionDuration=(SourceDuration*(.80f/.85f)-ActionSourceStartTime)/ActionPlayRate;
    }
    // Current dive rolls can repeat as soon as their movement lock releases.
    if(bRoll)RollCooldown=Definition->RollDiveTouchdown>0.f?0.f:ActionDuration+.15f;
    TSharedPtr<FRootMotionSource_ConstantForce> Source = MakeShared<FRootMotionSource_ConstantForce>();
    Source->InstanceName = bRoll?TEXT("GroundRoll"):TEXT("DodgeStep"); Source->Priority = 500;
    Source->AccumulateMode = ERootMotionAccumulateMode::Override;
    Source->Force = DodgeDirection*(bRoll?1.f:420.f); Source->Duration = ActionDuration;
    Source->StrengthOverTime = NewObject<UCurveFloat>(this);
    if(bRoll)
    {
        if(bMovingRoll || ActionPlayRate!=1.f)
        {
            FRichCurve AuthoredSpeed;
            for(const FVector2D& Key:Definition->RollProfile)AuthoredSpeed.AddKey(Key.X,Key.Y);
            const int32 Samples=FMath::CeilToInt(ActionDuration*60.f);
            for(int32 I=0;I<=Samples;++I)
            {
                const float U=float(I)/Samples;
                const float Time=ActionSourceStartTime+U*ActionDuration*ActionPlayRate;
                const float Speed=FMath::Max(bMovingRoll?EntrySpeed:0.f,AuthoredSpeed.Eval(Time)*ActionPlayRate);
                Source->StrengthOverTime->FloatCurve.AddKey(U,Speed);
            }
        }
        else for(const FVector2D& Key:Definition->RollProfile)
            Source->StrengthOverTime->FloatCurve.AddKey(Key.X/ActionDuration,Key.Y);
        // A roll that leaves a ledge must continue falling normally.
        Source->Settings.SetFlag(ERootMotionSourceSettingsFlags::IgnoreZAccumulate);
    }
    else for (int32 I = 0; I <= 16; ++I) Source->StrengthOverTime->FloatCurve.AddKey(I/16.f,FMath::Sin(PI*I/16.f));
    Source->FinishVelocityParams.Mode = bMovingRoll?ERootMotionFinishVelocityMode::MaintainLastRootMotionVelocity:ERootMotionFinishVelocityMode::ClampVelocity;
    Source->FinishVelocityParams.ClampVelocity = bRoll?20.f:80.f;
    GetCharacterMovement()->ApplyRootMotionSource(Source);
    if(AYorimichiCombatFX* FX=AYorimichiCombatFX::Get(this))
    {
        const FVector Ground=GetActorLocation()-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
        FX->Dust(Ground,.8f,-DodgeDirection*.4f); FX->Play(TEXT("dash"),Ground,.75f,.06f);
    }
}
void AWandererCharacter::Review_Dodge() { Dodge(FInputActionValue(true)); }
void AWandererCharacter::Dash(const FInputActionValue&)
{
    if (SkateRide->IsRiding() && !SkateRide->CanYieldToCharacter()) return;   // on foot the dash takes over from the board
    if (Moves) { if (SkateRide->IsRiding() && !TakeOverFromSkate(true)) return; PressMove(TEXT("dash")); return; }   // no air dash; the swimming dash
    if (bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(false)) return;
    if (!bReady || bMenuOpen || !Definition || MovementLocked() || bPendingTakeoff || Sailboat->IsEquipped() || DashCooldown>0.f) return;
    auto* M=GetCharacterMovement();
    const bool Air=M->IsFalling();
    if ((!Air && !M->IsMovingOnGround()) || (Air && bAirDashUsed) ||
        (AnimationAction==TEXT("DoubleJump") && ActionTime<.6f)) return;
    const auto& Profile=Air?Definition->AirDashProfile:Definition->GroundDashProfile;
    const FName Name=Air?TEXT("DashAir"):TEXT("DashGround");
    if (Profile.IsEmpty() || !Definition->FindAction(Name) || !StandForAction() || !TakeOverFromSkate(true)) return;
    if (Air) bAirDashUsed=true;
    DashCooldown=1.f;
    SetAction(Name,false,.025f);
    if(AYorimichiCombatFX* FX=AYorimichiCombatFX::Get(this))
    {
        const FVector Ground=GetActorLocation()-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
        if(!Air) FX->Dust(Ground,.7f,-GetActorForwardVector()*.5f);
        FX->Play(TEXT("dash"),GetActorLocation(),.8f,.06f);
    }
    // Profiles are in cm/s. The root stays in place in the animation; the
    // movement component sweeps the capsule against actual world collision.
    TSharedPtr<FRootMotionSource> Source;
    if (Air)
    {
        auto Burst=MakeShared<FRootMotionSource_ConstantForce>();
        Burst->Force=GetActorForwardVector();
        Burst->StrengthOverTime=NewObject<UCurveFloat>(this);
        for (const FVector2D& Key : Profile)
            Burst->StrengthOverTime->FloatCurve.AddKey(Key.X/ActionDuration,Key.Y);
        Source=Burst;
    }
    else
    {
        // A real capsule leap, rather than grounded strides or a pelvis-only
        // lift. JumpForce sweeps world collision and supplies both X and Z.
        auto Leap=MakeShared<FRootMotionSource_JumpForce>();
        Leap->Rotation=GetActorRotation(); Leap->Height=32.f;
        FRichCurve Speed;
        for (const FVector2D& Key : Profile)Speed.AddKey(Key.X,Key.Y);
        Leap->TimeMappingCurve=NewObject<UCurveFloat>(this);
        constexpr int32 Samples=84;
        float Distance=0.f;TArray<float> Travel;Travel.Add(0.f);
        const float Step=ActionDuration/Samples;
        for(int32 I=1;I<=Samples;++I)
        {
            Distance+=(Speed.Eval((I-1)*Step)+Speed.Eval(I*Step))*.5f*Step;
            Travel.Add(Distance);
        }
        Leap->Distance=Distance;
        for(int32 I=0;I<=Samples;++I)
            Leap->TimeMappingCurve->FloatCurve.AddKey(float(I)/Samples,Travel[I]/Distance);
        Source=Leap;
        M->SetMovementMode(MOVE_Falling);
        bGroundJumped=true;
    }
    Source->InstanceName=TEXT("ForwardDash"); Source->Priority=600;
    Source->AccumulateMode=ERootMotionAccumulateMode::Override;
    Source->Duration=ActionDuration;
    Source->FinishVelocityParams.Mode=ERootMotionFinishVelocityMode::SetVelocity;
    Source->FinishVelocityParams.SetVelocity=GetActorForwardVector()*Definition->RunSpeed;
    M->ApplyRootMotionSource(Source);
    // Neither dash consumes nor restores the separate double-jump allowance.
}
void AWandererCharacter::Wave(const FInputActionValue&) { if (SkateRide->IsRiding()) return; if (Sword && !Sword->CancelForInterrupt(true)) return; if (CanAct() && StandForAction()) SetAction(TEXT("Wave")); }
void AWandererCharacter::AttackPressed(const FInputActionValue&)
{
    if (Moves) { PressMove(TEXT("attack")); return; }
    if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->AttackPressed();
}
void AWandererCharacter::AttackReleased(const FInputActionValue&) { if (Moves) Moves->Press(TEXT("attack_release")); else if (Sword) Sword->AttackReleased(); }
void AWandererCharacter::ParryPressed(const FInputActionValue&)
{
    if (Moves) { PressMove(TEXT("guard")); return; }   // the shield guard and the lock-on, held
    if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->ParryPressed();
}
void AWandererCharacter::ParryReleased(const FInputActionValue&) { if (Moves) Moves->Press(TEXT("guard_release")); }
void AWandererCharacter::ToggleWeapon(const FInputActionValue&)
{
    if (Moves) { PressMove(TEXT("weapon")); return; }
    if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->ToggleWeapon();
}
void AWandererCharacter::FlightSlower(const FInputActionValue&) { ZeppelinStep(-1); }
void AWandererCharacter::FlightFaster(const FInputActionValue&) { ZeppelinStep(1); }
// Aboard, the two flight buttons change the ride's speed; at a docked ship they choose its next stop.
void AWandererCharacter::ZeppelinStep(int32 Direction)
{
    if(!GetZeppelin())return;
    if(IsZeppelinPassenger())GetZeppelin()->AdjustFlightSpeed(Direction);
    else if(bReady&&!bMenuOpen)GetZeppelin()->ChooseDestination(this,Direction);
}
void AWandererCharacter::Interact(const FInputActionValue&) { if(SkateRide->IsRiding())return; if(bReady&&!bMenuOpen&&Sword&&!Sword->CancelForInterrupt(true))return; if(bReady&&!bMenuOpen&&GetZeppelin()&&GetZeppelin()->TryInteract(this))return; if (CanAct() && StandForAction()) SetAction(TEXT("Interact")); }
void AWandererCharacter::ToggleMenu(const FInputActionValue&)
{
    if (!bReady) return;
    if (Map && Map->IsOpen()) { Map->Close(); return; }
    if (Preferences) Preferences->ToggleMenu();
}
void AWandererCharacter::ToggleMap(const FInputActionValue&)
{
    if (!bReady || !Map || bCinematic) return;
    if (Map->IsOpen()) Map->Close();
    else if (!bMenuOpen) Map->Open();     // not over the settings menu
}
void AWandererCharacter::ToggleMouse(const FInputActionValue&) { if (!bMenuOpen) SetMouseReleased(!bMouseReleased); }
void AWandererCharacter::Screenshot(const FInputActionValue&)
{
    const FString File = FPaths::ProjectSavedDir()/TEXT("Screenshots")/(TEXT("Wanderer_")+FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"))+TEXT(".png"));
    FScreenshotRequest::RequestScreenshot(File,false,false);
}
void AWandererCharacter::SetMenuOpen(bool bOpen)
{
    bMenuOpen = bOpen; MoveIntent = FVector2D::ZeroVector; bJog = bWalk = bSprintHeld = false;
    if (bOpen)
    {
        if (Sword) { Sword->CancelForInterrupt(false); Sword->DropAttackHold(); }   // a held charge must not survive the menu, and must not fire
        if (Moves) Moves->DropHolds();
        JumpBuffer = RollBuffer = 0.f;
        if (bPendingTakeoff) { bPendingTakeoff = false; SetAction(NAME_None); }
    }
    SetMouseReleased(bOpen);
}
void AWandererCharacter::SetMouseReleased(bool bReleased)
{
    bMouseReleased = bReleased;
    if (APlayerController* PC = Cast<APlayerController>(Controller))
    {
        // An offscreen run never captures or locks the mouse (see Yorimichi.cpp).
        if (FParse::Param(FCommandLine::Get(), TEXT("RenderOffscreen")))
        {
            PC->bShowMouseCursor = false;
            FInputModeGameAndUI Mode; Mode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock); Mode.SetHideCursorDuringCapture(false);
            PC->SetInputMode(Mode);
            if (GEngine && GEngine->GameViewport) GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
            return;
        }
        PC->bShowMouseCursor = bReleased;
        if (bReleased) { FInputModeGameAndUI Mode; Mode.SetHideCursorDuringCapture(false); PC->SetInputMode(Mode); }
        else { FInputModeGameOnly Mode; Mode.SetConsumeCaptureMouseDown(false); PC->SetInputMode(Mode); }
    }
}
void AWandererCharacter::ApplyCameraPreferences(float Sensitivity,float Distance,float FieldOfView)
{ MouseSensitivity = Sensitivity; PreferredArmLength = Distance; if(Sailboat)Sailboat->SetCameraDistance(Distance);else CameraArm->TargetArmLength = Distance; PreferredFOV = FieldOfView; if(IsZeppelinPassenger())GetZeppelin()->SetPassengerCameraDistance(Distance); }

void AWandererCharacter::SetAction(FName Action,bool bLoop,float BlendSeconds,bool bRestart)
{
    if (Action == AnimationAction && !bRestart) return;
    if (!Action.IsNone() && (!Definition || !Definition->FindAction(Action))) return;
    AnimationAction = Action; bActionLoops = bLoop; ActionTime = 0; ActionBlendTime = BlendSeconds; ++ActionSerial;
    ActionSourceStartTime=0.f;ActionPlayRate=1.f;
    if(Action!=TEXT("Roll"))RollBuffer=0.f;
    ActionDuration = Action.IsNone() ? 0.f : Definition->FindAction(Action)->GetPlayLength();
    UE_LOG(LogTemp,Verbose,TEXT("Wanderer action %s"),*Action.ToString());
}
void AWandererCharacter::AdvanceAction(float Dt)
{
    UCharacterMovementComponent* M = GetCharacterMovement();
    DashCooldown=FMath::Max(0.f,DashCooldown-Dt);
    RollCooldown=FMath::Max(0.f,RollCooldown-Dt);
    RollBuffer=FMath::Max(0.f,RollBuffer-Dt);
    SinceGrounded = M->IsMovingOnGround() ? 0.f : SinceGrounded+Dt;
    if (JumpBuffer > 0 && SinceGrounded < .10f && !MovementLocked() && !bPendingTakeoff && !bGroundJumped && !bAirJumpUsed)
    {
        JumpBuffer = 0;
        if (StandForAction()) { SetAction(TEXT("JumpStart"),false,.07f); bPendingTakeoff = true; }
    }
    JumpBuffer = FMath::Max(0.f,JumpBuffer-Dt);
    const float PreviousSourceTime=GetActionSourceTime();
    ActionTime += Dt;
    // Release the direction-forcing source as well as the input lock. Merely
    // unlocking input would still push the character along the old heading.
    if(IsRollRecovering())
    {
        if(RollBuffer>0.f)
        {
            Dodge(FInputActionValue(true));
            // A same-action restart resets the source clock. Do not process
            // the old roll's markers or erase the new motion source below.
            if(ActionTime==0.f)return;
        }
        M->RemoveRootMotionSource(TEXT("GroundRoll"));
        if(MoveIntent.IsNearlyZero())M->StopMovementImmediately();
    }
    if(AnimationAction==TEXT("Roll") && Definition->RollDiveTouchdown>Definition->RollDiveTakeoff &&
        PreviousSourceTime<Definition->RollDiveTakeoff && GetActionSourceTime()>=Definition->RollDiveTakeoff && M->IsMovingOnGround())
    {
        // A shallow ballistic dive; the horizontal override sweeps collision
        // independently and does not suppress gravity. The same clip continues
        // across touchdown into its shoulder/back roll.
        const float Flight=(Definition->RollDiveTouchdown-Definition->RollDiveTakeoff)/ActionPlayRate;
        LaunchCharacter(FVector(0,0,-M->GetGravityZ()*Flight*.5f),false,true);
        bGroundJumped=true;
    }
    if (AnimationAction == TEXT("JumpStart") && bPendingTakeoff && ActionTime >= (Definition->UseAuthoredMovement?ActionDuration:.06f))
    {
        bPendingTakeoff = false; bGroundJumped = true;
        // Launch after a short anticipation without stopping movement. A short grace window also works at a ledge.
        LaunchCharacter(FVector(0,0,M->JumpZVelocity),false,true);
        SetAction(TEXT("JumpRise"),false,.09f);
    }
    else if (M->IsFalling() && AnimationAction != TEXT("JumpStart"))
    {
        if(AnimationAction==TEXT("Roll") && GetActionSourceTime()>Definition->RollDiveTouchdown+.10f)
        {
            M->RemoveRootMotionSource(TEXT("GroundRoll"));
            if(Definition->RollDiveTouchdown>0.f)SetAction(TEXT("Fall"),true,.12f);
        }
        FallSpeed = M->Velocity.Z > 0.f ? 0.f : FMath::Max(FallSpeed,-M->Velocity.Z);
        // Do not replace the somersault at its apex; it opens upright before ending.
        if ((AnimationAction != TEXT("DoubleJump") && AnimationAction != TEXT("DashAir") && AnimationAction != TEXT("DashGround") && AnimationAction != TEXT("Roll")) || ActionTime >= ActionDuration)
        {
            if (M->Velocity.Z <= 0) SetAction(TEXT("Fall"),true,.12f);
            else if (AnimationAction != TEXT("JumpRise")) SetAction(TEXT("JumpRise"));
        }
    }
    else if (!AnimationAction.IsNone() && !bActionLoops && ActionTime >= ActionDuration && !(Sword && Sword->OwnsAction(AnimationAction)))
        SetAction(NAME_None,false,AnimationAction==TEXT("Roll")?.10f:.16f);
    if ((AnimationAction == TEXT("Wave") || AnimationAction == TEXT("Interact") || AnimationAction == TEXT("Land")) && !MoveIntent.IsNearlyZero()) SetAction(NAME_None);
}
/** Opt-in native regression scenario. Runs real boat ticks at 60 Hz; no settings are saved.
 * Covers launch, motion, stopping, deep-water exit refusal, a blocking hull fixture,
 * a real shoreline landing and forced teleport cleanup. Phone transport is tested separately. */
void AWandererCharacter::AdvanceSailboatReview(float Dt)
{
    auto Check=[&](bool Pass,const FString& Name)
    {
        ++SailboatReviewChecks;
        UE_LOG(LogTemp,Display,TEXT("SAILBOAT QA %s: %s"),Pass?TEXT("PASS"):TEXT("FAIL"),*Name);
        if(!Pass)SailboatReviewErrors.Add(Name);
    };
    if(SailboatReviewStep<0)
    {
        SailboatReviewStep=0;
        SailboatReviewInitialMesh=GetMesh()->GetRelativeTransform();
        if(ReviewDirectory.IsEmpty())FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory);
        if(ReviewDirectory.IsEmpty())ReviewDirectory=FPaths::ProjectSavedDir()/TEXT("Screenshots/SailboatQA");
        IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
        FApp::SetFixedDeltaTime(1./60.);FApp::SetUseFixedTimeStep(true);
        FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        SailboatTelemetry=TEXT("time,step,equipped,speed,sail,x,y,z,yaw,right_wrist_target_cm,status\n");
        UE_LOG(LogTemp,Display,TEXT("SAILBOAT QA START"));
    }
    static const float Durations[]={2,2,6,2,3,1,3,2,2,2,2,1,4,1,1,2,2,2,3,2,1,3,3};
    const bool Enter=!bSailboatReviewEntered;
    if(Enter){bSailboatReviewEntered=true;SailboatReviewAnchor=GetActorLocation();SailboatReviewYaw=GetActorRotation().Yaw;}
    MoveIntent=FVector2D::ZeroVector;
    switch(SailboatReviewStep)
    {
    case 0:
        if(Enter)Check(TravelTo(AJapanWorld::ToUE(-216,-169,1.6),80,TEXT("sailboat QA shore")),TEXT("shore setup"));
        break;
    case 1:
        if(Enter)
        {
            Check(GetCharacterMovement()->IsMovingOnGround(),TEXT("grounded before launch"));
            ToggleSailboat(FInputActionValue(true));
            Check(Sailboat->IsEquipped(),TEXT("launch from mainland beach"));
            SailboatReviewLaunch=GetActorLocation();SailboatReviewLaunchYaw=GetActorRotation().Yaw;
        }
        break;
    case 2:MoveIntent.Y=1;break;
    case 3:MoveIntent.X=-1;break;
    case 4:MoveIntent.X=1;break;
    case 5:break; // releasing Raise keeps the sail up
    case 6:MoveIntent.Y=-1;break;
    case 7:
        if(Enter)
        {
            Sailboat->EmergencyStop();
            SetActorLocationAndRotation(AJapanWorld::ToUE(-104,-258,0)+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),FRotator(0,90,0),false,nullptr,ETeleportType::TeleportPhysics);
            // Update the attachment before querying potential landing points.
            Sailboat->TickComponent(0,LEVELTICK_All,nullptr);
            Check(!Sailboat->Toggle()&&Sailboat->IsEquipped(),TEXT("deep-water disembark rejected"));
        }
        MoveIntent.Y=1;break;
    case 8:if(Enter)SetMenuOpen(true);break;
    case 9:if(Enter)SetMenuOpen(false);MoveIntent.Y=1;break;
    case 10:
        if(Enter){ToggleMap(FInputActionValue(true));Check(Map&&Map->IsOpen(),TEXT("map opened while sailing"));}
        break;
    case 11:
        if(Enter){if(Map&&Map->IsOpen())Map->Close();Sailboat->EmergencyStop();Check(Sailboat->GetSpeed()<.01&&Sailboat->GetRideVelocity().IsNearlyZero(),TEXT("emergency stop clears propulsion"));}
        break;
    case 12:
        if(Enter)
        {
            // An isolated test-only wall exercises swept HULL collision, wider than the rider capsule.
            SailboatReviewObstacle=GetWorld()->SpawnActor<AActor>();
            auto* Box=NewObject<UBoxComponent>(SailboatReviewObstacle,TEXT("SailboatQAWall"));
            SailboatReviewObstacle->SetRootComponent(Box);Box->SetBoxExtent(FVector(20,450,200));
            Box->SetCollisionProfileName(TEXT("BlockAll"));Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);Box->RegisterComponent();
            const FVector Center=GetActorLocation()+GetActorForwardVector()*115-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
            SailboatReviewObstacle->SetActorLocationAndRotation(Center+GetActorForwardVector()*550+FVector(0,0,100),GetActorRotation());
        }
        MoveIntent.Y=1;break;
    case 13:
        if(Enter)
        {
            if(SailboatReviewObstacle){SailboatReviewObstacle->Destroy();SailboatReviewObstacle=nullptr;}
            Sailboat->EmergencyStop();
            SetActorLocationAndRotation(SailboatReviewLaunch,FRotator(0,SailboatReviewLaunchYaw,0),false,nullptr,ETeleportType::TeleportPhysics);
            Sailboat->TickComponent(0,LEVELTICK_All,nullptr);
            Check(Sailboat->Toggle()&&!Sailboat->IsEquipped(),TEXT("disembark onto original shoreline"));
        }
        break;
    case 14:break;
    case 15:
        if(Enter){ToggleSailboat(FInputActionValue(true));Check(Sailboat->IsEquipped(),TEXT("relaunch after disembarking"));}
        MoveIntent.Y=1;break;
    case 16:
        if(Enter)
        {
            ReturnToSpawn();Check(!Sailboat->IsEquipped()&&Sailboat->GetSpeed()<.01,TEXT("spawn forces boat stow"));
            Check(GetCharacterMovement()->Velocity.IsNearlyZero(),TEXT("spawn clears momentum"));
            Check(GetMesh()->GetRelativeTransform().Equals(SailboatReviewInitialMesh,.1),TEXT("spawn restores initial character mesh transform"));
        }
        break;
    case 17:case 19:
        if(Enter)
        {
            TravelTo(AJapanWorld::ToUE(-216,-169,1.6),80,TEXT("recovery QA shore"));
            Check(!bHasSafeCoastLocation&&!bHasSafeCityLocation,TEXT("travel invalidates both water checkpoints"));
        }
        break;
    case 20:
        if(Enter){ToggleSkateboard(FInputActionValue(true));Check(SkateRide->IsRiding(),TEXT("skate equipped for water recovery"));}
        break;
    case 18:case 21:case 22:
        if(Enter)
        {
            if(SailboatReviewStep==22)
            {
                // Explicit no-checkpoint fixture exercises the first-fall fallback, on foot (step 21 ends back on the board).
                SkateRide->StowImmediately();
                bHasSafeCoastLocation=bHasSafeCityLocation=false;
                SailboatReviewRecoveryTarget=Landscape->PlayerStart.GetLocation();
            }
            else
            {
                Check(bHasSafeCoastLocation,TEXT("shore checkpoint recorded before water fall"));
                SailboatReviewRecoveryTarget=LastSafeCoastLocation;
            }
            // Start ABOVE the actual non-colliding water. Let ordinary gravity cross the threshold.
            bSailboatReviewObservedFall=false;
            if(SailboatReviewStep==21&&SkateRide->IsRiding())
            {
                // The board owns the rider's position: set it down above the water and let it roll off into the sea.
                SkateRide->PlaceAt(AJapanWorld::ToUE(-104,-258,2.0),80.f);SkateRide->Launch(FVector(130,40,0));
            }
            else
            {
                SetActorLocation(AJapanWorld::ToUE(-104,-258,2.0)+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),false,nullptr,ETeleportType::TeleportPhysics);
                GetCharacterMovement()->SetMovementMode(MOVE_Falling);
                GetCharacterMovement()->Velocity=FVector(130,40,0);
            }
            FallSpeed=1400;JumpBuffer=.2f;
            if(SailboatReviewStep==18)
            {
                auto Force=MakeShared<FRootMotionSource_ConstantForce>();Force->InstanceName=TEXT("RecoveryQAForce");Force->Duration=10;Force->Force=FVector(60,0,0);
                // Default Override replaces Z with zero and suspends the pawn above water.
                // An additive horizontal fixture preserves gravity while still requiring cleanup.
                Force->AccumulateMode=ERootMotionAccumulateMode::Additive;
                GetCharacterMovement()->ApplyRootMotionSource(Force);
            }
        }
        break;
    }
    SailboatReviewTime+=Dt;SailboatReviewElapsed+=Dt;
    const FVector P=GetActorLocation();
    if((SailboatReviewStep==18||SailboatReviewStep==21||SailboatReviewStep==22)
        &&FVector::Dist2D(P,AJapanWorld::ToUE(-104,-258,0))<2000
        &&P.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight()<0
        &&GetCharacterMovement()->Velocity.Z<0)bSailboatReviewObservedFall=true;
    SailboatTelemetry+=FString::Printf(TEXT("%.3f,%d,%d,%.2f,%.3f,%.2f,%.2f,%.2f,%.2f,%.3f,%s\n"),SailboatReviewTime,SailboatReviewStep,Sailboat->IsEquipped(),Sailboat->GetSpeed(),Sailboat->GetSailAmount(),P.X,P.Y,P.Z,GetActorRotation().Yaw,Sailboat->IsEquipped()?FVector::Dist(GetMesh()->GetSocketLocation(TEXT("hand_R")),Sailboat->HandPoint(1)):0.,*Sailboat->GetStatus());
    // Actual gameplay pose, rear chase and unobscured side views. No generated image edits.
    const bool Side=SailboatReviewStep==3||SailboatReviewStep==5||SailboatReviewStep==6;
    const bool Helm=SailboatReviewStep==4||SailboatReviewStep==5;
    const FVector Aim=Sailboat->IsEquipped()?Sailboat->PosePoint(Helm?FVector(-110,0,75):FVector(0,0,160)):P+FVector(0,0,45);
    // Opposite side of the boom, close enough to judge both hands, thighs and seat contact.
    const FVector Eye=Aim+GetActorForwardVector()*(Helm?190:Side?-120:-720)+GetActorRightVector()*(Helm?-330:Side?850:400)+FVector(0,0,Helm?115:230);
    FollowCamera->SetWorldLocationAndRotation(Eye,(Aim-Eye).Rotation());
    if(!bSailboatReviewShot&&SailboatReviewElapsed>Durations[SailboatReviewStep]-.35f)
    {
        bSailboatReviewShot=true;
        if(SailboatReviewStep==1||SailboatReviewStep==2||SailboatReviewStep==3||SailboatReviewStep==4||SailboatReviewStep==5||SailboatReviewStep==6||SailboatReviewStep==13)
            FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("sailboat_%02d_%s.png"),SailboatReviewStep,Helm?TEXT("helm"):Side?TEXT("side"):TEXT("rear")),false,false);
    }
    if(SailboatReviewElapsed<Durations[SailboatReviewStep])return;
    switch(SailboatReviewStep)
    {
    case 1:Check(Sailboat->GetSpeed()<.1,TEXT("launch starts stopped"));break;
    case 2:Check(Sailboat->GetSpeed()>550,TEXT("raise accelerates to cruising speed"));Check(FVector::Dist2D(P,SailboatReviewAnchor)>1300,TEXT("boat advances over water"));break;
    case 3:Check(FRotator::NormalizeAxis(GetActorRotation().Yaw-SailboatReviewYaw)<-25,TEXT("left steering changes heading"));break;
    case 4:Check(FRotator::NormalizeAxis(GetActorRotation().Yaw-SailboatReviewYaw)>35,TEXT("right steering changes heading"));break;
    case 5:Check(Sailboat->GetSpeed()>500,TEXT("released raise retains sail propulsion"));break;
    case 6:Check(Sailboat->GetSpeed()<.1&&Sailboat->GetSailAmount()<.01,TEXT("lower sail stops boat"));break;
    case 8:Check(Sailboat->GetSpeed()<.1&&FVector::Dist2D(P,SailboatReviewAnchor)<15,TEXT("menu stops translation"));break;
    case 9:Check(Sailboat->GetSpeed()>150,TEXT("sailing resumes after menu"));break;
    case 10:Check(Sailboat->GetSpeed()<.1&&FVector::Dist2D(P,SailboatReviewAnchor)<15,TEXT("map stops translation"));break;
    case 11:Check(Sailboat->GetSpeed()<.1&&FVector::Dist2D(P,SailboatReviewAnchor)<2,TEXT("emergency stop remains stopped"));break;
    case 12:Check(Sailboat->GetSpeed()<5,TEXT("hull collision stops propulsion"));Check(FVector::Dist2D(P,SailboatReviewAnchor)>150&&FVector::Dist2D(P,SailboatReviewAnchor)<345,TEXT("hull sweep stops before wall"));break;
    case 14:Check(!Sailboat->IsEquipped()&&GetCharacterMovement()->IsMovingOnGround(),TEXT("shore exit settles grounded"));break;
    case 16:Check(GetCharacterMovement()->IsMovingOnGround(),TEXT("spawn settles grounded"));break;
    case 17:case 19:Check(GetCharacterMovement()->IsMovingOnGround()&&bHasSafeCoastLocation,TEXT("recovery shoreline settled and cached"));break;
    case 18:case 21:case 22:
        {
            const FString Mode=SailboatReviewStep==18?TEXT("on foot"):SailboatReviewStep==21?TEXT("skating"):TEXT("without checkpoint");
            Check(bSailboatReviewObservedFall,TEXT("water fall crosses sea surface under gravity: ")+Mode);
            Check(FVector::Dist2D(P,SailboatReviewRecoveryTarget)<100,TEXT("water recovery returns safely: ")+Mode);
            // Riding into the sea puts the rider back on the board at the last dry spot (the board's own movement mode).
            if(SailboatReviewStep==21)Check(SkateRide->IsRiding()&&SkateRide->GetMode()==ESkateMode::Ground,TEXT("water recovery puts the rider back on the board: ")+Mode);
            else Check(GetCharacterMovement()->IsMovingOnGround(),TEXT("water recovery grounded: ")+Mode);
            Check(!Sailboat->IsEquipped(),TEXT("water recovery stows equipment: ")+Mode);
            Check(GetCharacterMovement()->Velocity.Size2D()<.1&&FallSpeed<.1&&JumpBuffer<.01&&!bPendingTakeoff,TEXT("water recovery clears momentum and fall state: ")+Mode);
            Check(!GetCharacterMovement()->CurrentRootMotion.HasActiveRootMotionSources(),TEXT("water recovery clears root motion: ")+Mode);
            if(SailboatReviewStep!=21)Check(GetMesh()->GetRelativeTransform().Equals(SailboatReviewInitialMesh,.1),TEXT("water recovery restores mesh: ")+Mode);
        }
        break;
    }
    ++SailboatReviewStep;SailboatReviewElapsed=0;bSailboatReviewEntered=false;bSailboatReviewShot=false;
    if(SailboatReviewStep<UE_ARRAY_COUNT(Durations))return;
    MoveIntent=FVector2D::ZeroVector;
    auto Result=MakeShared<FJsonObject>();Result->SetBoolField(TEXT("passed"),SailboatReviewErrors.IsEmpty());Result->SetNumberField(TEXT("checks"),SailboatReviewChecks);Result->SetNumberField(TEXT("seconds"),SailboatReviewTime);
    TArray<TSharedPtr<FJsonValue>> Errors;for(const FString& E:SailboatReviewErrors)Errors.Add(MakeShared<FJsonValueString>(E));Result->SetArrayField(TEXT("errors"),Errors);
    FString JSON;auto Writer=TJsonWriterFactory<>::Create(&JSON);FJsonSerializer::Serialize(Result,Writer);
    FFileHelper::SaveStringToFile(JSON,*(ReviewDirectory/TEXT("results.json")));
    FFileHelper::SaveStringToFile(SailboatTelemetry,*(ReviewDirectory/TEXT("telemetry.csv")));
    UE_LOG(LogTemp,Display,TEXT("SAILBOAT QA COMPLETE: %d checks, %d failures"),SailboatReviewChecks,SailboatReviewErrors.Num());
    bSailboatReview=false;FPlatformMisc::RequestExit(false);
}
void AWandererCharacter::RecordFrame()
{
    // Frames are JPG like the village film; -framestride=N keeps one frame in N (a rehearsal at 60 is one every two seconds)
    static int32 Stride = -1; if (Stride < 0) { Stride = 1; FParse::Value(FCommandLine::Get(),TEXT("framestride="),Stride); Stride = FMath::Max(1,Stride); }
    if (ReviewDirectory.IsEmpty()) { FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory); if (ReviewDirectory.IsEmpty()) ReviewDirectory = FPaths::ProjectSavedDir()/TEXT("Screenshots/Demo")/FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S")); IFileManager::Get().MakeDirectory(*ReviewDirectory,true); }
    const int32 Index = DemoFrame++;
    if (Index % Stride == 0) FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("frame_%05d.jpg"),Index),false,false);
}
/** Ground demo: spawn, road, the lane through the fishing village, a wave at the coconut stand, the sailboat crossing with
 *  to the island landing, a cut to the last stretch of the stairway, the temple, a slow orbit. */
/** Flyover: a detached camera along keyframes with look targets, easing per segment. */
void AWandererCharacter::Landed(const FHitResult& Hit)
{
    Super::Landed(Hit);
    if (SkateRide->GetMode() != ESkateMode::Off) { FallSpeed = 0.f; return; }   // a bail: the skate component plays the fall
    bPendingTakeoff = bGroundJumped = bAirJumpUsed = bAirDashUsed = false;
    GetCharacterMovement()->RemoveRootMotionSource(TEXT("ForwardDash"));
    SinceGrounded = 0.f;
    if (Sailboat->IsEquipped()) { FallSpeed = 0.f; return; }
    if (Moves) { Moves->Landed(Hit); FallSpeed = 0.f; return; }   // the move set plays the landing and the footsteps
    // The drop decides how hard the landing reads, before FallSpeed is cleared below.
    if (Footsteps) Footsteps->Land(Hit,FMath::GetMappedRangeValueClamped(FVector2f(200.f,1100.f),FVector2f(.55f,1.4f),FallSpeed));
    if (AnimationAction==TEXT("Roll") && ActionTime<ActionDuration) { FallSpeed=0.f; return; }
    SetAction(FallSpeed > 900.f ? TEXT("HardLand") : TEXT("Land"),false,.07f);
    FallSpeed = 0;
}
void AWandererCharacter::Tick(float Dt)
{
    Super::Tick(Dt);
    if (!Definition || !Landscape || !Landscape->bLoaded) return;
    if(!BuildingReviewSpecPath.IsEmpty())
    {
        ReadyTime+=Dt;if(ReadyTime>1.5f){bReady=true;AdvanceBuildingReview(Dt);}return;
    }
    if(Landscape->bForestLakeLoaded && !Sailboat->IsEquipped() && !Moves)
    {
        const FVector Relative=GetActorLocation()-Landscape->ForestLakeCenter;
        const double X=Relative.X/Landscape->ForestLakeRadii.X;
        const double Y=-Relative.Y/Landscape->ForestLakeRadii.Y;
        const double Angle=FMath::Atan2(Y,X);
        const double Shore=1.+.045*FMath::Sin(3.*Angle)+.035*FMath::Cos(5.*Angle);
        const double Feet=GetActorLocation().Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        if(X*X+Y*Y<Shore*Shore && Feet<Landscape->ForestLakeCenter.Z-45.)
        {
            TravelTo(Landscape->ForestLakeSafeShore,GetActorRotation().Yaw,TEXT("woodland lake shore"));
            UE_LOG(LogTemp,Display,TEXT("Woodland lake water recovery"));
        }
    }
    if(!Sailboat->IsEquipped() && GetActorLocation().X<=30000. && (!Moves || SkateRide->IsRiding()))
    {
        const FVector Here=GetActorLocation();
        const float Feet=Here.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        if(Feet<-100.f && Here.Y>4000.f)
        {
            // Riding into the sea (off the skate pier) puts him back on the board at the last dry spot.
            const bool bWasSkating=SkateRide->IsRiding();
            if(bHasSafeCoastLocation)
                TravelTo(LastSafeCoastLocation-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()),GetActorRotation().Yaw,TEXT("coastal water recovery"));
            else ReturnToSpawn();
            if(bWasSkating)bRemountSkate=true;
            UE_LOG(LogTemp,Display,TEXT("Coastal water recovery"));
        }
        else if(Feet>5.f && (GetCharacterMovement()->IsMovingOnGround() || (SkateRide->GetMode()==ESkateMode::Ground && SkateRide->GetSpeed()<900.f)))
        {LastSafeCoastLocation=Here-FVector(0,0,SkateRide->IsRiding()?20.f:0.f);bHasSafeCoastLocation=true;}
    }
    if(!Sailboat->IsEquipped() && Landscape->bHidamariLoaded && GetActorLocation().X>30000.)
    {
        const FVector Here=GetActorLocation();
        const double X=Here.X/100.,Y=-Here.Y/100.;
        const double Feet=Here.Z-GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        const bool Pond=FMath::Square((X-1030.)/46.)+FMath::Square((Y-284.)/32.)<1.;
        // Match the lower street profile at the canal; the bridge remains well
        // above this threshold and does not trigger recovery.
        const bool Canal=FMath::Abs(X-848.)<7.8 && Y>-130. && Y<-5.;
        const double CanalBank=Y<-98.?2.4+(Y+133.)*.8/35.:Y<-82.?3.2:3.2+(Y+82.)*6.8/89.;
        const bool Water=(Pond && Feet<2880.) || (Canal && Feet<(CanalBank-1.7)*100.) || Feet<-100.;
        if(Water)
        {
            // Recorded checkpoints are capsule centres; TravelTo accepts a floor point.
            const FVector Safe=bHasSafeCityLocation?LastSafeCityLocation-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()):AJapanWorld::ToUE(410,140,21.);
            TravelTo(Safe,GetActorRotation().Yaw,TEXT("Hidamari water recovery"));
            UE_LOG(LogTemp,Display,TEXT("Hidamari water recovery"));
        }
        else if(GetCharacterMovement()->IsMovingOnGround())
        {LastSafeCityLocation=Here;bHasSafeCityLocation=true;}
    }
    if(bRemountSkate && GetCharacterMovement()->IsMovingOnGround()){bRemountSkate=false;if(!SkateRide->IsRiding())SkateRide->Toggle();}
    ReadyTime += Dt;
    if (!bReady) { bReady = ReadyTime > 1.5f; if (bReady && IsPlayerControlled())
    {
        // Live bridge teleports go through the game's own travel (stows the board or boat, settles the camera).
        AtelierLive::SetTeleport([](APawn* Pawn, const FVector& Ground, float Yaw)
        { AWandererCharacter* Player = Cast<AWandererCharacter>(Pawn); return Player && Player->TravelTo(Ground, Yaw, TEXT("live")); });
        AtelierLive::Start(GetWorld());
    }
    return; }
    if (bCairoReview) AdvanceCairoReview(Dt);
    if (bSailboatReview) AdvanceSailboatReview(Dt);
    if (bMapReview) AdvanceMapReview(Dt);
    if (bSwordReview) AdvanceSwordReview(Dt);
    if (!BenchmarkView.IsEmpty()) AdvanceBenchmark(Dt);
    if (!TrailerSpecPath.IsEmpty()) AdvanceTrailer(Dt);
    if (PhoneInput) PhoneInput->Tick(Dt);
    if(IsZeppelinPassenger()){Stamina.Tick(Dt,false,false,bMenuOpen);return;}
    Sailboat->SetInput(MoveIntent,bMenuOpen || (Map && Map->IsOpen()));
    if (!Sailboat->IsEquipped() && !SkateRide->IsRiding())   // keep state time aligned while settings are open
    {
        if (Moves) Moves->Advance(Dt);
        else { if (Sword) Sword->Advance(Dt); AdvanceAction(Dt); }
    }
    UCharacterMovementComponent* M = GetCharacterMovement();
    LookGrace=FMath::Max(0.f,LookGrace-Dt);
    // Skating: the camera swings in behind the line of travel unless the player looked around in the last two seconds.
    float SkateYaw=0.f;
    // Riding, the camera comes lower and a little closer behind the board (skate. framing).
    const float PreviousSkateCamera=SkateCameraBlend;
    SkateCameraBlend=FMath::FInterpTo(SkateCameraBlend,SkateRide->IsRiding()&&SkateRide->IsOnBoard()?1.f:0.f,Dt,3.f);
    if(SkateCameraBlend<.002f)SkateCameraBlend=0.f;
    // Written only while blending in or out (the last write restores the walking framing).
    if((SkateCameraBlend>0.f||PreviousSkateCamera>0.f)&&Definition&&!Sailboat->IsEquipped()&&!IsZeppelinPassenger())
    {
        CameraArm->TargetOffset.Z=Definition->CameraHeight-20.f*SkateCameraBlend;
        if(PreferredArmLength>0.f)CameraArm->TargetArmLength=PreferredArmLength*(1.f-.22f*SkateCameraBlend);
    }
    if(SkateRide->IsRiding()&&Controller&&!bMenuOpen&&LookGrace<=0&&SkateRide->GetCameraYaw(SkateYaw))
    {
        const FRotator Now=Controller->GetControlRotation();
        Controller->SetControlRotation(FMath::RInterpTo(Now,FRotator(-8.f,SkateYaw,0),Dt,2.4f));
    }
    const bool CanSprint=!bWalk&&!bJog&&!bIsCrouched&&!MovementLocked()&&!SkateRide->IsRiding()&&!Sailboat->IsEquipped()&&!MoveIntent.IsNearlyZero()&&M->Velocity.Size2D()>40.f&&(!Moves||Moves->CanSprint());
    // A move set spends stamina itself (climbing, gliding, swimming, a charge) and refills it only on foot.
    Stamina.Tick(Dt,bSprintHeld,CanSprint,bMenuOpen||(Moves&&Moves->HoldsStamina()));
    M->MaxWalkSpeed = Definition->UseAuthoredMovement
        ? ((bWalk || bJog) ? Definition->WalkSpeed : Stamina.Sprinting ? GetSprintSpeed() : Definition->RunSpeed)
        : bWalk ? Definition->WalkSpeed : Definition->RunSpeed*(bJog?1.f:Stamina.Sprinting?2.5f:2.f);
    if (Moves) M->MaxWalkSpeed = Moves->GetMaxWalkSpeed(M->MaxWalkSpeed);   // lock-on strafing
    if (!bMenuOpen && !MovementLocked() && !Sailboat->IsEquipped() && !SkateRide->IsRiding())
    {
        const FRotationMatrix Basis(FRotator(0,GetControlRotation().Yaw,0));
        if (!BenchmarkView.IsEmpty() || !TrailerSpecPath.IsEmpty()) AddMovementInput(ReviewForward,MoveIntent.Y);
        else
        {
            AddMovementInput(Basis.GetUnitAxis(EAxis::X),MoveIntent.Y);
            AddMovementInput(Basis.GetUnitAxis(EAxis::Y),MoveIntent.X);
        }
    }
    // Riding fast widens the view a little (up to 9 degrees at 45 km/h).
    const float SkateFOV=SkateRide->IsRiding()?9.f*FMath::Clamp((SkateRide->GetSpeed()-500.f)/750.f,0.f,1.f):0.f;
    FollowCamera->SetFieldOfView(FMath::FInterpTo(FollowCamera->FieldOfView,PreferredFOV+SkateFOV+(!bWalk && !bJog && !SkateRide->IsRiding() && M->Velocity.Size2D()>Definition->JogSpeed+30.f ? 3.f : 0.f),Dt,5.f));
    // Combat camera shake: smooth noise scaled by trauma squared, decaying in real time (hit-stop freezes this actor's clock).
    {
        const float Real=FApp::GetDeltaTime();
        ShakeTrauma=FMath::Max(0.f,ShakeTrauma-1.9f*Real); DamageFlash=FMath::Max(0.f,DamageFlash-2.6f*Real); ShakeClock+=Real;
        if(FollowCamera->GetAttachParent()==CameraArm)
        {
            FVector Offset; FRotator Rotation; SampleShake(Offset,Rotation);
            FollowCamera->SetRelativeLocation(Offset); FollowCamera->SetRelativeRotation(Rotation);
        }
    }
    if(FightFilm) AdvanceFightFilm(*FightFilm,Dt);
}

void AWandererCharacter::CalcCamera(float DeltaTime, FMinimalViewInfo& OutResult)
{
    Super::CalcCamera(DeltaTime,OutResult);
    FTransform Camera; float FOV=0;
    const bool bBoard=SkateRide && SkateRide->GetRetailCamera(Camera,FOV);
    if (bBoard)
    {
        BoardCamera.Location=Camera.GetLocation(); BoardCamera.Rotation=Camera.Rotator();
        // Session publishes the vertical FOV used by its Bevy host. UE expects horizontal FOV.
        int32 Width=16,Height=9;
        if (APlayerController* PC=Cast<APlayerController>(Controller)) PC->GetViewportSize(Width,Height);
        const float Aspect=Height>0?float(Width)/Height:16.f/9.f;
        BoardCamera.FOV=FMath::RadiansToDegrees(2.f*FMath::Atan(FMath::Tan(FMath::DegreesToRadians(FOV)*.5f)*Aspect));
    }
    // Ease between the follow camera and the native skating camera over about 0.6 s when mounting, stepping off,
    // or looking around with the right stick, instead of cutting between them.
    const bool bWantBoard=bBoard && !bFixedView && LookGrace<=0;
    BoardCameraBlend=bFixedView?0.f:FMath::FInterpConstantTo(BoardCameraBlend,bWantBoard?1.f:0.f,DeltaTime,1.7f);
    if (BoardCameraBlend>0.f)
    {
        const float A=FMath::SmoothStep(0.f,1.f,BoardCameraBlend);
        OutResult.Location=FMath::Lerp(OutResult.Location,BoardCamera.Location,A);
        OutResult.Rotation=FQuat::Slerp(OutResult.Rotation.Quaternion(),BoardCamera.Rotation.Quaternion(),A).Rotator();
        OutResult.FOV=FMath::Lerp(OutResult.FOV,BoardCamera.FOV,A);
    }
}

void AWandererCharacter::SampleShake(FVector& Offset,FRotator& Rotation) const
{
    const float A=ShakeTrauma*ShakeTrauma,F=23.f;
    Offset=FVector(0.f,FMath::PerlinNoise1D(ShakeClock*F)*9.f,FMath::PerlinNoise1D(ShakeClock*F+41.3f)*7.f)*A;
    Rotation=FRotator(FMath::PerlinNoise1D(ShakeClock*F+7.1f)*2.2f,FMath::PerlinNoise1D(ShakeClock*F+19.7f)*2.2f,FMath::PerlinNoise1D(ShakeClock*F+3.3f)*3.f)*A;
}


void AWandererCharacter::AdvanceMapReview(float Dt)
{
    if (!Map || !Map->IsLoaded()) { UE_LOG(LogTemp,Error,TEXT("MAP QA: map not loaded")); FPlatformMisc::RequestExit(false); return; }
    const TArray<FJapanMapZone>& Zones = Map->GetZones();
    const float StepSeconds = 2.5f;
    MapReviewTime += Dt;
    const int32 Step = FMath::FloorToInt(MapReviewTime/StepSeconds);
    const float InStep = MapReviewTime-Step*StepSeconds;
    if (Step != MapReviewStep)
    {
        // Settle the previous zone: where did we actually end up, and are we standing?
        if (MapReviewStep >= 0 && MapReviewStep < Zones.Num())
        {
            const auto& Z = Zones[MapReviewStep];
            const FVector P = GetActorLocation()-FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
            MapTelemetry += FString::Printf(TEXT("{\"zone\":\"%s\",\"name\":\"%s\",\"target\":[%.1f,%.1f,%.1f],\"landed\":[%.1f,%.1f,%.1f],\"drift_cm\":%.1f,\"drop_cm\":%.1f,\"on_ground\":%s,\"speed\":%.1f},\n"),
                *Z.Key,*Z.Name,Z.Location.X,Z.Location.Y,Z.Location.Z,P.X,P.Y,P.Z,FVector::Dist2D(P,Z.Location),Z.Location.Z-P.Z,GetCharacterMovement()->IsMovingOnGround() ? TEXT("true") : TEXT("false"),GetVelocity().Size());
        }
        MapReviewStep = Step;
        if (Step < Zones.Num()) Map->TeleportToZone(Zones[Step].Key);
        else if (Step == Zones.Num()) { Map->TeleportToZone(TEXT("hamlet")); Map->Open(); }
        else
        {
            Map->Close();
            FString Json = TEXT("[\n")+MapTelemetry; Json.RemoveFromEnd(TEXT(",\n")); Json += TEXT("\n]\n");
            FFileHelper::SaveStringToFile(Json,*(ReviewDirectory/TEXT("map_qa.json")),FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
            UE_LOG(LogTemp,Display,TEXT("MAP QA COMPLETE: %d zones -> %s"),Zones.Num(),*ReviewDirectory);
            FPlatformMisc::RequestExit(false);
        }
    }
    if (InStep >= 1.6f && InStep-Dt < 1.6f)
    {
        if (Step < Zones.Num()) FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("map_%02d_%s.png"),Step,*Zones[Step].Key),false,false);
        else if (Step == Zones.Num()) FScreenshotRequest::RequestScreenshot(ReviewDirectory/TEXT("map_overlay.png"),true,false);
    }
}

AZeppelinService* AWandererCharacter::GetZeppelin() const { return Landscape?Landscape->Zeppelin.Get():nullptr; }
bool AWandererCharacter::IsZeppelinPassenger() const { return GetZeppelin()&&GetZeppelin()->IsPassenger(this); }
