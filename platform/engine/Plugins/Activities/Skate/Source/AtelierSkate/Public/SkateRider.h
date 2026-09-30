#pragma once
#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "SkateRider.generated.h"

/**
 * What USkateComponent needs from the character that rides. The game's player (an ACharacter) implements it; the
 * component drives that character's capsule, mesh and movement directly.
 */
UINTERFACE(MinimalAPI)
class USkateRider : public UInterface { GENERATED_BODY() };

class ATELIERSKATE_API ISkateRider
{
    GENERATED_BODY()
public:
    /** Getting on the board: put away what the hands hold and stop any action in progress. */
    virtual void PrepareToSkate() {}
    /** A menu has the player's controls: the board gets no input and the mouse stick recentres. */
    virtual bool IsSkateInputBlocked() const { return false; }
    /** The mouse is released to the desktop: the board gets no input. */
    virtual bool IsSkateMouseFree() const { return false; }
    /** The player's mouse sensitivity (0.4 is the default); scales the mouse flick. */
    virtual float GetSkateMouseSensitivity() const { return .4f; }
};
