#pragma once

#include "CoreMinimal.h"
#include "HRTypes.h"
#include "HRVisualGenome.generated.h"

/**
 * Everything the 3D horse needs to build one individual, resolved from its 61 visual loci, its permanent
 * seed and its exact world age. Port of the reference mobile implementation src/render/appearance.ts (resolveAppearance,
 * art version "ribbon-prototype-1"); every field marked [mobile] is numerically identical to the mobile
 * Appearance field of the same name (checked by Atelier.HorseRacing.Parity.Visual). Fields marked [3D] are
 * additions read from loci the mobile renderer ignores; they are a Technical Art proposal and
 * never change a [mobile] value. Visual genes never affect competition.
 *
 * Conventions:
 * - Multipliers are relative to the neutral adult Balanced horse (1.0 = neutral).
 * - Offsets (EarSpread, EyeHeight, NeckArch, Carriage, Profile) are 0 at neutral.
 * - Final body multipliers (Height, Length, Barrel, Legs, Bone, NeckWidth) already include the family
 *   base proportions (FamilyBase) and the juvenile factors; MorphWeights separates those contributions
 *   so a morph-target rig does not apply the family twice.
 * - Colours are sRGB "#RRGGBB" strings exactly as on mobile, plus FColor copies for materials.
 */
USTRUCT(BlueprintType)
struct ATELIERHORSERACING_API FHRPhenotype
{
	GENERATED_BODY()

