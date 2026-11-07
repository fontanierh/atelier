#include "JapanAtlasWidget.h"
#include "JapanAtlasLabels.h"
#include "JapanMap.h"
#include "JapanMarkers.h"
#include "JapanHUD.h"
#include "JapanMapControls.h"
#include "WandererCharacter.h"
#include "AtelierData.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Styling/CoreStyle.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Text/STextBlock.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

namespace
{
FLinearColor C(const TCHAR* Hex) { return FLinearColor(FColor::FromHex(Hex)); }
const FLinearColor Gold=C(TEXT("D4B774")), Ink=C(TEXT("332C20")), Cream=C(TEXT("EBE2CA")), Muted=C(TEXT("A3AF9B"));
const FSlateBrush* White() { return FCoreStyle::Get().GetBrush("WhiteBrush"); }
FSlateFontInfo Font(int32 Size,bool Serif=false)
{
    const FString File=AtelierDataPath(TEXT("map/atlas-serif.ttf"));
    if (Serif && FPaths::FileExists(File)) return FSlateFontInfo(File,Size);
    return FCoreStyle::GetDefaultFontStyle(Serif?"Bold":"Regular",Size);
}
FSlateBrush Fill(const FLinearColor& Colour)
{
    FSlateBrush B; B.DrawAs=ESlateBrushDrawType::Box; B.TintColor=Colour; return B;
}
const FButtonStyle* ButtonStyle()
{
    static const FButtonStyle Style=[]
    {
        FButtonStyle S=FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("Button");
        S.Normal=Fill(C(TEXT("1C2B26"))); S.Hovered=Fill(C(TEXT("384331"))); S.Pressed=Fill(C(TEXT("4C5038")));
        S.NormalPadding=FMargin(10,7); S.PressedPadding=FMargin(10,7); return S;
    }();
    return &Style;
}
TSharedRef<STextBlock> Text(const FString& Value,int32 Size=13,const FLinearColor& Colour=Cream,bool Serif=false,bool Wrap=false)
{
    return SNew(STextBlock).Text(FText::FromString(Value)).Font(Font(Size,Serif)).ColorAndOpacity(Colour).AutoWrapText(Wrap);
}
TSharedRef<SButton> Button(const FString& Value,TFunction<void()> Action)
{
    return SNew(SButton).ButtonStyle(ButtonStyle()).IsFocusable(false).ContentPadding(FMargin(10,7))
        .OnClicked_Lambda([Action]{Action();return FReply::Handled();})[Text(Value,12)];
}
TSharedRef<SButton> DynamicButton(TFunction<FString()> Label,TFunction<void()> Action)
{
    return SNew(SButton).ButtonStyle(ButtonStyle()).IsFocusable(false).ContentPadding(FMargin(10,7))
        .OnClicked_Lambda([Action]{Action();return FReply::Handled();})
        [SNew(STextBlock).Font(Font(12)).ColorAndOpacity(Cream).Text_Lambda([Label]{return FText::FromString(Label());})];
}

/** Text input consumes unhandled keys before they reach gameplay. */
class SAtlasTextBox : public SEditableTextBox
{
public:
    TWeakObjectPtr<UJapanMap> Map;
    bool bMarker = false;
    virtual FReply OnPreviewKeyDown(const FGeometry&,const FKeyEvent& E) override
    {
        if (E.GetKey()==EKeys::Gamepad_FaceButton_Right)
        { if (!E.IsRepeat()) if (auto* M=Map.Get()) M->AtlasBack(); return FReply::Handled(); }
        if (E.GetKey()==EKeys::Escape || E.GetKey()==EKeys::Gamepad_Special_Left || E.GetKey()==EKeys::Gamepad_Special_Right)
        { if (auto* M=Map.Get()) M->Close(); return FReply::Handled(); }
        if (E.GetKey()==EKeys::F5)
        { if (bMarker && !E.IsRepeat()) if (auto* M=Map.Get()) M->SaveMarker(GetText().ToString()); return FReply::Handled(); }
        return FReply::Unhandled();
    }
    virtual FReply OnKeyDown(const FGeometry& G,const FKeyEvent& E) override
    {
        const auto R=SEditableTextBox::OnKeyDown(G,E); return R.IsEventHandled()?R:FReply::Handled();
    }
};

class SAtlasOverview : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SAtlasOverview){} SLATE_ARGUMENT(UJapanMap*,Map) SLATE_END_ARGS()
    void Construct(const FArguments& A) { Map=A._Map; }
    virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(200,138); }
    virtual int32 OnPaint(const FPaintArgs&,const FGeometry& G,const FSlateRect&,FSlateWindowElementList& Out,int32 Layer,const FWidgetStyle&,bool) const override
    {
        const auto* M=Map.Get();const auto* World=M?M->GetAtlasFrame(TEXT("world")):nullptr;if(!World)return Layer;
        const FVector2D Area=G.GetLocalSize(),Image(World->Brush.ImageSize);
        const double Scale=FMath::Min(Area.X/Image.X,Area.Y/Image.Y);const FVector2D Extent=Image*Scale,Origin=(Area-Extent)*.5;
        FSlateDrawElement::MakeBox(Out,Layer,G.ToPaintGeometry(FVector2f(Extent),FSlateLayoutTransform(FVector2f(Origin))),&World->Brush);
        if(const auto* R=M->GetAtlasFrame(M->GetAtlasRegion()))
        {
            TArray<FVector2f> P;
            for(const auto& V:R->Polygon)P.Add(FVector2f(Origin+M->ToAtlas(FVector(V.X*100.,-V.Y*100.,0),TEXT("world"))*Extent));
            if(!P.IsEmpty()){const FVector2f First=P[0]; P.Add(First);FSlateDrawElement::MakeLines(Out,Layer+1,G.ToPaintGeometry(),P,ESlateDrawEffect::None,Gold,true,2.f);}
        }
        return Layer+2;
    }
    virtual FReply OnMouseButtonDown(const FGeometry&,const FPointerEvent& E) override
    {if(E.GetEffectingButton()==EKeys::LeftMouseButton)if(auto* M=Map.Get())M->SelectAtlasRegion(TEXT("world"));return FReply::Handled();}
