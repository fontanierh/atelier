#include "JapanMap.h"
#include "AtelierData.h"
#include "JapanHUD.h"
#include "SkatePark.h"
#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "LiveLibrary.h"
#include "SkateComponent.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
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
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SEditableTextBox.h"

static const FString MarkerPrefix = TEXT("marker_");

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

/** The controller buttons the map names, in the HUD's label style (AJapanHUD::CurrentControllerStyle). */
struct FMapPadLabels { const TCHAR *Travel, *Close, *Zoom, *Map, *Mark, *Return; };
static FMapPadLabels MapPadLabels(int32 Style)
{
    switch (Style)
    {
        case 1: return {TEXT("A"),TEXT("B"),TEXT("LB / RB"),TEXT("View"),TEXT("Y"),TEXT("X")};
        case 2: return {TEXT("Cross"),TEXT("Circle"),TEXT("L1 / R1"),TEXT("Touchpad"),TEXT("Triangle"),TEXT("Square")};
        case 3: return {TEXT("B"),TEXT("A"),TEXT("L / R"),TEXT("Minus"),TEXT("X"),TEXT("Y")};
        default: return {TEXT("Bottom button"),TEXT("Right button"),TEXT("Shoulder buttons"),TEXT("View / Select"),TEXT("Top button"),TEXT("Left button")};
    }
}

/** The sheet itself: the painted map fitted into the available space, the zone pins with their names, the player.
 *  Mouse: hover a pin and click it. Controller: the left stick moves a reticle that catches the nearest pin, the d-pad
 *  hops pin to pin, the right stick pans, the shoulders zoom, the bottom button travels and the right button closes. */
