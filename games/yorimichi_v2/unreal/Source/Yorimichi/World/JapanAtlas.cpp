#include "JapanMap.h"
#include "JapanAtlasNames.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "LiveLibrary.h"
#include "Dom/JsonObject.h"
#include "Engine/Texture2D.h"
#include "ImageUtils.h"
#include "Misc/Paths.h"
#include "Widgets/Input/SEditableTextBox.h"

namespace
{
bool InPolygon(const TArray<FVector2D>& P, const FVector2D& Q)
{
    bool Inside = false;
    for (int32 I=0,J=P.Num()-1; I<P.Num(); J=I++)
    {
        const FVector2D A=P[J],B=P[I],D=B-A,R=Q-A;
        if (FMath::Abs(D^R)<1.e-6 && Q.X>=FMath::Min(A.X,B.X)-1.e-6 && Q.X<=FMath::Max(A.X,B.X)+1.e-6
            && Q.Y>=FMath::Min(A.Y,B.Y)-1.e-6 && Q.Y<=FMath::Max(A.Y,B.Y)+1.e-6) return true;
        if ((A.Y>Q.Y)!=(B.Y>Q.Y) && Q.X<A.X+(Q.Y-A.Y)*D.X/D.Y) Inside=!Inside;
    }
    return Inside;
}
bool InsideFrame(const FJapanAtlasFrame& F, const FVector& L)
{
    const FVector2D P(L.X/100.,-L.Y/100.);
    return P.X>=F.Bounds.Min.X && P.X<=F.Bounds.Max.X && P.Y>=F.Bounds.Min.Y && P.Y<=F.Bounds.Max.Y;
}
}

