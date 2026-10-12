#pragma once
#include "WandererCharacter.h"
#include "NoxCharacter.generated.h"

/** Nox: the approved separate head/body assembly with the full merged move set and
 * procedural bike clips. Skate poses retarget to the same humanoid contract at runtime.
 * Select with -rider=Nox or the character menu once unreal.nox_adventure is built.
 */
UCLASS()
class YORIMICHI_API ANoxCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    ANoxCharacter();
    virtual void BeginPlay() override;
    virtual FString GetPlayableName() const override { return Name(); }
    virtual FString GetBikeRig() const override { return TEXT("Nox"); }
    virtual bool PlantsFeet() const override { return true; }
    /** The bomber and hoodie extend beyond the torso skin. */
    virtual float GetSkateClothingClearance() const override { return 3.f; }
    /** Retain the rounded boot soles in the fitted bail collision. */
    virtual int32 GetSkateCollisionHullDirections() const override { return 1024; }
    // Only his longer legs move the sailboat stance; Cairo and the others keep it as it was fitted.
    virtual float SailboatReach(float LegLength) const override { return FMath::Clamp(LegLength / 55.f, 1.f, 1.6f); }
    /** His name for -rider= and the character switch. */
    static FString Name() { return TEXT("Nox"); }
    /** His definition and move record (Content/Data/nox/adventure.json) are imported; checked on disk, never loaded. */
    static bool IsBuilt();
};
