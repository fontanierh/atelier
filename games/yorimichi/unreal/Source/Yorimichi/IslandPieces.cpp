#include "IslandPieces.h"
#include "Internationalization/Regex.h"

bool JapanIslandPieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result)
{
    Result.Reset();
    const TArray<FString> Expected={TEXT("Terrain"),TEXT("Road"),TEXT("Lane"),TEXT("Guardrail"),
        TEXT("Wires"),TEXT("FarHills"),TEXT("Sea")};
    double Schema=0.;bool Complete=false;const TSharedPtr<FJsonObject>* Parents=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Origin=nullptr;
    if(!Manifest || !Manifest->TryGetNumberField(TEXT("schema"),Schema) || Schema!=1. ||
       !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
       !Manifest->TryGetArrayField(TEXT("origin"),Origin) || Origin->Num()!=3 ||
       !Manifest->TryGetObjectField(TEXT("parents"),Parents) || (*Parents)->Values.Num()!=Expected.Num())return false;
    for(const auto& Value:*Origin)
    { double N=1.;if(!Value || !Value->TryGetNumber(N) || N!=0.)return false; }
    TMap<FString,TArray<FString>> Pending;TSet<FString> Seen;
    const FRegexPattern Digest(TEXT("^[0-9a-f]{64}$"));
    for(const FString& Parent:Expected)
    {
        const TSharedPtr<FJsonObject>* Group=nullptr;
        if(!(*Parents)->TryGetObjectField(Parent,Group))return false;
        bool Collision=false,Shadow=false;const bool Solid=Parent!=TEXT("Sea");
        const TArray<TSharedPtr<FJsonValue>>* Meshes=nullptr;
        if(!(*Group)->TryGetBoolField(TEXT("collision"),Collision) || Collision!=Solid ||
           !(*Group)->TryGetBoolField(TEXT("cast_shadow"),Shadow) || Shadow!=Solid ||
           !(*Group)->TryGetArrayField(TEXT("meshes"),Meshes) || Meshes->IsEmpty())return false;
        const FRegexPattern Names(TEXT("^")+Parent+
            TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        auto& Paths=Pending.Add(Parent);
        for(const auto& Value:*Meshes)
        {
            if(!Value || Value->Type!=EJson::Object)return false;
            const auto Row=Value->AsObject();FString Name,Asset,SHA;double Count=0.;
            if(!Row->TryGetStringField(TEXT("name"),Name) || Seen.Contains(Name.ToLower()) ||
               !Row->TryGetStringField(TEXT("asset"),Asset) ||
               Asset!=TEXT("/Game/Experiments/IslandTerrain/v1_atomic/")+Name ||
               !Row->TryGetStringField(TEXT("sha256"),SHA) ||
               !Row->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) ||
               Count<1. || Count>32768. || FMath::FloorToDouble(Count)!=Count)return false;
            FRegexMatcher NameMatch(Names,Name),HashMatch(Digest,SHA);
            if((Name!=Parent && (!NameMatch.FindNext() || NameMatch.GetMatchBeginning()!=0 ||
                NameMatch.GetMatchEnding()!=Name.Len())) || !HashMatch.FindNext())return false;
            const TArray<TSharedPtr<FJsonValue>> *Low=nullptr,*High=nullptr;
            if(!Row->TryGetArrayField(TEXT("min"),Low) || !Row->TryGetArrayField(TEXT("max"),High) ||
               Low->Num()!=3 || High->Num()!=3)return false;
            for(int32 Axis=0;Axis<3;++Axis)
            {
                double A=0.,B=0.;
                if(!(*Low)[Axis] || !(*High)[Axis] || !(*Low)[Axis]->TryGetNumber(A) ||
                   !(*High)[Axis]->TryGetNumber(B) || !FMath::IsFinite(A) || !FMath::IsFinite(B) || A>B)return false;
            }
            Seen.Add(Name.ToLower());Paths.Add(Asset+TEXT(".")+Name);
        }
    }
    Result=MoveTemp(Pending);return true;
}