void UJapanMap::InitializeAtlas(const TSharedPtr<FJsonObject>& Root, const FString& Dir)
{
    const TSharedPtr<FJsonObject>* Atlas = nullptr;
    if (!Root->TryGetObjectField(TEXT("atlas"),Atlas)) return;
    AtlasData = *Atlas;
    auto ReadFrame = [&](const TSharedPtr<FJsonObject>& O,FJapanAtlasFrame& F)
    {
        const TArray<TSharedPtr<FJsonValue>>* B=nullptr;
        FString Relative;
        if (!O.IsValid() || !O->TryGetStringField(TEXT("key"),F.Key) || !O->TryGetStringField(TEXT("name"),F.Name)
            || !O->TryGetStringField(TEXT("image"),Relative) || !Relative.StartsWith(TEXT("atlas/")) || Relative.Contains(TEXT(".."))
            || !O->TryGetArrayField(TEXT("bounds"),B) || B->Num()!=4) return false;
        F.Bounds=FBox2D(FVector2D((*B)[0]->AsNumber(),(*B)[1]->AsNumber()),FVector2D((*B)[2]->AsNumber(),(*B)[3]->AsNumber()));
        if (F.Bounds.GetSize().X<=0 || F.Bounds.GetSize().Y<=0) return false;
        F.LabelPosition=F.Bounds.GetCenter();
        const TArray<TSharedPtr<FJsonValue>>* Label=nullptr;
        if(O->TryGetArrayField(TEXT("label"),Label) && Label->Num()==2) F.LabelPosition=FVector2D((*Label)[0]->AsNumber(),(*Label)[1]->AsNumber());
        const TArray<TSharedPtr<FJsonValue>>* Points=nullptr;
        if (O->TryGetArrayField(TEXT("polygon"),Points)) for (const auto& V:*Points)
        { const auto& A=V->AsArray(); if (A.Num()==2) F.Polygon.Add(FVector2D(A[0]->AsNumber(),A[1]->AsNumber())); }
        FString Colour; if (O->TryGetStringField(TEXT("color"),Colour)) F.Colour=FLinearColor(FColor::FromHex(Colour));
        UTexture2D* Image=FImageUtils::ImportFileAsTexture2D(Dir/Relative);
        if (!Image) return false;
        AtlasTextures.Add(Image); F.Brush.SetResourceObject(Image); F.Brush.ImageSize=FVector2D(Image->GetSizeX(),Image->GetSizeY());
        F.Brush.DrawAs=ESlateBrushDrawType::Image; F.Brush.TintColor=FLinearColor::White;
        return true;
    };
    const TSharedPtr<FJsonObject>* World=nullptr;
    if (!AtlasData->TryGetObjectField(TEXT("world"),World) || !ReadFrame(*World,WorldFrame)) { AtlasData.Reset(); return; }
    const TArray<TSharedPtr<FJsonValue>>* Regions=nullptr;
    if (AtlasData->TryGetArrayField(TEXT("regions"),Regions)) for (const auto& Row:*Regions)
    { FJapanAtlasFrame F; if (ReadFrame(Row->AsObject(),F)) AtlasRegions.Add(MoveTemp(F)); }
    const TArray<TSharedPtr<FJsonValue>>* Landmarks=nullptr;
    if (AtlasData->TryGetArrayField(TEXT("landmarks"),Landmarks)) for (const auto& Row:*Landmarks)
    {
        const auto O=Row->AsObject(); FJapanAtlasLandmark L;
        L.Key=O->GetStringField(TEXT("key")); L.Name=O->GetStringField(TEXT("name")); L.Region=O->GetStringField(TEXT("region"));
        L.Category=O->GetStringField(TEXT("category")); O->TryGetBoolField(TEXT("editable"),L.bEditable);
        L.Location=AJapanWorld::ToUE(O->GetNumberField(TEXT("x")),O->GetNumberField(TEXT("y")),O->GetNumberField(TEXT("z")));
        AtlasLandmarks.Add(MoveTemp(L));
    }
    const TSharedPtr<FJsonObject>* Air=nullptr;
    if (AtlasData->TryGetObjectField(TEXT("air"),Air) && Air && Air->IsValid())
    {
        const TArray<TSharedPtr<FJsonValue>>* Line=nullptr;
        if ((*Air)->TryGetArrayField(TEXT("line"),Line)) for (const auto& V:*Line)
            if (V.IsValid() && V->Type==EJson::String) AirRoute.Line.Add(V->AsString());
        const TArray<TSharedPtr<FJsonValue>>* Stops=nullptr;
        if ((*Air)->TryGetArrayField(TEXT("stops"),Stops)) for (const auto& V:*Stops)
        {
            const TSharedPtr<FJsonObject>* O=nullptr; if (!V->TryGetObject(O)) continue;
            FJapanAtlasAirStop Stop;
            Stop.Key=(*O)->GetStringField(TEXT("key")); (*O)->TryGetStringField(TEXT("name"),Stop.Name);
            Stop.Location=AJapanWorld::ToUE((*O)->GetNumberField(TEXT("x")),(*O)->GetNumberField(TEXT("y")),(*O)->GetNumberField(TEXT("z")));
            AirRoute.Stops.Add(MoveTemp(Stop));
        }
        const TArray<TSharedPtr<FJsonValue>>* Legs=nullptr;
        if ((*Air)->TryGetArrayField(TEXT("legs"),Legs)) for (const auto& V:*Legs)
        {
            const TSharedPtr<FJsonObject>* O=nullptr; if (!V->TryGetObject(O)) continue;
            FJapanAtlasAirLeg Leg;
            Leg.From=(*O)->GetStringField(TEXT("from")); Leg.To=(*O)->GetStringField(TEXT("to"));
            Leg.Seconds=(*O)->GetNumberField(TEXT("seconds"));
            Leg.Height=(*O)->GetNumberField(TEXT("height"));
            AirRoute.Legs.Add(MoveTemp(Leg));
        }
        (*Air)->TryGetStringField(TEXT("note"),AirRoute.Note);
    }
    if (auto* Store=AtlasNameStore()) Store->Load();
}

const FJapanAtlasFrame* UJapanMap::GetAtlasFrame(const FString& Key) const
{
    if (Key==TEXT("world")) return WorldFrame.Key.IsEmpty() ? nullptr : &WorldFrame;
    return AtlasRegions.FindByPredicate([&](const FJapanAtlasFrame& R){return R.Key==Key;});
}

const FSlateBrush* UJapanMap::GetAtlasBrush() const
{
    const auto* F=GetAtlasFrame(ActiveRegion); return F ? &F->Brush : &Brush;
}

FVector2D UJapanMap::ToAtlas(const FVector& Location, const FString& Region) const
{
    const auto* F=GetAtlasFrame(Region.IsEmpty()?ActiveRegion:Region);
    if (!F) return ToSheet(Location);
    return FVector2D((Location.X/100.-F->Bounds.Min.X)/F->Bounds.GetSize().X,
                     (F->Bounds.Max.Y+Location.Y/100.)/F->Bounds.GetSize().Y);
}

FString UJapanMap::RegionForLocation(const FVector& Location) const
{
    for (const auto& R:AtlasRegions) if (InPolygon(R.Polygon,FVector2D(Location.X/100.,-Location.Y/100.)) && InsideFrame(R,Location)) return R.Key;
    return TEXT("world");
}

