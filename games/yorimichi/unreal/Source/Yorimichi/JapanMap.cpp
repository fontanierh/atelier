#include "JapanMap.h"
#include "YoriData.h"
#include "SkatePark.h"
#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Texture2D.h"
#include "ImageUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Text/STextBlock.h"

static FSlateBrush ShapeBrush(float Radius)
{
    FSlateBrush B;
    B.DrawAs = ESlateBrushDrawType::RoundedBox;
    B.ImageSize = FVector2D(16,16);
    B.TintColor = FLinearColor::White;
    if (Radius <= 0.f) B.OutlineSettings.RoundingType = ESlateBrushRoundingType::HalfHeightRadius;   // a disc for square boxes
    else { B.OutlineSettings.RoundingType = ESlateBrushRoundingType::FixedRadius; B.OutlineSettings.CornerRadii = FVector4(Radius,Radius,Radius,Radius); }
    return B;
}

/** The sheet itself: the painted map fitted into the available space, the zone pins with their names, the player. */
class SJapanMapSheet : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SJapanMapSheet) {}
        SLATE_ARGUMENT(UJapanMap*, Map)
    SLATE_END_ARGS()
    void Construct(const FArguments& In) { Map = In._Map; SetCursor(EMouseCursor::Default); SetClipping(EWidgetClipping::ClipToBounds); }
    FString GetHoveredHint() const
    {
        const UJapanMap* M = Map.Get();
        if (!M || !M->GetZones().IsValidIndex(Hovered)) return FString();
        const auto& Z = M->GetZones()[Hovered];
        return Z.Name + (Z.Hint.IsEmpty() ? TEXT("") : TEXT("  —  ")) + Z.Hint + TEXT("   ·   click to travel");
    }
    virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(900,600); }
    virtual bool SupportsKeyboardFocus() const override { return true; }
    virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& G, const FSlateRect& Clip, FSlateWindowElementList& Out, int32 Layer, const FWidgetStyle& Style, bool bParentEnabled) const override
    {
        const UJapanMap* M = Map.Get();
        if (!M) return Layer;
        Fit(G);
        FSlateDrawElement::MakeBox(Out,Layer,G.ToPaintGeometry(FVector2f(SheetSize),FSlateLayoutTransform(FVector2f(SheetOffset))),M->GetBrush(),ESlateDrawEffect::None,FLinearColor::White);
        const FSlateFontInfo Font = FCoreStyle::GetDefaultFontStyle("Bold",13);
        const FSlateFontInfo BigFont = FCoreStyle::GetDefaultFontStyle("Bold",15);
        TSharedRef<FSlateFontMeasure> Measure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
        // pins: a white halo, a red disc, the name on a dark tab
        const TArray<FJapanMapZone>& Zones = M->GetZones();
        for (int32 Pass = 0; Pass < 2; ++Pass)
            for (int32 I = 0; I < Zones.Num(); ++I)
            {
                const bool bHot = I == Hovered;
                if ((Pass == 1) != bHot) continue;               // the hovered pin paints last, on top
                const FVector2D P = SheetOffset + M->ToSheet(Zones[I].Location) * SheetSize;
                const float R = bHot ? 11.f : 8.f;
                Disc(Out,Layer+1,G,P,R+2.5f,FLinearColor(1,.97f,.9f,1));
                Disc(Out,Layer+2,G,P,R,bHot ? FLinearColor(.95f,.45f,.18f,1) : FLinearColor(.72f,.18f,.12f,1));
                const FString Number=FString::FromInt(I+1);
                const FVector2D NumberSize=Measure->Measure(Number,Font);
                FSlateDrawElement::MakeText(Out,Layer+3,G.ToPaintGeometry(FVector2f(NumberSize),FSlateLayoutTransform(FVector2f(P-NumberSize*.5f))),Number,Font,ESlateDrawEffect::None,FLinearColor::White);
                if(!bHot)continue;
                const FString& Name = Zones[I].Name;
                const FVector2D TextSize = Measure->Measure(Name,bHot ? BigFont : Font);
                const bool bLeft = P.X + R + 12 + TextSize.X + 12 > SheetOffset.X + SheetSize.X;
                const FVector2D TabSize(TextSize.X+14, TextSize.Y+6);
                const FVector2D Tab(bLeft ? P.X - R - 8 - TabSize.X : P.X + R + 8, P.Y - TabSize.Y*.5f);
                FSlateDrawElement::MakeBox(Out,Layer+3,G.ToPaintGeometry(FVector2f(TabSize),FSlateLayoutTransform(FVector2f(Tab))),&TabBrush,ESlateDrawEffect::None,FLinearColor(.06f,.07f,.06f,bHot ? .92f : .72f));
                FSlateDrawElement::MakeText(Out,Layer+4,G.ToPaintGeometry(FVector2f(TextSize),FSlateLayoutTransform(FVector2f(Tab.X+7,Tab.Y+3))),Name,bHot ? BigFont : Font,ESlateDrawEffect::None,FLinearColor(1,.96f,.86f,1));
            }
        // the player: a disc with a heading arrow, pulsing so it is easy to find
        if (const AWandererCharacter* Pawn = M->GetOwnerPawn())
        {
            const FVector2D P = SheetOffset + M->ToSheet(Pawn->GetActorLocation()) * SheetSize;
            const float A = FMath::DegreesToRadians(UJapanMap::SheetHeading(Pawn->GetActorRotation().Yaw));
            const FVector2D Dir(FMath::Cos(A),FMath::Sin(A)), Perp(-Dir.Y,Dir.X);
            const float Pulse = 12.f + 6.f*FMath::Sin(FPlatformTime::Seconds()*4.0);
            Disc(Out,Layer+5,G,P,Pulse+10.f,FLinearColor(1,.85f,.35f,.18f));
            Disc(Out,Layer+5,G,P,Pulse,FLinearColor(1,.85f,.35f,.35f));
            TArray<FVector2f> Tri = { FVector2f(P+Dir*22.f), FVector2f(P-Dir*9.f+Perp*11.f), FVector2f(P-Dir*3.f), FVector2f(P-Dir*9.f-Perp*11.f), FVector2f(P+Dir*22.f) };
            FSlateDrawElement::MakeLines(Out,Layer+6,G.ToPaintGeometry(),Tri,ESlateDrawEffect::None,FLinearColor(1,.98f,.9f,1),true,6.f);
            FSlateDrawElement::MakeLines(Out,Layer+7,G.ToPaintGeometry(),Tri,ESlateDrawEffect::None,FLinearColor(.12f,.22f,.5f,1),true,3.f);
            Disc(Out,Layer+8,G,P,5.f,FLinearColor(1,.98f,.9f,1));
            Disc(Out,Layer+9,G,P,3.f,FLinearColor(.12f,.22f,.5f,1));
        }
        return Layer+10;
    }
    virtual FReply OnMouseMove(const FGeometry& G,const FPointerEvent& E) override
    {
        const FVector2D P=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        if(bHeld){bMoved|=FVector2D::Distance(P,DragStart)>5.;if(bMoved)Pan+=P-LastMouse;LastMouse=P;return FReply::Handled();}
        Hovered=Pick(G,E);return FReply::Unhandled();
    }
    virtual void OnMouseLeave(const FPointerEvent&) override { Hovered=-1; }
    virtual FReply OnMouseWheel(const FGeometry& G,const FPointerEvent& E) override
    {
        Fit(G);const FVector2D P=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        const double Old=Zoom;Zoom=FMath::Clamp(Zoom*FMath::Pow(1.25,E.GetWheelDelta()),1.,6.);
        const FVector2D NewSize=SheetSize*(Zoom/Old);
        Pan=P-(P-SheetOffset)*(Zoom/Old)-(G.GetLocalSize()-NewSize)*.5;
        return FReply::Handled();
    }
    virtual FReply OnMouseButtonDown(const FGeometry& G,const FPointerEvent& E) override
    {
        if(E.GetEffectingButton()!=EKeys::LeftMouseButton)return FReply::Unhandled();
        bHeld=true;bMoved=false;DragStart=LastMouse=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        return FReply::Handled().CaptureMouse(AsShared());
    }
    virtual FReply OnMouseButtonUp(const FGeometry& G,const FPointerEvent& E) override
    {
        if(!bHeld)return FReply::Unhandled();bHeld=false;
        if(!bMoved){const int32 I=Pick(G,E);if(UJapanMap* M=Map.Get();M && M->GetZones().IsValidIndex(I))
        {const FString Key=M->GetZones()[I].Key;if(M->TeleportToZone(Key))M->Close();}}
        return FReply::Handled().ReleaseMouseCapture();
    }
