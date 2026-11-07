#pragma once
#include "Components/ActorComponent.h"
#include "HairSpringComponent.generated.h"

/** A damped spring on two hair morph targets (forward and sideways), driven by the head's acceleration in the
 *  character's frame: the hair lags a start and swings on a stop. Released during actions that bring the hands to the
 *  head (a roll, the double jump's tuck), so the skin readers never meet a swung lock. -statichair (or -cairostatichair) holds it still. */
UCLASS()
class YORIMICHI_API UHairSpringComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UHairSpringComponent();
    virtual void TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    /** Forward, sideways. */
    UPROPERTY() TArray<FName> Morphs;
    UPROPERTY() TArray<FName> ContactActions = {TEXT("Roll"), TEXT("DoubleJump")};
private:
    FVector PreviousHead = FVector::ZeroVector;
    FVector PreviousVelocity = FVector::ZeroVector;
    FVector2D Flex = FVector2D::ZeroVector;
    FVector2D FlexVelocity = FVector2D::ZeroVector;
    float ContactFade = 1.f;
    bool bInitialized = false;
};