private:
    TWeakObjectPtr<UJapanMap> Map;
};

class SAtlasSheet : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SAtlasSheet){} SLATE_ARGUMENT(UJapanMap*,Map) SLATE_END_ARGS()
    void Construct(const FArguments& A)
    {
        Map=A._Map; bPad=AJapanHUD::CurrentControllerStyle()!=0; SetClipping(EWidgetClipping::ClipToBounds);
        DiscBrush=Fill(FLinearColor::White); DiscBrush.DrawAs=ESlateBrushDrawType::RoundedBox;
        DiscBrush.OutlineSettings.RoundingType=ESlateBrushRoundingType::HalfHeightRadius;
        ResetView();
    }
    virtual bool SupportsKeyboardFocus() const override { return true; }
    virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(1200,800); }
    void ResetView()
    {
        Zoom=1.; Pan=FVector2D::ZeroVector; Hot.Empty(); bPinned=false;
        if (const auto* M=Map.Get()) { View=M->GetAtlasRegion(); if (const auto* Pawn=M->GetOwnerPawn()) Cursor=M->ToAtlas(Pawn->GetActorLocation()).ClampAxes(0.,1.); }
    }
    void SetZoom(double Factor)
    {
        const double Before=Zoom; Zoom=FMath::Clamp(Zoom*Factor,1.,12.);
        if(bPad)Pan+=(Cursor-FVector2D(.5,.5))*Size*(1.-Zoom/Before);
    }
    FString ReturnHint() const
    { return bPad ? FString::Printf(TEXT("Return · %s"),MapPadLabels(AJapanHUD::CurrentControllerStyle()).Return) : TEXT("Return · F9"); }
    bool IsControllerMode() const { return bPad; }
    FString Hint() const
    {
        if (const auto* M=Map.Get();M && !M->GetAtlasError().IsEmpty()) return M->GetAtlasError();
        const auto L=MapPadLabels(AJapanHUD::CurrentControllerStyle());
        FString Help=bPad ? FString::Printf(TEXT("Left stick / d-pad: choose · Right stick: pan · %s: cycle places · %s: zoom · %s: select · %s: back · %s: current region · %s: fit · %s: save · %s: return"),L.Cycle,L.Zoom,L.Travel,L.Close,L.Current,L.Fit,L.Mark,L.Return)
                          : FString(TEXT("Click a destination to travel  ·  Scroll to zoom  ·  Drag to pan  ·  Right-click to go back"));
        for (const auto& T:Targets()) if (T.Key==Hot)
            return T.Name+TEXT(" · ")+(bPad?FString(L.Travel):FString(TEXT("Select")))+TEXT(": ")+(T.bTravel?TEXT("travel"):T.bEditable?TEXT("rename"):TEXT("open region"))+TEXT("\n")+Help;
        return Help;
    }
    FString Snapshot() const
    {
        auto O=MakeShared<FJsonObject>();O->SetStringField(TEXT("focus"),Hot);O->SetBoolField(TEXT("pad"),bPad);
        O->SetNumberField(TEXT("zoom"),Zoom);O->SetNumberField(TEXT("pan_x"),Pan.X);O->SetNumberField(TEXT("pan_y"),Pan.Y);
        O->SetNumberField(TEXT("screen_x"),Offset.X+Cursor.X*Size.X);O->SetNumberField(TEXT("screen_y"),Offset.Y+Cursor.Y*Size.Y);
        O->SetNumberField(TEXT("cursor_x"),Cursor.X);O->SetNumberField(TEXT("cursor_y"),Cursor.Y);O->SetStringField(TEXT("hint"),Hint());O->SetStringField(TEXT("return_hint"),ReturnHint());
        TArray<TSharedPtr<FJsonValue>> Keys;for(const auto& T:Targets())Keys.Add(MakeShared<FJsonValueString>(T.Key));O->SetArrayField(TEXT("targets"),Keys);
        FString Result;FJsonSerializer::Serialize(O,TJsonWriterFactory<>::Create(&Result));return Result;
    }
    virtual int32 OnPaint(const FPaintArgs&, const FGeometry& G,const FSlateRect&,FSlateWindowElementList& Out,int32 Layer,const FWidgetStyle&,bool) const override
    {
        const auto* M=Map.Get(); if (!M) return Layer; Fit(G);
        const auto& Air=M->GetAtlasAirRoute();
        auto AirStop=[&Air](const FString& Key)->const FJapanAtlasAirStop*
        { return Air.Stops.FindByPredicate([&Key](const FJapanAtlasAirStop& S){return S.Key==Key;}); };
        const FVector2D Area=G.GetLocalSize();
        const FLinearColor Background=View==TEXT("world")?C(TEXT("0E1B18")):C(TEXT("B9A379"));
        FSlateDrawElement::MakeBox(Out,Layer,G.ToPaintGeometry(),White(),ESlateDrawEffect::None,Background);
        FSlateDrawElement::MakeBox(Out,Layer+1,G.ToPaintGeometry(FVector2f(Size),FSlateLayoutTransform(FVector2f(Offset))),M->GetAtlasBrush(),ESlateDrawEffect::None,FLinearColor::White);
        if (Air.Stops.Num() && Air.Legs.Num())
        {
            for (const auto& Leg : Air.Legs)
            {
                const auto* A=AirStop(Leg.From); const auto* B=AirStop(Leg.To); if (!A || !B) continue;
                const FVector2D PA=Offset+M->ToAtlas(A->Location)*Size, PB=Offset+M->ToAtlas(B->Location)*Size;
                FSlateDrawElement::MakeLines(Out,Layer+2,G.ToPaintGeometry(),{FVector2f(PA),FVector2f(PB)},ESlateDrawEffect::None,FLinearColor(.02f,.05f,.06f,.35f),true,3.5f);
                DashedLine(Out,Layer+2,G,PA,PB,Gold,1.5f,10.f,7.f);
                AirChevron(Out,Layer+2,G,PA,PB,Gold);
            }
            for (const auto& Stop : Air.Stops)
            {
                const FVector2D P=Offset+M->ToAtlas(Stop.Location)*Size;
                AirDiamond(Out,Layer+2,G,P,7.f,Gold);
            }
        }
        if (View==TEXT("world")) for (const auto& R:M->GetAtlasRegions()) if (R.Key==Hot)
        {
            TArray<FVector2f> P;
            for (const auto& V:R.Polygon) P.Add(FVector2f(Offset+M->ToAtlas(FVector(V.X*100.,-V.Y*100.,0))*Size));
            if (!P.IsEmpty()) { const FVector2f First=P[0]; P.Add(First); FSlateDrawElement::MakeLines(Out,Layer+2,G.ToPaintGeometry(),P,ESlateDrawEffect::None,Gold,true,2.f); }
        }

        const auto TargetsNow=Targets();
        TArray<FAtlasLabelRequest> Requests;
        TArray<FAtlasLabelBox> Obstacles;
        TArray<FVector2D> Anchors;
        Requests.Reserve(TargetsNow.Num()); Anchors.Reserve(TargetsNow.Num());
        for (const auto& T:TargetsNow)
        {
            const bool Region=T.Category==TEXT("region"),Stable=T.bEditable,Marker=T.Category==TEXT("marker"),Hover=T.Key==Hot;
            const int32 PointSize=Region?17:Hover?15:12;
            const FVector2D P=Offset+M->ToAtlas(T.Location)*Size;
            Anchors.Add(P);
            FAtlasLabelRequest Request;
            Request.Anchor=P; Request.Size=Measure(T.Name,PointSize,true)+FVector2D(10,4);
            Request.Priority=Region?100:Hover?1000:Marker?70:Stable?60:T.Category==TEXT("player")?90:T.Category==TEXT("station")?55:50;
            Request.bForce=Hover; Request.bCentered=Region;
            Requests.Add(Request);
            if (!Region)
            {
                const float Radius=Hover?14.f:11.f;
                Obstacles.Add(AtlasLabelLayout::BoxAt(P-FVector2D(Radius,Radius),FVector2D(Radius*2,Radius*2)));
            }
        }
        if (const auto* Pawn=M->GetOwnerPawn())
        {
            const auto UV=M->ToAtlas(Pawn->GetActorLocation());
            if (UV.X>=0 && UV.X<=1 && UV.Y>=0 && UV.Y<=1)
            {
                const FVector2D P=Offset+UV*Size;
                Obstacles.Add(AtlasLabelLayout::BoxAt(P-FVector2D(26,26),FVector2D(52,52)));
            }
        }
        const int32 AirLabelStart=Requests.Num();
        TArray<FString> AirLabelText;
        for (const auto& Leg : Air.Legs)
        {
            const auto* A=AirStop(Leg.From); const auto* B=AirStop(Leg.To); if (!A || !B) continue;
            const FVector2D Mid=M->ToAtlas((A->Location+B->Location)*.5f);
            if (Mid.X<0.f || Mid.X>1.f || Mid.Y<0.f || Mid.Y>1.f) continue;
            const FString Time=FString::Printf(TEXT("%.0fs"),Leg.Seconds);
            FAtlasLabelRequest R; R.Anchor=Offset+Mid*Size; R.Size=Measure(Time,10,false)+FVector2D(8,2);
            R.Priority=30; R.bCentered=true;
            Requests.Add(R); AirLabelText.Add(Time);
        }
        const auto Placements=AtlasLabelLayout::LayOut(Requests,Obstacles,Area,16.f,8.f);

        // Region captions are placed first and keep a leader back to their true centre.
        for (int32 I=0;I<TargetsNow.Num();++I)
        {
            const auto& T=TargetsNow[I];
            if (T.Category!=TEXT("region") || !Placements[I].bVisible || T.Link.Equals(T.Location,1.)) continue;
            const FVector2D Link=Offset+M->ToAtlas(T.Link)*Size;
            const FVector2D Centre=Placements[I].Position+Requests[I].Size*.5f;
            FSlateDrawElement::MakeLines(Out,Layer+2,G.ToPaintGeometry(),{FVector2f(Link),FVector2f(Centre)},ESlateDrawEffect::None,Gold.CopyWithNewOpacity(.8f),true,1.2f);
            Disc(Out,Layer+3,G,Link,3.f,Gold);
        }

        // Pins stay put; only their labels move.
        for (int32 I=0;I<TargetsNow.Num();++I)
        {
            const auto& T=TargetsNow[I];
            if (T.Category==TEXT("region")) continue;
            const bool Hover=T.Key==Hot,Marker=T.Category==TEXT("marker"),Stable=T.bEditable;
            const FVector2D P=Anchors[I];
            Disc(Out,Layer+3,G,P,Hover?11.f:8.f,C(TEXT("21382D")));
            Ring(Out,Layer+4,G,P,Hover?12.f:9.f,1.4f,Gold);
            DrawText(Out,Layer+5,G,T.Category==TEXT("player")?TEXT("P"):Marker?TEXT("M"):Stable?TEXT("◇"):T.Category==TEXT("station")?TEXT("T"):TEXT("•"),P,11,Gold,false,true);
        }

        if (const auto* Pawn=M->GetOwnerPawn())
        {
            const auto UV=M->ToAtlas(Pawn->GetActorLocation());
            if (UV.X>=0 && UV.X<=1 && UV.Y>=0 && UV.Y<=1)
            {
                const auto P=Offset+UV*Size; const double A=FMath::DegreesToRadians(UJapanMap::SheetHeading(Pawn->GetActorRotation().Yaw));
                const FVector2D D(FMath::Cos(A),FMath::Sin(A)),N(-D.Y,D.X);
                Disc(Out,Layer+8,G,P,14,C(TEXT("132D41")).CopyWithNewOpacity(.8f));
                TArray<FVector2f> Points={FVector2f(P+D*17),FVector2f(P-D*8+N*8),FVector2f(P-D*3),FVector2f(P-D*8-N*8),FVector2f(P+D*17)};
                FSlateDrawElement::MakeLines(Out,Layer+9,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,Cream,true,3.f);
            }
        }
        for (int32 I=AirLabelStart;I<Requests.Num();++I)
        {
            if (!Placements[I].bVisible) continue;
            const FVector2D Pos=Placements[I].Position, Extent=Requests[I].Size;
            FSlateDrawElement::MakeBox(Out,Layer+10,G.ToPaintGeometry(FVector2f(Extent),FSlateLayoutTransform(FVector2f(Pos))),White(),ESlateDrawEffect::None,C(TEXT("132D41")).CopyWithNewOpacity(.88f));
            DrawText(Out,Layer+11,G,AirLabelText[I-AirLabelStart],Pos+FVector2D(4,1),10,Gold,false,false);
        }

        // Labels are drawn after the pins, with the hovered label last and on top.
        for (int32 Pass=0;Pass<2;++Pass) for (int32 I=0;I<TargetsNow.Num();++I)
        {
            const auto& T=TargetsNow[I]; const bool Hover=T.Key==Hot;
            if (Hover!=(Pass==1) || !Placements[I].bVisible) continue;
            const FVector2D Pos=Placements[I].Position, Extent=Requests[I].Size;
            if (Placements[I].bLeader)
            {
                const FVector2D P=Anchors[I];
                const FVector2D Edge(FMath::Clamp(P.X,Pos.X,Pos.X+Extent.X),FMath::Clamp(P.Y,Pos.Y,Pos.Y+Extent.Y));
                FSlateDrawElement::MakeLines(Out,Layer+10,G.ToPaintGeometry(),{FVector2f(P),FVector2f(Edge)},ESlateDrawEffect::None,Ink.CopyWithNewOpacity(.55f),true,1.f);
            }
            const int32 PointSize=T.Category==TEXT("region")?17:Hover?15:12;
            FSlateDrawElement::MakeBox(Out,Layer+11,G.ToPaintGeometry(FVector2f(Extent),FSlateLayoutTransform(FVector2f(Pos))),White(),ESlateDrawEffect::None,C(TEXT("EBD7AC")).CopyWithNewOpacity(Hover?.98f:.88f));
            DrawText(Out,Layer+12,G,T.Name,Pos+FVector2D(5,2),PointSize,Ink,true,false);
        }

        if (bPad) {const auto P=Offset+Cursor*Size;Ring(Out,Layer+13,G,P,Hot.IsEmpty()?13:18,4,C(TEXT("182C23")));Ring(Out,Layer+14,G,P,Hot.IsEmpty()?13:18,1.5f,Cream);}
        return Layer+15;
    }
    virtual void Tick(const FGeometry& G,double Now,float Dt) override
    {
        SLeafWidget::Tick(G,Now,Dt); auto* M=Map.Get(); if (!M) return;
        if (View!=M->GetAtlasRegion()) ResetView();
        if (!HasKeyboardFocus() && !M->IsEditingMapText()) FSlateApplication::Get().SetKeyboardFocus(AsShared(),EFocusCause::SetDirectly);
        if (!bPad) return;
        Fit(G); const double Speed=G.GetLocalSize().Y*.55*Dt;
        const auto L=Shape(Left),R=Shape(Right);
        if (!R.IsZero() && Zoom>1)
        {
            const auto Before=Offset;Pan-=FVector2D(R.X,-R.Y)*Speed*1.4;Fit(G);
            Cursor=(Cursor+(Before-Offset)/Size).ClampAxes(0.,1.);bPinned=false;
        }
        if (!L.IsZero()) {Cursor=(Cursor+FVector2D(L.X,-L.Y)*Speed/Size).ClampAxes(0.,1.);bPinned=false;}
        if(bPinned && !Targets().ContainsByPredicate([this](const FJapanAtlasTarget& T){return T.Key==Hot;}))bPinned=false;
        Fit(G); if(!bPinned)Hot=Pick(G,Offset+Cursor*Size,30);
        if (L.IsZero() && R.IsZero()) for (const auto& T:Targets()) if (T.Key==Hot) Cursor=FMath::Lerp(Cursor,M->ToAtlas(T.Location),FMath::Min(1.,Dt*12.));
        const FVector2D P=Offset+Cursor*Size,A=G.GetLocalSize();const FVector2D Margin(55,55);
        Pan+=((Margin-P).ComponentMax(FVector2D::ZeroVector)-(P-(A-Margin)).ComponentMax(FVector2D::ZeroVector))*FMath::Min(1.,Dt*9.);
    }
    virtual FReply OnKeyDown(const FGeometry& G,const FKeyEvent& E) override
    {
        auto* M=Map.Get();if (!M)return FReply::Handled();const FKey K=E.GetKey();bPad=K.IsGamepadKey();
        if (K==EKeys::Escape || K==EKeys::M || K==EKeys::Gamepad_Special_Left || K==EKeys::Gamepad_Special_Right) {M->Close();return FReply::Handled();}
        if (K==EKeys::BackSpace || K==EKeys::Gamepad_FaceButton_Right) {if(!E.IsRepeat())M->AtlasBack();return FReply::Handled();}
        if (K==EKeys::F5 || K==EKeys::Gamepad_FaceButton_Top) {if(!E.IsRepeat())M->SetMarker();return FReply::Handled();}
        if (K==EKeys::F9 || K==EKeys::Gamepad_FaceButton_Left) {if(!E.IsRepeat()&&M->ReturnToMarker())M->Close();return FReply::Handled();}
        const auto Direction=K==EKeys::Up || K==EKeys::Gamepad_DPad_Up?FVector2D(0,-1):K==EKeys::Down || K==EKeys::Gamepad_DPad_Down?FVector2D(0,1):K==EKeys::Left || K==EKeys::Gamepad_DPad_Left?FVector2D(-1,0):K==EKeys::Right || K==EKeys::Gamepad_DPad_Right?FVector2D(1,0):FVector2D::ZeroVector;
        if (!Direction.IsZero()) {bPad=true;Hop(G,Direction);return FReply::Handled();}
        if (E.IsRepeat())return FReply::Handled();
        if (K==EKeys::Enter || K==EKeys::Gamepad_FaceButton_Bottom) Activate();
        else if(K==EKeys::Gamepad_LeftTrigger || K==EKeys::Gamepad_RightTrigger)Cycle(K==EKeys::Gamepad_LeftTrigger?-1:1);
        else if(K==EKeys::Gamepad_RightThumbstick)ResetView();
        else if(K==EKeys::Gamepad_LeftThumbstick){M->AtlasCurrentRegion();ResetView();}
        else if (K==EKeys::Gamepad_RightShoulder || K==EKeys::Add || K==EKeys::Equals) SetZoom(1.4);
        else if (K==EKeys::Gamepad_LeftShoulder || K==EKeys::Subtract || K==EKeys::Hyphen) SetZoom(1./1.4);
        return FReply::Handled();
    }
    virtual FReply OnAnalogValueChanged(const FGeometry&,const FAnalogInputEvent& E) override
    {
        const auto K=E.GetKey(); const float V=E.GetAnalogValue();
        if(K==EKeys::Gamepad_LeftX)Left.X=V;else if(K==EKeys::Gamepad_LeftY)Left.Y=V;else if(K==EKeys::Gamepad_RightX)Right.X=V;else if(K==EKeys::Gamepad_RightY)Right.Y=V;
        if (FMath::Abs(V)>.25f)bPad=true;return FReply::Handled();
    }
    virtual FNavigationReply OnNavigation(const FGeometry&,const FNavigationEvent&) override{return FNavigationReply::Stop();}
    virtual FReply OnMouseMove(const FGeometry& G,const FPointerEvent& E) override
    {
        const auto P=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        if(Held){Moved|=FVector2D::Distance(P,Start)>5.;if(Moved)Pan+=P-Last;Last=P;return FReply::Handled();}
        if(!E.GetCursorDelta().IsNearlyZero()){bPad=false;bPinned=false;Hot=Pick(G,P,24);}return FReply::Handled();
    }
    virtual void OnMouseLeave(const FPointerEvent&) override {if(!bPad)Hot.Empty();}
    virtual FReply OnMouseWheel(const FGeometry& G,const FPointerEvent& E) override
    {
        bPad=false;bPinned=false;
        Fit(G);const auto P=G.AbsoluteToLocal(E.GetScreenSpacePosition());const double Old=Zoom;SetZoom(FMath::Pow(1.25,E.GetWheelDelta()));
        Pan=P-(P-Offset)*(Zoom/Old)-(G.GetLocalSize()-Size*(Zoom/Old))*.5;return FReply::Handled();
    }
    virtual FReply OnMouseButtonDown(const FGeometry& G,const FPointerEvent& E) override
    {
        if(E.GetEffectingButton()==EKeys::RightMouseButton){if(auto* M=Map.Get())M->AtlasBack();return FReply::Handled();}
        if(E.GetEffectingButton()!=EKeys::LeftMouseButton)return FReply::Handled();
        Held=true;Moved=false;bPad=false;bPinned=false;Start=Last=G.AbsoluteToLocal(E.GetScreenSpacePosition());return FReply::Handled().CaptureMouse(AsShared());
    }
    virtual FReply OnMouseButtonUp(const FGeometry& G,const FPointerEvent& E) override
    {
        if(E.GetEffectingButton()!=EKeys::LeftMouseButton || !Held)return FReply::Handled();Held=false;
        if(!Moved){Hot=Pick(G,G.AbsoluteToLocal(E.GetScreenSpacePosition()),24);Activate();}return FReply::Handled().ReleaseMouseCapture();
    }