private:
    TWeakObjectPtr<UJapanMap> Map;
    mutable FVector2D SheetOffset = FVector2D::ZeroVector, SheetSize = FVector2D(1,1);
    int32 Hovered = -1;
    double Zoom=1.;mutable FVector2D Pan=FVector2D::ZeroVector;FVector2D DragStart,LastMouse;bool bHeld=false,bMoved=false;
    FSlateBrush DiscBrush = ShapeBrush(0.f), TabBrush = ShapeBrush(5.f);
    void Fit(const FGeometry& G) const
    {
        const FVector2D Area = G.GetLocalSize();
        const FVector2D Image = Map.IsValid() ? Map->GetBrush()->ImageSize : FVector2D(3,2);
        const float Scale = FMath::Min(Area.X/Image.X, Area.Y/Image.Y);
        SheetSize=Image*Scale*Zoom;SheetOffset=(Area-SheetSize)*.5f+Pan;
        SheetOffset.X=SheetSize.X<=Area.X?(Area.X-SheetSize.X)*.5:FMath::Clamp(SheetOffset.X,Area.X-SheetSize.X,0.);
        SheetOffset.Y=SheetSize.Y<=Area.Y?(Area.Y-SheetSize.Y)*.5:FMath::Clamp(SheetOffset.Y,Area.Y-SheetSize.Y,0.);
        Pan=SheetOffset-(Area-SheetSize)*.5;
    }
    void Disc(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, const FVector2D& Centre, float Radius, const FLinearColor& Colour) const
    {
        FSlateDrawElement::MakeBox(Out,Layer,G.ToPaintGeometry(FVector2f(Radius*2,Radius*2),FSlateLayoutTransform(FVector2f(Centre-FVector2D(Radius,Radius)))),&DiscBrush,ESlateDrawEffect::None,Colour);
    }
    int32 Pick(const FGeometry& G, const FPointerEvent& E) const
    {
        const UJapanMap* M = Map.Get();
        if (!M) return -1;
        Fit(G);
        const FVector2D Local = G.AbsoluteToLocal(E.GetScreenSpacePosition());
        int32 Best = -1; float BestD = 26.f;
        for (int32 I = 0; I < M->GetZones().Num(); ++I)
        {
            const float D = FVector2D::Distance(Local,SheetOffset + M->ToSheet(M->GetZones()[I].Location)*SheetSize);
            if (D < BestD) { BestD = D; Best = I; }
        }
        return Best;
    }
};

