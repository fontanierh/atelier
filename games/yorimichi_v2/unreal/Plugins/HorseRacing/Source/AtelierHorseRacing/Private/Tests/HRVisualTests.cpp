#include "HRBreeds.h"
#include "HRTestUtil.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

namespace
{
	TMap<FString, FHRGenePair> GenomeFromJson(const TSharedPtr<FJsonObject>& Object)
	{
		TMap<FString, FHRGenePair> G;
		for (const TPair<FString, TSharedPtr<FJsonValue>>& It : Object->Values)
		{
			const TArray<TSharedPtr<FJsonValue>>& V = It.Value->AsArray();
			G.Add(It.Key, FHRGenePair((int32)V[0]->AsNumber(), (int32)V[1]->AsNumber()));
		}
		return G;
	}

	/** Compares one C++ phenotype with one reference Appearance (key and version excluded). */
	struct FAppearanceCheck
	{
		FAutomationTestBase& Test;
		double MaxDiff = 0;
		int32 Values = 0;

		void Number(const FString& What, double Mine, const TSharedPtr<FJsonObject>& A, const TCHAR* Field)
		{
			const double Diff = FMath::Abs(Mine - A->GetNumberField(Field));
			MaxDiff = FMath::Max(MaxDiff, Diff);
			Values++;
			if (Diff > 1e-12) Test.AddError(FString::Printf(TEXT("%s %s: %.17g, reference %.17g"), *What, Field, Mine, A->GetNumberField(Field)));
		}
		void Text(const FString& What, const FString& Mine, const TSharedPtr<FJsonObject>& A, const TCHAR* Field)
		{
			Values++;
			if (!Mine.Equals(A->GetStringField(Field), ESearchCase::CaseSensitive))
				Test.AddError(FString::Printf(TEXT("%s %s: %s, reference %s"), *What, Field, *Mine, *A->GetStringField(Field)));
		}
		void All(const FString& What, const FHRPhenotype& P, const TSharedPtr<FJsonObject>& A)
		{
			Text(What, P.FamilyName, A, TEXT("family"));
			Text(What, P.Body, A, TEXT("body"));
			Text(What, P.Hair, A, TEXT("hair"));
			Text(What, P.Points, A, TEXT("points"));
			Text(What, P.Eye, A, TEXT("eye"));
			Text(What, P.Pattern, A, TEXT("pattern"));
			Text(What, P.HairSide, A, TEXT("hairSide"));
			Number(What, P.Height, A, TEXT("height"));
			Number(What, P.Length, A, TEXT("length"));
			Number(What, P.Barrel, A, TEXT("barrel"));
			Number(What, P.Legs, A, TEXT("legs"));
			Number(What, P.Bone, A, TEXT("bone"));
			Number(What, P.Neck, A, TEXT("neck"));
			Number(What, P.NeckWidth, A, TEXT("neckWidth"));
			Number(What, P.Head, A, TEXT("head"));
			Number(What, P.Muzzle, A, TEXT("muzzle"));
			Number(What, P.Ears, A, TEXT("ears"));
			Number(What, P.Mane, A, TEXT("mane"));
			Number(What, P.Tail, A, TEXT("tail"));
			Number(What, P.ManeLength, A, TEXT("maneLength"));
			Number(What, P.TailLength, A, TEXT("tailLength"));
			Number(What, P.Face, A, TEXT("face"));
			Number(What, P.FaceExtent, A, TEXT("faceExtent"));
			Number(What, P.PatternId, A, TEXT("patternId"));
			Number(What, P.Juvenile, A, TEXT("juvenile"));
			Number(What, P.Pose, A, TEXT("pose"));
			Number(What, P.Profile, A, TEXT("profile"));
			Number(What, P.Chest, A, TEXT("chest"));
			Number(What, P.Hindquarter, A, TEXT("hindquarter"));
			Number(What, P.HeadWidth, A, TEXT("headWidth"));
			Number(What, P.Jaw, A, TEXT("jaw"));
			Number(What, P.EarSpread, A, TEXT("earSpread"));
			Number(What, P.EyeSpacing, A, TEXT("eyeSpacing"));
			Number(What, P.EyeHeight, A, TEXT("eyeHeight"));
			Number(What, P.NeckArch, A, TEXT("neckArch"));
			Number(What, P.Carriage, A, TEXT("carriage"));
			Number(What, P.Forelock, A, TEXT("forelock"));
			const TArray<TSharedPtr<FJsonValue>>& Socks = A->GetArrayField(TEXT("socks"));
			Values++;
			bool bSocks = Socks.Num() == 4 && P.Socks.Num() == 4;
			for (int32 I = 0; bSocks && I < 4; ++I) bSocks = P.Socks[I] == (int32)Socks[I]->AsNumber();
			if (!bSocks) Test.AddError(What + TEXT(" socks differ"));
			// 3D-only invariants.
			double FamilySum = 0;
			for (const double W : P.FamilyWeights) FamilySum += W;
			if (FMath::Abs(FamilySum - 1) > 1e-9) Test.AddError(What + TEXT(" family weights do not sum to 1"));
			for (const TPair<FName, double>& W : P.MorphWeights)
			{
				if (W.Value < -1 - 1e-9 || W.Value > 1 + 1e-9) Test.AddError(FString::Printf(TEXT("%s morph %s out of range: %f"), *What, *W.Key.ToString(), W.Value));
			}
		}
	};
}

