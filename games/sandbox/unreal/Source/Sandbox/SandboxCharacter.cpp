#include "SandboxCharacter.h"
#include "LiveLibrary.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "Engine/LocalPlayer.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputAction.h"
#include "InputMappingContext.h"
#include "InputModifiers.h"
#include "UObject/ConstructorHelpers.h"

ASandboxCharacter::ASandboxCharacter()
{
    GetCapsuleComponent()->InitCapsuleSize(34.f, 88.f);
    bUseControllerRotationYaw = false;
    GetCharacterMovement()->bOrientRotationToMovement = true;
    GetCharacterMovement()->RotationRate = FRotator(0, 720, 0);
    GetCharacterMovement()->MaxWalkSpeed = 600.f;
    GetCharacterMovement()->JumpZVelocity = 620.f;
    GetCharacterMovement()->AirControl = .4f;
    // A body from the engine's basic shapes (referenced, not copied): a cylinder and a sphere for the head.
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
    Body = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Body"));
    Body->SetupAttachment(GetCapsuleComponent());
    Body->SetStaticMesh(Cylinder.Object);
    Body->SetRelativeScale3D(FVector(.6f, .6f, 1.3f));
    Body->SetRelativeLocation(FVector(0, 0, -20.f));
    Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Head = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Head"));
    Head->SetupAttachment(GetCapsuleComponent());
    Head->SetStaticMesh(Sphere.Object);
    Head->SetRelativeScale3D(FVector(.45f));
    Head->SetRelativeLocation(FVector(8.f, 0, 66.f));
    Head->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Arm = CreateDefaultSubobject<USpringArmComponent>(TEXT("Arm"));
    Arm->SetupAttachment(GetCapsuleComponent());
    Arm->TargetArmLength = 420.f;
    Arm->SocketOffset = FVector(0, 0, 60.f);
    Arm->bUsePawnControlRotation = true;
    Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
    Camera->SetupAttachment(Arm);
}

void ASandboxCharacter::BeginPlay()
{
    Super::BeginPlay();
    if (Controller) Controller->SetControlRotation(FRotator(-12.f, GetActorRotation().Yaw, 0));
    AtelierLive::Start(GetWorld());   // the live bridge: `atelier live`, runtime props, overlays
}

void ASandboxCharacter::SetupPlayerInputComponent(UInputComponent* Input)
{
    Super::SetupPlayerInputComponent(Input);
    Mapping = NewObject<UInputMappingContext>(this);
    auto Action = [&](FName Name, EInputActionValueType Type)
    {
        UInputAction* A = NewObject<UInputAction>(this, Name); A->ValueType = Type; Actions.Add(Name, A); return A;
    };
    auto Key = [&](UInputAction* A, FKey K, bool bNegate = false, bool bY = false)
    {
        FEnhancedActionKeyMapping& M = Mapping->MapKey(A, K);
        if (bNegate) M.Modifiers.Add(NewObject<UInputModifierNegate>(Mapping));
        if (bY) { auto* Swizzle = NewObject<UInputModifierSwizzleAxis>(Mapping); Swizzle->Order = EInputAxisSwizzle::YXZ; M.Modifiers.Add(Swizzle); }
        return &M;
    };
    UInputAction* MoveAction = Action(TEXT("Move"), EInputActionValueType::Axis2D);
    Key(MoveAction, EKeys::W, false, true); Key(MoveAction, EKeys::S, true, true); Key(MoveAction, EKeys::A, true); Key(MoveAction, EKeys::D);
    Key(MoveAction, EKeys::Gamepad_Left2D)->Modifiers.Add(NewObject<UInputModifierDeadZone>(Mapping));
    UInputAction* LookAction = Action(TEXT("Look"), EInputActionValueType::Axis2D);
    Key(LookAction, EKeys::MouseX); Key(LookAction, EKeys::MouseY, false, true);
    UInputAction* StickAction = Action(TEXT("Stick"), EInputActionValueType::Axis2D);
    Key(StickAction, EKeys::Gamepad_Right2D)->Modifiers.Add(NewObject<UInputModifierDeadZone>(Mapping));
    UInputAction* JumpAction = Action(TEXT("Jump"), EInputActionValueType::Boolean);
    Key(JumpAction, EKeys::SpaceBar); Key(JumpAction, EKeys::Gamepad_FaceButton_Bottom);
    if (APlayerController* PC = Cast<APlayerController>(Controller))
        if (ULocalPlayer* LP = PC->GetLocalPlayer())
            if (auto* Subsystem = LP->GetSubsystem<UEnhancedInputLocalPlayerSubsystem>()) Subsystem->AddMappingContext(Mapping, 0);
    if (auto* E = Cast<UEnhancedInputComponent>(Input))
    {
        E->BindAction(MoveAction, ETriggerEvent::Triggered, this, &ASandboxCharacter::Move);
        E->BindAction(LookAction, ETriggerEvent::Triggered, this, &ASandboxCharacter::Look);
        E->BindAction(StickAction, ETriggerEvent::Triggered, this, &ASandboxCharacter::StickLook);
        E->BindAction(JumpAction, ETriggerEvent::Started, this, &ACharacter::Jump);
        E->BindAction(JumpAction, ETriggerEvent::Completed, this, &ACharacter::StopJumping);
    }
}

void ASandboxCharacter::Move(const FInputActionValue& Value)
{
    const FVector2D V = Value.Get<FVector2D>();
    if (!Controller || V.IsNearlyZero()) return;
    const FRotator Yaw(0, Controller->GetControlRotation().Yaw, 0);
    AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::X), V.Y);
    AddMovementInput(FRotationMatrix(Yaw).GetUnitAxis(EAxis::Y), V.X);
}

void ASandboxCharacter::Look(const FInputActionValue& Value)
{
    const FVector2D V = Value.Get<FVector2D>();
    AddControllerYawInput(V.X * .4f); AddControllerPitchInput(-V.Y * .4f);
}

void ASandboxCharacter::StickLook(const FInputActionValue& Value)
{
    const FVector2D V = Value.Get<FVector2D>() * GetWorld()->GetDeltaSeconds() * 140.f;
    AddControllerYawInput(V.X); AddControllerPitchInput(-V.Y);
}
