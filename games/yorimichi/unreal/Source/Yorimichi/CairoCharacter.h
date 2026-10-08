#pragma once
#include "WandererCharacter.h"
#include "CairoCharacter.generated.h"

/** Same controls and animation graph, with class defaults for the shorter body.
 * CharacterMovement restores class-default collision and mesh offsets on uncrouch.
 * Where a person plays he has the merged move set (UBotwMoveSet: Link's moves with his double jump) on Link's clips
 * retargeted to him (assets/characters/botw/retarget.py, Scripts/import_botw_moveset.py), whenever it is built, unless the
 * "Move set" setting picks his legacy moves (or the legacy BOTW set); scripted sessions keep his legacy moves unless the
 * command line asks with -rider=CairoBotw.
 */
UCLASS()
class YORIMICHI_API ACairoCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ACairoCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual FString GetPlayableName() const override { return bBotw ? BotwName() : FString(TEXT("Cairo")); }
    virtual FString GetBikeRig() const override { return TEXT("Cairo"); }
    virtual FString GetHorseRider() const override;
    virtual bool PlantsFeet() const override { return true; }
    /** His name with the merged move set, for -rider= and the character switch. */
    static FString BotwName() { return TEXT("CairoBotw"); }
    /** His merged move set's definition and record (Content/Data/cairo/botw.json) are imported (build unreal.cairo_botw). */
    static bool HasBotw();
    /** The character switch, before BeginPlay: with the merged move set or without. */
    void SetBotw(bool bOn) { bBotw = bOn; }
    bool IsBotw() const { return bBotw; }
private:
    bool bBotw = false;
    FVector PreviousHairHead = FVector::ZeroVector;
    FVector PreviousHairVelocity = FVector::ZeroVector;
    FVector2D HairFlex = FVector2D::ZeroVector;
    FVector2D HairFlexVelocity = FVector2D::ZeroVector;
    float HairContactFade = 1.f;
    bool bHairInitialized = false;
};