// The 61-locus visual genome and the resolved appearance match the reference implementation exactly
// (vectors exported from its visualGenome.ts and appearance.ts). Ages here are in horse months.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRVisualParityTest, "Atelier.HorseRacing.Parity.Visual", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRVisualParityTest::RunTest(const FString&)
{
	const TSharedPtr<FJsonObject> P = HRTest::LoadParity(TEXT("reference-visual-parity.json"));
	if (!TestNotNull(TEXT("visual parity file"), P.Get())) return false;

	const TArray<TSharedPtr<FJsonValue>>& Loci = P->GetArrayField(TEXT("loci"));
	TestEqual(TEXT("locus count"), HRVisual::Loci().Num(), HRVisual::LocusCount);
	TestEqual(TEXT("reference locus count"), Loci.Num(), HRVisual::LocusCount);
	for (int32 I = 0; I < FMath::Min(Loci.Num(), HRVisual::Loci().Num()); ++I)
	{
		TestTrue(FString::Printf(TEXT("locus %d order"), I), HRVisual::Loci()[I].Equals(Loci[I]->AsString(), ESearchCase::CaseSensitive));
	}

	FAppearanceCheck Check{*this};
	TMap<FString, TMap<FString, FHRGenePair>> Genomes;
	int32 Genes = 0, Foals = 0;
	for (const TSharedPtr<FJsonValue>& V : P->GetArrayField(TEXT("cases")))
	{
		const TSharedPtr<FJsonObject> C = V->AsObject();
		const FString Seed = C->GetStringField(TEXT("seed"));
		const TMap<FString, FHRGenePair> Reference = GenomeFromJson(C->GetObjectField(TEXT("genome")));
		TMap<FString, FHRGenePair> Mine;
		const TArray<TSharedPtr<FJsonValue>>* Parents = nullptr;
		if (C->TryGetArrayField(TEXT("parents"), Parents))
		{
			const TMap<FString, FHRGenePair>* M = Genomes.Find((*Parents)[0]->AsString());
			const TMap<FString, FHRGenePair>* F = Genomes.Find((*Parents)[1]->AsString());
			if (!TestTrue(Seed + TEXT(" parents known"), M && F)) continue;
			Mine = HRVisual::Generate(Seed, M, F);
			Foals++;
		}
		else if (Reference.Num() > 0)
		{
			Mine = HRVisual::Generate(Seed);
		}
		// The 'empty' case checks the fallbacks of a genome without visual loci.
		TestTrue(Seed + TEXT(" identical visual genome"), HRTest::SameGenes(Mine, Reference));
		Genes += Mine.Num();
		Genomes.Add(Seed, Mine);

		const TArray<TSharedPtr<FJsonValue>>& Ages = C->GetArrayField(TEXT("ages"));
		const TArray<TSharedPtr<FJsonValue>>& Appearances = C->GetArrayField(TEXT("appearances"));
		for (int32 I = 0; I < Ages.Num(); ++I)
		{
			const int32 Age = (int32)Ages[I]->AsNumber();
			Check.All(FString::Printf(TEXT("%s@%d"), *Seed, Age), HRVisual::ResolvePhenotype(Seed, Mine, Age), Appearances[I]->AsObject());
		}
	}

	// The five horses of reference-parity.json, generated here by GenerateHorse.
	const TArray<FHRHorse> Horses = HRTest::MakeParityHorses();
	const TArray<TSharedPtr<FJsonValue>>& RefHorses = P->GetArrayField(TEXT("horses"));
	TestEqual(TEXT("parity horses"), RefHorses.Num(), Horses.Num());
	for (int32 H = 0; H < FMath::Min(Horses.Num(), RefHorses.Num()); ++H)
	{
		const TSharedPtr<FJsonObject> X = RefHorses[H]->AsObject();
		TestEqual(TEXT("parity horse seed"), Horses[H].Seed, X->GetStringField(TEXT("seed")));
		const TArray<TSharedPtr<FJsonValue>>& Ages = X->GetArrayField(TEXT("ages"));
		const TArray<TSharedPtr<FJsonValue>>& Appearances = X->GetArrayField(TEXT("appearances"));
		for (int32 I = 0; I < Ages.Num(); ++I)
		{
			const int32 Age = (int32)Ages[I]->AsNumber();
			Check.All(FString::Printf(TEXT("%s@%d"), *Horses[H].Id, Age), HRVisual::ResolvePhenotype(Horses[H], Age), Appearances[I]->AsObject());
		}
	}
	AddInfo(FString::Printf(TEXT("%d visual genomes (%d foals, %d allele pairs) and %d appearance values compared; max numeric difference %.3g"),
		Genomes.Num(), Foals, Genes, Check.Values, Check.MaxDiff));
	return true;
}


