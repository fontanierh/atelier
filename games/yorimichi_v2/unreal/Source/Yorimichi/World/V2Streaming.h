#pragma once
#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "V2Streaming.generated.h"

/** The World Partition loading ranges of a V2 map (docs/YORIMICHI_V2_PLAN.md §6, "Repeated buildings, layers and
 *  loading"). The original game spawns its whole island at once and only culls by screen size, so a V2 map must
 *  load its saved scenery at least as far as the original shows it. The engine keeps the ranges in its runtime hash,
 *  which Python cannot read: these reach it through reflection, for both the spatial hash (Grids) and the runtime
 *  hash set (RuntimePartitions). */
UCLASS()
class YORIMICHI_API UV2Streaming : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** Every loading range under the world's runtime hash, as "path=range_cm" lines; empty without World Partition. */
    UFUNCTION(BlueprintCallable, Category = "V2 Streaming", meta = (WorldContext = "WorldContext"))
    static FString DescribeLoadingRanges(const UObject* WorldContext);

    /** Set the loading range of every streaming grid or partition layer under the world's runtime hash, not of its
     *  HLOD layers, to RangeCm and mark the map dirty (editor only, before saving the map). Returns how many changed. */
    UFUNCTION(BlueprintCallable, Category = "V2 Streaming", meta = (WorldContext = "WorldContext"))
    static int32 SetLoadingRanges(const UObject* WorldContext, float RangeCm);
};
