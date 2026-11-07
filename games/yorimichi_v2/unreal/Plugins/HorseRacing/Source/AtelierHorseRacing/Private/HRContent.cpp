#include "HRContent.h"

#include "HRClock.h"
#include "HRRandom.h"
#include "HRNames.inl"

namespace HRContent
{
	const TArray<FEvent>& Events()
	{
		// Twelve dates; days 2, 5, 8 and 11 are the Grands Prix: a classic, a two-run sprint, a two-lap race and a
		// sprint tournament.
		static const TArray<FEvent> List = {
			{TEXT("lanterns"), TEXT("Lantern Sprint"), 800, 0, 0, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("dew"), TEXT("Dew Loops"), 1200, 1, 2, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("gp_classic"), TEXT("Classic Grand Prix"), 1400, 0, 1, TEXT("home"), true, 1200, 1200, false, 1, 1, false},
			{TEXT("ford"), TEXT("Ford Line"), 900, 0, 0, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("shore"), TEXT("Shore Sands"), 1000, 2, 0, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("gp_sprint"), TEXT("Lagoon Sprint Grand Prix"), 500, 0, 0, TEXT("lagoon"), true, 500, 500, false, 2, 1, false},
			{TEXT("needle"), TEXT("Sand Needle"), 800, 2, 0, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("cedar"), TEXT("Cedar Bend"), 1200, 1, 2, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("gp_two_laps"), TEXT("Two-Lap Grand Prix"), 2000, 0, 1, TEXT("city"), true, 2000, 2000, false, 1, 2, false},
			{TEXT("traverse"), TEXT("High Traverse"), 1300, 0, 2, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("tide"), TEXT("Rising Tide"), 1600, 1, 1, TEXT("home"), false, 0, 0, false, 1, 1, false},
			{TEXT("gp_tournament"), TEXT("Tournament Grand Prix"), 1800, 0, 1, TEXT("highlands"), true, 600, 1800, false, 1, 1, true},
		};
		return List;
	}

	const FEvent& EventForT(int32 T)
	{
		return Events()[HRClock::DayOfSeason(T)];
	}

	const FEvent* FindEvent(const FString& Id)
	{
		for (const FEvent& E : Events())
		{
			if (Id == E.Id) return &E;
		}
		return nullptr;
	}

	const TArray<FString>& Traits()
	{
		static const TArray<FString> List = {TEXT("solar"), TEXT("breath"), TEXT("gate"), TEXT("quiet"), TEXT("clear"), TEXT("wise")};
		return List;
	}

	FString RoundName(const FString& Round, int32 Group)
	{
		if (Round == TEXT("final")) return TEXT("final");
		if (Round == TEXT("semi")) return FString::Printf(TEXT("heat %d"), Group + 1);
		if (Round == TEXT("qualif")) return FString::Printf(TEXT("qualifying sprint %d"), Group + 1);
		if (Round == TEXT("barrage")) return Group == 0 ? FString(TEXT("barrage")) : FString::Printf(TEXT("barrage %d"), Group + 1);
		return FString::Printf(TEXT("race %d"), Group + 1);
	}

	FString FormatDay(int32 T)
	{
		return FString::Printf(TEXT("season %d, day %d"), HRClock::SeasonOf(T) + 1, HRClock::DayOfSeason(T) + 1);
	}

	FString AgeLabel(int32 Days)
	{
		const int32 Months = FMath::Max(0, Days) / HRClock::LifeMonth;
		const int32 Years = Months / 12, Rest = Months % 12;
		const FString Y = FString::Printf(TEXT("%d year%s"), Years, Years == 1 ? TEXT("") : TEXT("s"));
		const FString M = FString::Printf(TEXT("%d month%s"), Rest, Rest == 1 ? TEXT("") : TEXT("s"));
		if (!Years) return M;
		return Rest ? Y + TEXT(" ") + M : Y;
	}