// Every horse of a living world carries the 61 loci: founders from their seed, foals one allele from each parent; a save
// without them gains exactly the loci GenerateHorse gives today.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRVisualInheritanceTest, "Atelier.HorseRacing.Visual.Inheritance", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRVisualInheritanceTest::RunTest(const FString&)
{
	FHRWorldState S = HRRules::CreateWorld(TEXT("visual-inheritance"));
	for (int32 Day = 0; Day < 36; ++Day) HRRules::AdvanceDay(S);
	TestEqual(TEXT("new worlds use the current rules"), S.RulesVersion, FString(HRRules::RulesVersion));
	int32 Foals = 0;
	for (const TPair<FString, FHRHorse>& It : S.Horses)
	{
		const FHRHorse& H = It.Value;
		TestTrue(H.Id + TEXT(" has the visual loci"), HRVisual::HasAllLoci(H.Genome));
		const TMap<FString, FHRGenePair> Visual = HRTest::VisualOnly(H.Genome);
		if (H.Parents.Num() == 2)
		{
			const FHRHorse& M = S.Horses.FindChecked(H.Parents[0]);
			const FHRHorse& F = S.Horses.FindChecked(H.Parents[1]);
			TestTrue(H.Id + TEXT(" inherits its visual loci"), HRTest::SameGenes(Visual, HRVisual::Generate(H.Seed, &M.Genome, &F.Genome)));
			for (const TPair<FString, FHRGenePair>& G : Visual)
			{
				const FHRGenePair& PM = M.Genome[G.Key];
				const FHRGenePair& PF = F.Genome[G.Key];
				TestTrue(H.Id + TEXT(" one allele from each parent"), (G.Value.A == PM.A || G.Value.A == PM.B) && (G.Value.B == PF.A || G.Value.B == PF.B));
			}
			Foals++;
		}
		else
		{
			TestTrue(H.Id + TEXT(" founder visual loci from its seed"), HRTest::SameGenes(Visual, HRVisual::Generate(H.Seed)));
		}
	}
	TestTrue(TEXT("the world has foals"), Foals > 0);

	// A save without the visual loci and the breed gene gains exactly what the generator gives today.
	const FString Expected = HRTest::ToJson(S);
	FHRWorldState Old = S;
	for (TPair<FString, FHRHorse>& It : Old.Horses)
	{
		TMap<FString, FHRGenePair> Kept;
		for (const TPair<FString, FHRGenePair>& G : It.Value.Genome)
			if (!HRVisual::Loci().Contains(G.Key) && G.Key != HRBreeds::Gene) Kept.Add(G.Key, G.Value);
		It.Value.Genome = MoveTemp(Kept);
	}
	TestEqual(TEXT("every horse completed"), HRVisual::FillMissingLoci(Old), Old.Horses.Num());
	HRBreeds::FillMissing(Old);
	TestTrue(TEXT("the migration rebuilds the same genomes"), HRTest::ToJson(Old) == Expected);
	TestEqual(TEXT("a complete save is left alone"), HRVisual::FillMissingLoci(S), 0);
	return true;
}

