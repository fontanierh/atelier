// SPDX-License-Identifier: Apache-2.0
#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "SkateRuntimeAsset.h"
#include "SkateRuntimeAssetLibrary.generated.h"

/** Headless editor entry points, also exposed by Unreal's Python reflection. */
UCLASS()
class ATELIERSKATEEDITOR_API USkateRuntimeAssetLibrary final : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Source folder is an authoring input only; no source path is serialized. */
    UFUNCTION(BlueprintCallable, Category="Skate|Runtime")
    static FSkateRuntimeAssetValidationReport BuildRuntimeAsset(const FString& BundleDirectory,
        const FString& AssetPath,const FString& ExpectedManifestSha256,int32 ExpectedRecordCount = 3334);

    UFUNCTION(BlueprintCallable, Category="Skate|Runtime")
    static FSkateRuntimeAssetValidationReport ValidateRuntimeAsset(const USkateRuntimeAsset* Asset,
        bool bCheckDecodedPayloads = true);

    /** Actual file-source and immutable asset-source sessions, on the same floor. */
    UFUNCTION(BlueprintCallable, Category="Skate|Runtime")
    static FSkateRuntimeAssetValidationReport ValidateResourceEquivalence(const USkateRuntimeAsset* Asset,
        const FString& BundleDirectory,int32 TicksPerStance = 120);
};
