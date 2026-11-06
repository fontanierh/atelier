#pragma once

// Shared helpers of the horse racing automation tests (reference vectors exported from the TypeScript implementation).

#include "CoreMinimal.h"
#include "HRRules.h"
#include "HRSave.h"
#include "HRVisualGenome.h"
#include "Dom/JsonObject.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace HRTest
{
	/** A reference vector file from the plugin's Tests folder. */
	inline TSharedPtr<FJsonObject> LoadParity(const TCHAR* File)
	{
		const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("HorseRacing"));
		FString Text;
		if (!Plugin || !FFileHelper::LoadFileToString(Text, *FPaths::Combine(Plugin->GetBaseDir(), TEXT("Tests"), File)))
		{
			return nullptr;
		}
		TSharedPtr<FJsonObject> Root;
		FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root);
		return Root;
	}

	inline FString ToJson(const FHRWorldState& S)
	{
		return HRSave::ToJson(S);
	}

	/** The race day each reference horse was generated on (founders 0, the foal 5, the market horses 3). */
	inline const int32 ParityDays[5] = {0, 0, 5, 3, 3};

	/** The five horses of reference-parity.json, generated with the same options as the reference. */
	inline TArray<FHRHorse> MakeParityHorses()
	{
		auto Make = [](const TCHAR* Id, const TCHAR* Owner, int32 T, const TCHAR* Origin, int32 Slot, int32 Age, const TCHAR* Prospect)
		{
			HRRules::FGenerationOptions O;
			O.Id = Id;
			O.Seed = FString::Printf(TEXT("haras-1:%s"), Id);
			O.OwnerId = Owner;
			O.T = T;
			O.Origin = Origin;
			O.Slot = Slot;
			O.AgeSteps = Age;
			O.Prospect = Prospect;
			return O;
		};
		const FHRHorse A = HRRules::GenerateHorse(Make(TEXT("riv_aulnes:founder:0"), TEXT("riv_aulnes"), 0, TEXT("rival"), 8, 20, TEXT("established")));
		const FHRHorse B = HRRules::GenerateHorse(Make(TEXT("riv_x:founder:1"), TEXT("riv_x"), 0, TEXT("rival"), 4, 30, TEXT("")));
		HRRules::FGenerationOptions FoalO = Make(TEXT("riv_x:foal:5"), TEXT("riv_x"), 5, TEXT("foal"), 0, -1, TEXT(""));
		FoalO.Mother = A.bMare ? &A : &B;
		FoalO.Father = A.bMare ? &B : &A;
		const FHRHorse C = HRRules::GenerateHorse(FoalO);
		const FHRHorse D = HRRules::GenerateHorse(Make(TEXT("m:board:3:1"), TEXT("market"), 3, TEXT("recruit"), 1, -1, TEXT("")));
		const FHRHorse E = HRRules::GenerateHorse(Make(TEXT("m:recovery:3"), TEXT("market"), 3, TEXT("recovery"), 0, -1, TEXT("")));
		return {A, B, C, D, E};
	}

	inline TMap<FString, FHRGenePair> VisualOnly(const TMap<FString, FHRGenePair>& Genome)
	{
		TMap<FString, FHRGenePair> Out;
		for (const FString& Id : HRVisual::Loci())
			if (const FHRGenePair* P = Genome.Find(Id)) Out.Add(Id, *P);
		return Out;
	}

	inline bool SameGenes(const TMap<FString, FHRGenePair>& A, const TMap<FString, FHRGenePair>& B)
	{
		if (A.Num() != B.Num()) return false;
		for (const TPair<FString, FHRGenePair>& It : A)
		{
			const FHRGenePair* P = B.Find(It.Key);
			if (!P || P->A != It.Value.A || P->B != It.Value.B) return false;
		}
		return true;
	}

	/** Every horse of one stable entered today. */
	inline int32 EntriesOf(const FHRWorldState& S, const FString& StableId)
	{
		int32 N = 0;
		for (const FHRRace& R : S.Meeting.Races)
			for (const FHRRunner& E : R.Entries) N += E.StableId == StableId ? 1 : 0;
		return N;
	}
}

#endif
