#pragma once

#include "HRTypes.h"

struct FHRPhenotype;

/** Mesh-independent breed inheritance. Visual genes never alter competitive abilities. */
namespace HRBreeds
{
    inline constexpr const TCHAR* Gene = TEXT("breed");
    inline constexpr int32 AlleleCount = 4;

    /** Alleles: Standard, Giant, Bone, Spirit. Invalid alleles fail explicitly. */
    ATELIERHORSERACING_API const TCHAR* AlleleName(int32 Allele);
    /** Giant is dominant; Bone/Spirit need two copies. An absent gene expresses Standard.
     * Invalid alleles return false without changing Out. */
    ATELIERHORSERACING_API bool TryExpress(const FHRGenePair* Pair, FString& Out);
    /** One inherited allele per parent; an absent parent gene uses the founder distribution.
     * Invalid parent alleles or output aliasing any parent gene return false without changing Out.
     * Does not mutate either genome. */
    ATELIERHORSERACING_API bool TryGenerate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother,
        const TMap<FString, FHRGenePair>* Father, FHRGenePair& Out);
    /** Internal rule convenience over validated gene pairs and genomes; invalid alleles fail explicitly. */
    ATELIERHORSERACING_API FString Express(const FHRGenePair* Pair);
    ATELIERHORSERACING_API FString Express(const TMap<FString, FHRGenePair>& Genome);
    ATELIERHORSERACING_API FHRGenePair Generate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother,
        const TMap<FString, FHRGenePair>* Father);
    /** Save migration: gives the breed gene to every horse without it (parents first). Returns the horses completed. */
    ATELIERHORSERACING_API int32 FillMissing(FHRWorldState& S);
    /** Uniform scale of an individual against its breed's neutral adult: 1 +- 0.2 from body.height, foals smaller. */
    ATELIERHORSERACING_API float IndividualScale(const FHRPhenotype& P);
}
