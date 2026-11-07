#include "CitySurfacePieces.h"
#include "CitySurfaceParents.h"
#include "Internationalization/Regex.h"

const TArray<FString>& JapanCityPieces::Parents()
{
    #define CITY_PARENT(Name) TEXT(Name),
    static const TArray<FString> Names={YORIMICHI_CITY_PARENTS(CITY_PARENT)};
    #undef CITY_PARENT
    return Names;
}

bool JapanCityPieces::IsParent(const FString& Name) { return Parents().Contains(Name); }

bool JapanCityPieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
    TMap<FString,FBox>* LogicalBounds)
{
    Result.Reset();
    if(LogicalBounds) LogicalBounds->Reset();
    double Version=0.,Limit=0.;bool Complete=false;FString Tag;
    const TSharedPtr<FJsonObject>* Sources=nullptr;
    if (!Manifest || !Manifest->TryGetNumberField(TEXT("version"),Version) || Version!=3. ||
        !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
        !Manifest->TryGetStringField(TEXT("tag"),Tag) || Tag!=TEXT("v1_128m") ||
        !Manifest->TryGetNumberField(TEXT("triangle_limit"),Limit) || Limit!=32768. ||
        !Manifest->TryGetObjectField(TEXT("sources"),Sources) || (*Sources)->Values.Num()!=Parents().Num()) return false;
    TMap<FString,TArray<FString>> Pending;
    TMap<FString,FBox> PendingBounds;
    TSet<FString> Names;
    for (const auto& Pair:(*Sources)->Values)
    {
        const FString ParentName(Pair.Key);
        if (!IsParent(ParentName) || !Pair.Value || Pair.Value->Type!=EJson::Object) return false;
        const auto Source=Pair.Value->AsObject();
        const TSharedPtr<FJsonObject>* Bounds=nullptr;
        const TArray<TSharedPtr<FJsonValue>> *Low=nullptr,*High=nullptr;
        if(!Source->TryGetObjectField(TEXT("source_bounds"),Bounds) ||
            !(*Bounds)->TryGetArrayField(TEXT("min"),Low) || !(*Bounds)->TryGetArrayField(TEXT("max"),High) ||
            Low->Num()!=3 || High->Num()!=3) return false;
        FVector Lower,Upper;
        for(int32 Axis=0;Axis<3;++Axis)
        {
            double A=0.,B=0.;
            if(!(*Low)[Axis] || !(*High)[Axis] || !(*Low)[Axis]->TryGetNumber(A) || !(*High)[Axis]->TryGetNumber(B) ||
                !FMath::IsFinite(A) || !FMath::IsFinite(B) || A>B) return false;
            Lower[Axis]=A*100.;Upper[Axis]=B*100.;
        }
        const FBox NativeBounds(FVector(Lower.X,-Upper.Y,Lower.Z),FVector(Upper.X,-Lower.Y,Upper.Z));
        if(!NativeBounds.IsValid || NativeBounds.Min.ContainsNaN() || NativeBounds.Max.ContainsNaN())return false;
        PendingBounds.Add(ParentName,NativeBounds);
        double Expected=0.,ExpectedHulls=0.;
        const TArray<TSharedPtr<FJsonValue>>* Tiles=nullptr;
        if (!Source->TryGetNumberField(TEXT("source_triangles"),Expected) || !FMath::IsFinite(Expected) || Expected<1. || Expected>MAX_int32 ||
            FMath::FloorToDouble(Expected)!=Expected ||
            !Source->TryGetNumberField(TEXT("source_collision_hulls"),ExpectedHulls) || !FMath::IsFinite(ExpectedHulls) || ExpectedHulls<0. || ExpectedHulls>MAX_int32 ||
            FMath::FloorToDouble(ExpectedHulls)!=ExpectedHulls ||
            !Source->TryGetArrayField(TEXT("tiles"),Tiles) || Tiles->IsEmpty()) return false;
        const FRegexPattern Pattern(TEXT("^")+ParentName+
            TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        double Total=0.,Hulls=0.;int32 HullOwners=0;
        auto& Paths=Pending.Add(ParentName);
        for (const auto& Value:*Tiles)
        {
            if (!Value || Value->Type!=EJson::Object) return false;
            const auto Tile=Value->AsObject();FString Name;double Count=0.,Collision=0.;
            if (!Tile->TryGetStringField(TEXT("name"),Name) || Names.Contains(Name) ||
                !Tile->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) || Count<1. || Count>Limit ||
                FMath::FloorToDouble(Count)!=Count ||
                !Tile->TryGetNumberField(TEXT("collision_hulls"),Collision) ||
                (Collision!=0. && Collision!=ExpectedHulls)) return false;
            FRegexMatcher Matcher(Pattern,Name);
            const bool WholeSmall=Name==ParentName && Tiles->Num()==1 && Expected<=Limit;
            if (!WholeSmall && (!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len())) return false;
            Names.Add(Name);Total+=Count;Hulls+=Collision;HullOwners+=Collision>0.;
            Paths.Add(FString::Printf(TEXT("/Game/Experiments/CitySurfaces/v1_128m/%s.%s"),*Name,*Name));
        }
        if (Total!=Expected || Hulls!=ExpectedHulls || HullOwners!=(ExpectedHulls>0.?1:0)) return false;
    }
    Result=MoveTemp(Pending);
    if(LogicalBounds) *LogicalBounds=MoveTemp(PendingBounds);
    return true;
}
