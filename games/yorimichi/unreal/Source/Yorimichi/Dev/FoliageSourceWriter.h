#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FoliageSourceWriter.generated.h"
class UStaticMesh;

// Receiver-only editor diagnostic: production preparation lives in its own module.
UCLASS()
class YORIMICHI_API UYorimichiFoliageSourceWriter : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool ExportSource(UStaticMesh* Source,const TArray<int32>& LeafSlots,
        const FString& Classification,const FString& Kind,const FString& Path,int32 LODIndex=0);
};
