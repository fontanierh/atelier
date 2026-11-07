#pragma once
#include "CoreMinimal.h"
#include "JapanBikeState.h"
#include "JapanParkedBikeState.generated.h"

/** One host-authored bike per pawn identity. It outlives riding epochs, and is
 * removed when that pawn leaves the session. It has no collision or simulation. */
USTRUCT()
struct FJapanParkedBikeState
{
    GENERATED_BODY()
    UPROPERTY() bool Visible = false;
    UPROPERTY() FTransform Transform;
    UPROPERTY() FJapanBikeState Pose;
};
