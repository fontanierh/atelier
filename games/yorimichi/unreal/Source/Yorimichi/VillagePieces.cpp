#include "VillagePieces.h"
#include "Internationalization/Regex.h"

const TArray<FString>& JapanVillagePieces::Parents()
{
    static const TArray<FString> Values={TEXT("Village_TeaHouse"),TEXT("Village_CottageA"),TEXT("Village_CottageB"),
        TEXT("Village_Workshop"),TEXT("Village_Storehouse"),TEXT("Village_Garden"),TEXT("Village_Sign"),TEXT("Village_Ground"),
        TEXT("Village_Edges"),TEXT("Village_Details"),TEXT("Village_Planting"),TEXT("Village_Threshold")};
    return Values;
}
bool JapanVillagePieces::IsParent(const FString& Name){return Parents().Contains(Name);}

bool JapanVillagePieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
    TMap<FString,FBox>* LogicalBounds)
{
    Result.Reset();if(LogicalBounds)LogicalBounds->Reset();
    double Schema=0.;bool Complete=false;const TSharedPtr<FJsonObject>* Sources=nullptr;
    if(!Manifest || !Manifest->TryGetNumberField(TEXT("schema"),Schema) || Schema!=1. ||
       !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
       !Manifest->TryGetObjectField(TEXT("parents"),Sources) || (*Sources)->Values.Num()!=Parents().Num())return false;
    TMap<FString,TArray<FString>> Pending;TMap<FString,FBox> Bounds;TSet<FString> Seen;
    for(const FString& Parent:Parents())
    {
        const TSharedPtr<FJsonObject>* Source=nullptr;double Expected=0.,Hulls=-1.;FString Collision,Palette;
        const TArray<TSharedPtr<FJsonValue>> *Pieces=nullptr,*Slots=nullptr;
        if(!(*Sources)->TryGetObjectField(Parent,Source) || !(*Source)->TryGetNumberField(TEXT("source_triangles"),Expected) ||
           !FMath::IsFinite(Expected) || Expected<1. || Expected>MAX_int32 || FMath::FloorToDouble(Expected)!=Expected ||
           !(*Source)->TryGetNumberField(TEXT("source_collision_hulls"),Hulls) || !FMath::IsFinite(Hulls) || Hulls<0. ||
           Hulls>MAX_int32 || FMath::FloorToDouble(Hulls)!=Hulls ||
           !(*Source)->TryGetStringField(TEXT("collision"),Collision) ||
           Collision!=(Parent==TEXT("Village_Ground")?TEXT("complex_as_simple"):TEXT("simple_and_complex")) ||
           !(*Source)->TryGetArrayField(TEXT("slots"),Slots) || Slots->Num()!=1 ||
           !(*Slots)[0] || !(*Slots)[0]->TryGetString(Palette) || Palette!=TEXT("VillagePalette") ||
           !(*Source)->TryGetArrayField(TEXT("pieces"),Pieces) || Pieces->IsEmpty())return false;
        const FRegexPattern Pattern(TEXT("^")+Parent+TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        FBox Whole(ForceInit);double Total=0.;int32 Index=0;auto& Paths=Pending.Add(Parent);
        for(const auto& Value:*Pieces)
        {
            if(!Value || Value->Type!=EJson::Object)return false;
            const auto Piece=Value->AsObject();FString Name,Digest,UV;double Count=0.,OwnedHulls=-1.;
            const TArray<TSharedPtr<FJsonValue>> *Low=nullptr,*High=nullptr,*UVs=nullptr;
            if(!Piece->TryGetStringField(TEXT("name"),Name) || Seen.Contains(Name.ToLower()) ||
               !Piece->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) || Count<1. || Count>32768. || FMath::FloorToDouble(Count)!=Count ||
               !Piece->TryGetNumberField(TEXT("collision_hulls"),OwnedHulls) || OwnedHulls!=(Index==0?Hulls:0.) ||
               !Piece->TryGetStringField(TEXT("sha256"),Digest) || Digest.Len()!=64 ||
               !Piece->TryGetArrayField(TEXT("min"),Low) || !Piece->TryGetArrayField(TEXT("max"),High) || Low->Num()!=3 || High->Num()!=3 ||
               !Piece->TryGetArrayField(TEXT("uv_channels"),UVs) || UVs->Num()!=1 || !(*UVs)[0] ||
               !(*UVs)[0]->TryGetString(UV) || UV!=TEXT("UVMap"))return false;
            FRegexMatcher Matcher(Pattern,Name);
            if(Name!=Parent && (!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len()))return false;
            for(const TCHAR C:Digest)if(!((C>=TEXT('0') && C<=TEXT('9')) || (C>=TEXT('a') && C<=TEXT('f'))))return false;
            FVector A,B;
            for(int32 Axis=0;Axis<3;++Axis)
            {
                double L=0.,H=0.;if(!(*Low)[Axis] || !(*High)[Axis] || !(*Low)[Axis]->TryGetNumber(L) ||
                    !(*High)[Axis]->TryGetNumber(H) || !FMath::IsFinite(L) || !FMath::IsFinite(H) || L>H)return false;
                A[Axis]=L*100.;B[Axis]=H*100.;
            }
            FBox Box(FVector(A.X,-B.Y,A.Z),FVector(B.X,-A.Y,B.Z));
            if(!Box.IsValid || Box.Min.ContainsNaN() || Box.Max.ContainsNaN())return false;
            Whole+=Box;Seen.Add(Name.ToLower());Total+=Count;++Index;
            Paths.Add(FString::Printf(TEXT("/Game/Experiments/VillageAtomic/v1_atomic/%s.%s"),*Name,*Name));
        }
        if(Total!=Expected)return false;
        Bounds.Add(Parent,Whole);
    }
    Result=MoveTemp(Pending);if(LogicalBounds)*LogicalBounds=MoveTemp(Bounds);return true;
}
