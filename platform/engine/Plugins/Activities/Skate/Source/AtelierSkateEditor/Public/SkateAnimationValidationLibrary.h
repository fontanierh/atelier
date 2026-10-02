#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkateAnimationValidationLibrary.generated.h"

/** Headless checks for the reusable pose node, real mesh bone mappings and profile contract. */
UCLASS()
class ATELIERSKATEEDITOR_API USkateAnimationValidationLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Returns JSON with valid, tests_run, tests_passed, tests_failed, bone_containers, checks and issues.
     *  Native class inspection uses an unregistered transient mesh component; no gameplay world is started.
     *  Pass an empty AnimInstanceClassPath to omit host-specific proxy inspection. */
    UFUNCTION(BlueprintCallable, Category = "Skate|Validation")
    static FString ValidateSkateAnimation(
        const FString& MeshPath,
        const FString& ProfilePath,
        const FString& AnimInstanceClassPath = TEXT(""));
};
