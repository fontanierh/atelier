#pragma once
#include "CoreMinimal.h"

class UStaticMesh;

/** Cached, mesh-derived wheel support for QA. Missing geometry or ground is invalid, never a zero gap. */
namespace JapanBikeSupport
{
constexpr double InvalidGap = 1.e30;
bool Build(TConstArrayView<FVector> Vertices, TArray<FVector>& Points);
bool Load(UStaticMesh* Mesh, TArray<FVector>& Points);
double Gap(TConstArrayView<FVector> Points, const FTransform& Transform,
    TFunctionRef<bool(const FVector&, double&)> GroundHeight);
}
