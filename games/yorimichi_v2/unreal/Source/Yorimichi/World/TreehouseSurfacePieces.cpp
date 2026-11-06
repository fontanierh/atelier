#include "TreehouseSurfacePieces.h"
#include "Internationalization/Regex.h"

const TArray<FString>& JapanTreehouseSurfacePieces::Parents()
{
    static const TArray<FString> Values={TEXT("TH_Structure"),TEXT("TH_Frame"),TEXT("TH_Trunks"),TEXT("TH_Dressing")};
    return Values;
}
bool JapanTreehouseSurfacePieces::IsParent(const FString& Name) {return Parents().Contains(Name);}

bool JapanTreehouseSurfacePieces::Read(const TSharedPtr<FJsonObject>& Manifest,TMap<FString,TArray<FString>>& Result,
    TMap<FString,FBox>* LogicalBounds)
{
    Result.Reset();if(LogicalBounds)LogicalBounds->Reset();
    double Schema=0.;bool Complete=false;const TSharedPtr<FJsonObject> *ParentsObject=nullptr,*Assets=nullptr;
    if(!Manifest || !Manifest->TryGetNumberField(TEXT("schema"),Schema) || Schema!=1. ||
       !Manifest->TryGetBoolField(TEXT("complete"),Complete) || !Complete ||
       !Manifest->TryGetObjectField(TEXT("parents"),ParentsObject) || (*ParentsObject)->Values.Num()!=Parents().Num() ||
       !Manifest->TryGetObjectField(TEXT("assets"),Assets))return false;
    TMap<FString,TArray<FString>> Pending;TMap<FString,FBox> Bounds;TSet<FString> Seen;
    for(const FString& Parent:Parents())
    {
        const TArray<TSharedPtr<FJsonValue>>* Children=nullptr;
        if(!(*ParentsObject)->TryGetArrayField(Parent,Children) || Children->IsEmpty())return false;
        const FRegexPattern Pattern(TEXT("^")+Parent+TEXT("_cell_(?:0|-?[1-9][0-9]*)_(?:0|-?[1-9][0-9]*)(?:_Piece[0-3]{1,16})?$"));
        const bool WholeOwner=Parent==TEXT("TH_Frame") || Parent==TEXT("TH_Trunks");
        const FString Folder=Parent==TEXT("TH_Structure")?TEXT("structure"):Parent==TEXT("TH_Dressing")?TEXT("dressing"):
            Parent==TEXT("TH_Frame")?TEXT("frame"):TEXT("trunks");
        const FString Destination=Parent==TEXT("TH_Structure")?TEXT("/Game/Japan/Treehouse/StructurePieces"):
            Parent==TEXT("TH_Dressing")?TEXT("/Game/Japan/Treehouse/Pieces"):TEXT("/Game/Japan/Assets");
        if(WholeOwner && Children->Num()!=1)return false;
        FBox Whole(ForceInit);auto& Paths=Pending.Add(Parent);
        for(const auto& Child:*Children)
        {
            FString Name;if(!Child || !Child->TryGetString(Name) || Seen.Contains(Name.ToLower()))return false;
            FRegexMatcher Matcher(Pattern,Name);
            if(WholeOwner?Name!=Parent:(!Matcher.FindNext() || Matcher.GetMatchBeginning()!=0 || Matcher.GetMatchEnding()!=Name.Len()))return false;
            const TSharedPtr<FJsonObject>* Row=nullptr;FString Owner,File,Digest;double Count=0.,Hulls=-1.;
            const TArray<TSharedPtr<FJsonValue>> *Low=nullptr,*High=nullptr;
            if(!(*Assets)->TryGetObjectField(Name,Row) || !(*Row)->TryGetStringField(TEXT("parent"),Owner) || Owner!=Parent ||
               !(*Row)->TryGetStringField(TEXT("fbx"),File) || File!=TEXT("assets/")+Folder+TEXT("/")+Name+TEXT(".fbx") ||
               !(*Row)->TryGetStringField(TEXT("sha256"),Digest) || Digest.Len()!=64 ||
               !(*Row)->TryGetNumberField(TEXT("triangles"),Count) || !FMath::IsFinite(Count) || Count<1. || Count>32768. || FMath::FloorToDouble(Count)!=Count ||
               !(*Row)->TryGetNumberField(TEXT("collision_hulls"),Hulls) || Hulls!=0. ||
               !(*Row)->TryGetArrayField(TEXT("min"),Low) || !(*Row)->TryGetArrayField(TEXT("max"),High) || Low->Num()!=3 || High->Num()!=3)return false;
            const TArray<TSharedPtr<FJsonValue>>* UVs=nullptr;
            const bool PieceFade=Parent==TEXT("TH_Frame") || Parent==TEXT("TH_Dressing");
            if(!(*Row)->TryGetArrayField(TEXT("uv_channels"),UVs) || UVs->Num()!=(PieceFade?5:1))return false;
            for(int32 I=0;I<UVs->Num();++I)
            {
                FString UV;const FString Expected=I==0?TEXT("UVMap"):FString::Printf(TEXT("Piece%d"),I);
                if(!(*UVs)[I] || !(*UVs)[I]->TryGetString(UV) || UV!=Expected)return false;
            }
            for(const TCHAR C:Digest)if(!((C>=TEXT('0') && C<=TEXT('9')) || (C>=TEXT('a') && C<=TEXT('f'))))return false;
            FVector A,B;
            for(int32 I=0;I<3;++I)
            {
                double L=0.,H=0.;if(!(*Low)[I] || !(*High)[I] || !(*Low)[I]->TryGetNumber(L) || !(*High)[I]->TryGetNumber(H) ||
                    !FMath::IsFinite(L) || !FMath::IsFinite(H) || L>H)return false;
                A[I]=L*100.;B[I]=H*100.;
            }
            FBox Piece(FVector(A.X,-B.Y,A.Z),FVector(B.X,-A.Y,B.Z));
            if(!Piece.IsValid || Piece.Min.ContainsNaN() || Piece.Max.ContainsNaN())return false;
            Whole+=Piece;Seen.Add(Name.ToLower());Paths.Add(FString::Printf(TEXT("%s/%s.%s"),*Destination,*Name,*Name));
        }
        Bounds.Add(Parent,Whole);
    }
    if(Seen.Num()!=(*Assets)->Values.Num())return false;
    Result=MoveTemp(Pending);if(LogicalBounds)*LogicalBounds=MoveTemp(Bounds);return true;
}