class SJapanMapSheet : public SLeafWidget
{
public:
    SLATE_BEGIN_ARGS(SJapanMapSheet) : _Map(nullptr), _PadStyle(0) {}
        SLATE_ARGUMENT(UJapanMap*, Map)
        SLATE_ARGUMENT(int32, PadStyle)
    SLATE_END_ARGS()
    void Construct(const FArguments& In)
    {
        Map = In._Map; PadStyle = In._PadStyle; bPad = PadStyle != 0;
        SetCursor(EMouseCursor::Default); SetClipping(EWidgetClipping::ClipToBounds);
        if (const UJapanMap* M = Map.Get()) if (const AWandererCharacter* Pawn = M->GetOwnerPawn())   // the reticle starts on the player
            Cursor = M->ToSheet(Pawn->GetActorLocation()).ClampAxes(0.,1.);
    }
    FString GetHoveredHint() const
    {
        const UJapanMap* M = Map.Get();
        if (!M || !M->GetZones().IsValidIndex(Hovered)) return FString();
        const auto& Z = M->GetZones()[Hovered];
        return Z.Name + (Z.Hint.IsEmpty() ? TEXT("") : TEXT("  —  ")) + Z.Hint + TEXT("   ·   ") + (bPad ? FString(Labels().Travel) + TEXT(" to travel") : FString(TEXT("click to travel")));
    }
    FString GetControlsHint() const
    {
        if (!bPad) return TEXT("scroll to zoom · drag to explore · click a pin to travel · M or Esc closes");
        const FMapPadLabels L = Labels();
        return FString::Printf(TEXT("left stick or d-pad: choose a pin · right stick: pan · %s: zoom · %s: travel · %s or %s: close"),L.Zoom,L.Travel,L.Close,L.Map);
    }
    FString GetMarkerHint() const
    {
        const UJapanMap* M = Map.Get();
        const FString State = M && M->HasMarker() ? M->GetMarkerName()+FString::Printf(TEXT(" · %d saved places"),M->GetMarkerKeys().Num()) : TEXT("No saved markers");
        if (!bPad) return State + TEXT(" · F5: save a new place · F9: return");
        const FMapPadLabels L = Labels();
        return State + FString::Printf(TEXT(" · %s: save here · %s: return"),L.Mark,L.Return);
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
                const bool bMarker = Zones[I].Key.StartsWith(MarkerPrefix);
                Disc(Out,Layer+2,G,P,R,bMarker ? FLinearColor(.12f,.45f,.85f,1) : bHot ? FLinearColor(.95f,.45f,.18f,1) : FLinearColor(.72f,.18f,.12f,1));
                const FString Number=bMarker ? TEXT("M") : FString::FromInt(I+1);
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
        // the controller reticle: a ring that widens round the pin it has caught
        if (bPad)
        {
            const FVector2D C = SheetOffset + Cursor * SheetSize;
            const float R = Hovered >= 0 ? 18.f : 13.f;
            Ring(Out,Layer+10,G,C,R,5.f,FLinearColor(.06f,.07f,.06f,.8f));
            Ring(Out,Layer+11,G,C,R,2.5f,FLinearColor(1,.96f,.86f,1));
            if (Hovered < 0) Disc(Out,Layer+11,G,C,2.5f,FLinearColor(1,.96f,.86f,1));
        }
        return Layer+12;
    }
    virtual void Tick(const FGeometry& G,const double Now,const float Dt) override
    {
        SLeafWidget::Tick(G,Now,Dt);
        // the controller talks to the focused widget: keep it here (a click on the frame round the sheet gives it to the game view)
        const UJapanMap* M = Map.Get();
        if (!M) return;
        if (!HasKeyboardFocus() && !M->IsEditingMarkerName()) FSlateApplication::Get().SetKeyboardFocus(AsShared(),EFocusCause::SetDirectly);
        if (!bPad || !M) return;
        Fit(G);
        const FVector2D Area = G.GetLocalSize();
        const double Speed = Area.Y*.6*Dt;
        // the right stick pans (zoomed in); the reticle stays where it is on screen
        if (const FVector2D Look = Shape(RightStick); !Look.IsZero() && Zoom > 1.)
        {
            const FVector2D Screen = SheetOffset + Cursor*SheetSize;
            Pan -= FVector2D(Look.X,-Look.Y)*Speed*1.5; Fit(G);
            Cursor = ((Screen-SheetOffset)/SheetSize).ClampAxes(0.,1.);
        }
        // the left stick moves the reticle, slower over a pin; let go and it settles on the pin it caught
        const FVector2D Move = Shape(LeftStick);
        if (!Move.IsZero()) Cursor = (Cursor + FVector2D(Move.X,-Move.Y)*Speed*(Hovered >= 0 ? .6 : 1.)/SheetSize).ClampAxes(0.,1.);
        Hovered = PickAt(G,SheetOffset + Cursor*SheetSize,30.f);
        if (Move.IsZero() && Hovered >= 0) Cursor = FMath::Lerp(Cursor,M->ToSheet(M->GetZones()[Hovered].Location),FMath::Min(1.,Dt*12.));
        // zoomed in, the view follows the reticle towards the edges
        const FVector2D Screen = SheetOffset + Cursor*SheetSize, Margin(90,90);
        Pan += ((Margin-Screen).ComponentMax(FVector2D::ZeroVector) - (Screen-(Area-Margin)).ComponentMax(FVector2D::ZeroVector))*FMath::Min(1.,Dt*10.);
        Fit(G);
    }
    virtual FReply OnKeyDown(const FGeometry& G,const FKeyEvent& E) override
    {
        const FKey K = E.GetKey();
        UJapanMap* M = Map.Get();
        if (M && (K == EKeys::F5 || K == EKeys::F9 || K == EKeys::Gamepad_FaceButton_Top || K == EKeys::Gamepad_FaceButton_Left))
        {
            bPad = K.IsGamepadKey();
            if (!E.IsRepeat())
            {
                if (K == EKeys::F5 || K == EKeys::Gamepad_FaceButton_Top) M->SetMarker();
                else if (M->ReturnToMarker()) M->Close();
            }
            return FReply::Handled();
        }
        // keyboard keys (M, Esc) and the controller's map and menu buttons go on to the game, which closes the map
        if (!M || !K.IsGamepadKey() || K == EKeys::Gamepad_Special_Left || K == EKeys::Gamepad_Special_Right) return FReply::Unhandled();
        const FVector2D Dir = K == EKeys::Gamepad_DPad_Up ? FVector2D(0,-1) : K == EKeys::Gamepad_DPad_Down ? FVector2D(0,1)
            : K == EKeys::Gamepad_DPad_Left ? FVector2D(-1,0) : K == EKeys::Gamepad_DPad_Right ? FVector2D(1,0) : FVector2D::ZeroVector;
        if (!Dir.IsZero()) { bPad = true; Hop(G,Dir); return FReply::Handled(); }
        if (E.IsRepeat()) return FReply::Handled();
        if (K == EKeys::Gamepad_FaceButton_Bottom && M->GetZones().IsValidIndex(Hovered))
        {
            const FString Key = M->GetZones()[Hovered].Key;
            if (M->TeleportToZone(Key)) M->Close();
        }
        else if (K == EKeys::Gamepad_FaceButton_Right) M->Close();
        else if (K == EKeys::Gamepad_LeftShoulder || K == EKeys::Gamepad_RightShoulder) { Fit(G); ZoomAbout(G,SheetOffset + Cursor*SheetSize,K == EKeys::Gamepad_RightShoulder ? 1.5 : 1/1.5); }
        bPad = true;
        return FReply::Handled();   // every other button is swallowed: no sword or jump behind the map
    }
    virtual FReply OnAnalogValueChanged(const FGeometry&,const FAnalogInputEvent& E) override
    {
        const FKey K = E.GetKey(); const float V = E.GetAnalogValue();
        if (K == EKeys::Gamepad_LeftX) LeftStick.X = V; else if (K == EKeys::Gamepad_LeftY) LeftStick.Y = V;
        else if (K == EKeys::Gamepad_RightX) RightStick.X = V; else if (K == EKeys::Gamepad_RightY) RightStick.Y = V;
        else return K.IsGamepadKey() ? FReply::Handled() : FReply::Unhandled();
        if (FMath::Abs(V) > .3f) bPad = true;
        return FReply::Handled();
    }
    virtual FNavigationReply OnNavigation(const FGeometry&,const FNavigationEvent&) override { return FNavigationReply::Stop(); }
    virtual FReply OnMouseMove(const FGeometry& G,const FPointerEvent& E) override
    {
        const FVector2D P=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        if(bHeld){bMoved|=FVector2D::Distance(P,DragStart)>5.;if(bMoved)Pan+=P-LastMouse;LastMouse=P;return FReply::Handled();}
        if(E.GetCursorDelta().IsNearlyZero())return FReply::Unhandled();   // a synthesized move (the sheet moved under a still mouse)
        bPad=false;Hovered=PickAt(G,P);return FReply::Unhandled();
    }
    virtual void OnMouseLeave(const FPointerEvent&) override { if(!bPad)Hovered=-1; }
    virtual FReply OnMouseWheel(const FGeometry& G,const FPointerEvent& E) override
    {
        Fit(G);ZoomAbout(G,G.AbsoluteToLocal(E.GetScreenSpacePosition()),FMath::Pow(1.25,E.GetWheelDelta()));
        return FReply::Handled();
    }
    virtual FReply OnMouseButtonDown(const FGeometry& G,const FPointerEvent& E) override
    {
        if(E.GetEffectingButton()!=EKeys::LeftMouseButton)return FReply::Unhandled();
        bPad=false;bHeld=true;bMoved=false;DragStart=LastMouse=G.AbsoluteToLocal(E.GetScreenSpacePosition());
        return FReply::Handled().CaptureMouse(AsShared());
    }
    virtual FReply OnMouseButtonUp(const FGeometry& G,const FPointerEvent& E) override
    {
        if(!bHeld)return FReply::Unhandled();bHeld=false;
        if(!bMoved){const int32 I=PickAt(G,G.AbsoluteToLocal(E.GetScreenSpacePosition()));if(UJapanMap* M=Map.Get();M && M->GetZones().IsValidIndex(I))
        {const FString Key=M->GetZones()[I].Key;if(M->TeleportToZone(Key))M->Close();}}
        return FReply::Handled().ReleaseMouseCapture();
    }
private:
    TWeakObjectPtr<UJapanMap> Map;
    mutable FVector2D SheetOffset = FVector2D::ZeroVector, SheetSize = FVector2D(1,1);
    int32 Hovered = -1;
    double Zoom=1.;mutable FVector2D Pan=FVector2D::ZeroVector;FVector2D DragStart,LastMouse;bool bHeld=false,bMoved=false;
    int32 PadStyle = 0; bool bPad = false;
    FVector2D Cursor = FVector2D(.5,.5), LeftStick = FVector2D::ZeroVector, RightStick = FVector2D::ZeroVector;   // reticle in sheet uv
    FSlateBrush DiscBrush = ShapeBrush(0.f), TabBrush = ShapeBrush(5.f);
    FMapPadLabels Labels() const { return MapPadLabels(PadStyle ? PadStyle : 4); }
    /** Dead zone, then a square curve: fine aim near the centre, speed at full tilt. */
    static FVector2D Shape(const FVector2D& Stick)
    {
        const double L = Stick.Size();
        if (L < .2) return FVector2D::ZeroVector;
        const double T = FMath::Min((L-.2)/.8,1.);
        return Stick/L*T*T;
    }
    void ZoomAbout(const FGeometry& G,const FVector2D& P,double Factor)
    {
        const double Old=Zoom;Zoom=FMath::Clamp(Zoom*Factor,1.,6.);
        const FVector2D NewSize=SheetSize*(Zoom/Old);
        Pan=P-(P-SheetOffset)*(Zoom/Old)-(G.GetLocalSize()-NewSize)*.5;
    }
    /** The d-pad: the nearest pin ahead in that direction, within about 56 degrees of it. */
    void Hop(const FGeometry& G,const FVector2D& Dir)
    {
        const UJapanMap* M = Map.Get();
        if (!M) return;
        Fit(G);
        const FVector2D From = SheetOffset + Cursor*SheetSize;
        int32 Best = -1; double BestScore = TNumericLimits<double>::Max();
        for (int32 I = 0; I < M->GetZones().Num(); ++I)
        {
            const FVector2D D = SheetOffset + M->ToSheet(M->GetZones()[I].Location)*SheetSize - From;
            const double Along = D | Dir, Across = FMath::Abs(D ^ Dir);
            if (Along < 8. || Across > Along*1.5) continue;
            if (const double Score = Along + Across*2.; Score < BestScore) { BestScore = Score; Best = I; }
        }
        if (Best >= 0) { Cursor = M->ToSheet(M->GetZones()[Best].Location); Hovered = Best; }
    }
    void Ring(FSlateWindowElementList& Out, int32 Layer, const FGeometry& G, const FVector2D& Centre, float Radius, float Thickness, const FLinearColor& Colour) const
    {
        TArray<FVector2f> Points;
        for (int32 I = 0; I <= 32; ++I) { const double A = I*UE_TWO_PI/32; Points.Add(FVector2f(Centre + FVector2D(FMath::Cos(A),FMath::Sin(A))*Radius)); }
        FSlateDrawElement::MakeLines(Out,Layer,G.ToPaintGeometry(),Points,ESlateDrawEffect::None,Colour,true,Thickness);
    }
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
    int32 PickAt(const FGeometry& G, const FVector2D& Local, float Reach = 26.f) const
    {
        const UJapanMap* M = Map.Get();
        if (!M) return -1;
        Fit(G);
        int32 Best = -1; float BestD = Reach;
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
    const FString Dir = AtelierDataPath(TEXT("map"));
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
    // The skate pier (world/regions/skatepark) is newer than the painted sheet: add its stop unless map.json already has one.
    if (!Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("skatepier"); }))
    {
        FVector World; float Yaw = 0.f;
        if (ASkatePark::ReadParkSpawn(AtelierDataPath(TEXT("skatepark/park.json")), World, Yaw))
        {
            FJapanMapZone Zone; Zone.Key = TEXT("skatepier"); Zone.Name = TEXT("Skate pier");
            Zone.Hint = TEXT("Concrete plaza on the sea: ramps, rails and ledges (B for the board)");
            Zone.Location = AJapanWorld::ToUE(World.X, World.Y, World.Z); Zone.Yaw = -Yaw;
            Zones.Add(Zone);
        }
    }
    // The hippodrome (docs/HIPPODROME.md) is newer than the painted sheet too: its stop is the grandstand's walk, by Hudson.
    if (!Zones.ContainsByPredicate([](const FJapanMapZone& Zone) { return Zone.Key == TEXT("hippodrome"); }))
    {
        FString HippodromeText; TSharedPtr<FJsonObject> Hippodrome;
        const TArray<TSharedPtr<FJsonValue>>* Origin = nullptr; const TSharedPtr<FJsonObject>* Return = nullptr; const TArray<TSharedPtr<FJsonValue>>* At = nullptr;
        if (FFileHelper::LoadFileToString(HippodromeText, *AtelierDataPath(TEXT("hippodrome/hippodrome.json")))
            && FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(HippodromeText), Hippodrome) && Hippodrome.IsValid()
            && Hippodrome->TryGetArrayField(TEXT("origin"), Origin) && Origin->Num() >= 3
            && Hippodrome->TryGetObjectField(TEXT("return"), Return) && (*Return)->TryGetArrayField(TEXT("at"), At) && At->Num() >= 2)
        {
            FJapanMapZone Zone; Zone.Key = TEXT("hippodrome"); Zone.Name = TEXT("Hidamari Hippodrome");
            Zone.Hint = TEXT("The racecourse north of the city: ask Hudson by the grandstand for a race");
            Zone.Location = AJapanWorld::ToUE((*Origin)[0]->AsNumber() + (*At)[0]->AsNumber(), (*Origin)[1]->AsNumber() + (*At)[1]->AsNumber(), (*Origin)[2]->AsNumber());
            Zone.Yaw = -float((*Return)->GetNumberField(TEXT("yaw")));
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

FJapanMarkers* UJapanMap::MarkerStore() const
{
    if (!Owner || !Owner->GetLandscape()) return nullptr;
    auto* Store = &Owner->GetLandscape()->Markers; Store->Load(); return Store;
}

const TArray<FJapanMapZone>& UJapanMap::GetZones() const
{
    const auto* Store = MarkerStore();
    Zones.RemoveAll([Store](const FJapanMapZone& Z)
    {
        return Z.Key.StartsWith(MarkerPrefix) && (!Store || !Store->All().ContainsByPredicate([&](const FJapanMarker& M) { return M.Key == Z.Key; }));
    });
    if (Store) for (const auto& M : Store->All())
    {
        auto* Z = Zones.FindByPredicate([&](const FJapanMapZone& Zone) { return Zone.Key == M.Key; });
        if (!Z) Z = &Zones.AddDefaulted_GetRef();
        Z->Key = M.Key; Z->Name = M.Name; Z->Hint = TEXT("Saved skate-line location");
        Z->Location = M.Ground.GetLocation(); Z->Yaw = M.Ground.Rotator().Yaw;
    }
    return Zones;
}

bool UJapanMap::HasMarker() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected();
}

