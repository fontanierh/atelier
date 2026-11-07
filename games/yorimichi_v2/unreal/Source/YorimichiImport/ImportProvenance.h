#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "ImportProvenance.generated.h"

class UAssetImportData;

/** Adopted packages keep no donor provenance (CONTRACTS yorimichi-v2-portable-records; Scripts/scrub_import_data.py). */
UCLASS()
class UImportProvenance : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** An Interchange import's factory node ID names its source file and is read-only to scripts: rename it.
     *  False when Data is not Interchange import data. */
    UFUNCTION(BlueprintCallable, Category="Import provenance")
    static bool RenameInterchangeNode(UAssetImportData* Data, const FString& NodeId);
};
