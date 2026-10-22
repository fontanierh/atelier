#include "CitySurfacePieces.h"
#include "Internationalization/Regex.h"

bool JapanCityPieces::IsParent(const FString& Name)
{
    return Name==TEXT("HD_Terrain") || Name==TEXT("HD_Streets") || Name==TEXT("HD_Square");
}

bool JapanCityPieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result)
{
    Result.Reset();
    double Version=0.,Limit=0.;bool Complete=false;FString Tag;
    const TSharedPtr<FJsonObject>* Sources=nullptr;
    if (!Manifest || !Manifest->TryGetNumberField(TEXT("version"),Version) || Version!=2. ||
        !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
        !Manifest->TryGetStringField(TEXT("tag"),Tag) || Tag!=TEXT("v1_128m") ||
        !Manifest->TryGetNumberField(TEXT("triangle_limit"),Limit) || Limit!=32768. ||
        !Manifest->TryGetObjectField(TEXT("sources"),Sources) || (*Sources)->Values.Num()!=3) return false;
    TMap<FString,TArray<FString>> Pending;
    TSet<FString> Names;
    for (const auto& Pair:(*Sources)->Values)
    {
        if (!IsParent(Pair.Key) || !Pair.Value || Pair.Value->Type!=EJson::Object) return false;
        const auto Source=Pair.Value->AsObject();
        double Expected=0.,ExpectedHulls=0.;
        const TArray<TSharedPtr<FJsonValue>>* Tiles=nullptr;
        if (!Source->TryGetNumberField(TEXT("source_triangles"),Expected) || !FMath::IsFinite(Expected) || Expected<1. || Expected>MAX_int32 ||
            FMath::FloorToDouble(Expected)!=Expected ||
            !Source->TryGetNumberField(TEXT("source_collision_hulls"),ExpectedHulls) || !FMath::IsFinite(ExpectedHulls) || ExpectedHulls<0. || ExpectedHulls>MAX_int32 ||
            FMath::FloorToDouble(ExpectedHulls)!=ExpectedHulls ||
            !Source->TryGetArrayField(TEXT("tiles"),Tiles) || Tiles->IsEmpty()) return false;
        const FRegexPattern Pattern(TEXT("^")+Pair.Key+
            TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        double Total=0.,Hulls=0.;int32 HullOwners=0;
        auto& Paths=Pending.Add(Pair.Key);
        for (const auto& Value:*Tiles)
        {
            if (!Value || Value->Type!=EJson::Object) return false;
            const auto Tile=Value->AsObject();FString Name;double Count=0.,Collision=0.;
            if (!Tile->TryGetStringField(TEXT("name"),Name) || Names.Contains(Name) ||
                !Tile->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) || Count<1. || Count>Limit ||
                FMath::FloorToDouble(Count)!=Count ||
                !Tile->TryGetNumberField(TEXT("collision_hulls"),Collision) ||
                (Collision!=0. && Collision!=ExpectedHulls)) return false;
            FRegexMatcher Matcher(Pattern,Name);if (!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len()) return false;
            Names.Add(Name);Total+=Count;Hulls+=Collision;HullOwners+=Collision>0.;
            Paths.Add(FString::Printf(TEXT("/Game/Experiments/CitySurfaces/v1_128m/%s.%s"),*Name,*Name));
        }
        if (Total!=Expected || Hulls!=ExpectedHulls || HullOwners!=(ExpectedHulls>0.?1:0)) return false;
    }
    Result=MoveTemp(Pending);
    return true;
}
