#include "HRVisualGenome.h"

#include "HRBreeds.h"
#include "HRClock.h"

#include "Misc/Parse.h"

// Port of the reference mobile implementation src/render/visualGenome.ts (generateVisualGenome) and
// src/render/appearance.ts (resolveAppearance). Draw tags, allele domains and arithmetic follow the
// TypeScript line by line; Atelier.HorseRacing.Parity.Visual compares both implementations.

// Bit-for-bit floating point parity with JavaScript: never fuse a*b+c into one FMA instruction.
#if defined(__clang__)
#pragma clang fp contract(off)
#elif defined(_MSC_VER)
#pragma fp_contract(off)
#endif

namespace
{
	const TCHAR* const GFamilies[5] = {TEXT("Light"), TEXT("Runner"), TEXT("Balanced"), TEXT("Endurance"), TEXT("Powerful")};

	/** Allele weights per locus (mobile `domains`). */
	const TMap<FString, TArray<int32>>& Domains()
	{
		static const TMap<FString, TArray<int32>> Table = []
		{
			TMap<FString, TArray<int32>> T;
			TArray<FString> Quantitative;
			for (const TCHAR* F : GFamilies)
			{
				Quantitative.Add(FString::Printf(TEXT("family.%s.a"), F));
				Quantitative.Add(FString::Printf(TEXT("family.%s.b"), F));
			}
			for (const TCHAR* K : {TEXT("height"), TEXT("length"), TEXT("chest"), TEXT("barrel"), TEXT("hindquarter"), TEXT("leg"), TEXT("boneSubstance")})
				Quantitative.Add(FString::Printf(TEXT("body.%s"), K));
			for (const TCHAR* K : {TEXT("length"), TEXT("thickness"), TEXT("arch"), TEXT("carriage")})
				Quantitative.Add(FString::Printf(TEXT("neck.%s"), K));
			for (const TCHAR* K : {TEXT("length"), TEXT("forehead"), TEXT("muzzle"), TEXT("jaw"), TEXT("earLength"), TEXT("earSpread"), TEXT("eyeHeight"), TEXT("eyeSpacing")})
				Quantitative.Add(FString::Printf(TEXT("head.%s"), K));
			for (const TCHAR* K : {TEXT("maneLength"), TEXT("tailLength"), TEXT("wave"), TEXT("tailFullness")})
				Quantitative.Add(FString::Printf(TEXT("hair.%s"), K));
			for (const TCHAR* K : {TEXT("face"), TEXT("body"), TEXT("leftFore"), TEXT("rightFore"), TEXT("leftHind"), TEXT("rightHind")})
				Quantitative.Add(FString::Printf(TEXT("extent.%s"), K));
			Quantitative.Add(TEXT("individual.temperament"));
			for (const FString& Id : Quantitative) T.Add(Id, {1, 2, 3, 2, 1});

			auto Ones = [](int32 N) { TArray<int32> W; W.Init(1, N); return W; };
			T.Add(TEXT("head.profile"), {40, 30, 30});
			T.Add(TEXT("hair.mane"), Ones(6));
			T.Add(TEXT("hair.tail"), Ones(6));
			T.Add(TEXT("hair.forelock"), Ones(4));
			T.Add(TEXT("hair.side"), Ones(3));
			T.Add(TEXT("mask.face"), Ones(12));
			T.Add(TEXT("mask.body"), Ones(10));
			T.Add(TEXT("mask.overlay"), Ones(6));
			for (const TCHAR* Leg : {TEXT("leftFore"), TEXT("rightFore"), TEXT("leftHind"), TEXT("rightHind")})
				T.Add(FString::Printf(TEXT("mask.%s"), Leg), Ones(8));
			T.Add(TEXT("coat.extension"), {70, 30});
			T.Add(TEXT("coat.agouti"), {60, 40});
			T.Add(TEXT("coat.cream"), {95, 5});
			T.Add(TEXT("coat.dun"), {85, 15});
			T.Add(TEXT("coat.gray"), {95, 5});
			T.Add(TEXT("coat.flaxen"), {80, 20});
			T.Add(TEXT("coat.roan"), {95, 5});
			T.Add(TEXT("coat.pattern"), {80, 15, 5});
			T.Add(TEXT("individual.eye"), {80, 15, 5});
			check(T.Num() == HRVisual::LocusCount);
			return T;
		}();
		return Table;
	}

