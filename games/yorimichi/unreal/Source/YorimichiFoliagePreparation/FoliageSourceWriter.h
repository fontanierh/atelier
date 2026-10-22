#pragma once
#include "CoreMinimal.h"
#include "UObject/Object.h"
#include "FoliageSourceWriter.generated.h"
class UStaticMesh;

// Independent editor-only source transport; current validation belongs to the caller.
UCLASS()
class YORIMICHIFOLIAGEPREPARATION_API UYorimichiFoliageSourceWriter : public UObject
{
    GENERATED_BODY()
public:
    UFUNCTION(BlueprintCallable) static bool ExportSource(UStaticMesh* Source,const TArray<int32>& LeafSlots,
        const FString& Classification,const FString& Kind,const FString& Path,int32 LODIndex=0);
};
