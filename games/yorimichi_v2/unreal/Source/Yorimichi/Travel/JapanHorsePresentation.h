#pragma once
#include "CoreMinimal.h"
#include "JapanHorseState.h"
#include "JapanHorsePresentation.generated.h"
USTRUCT()
struct FJapanHorsePresentation
{
    GENERATED_BODY()
    UPROPERTY() uint32 Epoch = 0;
    UPROPERTY() double Stamp = 0.;
    UPROPERTY() FJapanHorseState State;
};