private:
    TWeakObjectPtr<UJapanMap> Map;
    mutable FVector2D Offset=FVector2D::ZeroVector,Size=FVector2D(1,1),Pan=FVector2D::ZeroVector;
    FVector2D Cursor=FVector2D(.5,.5),Left=FVector2D::ZeroVector,Right=FVector2D::ZeroVector,Start,Last;
    double Zoom=1.;bool bPad=false,bPinned=false,Held=false,Moved=false;FString View,Hot;FSlateBrush DiscBrush;
    static FVector2D Shape(const FVector2D& V){const double L=V.Size();return L<.2?FVector2D::ZeroVector:V/L*FMath::Square(FMath::Min(1.,(L-.2)/.8));}
    TArray<FJapanAtlasTarget> Targets() const
    {
        const auto* M=Map.Get();if(!M)return {};auto T=M->GetAtlasTargets();
        T.RemoveAll([M](const FJapanAtlasTarget& P){const auto UV=M->ToAtlas(P.Location);return UV.X<0 || UV.X>1 || UV.Y<0 || UV.Y>1;});
        if(View==TEXT("world") && M->SearchText.IsEmpty())T.RemoveAll([](const FJapanAtlasTarget& P){return P.Category!=TEXT("region") && P.Category!=TEXT("player") && P.Region!=TEXT("world");});return T;
    }
    void Fit(const FGeometry& G) const
    {
        const auto* M=Map.Get();const FVector2D Image=M?FVector2D(M->GetAtlasBrush()->ImageSize):FVector2D(3,2),Area=G.GetLocalSize();
        const double Scale=FMath::Min(Area.X/FMath::Max(1.,Image.X),Area.Y/FMath::Max(1.,Image.Y));Size=Image*Scale*Zoom;Offset=(Area-Size)*.5+Pan;
        Offset.X=Size.X<=Area.X?(Area.X-Size.X)*.5:FMath::Clamp(Offset.X,Area.X-Size.X,0.);Offset.Y=Size.Y<=Area.Y?(Area.Y-Size.Y)*.5:FMath::Clamp(Offset.Y,Area.Y-Size.Y,0.);Pan=Offset-(Area-Size)*.5;
    }
    FString Pick(const FGeometry& G,const FVector2D& P,double Radius) const
    {
        const auto* M=Map.Get();if(!M)return {};Fit(G);FString Best;double Distance=Radius;
        for(const auto& T:Targets()){const double D=FVector2D::Distance(P,Offset+M->ToAtlas(T.Location)*Size);if(D<Distance){Distance=D;Best=T.Key;}}
        if(Best.IsEmpty() && View==TEXT("world"))if(const auto* F=M->GetAtlasFrame(TEXT("world")))
        {
            const auto UV=(P-Offset)/Size;if(UV.X>=0 && UV.X<=1 && UV.Y>=0 && UV.Y<=1)
            {const auto B=F->Bounds;const FString Region=M->RegionForLocation(FVector((B.Min.X+UV.X*B.GetSize().X)*100.,-(B.Max.Y-UV.Y*B.GetSize().Y)*100.,0));if(Region!=TEXT("world"))Best=Region;}
        }
        return Best;
    }
    void Activate()
    {
        if(auto* M=Map.Get())for(const auto& T:Targets())if(T.Key==Hot)
        {if(T.Category==TEXT("region"))M->SelectAtlasRegion(T.Key);else if(T.bEditable)M->SelectStable(T.Key);else if(T.bTravel && M->TeleportToZone(T.Key))M->Close();return;}
    }
    void Hop(const FGeometry& G,const FVector2D& Direction)
    {
        const auto* M=Map.Get();if(!M)return;Fit(G);const auto From=Offset+Cursor*Size;double Best=TNumericLimits<double>::Max();
        for(const auto& T:Targets())
        {const auto D=Offset+M->ToAtlas(T.Location)*Size-From;const double Along=D|Direction,Across=FMath::Abs(D^Direction);if(Along<5 || Across>Along*1.8)continue;
         if(Along+Across*2<Best){Best=Along+Across*2;Cursor=M->ToAtlas(T.Location);Hot=T.Key;bPinned=true;}}
    }
    void Cycle(int32 Direction)
    {
        const auto* M=Map.Get();const auto T=Targets();if(!M || T.IsEmpty())return;
        int32 Index=T.IndexOfByPredicate([this](const FJapanAtlasTarget& P){return P.Key==Hot;});
        Index=Index==INDEX_NONE?(Direction>0?0:T.Num()-1):(Index+Direction+T.Num())%T.Num();
        Hot=T[Index].Key;Cursor=M->ToAtlas(T[Index].Location);bPinned=true;
    }
    static FVector2D Measure(const FString& S,int32 Size,bool Serif){return FSlateApplication::Get().GetRenderer()->GetFontMeasureService()->Measure(S,Font(Size,Serif));}
    void DrawText(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FString& S,FVector2D P,int32 PointSize,const FLinearColor& Colour,bool Serif,bool Center) const
    {const auto Extent=Measure(S,PointSize,Serif);if(Center)P-=Extent*.5;FSlateDrawElement::MakeText(Out,L,G.ToPaintGeometry(FVector2f(Extent),FSlateLayoutTransform(FVector2f(P))),S,Font(PointSize,Serif),ESlateDrawEffect::None,Colour);}
    void DashedLine(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FVector2D& A,const FVector2D& B,const FLinearColor& Colour,float Thickness,float Dash,float Gap) const
    {
        const FVector2D D=B-A; const float Length=D.Size(); if (Length<1.f) return;
        const FVector2D U=D/Length;
        for (float T=0.f;T<Length;T+=Dash+Gap)
        {
            const float E=FMath::Min(T+Dash,Length);
            FSlateDrawElement::MakeLines(Out,L,G.ToPaintGeometry(),{FVector2f(A+U*T),FVector2f(A+U*E)},ESlateDrawEffect::None,Colour,true,Thickness);
        }
    }
    void AirDiamond(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FVector2D& P,float R,const FLinearColor& Colour) const
    {
        TArray<FVector2f> Points={FVector2f(P+FVector2D(0,-R)),FVector2f(P+FVector2D(R,0)),FVector2f(P+FVector2D(0,R)),FVector2f(P+FVector2D(-R,0)),FVector2f(P+FVector2D(0,-R))};
        FSlateDrawElement::MakeLines(Out,L,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,Colour,true,1.5f);
    }
    void AirChevron(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FVector2D& A,const FVector2D& B,const FLinearColor& Colour) const
    {
        const FVector2D D=B-A; if (D.Size()<1.f) return;
        const FVector2D U=D/D.Size(), N(-U.Y,U.X), M=(A+B)*.5f;
        TArray<FVector2f> Points={FVector2f(M+U*6.f),FVector2f(M-U*4.f+N*5.f),FVector2f(M-U*4.f-N*5.f),FVector2f(M+U*6.f)};
        FSlateDrawElement::MakeLines(Out,L,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,Colour,true,1.5f);
    }
    void Disc(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FVector2D& P,float R,const FLinearColor& Colour) const
    {FSlateDrawElement::MakeBox(Out,L,G.ToPaintGeometry(FVector2f(R*2,R*2),FSlateLayoutTransform(FVector2f(P-FVector2D(R,R)))),&DiscBrush,ESlateDrawEffect::None,Colour);}
    static void Ring(FSlateWindowElementList& Out,int32 L,const FGeometry& G,const FVector2D& P,float R,float Width,const FLinearColor& Colour)
    {TArray<FVector2f> Points;for(int32 I=0;I<=32;++I){const double A=I*UE_TWO_PI/32.;Points.Add(FVector2f(P+FVector2D(FMath::Cos(A),FMath::Sin(A))*R));}FSlateDrawElement::MakeLines(Out,L,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,Colour,true,Width);}
};
}