// Unrelated horses differ; relatives resemble one another (finite sample, not a perception test).
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRVisualDiversityTest, "Atelier.HorseRacing.Visual.Diversity", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRVisualDiversityTest::RunTest(const FString&)
{
	auto Distance = [](const TMap<FString, FHRGenePair>& A, const TMap<FString, FHRGenePair>& B)
	{
		int32 Shared = 0, Total = 0;
		for (const FString& Id : HRVisual::Loci())
		{
			const FHRGenePair X = A[Id], Y = B[Id];
			Shared += (X.A == Y.A || X.A == Y.B) + (X.B == Y.A || X.B == Y.B);
			Total += 2;
		}
		return 1.0 - (double)Shared / Total;
	};
	TArray<TMap<FString, FHRGenePair>> Founders;
	for (int32 I = 0; I < 24; ++I) Founders.Add(HRVisual::Generate(FString::Printf(TEXT("diversity-%d"), I)));
	double Unrelated = 0, Siblings = 0;
	int32 NU = 0, NS = 0;
	TSet<int32> FamiliesSeen;
	for (int32 I = 0; I < Founders.Num(); ++I)
	{
		FamiliesSeen.Add(HRVisual::ResolvePhenotype(FString::Printf(TEXT("diversity-%d"), I), Founders[I], 48).Family);
		for (int32 J = I + 1; J < Founders.Num(); ++J, ++NU) Unrelated += Distance(Founders[I], Founders[J]);
	}
	for (int32 Pair = 0; Pair + 1 < Founders.Num(); Pair += 2)
	{
		const TMap<FString, FHRGenePair> A = HRVisual::Generate(FString::Printf(TEXT("sib-%d-a"), Pair), &Founders[Pair], &Founders[Pair + 1]);
		const TMap<FString, FHRGenePair> B = HRVisual::Generate(FString::Printf(TEXT("sib-%d-b"), Pair), &Founders[Pair], &Founders[Pair + 1]);
		Siblings += Distance(A, B);
		NS++;
	}
	Unrelated /= NU;
	Siblings /= NS;
	AddInfo(FString::Printf(TEXT("Allele-sharing distance: unrelated founders %.3f, full siblings %.3f; %d body families among 24 founders."), Unrelated, Siblings, FamiliesSeen.Num()));
	TestTrue(TEXT("siblings share more visual alleles than unrelated horses"), Siblings < Unrelated);
	TestTrue(TEXT("founders span several body families"), FamiliesSeen.Num() >= 4);
	TestTrue(TEXT("deterministic genome"), HRTest::SameGenes(HRVisual::Generate(TEXT("again")), HRVisual::Generate(TEXT("again"))));
	return true;
}