FTransform UJapanMap::GetMarkerTransform() const
{
    const auto* Store = MarkerStore();
    return Store && Store->Selected() ? Store->Selected()->Ground : FTransform::Identity;
}

TArray<FString> UJapanMap::GetMarkerKeys() const
{
    TArray<FString> Keys;
    if (const auto* Store = MarkerStore()) for (const auto& M : Store->All()) Keys.Add(M.Key);
    return Keys;
}

FString UJapanMap::GetMarkerName() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected() ? Store->Selected()->Name : FString();
}

FString UJapanMap::GetSelectedMarkerKey() const
{
    const auto* Store = MarkerStore(); return Store && Store->Selected() ? Store->Selected()->Key : FString();
}

bool UJapanMap::MarkerResult(bool Result)
{
    if (!Result) if (const auto* Store = MarkerStore()) ULiveLibrary::Say(Store->Error.IsEmpty() ? TEXT("Choose a saved marker first.") : Store->Error);
    return Result;
}

bool UJapanMap::SelectMarker(const FString& Key)
{
    auto* Store = MarkerStore(); return Store && MarkerResult(Store->Select(Key));
}

bool UJapanMap::RenameMarker(const FString& Name)
{
    auto* Store = MarkerStore();
    if (!Store || !MarkerResult(Store->Rename(Name))) return false;
    ULiveLibrary::Say(TEXT("Marker renamed.")); return true;
}