/** Landscape atlas chrome; text/places are widgets and never painted into the map texture. */
class SJapanAtlas : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SJapanAtlas){} SLATE_ARGUMENT(UJapanMap*,Map) SLATE_END_ARGS()
    void Construct(const FArguments& A)
    {
        Map=A._Map;auto* M=Map.Get();
        Sheet=SNew(SAtlasSheet).Map(M);
        auto Search=SNew(SAtlasTextBox).HintText(FText::FromString(TEXT("Find a place..."))).Font(Font(13))
            .OnTextChanged_Lambda([this](const FText& T){if(auto* P=Map.Get())P->SearchText=T.ToString();});
        Search->Map=M;M->AtlasSearch=Search;
        auto Marker=SNew(SAtlasTextBox).HintText(FText::FromString(TEXT("Name a saved place"))).Font(Font(12)).SelectAllTextWhenFocused(true).ClearKeyboardFocusOnCommit(false)
            .Text(FText::FromString(M->MarkerStore()?M->MarkerStore()->NextName():FString(TEXT("Marker 1"))))
            .OnTextCommitted_Lambda([this](const FText& T,ETextCommit::Type Type){if(Type==ETextCommit::OnEnter)if(auto* P=Map.Get();P&&P->SaveMarker(T.ToString()))P->MarkerName->SetText(FText::FromString(P->MarkerStore()->NextName()));});
        Marker->Map=M;Marker->bMarker=true;M->MarkerName=Marker;
        ChildSlot
        [SNew(SBorder).BorderImage(White()).BorderBackgroundColor(C(TEXT("101A19"))).Padding(18)
         [SNew(SBorder).BorderImage(White()).BorderBackgroundColor(C(TEXT("8F8055"))).Padding(1)
          [SNew(SVerticalBox)
           +SVerticalBox::Slot().AutoHeight()
           [SNew(SBorder).BorderImage(White()).BorderBackgroundColor(C(TEXT("1B2D27"))).Padding(FMargin(22,14))
            [SNew(SHorizontalBox)
             +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,40,0)[Text(TEXT("YORIMICHI"),24,Gold,true)]
             +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Button(TEXT("World"),[this]{if(auto* P=Map.Get())P->SelectAtlasRegion(TEXT("world"));})]
             +SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center).Padding(12,0)[SNew(STextBlock).Font(Font(14)).ColorAndOpacity(Cream).Text_Lambda([this]{return FText::FromString(TEXT("›  ")+(Map.IsValid()?Map->GetAtlasTitle():FString()));})]
             +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,12,0)[SNew(SBox).WidthOverride(210)[Search]]
             +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)[Button(TEXT("×"),[this]{if(auto* P=Map.Get())P->Close();})]]]
           +SVerticalBox::Slot().FillHeight(1)
           [SNew(SHorizontalBox)
            +SHorizontalBox::Slot().AutoWidth()
            [SNew(SBox).WidthOverride(248)
             [SNew(SBorder).BorderImage(White()).BorderBackgroundColor(C(TEXT("192B24"))).Padding(18)
              [SNew(SVerticalBox)
               +SVerticalBox::Slot().AutoHeight()[Text(TEXT("REGION ATLAS"),10,Gold)]
               +SVerticalBox::Slot().AutoHeight().Padding(0,10,0,5)[SNew(STextBlock).Font(Font(26,true)).ColorAndOpacity(Cream).AutoWrapText(true).Text_Lambda([this]{return FText::FromString(Map.IsValid()?Map->GetAtlasTitle():FString());})]
               +SVerticalBox::Slot().AutoHeight().Padding(0,3,0,15)[Button(TEXT("←  World overview"),[this]{if(auto* P=Map.Get())P->SelectAtlasRegion(TEXT("world"));})]
               +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,8)[SNew(STextBlock).Font(Font(9)).ColorAndOpacity(Gold).AutoWrapText(true).Text_Lambda([this]{return FText::FromString(AirLegend());})]
               +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,12)[SNew(SAtlasOverview).Map(M).Visibility_Lambda([this]{return Map.IsValid()&&Map->GetAtlasRegion()!=TEXT("world")?EVisibility::Visible:EVisibility::Collapsed;})]
               +SVerticalBox::Slot().FillHeight(1)[SNew(SScrollBox)+SScrollBox::Slot()[SAssignNew(Rows,SVerticalBox)]]
               +SVerticalBox::Slot().AutoHeight().Padding(0,8,0,0)[SAssignNew(StableEditor,SVerticalBox)]
               +SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)[Button(TEXT("Your current region"),[this]{if(auto* P=Map.Get())P->AtlasCurrentRegion();})]]]]
            +SHorizontalBox::Slot().FillWidth(1)[Sheet.ToSharedRef()]]
           +SVerticalBox::Slot().AutoHeight()
           [SNew(SBorder).BorderImage(White()).BorderBackgroundColor(C(TEXT("192B24"))).Padding(FMargin(14,8))
            [SNew(SVerticalBox)
             +SVerticalBox::Slot().AutoHeight().Padding(0,0,0,6)
             [SNew(STextBlock).Font(Font(11)).ColorAndOpacity(Gold).Text_Lambda([this]{const auto* P=Map.Get();return FText::FromString(P&&P->HasMarker()?TEXT("Selected saved place: ")+P->GetMarkerName():TEXT("Save a place to return here later"));})]
             +SVerticalBox::Slot().AutoHeight()
             [SNew(SHorizontalBox)
              +SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0,0,12,0)[Text(TEXT("SAVED PLACES"),10,Gold)]
              +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,8,0)[Marker]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("Save here"),[this]{if(auto* P=Map.Get();P&&P->SaveMarker(P->MarkerName->GetText().ToString()))P->MarkerName->SetText(FText::FromString(P->MarkerStore()->NextName()));})]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("Rename"),[this]{if(auto* P=Map.Get())P->RenameMarker(P->MarkerName->GetText().ToString());})]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("Delete"),[this]{if(auto* P=Map.Get())P->DeleteMarker();})]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("‹"),[this]{if(auto* P=Map.Get())P->CycleMarker(-1);})]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("›"),[this]{if(auto* P=Map.Get())P->CycleMarker(1);})]
              +SHorizontalBox::Slot().AutoWidth()[DynamicButton([this]{return Sheet->ReturnHint();},[this]{if(auto* P=Map.Get();P&&P->ReturnToMarker())P->Close();})]]
             +SVerticalBox::Slot().AutoHeight().Padding(0,7,0,0)
             [SNew(SHorizontalBox)
              +SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
              [SNew(SBox).HeightOverride_Lambda([this]{return Sheet->IsControllerMode()?64.f:28.f;}).VAlign(VAlign_Center)
               [SNew(STextBlock).Font(Font(11)).ColorAndOpacity(Muted).AutoWrapText(true).Text_Lambda([this]{return FText::FromString(Sheet->Hint());})]]
              +SHorizontalBox::Slot().AutoWidth().Padding(12,0,5,0)[Button(TEXT("−"),[this]{Sheet->SetZoom(1./1.4);})]
              +SHorizontalBox::Slot().AutoWidth().Padding(0,0,5,0)[Button(TEXT("+"),[this]{Sheet->SetZoom(1.4);})]
              +SHorizontalBox::Slot().AutoWidth()[Button(TEXT("Fit map"),[this]{Sheet->ResetView();})]]]]]]];
        Refresh();
    }
    virtual void Tick(const FGeometry& G,double Now,float Dt) override
    {
        SCompoundWidget::Tick(G,Now,Dt);auto* M=Map.Get();if(!M)return;
        uint32 Signature=HashCombine(GetTypeHash(M->GetAtlasRegion()),GetTypeHash(M->SearchText));
        Signature=HashCombine(Signature,GetTypeHash(M->AtlasRevision));
        for(const auto& T:M->GetAtlasTargets())Signature=HashCombine(Signature,HashCombine(GetTypeHash(T.Key),GetTypeHash(T.Name)));
        if(Signature!=LastSignature){LastSignature=Signature;Refresh();}
    }
    FString ControllerSnapshot() const { return Sheet->Snapshot(); }
