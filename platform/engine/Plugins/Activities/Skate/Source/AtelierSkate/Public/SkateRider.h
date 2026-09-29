#pragma once
#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "SkateRider.generated.h"

class UAnimSequence;

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
    /** The rider's clip for a role (platform/conventions/clip-roles.toml): the skate roles (SkateStance, SkateOllie ...
     *  and their <Role>Goofy copies) and the locomotion roles the ride falls back on (Idle, Roll). Null when missing. */
    virtual UAnimSequence* FindSkateClip(FName Role) const = 0;
    /** Getting on the board: put away what the hands hold and stop any action in progress. */
    virtual void PrepareToSkate() {}
    /** A menu has the player's controls: the board gets no input and the mouse stick recentres. */
    virtual bool IsSkateInputBlocked() const { return false; }
    /** The mouse is released to the desktop: the board gets no input. */
    virtual bool IsSkateMouseFree() const { return false; }
    /** The player's mouse sensitivity (0.4 is the default); scales the mouse flick. */
    virtual float GetSkateMouseSensitivity() const { return .4f; }
    /** Limb contacts of the rider's skate clips, a file under Content/Data (the character's skate-build.json: per clip,
     *  when each foot is on the deck and each hand holds it). Empty: every foot counts as planted, no hand holds. */
    virtual FString GetSkateContactsFile() const { return FString(); }
};
