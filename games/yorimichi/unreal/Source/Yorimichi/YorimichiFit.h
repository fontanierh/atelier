#pragma once
#include "Kismet/BlueprintFunctionLibrary.h"
#include "YorimichiFit.generated.h"

class USkeletalMeshComponent;
class UStaticMeshComponent;

/** Fitting checks for equipment a character carries (scenarios run them through the live bridge). */
UCLASS()
class YORIMICHI_API UYorimichiFitLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()
public:
    /** How far Body's skin (its current pose, skinned on the CPU: the mesh needs CPU access) comes through Prop, a piece
     *  it carries: the piece is taken as an elliptic cylinder in its mesh's bounds, along its longest axis for a rod (a
     *  sword, a sheath) or across its two longest for a disc (a shield), shrunk by MarginCm. Returns
     *  "inside N, deepest D cm; Slot n d; ..." with each material slot's count and depth (cm into the piece). Cloth
     *  sections count by their skinned pose. */
    UFUNCTION(BlueprintCallable, Category = "Yorimichi|Debug")
    static FString PropClearance(USkeletalMeshComponent* Body, UStaticMeshComponent* Prop, float MarginCm);
};
