#include "HRRules.h"

#include "HRClock.h"

#include "HRRandom.h"
#include "HRVisualGenome.h"
#include "HRBreeds.h"

// Port of the reference generation.ts (genes, abilities, tissue zones, appearance, visual genome). Draw tags are
// identical, so the same seed gives the same genome and abilities as the reference implementation.

namespace
{
	const int64 GWeights[5] = {10, 20, 40, 20, 10};

	FHRGenePair Pair(const FString& Seed, const FString& Tag, TFunctionRef<bool(int32)> Filter)
	{
		TArray<FHRGenePair> Values;
		TArray<int64> Weights;
		for (int32 A = 0; A < 5; ++A)
			for (int32 B = 0; B < 5; ++B)
				if (Filter(A + B))
				{
					Values.Emplace(A, B);
					Weights.Add(GWeights[A] * GWeights[B]);
				}
		return Values[HRRandom::PickWeighted(Seed, Tag, Weights)];
	}

	FHRGenePair Pair(const FString& Seed, const FString& Tag)
	{
		return Pair(Seed, Tag, [](int32) { return true; });
	}

	const TCHAR* const GAbilityKeys[4] = {TEXT("acceleration"), TEXT("speed"), TEXT("endurance"), TEXT("composure")};

	int32 SumOf(const TMap<FString, FHRGenePair>& G, const FString& Key)
	{
		return (int32)G.FindChecked(Key).Sum();
	}
}

