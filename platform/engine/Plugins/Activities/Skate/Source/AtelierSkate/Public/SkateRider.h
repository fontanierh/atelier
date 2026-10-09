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
    /** The rider's bone for a humanoid contract name (root, pelvis, spine, spine_mid, chest, neck, head, clavicle_L,
     *  upperarm_L, forearm_L, hand_L, thigh_L, shin_L, foot_L, toe_L, the right side, and the optional finger_N_L,
     *  finger_tip_N_L, finger_end_N_L, thumb_L, thumb_tip_L, thumb_end_L), NAME_None when it has none. The board's
     *  retargeter finds every bone through this; a rig that follows the contract keeps the default. */
    virtual FName GetSkateBone(FName Contract) const { return Contract; }
    /** The visible board's size relative to the source rider's: a short character with big feet rides a bigger one.
     *  It grows about its ground contact and the pose rises onto its deck; the ride's physics keep the source board. */
    virtual float GetSkateBoardScale() const { return 1.f; }
    /** On foot: whether the hands are free to hold the board. False (a weapon drawn, climbing,
     *  gliding, swimming, sailing, an interaction) puts a held board away (RIDE.md, "Transitions"). */
    virtual bool CanCarrySkateBoard() const { return true; }
};
