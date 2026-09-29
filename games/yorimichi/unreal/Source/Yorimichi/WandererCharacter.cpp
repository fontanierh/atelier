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
    CameraArm = CreateDefaultSubobject<USpringArmComponent>(TEXT("FollowArm"));
    CameraArm->SetupAttachment(GetRootComponent());
    CameraArm->TargetOffset = FVector(0,0,35);
    CameraArm->TargetArmLength = 420.f;
    CameraArm->bUsePawnControlRotation = true;
    CameraArm->ProbeSize = 12.f;
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
    // Countryside ambience under everything (birdsong, breeze, a distant sea); combat sounds sit on top of it.
    if (USoundWave* Ambience = LoadObject<USoundWave>(nullptr, TEXT("/Game/Audio/Combat/ambience_countryside_01.ambience_countryside_01"), nullptr, LOAD_NoWarn | LOAD_Quiet))
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
    bSouthwestDemo=FParse::Param(FCommandLine::Get(),TEXT("southwestdemo"));
    bSouthwestFly=FParse::Param(FCommandLine::Get(),TEXT("southwestfly"));
    if (bSouthwestDemo || bSouthwestFly) { bCinematic = true; int32 DemoFps = 60; FParse::Value(FCommandLine::Get(),TEXT("demofps="),DemoFps); FApp::SetFixedDeltaTime(1.0/FMath::Clamp(DemoFps,10,120)); FApp::SetUseFixedTimeStep(true); }
    bGroundContactReview=FParse::Param(FCommandLine::Get(),TEXT("groundcontactqa"));
    bWarmReview = FParse::Param(FCommandLine::Get(),TEXT("warmqa"));
    bJumpReview = FParse::Param(FCommandLine::Get(),TEXT("jumpqa"));
    bLocomotionReview = FParse::Param(FCommandLine::Get(),TEXT("locomotionqa")) || FParse::Param(FCommandLine::Get(),TEXT("locomotionvideo"));
    bRecordReview = FParse::Param(FCommandLine::Get(),TEXT("wanderervideo")) || FParse::Param(FCommandLine::Get(),TEXT("locomotionvideo"));
    bReview = bJumpReview || bGroundContactReview || bLocomotionReview || bRecordReview || FParse::Param(FCommandLine::Get(),TEXT("wandererqa"));
    bWorldReview = FParse::Param(FCommandLine::Get(),TEXT("worldshots"));
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
    if (bWarmReview || bGroundContactReview || bReview || bMapReview || bSwordReview || !TrailerSpecPath.IsEmpty())
    {
        FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory);
        if (ReviewDirectory.IsEmpty()) ReviewDirectory = FPaths::ProjectSavedDir()/TEXT("Screenshots/Wanderer")/FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
        IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
    }
    if (bGroundContactReview) GetMesh()->RegisterOnBoneTransformsFinalizedDelegate(FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this,&AWandererCharacter::RecordGroundContactPose));
    if (bLocomotionReview) GetMesh()->RegisterOnBoneTransformsFinalizedDelegate(FOnBoneTransformsFinalizedMultiCast::FDelegate::CreateUObject(this,&AWandererCharacter::RecordLocomotionPose));
    SetMouseReleased(bReview || !BenchmarkView.IsEmpty() || !TrailerSpecPath.IsEmpty());
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
    SetActorLocation(World->PlayerStart.GetLocation()+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3.f),false,nullptr,ETeleportType::TeleportPhysics);
    SetActorRotation(World->PlayerStart.Rotator());
    ReviewForward = GetActorForwardVector();
    if (Controller) Controller->SetControlRotation(FRotator(-8,World->PlayerStart.Rotator().Yaw,0));
    if (Preferences) Preferences->Apply();
    if (FParse::Param(FCommandLine::Get(),TEXT("sworddummy"))) SpawnSwordDummy();
}

void AWandererCharacter::ReturnToSpawn()
{
    if (!bReady || !Landscape || !Landscape->bLoaded) return;
    TravelTo(Landscape->PlayerStart.GetLocation(),Landscape->PlayerStart.Rotator().Yaw,TEXT("spawn"));
    UE_LOG(LogTemp,Display,TEXT("PHONE STREAM returned to spawn"));
}

