#pragma once
#include "WandererCharacter.h"
#include "CairoCharacter.generated.h"

/** Same controls and animation graph, with class defaults for the shorter body.
 * CharacterMovement restores class-default collision and mesh offsets on uncrouch.
 * His merged move set (UAdventureMoveSet) uses the reference motions retargeted onto his own skeleton,
 * plus his double jump and sword guard (assets/characters/adventure/retarget.py, Scripts/import_adventure_moveset.py).
 */
UCLASS()
class YORIMICHI_API ACairoCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ACairoCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual FString GetPlayableName() const override { return TEXT("Cairo"); }
    virtual FString GetBikeRig() const override { return TEXT("Cairo"); }
    virtual bool PlantsFeet() const override { return true; }
    /** His merged move set's definition and record (Content/Data/cairo/adventure.json) are imported (build unreal.cairo_adventure). */
    static bool HasAdventure();
private:
    FVector PreviousHairHead = FVector::ZeroVector;
    FVector PreviousHairVelocity = FVector::ZeroVector;
    FVector2D HairFlex = FVector2D::ZeroVector;
    FVector2D HairFlexVelocity = FVector2D::ZeroVector;
    float HairContactFade = 1.f;
    bool bHairInitialized = false;
};