void UJapanMap::Initialize(AWandererCharacter* Pawn)
{
    Owner = Pawn;
    const FString Dir = YoriDataPath(TEXT("map"));
    FString Text;
    if (!FFileHelper::LoadFileToString(Text,*(Dir/TEXT("map.json")))) { UE_LOG(LogTemp,Warning,TEXT("world map: %s/map.json missing (run atelier build yorimichi)"),*Dir); return; }
    TSharedPtr<FJsonObject> Root;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root) || !Root.IsValid()) { UE_LOG(LogTemp,Warning,TEXT("world map: map.json unreadable")); return; }
    const TArray<TSharedPtr<FJsonValue>>* B = nullptr;
    if (Root->TryGetArrayField(TEXT("bounds"),B) && B->Num() == 4)
        Bounds = FBox2D(FVector2D((*B)[0]->AsNumber(),(*B)[1]->AsNumber()),FVector2D((*B)[2]->AsNumber(),(*B)[3]->AsNumber()));
    auto ReadProjection=[&](const TCHAR* Key,TArray<FVector2D>& Dest)
    {
        const TArray<TSharedPtr<FJsonValue>>* Rows=nullptr;
        if(Root->TryGetArrayField(Key,Rows))for(const auto& Row:*Rows)
        {const auto& A=Row->AsArray();if(A.Num()==2)Dest.Add(FVector2D(A[0]->AsNumber(),A[1]->AsNumber()));}
    };
    ReadProjection(TEXT("projection_x"),ProjectionX);ReadProjection(TEXT("projection_y"),ProjectionY);
    const TArray<TSharedPtr<FJsonValue>>* Z = nullptr;
    if (Root->TryGetArrayField(TEXT("zones"),Z))
        for (const auto& V : *Z)
        {
            const TSharedPtr<FJsonObject>* O = nullptr;
            if (!V->TryGetObject(O)) continue;
            FJapanMapZone Zone;
            Zone.Key = (*O)->GetStringField(TEXT("key")); Zone.Name = (*O)->GetStringField(TEXT("name"));
            (*O)->TryGetStringField(TEXT("hint"),Zone.Hint);
            Zone.Location = AJapanWorld::ToUE((*O)->GetNumberField(TEXT("x")),(*O)->GetNumberField(TEXT("y")),(*O)->GetNumberField(TEXT("z")));
            Zone.Yaw = -(*O)->GetNumberField(TEXT("yaw"));
            if (!Zone.Key.IsEmpty()) Zones.Add(Zone);
        }
    // The skate pier (japan/skatepark) is newer than the painted sheet: add its stop unless map.json already has one.
    if (!Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("skatepier"); }))
    {
        FVector World; float Yaw = 0.f;
        if (ASkatePark::ReadParkSpawn(YoriDataPath(TEXT("skatepark/park.json")), World, Yaw))
        {
            FJapanMapZone Zone; Zone.Key = TEXT("skatepier"); Zone.Name = TEXT("Skate pier");
            Zone.Hint = TEXT("Concrete plaza on the sea: ramps, rails and ledges (B for the board)");
            Zone.Location = AJapanWorld::ToUE(World.X, World.Y, World.Z); Zone.Yaw = -Yaw;
            Zones.Add(Zone);
        }
    }
    ImageFile = Dir/TEXT("map.png");
    Texture = FImageUtils::ImportFileAsTexture2D(ImageFile);
    if (Texture)
    {
        Brush.SetResourceObject(Texture);
        Brush.ImageSize = FVector2D(Texture->GetSizeX(),Texture->GetSizeY());
        Brush.DrawAs = ESlateBrushDrawType::Image;
        Brush.TintColor = FLinearColor::White;
    }
    else UE_LOG(LogTemp,Warning,TEXT("world map: %s failed to load"),*ImageFile);
    bLoaded = Zones.Num() > 0 && Texture != nullptr;
    UE_LOG(LogTemp,Display,TEXT("world map: %d zones, sheet %s, bounds x %.0f..%.0f y %.0f..%.0f"),Zones.Num(),Texture ? *FString::Printf(TEXT("%dx%d"),Texture->GetSizeX(),Texture->GetSizeY()) : TEXT("missing"),Bounds.Min.X,Bounds.Max.X,Bounds.Min.Y,Bounds.Max.Y);
}