	const TArray<FStableDef>& StableDefs()
	{
		static const TArray<FStableDef> List = {
			{TEXT("old_mill"), TEXT("Old Mill Stable"), TEXT("8a8478"), 0, TEXT("Waiting for a new owner.")},
			{TEXT("alders"), TEXT("Alders Stud"), TEXT("43947b"), 0, TEXT("The patience of wet meadows.")},
			{TEXT("clear_bridge"), TEXT("Clear Bridge Stable"), TEXT("4276ed"), 1, TEXT("Leave fast, arrive first.")},
			{TEXT("three_meadows"), TEXT("Three Meadows Estate"), TEXT("dbc794"), 3, TEXT("Three meadows, one bloodline.")},
			{TEXT("low_dunes"), TEXT("Low Dunes Stable"), TEXT("e7894b"), 2, TEXT("Sand forges hearts.")},
			{TEXT("long_rocks"), TEXT("Long Rocks Estate"), TEXT("ab4268"), 4, TEXT("No distance scares us.")},
			{TEXT("fawn_hill"), TEXT("Fawn Hill Stable"), TEXT("7d5ba6"), 5, TEXT("We breed champions, not horses.")},
		};
		return List;
	}

	const TArray<FString>& HorseNamePool()
	{
		static const TArray<FString> Pool = []
		{
			TArray<FString> All;
			TSet<FString> Seen;
			auto Add = [&](const FString& S)
			{
				if (!Seen.Contains(S))
				{
					Seen.Add(S);
					All.Add(S);
				}
			};
			for (const TCHAR* S : GHRName_singles) Add(S);
			for (const TCHAR* S : GHRName_phrases) Add(S);
			for (const TCHAR* H : GHRName_heads)
				for (const TCHAR* P : GHRName_places) Add(FString::Printf(TEXT("%s %s"), H, P));
			for (const TCHAR* H : GHRName_singles)
				for (const TCHAR* P : GHRName_places) Add(FString::Printf(TEXT("%s %s"), H, P));
			// Filter after de-duplication, as the reference pool does (JS length = UTF-16 units).
			All.RemoveAll([](const FString& S) { return StringCast<UTF16CHAR>(*S, S.Len()).Length() > 22; });
			return All;
		}();
		return Pool;
	}

	FString GeneratedHorseName(const FString& Seed)
	{
		if (HRRandom::Draw(Seed, TEXT("name-style:living-v1"), 4) == 0)
		{
			TArray<FString> Short;
			for (const TCHAR* S : GHRName_singles) Short.Add(S);
			for (const TCHAR* S : GHRName_phrases) Short.Add(S);
			return Short[HRRandom::Draw(Seed, TEXT("name:living-v1"), Short.Num())];
		}
		const TArray<FString>& Pool = HorseNamePool();
		return Pool[HRRandom::Draw(Seed, TEXT("name:living-v1"), Pool.Num())];
	}

	FString NormalizeName(const FString& Name)
	{
		// Accent folding, then lower case (reference: NFD + strip marks + toLowerCase).
		static const TMap<TCHAR, TCHAR> Fold = {
			{TEXT('à'), TEXT('a')}, {TEXT('â'), TEXT('a')}, {TEXT('ä'), TEXT('a')}, {TEXT('á'), TEXT('a')},
			{TEXT('é'), TEXT('e')}, {TEXT('è'), TEXT('e')}, {TEXT('ê'), TEXT('e')}, {TEXT('ë'), TEXT('e')},
			{TEXT('î'), TEXT('i')}, {TEXT('ï'), TEXT('i')}, {TEXT('í'), TEXT('i')},
			{TEXT('ô'), TEXT('o')}, {TEXT('ö'), TEXT('o')}, {TEXT('ó'), TEXT('o')},
			{TEXT('ù'), TEXT('u')}, {TEXT('û'), TEXT('u')}, {TEXT('ü'), TEXT('u')}, {TEXT('ú'), TEXT('u')},
			{TEXT('ç'), TEXT('c')}, {TEXT('ñ'), TEXT('n')}, {TEXT('ÿ'), TEXT('y')},
			{TEXT('À'), TEXT('a')}, {TEXT('Â'), TEXT('a')}, {TEXT('É'), TEXT('e')}, {TEXT('È'), TEXT('e')},
			{TEXT('Ê'), TEXT('e')}, {TEXT('Î'), TEXT('i')}, {TEXT('Ô'), TEXT('o')}, {TEXT('Û'), TEXT('u')},
			{TEXT('Ç'), TEXT('c')}, {TEXT('’'), TEXT('\'')},
		};
		FString Out;
		Out.Reserve(Name.Len());
		for (const TCHAR C : Name)
		{
			const TCHAR* F = Fold.Find(C);
			Out.AppendChar(F ? *F : FChar::ToLower(C));
		}
		return Out;
	}
}