namespace HRRules
{
	FHRHorse GenerateHorse(const FGenerationOptions& O)
	{
		const FString& Seed = O.Seed;
		const FString& Origin = O.Origin;
		const int32 Slot = O.Slot;
		const bool bRobust = Origin == TEXT("rival") || Origin == TEXT("recovery") || Origin == TEXT("starter");
		TMap<FString, FHRGenePair> G;

		for (const TCHAR* A : GAbilityKeys)
		{
			G.Add(FString::Printf(TEXT("ceiling.%s"), A), Pair(Seed, FString::Printf(TEXT("ceiling.%s"), A)));
			G.Add(FString::Printf(TEXT("response.%s"), A), Pair(Seed, FString::Printf(TEXT("response.%s"), A)));
		}
		for (int32 Z = 0; Z < 4; ++Z)
		{
			if (bRobust)
			{
				// Finite weighted joint conditioning: no completed-horse rejection or gene repair.
				TArray<FIntVector4> Combos;
				TArray<int64> Weights;
				for (int32 A = 0; A < 5; ++A)
					for (int32 B = 0; B < 5; ++B)
						for (int32 C = 0; C < 5; ++C)
							for (int32 D = 0; D < 5; ++D)
								if (A + B + C + D >= 14)
								{
									Combos.Emplace(A, B, C, D);
									Weights.Add(GWeights[A] * GWeights[B] * GWeights[C] * GWeights[D]);
								}
				const FIntVector4 V = Combos[HRRandom::PickWeighted(Seed, FString::Printf(TEXT("body.%d"), Z), Weights)];
				G.Add(FString::Printf(TEXT("structureA.%d"), Z), FHRGenePair(V.X, V.Y));
				G.Add(FString::Printf(TEXT("structureB.%d"), Z), FHRGenePair(V.Z, V.W));
			}
			else
			{
				G.Add(FString::Printf(TEXT("structureA.%d"), Z), Pair(Seed, FString::Printf(TEXT("structureA.%d"), Z)));
				G.Add(FString::Printf(TEXT("structureB.%d"), Z), Pair(Seed, FString::Printf(TEXT("structureB.%d"), Z)));
			}
			for (const TCHAR* K : {TEXT("acute"), TEXT("adapt"), TEXT("recovery"), TEXT("inflammation")})
			{
				const FString Key = FString::Printf(TEXT("%s.%d"), K, Z);
				const FString KS = K;
				G.Add(Key, Pair(Seed, Key, [&](int32 S)
				{
					return !bRobust || (KS == TEXT("acute") ? S == 8 : KS == TEXT("recovery") ? S >= 6 : true);
				}));
			}
		}
		for (const TCHAR* K : {TEXT("maturity"), TEXT("longevity"), TEXT("stress")})
		{
			const FString KS = K;
			G.Add(KS, Pair(Seed, KS, [&](int32 S)
			{
				return KS != TEXT("longevity") || Origin == TEXT("foal") ||
					(Origin == TEXT("recovery") ? S <= 5 : S >= 3 && S <= 7);
			}));
		}
		{
			TArray<FHRGenePair> Risks = {FHRGenePair(0, 0), FHRGenePair(0, 1), FHRGenePair(1, 0)};
			TArray<int64> Weights = {81, 9, 9};
			if (!bRobust)
			{
				Risks.Emplace(1, 1);
				Weights.Add(1);
			}
			G.Add(TEXT("stifleRisk"), Risks[HRRandom::PickWeighted(Seed, TEXT("risk"), Weights)]);
		}
		G.Add(TEXT("signature"), FHRGenePair(HRRandom::Draw(Seed, TEXT("signature.a"), 6), HRRandom::Draw(Seed, TEXT("signature.b"), 6)));
		G.Add(TEXT("surface"), FHRGenePair(HRRandom::Draw(Seed, TEXT("surface.a"), 3), HRRandom::Draw(Seed, TEXT("surface.b"), 3)));
		G.Add(TEXT("surfaceFlex"), FHRGenePair(HRRandom::Draw(Seed, TEXT("flex.a"), 2), HRRandom::Draw(Seed, TEXT("flex.b"), 2)));
		for (const TCHAR* K : {TEXT("family"), TEXT("coat"), TEXT("marking"), TEXT("height"), TEXT("bulk"), TEXT("legs"), TEXT("head"), TEXT("hair")})
		{
			const FString Key = FString::Printf(TEXT("visual.%s"), K);
			G.Add(Key, Pair(Seed, Key));
		}

		if (Origin == TEXT("recovery"))
		{
			const bool bStrong = HRRandom::Draw(Seed, TEXT("recovery-branch"), 100) == 0;
			for (const TCHAR* A : GAbilityKeys)
				G.Add(FString::Printf(TEXT("ceiling.%s"), A), Pair(Seed, FString::Printf(TEXT("recovery.%s"), A),
					[&](int32 S) { return bStrong ? S >= 6 : S >= 1 && S <= 3; }));
		}
		if (Origin == TEXT("rival") && !O.Prospect.IsEmpty())
		{
			const bool bEstablished = O.Prospect == TEXT("established");
			for (const TCHAR* A : GAbilityKeys)
				G.Add(FString::Printf(TEXT("ceiling.%s"), A), Pair(Seed, FString::Printf(TEXT("world.%s"), A),
					[&](int32 S) { return bEstablished ? S >= 5 : S <= 4; }));
		}
		if (Origin == TEXT("recruit") && Slot == 3)
		{
			for (const TCHAR* A : GAbilityKeys)
				G.Add(FString::Printf(TEXT("ceiling.%s"), A), Pair(Seed, FString::Printf(TEXT("developed.%s"), A),
					[](int32 S) { return S >= 6; }));
		}
		if (Origin == TEXT("recruit") && Slot == 0)
		{
			G.Add(TEXT("response.composure"), Pair(Seed, TEXT("prospect.fast"), [](int32 S) { return S >= 6; }));
		}
		if (O.Mother && O.Father)
		{
			TArray<FString> Keys;
			G.GetKeys(Keys);
			for (const FString& Key : Keys)
			{
				const FHRGenePair* M = O.Mother->Genome.Find(Key);
				const FHRGenePair* F = O.Father->Genome.Find(Key);
				if (!M || !F)
				{
					continue;
				}
				G.Add(Key, FHRGenePair(
					(*M)[HRRandom::Draw(Seed, FString::Printf(TEXT("inherit.m.%s"), *Key), 2)],
					(*F)[HRRandom::Draw(Seed, FString::Printf(TEXT("inherit.f.%s"), *Key), 2)]));
			}
			if (HRRandom::Draw(Seed, TEXT("mutation"), 100) >= 98)
			{
				const FString Key = FString::Printf(TEXT("response.%s"), GAbilityKeys[HRRandom::Draw(Seed, TEXT("mutation.locus"), 4)]);
				const int32 Ix = HRRandom::Draw(Seed, TEXT("mutation.allele"), 2);
				FHRGenePair& P = G.FindChecked(Key);
				int32& V = Ix == 0 ? P.A : P.B;
				V += V == 0 ? 1 : V == 4 ? -1 : (HRRandom::Draw(Seed, TEXT("mutation.direction"), 2) ? 1 : -1);
			}
		}

		// The 61-locus visual genome (mobile visualGenome.ts), added after the inheritance above exactly as
		// mobile generateHorse does: founders draw it from the seed, foals take one allele from each parent.
		{
			const bool bParents = O.Mother && O.Father;
			// Replaced genes above leave free slots in the map; compacting first keeps the saved order canonical
			// (other genes, then the visual loci in locus order), the same order a migrated save gets.
			G.CompactStable();
			G.Append(HRVisual::Generate(Seed, bParents ? &O.Mother->Genome : nullptr, bParents ? &O.Father->Genome : nullptr));
			// The breed gene (HRBreeds.h), after the reference genome so the reference genes stay identical.
			G.Add(HRBreeds::Gene, HRBreeds::Generate(Seed, bParents ? &O.Mother->Genome : nullptr, bParents ? &O.Father->Genome : nullptr));
		}

		const int32 Longevity = SumOf(G, TEXT("longevity"));
		const int32 Career = Longevity >= 7 ? 9 : Longevity >= 5 ? 8 : Longevity >= 3 ? 7 : 6;
		// Ages are drawn in horse months (as the reference does), then counted in race days on the horse clock.
		int32 Age = Origin == TEXT("foal") ? 0 : (Origin == TEXT("recruit") && Slot == 0) ? 12 : 24;
		if (Origin == TEXT("rival") || (Origin == TEXT("recruit") && Slot == 3))
		{
			Age += HRRandom::Draw(Seed, TEXT("founder.age"), FMath::Max(1, Career * 12 - 23));
		}
		if (O.AgeSteps >= 0)
		{
			Age = O.AgeSteps;
		}
		const int32 BirthT = O.T - Age * HRClock::LifeMonth;
		static const double RivalDevelopment[3] = {0.75, 0.9, 1.0};
		const double Development = Age < 12 ? 0.65
			: (Origin == TEXT("recruit") && Slot >= 2) ? 1.0
			: Origin == TEXT("rival") ? RivalDevelopment[FMath::Min(2, Slot / 3)]
			: 0.75;

		FHRHorse H;
		H.Id = O.Id;
		H.Seed = Seed;
		H.OwnerId = O.OwnerId;
		H.Origin = Origin;
		H.Abilities.SetNum(4);
		H.Ceilings.SetNum(4);
		H.Response.SetNum(4);
		H.Progress.SetNumZeroed(4);
		for (int32 A = 0; A < 4; ++A)
		{
			H.Ceilings[A] = 2 + SumOf(G, FString::Printf(TEXT("ceiling.%s"), GAbilityKeys[A]));
			H.Abilities[A] = 1 + (int32)FMath::FloorToDouble((H.Ceilings[A] - 1) * Development);
			const int32 R = SumOf(G, FString::Printf(TEXT("response.%s"), GAbilityKeys[A]));
			H.Response[A] = R <= 2 ? 70 : R <= 5 ? 100 : 135;
		}
		const bool bStifle = SumOf(G, TEXT("stifleRisk")) == 2;
		for (int32 Z = 0; Z < 4; ++Z)
		{
			const double Risk = Z == 1 && bStifle ? 0.7 : 1.0;
			const int32 Adapt = SumOf(G, FString::Printf(TEXT("adapt.%d"), Z));
			const int32 Rec = SumOf(G, FString::Printf(TEXT("recovery.%d"), Z));
			static const double Offsets[4] = {-0.5, 0, 0, 0.5};
			static const double AcuteOffsets[4] = {-0.25, 0, 0, 0.25};
			const double Offset = Offsets[HRRandom::Draw(Seed, FString::Printf(TEXT("structure-offset.%d"), Z), 4)];
			const double AcuteOffset = AcuteOffsets[HRRandom::Draw(Seed, FString::Printf(TEXT("acute-offset.%d"), Z), 4)];
			FHRZone Zone;
			Zone.Structure = (int32)HRRandom::Round((12 + 2 * (SumOf(G, FString::Printf(TEXT("structureA.%d"), Z)) + SumOf(G, FString::Printf(TEXT("structureB.%d"), Z))) + Offset) * 10000 * Risk);
			Zone.Acute = (int32)HRRandom::Round((6 + SumOf(G, FString::Printf(TEXT("acute.%d"), Z)) + AcuteOffset) * 10000 * Risk);
			Zone.Recovery = (Rec <= 2 ? 3 : Rec <= 5 ? 5 : 7) * 10000;
			Zone.Adaptation = (int32)((Adapt <= 2 ? 0.25 : Adapt <= 5 ? 0.5 : 0.75) * 10000);
			Zone.InflammationGene = SumOf(G, FString::Printf(TEXT("inflammation.%d"), Z));
			H.Zones.Add(Zone);
		}

		const FHRGenePair Surface = G.FindChecked(TEXT("surface"));
		H.Favorite = Surface[HRRandom::Draw(Seed, TEXT("surface.selector"), 2)];
		TArray<int32> Others;
		for (int32 X = 0; X < 3; ++X)
			if (X != H.Favorite) Others.Add(X);
		H.Difficult = SumOf(G, TEXT("surfaceFlex")) == 2 ? Others[HRRandom::Draw(Seed, TEXT("difficult"), 2)] : H.Favorite;

		static const TCHAR* const Coats[9] = {TEXT("5b3526"), TEXT("9c633b"), TEXT("302b29"), TEXT("b08a5e"), TEXT("d4c6ad"),
			TEXT("696663"), TEXT("7f4127"), TEXT("e5dcc5"), TEXT("423b38")};
		static const TCHAR* const Manes[3] = {TEXT("241d1a"), TEXT("4e3525"), TEXT("d0b588")};
		H.Appearance.Family = FMath::Min(4, SumOf(G, TEXT("visual.family")) / 2);
		H.Appearance.Coat = Coats[SumOf(G, TEXT("visual.coat"))];
		H.Appearance.Mane = Manes[SumOf(G, TEXT("visual.hair")) / 3];
		H.Appearance.Marking = SumOf(G, TEXT("visual.marking")) / 2;
		H.Appearance.Height = SumOf(G, TEXT("visual.height")) / 8.f;
		H.Appearance.Bulk = SumOf(G, TEXT("visual.bulk")) / 8.f;
		H.Appearance.LegLength = SumOf(G, TEXT("visual.legs")) / 8.f;
		H.Appearance.Head = SumOf(G, TEXT("visual.head")) / 8.f;
		H.Appearance.Hair = SumOf(G, TEXT("visual.hair")) / 8.f;

		H.Name = HRContent::GeneratedHorseName(Seed);
		H.bMare = HRRandom::Draw(Seed, TEXT("sex"), 2) != 0;
		H.BirthT = BirthT;
		H.ReadyT = BirthT + HRClock::LifeYear;
		H.ScheduledRetirementT = BirthT + HRClock::LifeYear + Career * HRClock::LifeYear;
		H.NextBreedingT = O.T;
		H.Placement = (Origin == TEXT("recruit") || Origin == TEXT("recovery")) ? TEXT("offer") : TEXT("active");
		H.Condition = 3;
		H.Stress = SumOf(G, TEXT("stress"));
		H.Trait = HRContent::Traits()[G.FindChecked(TEXT("signature"))[HRRandom::Draw(Seed, TEXT("signature.selector"), 2)]];
		if (O.Mother && O.Father)
		{
			H.Parents = {O.Mother->Id, O.Father->Id};
			H.Generation = 1 + FMath::Max(O.Mother->Generation, O.Father->Generation);
		}
		H.Genome = MoveTemp(G);
		if (!O.OwnerId.IsEmpty() && O.OwnerId != TEXT("market"))
		{
			H.Owners.Add(O.OwnerId);
		}
		return H;
	}

	FHRHorse& AddHorse(FHRWorldState& S, FHRHorse&& H)
	{
		// Open-addressed selection over the whole vocabulary: no numeric suffix (mobile uniqueHorseName).
		TSet<FString> Used;
		for (const TPair<FString, FHRHorse>& It : S.Horses)
		{
			Used.Add(HRContent::NormalizeName(It.Value.Name));
		}
		if (Used.Contains(HRContent::NormalizeName(H.Name)))
		{
			const TArray<FString>& Pool = HRContent::HorseNamePool();
			const int32 Start = HRRandom::Draw(H.Seed, TEXT("horse-name:living-v1"), Pool.Num());
			FString Chosen = Pool[Start];
			for (int32 Attempt = 0; Attempt < Pool.Num(); ++Attempt)
			{
				const FString& Candidate = Pool[(Start + Attempt) % Pool.Num()];
				if (!Used.Contains(HRContent::NormalizeName(Candidate)))
				{
					Chosen = Candidate;
					break;
				}
			}
			H.Name = Chosen;
		}
		const FString Id = H.Id;
		return S.Horses.Add(Id, MoveTemp(H));
	}
}