	const TMap<FString, TArray<FString>>& Enums()
	{
		static const TMap<FString, TArray<FString>> Table = {
			{TEXT("head.profile"), {TEXT("straight"), TEXT("dished"), TEXT("convex")}},
			{TEXT("hair.side"), {TEXT("left"), TEXT("right"), TEXT("upright")}},
			{TEXT("coat.extension"), {TEXT("E"), TEXT("e")}},
			{TEXT("coat.agouti"), {TEXT("A"), TEXT("a")}},
			{TEXT("coat.cream"), {TEXT("plain"), TEXT("Cr")}},
			{TEXT("coat.dun"), {TEXT("plain"), TEXT("D")}},
			{TEXT("coat.gray"), {TEXT("plain"), TEXT("G")}},
			{TEXT("coat.flaxen"), {TEXT("F"), TEXT("f")}},
			{TEXT("coat.roan"), {TEXT("plain"), TEXT("R")}},
			{TEXT("coat.pattern"), {TEXT("none"), TEXT("patch"), TEXT("spot")}},
			{TEXT("individual.eye"), {TEXT("dark"), TEXT("amber"), TEXT("blue")}},
		};
		return Table;
	}

	/** FNV-1a over UTF-16 code units; with bCodePoints, a surrogate pair contributes only its high unit. */
	uint32 Fnv(const FString& Value, bool bCodePoints)
	{
		const auto Utf16 = StringCast<UTF16CHAR>(*Value, Value.Len());
		const UTF16CHAR* P = Utf16.Get();
		const int32 N = Utf16.Length();
		uint32 H = 2166136261u;
		for (int32 I = 0; I < N; ++I)
		{
			const uint32 C = P[I];
			H = (H ^ C) * 16777619u;
			// visualGenome.ts iterates `for (const c of string)` (code points) and hashes c.charCodeAt(0).
			if (bCodePoints && C >= 0xD800 && C <= 0xDBFF && I + 1 < N && P[I + 1] >= 0xDC00 && P[I + 1] <= 0xDFFF)
			{
				++I;
			}
		}
		return H;
	}

	/** Signed morph weight: -1 at Lo, 0 at Neutral, +1 at Hi. */
	double Signed(double V, double Lo, double Hi, double Neutral)
	{
		return V >= Neutral ? (V - Neutral) / (Hi - Neutral) : (V - Neutral) / (Neutral - Lo);
	}

	/** Allele names are case-sensitive ("E" is not "e"); FString == ignores case, so never use it here. */
	bool Eq(const FString& A, const TCHAR* B)
	{
		return A.Equals(B, ESearchCase::CaseSensitive);
	}

	/** JS Math.round for the non-negative values used here. */
	int32 JsRound(double V)
	{
		return (int32)FMath::FloorToDouble(V + 0.5);
	}

	FString HexByte(int32 V)
	{
		// Number.prototype.toString(16).padStart(2, '0'): lowercase.
		return FString::Printf(TEXT("%02x"), V);
	}

	int32 ParseHexPair(const FString& Hex, int32 Offset)
	{
		return FParse::HexNumber(*Hex.Mid(1 + Offset, 2));
	}
}

namespace HRVisual
{
	const TArray<FString>& Loci()
	{
		static const TArray<FString> List = []
		{
			TArray<FString> L;
			Domains().GetKeys(L);
			// Object.keys(domains).sort(): ordinal UTF-16 order (case-sensitive).
			L.Sort([](const FString& A, const FString& B) { return A.Compare(B, ESearchCase::CaseSensitive) < 0; });
			return L;
		}();
		return List;
	}

	int32 AlleleCount(const FString& Locus)
	{
		const TArray<int32>* W = Domains().Find(Locus);
		return W ? W->Num() : 0;
	}

	const TArray<FString>* EnumValues(const FString& Locus)
	{
		return Enums().Find(Locus);
	}

	uint32 Draw(const FString& Seed, const FString& Tag, uint32 Max)
	{
		if (Max < 1)
			UE_LOG(LogTemp, Fatal, TEXT("HorseRacing visual draw requires Max >= 1"));
		uint32 H = Fnv(Seed + TEXT(":visual-v1:") + Tag, true);
		// Avalanche before reducing short strings to prevent neighbouring founder correlations.
		H ^= H >> 16;
		H *= 0x7feb352du;
		H ^= H >> 15;
		H *= 0x846ca68bu;
		H ^= H >> 16;
		return H % Max;
	}