bool AWandererCharacter::TravelTo(FVector Target, float Yaw, const TCHAR* Reason)
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
    if (GetWorld()->LineTraceSingleByChannel(Hit,Target+FVector(0,0,2500),Target-FVector(0,0,2500),ECC_Visibility,Params)) Target.Z = Hit.ImpactPoint.Z;
    else { float Ground = 0.f; if (Landscape->SampleGroundHeight(Target,Ground)) Target.Z = Ground; }
    SetActorLocationAndRotation(Target+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3.f),FRotator(0,Yaw,0),false,nullptr,ETeleportType::TeleportPhysics);
    Movement->bForceNextFloorCheck = true;
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
    // Triggers and D-pad Left are free on every pad; face buttons, sticks and shoulders keep their existing roles.
    Key(Inputs[TEXT("Attack")],EKeys::Gamepad_RightTrigger);
    Key(Inputs[TEXT("Parry")],EKeys::Gamepad_LeftTrigger);
    Key(Inputs[TEXT("Weapon")],EKeys::Gamepad_DPad_Left);
    Key(Inputs[TEXT("Dash")],EKeys::Gamepad_FaceButton_Left);
    Key(Inputs[TEXT("Interact")],EKeys::Gamepad_FaceButton_Top);
    Key(Inputs[TEXT("Jump")],EKeys::Gamepad_FaceButton_Bottom);
    Key(Inputs[TEXT("Sprint")],EKeys::Gamepad_LeftThumbstick);
    Key(Inputs[TEXT("Dodge")],EKeys::Gamepad_FaceButton_Right);
    Key(Inputs[TEXT("Crouch")],EKeys::Gamepad_RightThumbstick);
    Key(Inputs[TEXT("Map")],EKeys::Gamepad_Special_Left);
    Key(Inputs[TEXT("Menu")],EKeys::Gamepad_Special_Right);
    Key(Inputs[TEXT("Sailboat")],EKeys::Gamepad_DPad_Up);
    Key(Inputs[TEXT("Skateboard")],EKeys::Gamepad_DPad_Down);
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
        E->BindAction(Inputs[TEXT("Jump")],ETriggerEvent::Completed,this,&AWandererCharacter::ReleaseJump);
        E->BindAction(Inputs[TEXT("Attack")],ETriggerEvent::Completed,this,&AWandererCharacter::AttackReleased);
        E->BindAction(Inputs[TEXT("Attack")],ETriggerEvent::Canceled,this,&AWandererCharacter::AttackReleased);
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