FString UJapanMap::RegionForZone(const FJapanMapZone& Zone) const
{
    FString Key;
    if (Zone.Key==TEXT("megapark") || Zone.Key==TEXT("zeppelin_megapark") || Zone.Key==TEXT("hippodrome") || Zone.Key==TEXT("foothills")) Key=TEXT("northern_foothills");
    else if (Zone.Key==TEXT("craterpark")) Key=TEXT("volcanic_highlands");
    else Key=RegionForLocation(Zone.Location);
    const auto* F=GetAtlasFrame(Key); return F && InsideFrame(*F,Zone.Location) ? Key : FString(TEXT("world"));
}

FString UJapanMap::GetAtlasTitle() const
{
    const auto* F=GetAtlasFrame(ActiveRegion); return F ? F->Name : FString(TEXT("The World"));
}

TArray<FString> UJapanMap::GetAtlasRegionKeys() const
{
    TArray<FString> Out; for (const auto& R:AtlasRegions) Out.Add(R.Key); return Out;
}

bool UJapanMap::SelectAtlasRegion(const FString& Key)
{
    if (!GetAtlasFrame(Key)) return false;
    ActiveRegion=Key; SelectedStable.Empty(); SearchText.Empty(); ++AtlasRevision; return true;
}

void UJapanMap::AtlasCurrentRegion()
{
    SelectAtlasRegion(Owner ? RegionForLocation(Owner->GetActorLocation()) : FString(TEXT("world")));
}

void UJapanMap::AtlasBack()
{
    if (ActiveRegion!=TEXT("world")) SelectAtlasRegion(TEXT("world")); else Close();
}

TArray<FString> UJapanMap::GetAtlasZoneKeys(const FString& Region) const
{
    TArray<FString> Keys;
    for (const auto& Z:GetZones()) if (Region==TEXT("world") || RegionForZone(Z)==Region) Keys.Add(Z.Key);
    return Keys;
}

FJapanAtlasNames* UJapanMap::AtlasNameStore() const
{
    if (!Owner || !Owner->GetLandscape()) return nullptr;
    auto* S=&Owner->GetLandscape()->AtlasNames; S->Load(); return S;
}

FString UJapanMap::GetStableName(const FString& Key) const
{
    const auto* L=AtlasLandmarks.FindByPredicate([&](const FJapanAtlasLandmark& P){return P.Key==Key;});
    if (!L) return FString();
    const auto* S=AtlasNameStore(); return S ? S->Get(Key,L->Name) : L->Name;
}

FString UJapanMap::GetAtlasError() const
{
    const auto* S=AtlasNameStore(); return S ? S->Error : FString();
}

bool UJapanMap::RenameStable(const FString& Key,const FString& Name)
{
    const auto* L=AtlasLandmarks.FindByPredicate([&](const FJapanAtlasLandmark& P){return P.Key==Key && P.bEditable;});
    auto* S=AtlasNameStore();
    if (!L || !S) return false;
    if (!S->Rename(Key,Name)) { ULiveLibrary::Say(S->Error); return false; }
    ++AtlasRevision; return true;
}

bool UJapanMap::ResetStableName(const FString& Key)
{
    const auto* L=AtlasLandmarks.FindByPredicate([&](const FJapanAtlasLandmark& P){return P.Key==Key && P.bEditable;});
    auto* S=AtlasNameStore(); if (!L || !S) return false;
    if (!S->Reset(Key)) { ULiveLibrary::Say(S->Error); return false; }
    ++AtlasRevision; return true;
}

void UJapanMap::SelectStable(const FString& Key)
{
    if (!AtlasLandmarks.ContainsByPredicate([&](const FJapanAtlasLandmark& P){return P.Key==Key && P.bEditable;})) return;
    SelectedStable=Key; ++AtlasRevision;
}

bool UJapanMap::IsEditingMapText() const
{
    for (const auto& Input:{MarkerName,AtlasSearch,StableName}) if (Input.IsValid() && (Input->HasKeyboardFocus() || Input->HasFocusedDescendants())) return true;
    return false;
}

