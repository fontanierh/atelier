#pragma once
#include "WandererCharacter.h"
#include "ModoriCharacter.generated.h"

/** Modori, the rival (assets/characters/modori/README.md), as a playable character: Cairo's controls and animation graph
 * on his own 1.75 m body and coat, always with the merged move set (UBotwMoveSet: Link's moves with Cairo's double jump
 * and gestures, retargeted to him by cairo/botw.py --character modori, Scripts/import_cairo_botw.py). Chosen with
 * -rider=Modori or the Esc menu's character switch, whenever his move set is built (unreal.modori_botw).
 */
UCLASS()
class YORIMICHI_API AModoriCharacter : public AWandererCharacter
{
    GENERATED_BODY()
public:
    AModoriCharacter();
    virtual void BeginPlay() override;
    /** His name for -rider= and the character switch. */
    static FString Name() { return TEXT("Modori"); }
    /** His definition and move record (Content/Data/modori/botw.json) are imported; checked on disk, never loaded. */
    static bool IsBuilt();
};