	// ------------------------------------------------------------------ identity and age
	/** Exact age in horse months used for growth and graying (negative ages are treated as 0). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype") int32 AgeSteps = 24;
	/** [mobile] 0 adult .. 1 newborn. Drives the foal proportion morph (age.juvenile). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype") double Juvenile = 0;
	/** Physical maturity 0.0 .. 1.0 (0.8 at 12 months, 1.0 from 24 months); Juvenile = (1 - Maturity) / 0.6 clamped. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype") double Maturity = 1;

	// ------------------------------------------------------------------ breed
	/** [3D] Expressed breed ("Standard", "Giant", "Bone", "Spirit") from the "breed" gene (HRBreeds.h). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype") FString Breed;

	// ------------------------------------------------------------------ body family
	/** [mobile] Primary family index after projection: 0 Light, 1 Runner, 2 Balanced, 3 Endurance, 4 Powerful. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") int32 Family = 2;
	/** [mobile] Family name ("Light", "Runner", "Balanced", "Endurance", "Powerful"). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") FString FamilyName;
	/** Second-ranked family (blend partner). Meaningful only when FamilyBlend > 0. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") int32 SecondaryFamily = 2;
	/** Share of the secondary family, 0 .. 0.35 (capped by the family compatibility matrix). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") double FamilyBlend = 0;
	/** Morph weight of each family extreme, indexed like Family; sums to 1. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") TArray<double> FamilyWeights;
	/** Blended family base multipliers: height, length, barrel/neck width, legs, bone. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Family") TArray<double> FamilyBase;

	// ------------------------------------------------------------------ body and neck [mobile]
	/** Withers height multiplier (family base and foal size included). Scale of the whole skeleton. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Height = 1;
	/** Body length multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Length = 1;
	/** Barrel (ribcage and belly) volume multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Barrel = 1;
	/** Leg length multiplier (foals have relatively long legs). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Legs = 1;
	/** Bone substance (cannon and joint thickness) multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Bone = 1;
	/** Chest depth and breast width multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Chest = 1;
	/** Hindquarter (croup, gluteals, gaskin) mass multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Body") double Hindquarter = 1;
	/** Neck length multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Neck") double Neck = 1;
	/** Neck thickness multiplier (family base included). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Neck") double NeckWidth = 1;
	/** Topline arch offset, -0.18 (ewe neck) .. 0.22 (arched crest). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Neck") double NeckArch = 0;
	/** Neck carriage offset, -0.1 (low) .. 0.14 (high). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Neck") double Carriage = 0;

	// ------------------------------------------------------------------ head [mobile]
	/** Head length multiplier (foals have short heads). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double Head = 1;
	/** Forehead / head width multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double HeadWidth = 1;
	/** Muzzle size multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double Muzzle = 1;
	/** Jaw / cheek depth multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double Jaw = 1;
	/** Nasal profile: -1 dished .. 0 straight .. +1 convex (steps of 0.5; forbidden by family -> 0). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double Profile = 0;
	/** Ear length multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double Ears = 1;
	/** Ear spread offset, -0.09 (close) .. 0.12 (wide). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double EarSpread = 0;
	/** Eye spacing multiplier. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double EyeSpacing = 1;
	/** Eye height offset, -0.04 .. 0.04. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Head") double EyeHeight = 0;

	// ------------------------------------------------------------------ hair [mobile]
	/** Mane style module 0..5. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") int32 Mane = 0;
	/** Tail style module 0..5. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") int32 Tail = 0;
	/** Forelock style module 0..3. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") int32 Forelock = 0;
	/** Side the mane falls on: "left", "right" or "upright". */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") FString HairSide;
	/** Mane length multiplier (foals: short). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") double ManeLength = 1;
	/** Tail length multiplier (foals: short). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") double TailLength = 1;
	/** [3D] Hair wave, 0 straight .. 1 wavy (hair.wave). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") double Wave = 0.5;
	/** [3D] Tail fullness, 0 thin .. 1 full (hair.tailFullness). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Hair") double TailFullness = 0.5;

	// ------------------------------------------------------------------ coat [mobile colours]
	/** Base colour from extension/agouti: "chestnut", "bay" or "black". */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FString Foundation;
	/** Cream doses 0..2 (palomino, buckskin or smoky black; two doses: cremello, perlino or smoky cream). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") int32 Cream = 0;
	/** Flaxen mane and tail applied (chestnut, ff, no cream). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") bool bFlaxen = false;
	/** Carries gray (G): whitens progressively from 36 months. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") bool bGray = false;
	/** Gray progress 0..1 already mixed into Body and Hair (0 before 36 months). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") double GrayProgress = 0;
	/** [3D] Carries dun (D). Not rendered on mobile: the colours below ignore it. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") bool bDun = false;
	/** [3D] Carries roan (R). Not rendered on mobile: the colours below ignore it. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") bool bRoan = false;
	/** [mobile] Body coat "#RRGGBB". */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FString Body;
	/** [mobile] Mane and tail "#RRGGBB". */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FString Hair;
	/** [mobile] Points (lower legs, muzzle, ear rims) "#RRGGBB"; never grayed, as on mobile. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FString Points;
	/** [mobile] Iris "#RRGGBB" (dark, amber or blue). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FString Eye;
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FColor BodyColor = FColor::Black;
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FColor HairColor = FColor::Black;
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FColor PointsColor = FColor::Black;
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Coat") FColor EyeColor = FColor::Black;

	// ------------------------------------------------------------------ white markings [mobile]
	/** Face marking mask 0..11 (mask.face). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") int32 Face = 0;
	/** Face marking extent 0..4 (0 none). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") int32 FaceExtent = 0;
	/** Sock extent 0..4 per leg: left fore, right fore, left hind, right hind. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") TArray<int32> Socks;
	/** Body pattern: "none", "patch" or "spot". */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") FString Pattern;
	/** Body pattern mask 0..9 (mask.body). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") int32 PatternId = 0;
	/** [3D] Body pattern extent 0..4 (extent.body). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") int32 PatternExtent = 0;
	/** [3D] Overlay mask 0..5 (mask.overlay), e.g. a secondary pattern layer. */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") int32 Overlay = 0;
	/** [3D] Sock edge mask 0..7 per leg, same order as Socks (mask.leftFore ..). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Markings") TArray<int32> SockMasks;

	// ------------------------------------------------------------------ behaviour
	/** [mobile] Card/idle pose 0..5 (temperament + seed). */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype") int32 Pose = 0;