FString UJapanMap::ReviewAtlasAirRoute() const
{
    auto Out=MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Line;
    for (const auto& Key : AirRoute.Line) Line.Add(MakeShared<FJsonValueString>(Key));
    TArray<TSharedPtr<FJsonValue>> Stops;
    for (const auto& Stop : AirRoute.Stops)
    {
        auto Row=MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("key"),Stop.Key); Row->SetStringField(TEXT("name"),Stop.Name);
        Row->SetNumberField(TEXT("x"),Stop.Location.X/100.); Row->SetNumberField(TEXT("y"),-Stop.Location.Y/100.);
        Stops.Add(MakeShared<FJsonValueObject>(Row));
    }
    TArray<TSharedPtr<FJsonValue>> Legs;
    for (const auto& Leg : AirRoute.Legs)
    {
        auto Row=MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("from"),Leg.From); Row->SetStringField(TEXT("to"),Leg.To);
        Row->SetNumberField(TEXT("seconds"),Leg.Seconds); Row->SetNumberField(TEXT("height"),Leg.Height);
        Legs.Add(MakeShared<FJsonValueObject>(Row));
    }
    Out->SetArrayField(TEXT("line"),Line); Out->SetArrayField(TEXT("stops"),Stops);
    Out->SetArrayField(TEXT("legs"),Legs); Out->SetStringField(TEXT("note"),AirRoute.Note);
    FString Result; FJsonSerializer::Serialize(Out,TJsonWriterFactory<>::Create(&Result)); return Result;
}

TArray<FJapanAtlasTarget> UJapanMap::GetAtlasTargets() const
{
    TArray<FJapanAtlasTarget> Out;
    if (ActiveRegion==TEXT("world")) for (const auto& R:AtlasRegions) if (SearchText.IsEmpty() || R.Name.Contains(SearchText))
    {
        FJapanAtlasTarget T; T.Key=R.Key; T.Name=R.Name; T.Category=TEXT("region"); T.Region=R.Key;
        const auto P=R.LabelPosition,Q=R.Bounds.GetCenter(); T.Location=AJapanWorld::ToUE(P.X,P.Y,0); T.Link=AJapanWorld::ToUE(Q.X,Q.Y,0);
        T.Hint=TEXT("Open region map"); Out.Add(MoveTemp(T));
    }
    for (const auto& Z:GetZones()) if (ActiveRegion==TEXT("world") || !SearchText.IsEmpty() || RegionForZone(Z)==ActiveRegion)
    {
        FJapanAtlasTarget T; T.Key=Z.Key; T.Name=Z.Name; T.Hint=Z.Hint; T.Location=Z.Location; T.bTravel=true;
        T.Region=RegionForZone(Z); T.Category=Z.Key.StartsWith(TEXT("player_")) ? TEXT("player") : Z.Key.StartsWith(TEXT("marker_")) ? TEXT("marker") : Z.Key.Contains(TEXT("station")) ? TEXT("station") : TEXT("place");
        if (SearchText.IsEmpty() || T.Name.Contains(SearchText)) Out.Add(MoveTemp(T));
    }
    if (ActiveRegion!=TEXT("world") || !SearchText.IsEmpty()) for (const auto& L:AtlasLandmarks) if (L.Region==ActiveRegion || !SearchText.IsEmpty())
    {
        FJapanAtlasTarget T; T.Key=L.Key; T.Name=GetStableName(L.Key); T.Category=L.Category; T.Region=L.Region;
        T.Location=L.Location; T.bEditable=L.bEditable; T.Hint=TEXT("Select to rename this stable");
        if (SearchText.IsEmpty() || T.Name.Contains(SearchText)) Out.Add(MoveTemp(T));
    }
    return Out;
}

TSharedPtr<FJsonObject> UJapanMap::GetAtlasJson() const
{
    if (!AtlasData.IsValid()) return nullptr;
    auto Out=MakeShared<FJsonObject>(*AtlasData);
    Out->SetStringField(TEXT("error"),GetAtlasError());
    TArray<TSharedPtr<FJsonValue>> Rows;
    for (const auto& L:AtlasLandmarks)
    {
        auto R=MakeShared<FJsonObject>(); R->SetStringField(TEXT("key"),L.Key); R->SetStringField(TEXT("name"),GetStableName(L.Key));
        R->SetStringField(TEXT("region"),L.Region); R->SetStringField(TEXT("category"),L.Category); R->SetBoolField(TEXT("editable"),L.bEditable);
        R->SetNumberField(TEXT("x"),L.Location.X/100.); R->SetNumberField(TEXT("y"),-L.Location.Y/100.);
        Rows.Add(MakeShared<FJsonValueObject>(R));
    }
    Out->SetArrayField(TEXT("landmarks"),Rows); return Out;
}