const FJapanMapZone* UJapanMap::FindZone(const FString& Key) const
{
    for (const auto& Z : Zones) if (Z.Key == Key) return &Z;
    return nullptr;
}

bool UJapanMap::TeleportToZone(const FString& Key)
{
    const FJapanMapZone* Z = FindZone(Key);
    if (!Z || !Owner) return false;
    return Owner->TravelTo(Z->Location,Z->Yaw,*Z->Name);
}

FVector2D UJapanMap::ToSheet(const FVector& Location) const
{
    auto Project=[](double V,const TArray<FVector2D>& Knots)
    {
        if(Knots.IsEmpty())return V;
        if(V<=Knots[0].X)return Knots[0].Y;
        for(int32 I=1;I<Knots.Num();++I)if(V<=Knots[I].X)
            return FMath::Lerp(Knots[I-1].Y,Knots[I].Y,(V-Knots[I-1].X)/(Knots[I].X-Knots[I-1].X));
        return Knots.Last().Y;
    };
    const double X=Project(Location.X/100.0,ProjectionX),Y=Project(-Location.Y/100.0,ProjectionY);
    return FVector2D((X-Bounds.Min.X)/(Bounds.Max.X-Bounds.Min.X),(Bounds.Max.Y-Y)/(Bounds.Max.Y-Bounds.Min.Y));
}

void UJapanMap::Open()
{
    if (IsOpen() || !bLoaded || !Owner || !GEngine || !GEngine->GameViewport) return;
    TSharedRef<SJapanMapSheet> Sheet = SNew(SJapanMapSheet).Map(this);
    Widget = SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.02f,.03f,.03f,.86f)).Padding(FMargin(30,18,30,16))
        [SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,10)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(FText::FromString(TEXT("Yorimichi  ·  world map"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",22)).ColorAndOpacity(FLinearColor(1,.96f,.86f,1))]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom)[SNew(STextBlock).Text(FText::FromString(TEXT("scroll to zoom · drag to explore · click a pin to travel · M or Esc closes"))).Font(FCoreStyle::GetDefaultFontStyle("Regular",13)).ColorAndOpacity(FLinearColor(.78f,.79f,.72f,1))]]
            + SVerticalBox::Slot().FillHeight(1)[Sheet]
            + SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)
                [SNew(STextBlock).Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor(1,.9f,.6f,1))
                    .Text_Lambda([Sheet,this]
                    {
                        const FString Hint = Sheet->GetHoveredHint();
                        if (!Hint.IsEmpty()) return FText::FromString(Hint);
                        if (Owner) { const FVector L = Owner->GetActorLocation(); return FText::FromString(FString::Printf(TEXT("You are here: %.0f m east, %.0f m north of the road's middle"),L.X/100.0,-L.Y/100.0)); }
                        return FText::GetEmpty();
                    })]];
    GEngine->GameViewport->AddViewportWidgetContent(Widget.ToSharedRef(),19);
    Owner->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    FSlateApplication::Get().SetKeyboardFocus(Sheet,EFocusCause::SetDirectly);
}

void UJapanMap::Close()
{
    if (Widget && GEngine && GEngine->GameViewport) GEngine->GameViewport->RemoveViewportWidgetContent(Widget.ToSharedRef());
    Widget.Reset();
    if (Owner) Owner->SetMenuOpen(false);
}