	uint32 AppearanceHash(const FString& Value)
	{
		return Fnv(Value, false);
	}

	TMap<FString, FHRGenePair> Generate(const FString& Seed, const TMap<FString, FHRGenePair>* Mother, const TMap<FString, FHRGenePair>* Father)
	{
		TMap<FString, FHRGenePair> Result;
		const FString Anchor = GFamilies[Draw(Seed, TEXT("founder-family-anchor"), 5)];
		const FString AnchorPrefix = FString::Printf(TEXT("family.%s."), *Anchor);
		const TMap<FString, FHRGenePair>* Parents[2] = {Mother, Father};
		for (const FString& Id : Loci())
		{
			const TArray<int32>& Weights = Domains().FindChecked(Id);
			int32 Total = 0;
			for (const int32 W : Weights) Total += W;
			auto Founder = [&](int32 Side) -> int32
			{
				const FString Tag = FString::Printf(TEXT("%s:%d"), *Id, Side);
				// Only unrevealed founders receive a visible shape anchor. Offspring never reroll.
				if (Id.StartsWith(TEXT("family."), ESearchCase::CaseSensitive))
				{
					return Id.StartsWith(AnchorPrefix, ESearchCase::CaseSensitive) ? 3 + (int32)Draw(Seed, Tag, 2) : (int32)Draw(Seed, Tag, 2);
				}
				int32 Point = (int32)Draw(Seed, Tag, Total);
				for (int32 Allele = 0; Allele < Weights.Num(); ++Allele)
				{
					Point -= Weights[Allele];
					if (Point < 0) return Allele;
				}
				return Weights.Num() - 1;
			};
			int32 Alleles[2];
			for (int32 Side = 0; Side < 2; ++Side)
			{
				const FHRGenePair* Parent = Parents[Side] ? Parents[Side]->Find(Id) : nullptr;
				Alleles[Side] = Parent ? (*Parent)[Draw(Seed, FString::Printf(TEXT("inherit:%s:%d"), *Id, Side), 2)] : Founder(Side);
			}
			Result.Add(Id, FHRGenePair(Alleles[0], Alleles[1]));
		}
		return Result;
	}

	bool HasAllLoci(const TMap<FString, FHRGenePair>& Genome)
	{
		for (const FString& Id : Loci())
		{
			if (!Genome.Contains(Id)) return false;
		}
		return true;
	}