bool UJapanMap::DeleteMarker()
{
    auto* Store = MarkerStore();
    if (!Store || !MarkerResult(Store->Delete())) return false;
    ULiveLibrary::Say(TEXT("Marker deleted.")); return true;
}

void UJapanMap::CycleMarker(int32 Direction)
{
    const auto Keys = GetMarkerKeys(); if (Keys.IsEmpty()) return;
    const int32 I = Keys.Find(GetSelectedMarkerKey());
    SelectMarker(Keys[(FMath::Max(0,I)+Direction+Keys.Num())%Keys.Num()]);
}

bool UJapanMap::IsEditingMarkerName() const
{
    return MarkerName.IsValid() && MarkerName->HasKeyboardFocus();
}

bool UJapanMap::SetMarker()
{
    const auto* Store = MarkerStore(); return Store && SaveMarker(Store->NextName());
}

bool UJapanMap::SaveMarker(const FString& Name)
{
    if (!Owner || Owner->IsCinematic() || Owner->AreControlsSuspended() || !Owner->GetLandscape() || !Owner->GetLandscape()->bLoaded) return false;
    const bool bGrounded = Owner->GetCharacterMovement()->IsMovingOnGround() || (Owner->GetSkate() && Owner->GetSkate()->IsRiding() && Owner->GetSkate()->GetMode() == ESkateMode::Ground);
    if (!bGrounded) { ULiveLibrary::Say(TEXT("Stand on solid ground to save a marker.")); return false; }
    const FVector Feet = Owner->GetActorLocation() - FVector(0,0,Owner->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SavedMarker),false,Owner);
    if (!Owner->GetWorld()->LineTraceSingleByChannel(Hit,Feet+FVector(0,0,60),Feet-FVector(0,0,120),ECC_Visibility,Params)
        || FMath::Abs(Feet.Z-Hit.ImpactPoint.Z) > 35.f || !Owner->GetCharacterMovement()->IsWalkable(Hit))
    {
        ULiveLibrary::Say(TEXT("Stand on solid ground to save a marker.")); return false;
    }
    if (!MarkerResult(MarkerStore()->Add(Name,FTransform(FRotator(0,Owner->GetActorRotation().Yaw,0),Hit.ImpactPoint)))) return false;
    ULiveLibrary::Say(GetMarkerName()+TEXT(" saved. F9 returns here.")); return true;
}

