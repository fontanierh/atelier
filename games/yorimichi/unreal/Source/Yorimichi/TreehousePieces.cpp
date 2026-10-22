#include "TreehousePieces.h"
#include "Internationalization/Regex.h"

bool JapanTreehousePieces::Read(const TSharedPtr<FJsonObject>& Manifest,TArray<FString>& Result)
{
    Result.Reset();
    double Version=0.,Limit=0.,Cell=0.,Expected=0.,Collision=0.;bool Complete=false;FString Parent;
    const TArray<TSharedPtr<FJsonValue>>* Pieces=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* UVs=nullptr;
    if (!Manifest || !Manifest->TryGetNumberField(TEXT("version"),Version) || Version!=1. ||
        !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
        !Manifest->TryGetStringField(TEXT("parent"),Parent) || Parent!=TEXT("TH_Dressing") ||
        !Manifest->TryGetNumberField(TEXT("triangle_limit"),Limit) || Limit!=32768. ||
        !Manifest->TryGetNumberField(TEXT("cell_metres"),Cell) || Cell!=64. ||
        !Manifest->TryGetNumberField(TEXT("source_triangles"),Expected) || !FMath::IsFinite(Expected) ||
        Expected<1. || Expected>MAX_int32 || FMath::FloorToDouble(Expected)!=Expected ||
        !Manifest->TryGetNumberField(TEXT("collision_boxes"),Collision) || Collision!=0. ||
        !Manifest->TryGetArrayField(TEXT("uv_channels"),UVs) || UVs->Num()!=5 ||
        !Manifest->TryGetArrayField(TEXT("pieces"),Pieces) || Pieces->IsEmpty()) return false;
    const TCHAR* Names[]={TEXT("UVMap"),TEXT("Piece1"),TEXT("Piece2"),TEXT("Piece3"),TEXT("Piece4")};
    for(int32 I=0;I<5;++I)
    {
        FString Name;
        if (!(*UVs)[I] || !(*UVs)[I]->TryGetString(Name) || Name!=Names[I]) return false;
    }
    const FRegexPattern Pattern(TEXT("^TH_Dressing_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
    TArray<FString> Pending;TSet<FString> Seen;double Total=0.;
    for(const auto& Value:*Pieces)
    {
        if (!Value || Value->Type!=EJson::Object) return false;
        const auto Row=Value->AsObject();FString Name;double Count=0.;
        if (!Row->TryGetStringField(TEXT("name"),Name) || Seen.Contains(Name) ||
            !Row->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) ||
            Count<1. || Count>Limit || FMath::FloorToDouble(Count)!=Count) return false;
        FRegexMatcher Matcher(Pattern,Name);
        if (!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len()) return false;
        Seen.Add(Name);Total+=Count;
        Pending.Add(FString::Printf(TEXT("/Game/Japan/Treehouse/Pieces/%s.%s"),*Name,*Name));
    }
    if (Total!=Expected) return false;
    Result=MoveTemp(Pending);
    return true;
}
