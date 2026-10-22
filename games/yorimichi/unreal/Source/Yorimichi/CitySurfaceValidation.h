#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "CitySurfaceValidation.generated.h"

class UStaticMesh;

/** Receiving checks for the query surface replacing a generated city parent. */
UCLASS()
class YORIMICHI_API UCitySurfaceValidation : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable, Category="City surfaces")
    static bool ValidateCollision(UStaticMesh* Mesh, int32 ExpectedTriangles, bool HasAuthoredHulls);
};
