#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "InputActionValue.h"
#include "SandboxCharacter.generated.h"

class UCameraComponent;
class USpringArmComponent;
class UStaticMeshComponent;
class UInputAction;
class UInputMappingContext;

/** A capsule with a camera: runs, jumps and looks around; enough to walk up to what the live bridge puts in the world. */
UCLASS()
class SANDBOX_API ASandboxCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    ASandboxCharacter();
    virtual void BeginPlay() override;
    virtual void SetupPlayerInputComponent(UInputComponent* Input) override;
private:
    void Move(const FInputActionValue& Value);
    void Look(const FInputActionValue& Value);
    void StickLook(const FInputActionValue& Value);
    UPROPERTY() TObjectPtr<USpringArmComponent> Arm;
    UPROPERTY() TObjectPtr<UCameraComponent> Camera;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Body;
    UPROPERTY() TObjectPtr<UStaticMeshComponent> Head;
    UPROPERTY() TObjectPtr<UInputMappingContext> Mapping;
    UPROPERTY() TMap<FName, TObjectPtr<UInputAction>> Actions;
};
