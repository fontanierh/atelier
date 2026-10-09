#pragma once
#include "CoreMinimal.h"
#include "UObject/Interface.h"
#include "SkiRider.generated.h"

UINTERFACE(MinimalAPI)
class USkiRider : public UInterface { GENERATED_BODY() };

/** What the ski component asks of the character that skis (README.md, "Adding it to a game"). */
class ATELIERSKI_API ISkiRider
{
    GENERATED_BODY()
public:
    /** Putting the skis on: put away what the hands hold, stop any action in progress. */
    virtual void PrepareToSki() {}
    /** A menu has the controls: the skier gets neutral input. */
    virtual bool IsSkiInputBlocked() const { return false; }
    /** The rider's bone for a humanoid contract name (platform/conventions/rigs/humanoid.toml). */
    virtual FName GetSkiBone(FName Contract) const { return Contract; }
};
