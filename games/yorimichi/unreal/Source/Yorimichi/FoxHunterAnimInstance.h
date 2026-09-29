#pragma once
#include "CoreMinimal.h"
#include "Animation/AnimInstance.h"
#include "FoxHunterAnimInstance.generated.h"

/** Native graph for the fox hunter: a speed blend space (idle, creep, run) under the same velocity-preserving
 * action transition node as the player. Root motion comes from the clips that carry it (dashes, turns, hurt). */
UCLASS(Transient)
class YORIMICHI_API UFoxHunterAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
public:
    UFoxHunterAnimInstance();
protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};
