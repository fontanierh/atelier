#pragma once
#include "WandererCharacter.h"
#include "CairoCharacter.generated.h"

/** Same controls and animation graph, with class defaults for the shorter body.
 * CharacterMovement restores class-default collision and mesh offsets on uncrouch.
 * Where a person plays he has the merged move set (UAdventureMoveSet: the reference rig's moves with his double jump) on the reference rig's clips
 * retargeted to him (assets/characters/adventure/retarget.py, Scripts/import_adventure_moveset.py), whenever it is built, unless the
 * "Move set" setting picks his legacy moves; scripted sessions keep his legacy moves unless the
 * command line asks with -rider=CairoAdventure.
 */
UCLASS()
class YORIMICHI_API ACairoCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ACairoCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual FString GetPlayableName() const override { return bAdventure ? AdventureName() : FString(TEXT("Cairo")); }
    virtual FString GetBikeRig() const override { return TEXT("Cairo"); }
    virtual bool PlantsFeet() const override { return true; }
    /** His name with the merged move set, for -rider= and the character switch. */
    static FString AdventureName() { return TEXT("CairoAdventure"); }
    /** His merged move set's definition and record (Content/Data/cairo/adventure.json) are imported (build unreal.cairo_adventure). */
    static bool HasAdventure();
    /** The character switch, before BeginPlay: with the merged move set or without. */
    void SetAdventure(bool bOn) { bAdventure = bOn; }
    bool IsAdventure() const { return bAdventure; }
private:
    bool bAdventure = false;
    FVector PreviousHairHead = FVector::ZeroVector;
    FVector PreviousHairVelocity = FVector::ZeroVector;
    FVector2D HairFlex = FVector2D::ZeroVector;
    FVector2D HairFlexVelocity = FVector2D::ZeroVector;
    float HairContactFade = 1.f;
    bool bHairInitialized = false;
};
