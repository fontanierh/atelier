#pragma once
#include "CoreMinimal.h"
#include "JapanHorseAppearance.generated.h"

/** A horse's look as roster indices (Content/Data/horses/roster.json): breed_order, tack_sets, the coat (0 the breed's
 * own, k coat_variants[k-1]), coat_masks, the hair colour (0 the breed's own, k hair_colors[k-1]), hair_patterns and tints. Pawn-owned and outside the activity
 * epoch, like the parked bike. Session admission hashes Content/, so every machine reads the same roster order. */
USTRUCT()
struct FJapanHorseAppearance
{
    GENERATED_BODY()
    UPROPERTY() uint8 Breed = 0;
    UPROPERTY() uint8 Tack = 0;
    UPROPERTY() uint8 Coat = 0;
    UPROPERTY() uint8 Mask = 0;
    UPROPERTY() uint8 HairColor = 0;
    UPROPERTY() uint8 HairPattern = 0;
    UPROPERTY() uint8 Tint = 0;
    /** The host accepted a chosen look; until then every machine shows the roster's default. */
    UPROPERTY() bool bChosen = false;
    /** Within the roster's list sizes; an empty list leaves only index 0 (the imported look). Coats and HairColors count
     *  the breed's own and every roster entry. */
    bool IsWithin(int32 Breeds, int32 Tacks, int32 Coats, int32 Masks, int32 HairColors, int32 HairPatterns, int32 Tints) const
    {
        auto In = [](int32 Index, int32 Count) { return Index < FMath::Max(Count, 1); };
        return In(Breed, Breeds) && In(Tack, Tacks) && In(Coat, Coats) && In(Mask, Masks) && In(HairColor, HairColors) &&
            In(HairPattern, HairPatterns) && In(Tint, Tints);
    }
    /** The same look (bChosen aside). */
    bool SameLook(const FJapanHorseAppearance& Other) const
    {
        return Breed == Other.Breed && Tack == Other.Tack && Coat == Other.Coat && Mask == Other.Mask &&
            HairColor == Other.HairColor && HairPattern == Other.HairPattern && Tint == Other.Tint;
    }
};
