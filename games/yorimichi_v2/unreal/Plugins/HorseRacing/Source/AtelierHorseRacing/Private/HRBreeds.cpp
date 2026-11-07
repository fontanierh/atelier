#include "HRBreeds.h"
#include "HRRandom.h"
#include "HRVisualGenome.h"

namespace HRBreedsPrivate
{
    const TCHAR* const Alleles[] = {TEXT("Standard"), TEXT("Giant"), TEXT("Bone"), TEXT("Spirit")};
    const TArray<int64> FounderWeights = {74, 12, 7, 7};

    bool Valid(const FHRGenePair* Pair)
    {
        return !Pair || (Pair->A >= 0 && Pair->A < HRBreeds::AlleleCount &&
            Pair->B >= 0 && Pair->B < HRBreeds::AlleleCount);
    }
}

const TCHAR* HRBreeds::AlleleName(int32 Allele)
{
    if (Allele < 0 || Allele >= AlleleCount)
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing breed allele must be in 0..3"));
    return HRBreedsPrivate::Alleles[Allele];
}

bool HRBreeds::TryExpress(const FHRGenePair* Pair, FString& Out)
{
    if (!HRBreedsPrivate::Valid(Pair)) return false;
    const int32 Allele = !Pair ? 0 : Pair->A == Pair->B ? Pair->A :
        (Pair->A == 1 || Pair->B == 1) ? 1 : 0;
    Out = AlleleName(Allele);
    return true;
}

bool HRBreeds::TryGenerate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother,
    const TMap<FString, FHRGenePair>* Father, FHRGenePair& Out)
{
    // Output may be any gene value, not only the breed entry used below.
    for (const auto* Genome : {Mother, Father})
        if (Genome)
            for (const auto& Entry : *Genome)
                if (&Entry.Value == &Out) return false;
    const FHRGenePair* Parents[] = {Mother ? Mother->Find(Gene) : nullptr, Father ? Father->Find(Gene) : nullptr};
    if (!HRBreedsPrivate::Valid(Parents[0]) || !HRBreedsPrivate::Valid(Parents[1])) return false;
    int32 Alleles[2];
    for (int32 Side = 0; Side < 2; ++Side)
    {
        Alleles[Side] = Parents[Side]
            ? (*Parents[Side])[HRRandom::Draw(Seed, FString::Printf(TEXT("inherit.breed.%d"), Side), 2)]
            : HRRandom::PickWeighted(Seed, FString::Printf(TEXT("breed.%d"), Side), HRBreedsPrivate::FounderWeights);
    }
    Out = FHRGenePair(Alleles[0], Alleles[1]);
    return true;
}

FString HRBreeds::Express(const FHRGenePair* Pair)
{
    FString Out;
    if (!TryExpress(Pair, Out))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing Express requires valid breed alleles; validate with TryExpress"));
    return Out;
}

FString HRBreeds::Express(const TMap<FString, FHRGenePair>& Genome)
{
    return Express(Genome.Find(Gene));
}

FHRGenePair HRBreeds::Generate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother,
    const TMap<FString, FHRGenePair>* Father)
{
    FHRGenePair Out;
    if (!TryGenerate(Seed, Mother, Father, Out))
        UE_LOG(LogTemp, Fatal, TEXT("HorseRacing Generate requires valid parent breed alleles; validate with TryGenerate"));
    return Out;
}

int32 HRBreeds::FillMissing(FHRWorldState& S)
{
    TArray<FString> Ids;
    S.Horses.GetKeys(Ids);
    Ids.Sort([&S](const FString& A, const FString& B)
    {
        const int32 BA = S.Horses[A].BirthT, BB = S.Horses[B].BirthT;
        return BA != BB ? BA < BB : A.Compare(B, ESearchCase::CaseSensitive) < 0;
    });
    TSet<FString> Done;
    int32 Filled = 0;
    TFunction<void(const FString&)> Complete = [&](const FString& Id)
    {
        bool bSeen = false;
        Done.Add(Id, &bSeen);
        if (bSeen || !S.Horses.Contains(Id) || S.Horses[Id].Genome.Contains(Gene)) return;
        const TArray<FString> ParentIds = S.Horses[Id].Parents;
        const FHRHorse* M = nullptr;
        const FHRHorse* F = nullptr;
        if (ParentIds.Num() == 2)
        {
            Complete(ParentIds[0]);
            Complete(ParentIds[1]);
            M = S.Horses.Find(ParentIds[0]);
            F = S.Horses.Find(ParentIds[1]);
        }
        FHRHorse& H = S.Horses[Id];
        H.Genome.Add(Gene, Generate(H.Seed, M ? &M->Genome : nullptr, F ? &F->Genome : nullptr));
        Filled++;
    };
    for (const FString& Id : Ids) Complete(Id);
    return Filled;
}

float HRBreeds::IndividualScale(const FHRPhenotype& P)
{
    const double* W = P.MorphWeights.Find(TEXT("body.height"));
    const float Height = W ? FMath::Clamp((float)*W, -1.f, 1.f) : 0.f;
    return (1.f + 0.2f * Height) * (1.f - 0.4f * (float)P.Juvenile);
}
