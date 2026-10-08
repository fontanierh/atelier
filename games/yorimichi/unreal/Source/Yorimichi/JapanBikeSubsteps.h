#pragma once
#include "CoreMinimal.h"

namespace JapanBikeSubsteps
{
constexpr float MaximumStep=1.f/120.f;
constexpr int32 MaximumSteps=15;
constexpr float MaximumDelta=.125f;

// A lost packet can make one host move span several owner frames. Advance the
// bike and CMC together so that turning does not move the entire gap along its
// final heading. The same bounded partition is used for prediction and replay.
template<typename F> void Run(float Dt,F&& Simulate)
{
    if(!FMath::IsFinite(Dt)||Dt<=0.f)return;
    const float Bounded=FMath::Min(Dt,MaximumDelta);
    const int32 Count=FMath::Clamp(FMath::CeilToInt(Bounded/MaximumStep),1,MaximumSteps);
    const float Step=Bounded/Count;
    for(int32 I=0;I<Count;++I)Simulate(Step);
}
}
