#pragma once
#include "WandererCharacter.h"
#include "CairoCharacter.generated.h"

/** Same controls and animation graph, with class defaults for the shorter body.
 * CharacterMovement restores class-default collision and mesh offsets on uncrouch.
 */
UCLASS()
class YORIMICHI_API ACairoCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ACairoCharacter();
    virtual void Tick(float DeltaSeconds) override;
private:
    FVector PreviousHairHead = FVector::ZeroVector;
    FVector PreviousHairVelocity = FVector::ZeroVector;
    FVector2D HairFlex = FVector2D::ZeroVector;
    FVector2D HairFlexVelocity = FVector2D::ZeroVector;
    float HairContactFade = 1.f;
    bool bHairInitialized = false;
};