bool UJapanMap::ReturnToMarker()
{
    if (!Owner || Owner->IsCinematic() || Owner->AreControlsSuspended()) return false;
    if (!HasMarker()) { ULiveLibrary::Say(TEXT("Save a marker first (F5 or the map).")); return false; }
    const FTransform Marker = GetMarkerTransform();
    const FVector Ground = Marker.GetLocation();
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SavedMarkerReturn),false,Owner);
    const auto* Capsule = Owner->GetCapsuleComponent();
    // Travel resets crouching: test clearance for the standing capsule, even when saving or returning crouched.
    const auto* Standing = Owner->GetClass()->GetDefaultObject<AWandererCharacter>()->GetCapsuleComponent();
    const float Half = FMath::Max(Capsule->GetUnscaledCapsuleHalfHeight(),Standing->GetUnscaledCapsuleHalfHeight())*Capsule->GetShapeScale();
    const float Radius = FMath::Max(Capsule->GetUnscaledCapsuleRadius(),Standing->GetUnscaledCapsuleRadius())*Capsule->GetShapeScale();
    // A local trace keeps a marker below a bridge or roof on its original floor.
    if (!Owner->GetWorld()->LineTraceSingleByChannel(Hit,Ground+FVector(0,0,30),Ground-FVector(0,0,50),ECC_Visibility,Params)
        || FMath::Abs(Ground.Z-Hit.ImpactPoint.Z) > 20.f || !Owner->GetCharacterMovement()->IsWalkable(Hit)
        || Owner->GetWorld()->OverlapBlockingTestByProfile(Hit.ImpactPoint+FVector(0,0,Half+3.f),FQuat::Identity,
            Capsule->GetCollisionProfileName(),FCollisionShape::MakeCapsule(Radius,Half),Params))
    {
        ULiveLibrary::Say(TEXT("This marker's ground is unavailable or obstructed. Try again when it is clear.")); return false;
    }
    if (!Owner->TravelTo(Hit.ImpactPoint,Marker.Rotator().Yaw,*GetMarkerName(),30.f)) return false;
    ULiveLibrary::Say(TEXT("Returned to ")+GetMarkerName()+TEXT(".")); return true;
}