// The breed gene: dominance, founder rarity, inheritance and migration.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FHRBreedGeneticsTest, "Atelier.HorseRacing.Breeds.Genetics", EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FHRBreedGeneticsTest::RunTest(const FString&)
{
	auto Pair = [](int32 A, int32 B) { return FHRGenePair(A, B); };
	TestEqual(TEXT("no gene = Standard"), HRBreeds::Express(nullptr), FString(TEXT("Standard")));
	FHRGenePair P = Pair(0, 1);
	TestEqual(TEXT("Giant dominant"), HRBreeds::Express(&P), FString(TEXT("Giant")));
	P = Pair(2, 0);
	TestEqual(TEXT("a Bone carrier looks Standard"), HRBreeds::Express(&P), FString(TEXT("Standard")));
	P = Pair(3, 1);
	TestEqual(TEXT("a Spirit carrier with Giant looks Giant"), HRBreeds::Express(&P), FString(TEXT("Giant")));
	P = Pair(3, 3);
	TestEqual(TEXT("two Spirit alleles"), HRBreeds::Express(&P), FString(TEXT("Spirit")));

	TMap<FString, int32> Count;
	const int32 N = 4000;
	for (int32 I = 0; I < N; ++I)
	{
		const FHRGenePair G = HRBreeds::Generate(FString::Printf(TEXT("breed-founder-%d"), I), nullptr, nullptr);
		Count.FindOrAdd(HRBreeds::Express(&G))++;
	}
	const float Giant = Count.FindRef(TEXT("Giant")) / (float)N, Rare = (Count.FindRef(TEXT("Bone")) + Count.FindRef(TEXT("Spirit"))) / (float)N;
	AddInfo(FString::Printf(TEXT("founders: %d Standard, %d Giant, %d Bone, %d Spirit"), Count.FindRef(TEXT("Standard")), Count.FindRef(TEXT("Giant")), Count.FindRef(TEXT("Bone")), Count.FindRef(TEXT("Spirit"))));
	TestTrue(TEXT("Giants are common (15-30 %)"), Giant > 0.15f && Giant < 0.30f);
	TestTrue(TEXT("the rare breeds are rare but exist (0.3-3 %)"), Rare > 0.003f && Rare < 0.03f);

	FHRWorldState S = HRRules::CreateWorld(TEXT("breed-genetics"));
	for (int32 Day = 0; Day < 36; ++Day) HRRules::AdvanceDay(S);
	int32 Foals = 0;
	for (const TPair<FString, FHRHorse>& It : S.Horses)
	{
		const FHRHorse& H = It.Value;
		const FHRGenePair* G = H.Genome.Find(HRBreeds::Gene);
		if (!TestNotNull(H.Id + TEXT(" has the breed gene"), G)) continue;
		if (H.Parents.Num() != 2) continue;
		const FHRGenePair* M = S.Horses[H.Parents[0]].Genome.Find(HRBreeds::Gene);
		const FHRGenePair* F = S.Horses[H.Parents[1]].Genome.Find(HRBreeds::Gene);
		if (!M || !F) continue;
		TestTrue(H.Id + TEXT(" one breed allele from each parent"), (G->A == M->A || G->A == M->B) && (G->B == F->A || G->B == F->B));
		Foals++;
	}
	TestTrue(TEXT("the world has foals"), Foals > 0);

	// A save without the gene receives exactly the genes the generator gives today.
	const FString Expected = HRTest::ToJson(S);
	FHRWorldState Old = S;
	for (TPair<FString, FHRHorse>& It : Old.Horses) It.Value.Genome.Remove(HRBreeds::Gene);
	TestEqual(TEXT("every horse completed"), HRBreeds::FillMissing(Old), Old.Horses.Num());
	TestTrue(TEXT("migration rebuilds the same breed genes"), HRTest::ToJson(Old) == Expected);

	// The look's scale: +-20 % around the breed's neutral adult, foals scaled down.
	const FHRHorse& Any = S.Horses.CreateConstIterator()->Value;
	const float Adult = HRBreeds::IndividualScale(HRVisual::ResolvePhenotype(Any, 48));
	const float Newborn = HRBreeds::IndividualScale(HRVisual::ResolvePhenotype(Any, 0));
	TestTrue(TEXT("adult scale within +-20 %"), Adult >= 0.8f && Adult <= 1.2f);
	TestTrue(TEXT("a newborn smaller than its adult self"), Newborn < Adult && Newborn >= 0.45f);
	return true;
}

#endif