void AWandererCharacter::Move(const FInputActionValue& V) { MoveIntent = (bMenuOpen || bFixedView || (bReview && !bLocomotionReview)) ? FVector2D::ZeroVector : V.Get<FVector2D>(); }
void AWandererCharacter::MouseLook(const FInputActionValue& V)
{
    if (!bReady || bMenuOpen || bMouseReleased || bFixedView || (bReview && ReviewStep != 0)) return;
    // Riding: holding the left button turns the mouse into the right stick (Flick-It), not the camera.
    if (SkateRide->IsRiding()) if (const APlayerController* PC = Cast<APlayerController>(Controller); PC && PC->IsInputKeyDown(EKeys::LeftMouseButton)) return;
    const FVector2D Delta = V.Get<FVector2D>()*MouseSensitivity;
    // MouseY is positive upward. Legacy pitch scaling is explicitly disabled in config.
    if(!Delta.IsNearlyZero())LookGrace=2.f;
    AddControllerYawInput(Delta.X); AddControllerPitchInput(Delta.Y);
}
void AWandererCharacter::StickLook(const FInputActionValue& V)
{
    if (!bReady || bMenuOpen || bFixedView || bReview || SkateRide->IsRiding()) return;   // riding: the right stick is Flick-It
    const FVector2D Delta = V.Get<FVector2D>()*145.f*GetWorld()->GetDeltaSeconds();
    if(!Delta.IsNearlyZero())LookGrace=2.f;
    // SceneViewport negates Gamepad_RightY. Restore up-is-look-up with legacy scales disabled.
    AddControllerYawInput(Delta.X); AddControllerPitchInput(-Delta.Y);
}
void AWandererCharacter::Sprint(const FInputActionValue& V) { bSprintHeld = V.Get<bool>(); }
void AWandererCharacter::Jog(const FInputActionValue& V) { bJog = V.Get<bool>(); }
void AWandererCharacter::Walk(const FInputActionValue& V) { bWalk = V.Get<bool>(); }
bool AWandererCharacter::IsPhoneTouchActive() const { return PhoneInput && PhoneInput->IsTouchActive(); }
bool AWandererCharacter::IsSkateInputBlocked() const { return bMenuOpen || (Map && Map->IsOpen()); }
UAnimSequence* AWandererCharacter::FindSkateClip(FName Role) const
{
    if (!Definition) return nullptr;
    if (const TObjectPtr<UAnimSequence>* Clip = Definition->SkateActions.Find(Role)) if (*Clip) return *Clip;
    return Definition->FindAction(Role);
}
void AWandererCharacter::PrepareToSkate()
{
    if (Sword && Sword->IsArmed()) Sword->SetArmed(false);
    SetAction(NAME_None);
}
bool AWandererCharacter::CanAct() const { return bReady && !bMenuOpen && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && GetCharacterMovement()->IsMovingOnGround() && !MovementLocked() && !bPendingTakeoff; }
bool AWandererCharacter::StandForAction()
{
    UnCrouch();
    GetCharacterMovement()->UnCrouch(); // Checks overhead clearance before a standing clip.
    return !bIsCrouched;
}
bool AWandererCharacter::MovementLocked() const
{
    return IsZeppelinPassenger() || (Sword && Sword->LocksMovement()) || AnimationAction == TEXT("Dodge") ||
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
    if (SkateRide->IsRiding()) return;   // Space loads and pops the board (read by the skate component)
    if (Sailboat->IsEquipped()) return;
    if (bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(false)) return;   // a draw, sheathe or deflection finishes first
    if (!bReady || bMenuOpen || MovementLocked() || bPendingTakeoff) return;
    UCharacterMovementComponent* M = GetCharacterMovement();
    if (M->IsFalling() && (bGroundJumped || SinceGrounded >= .10f))
    {
        if (bAirJumpUsed || !Definition || !Definition->FindAction(TEXT("DoubleJump"))) return;
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
    if (!bGroundJumped && !bAirJumpUsed) JumpBuffer = .16f;
}
void AWandererCharacter::ReleaseJump(const FInputActionValue&) { StopJumping(); }
void AWandererCharacter::ToggleSailboat(const FInputActionValue&)
{
    if (!bReady || bMenuOpen || IsZeppelinPassenger() || SkateRide->IsRiding()) return;
    if (Sailboat->IsEquipped()) { Sailboat->Toggle(); return; }
    if (Sword && !Sword->CancelForInterrupt(true)) return;
    if (CanAct() && StandForAction() && Sailboat->Toggle()) { SetAction(NAME_None); JumpBuffer = 0.f; bPendingTakeoff = false; StopJumping(); }
}
void AWandererCharacter::ToggleSkateboard(const FInputActionValue&)
{
    if (SkateRide->IsAvailable())
    {
        if (!bReady || bMenuOpen || IsZeppelinPassenger() || Sailboat->IsEquipped()) return;
        if (SkateRide->IsRiding()) { SkateRide->Toggle(); return; }
        if (Sword && !Sword->CancelForInterrupt(true)) return;
        if (CanAct() && StandForAction() && SkateRide->Toggle()) { SetAction(NAME_None); JumpBuffer = 0.f; bPendingTakeoff = false; StopJumping(); }
    }
}
void AWandererCharacter::ToggleCrouch(const FInputActionValue&)
{
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
    else return false;
    return true;
}

void AWandererCharacter::Dodge(const FInputActionValue&)
{
    if (SkateRide->IsRiding()) return;
    // With an armed roll (game-r16) the sword stays in hand; without one, rolling tucks it away and the next attack draws it.
    if(bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(!(Definition && Definition->FindAction(TEXT("SwordRoll"))))) return;
    if(!CanAct())
    {
        // A press near the end of the tuck can chain at the first supported
        // frame. Earlier presses expire rather than queuing an eventual roll.
        if(bReady && !bMenuOpen && AnimationAction==TEXT("Roll") && Definition && Definition->RollDiveTouchdown>0.f)
            RollBuffer=.18f;
        return;
    }
    if (RollCooldown>0.f || !StandForAction()) return;
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
    if (SkateRide->IsRiding()) return;
    if (bReady && !bMenuOpen && Sword && !Sword->CancelForInterrupt(false)) return;
    if (!bReady || bMenuOpen || !Definition || MovementLocked() || bPendingTakeoff || Sailboat->IsEquipped() || DashCooldown>0.f) return;
    auto* M=GetCharacterMovement();
    const bool Air=M->IsFalling();
    if ((!Air && !M->IsMovingOnGround()) || (Air && bAirDashUsed) ||
        (AnimationAction==TEXT("DoubleJump") && ActionTime<.6f)) return;
    const auto& Profile=Air?Definition->AirDashProfile:Definition->GroundDashProfile;
    const FName Name=Air?TEXT("DashAir"):TEXT("DashGround");
    if (Profile.IsEmpty() || !Definition->FindAction(Name) || !StandForAction()) return;
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
void AWandererCharacter::AttackPressed(const FInputActionValue&) { if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->AttackPressed(); }
void AWandererCharacter::AttackReleased(const FInputActionValue&) { if (Sword) Sword->AttackReleased(); }
void AWandererCharacter::ParryPressed(const FInputActionValue&) { if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->ParryPressed(); }
void AWandererCharacter::ToggleWeapon(const FInputActionValue&) { if (Sword && !SkateRide->IsRiding() && !Sailboat->IsEquipped() && !IsZeppelinPassenger()) Sword->ToggleWeapon(); }
void AWandererCharacter::FlightSlower(const FInputActionValue&) { if(IsZeppelinPassenger())GetZeppelin()->AdjustFlightSpeed(-1); }
void AWandererCharacter::FlightFaster(const FInputActionValue&) { if(IsZeppelinPassenger())GetZeppelin()->AdjustFlightSpeed(1); }
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
bool AWandererCharacter::LoadSouthwestData()
{
    FString Text; const FString Path = AtelierDataPath(TEXT("world.json"));
    if (!FFileHelper::LoadFileToString(Text,*Path)) return false;
    TSharedPtr<FJsonObject> Root; auto Reader = TJsonReaderFactory<>::Create(Text);
    if (!FJsonSerializer::Deserialize(Reader,Root) || !Root.IsValid()) return false;
    const TSharedPtr<FJsonObject>* SW = nullptr; if (!Root->TryGetObjectField(TEXT("southwest"),SW)) return false;
    auto Points = [&](const TCHAR* Key, TArray<FVector>& Out){ const TArray<TSharedPtr<FJsonValue>>* A=nullptr; if ((*SW)->TryGetArrayField(Key,A)) for (auto& V : *A) { auto& P=V->AsArray(); if (P.Num()>=3) Out.Add(AJapanWorld::ToUE(P[0]->AsNumber(),P[1]->AsNumber(),P[2]->AsNumber())); } };
    Points(TEXT("lane"),DemoLane); Points(TEXT("ramp"),DemoRamp); Points(TEXT("crossing"),DemoCrossing);
    const TSharedPtr<FJsonObject>* Island=nullptr;
    if ((*SW)->TryGetObjectField(TEXT("island"),Island))
    {
        const TArray<TSharedPtr<FJsonValue>>* A=nullptr;
        if ((*Island)->TryGetArrayField(TEXT("landing"),A) && A->Num()>=3) DemoLanding = AJapanWorld::ToUE((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
        if ((*Island)->TryGetArrayField(TEXT("summit"),A) && A->Num()>=3) DemoSummit = AJapanWorld::ToUE((*A)[0]->AsNumber(),(*A)[1]->AsNumber(),(*A)[2]->AsNumber());
    }
    DemoStand = AJapanWorld::ToUE(-221,-169.5,1.0); DemoSide = AJapanWorld::ToUE(-215.5,-164.5,1.0); DemoLaunch = AJapanWorld::ToUE(-214,-176,0.0);
    // The rebuilt counter occupies the old lane endpoint. Stop in the open
    // forecourt, then go around the east side to the water.
    while (DemoLane.Num()>2 && DemoLane.Last().Y>16400.f) DemoLane.Pop();
    DemoLane.Add(AJapanWorld::ToUE(-222,-164.5,1.0));
    return DemoLane.Num()>2 && DemoRamp.Num()>2 && DemoCrossing.Num()>1;
}
bool AWandererCharacter::FollowTo(const FVector& Target, float Dt, float Tolerance)
{
    FVector To = Target-GetActorLocation(); To.Z = 0;
    if (To.Size() < Tolerance) { MoveIntent = FVector2D::ZeroVector; return true; }
    ReviewForward = To.GetSafeNormal();
    const float Yaw = ReviewForward.Rotation().Yaw;
    if (Controller) { FRotator R = Controller->GetControlRotation(); R.Yaw = FMath::FixedTurn(R.Yaw,Yaw,90.f*Dt); R.Pitch = FMath::FInterpTo(FRotator::NormalizeAxis(R.Pitch),-9.f,Dt,2.f); Controller->SetControlRotation(R); }
    MoveIntent = FVector2D(0,1.f); return false;
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
void AWandererCharacter::AdvanceSouthwestDemo(float Dt)
{
    DemoTime += Dt; PhaseTime += Dt;
    if (DemoPhase < 0)
    {
        if (!LoadSouthwestData()) { UE_LOG(LogTemp,Error,TEXT("DEMO: southwest data missing")); FPlatformMisc::RequestExit(false); return; }
        DemoPhase = 0; FParse::Value(FCommandLine::Get(),TEXT("demostartphase="),DemoPhase); DemoPhase=FMath::Clamp(DemoPhase,0,8); PhaseTime = 0; DemoIndex = 0; bJog = false; bWalk = false;
        if (Controller) Controller->SetControlRotation(FRotator(-9,GetActorRotation().Yaw,0));
        UE_LOG(LogTemp,Display,TEXT("DEMO START lane %d ramp %d"),DemoLane.Num(),DemoRamp.Num());
    }
    auto Next = [&](){ DemoPhase++; PhaseTime = 0; DemoIndex = 0; UE_LOG(LogTemp,Display,TEXT("DEMO PHASE %d at %.1f s position %s"),DemoPhase,DemoTime,*GetActorLocation().ToCompactString()); };
    // safety: no phase may run forever; a stuck follow skips ahead instead of filling the disk with frames
    static const float Limits[] = {3.f,55.f,6.f,14.f,110.f,25.f,20.f,4.f,30.f};
    // stuck detector: a follow phase that has not moved a metre in four seconds is skipped
    if (DemoPhase==1 || DemoPhase==3 || DemoPhase==5 || DemoPhase==6) { if (FVector::DistSquared(GetActorLocation(),StuckAnchor) > 100.f*100.f) { StuckAnchor = GetActorLocation(); StuckTime = 0.f; } else if ((StuckTime += Dt) > 4.f) { UE_LOG(LogTemp,Warning,TEXT("DEMO phase %d stuck step %.1f floor %s"),DemoPhase,GetCharacterMovement()->MaxStepHeight,*GetNameSafe(GetCharacterMovement()->CurrentFloor.HitResult.GetComponent())); StuckTime = 0.f; Next(); } } else { StuckAnchor = GetActorLocation(); StuckTime = 0.f; }
    if (DemoPhase < 9 && PhaseTime > Limits[DemoPhase]) { UE_LOG(LogTemp,Warning,TEXT("DEMO phase %d timed out"),DemoPhase); if (Sailboat->IsEquipped() && DemoPhase==4) Sailboat->Toggle(); Next(); }
    if (DemoTime > 240.f) { UE_LOG(LogTemp,Display,TEXT("DEMO COMPLETE (time cap) %d frames"),DemoFrame); FPlatformMisc::RequestExit(false); bSouthwestDemo=false; return; }
    switch (DemoPhase)
    {
    case 0: MoveIntent = FVector2D::ZeroVector; if (PhaseTime > 1.5f) Next(); break;
    case 1: // along the road and down the lane to the stand
        if (FollowTo(DemoLane[DemoIndex],Dt,DemoIndex==DemoLane.Num()-1 ? 90.f : 140.f)) { DemoIndex += 6; if (DemoIndex >= DemoLane.Num()) { DemoIndex = DemoLane.Num()-1; if (FollowTo(DemoLane.Last(),Dt,90.f)) Next(); } }
        break;
    case 2: // at the stand: face it, wave
        MoveIntent = FVector2D::ZeroVector; bJog = true;
        if (PhaseTime < .8f) { DemoIndex = -1; FVector To = DemoStand-GetActorLocation(); To.Z = 0; SetActorRotation(FRotator(0,To.Rotation().Yaw,0)); if (Controller) Controller->SetControlRotation(FRotator(-6,To.Rotation().Yaw+35.f,0)); }
        if (PhaseTime > .8f && PhaseTime < 1.0f) Wave(FInputActionValue());
        if (PhaseTime > 4.0f) Next();
        break;
    case 3: // to the water's edge and launch: round the stand's east side first (a straight line runs through the hut)
        bJog = true;
        if (DemoIndex == 0) { if (FollowTo(DemoSide,Dt,90.f)) DemoIndex = 1; break; }
        if (FollowTo(DemoLaunch,Dt,70.f)) { if (!Sailboat->IsEquipped()) { ToggleSailboat(FInputActionValue());  } if (Sailboat->IsEquipped() && PhaseTime > 1.f) Next(); }
        break;
    case 4: // Follow the coastal crossing waypoints, then close on the cove
    {
        if (!Sailboat->IsEquipped()) { Next(); break; }
        const FVector To = DemoCrossing[DemoIndex]-GetActorLocation();
        const float Dist=To.Size2D();
        if (Dist<600.f)
        {
            if (DemoIndex+1>=DemoCrossing.Num()) { if(Sailboat->Toggle()){Next();break;} }
            else ++DemoIndex;
        }
        const float TargetYaw=(DemoCrossing[DemoIndex]-GetActorLocation()).Rotation().Yaw;
        const float Err=FRotator::NormalizeAxis(TargetYaw-GetActorRotation().Yaw);
        // Lower the sail for sharp turns, then raise it again toward the next waypoint.
        MoveIntent=FVector2D(FMath::Clamp(Err/25.f,-1.f,1.f),FMath::Abs(Err)>40.f ? -1.f : 1.f);
        if (Controller) { FRotator R = Controller->GetControlRotation(); R.Yaw = FMath::FixedTurn(R.Yaw,GetActorRotation().Yaw+8.f,60.f*Dt); R.Pitch = FMath::FInterpTo(FRotator::NormalizeAxis(R.Pitch),4.f,Dt,1.f); Controller->SetControlRotation(R); }
        if (PhaseTime > 150.f) { Sailboat->Toggle(); Next(); }
        break;
    }
    case 5: // wade to the cove
        bJog = false; bWalk = false;
        if (FollowTo(DemoLanding,Dt,120.f)) Next();
        break;
    case 6: // a cut to the top of the stairway on the summit terrace, then walk up to the temple
        // the temple faces north (UE -Y), the island is rotated 15 degrees: start at the foot of the approach steps and walk to the veranda
        if (PhaseTime < .1f) { const FVector Start = DemoSummit+FRotator(0,-15.f,0).RotateVector(FVector(0,-1900.f,0)); SetActorLocation(Start+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+40.f),false,nullptr,ETeleportType::TeleportPhysics); const FVector To=DemoSummit-Start; SetActorRotation(FRotator(0,To.Rotation().Yaw,0)); if (Controller) Controller->SetControlRotation(FRotator(-10,To.Rotation().Yaw,0)); bJog = true; }
        else if (FollowTo(DemoSummit+FRotator(0,-15.f,0).RotateVector(FVector(0,-750.f,0)),Dt,120.f)) Next();
        break;
    case 7: // pause at the temple steps
        MoveIntent = FVector2D::ZeroVector; if (PhaseTime > 2.f) Next();
        break;
    case 8: // slow orbit at the summit
        MoveIntent = FVector2D::ZeroVector;
        if (Controller) { FRotator R = Controller->GetControlRotation(); R.Yaw += 9.f*Dt; R.Pitch = FMath::FInterpTo(FRotator::NormalizeAxis(R.Pitch),-16.f,Dt,1.f); Controller->SetControlRotation(R); }
        if (PhaseTime > 10.f) { UE_LOG(LogTemp,Display,TEXT("DEMO COMPLETE at %.1f s, %d frames"),DemoTime,DemoFrame); FPlatformMisc::RequestExit(false); bSouthwestDemo=false; return; }
        break;
    default: break;
    }
    RecordFrame();
}
/** Flyover: a detached camera along keyframes with look targets, easing per segment. */
void AWandererCharacter::AdvanceSouthwestFly(float Dt)
{
    struct FKey { FVector At, Look; float Seconds; };
    static const TArray<FKey> Keys = {
        { AJapanWorld::ToUE(-262,-104,45), AJapanWorld::ToUE(-200,-96,12), 0.f },
        { AJapanWorld::ToUE(-140,-115,70), AJapanWorld::ToUE(-40,-70,15), 14.f },       // east along the road, over the forest
        { AJapanWorld::ToUE(-250,-150,42), AJapanWorld::ToUE(-262,-124,8), 14.f },      // back over the fishing village
        { AJapanWorld::ToUE(-215,-195,26), AJapanWorld::ToUE(-221,-169,3), 9.f },       // the coconut stand from the water
        { AJapanWorld::ToUE(-190,-320,70), AJapanWorld::ToUE(-150,-480,60), 12.f },     // out to sea, the island ahead
        { AJapanWorld::ToUE(80,-470,150), AJapanWorld::ToUE(-150,-475,70), 12.f },      // around the island, east side
        { AJapanWorld::ToUE(-150,-720,160), AJapanWorld::ToUE(-152,-472,80), 12.f },    // south
        { AJapanWorld::ToUE(-380,-480,150), AJapanWorld::ToUE(-152,-472,80), 12.f },    // west
        { AJapanWorld::ToUE(-185,-395,120), AJapanWorld::ToUE(-152,-472,100), 9.f },    // climb to the summit
        { AJapanWorld::ToUE(-175,-440,112), AJapanWorld::ToUE(-152,-472,99), 8.f },     // the temple
    };
    if (DemoPhase < 0)
    {
        DemoPhase = 0; DemoTime = 0; FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        GetCharacterMovement()->DisableMovement(); GetMesh()->SetVisibility(false,true);
        UE_LOG(LogTemp,Display,TEXT("FLYOVER START"));
    }
    DemoTime += Dt;
    float T = DemoTime; int32 Seg = 1;
    while (Seg < Keys.Num() && T > Keys[Seg].Seconds) { T -= Keys[Seg].Seconds; Seg++; }
    if (Seg >= Keys.Num()) { UE_LOG(LogTemp,Display,TEXT("FLYOVER COMPLETE %d frames"),DemoFrame); FPlatformMisc::RequestExit(false); bSouthwestFly=false; return; }
    const float U = FMath::Clamp(T/Keys[Seg].Seconds,0.f,1.f); const float E = U*U*(3-2*U);
    const FVector At = FMath::Lerp(Keys[Seg-1].At,Keys[Seg].At,E), Look = FMath::Lerp(Keys[Seg-1].Look,Keys[Seg].Look,E);
    FollowCamera->SetWorldLocationAndRotation(At,(Look-At).Rotation());
    RecordFrame();
}
void AWandererCharacter::Landed(const FHitResult& Hit)
{
    Super::Landed(Hit);
    if (SkateRide->IsRiding()) { FallSpeed = 0.f; return; }   // a bail: the skate component plays the fall
    bPendingTakeoff = bGroundJumped = bAirJumpUsed = bAirDashUsed = false;
    GetCharacterMovement()->RemoveRootMotionSource(TEXT("ForwardDash"));
    SinceGrounded = 0.f;
    if (Sailboat->IsEquipped()) { FallSpeed = 0.f; return; }
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
    if(Landscape->bForestLakeLoaded && !Sailboat->IsEquipped())
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
    if(!Sailboat->IsEquipped() && GetActorLocation().X<=30000.)
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
    if (bWarmReview) AdvanceWarmReview(Dt);
    if (bReview) AdvanceReview(Dt);
    if (bSailboatReview) AdvanceSailboatReview(Dt);
    if (bMapReview) AdvanceMapReview(Dt);
    if (bSwordReview) AdvanceSwordReview(Dt);
    if (bSouthwestDemo) AdvanceSouthwestDemo(Dt);
    if (bSouthwestFly) { AdvanceSouthwestFly(Dt); return; }
    if (!BenchmarkView.IsEmpty()) AdvanceBenchmark(Dt);
    if (!TrailerSpecPath.IsEmpty()) AdvanceTrailer(Dt);
    if (PhoneInput) PhoneInput->Tick(Dt);
    if(IsZeppelinPassenger()){Stamina.Tick(Dt,false,false,bMenuOpen);return;}
    Sailboat->SetInput(MoveIntent,bMenuOpen || (Map && Map->IsOpen()));
    if (!Sailboat->IsEquipped() && !SkateRide->IsRiding()) { if (Sword) Sword->Advance(Dt); AdvanceAction(Dt); } // Keep state time aligned while settings are open.
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
    const bool CanSprint=!bWalk&&!bJog&&!bIsCrouched&&!MovementLocked()&&!SkateRide->IsRiding()&&!Sailboat->IsEquipped()&&!MoveIntent.IsNearlyZero()&&M->Velocity.Size2D()>40.f;
    Stamina.Tick(Dt,bSprintHeld,CanSprint,bMenuOpen);
    M->MaxWalkSpeed = Definition->UseAuthoredMovement
        ? ((bWalk || bJog) ? Definition->WalkSpeed : Stamina.Sprinting ? GetSprintSpeed() : Definition->RunSpeed)
        : bWalk ? Definition->WalkSpeed : Definition->RunSpeed*(bJog?1.f:Stamina.Sprinting?2.5f:2.f);
    if (!bMenuOpen && !MovementLocked() && !Sailboat->IsEquipped() && !SkateRide->IsRiding())
    {
        const FRotationMatrix Basis(FRotator(0,GetControlRotation().Yaw,0));
        if (bReview || bSouthwestDemo || !BenchmarkView.IsEmpty() || !TrailerSpecPath.IsEmpty()) AddMovementInput(ReviewForward,MoveIntent.Y);
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

void AWandererCharacter::SampleShake(FVector& Offset,FRotator& Rotation) const
{
    const float A=ShakeTrauma*ShakeTrauma,F=23.f;
    Offset=FVector(0.f,FMath::PerlinNoise1D(ShakeClock*F)*9.f,FMath::PerlinNoise1D(ShakeClock*F+41.3f)*7.f)*A;
    Rotation=FRotator(FMath::PerlinNoise1D(ShakeClock*F+7.1f)*2.2f,FMath::PerlinNoise1D(ShakeClock*F+19.7f)*2.2f,FMath::PerlinNoise1D(ShakeClock*F+3.3f)*3.f)*A;
}

void AWandererCharacter::AdvanceReview(float Dt)
{
    if (bJumpReview) { AdvanceJumpReview(Dt); return; }
    if (bGroundContactReview) { AdvanceGroundContactReview(Dt); return; }
    if (bLocomotionReview) { AdvanceLocomotionReview(Dt); return; }
    ReviewTime += Dt;
    if (bWorldReview)
    {
        const int32 View = FMath::FloorToInt(ReviewTime/3.f);
        if (View > Landscape->Shots.Num()) { UE_LOG(LogTemp,Display,TEXT("WANDERER QA COMPLETE")); FPlatformMisc::RequestExit(false); return; }
        if (View != ReviewStep)
        {
            ReviewStep = View; GetCharacterMovement()->StopMovementImmediately();
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
            FWorldShot Shot = Landscape->Shots[FMath::Min(View,Landscape->Shots.Num()-1)];
            if (View == Landscape->Shots.Num())
            {
                Shot = Landscape->Shots[0];
                const FVector Forward = FRotator(0,Shot.Rotation.Yaw,0).Vector();
                Shot.Location += -Forward*120.f+FVector(0,0,45);
                Shot.Rotation = FRotator(-2.f,Shot.Rotation.Yaw,0);
            }
            FollowCamera->SetWorldLocationAndRotation(Shot.Location,Shot.Rotation);
        }
        const float Local = FMath::Fmod(ReviewTime,3.f);
        if (Local >= 2.5f && Local-Dt < 2.5f)
            FScreenshotRequest::RequestScreenshot(ReviewDirectory/(View == Landscape->Shots.Num() ? TEXT("gate_road.png") : FString::Printf(TEXT("shot_%02d.png"),View)),false,false);
        return;
    }
    const int32 Step = FMath::FloorToInt(ReviewTime/2.5f);
    if (Step != ReviewStep)
    {
        ReviewStep = Step;
        MoveIntent = FVector2D::ZeroVector; bJog = bWalk = bSprintHeld = false;
        switch (Step)
        {
        case 0: SetMouseReleased(false); break;
        case 1: bWalk = true; MoveIntent.Y = 1; break;
        case 2: bJog = true; MoveIntent.Y = 1; break;
        case 3: MoveIntent.Y = 1; break;
        case 4: RequestJump(FInputActionValue()); break;
        case 5: ToggleCrouch(FInputActionValue()); break;
        case 6: MoveIntent.Y = 1; break;
        case 7: ToggleCrouch(FInputActionValue()); Wave(FInputActionValue()); break;
        case 8: Interact(FInputActionValue()); break;
        case 9: Dodge(FInputActionValue()); break;
        case 10:
            FFileHelper::SaveStringToFile(ReviewTelemetry,*(ReviewDirectory/TEXT("telemetry.csv")));
            FFileHelper::SaveStringToFile(FString::Printf(TEXT("{\"mouse_up_pitch_delta\":%.6f,\"mouse_down_pitch_delta\":%.6f}"),UpPitchDelta,DownPitchDelta),*(ReviewDirectory/TEXT("input.json")));
            if (UpPitchDelta <= 0 || DownPitchDelta >= 0)
            {
                UE_LOG(LogTemp,Error,TEXT("WANDERER INPUT QA FAILED: up %f down %f"),UpPitchDelta,DownPitchDelta);
                FPlatformMisc::RequestExitWithStatus(false,2); return;
            }
            UE_LOG(LogTemp,Display,TEXT("WANDERER QA COMPLETE"));
            FPlatformMisc::RequestExit(false); return;
        }
        if (Step > 0)
        {
            const float Offset = Step == 2 || Step == 6 ? 0.f : Step == 4 ? 90.f : 145.f;
            Controller->SetControlRotation(FRotator(-8,ReviewForward.Rotation().Yaw+Offset,0));
        }
        UE_LOG(LogTemp,Display,TEXT("WANDERER QA STEP %d"),Step);
    }
    if (Step == 0)
    {
        APlayerController* PC = CastChecked<APlayerController>(Controller);
        if (InputReviewStage == 0 && ReviewTime > .15f)
        {
            InputReviewPitch = FRotator::NormalizeAxis(PC->GetControlRotation().Pitch);
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(EKeys::MouseY,IE_Axis,20.f,1)); InputReviewStage = 1;
        }
        else if (InputReviewStage == 1 && ReviewTime > .4f)
        {
            UpPitchDelta = FRotator::NormalizeAxis(PC->GetControlRotation().Pitch)-InputReviewPitch;
            InputReviewPitch = FRotator::NormalizeAxis(PC->GetControlRotation().Pitch);
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(EKeys::MouseY,IE_Axis,-20.f,1)); InputReviewStage = 2;
        }
        else if (InputReviewStage == 2 && ReviewTime > .65f)
        {
            DownPitchDelta = FRotator::NormalizeAxis(PC->GetControlRotation().Pitch)-InputReviewPitch;
            SetMouseReleased(true); InputReviewStage = 3;
            Controller->SetControlRotation(FRotator(-8,ReviewForward.Rotation().Yaw+155.f,0));
            UE_LOG(LogTemp,Display,TEXT("WANDERER INPUT: up %+f down %+f"),UpPitchDelta,DownPitchDelta);
        }
    }
    const FVector Left = GetMesh()->GetBoneLocation(TEXT("foot_L"),EBoneSpaces::ComponentSpace);
    const FVector Right = GetMesh()->GetBoneLocation(TEXT("foot_R"),EBoneSpaces::ComponentSpace);
    ReviewTelemetry += FString::Printf(TEXT("%.4f,%d,%.4f,%d,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f\n"),ReviewTime,Step,GetVelocity().Size2D(),GetCharacterMovement()->IsFalling(),bIsCrouched,FRotator::NormalizeAxis(GetControlRotation().Pitch),Left.X,Left.Y,Left.Z,Right.X,Right.Y,Right.Z,GetCapsuleComponent()->GetUnscaledCapsuleHalfHeight(),GetMesh()->GetRelativeLocation().Z);
    // Video mode records consecutive game frames; launch with -UseFixedTimeStep -FPS=30.
    if (bRecordReview)
    {
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("frame_%05d.png"),ReviewFrame++),false,false);
        return;
    }
    // Capture at three distinct phases of each action; filenames never overwrite manual captures.
    const float Local = FMath::Fmod(ReviewTime,2.5f);
    for (float T : {.30f,.65f,1.30f}) if (Local >= T && Local-Dt < T)
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("state_%02d_%03d.png"),Step,FMath::RoundToInt(T*100)),false,false);
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
