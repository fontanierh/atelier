#pragma once
#include "CoreMinimal.h"
#include "JapanBikeState.h"
#include "JapanBikePresentation.generated.h"
USTRUCT()
struct FJapanBikePresentation
{
    GENERATED_BODY()
    UPROPERTY() uint32 Epoch = 0;
    UPROPERTY() double Stamp = 0.;
    UPROPERTY() FJapanBikeState State;
};
