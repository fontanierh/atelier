#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "FoliageBuilder.generated.h"

class UStaticMesh;

/** Raw import certification only; preparation must not link this module. */
UCLASS()
class YORIMICHIIMPORT_API UYorimichiFoliageBuilder : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Source import boundary: certify UV5 face roles in cooked slot names. */
    UFUNCTION(BlueprintCallable) static bool StampSourceRoles(UStaticMesh* Source);
    /** Synchronous commandlet collection; no future editor tick is required. */
    UFUNCTION(BlueprintCallable) static void CollectUnused();
};
