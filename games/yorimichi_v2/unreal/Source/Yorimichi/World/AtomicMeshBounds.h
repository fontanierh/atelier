#pragma once
#include "CoreMinimal.h"
class UStaticMesh;

namespace AtomicMeshBounds
{
/** Exact saved MeshDescription LOD0 position-union bounds, including its true vertex sphere.
 * Editor observation only; refuses missing, duplicate, multi-LOD or unavailable source descriptions.
 * Geometry, CPU-access flags and asset build settings are never changed. */
YORIMICHI_API bool MeasureLod0PartsBounds(const TArray<UStaticMesh*>& Parts, FBoxSphereBounds& OutBounds);
}