private:
    TWeakObjectPtr<UJapanMap> Map;TSharedPtr<SAtlasSheet> Sheet;TSharedPtr<SVerticalBox> Rows,StableEditor;uint32 LastSignature=0;
    FString AirLegend() const
    {
        const auto* M=Map.Get(); if (!M) return FString();
        const auto& Air=M->GetAtlasAirRoute(); if (Air.Stops.Num()<2 || Air.Legs.IsEmpty()) return FString();
        FString Names, Times;
        for (int32 I=0;I<Air.Stops.Num();++I)
        {
            FString Name=Air.Stops[I].Name; Name.ReplaceInline(TEXT(" air station"),TEXT(""));
            if (I) Names+=TEXT("  ↔  "); Names+=Name;
        }
        for (int32 I=0;I<Air.Legs.Num();++I) { if (I) Times+=TEXT(" · "); Times+=FString::Printf(TEXT("%.0fs"),Air.Legs[I].Seconds); }
        return TEXT("ZEPPELIN · ")+Names+TEXT("  ·  ")+Times;
    }
    void Refresh()
    {
        auto* M=Map.Get();if(!M)return;Rows->ClearChildren();StableEditor->ClearChildren();M->StableName.Reset();
        if(M->AtlasSearch.IsValid() && M->SearchText.IsEmpty() && !M->AtlasSearch->GetText().IsEmpty())M->AtlasSearch->SetText(FText::GetEmpty());
        for(const auto& T:M->GetAtlasTargets())
        {
            Rows->AddSlot().AutoHeight().Padding(0,0,0,4)
            [SNew(SButton).ButtonStyle(ButtonStyle()).IsFocusable(false).ContentPadding(FMargin(10,9))
             .OnClicked_Lambda([this,T]{if(auto* P=Map.Get()){if(T.Category==TEXT("region"))P->SelectAtlasRegion(T.Key);else if(T.bEditable)P->SelectStable(T.Key);else if(T.bTravel&&P->TeleportToZone(T.Key))P->Close();}return FReply::Handled();})
             [SNew(SVerticalBox)
              +SVerticalBox::Slot().AutoHeight()[Text(T.Name,13,T.bEditable?C(TEXT("C3CAA6")):Cream,T.Category==TEXT("region"),true)]
              +SVerticalBox::Slot().AutoHeight().Padding(0,4,0,0)[Text(T.Category==TEXT("region")?TEXT("Open region"):T.bEditable?TEXT("Stable · select to rename"):T.Category==TEXT("marker")?TEXT("Saved place"):TEXT("Travel here"),10,Muted)]]];
        }
        const FString Key=M->GetSelectedStable();if(Key.IsEmpty())return;
        auto Input=SNew(SAtlasTextBox).Font(Font(12)).Text(FText::FromString(M->GetStableName(Key))).SelectAllTextWhenFocused(true).ClearKeyboardFocusOnCommit(false)
            .OnTextCommitted_Lambda([this,Key](const FText& T,ETextCommit::Type Type){if(Type==ETextCommit::OnEnter)if(auto* P=Map.Get())P->RenameStable(Key,T.ToString());});
        Input->Map=M;M->StableName=Input;
        StableEditor->AddSlot().AutoHeight().Padding(0,0,0,7)[Text(TEXT("STABLE NAME"),10,Gold)];
        StableEditor->AddSlot().AutoHeight()[Input];
        StableEditor->AddSlot().AutoHeight().Padding(0,6,0,0)
        [SNew(SHorizontalBox)
         +SHorizontalBox::Slot().FillWidth(1).Padding(0,0,4,0)[Button(TEXT("Save name"),[this,Key,Input]{if(auto* P=Map.Get())P->RenameStable(Key,Input->GetText().ToString());})]
         +SHorizontalBox::Slot().AutoWidth()[Button(TEXT("Reset"),[this,Key]{if(auto* P=Map.Get())P->ResetStableName(Key);})]];
    }
};

TSharedRef<SWidget> MakeJapanAtlasWidget(UJapanMap* Map) { return SNew(SJapanAtlas).Map(Map); }
FString JapanAtlasControllerSnapshot(const TSharedRef<SWidget>& Widget)
{ return StaticCastSharedRef<SJapanAtlas>(Widget)->ControllerSnapshot(); }