	int32 FillMissingLoci(FHRWorldState& S)
	{
		TArray<FString> Ids;
		S.Horses.GetKeys(Ids);
		// Birth order (then id): parents are always completed before their foals.
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
			if (bSeen || !S.Horses.Contains(Id) || HasAllLoci(S.Horses[Id].Genome)) return;
			const TArray<FString> ParentIds = S.Horses[Id].Parents;
			const FHRHorse* M = nullptr;
			const FHRHorse* F = nullptr;
			if (ParentIds.Num() == 2)
			{
				// Safety net for unusual birth dates: a parent is always completed first.
				Complete(ParentIds[0]);
				Complete(ParentIds[1]);
				M = S.Horses.Find(ParentIds[0]);
				F = S.Horses.Find(ParentIds[1]);
			}
			FHRHorse& H = S.Horses[Id];
			// A parent missing from the world draws that side like a founder, as mobile does.
			const TMap<FString, FHRGenePair> Visual = Generate(H.Seed, M ? &M->Genome : nullptr, F ? &F->Genome : nullptr);
			for (const TPair<FString, FHRGenePair>& It : Visual)
			{
				if (!H.Genome.Contains(It.Key)) H.Genome.Add(It.Key, It.Value);
			}
			Filled++;
		};
		for (const FString& Id : Ids) Complete(Id);
		return Filled;
	}

	FHRPhenotype ResolvePhenotype(const FString& Seed, const TMap<FString, FHRGenePair>& Genome, int32 AgeSteps)
	{
		// --- appearance.ts helpers (pair / sum / u / range / has / low).
		// The mobile prototype adapter (eight legacy visual.* loci, no family.*) is not ported: older
		// saves are migrated to the full 61 loci (HRVisual::FillMissingLoci) before any rendering.
		auto Names = [&Genome](const TCHAR* Id, const TCHAR* Fallback) -> TArray<FString>
		{
			const FHRGenePair* P = Genome.Find(Id);
			if (!P) return {Fallback, Fallback};
			const TArray<FString>* E = EnumValues(Id);
			TArray<FString> Out;
			for (int32 I = 0; I < 2; ++I)
			{
				const int32 A = (*P)[I];
				Out.Add(E && E->IsValidIndex(A) ? (*E)[A] : FString(Fallback));
			}
			return Out;
		};
		auto Sum = [&Genome](const FString& Id) -> int32
		{
			const FHRGenePair* P = Genome.Find(Id);
			return P ? (int32)P->Sum() : 4;
		};
		auto U = [&](const FString& Id) -> double
		{
			const int64 Noise = AppearanceHash(Seed + TEXT(":") + Id) % 1201;
			return FMath::Min(1.0, FMath::Max(0.0, (double)(1250 * (int64)Sum(Id) + Noise - 600) / 10000));
		};
		auto Range = [&](const TCHAR* Id, double Lo, double Hi) -> double
		{
			return Lo + U(Id) * (Hi - Lo);
		};
		auto Has = [&](const TCHAR* Id, const TCHAR* Value) -> bool
		{
			const TArray<FString> Pair = Names(Id, TEXT("plain"));
			return Eq(Pair[0], Value) || Eq(Pair[1], Value);
		};
		auto Low = [&Genome](const TCHAR* Id, int32 Max) -> int32
		{
			const FHRGenePair* P = Genome.Find(Id);
			const int32 Min = P ? FMath::Min(P->A, P->B) : 0;
			return FMath::Min(Max, FMath::Max(0, Min));
		};

		// --- body family: ranked scores, blend capped by the compatibility matrix, 'B' projects to Balanced.
		static const int32 Matrix[5][5] = {
			{0, 3500, 3500, -1, -1},
			{3500, 0, 3500, 3500, -1},
			{2500, 2500, 0, 2500, -1},
			{-1, 3500, 3500, 0, 3500},
			{-1, -1, 2000, 3500, 0},
		};
		static const double Bases[5][5] = {
			{0.92, 1.02, 0.8, 1.1, 0.79},
			{1.04, 1.12, 0.91, 1.07, 0.91},
			{1, 1, 1, 1, 1},
			{1.03, 1.07, 1.12, 1.02, 1.07},
			{1.04, 0.96, 1.22, 0.9, 1.23},
		};
		struct FRank { int32 I; int32 Score; uint32 Tie; };
		TArray<FRank> Ranked;
		for (int32 I = 0; I < 5; ++I)
		{
			const FString F = GFamilies[I];
			Ranked.Add({I, Sum(FString::Printf(TEXT("family.%s.a"), *F)) + Sum(FString::Printf(TEXT("family.%s.b"), *F)),
				AppearanceHash(FString::Printf(TEXT("%s:family:%s"), *Seed, *F))});
		}
		Ranked.Sort([](const FRank& A, const FRank& B)
		{
			if (A.Score != B.Score) return A.Score > B.Score;
			if (A.Tie != B.Tie) return A.Tie < B.Tie;
			return A.I < B.I;
		});
		int32 P = Ranked[0].I;
		const int32 S = Ranked[1].I;
		double Blend = 0;
		const int32 Gap = Ranked[0].Score - Ranked[1].Score;
		if (Gap <= 3)
		{
			const int32 Cap = Matrix[P][S];
			if (Cap < 0) P = 2;
			else Blend = FMath::Min(JsRound((3500.0 * (16 - 5 * Gap)) / 16), Cap) / 10000.0;
		}
		double B[5];
		for (int32 I = 0; I < 5; ++I) B[I] = Bases[P][I] * (1 - Blend) + Bases[S][I] * Blend;

		// --- coat colour genetics.
		static const TCHAR* const Palette[3][3][3] = {
			{{TEXT("#A85D35"), TEXT("#A85D35"), TEXT("#824323")}, {TEXT("#D6B878"), TEXT("#D6B878"), TEXT("#EBDCA9")}, {TEXT("#EFE2C6"), TEXT("#EFE2C6"), TEXT("#F4ECD9")}},
			{{TEXT("#805137"), TEXT("#302B29"), TEXT("#252525")}, {TEXT("#B69D68"), TEXT("#3A3530"), TEXT("#302D29")}, {TEXT("#E5DAC1"), TEXT("#B4A28C"), TEXT("#C0B29A")}},
			{{TEXT("#303437"), TEXT("#292D30"), TEXT("#24282B")}, {TEXT("#514E46"), TEXT("#393A36"), TEXT("#30322F")}, {TEXT("#C9C5B7"), TEXT("#9C9B92"), TEXT("#ACA99C")}},
		};
		const TArray<FString> Extension = Names(TEXT("coat.extension"), TEXT("E"));
		const int32 Foundation = (Eq(Extension[0], TEXT("e")) && Eq(Extension[1], TEXT("e"))) ? 0 : Has(TEXT("coat.agouti"), TEXT("A")) ? 1 : 2;
		const TArray<FString> CreamAlleles = Names(TEXT("coat.cream"), TEXT("plain"));
		const int32 Cream = (int32)Eq(CreamAlleles[0], TEXT("Cr")) + (int32)Eq(CreamAlleles[1], TEXT("Cr"));
		FString Body = Palette[Foundation][Cream][0];
		const FString Points = Palette[Foundation][Cream][1];
		FString Hair = Palette[Foundation][Cream][2];
		const TArray<FString> Flaxen = Names(TEXT("coat.flaxen"), TEXT("F"));
		const bool bFlaxen = Foundation == 0 && Eq(Flaxen[0], TEXT("f")) && Eq(Flaxen[1], TEXT("f")) && Cream == 0;
		if (bFlaxen) Hair = TEXT("#E6CF96");
		const int32 Age = FMath::Max(0, AgeSteps);
		const bool bGray = Has(TEXT("coat.gray"), TEXT("G"));
		double GrayT = 0;
		if (bGray && Age >= 36)
		{
			GrayT = FMath::Min(1.0, (FMath::FloorToDouble(Age / 12.0) - 2) / 8);
			static const int32 Target[3] = {0xEE, 0xEC, 0xE2};
			auto Mix = [GrayT](const FString& Hex)
			{
				FString Out = TEXT("#");
				for (int32 C = 0; C < 3; ++C)
				{
					Out += HexByte(JsRound(ParseHexPair(Hex, 2 * C) * (1 - GrayT) + Target[C] * GrayT));
				}
				return Out;
			};
			Body = Mix(Body);
			Hair = Mix(Hair);
		}

		// --- growth by exact age.
		const double Maturity = Age < 12 ? (0.8 * Age) / 12 : 0.8 + (0.2 * FMath::Min(Age - 12, 12)) / 12;
		const double Juvenile = FMath::Min(1.0, FMath::Max(0.0, (1 - Maturity) / 0.6));

		// --- ordered morph clamps.
		double Legs = Range(TEXT("body.leg"), 0.88, 1.14);
		double Bone = Range(TEXT("body.boneSubstance"), 0.82, 1.2);
		const double Barrel = Range(TEXT("body.barrel"), 0.86, 1.18);
		if (Barrel > 1.1 && P != 3) Legs = FMath::Min(Legs, 1.08);
		if (Legs > 1.08) Bone = FMath::Max(0.88, Bone);
		const TArray<FString> Profiles = Names(TEXT("head.profile"), TEXT("straight"));
		double Profile = ((int32)Eq(Profiles[0], TEXT("convex")) + (int32)Eq(Profiles[1], TEXT("convex")) - (int32)Eq(Profiles[0], TEXT("dished")) - (int32)Eq(Profiles[1], TEXT("dished"))) * 0.5;
		if ((P < 2 && Profile > 0) || (P > 2 && Profile < 0)) Profile = 0;
		const double HeadLength = FMath::Min(P == 4 ? 1.08 : 1.1, Range(TEXT("head.length"), 0.9, 1.1));
		const double NeckLength = Range(TEXT("neck.length"), 0.86, 1.16);
		const double NeckThickness = FMath::Max(HeadLength > 1.08 && NeckLength > 1.1 ? 0.92 : 0.84, Range(TEXT("neck.thickness"), 0.84, 1.18));

		FHRPhenotype R;
		R.AgeSteps = AgeSteps;
		R.Maturity = Maturity;
		R.Juvenile = Juvenile;
		R.Family = P;
		R.FamilyName = GFamilies[P];
		R.SecondaryFamily = S;
		R.FamilyBlend = Blend;
		R.FamilyWeights.Init(0, 5);
		R.FamilyWeights[P] += 1 - Blend;
		R.FamilyWeights[S] += Blend;
		R.FamilyBase.Append(B, 5);

		const double HeightTrait = Range(TEXT("body.height"), 0.86, 1.14);
		const double LengthTrait = Range(TEXT("body.length"), 0.9, 1.12);
		R.Height = HeightTrait * B[0] * (1 - 0.22 * Juvenile);
		R.Length = LengthTrait * B[1];
		R.Barrel = Barrel * B[2] * (1 - 0.12 * Juvenile);
		R.Legs = Legs * B[3] * (1 + 0.08 * Juvenile);
		R.Bone = Bone * B[4];
		R.Neck = NeckLength;
		R.NeckWidth = NeckThickness * B[2];
		R.Head = HeadLength * (1 - 0.16 * Juvenile);
		R.Muzzle = Range(TEXT("head.muzzle"), 0.84, 1.16);
		const double EarTrait = Range(TEXT("head.earLength"), 0.82, 1.2);
		R.Ears = EarTrait * (1 + 0.08 * Juvenile);
		R.Mane = Low(TEXT("hair.mane"), 5);
		R.Tail = Low(TEXT("hair.tail"), 5);
		R.ManeLength = Range(TEXT("hair.maneLength"), 0.65, 1.35) * (1 - 0.35 * Juvenile);
		R.TailLength = Range(TEXT("hair.tailLength"), 0.7, 1.3) * (1 - 0.35 * Juvenile);
		R.Face = Low(TEXT("mask.face"), 11);
		R.FaceExtent = Sum(TEXT("extent.face")) / 2;
		static const TCHAR* const LegIds[4] = {TEXT("leftFore"), TEXT("rightFore"), TEXT("leftHind"), TEXT("rightHind")};
		for (const TCHAR* Leg : LegIds)
		{
			R.Socks.Add(Sum(FString::Printf(TEXT("extent.%s"), Leg)) / 2);
			R.SockMasks.Add(Low(*FString::Printf(TEXT("mask.%s"), Leg), 7));
		}
		R.Pattern = Has(TEXT("coat.pattern"), TEXT("patch")) ? TEXT("patch") : Has(TEXT("coat.pattern"), TEXT("spot")) ? TEXT("spot") : TEXT("none");
		R.PatternId = Low(TEXT("mask.body"), 9);
		R.Pose = (int32)(((uint32)Sum(TEXT("individual.temperament")) + AppearanceHash(Seed + TEXT(":pose")) % 6) % 6);
		R.Eye = Has(TEXT("individual.eye"), TEXT("dark")) ? TEXT("#272425") : Has(TEXT("individual.eye"), TEXT("amber")) ? TEXT("#936C31") : TEXT("#759CAD");
		R.Profile = Profile;
		R.Chest = FMath::Min(Range(TEXT("body.chest"), 0.88, 1.16), Barrel + 0.18);
		R.Hindquarter = Range(TEXT("body.hindquarter"), 0.86, 1.18);
		const double ForeheadTrait = Range(TEXT("head.forehead"), 0.86, 1.14);
		R.HeadWidth = ForeheadTrait * (1 + 0.06 * Juvenile);
		R.Jaw = FMath::Min(P == 0 ? 1.06 : 1.12, Range(TEXT("head.jaw"), 0.88, 1.12));
		R.EarSpread = Range(TEXT("head.earSpread"), -0.09, 0.12);
		R.EyeSpacing = Range(TEXT("head.eyeSpacing"), 0.92, 1.08);
		R.EyeHeight = Range(TEXT("head.eyeHeight"), -0.04, 0.04);
		R.NeckArch = Range(TEXT("neck.arch"), -0.18, 0.22);
		R.Carriage = Range(TEXT("neck.carriage"), -0.1, 0.14);
		const TArray<FString> Sides = Names(TEXT("hair.side"), TEXT("left"));
		R.HairSide = Sides[AppearanceHash(Seed + TEXT(":hair.side")) % 2];
		R.Forelock = Low(TEXT("hair.forelock"), 3);

		// Coat parameters for the 3D material.
		static const TCHAR* const FoundationNames[3] = {TEXT("chestnut"), TEXT("bay"), TEXT("black")};
		R.Foundation = FoundationNames[Foundation];
		R.Cream = Cream;
		R.bFlaxen = bFlaxen;
		R.bGray = bGray;
		R.GrayProgress = GrayT;
		R.Body = Body;
		R.Hair = Hair;
		R.Points = Points;
		R.BodyColor = FColor::FromHex(Body);
		R.HairColor = FColor::FromHex(Hair);
		R.PointsColor = FColor::FromHex(Points);
		R.EyeColor = FColor::FromHex(R.Eye);

		// [3D] loci the mobile renderer does not read yet (Technical Art proposal).
		R.bDun = Has(TEXT("coat.dun"), TEXT("D"));
		R.bRoan = Has(TEXT("coat.roan"), TEXT("R"));
		R.Wave = U(TEXT("hair.wave"));
		R.TailFullness = U(TEXT("hair.tailFullness"));
		R.PatternExtent = Sum(TEXT("extent.body")) / 2;
		R.Overlay = Low(TEXT("mask.overlay"), 5);

		// [3D] Morph-target weights from the trait values (before family base and juvenile factors).
		TMap<FName, double>& W = R.MorphWeights;
		W.Add(TEXT("body.height"), Signed(HeightTrait, 0.86, 1.14, 1));
		W.Add(TEXT("body.length"), Signed(LengthTrait, 0.9, 1.12, 1));
		W.Add(TEXT("body.chest"), Signed(R.Chest, 0.88, 1.16, 1));
		W.Add(TEXT("body.barrel"), Signed(Barrel, 0.86, 1.18, 1));
		W.Add(TEXT("body.hindquarter"), Signed(R.Hindquarter, 0.86, 1.18, 1));
		W.Add(TEXT("body.leg"), Signed(Legs, 0.88, 1.14, 1));
		W.Add(TEXT("body.boneSubstance"), Signed(Bone, 0.82, 1.2, 1));
		W.Add(TEXT("neck.length"), Signed(NeckLength, 0.86, 1.16, 1));
		W.Add(TEXT("neck.thickness"), Signed(NeckThickness, 0.84, 1.18, 1));
		W.Add(TEXT("neck.arch"), Signed(R.NeckArch, -0.18, 0.22, 0));
		W.Add(TEXT("neck.carriage"), Signed(R.Carriage, -0.1, 0.14, 0));
		W.Add(TEXT("head.length"), Signed(HeadLength, 0.9, 1.1, 1));
		W.Add(TEXT("head.forehead"), Signed(ForeheadTrait, 0.86, 1.14, 1));
		W.Add(TEXT("head.muzzle"), Signed(R.Muzzle, 0.84, 1.16, 1));
		W.Add(TEXT("head.jaw"), Signed(R.Jaw, 0.88, 1.12, 1));
		W.Add(TEXT("head.profile"), Profile);
		W.Add(TEXT("head.earLength"), Signed(EarTrait, 0.82, 1.2, 1));
		W.Add(TEXT("head.earSpread"), Signed(R.EarSpread, -0.09, 0.12, 0));
		W.Add(TEXT("head.eyeSpacing"), Signed(R.EyeSpacing, 0.92, 1.08, 1));
		W.Add(TEXT("head.eyeHeight"), Signed(R.EyeHeight, -0.04, 0.04, 0));
		for (int32 I = 0; I < 5; ++I) W.Add(FName(FString::Printf(TEXT("family.%s"), GFamilies[I])), R.FamilyWeights[I]);
		W.Add(TEXT("age.juvenile"), Juvenile);
		R.Breed = HRBreeds::Express(Genome);
		return R;
	}

	FHRPhenotype ResolvePhenotype(const FHRHorse& H, int32 AgeSteps)
	{
		return ResolvePhenotype(H.Seed, H.Genome, AgeSteps);
	}

	FHRPhenotype ResolvePhenotypeAt(const FHRHorse& H, int32 WorldT)
	{
		return ResolvePhenotype(H.Seed, H.Genome, HRClock::LifeMonths(H.BirthT, WorldT));
	}
}
