#pragma once
#include "WandererCharacter.h"
#include "CairoCharacter.generated.h"

/** Same controls and animation graph, with class defaults for the shorter body.
 * CharacterMovement restores class-default collision and mesh offsets on uncrouch.
 * With -rider=CairoBotw, or "Cairo (BotW)" in the character switch, he plays Breath of the Wild's move set (UBotwMoveSet)
 * on Link's clips retargeted to him (assets/characters/cairo/botw.py, Scripts/import_cairo_botw.py).
 */
UCLASS()
class YORIMICHI_API ACairoCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ACairoCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    /** His name with the BotW move set, for -rider= and the character switch. */
    static FString BotwName() { return TEXT("CairoBotw"); }
    /** His BotW definition and move record (Content/Data/cairo/botw.json) are imported (build unreal.cairo_botw). */
    static bool HasBotw();
    /** The character switch, before BeginPlay: with the BotW move set or without. */
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