	// ------------------------------------------------------------------ 3D morph targets
	/**
	 * [3D] Signed morph-target weights keyed by the locus they serve ("body.chest", "head.profile",
	 * "family.Light", "age.juvenile", ...): -1 at the low end of the locus range, 0 neutral, +1 at the high
	 * end. Trait weights exclude the family base and juvenile factors (those have their own family.* and
	 * age.juvenile weights). body.height is listed for completeness but is meant as skeleton scale.
	 */
	UPROPERTY(BlueprintReadOnly, Category = "Phenotype|Morphs") TMap<FName, double> MorphWeights;
};

/**
 * The 61-locus visual genome of the reference mobile implementation (src/render/visualGenome.ts), bit-identical:
 * same locus ids, allele domains, founder family anchor and inheritance draws. Alleles are stored as
 * integers; the enum loci decode with EnumValues (e.g. coat.extension 0 = "E", 1 = "e").
 */
namespace HRVisual
{
	inline constexpr int32 LocusCount = 61;
	inline constexpr const TCHAR* ArtVersion = TEXT("ribbon-prototype-1");

	/** The 61 locus ids in mobile VISUAL_LOCI order (sorted by UTF-16 code units). */
	ATELIERHORSERACING_API const TArray<FString>& Loci();
	/** Number of alleles of a locus (0 when unknown). Numeric loci take values 0 .. count - 1. */
	ATELIERHORSERACING_API int32 AlleleCount(const FString& Locus);
	/** Allele names of an enum locus (head.profile, hair.side, coat.*, individual.eye); nullptr otherwise. */
	ATELIERHORSERACING_API const TArray<FString>* EnumValues(const FString& Locus);

	/** visualGenome.ts draw(): FNV-1a over `${seed}:visual-v1:${tag}` + avalanche, reduced by modulo. */
	ATELIERHORSERACING_API uint32 Draw(const FString& Seed, const FString& Tag, uint32 Max);
	/** appearance.ts hash(): plain 32-bit FNV-1a over UTF-16 code units (no avalanche). */
	ATELIERHORSERACING_API uint32 AppearanceHash(const FString& Value);

	/**
	 * generateVisualGenome(seed, parents): founders draw from the seed (with one anchored family), foals
	 * take one allele per locus from each parent. Mother/Father may be null or miss a locus: that side is
	 * then drawn like a founder's, as on mobile.
	 */
	ATELIERHORSERACING_API TMap<FString, FHRGenePair> Generate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother = nullptr, const TMap<FString, FHRGenePair>* Father = nullptr);

	/** True when the genome holds all 61 visual loci. */
	ATELIERHORSERACING_API bool HasAllLoci(const TMap<FString, FHRGenePair>& Genome);

	/**
	 * Save migration: gives every horse that lacks visual loci the genome GenerateHorse would have given it
	 * (founders from their seed, foals from their parents, parents first). Existing loci are kept.
	 * Returns the number of horses completed.
	 */
	ATELIERHORSERACING_API int32 FillMissingLoci(FHRWorldState& S);

	/** resolveAppearance(horse, ageSteps) for the 3D horse. Missing loci use the mobile fallbacks. */
	ATELIERHORSERACING_API FHRPhenotype ResolvePhenotype(const FString& Seed, const TMap<FString, FHRGenePair>& Genome, int32 AgeSteps);
	ATELIERHORSERACING_API FHRPhenotype ResolvePhenotype(const FHRHorse& H, int32 AgeSteps);
	/** Phenotype on race day WorldT: the age is counted in horse months (HRClock::LifeMonths). */
	ATELIERHORSERACING_API FHRPhenotype ResolvePhenotypeAt(const FHRHorse& H, int32 WorldT);
}
