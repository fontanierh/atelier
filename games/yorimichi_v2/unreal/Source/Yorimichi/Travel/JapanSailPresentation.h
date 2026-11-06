#pragma once
#include "CoreMinimal.h"
#include "JapanSailState.h"
#include "JapanSailPresentation.generated.h"
USTRUCT()
struct FJapanSailPresentation
{
    GENERATED_BODY()
    UPROPERTY() uint32 Epoch=0;
    UPROPERTY() double Stamp=0.;
    UPROPERTY() FJapanSailState State;
};
