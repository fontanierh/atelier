#pragma once
#include "WandererCharacter.h"
#include "ModoriCharacter.generated.h"

/** Modori, the rival (assets/characters/modori/README.md), as a playable character: Cairo's controls and animation graph
 * on his own 1.75 m body and coat, always with the merged move set (UBotwMoveSet: Link's moves with Cairo's double jump
 * and gestures, retargeted to him by botw/retarget.py --character modori, Scripts/import_botw_moveset.py). Chosen with
 * -rider=Modori or the Esc menu's character switch, whenever his move set is built (unreal.modori_botw).
 */
UCLASS()
class YORIMICHI_API AModoriCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    AModoriCharacter();
    virtual void BeginPlay() override;
    virtual FString GetPlayableName() const override { return Name(); }
    virtual FString GetBikeRig() const override { return TEXT("Modori"); }
    virtual bool PlantsFeet() const override { return true; }
    // Only his longer legs move the sailboat stance; Cairo and the others keep it as it was fitted.
    virtual float SailboatReach(float LegLength) const override { return FMath::Clamp(LegLength / 55.f, 1.f, 1.6f); }
    /** His name for -rider= and the character switch. */
    static FString Name() { return TEXT("Modori"); }
    /** His definition and move record (Content/Data/modori/botw.json) are imported; checked on disk, never loaded. */
    static bool IsBuilt();
};
