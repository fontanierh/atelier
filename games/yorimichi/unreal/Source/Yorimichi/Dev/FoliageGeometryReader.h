#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FoliageGeometryReader.generated.h"

class UStaticMesh;
class UMaterialInterface;

// Receiver-only editor transport diagnostic. Source ownership and current
// geometry/material/settings validation remain with the preparation caller.
UCLASS()
class YORIMICHI_API UYorimichiFoliageGeometryReader : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable)
    static UStaticMesh* BuildVariant(UStaticMesh* Source, const FString& GeometryPath,
        const TArray<float>& Screens, const FString& Destination,
        UMaterialInterface* NearCanopy, UMaterialInterface* FarCanopy);
};