const FJapanMapZone* UJapanMap::FindZone(const FString& Key) const
{
    for (const auto& Z : GetZones()) if (Z.Key == Key) return &Z;
    return nullptr;
}

bool UJapanMap::TeleportToZone(const FString& Key)
{
    if (Key.StartsWith(MarkerPrefix)) return SelectMarker(Key) && ReturnToMarker();
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
    TSharedRef<SJapanMapSheet> Sheet = SNew(SJapanMapSheet).Map(this).PadStyle(AJapanHUD::CurrentControllerStyle());
    Widget = SNew(SBorder).BorderImage(FCoreStyle::Get().GetBrush("WhiteBrush")).BorderBackgroundColor(FLinearColor(.02f,.03f,.03f,.86f)).Padding(FMargin(30,18,30,16))
        [SNew(SVerticalBox)
            + SVerticalBox::Slot().AutoHeight().Padding(0,0,0,10)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(1)[SNew(STextBlock).Text(FText::FromString(TEXT("Yorimichi  ·  world map"))).Font(FCoreStyle::GetDefaultFontStyle("Bold",22)).ColorAndOpacity(FLinearColor(1,.96f,.86f,1))]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Bottom)[SNew(STextBlock).Text_Lambda([Sheet] { return FText::FromString(Sheet->GetControlsHint()); }).Font(FCoreStyle::GetDefaultFontStyle("Regular",13)).ColorAndOpacity(FLinearColor(.78f,.79f,.72f,1))]]
            + SVerticalBox::Slot().FillHeight(1)[Sheet]
            + SVerticalBox::Slot().AutoHeight().Padding(0,10,0,0)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().FillWidth(1).Padding(0,0,10,0)
                        [SAssignNew(MarkerName,SEditableTextBox).HintText(FText::FromString(TEXT("Name this skate-line spot")))
                            .Text(FText::FromString(MarkerStore()->NextName()))]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,10,0)
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Save here")))
                            .OnClicked_Lambda([this] { if (SaveMarker(MarkerName->GetText().ToString())) MarkerName->SetText(FText::FromString(MarkerStore()->NextName())); return FReply::Handled(); })]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,10,0)
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Rename selected")))
                            .IsEnabled_Lambda([this] { return HasMarker(); })
                            .OnClicked_Lambda([this] { RenameMarker(MarkerName->GetText().ToString()); return FReply::Handled(); })]
                    + SHorizontalBox::Slot().AutoWidth()
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Delete selected")))
                            .IsEnabled_Lambda([this] { return HasMarker(); })
                            .OnClicked_Lambda([this] { DeleteMarker(); return FReply::Handled(); })]]
            + SVerticalBox::Slot().AutoHeight().Padding(0,8,0,0)
                [SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,10,0)
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Previous")))
                            .IsEnabled_Lambda([this] { return HasMarker(); })
                            .OnClicked_Lambda([this] { CycleMarker(-1); return FReply::Handled(); })]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,10,0)
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Next")))
                            .IsEnabled_Lambda([this] { return HasMarker(); })
                            .OnClicked_Lambda([this] { CycleMarker(1); return FReply::Handled(); })]
                    + SHorizontalBox::Slot().AutoWidth().Padding(0,0,16,0)
                        [SNew(SButton).IsFocusable(false).Text(FText::FromString(TEXT("Return (F9)")))
                            .IsEnabled_Lambda([this] { return HasMarker(); })
                            .OnClicked_Lambda([this] { if (ReturnToMarker()) Close(); return FReply::Handled(); })]
                    + SHorizontalBox::Slot().FillWidth(1).VAlign(VAlign_Center)
                        [SNew(STextBlock).Text_Lambda([Sheet] { return FText::FromString(Sheet->GetMarkerHint()); })
                            .Font(FCoreStyle::GetDefaultFontStyle("Regular",14)).ColorAndOpacity(FLinearColor(.78f,.79f,.72f,1))]]
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
    Widget.Reset(); MarkerName.Reset();
    if (Owner) Owner->SetMenuOpen(false);
}
