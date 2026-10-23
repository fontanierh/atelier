#include "SouthwestPieces.h"
#include "Internationalization/Regex.h"

const TArray<FString>& JapanSouthwestPieces::Parents()
{
    static const TArray<FString> Values={TEXT("SW_CoconutStand"),TEXT("SW_FisherHouseA"),TEXT("SW_FisherHouseB"),
        TEXT("SW_BoatShed"),TEXT("SW_StoneStairs"),TEXT("SW_Dock"),TEXT("SW_Boat"),TEXT("SW_DryingRack"),
        TEXT("SW_Temple"),TEXT("SW_Island"),TEXT("SW_Boulder_A"),TEXT("SW_Boulder_B"),TEXT("SW_Boulder_C"),
        TEXT("SW_StoneWall"),TEXT("Tree_PineLean_A"),TEXT("Tree_PineLean_B")};
    return Values;
}

bool JapanSouthwestPieces::IsParent(const FString& Name) { return Parents().Contains(Name); }

bool JapanSouthwestPieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
    TMap<FString,FBox>* LogicalBounds)
{
    Result.Reset();if(LogicalBounds) LogicalBounds->Reset();
    double Version=0.,Limit=0.;bool Complete=false;const TSharedPtr<FJsonObject>* Sources=nullptr;
    if(!Manifest || !Manifest->TryGetNumberField(TEXT("version"),Version) || Version!=1. ||
       !Manifest->TryGetNumberField(TEXT("triangle_limit"),Limit) || Limit!=32768. ||
       !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
       !Manifest->TryGetObjectField(TEXT("parents"),Sources) || (*Sources)->Values.Num()!=Parents().Num())return false;
    TMap<FString,TArray<FString>> Pending;TMap<FString,FBox> Bounds;TSet<FString> Seen;
    for(const auto& Pair:(*Sources)->Values)
    {
        if(!IsParent(Pair.Key) || !Pair.Value || Pair.Value->Type!=EJson::Object)return false;
        const auto Source=Pair.Value->AsObject();double Expected=0.;
        const TArray<TSharedPtr<FJsonValue>> *Pieces=nullptr,*Box=nullptr;
        if(!Source->TryGetNumberField(TEXT("source_triangles"),Expected) || !FMath::IsFinite(Expected) ||
           Expected<1. || Expected>MAX_int32 || FMath::FloorToDouble(Expected)!=Expected ||
           !Source->TryGetArrayField(TEXT("pieces"),Pieces) || Pieces->IsEmpty() ||
           !Source->TryGetArrayField(TEXT("bounds"),Box) || Box->Num()!=2)return false;
        if(!(*Box)[0] || !(*Box)[1] || (*Box)[0]->Type!=EJson::Array || (*Box)[1]->Type!=EJson::Array)return false;
        const auto& Low=(*Box)[0]->AsArray();const auto& High=(*Box)[1]->AsArray();
        if(Low.Num()!=3 || High.Num()!=3)return false;
        FVector A,B;
        for(int32 I=0;I<3;++I)
        {
            double L=0.,H=0.;if(!Low[I] || !High[I] || !Low[I]->TryGetNumber(L) || !High[I]->TryGetNumber(H) ||
                !FMath::IsFinite(L) || !FMath::IsFinite(H) || L>H)return false;
            A[I]=L*100.;B[I]=H*100.;
        }
        const FBox NativeBounds(FVector(A.X,-B.Y,A.Z),FVector(B.X,-A.Y,B.Z));
        if(!NativeBounds.IsValid || NativeBounds.Min.ContainsNaN() || NativeBounds.Max.ContainsNaN())return false;
        Bounds.Add(Pair.Key,NativeBounds);double Total=0.;auto& Paths=Pending.Add(Pair.Key);
        const FRegexPattern Pattern(TEXT("^")+Pair.Key+
            TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        for(const auto& Value:*Pieces)
        {
            if(!Value || Value->Type!=EJson::Object)return false;
            const auto Piece=Value->AsObject();FString Name;double Count=0.;
            if(!Piece->TryGetStringField(TEXT("name"),Name) || Seen.Contains(Name.ToLower()) ||
                !Piece->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) ||
                Count<1. || Count>Limit || FMath::FloorToDouble(Count)!=Count)return false;
            FRegexMatcher Matcher(Pattern,Name);
            if(Name!=Pair.Key && (!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len()))return false;
            Seen.Add(Name.ToLower());Total+=Count;
            Paths.Add(FString::Printf(TEXT("/Game/Japan/Southwest/Pieces/%s.%s"),*Name,*Name));
        }
        if(Total!=Expected)return false;
    }
    Result=MoveTemp(Pending);if(LogicalBounds)*LogicalBounds=MoveTemp(Bounds);return true;
}
