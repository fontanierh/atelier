#include "JapanCharacterSelect.h"
#include "AtelierData.h"
#include "JapanGameMode.h"
#include "JapanHUD.h"
#include "JapanNetwork.h"
#include "JapanPreferences.h"
#include "LiveLibrary.h"
#include "PlayableCharacter.h"
#include "WandererCharacter.h"
#include "Brushes/SlateColorBrush.h"
#include "Brushes/SlateRoundedBoxBrush.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/IConsoleManager.h"
#include "ImageUtils.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Misc/App.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Rendering/DrawElements.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateTypes.h"
#include "TimerManager.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/SLeafWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace
{
    FLinearColor HexColor(const TCHAR* InHex, float Alpha = 1.f)
    {
        FLinearColor Color = FLinearColor::FromSRGBColor(FColor::FromHex(InHex));
        Color.A = Alpha;
        return Color;
    }

    const FLinearColor BackdropTint = HexColor(TEXT("07120e"), 0.62f);
    const FLinearColor BoardOuterFill = HexColor(TEXT("0b1c15"), 0.96f);
    const FLinearColor BoardInnerFill = HexColor(TEXT("0e221a"), 0.98f);
    const FLinearColor PlaqueFill = HexColor(TEXT("0e221a"), 1.f);
    const FLinearColor PlaqueSelectedFill = HexColor(TEXT("132b21"), 1.f);
    const FLinearColor Brass = HexColor(TEXT("c9a05a"), 1.f);
    const FLinearColor BrassSoft = HexColor(TEXT("c9a05a"), 0.48f);
    const FLinearColor BrassFaint = HexColor(TEXT("c9a05a"), 0.25f);
    const FLinearColor GoldButtonFill = HexColor(TEXT("d9ab4e"), 1.f);
    const FLinearColor GoldButtonBorder = HexColor(TEXT("ffe299"), 1.f);
    const FLinearColor DarkButtonFill = HexColor(TEXT("0a1812"), 0.95f);
    const FLinearColor Cream = HexColor(TEXT("fff6e5"), 1.f);
    const FLinearColor SageCream = HexColor(TEXT("d0ddd4"), 1.f);
    const FLinearColor InkDark = HexColor(TEXT("19140a"), 1.f);

    TMap<FString, TSharedPtr<FSlateBrush>>& BrushCache()
    {
        static TMap<FString, TSharedPtr<FSlateBrush>> Cache;
        return Cache;
    }

    const FSlateBrush* SolidBrush(const FLinearColor& Fill)
    {
        const FString Key = FString::Printf(TEXT("solid:%s"), *Fill.ToString());
        if (const TSharedPtr<FSlateBrush>* Found = BrushCache().Find(Key)) return Found->Get();
        TSharedPtr<FSlateBrush> Brush = MakeShared<FSlateColorBrush>(Fill);
        BrushCache().Add(Key, Brush);
        return Brush.Get();
    }

    const FSlateBrush* RoundedBrush(const FLinearColor& Fill, float Radius, const FLinearColor& Outline = FLinearColor::Transparent, float OutlineWidth = 0.f)
    {
        const float Clamped = FMath::Min(Radius, 15.f);
        const FVector4 Radii(Clamped, Clamped, Clamped, Clamped);
        const FString Key = FString::Printf(TEXT("round:%s:%.1f:%s:%.1f"), *Fill.ToString(), Clamped, *Outline.ToString(), OutlineWidth);
        if (const TSharedPtr<FSlateBrush>* Found = BrushCache().Find(Key)) return Found->Get();
        TSharedPtr<FSlateBrush> Brush = MakeShared<FSlateRoundedBoxBrush>(FSlateColor(Fill), Radii, FSlateColor(Outline), OutlineWidth);
        BrushCache().Add(Key, Brush);
        return Brush.Get();
    }

    const FButtonStyle& CardButtonStyle()
    {
        static FButtonStyle Style = []
        {
            FButtonStyle S = FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("Button");
            const FSlateColorBrush Empty(FLinearColor::Transparent);
            S.SetNormal(Empty).SetHovered(Empty).SetPressed(Empty).SetDisabled(Empty);
            S.SetNormalPadding(FMargin(0)).SetPressedPadding(FMargin(0));
            return S;
        }();
        return Style;
    }

    class SVerticalGradientOverlay : public SLeafWidget
    {
    public:
        SLATE_BEGIN_ARGS(SVerticalGradientOverlay) : _TopColor(FLinearColor::Transparent), _BottomColor(FLinearColor::Black) {}
            SLATE_ARGUMENT(FLinearColor, TopColor)
            SLATE_ARGUMENT(FLinearColor, BottomColor)
        SLATE_END_ARGS()

        void Construct(const FArguments& InArgs)
        {
            TopColor = InArgs._TopColor;
            BottomColor = InArgs._BottomColor;
            SetCanTick(false);
        }

        virtual FVector2D ComputeDesiredSize(float) const override { return FVector2D(16.f, 16.f); }

        virtual int32 OnPaint(const FPaintArgs&, const FGeometry& AllottedGeometry, const FSlateRect&, FSlateWindowElementList& OutDrawElements,
            int32 LayerId, const FWidgetStyle& InWidgetStyle, bool) const override
        {
            const FVector2D Size = AllottedGeometry.GetLocalSize();
            const float Alpha = InWidgetStyle.GetColorAndOpacityTint().A;
            FLinearColor C0 = TopColor; C0.A *= Alpha;
            FLinearColor C1 = BottomColor; C1.A *= Alpha;
            TArray<FSlateGradientStop> Stops;
            Stops.Add(FSlateGradientStop(FVector2D::ZeroVector, C0));
            Stops.Add(FSlateGradientStop(FVector2D(0.f, Size.Y), C1));
            FSlateDrawElement::MakeGradient(OutDrawElements, LayerId, AllottedGeometry.ToPaintGeometry(), Stops, Orient_Horizontal, ESlateDrawEffect::None);
            return LayerId;
        }

    private:
        FLinearColor TopColor;
        FLinearColor BottomColor;
    };

    void ApplyCharacterTheme(FJapanCharacterSelect::FCardInfo& Card)
    {
        if (Card.Id == TEXT("cairo"))
        {
            Card.Badge = TEXT("DEFAULT");
            Card.Tagline = TEXT("Knows every shortcut.");
            Card.Accent = HexColor(TEXT("e2b44c"));
            Card.AccentBorder = HexColor(TEXT("ffe08c"));
            Card.BadgeFill = HexColor(TEXT("4c3914"), 0.96f);
            Card.BadgeText = HexColor(TEXT("ffebb0"));
        }
        else if (Card.Id == TEXT("modori"))
        {
            Card.Badge = TEXT("RIVAL");
            Card.Tagline = TEXT("Came back from the woods.");
            Card.Accent = HexColor(TEXT("89b4d4"));
            Card.AccentBorder = HexColor(TEXT("b6dcfa"));
            Card.BadgeFill = HexColor(TEXT("1d3242"), 0.96f);
            Card.BadgeText = HexColor(TEXT("dcf0ff"));
        }
        else if (Card.Id == TEXT("nox"))
        {
            Card.Badge = TEXT("NIGHT RIDER");
            Card.Tagline = TEXT("Up all night.");
            Card.Accent = HexColor(TEXT("9a7ed6"));
            Card.AccentBorder = HexColor(TEXT("c7b0ff"));
            Card.BadgeFill = HexColor(TEXT("2a2040"), 0.96f);
            Card.BadgeText = HexColor(TEXT("eadfff"));
        }
        else if (Card.Id == TEXT("paul"))
        {
            Card.Badge = TEXT("CHALLENGER");
            Card.Tagline = TEXT("New in town.");
            Card.Accent = HexColor(TEXT("6db37e"));
            Card.AccentBorder = HexColor(TEXT("9fe0ae"));
            Card.BadgeFill = HexColor(TEXT("1a3724"), 0.96f);
            Card.BadgeText = HexColor(TEXT("dcffe5"));
        }
        else
        {
            Card.Badge = Card.bDefault ? TEXT("DEFAULT") : TEXT("WANDERER");
            Card.Tagline = TEXT("Ready for the road.");
            Card.Accent = Brass;
            Card.AccentBorder = GoldButtonBorder;
            Card.BadgeFill = HexColor(TEXT("2a2415"), 0.96f);
            Card.BadgeText = Cream;
        }
    }

    class SJapanCharacterSelectWidget;

    struct FSelectSessionState
    {
        TWeakObjectPtr<AWandererCharacter> Owner;
        TWeakObjectPtr<const UWorld> OpenedWorld;
        TSharedPtr<SJapanCharacterSelectWidget> Widget;
        TArray<FJapanCharacterSelect::FCardInfo> Roster;
        int32 SelectedIndex = 0;
        bool bStartup = false;
        bool bStartupShownInProcess = false;
    };

    FSelectSessionState& State()
    {
        static FSelectSessionState S;
        return S;
    }

    class SJapanCharacterSelectWidget : public SCompoundWidget
    {
    public:
        SLATE_BEGIN_ARGS(SJapanCharacterSelectWidget) {}
        SLATE_END_ARGS()

        void Construct(const FArguments&)
        {
            bCanSupportFocus = true;
            PadStyle = AJapanHUD::CurrentControllerStyle();
            bPad = PadStyle != 0;

            TSharedRef<SHorizontalBox> CardRow = SNew(SHorizontalBox);
            const TArray<FJapanCharacterSelect::FCardInfo>& Roster = State().Roster;
            for (int32 Index = 0; Index < Roster.Num(); ++Index)
            {
                CardRow->AddSlot()
                .AutoWidth()
                .Padding(Index == 0 ? 0.f : 18.f, 0.f, 0.f, 0.f)
                [
                    BuildCard(Index, Roster[Index])
                ];
            }

            FSlateFontInfo EyebrowFont = FCoreStyle::GetDefaultFontStyle("Bold", 12);
            EyebrowFont.LetterSpacing = 220;
            FSlateFontInfo TitleFont = FCoreStyle::GetDefaultFontStyle("Bold", 32);
            FSlateFontInfo LegendFont = FCoreStyle::GetDefaultFontStyle("Regular", 13);

            TSharedRef<SVerticalBox> Layout = SNew(SVerticalBox)
                // Header: ornamental brass rule + YORIMICHI + Choose Your Wanderer
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 0.f, 0.f, 6.f)
                [
                    SNew(SHorizontalBox)
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0.f, 0.f, 14.f, 0.f)
                    [
                        SNew(SBox).WidthOverride(96.f).HeightOverride(1.f)
                        [SNew(SImage).Image(SolidBrush(BrassSoft))]
                    ]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                    [
                        SNew(STextBlock)
                        .Text(FText::FromString(TEXT("◆   Y O R I M I C H I   ◆")))
                        .Font(EyebrowFont)
                        .ColorAndOpacity(HexColor(TEXT("e6c883")))
                        .ShadowOffset(FVector2D(0.f, 1.f))
                        .ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.75f))
                    ]
                    + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(14.f, 0.f, 0.f, 0.f)
                    [
                        SNew(SBox).WidthOverride(96.f).HeightOverride(1.f)
                        [SNew(SImage).Image(SolidBrush(BrassSoft))]
                    ]
                ]
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 0.f, 0.f, 20.f)
                [
                    SNew(STextBlock)
                    .Text(FText::FromString(TEXT("Choose Your Wanderer")))
                    .Font(TitleFont)
                    .ColorAndOpacity(Cream)
                    .ShadowOffset(FVector2D(0.f, 2.f))
                    .ShadowColorAndOpacity(FLinearColor(0.f, 0.f, 0.f, 0.85f))
                ]
                // Main architectural dark forest & brushed-brass selection board
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
                [
                    SNew(SOverlay)
                    + SOverlay::Slot().Padding(FMargin(0.f, 6.f, 0.f, -6.f))
                    [
                        SNew(SBorder)
                        .BorderImage(RoundedBrush(FLinearColor(0.f, 0.f, 0.f, 0.55f), 15.f))
                    ]
                    + SOverlay::Slot()
                    [
                        SNew(SBorder)
                        .BorderImage(RoundedBrush(BoardOuterFill, 14.f, Brass, 1.5f))
                        .Padding(5.f)
                        [
                            SNew(SBorder)
                            .BorderImage(RoundedBrush(BoardInnerFill, 11.f, BrassFaint, 1.f))
                            .Padding(FMargin(24.f, 24.f, 24.f, 24.f))
                            [
                                CardRow
                            ]
                        ]
                    ]
                ]
                // Bottom control legend pill bar
                + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 18.f, 0.f, 0.f)
                [
                    SNew(SBorder)
                    .BorderImage(RoundedBrush(BoardOuterFill, 10.f, BrassSoft, 1.f))
                    .Padding(FMargin(28.f, 10.f))
                    [
                        SNew(STextBlock)
                        .Font(LegendFont)
                        .ColorAndOpacity(HexColor(TEXT("f3e8d2")))
                        .Text_Lambda([this] { return FText::FromString(LegendText()); })
                    ]
                ];

            ChildSlot
            [
                SNew(SOverlay)
                + SOverlay::Slot()
                [
                    SNew(SBorder).BorderImage(SolidBrush(BackdropTint))
                ]
                + SOverlay::Slot().VAlign(VAlign_Top)
                [
                    SNew(SBox).HeightOverride(220.f)
                    [SNew(SVerticalGradientOverlay).TopColor(HexColor(TEXT("040b08"), 0.78f)).BottomColor(FLinearColor::Transparent)]
                ]
                + SOverlay::Slot().VAlign(VAlign_Bottom)
                [
                    SNew(SBox).HeightOverride(220.f)
                    [SNew(SVerticalGradientOverlay).TopColor(FLinearColor::Transparent).BottomColor(HexColor(TEXT("040b08"), 0.82f))]
                ]
                + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Center).Padding(32.f, 24.f)
                [
                    SNew(SScaleBox)
                    .Stretch(EStretch::ScaleToFit)
                    .StretchDirection(EStretchDirection::DownOnly)
                    [
                        Layout
                    ]
                ]
            ];
        }

        virtual bool SupportsKeyboardFocus() const override { return true; }

        virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override
        {
            SCompoundWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
            if (AnalogCooldown > 0.f) AnalogCooldown = FMath::Max(0.f, AnalogCooldown - InDeltaTime);
            const int32 CurrentPad = AJapanHUD::CurrentControllerStyle();
            if (CurrentPad != PadStyle) { PadStyle = CurrentPad; bPad = PadStyle != 0; }
            if (FSlateApplication::IsInitialized() && FSlateApplication::Get().GetActiveTopLevelWindow().IsValid())
            {
                const TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetUserFocusedWidget(0);
                if (!Focused || (!HasUserFocus(0).IsSet() && !HasUserFocusedDescendants(0)))
                {
                    FSlateApplication::Get().SetUserFocus(0, SharedThis(this), EFocusCause::Navigation);
                }
            }
        }

        virtual FReply OnPreviewKeyDown(const FGeometry&, const FKeyEvent& E) override
        {
            const FKey K = E.GetKey();
            bPad = K.IsGamepadKey();
            if (K == EKeys::Left || K == EKeys::A || K == EKeys::Gamepad_DPad_Left || K == EKeys::Gamepad_LeftShoulder)
            {
                FJapanCharacterSelect::StepSelection(-1);
                return FReply::Handled();
            }
            if (K == EKeys::Right || K == EKeys::D || K == EKeys::Gamepad_DPad_Right || K == EKeys::Gamepad_RightShoulder || K == EKeys::Tab)
            {
                FJapanCharacterSelect::StepSelection(E.IsShiftDown() && K == EKeys::Tab ? -1 : 1);
                return FReply::Handled();
            }
            if (K == EKeys::Enter || K == EKeys::Virtual_Gamepad_Accept.GetVirtualKey() || K == EKeys::SpaceBar || K == EKeys::Gamepad_FaceButton_Bottom || K == EKeys::Gamepad_Special_Right)
            {
                if (!E.IsRepeat()) ConfirmIndex(State().SelectedIndex);
                return FReply::Handled();
            }
            if (K == EKeys::Escape || K == EKeys::Gamepad_FaceButton_Right)
            {
                if (!E.IsRepeat())
                {
                    if (State().bStartup) ConfirmIndex(State().SelectedIndex);
                    else FJapanCharacterSelect::Close();
                }
                return FReply::Handled();
            }
            const FKey NumberKeys[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
            const FKey NumpadKeys[] = { EKeys::NumPadOne, EKeys::NumPadTwo, EKeys::NumPadThree, EKeys::NumPadFour, EKeys::NumPadFive, EKeys::NumPadSix };
            for (int32 I = 0; I < UE_ARRAY_COUNT(NumberKeys); ++I)
            {
                if ((K == NumberKeys[I] || K == NumpadKeys[I]) && State().Roster.IsValidIndex(I))
                {
                    State().SelectedIndex = I;
                    if (!E.IsRepeat()) ConfirmIndex(I);
                    return FReply::Handled();
                }
            }
            return FReply::Handled();
        }

        virtual FReply OnKeyDown(const FGeometry&, const FKeyEvent&) override { return FReply::Handled(); }
        virtual FReply OnKeyUp(const FGeometry&, const FKeyEvent&) override { return FReply::Handled(); }

        virtual FReply OnAnalogValueChanged(const FGeometry&, const FAnalogInputEvent& E) override
        {
            if (!E.GetKey().IsGamepadKey()) return FReply::Unhandled();
            if (E.GetKey() == EKeys::Gamepad_LeftX)
            {
                const float V = E.GetAnalogValue();
                if (FMath::Abs(V) < 0.3f) { bStickLatched = false; }
                else if (FMath::Abs(V) > 0.55f && (!bStickLatched || AnalogCooldown <= 0.f))
                {
                    bPad = true;
                    bStickLatched = true;
                    AnalogCooldown = 0.26f;
                    FJapanCharacterSelect::StepSelection(V > 0.f ? 1 : -1);
                }
            }
            return FReply::Handled();
        }

    private:
        int32 PadStyle = 0;
        bool bPad = false;
        bool bStickLatched = false;
        float AnalogCooldown = 0.f;

        void ConfirmIndex(int32 Index)
        {
            if (!State().Roster.IsValidIndex(Index)) return;
            const FString Name = State().Roster[Index].Name;
            AWandererCharacter* Pawn = State().Owner.Get();
            if (Pawn && Pawn->GetWorld())
            {
                Pawn->GetWorldTimerManager().SetTimerForNextTick(FTimerDelegate::CreateLambda([Name]
                {
                    FJapanCharacterSelect::Choose(Name);
                }));
            }
            else
            {
                FJapanCharacterSelect::Choose(Name);
            }
        }

        TSharedRef<SWidget> BuildCard(int32 Index, const FJapanCharacterSelect::FCardInfo& Card)
        {
            const FSlateBrush* Portrait = FJapanCharacterSelect::PortraitBrush(Card.Id);
            FSlateFontInfo BadgeFont = FCoreStyle::GetDefaultFontStyle("Bold", 9);
            BadgeFont.LetterSpacing = 120;
            FSlateFontInfo NameFont = FCoreStyle::GetDefaultFontStyle("Bold", 21);
            FSlateFontInfo TaglineFont = FCoreStyle::GetDefaultFontStyle("Regular", 12);
            FSlateFontInfo OrnamentFont = FCoreStyle::GetDefaultFontStyle("Regular", 8);
            FSlateFontInfo ActionFont = FCoreStyle::GetDefaultFontStyle("Bold", 12);

            TSharedRef<SWidget> PortraitView = Portrait
                ? StaticCastSharedRef<SWidget>(SNew(SScaleBox).Stretch(EStretch::ScaleToFill)[SNew(SImage).Image(Portrait)])
                : StaticCastSharedRef<SWidget>(SNew(SBorder).BorderImage(SolidBrush(Card.BadgeFill)));

            TSharedRef<SWidget> CardBody = SNew(SBox)
                .WidthOverride(292.f)
                [
                    SNew(SOverlay)
                    // Main card container (with top margin for the overlapping badge)
                    + SOverlay::Slot().Padding(0.f, 11.f, 0.f, 0.f)
                    [
                        SNew(SBorder)
                        .Padding(2.f)
                        .BorderImage_Lambda([Index, Card]
                        {
                            const bool bSel = State().SelectedIndex == Index;
                            return RoundedBrush(
                                bSel ? PlaqueSelectedFill : PlaqueFill,
                                12.f,
                                bSel ? Card.AccentBorder : FLinearColor(Card.Accent.R, Card.Accent.G, Card.Accent.B, 0.48f),
                                bSel ? 2.5f : 1.2f);
                        })
                        [
                            SNew(SVerticalBox)
                            // Portrait area
                            + SVerticalBox::Slot().AutoHeight()
                            [
                                SNew(SBox).HeightOverride(316.f).Clipping(EWidgetClipping::ClipToBounds)
                                [
                                    SNew(SOverlay)
                                    + SOverlay::Slot()[PortraitView]
                                    // Subtle top and bottom vignette inside the portrait frame
                                    + SOverlay::Slot().VAlign(VAlign_Top)
                                    [
                                        SNew(SBox).HeightOverride(48.f)
                                        [SNew(SVerticalGradientOverlay).TopColor(FLinearColor(0.f, 0.f, 0.f, 0.42f)).BottomColor(FLinearColor::Transparent)]
                                    ]
                                    + SOverlay::Slot().VAlign(VAlign_Bottom)
                                    [
                                        SNew(SBox).HeightOverride(64.f)
                                        [SNew(SVerticalGradientOverlay).TopColor(FLinearColor::Transparent).BottomColor(PlaqueFill)]
                                    ]
                                ]
                            ]
                            // Accent rule between portrait and engraved plaque
                            + SVerticalBox::Slot().AutoHeight()
                            [
                                SNew(SBox).HeightOverride(1.5f)
                                [
                                    SNew(SImage).Image_Lambda([Index, Card]
                                    {
                                        const bool bSel = State().SelectedIndex == Index;
                                        return SolidBrush(bSel ? Card.AccentBorder : FLinearColor(Card.Accent.R, Card.Accent.G, Card.Accent.B, 0.45f));
                                    })
                                ]
                            ]
                            // Engraved character plaque: Name + Short 3-5 word line + diamond rule + Play/Select pill
                            + SVerticalBox::Slot().AutoHeight()
                            [
                                SNew(SBorder)
                                .Padding(FMargin(18.f, 14.f, 18.f, 16.f))
                                .BorderImage_Lambda([Index]
                                {
                                    return SolidBrush(State().SelectedIndex == Index ? PlaqueSelectedFill : PlaqueFill);
                                })
                                [
                                    SNew(SVerticalBox)
                                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center)
                                    [
                                        SNew(STextBlock)
                                        .Text(FText::FromString(Card.Name))
                                        .Font(NameFont)
                                        .ColorAndOpacity(Cream)
                                    ]
                                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 4.f, 0.f, 10.f)
                                    [
                                        SNew(STextBlock)
                                        .Text(FText::FromString(Card.Tagline))
                                        .Font(TaglineFont)
                                        .ColorAndOpacity(SageCream)
                                    ]
                                    + SVerticalBox::Slot().AutoHeight().HAlign(HAlign_Center).Padding(0.f, 0.f, 0.f, 12.f)
                                    [
                                        SNew(SHorizontalBox)
                                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(0.f, 0.f, 8.f, 0.f)
                                        [SNew(SBox).WidthOverride(44.f).HeightOverride(1.f)[SNew(SImage).Image(SolidBrush(BrassFaint))]]
                                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center)
                                        [SNew(STextBlock).Text(FText::FromString(TEXT("◆"))).Font(OrnamentFont).ColorAndOpacity(BrassSoft)]
                                        + SHorizontalBox::Slot().AutoWidth().VAlign(VAlign_Center).Padding(8.f, 0.f, 0.f, 0.f)
                                        [SNew(SBox).WidthOverride(44.f).HeightOverride(1.f)[SNew(SImage).Image(SolidBrush(BrassFaint))]]
                                    ]
                                    + SVerticalBox::Slot().AutoHeight()
                                    [
                                        SNew(SBorder)
                                        .HAlign(HAlign_Center)
                                        .VAlign(VAlign_Center)
                                        .Padding(FMargin(16.f, 9.f))
                                        .BorderImage_Lambda([Index, Card]
                                        {
                                            const bool bSel = State().SelectedIndex == Index;
                                            return bSel
                                                ? RoundedBrush(GoldButtonFill, 7.f, GoldButtonBorder, 1.5f)
                                                : RoundedBrush(DarkButtonFill, 7.f, FLinearColor(Card.Accent.R, Card.Accent.G, Card.Accent.B, 0.55f), 1.f);
                                        })
                                        [
                                            SNew(STextBlock)
                                            .Font(ActionFont)
                                            .Text_Lambda([Index]
                                            {
                                                return FText::FromString(State().SelectedIndex == Index ? TEXT("Selected  ·  Play") : TEXT("Select"));
                                            })
                                            .ColorAndOpacity_Lambda([Index]
                                            {
                                                return FSlateColor(State().SelectedIndex == Index ? InkDark : Cream);
                                            })
                                        ]
                                    ]
                                ]
                            ]
                        ]
                    ]
                    // Top overlapping role pill badge (DEFAULT, RIVAL, NIGHT RIDER, CHALLENGER)
                    + SOverlay::Slot().HAlign(HAlign_Center).VAlign(VAlign_Top)
                    [
                        SNew(SBorder)
                        .Padding(FMargin(16.f, 4.f))
                        .BorderImage_Lambda([Index, Card]
                        {
                            const bool bSel = State().SelectedIndex == Index;
                            return RoundedBrush(Card.BadgeFill, 8.f, bSel ? Card.AccentBorder : Card.Accent, bSel ? 1.6f : 1.1f);
                        })
                        [
                            SNew(STextBlock)
                            .Text(FText::FromString(Card.Badge))
                            .Font(BadgeFont)
                            .ColorAndOpacity(Card.BadgeText)
                        ]
                    ]
                ];

            return SNew(SButton)
                .ButtonStyle(&CardButtonStyle())
                .ContentPadding(FMargin(0.f))
                .IsFocusable(false)
                .Cursor(EMouseCursor::Hand)
                .OnHovered_Lambda([this, Index]
                {
                    bPad = false;
                    State().SelectedIndex = Index;
                })
                .OnClicked_Lambda([this, Index]
                {
                    bPad = false;
                    State().SelectedIndex = Index;
                    ConfirmIndex(Index);
                    return FReply::Handled();
                })
                [
                    CardBody
                ];
        }

        FString LegendText() const
        {
            if (!bPad)
            {
                return State().bStartup
                    ? TEXT("◄ / ►   Left / Right or Mouse: Choose      ·      Enter / Space / A: Play      ·      1 – 4: Quick Pick")
                    : TEXT("◄ / ►   Left / Right or Mouse: Choose      ·      Enter / Space / A: Play      ·      1 – 4: Quick Pick      ·      Esc: Cancel");
            }
            const TCHAR* Accept = TEXT("Bottom button");
            const TCHAR* Cancel = TEXT("Right button");
            switch (PadStyle)
            {
                case 1: Accept = TEXT("A"); Cancel = TEXT("B"); break;
                case 2: Accept = TEXT("Cross"); Cancel = TEXT("Circle"); break;
                case 3: Accept = TEXT("B"); Cancel = TEXT("A"); break;
                default: break;
            }
            return State().bStartup
                ? FString::Printf(TEXT("◄ / ►   D-Pad or Left Stick: Choose      ·      %s: Play"), Accept)
                : FString::Printf(TEXT("◄ / ►   D-Pad or Left Stick: Choose      ·      %s: Play      ·      %s: Cancel"), Accept, Cancel);
        }
    };
}

const FSlateBrush* FJapanCharacterSelect::PortraitBrush(const FString& CharacterId)
{
    if (CharacterId.IsEmpty()) return nullptr;
    const FString Key = TEXT("portrait:") + CharacterId;
    if (const TSharedPtr<FSlateBrush>* Cached = BrushCache().Find(Key)) return Cached->Get();
    const FString Path = AtelierDataPath(CharacterId / TEXT("portrait.png"));
    UTexture2D* Texture = IFileManager::Get().FileExists(*Path) ? FImageUtils::ImportFileAsTexture2D(Path) : nullptr;
    TSharedPtr<FSlateBrush> Brush;
    if (Texture)
    {
        Texture->AddToRoot();
        Brush = MakeShared<FSlateBrush>();
        Brush->SetResourceObject(Texture);
        Brush->ImageSize = FVector2D(Texture->GetSizeX(), Texture->GetSizeY());
        Brush->DrawAs = ESlateBrushDrawType::Image;
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("CharacterSelect: missing portrait %s"), *Path);
    }
    BrushCache().Add(Key, Brush);
    return Brush.Get();
}

TArray<FJapanCharacterSelect::FCardInfo> FJapanCharacterSelect::Cards()
{
    TArray<const FPlayableCharacter*> Ordered;
    const FPlayableCharacter& Default = FPlayableCharacter::Default();
    if (!Default.Name.IsEmpty() && Default.Built()) Ordered.Add(&Default);
    for (const FPlayableCharacter& Character : FPlayableCharacter::All())
    {
        if (!Character.bDefault && Character.Built()) Ordered.Add(&Character);
    }
    TArray<FCardInfo> Result;
    for (const FPlayableCharacter* Character : Ordered)
    {
        FCardInfo Card;
        Card.Id = Character->Id;
        Card.Name = Character->Name;
        Card.bDefault = Character->bDefault;
        Card.bBuilt = Character->Built();
        Card.bPortraitLoaded = PortraitBrush(Character->Id) != nullptr;
        ApplyCharacterTheme(Card);
        Result.Add(MoveTemp(Card));
    }
    return Result;
}

bool FJapanCharacterSelect::ShouldOpenAtStartup(const UWorld* World)
{
    if (!World || JapanNetwork::IsOnline(World) || World->GetNetMode() != NM_Standalone) return false;
    if (State().bStartupShownInProcess) return false;
    const TCHAR* Cmd = FCommandLine::Get();
    if (FApp::IsUnattended() || FParse::Param(Cmd, TEXT("unattended")) || FParse::Param(Cmd, TEXT("nocharacterselect"))) return false;
    if (AJapanGameMode::IsScriptedSession()) return false;
    if (FParse::Param(Cmd, TEXT("nullrhi")) || FParse::Param(Cmd, TEXT("RenderOffscreen")) || IsRunningCommandlet()) return false;
    if (FCString::Stristr(Cmd, TEXT("-seconds=")) || FCString::Stristr(Cmd, TEXT("-camera="))) return false;
    if (!FPlayableCharacter::Requested().IsEmpty()) return false;
    const bool bExplicit = FParse::Param(Cmd, TEXT("characterselect"));
#if WITH_EDITOR
    return bExplicit;
#else
    return true;
#endif
}

bool FJapanCharacterSelect::HasOpenedForWorld(const UWorld* World)
{
    return State().bStartupShownInProcess || (World && State().OpenedWorld.Get() == World);
}

bool FJapanCharacterSelect::Open(AWandererCharacter* Pawn, bool bStartup)
{
    if (!Pawn || Pawn->IsNpc() || !Cast<APlayerController>(Pawn->GetController()))
        Pawn = Cast<AWandererCharacter>(ULiveLibrary::Player());
    if (!Pawn || !Pawn->GetWorld() || JapanNetwork::IsOnline(Pawn->GetWorld()) || !GEngine || !GEngine->GameViewport) return false;
    TArray<FCardInfo> Roster = Cards();
    if (Roster.Num() == 0) return false;
    Close();
    if (UJapanPreferences* Prefs = Pawn->GetPreferences()) Prefs->CloseMenu();
    FSelectSessionState& S = State();
    S.Owner = Pawn;
    S.OpenedWorld = Pawn->GetWorld();
    S.Roster = MoveTemp(Roster);
    S.bStartup = bStartup;
    if (bStartup) S.bStartupShownInProcess = true;
    const FString CurrentName = FPlayableCharacter::NameOf(Pawn);
    S.SelectedIndex = 0;
    for (int32 I = 0; I < S.Roster.Num(); ++I)
    {
        if (S.Roster[I].Name == CurrentName) { S.SelectedIndex = I; break; }
    }
    S.Widget = SNew(SJapanCharacterSelectWidget);
    GEngine->GameViewport->AddViewportWidgetContent(S.Widget.ToSharedRef(), 25);
    Pawn->SetMenuOpen(true);
    GEngine->GameViewport->SetMouseCaptureMode(EMouseCaptureMode::NoCapture);
    if (FSlateApplication::IsInitialized())
    {
        FSlateApplication::Get().SetUserFocus(0, S.Widget, EFocusCause::SetDirectly);
    }
    UE_LOG(LogTemp, Display, TEXT("CHARACTER SELECT opened startup=%d characters=%d selected=%s"),
        int32(bStartup), S.Roster.Num(), *S.Roster[S.SelectedIndex].Name);
    return true;
}

void FJapanCharacterSelect::Close(const AWandererCharacter* OwnerPawn)
{
    FSelectSessionState& S = State();
    if (OwnerPawn && S.Owner.Get() != OwnerPawn) return;
    if (S.Widget.IsValid() && GEngine && GEngine->GameViewport)
    {
        GEngine->GameViewport->RemoveViewportWidgetContent(S.Widget.ToSharedRef());
    }
    S.Widget.Reset();
    if (AWandererCharacter* Pawn = S.Owner.Get())
    {
        Pawn->SetMenuOpen(false);
    }
    S.Owner.Reset();
}

bool FJapanCharacterSelect::IsOpen()
{
    return State().Widget.IsValid();
}

bool FJapanCharacterSelect::StepSelection(int32 Delta)
{
    FSelectSessionState& S = State();
    if (!S.Widget.IsValid() || S.Roster.Num() == 0) return false;
    const int32 Count = S.Roster.Num();
    S.SelectedIndex = ((S.SelectedIndex + Delta) % Count + Count) % Count;
    return true;
}

bool FJapanCharacterSelect::Highlight(const FString& NameOrId)
{
    FSelectSessionState& S = State();
    if (!S.Widget.IsValid() || NameOrId.IsEmpty()) return false;
    for (int32 I = 0; I < S.Roster.Num(); ++I)
    {
        if (S.Roster[I].Name.Equals(NameOrId, ESearchCase::IgnoreCase) || S.Roster[I].Id.Equals(NameOrId, ESearchCase::IgnoreCase))
        {
            S.SelectedIndex = I;
            return true;
        }
    }
    return false;
}

AWandererCharacter* FJapanCharacterSelect::Choose(const FString& NameOrId)
{
    FSelectSessionState& S = State();
    if (!NameOrId.IsEmpty() && !Highlight(NameOrId) && !FPlayableCharacter::Find(NameOrId))
    {
        UE_LOG(LogTemp, Warning, TEXT("CHARACTER SELECT unknown character: %s"), *NameOrId);
        return S.Owner.IsValid() ? S.Owner.Get() : Cast<AWandererCharacter>(ULiveLibrary::Player());
    }
    AWandererCharacter* Pawn = S.Owner.Get();
    if (!Pawn || Pawn->IsNpc() || !Cast<APlayerController>(Pawn->GetController())) Pawn = Cast<AWandererCharacter>(ULiveLibrary::Player());
    FString TargetName = NameOrId;
    if (S.Roster.IsValidIndex(S.SelectedIndex) && (TargetName.IsEmpty() || S.Widget.IsValid()))
    {
        TargetName = S.Roster[S.SelectedIndex].Name;
    }
    Close();
    if (!Pawn || TargetName.IsEmpty()) return Pawn;
    if (FPlayableCharacter::NameOf(Pawn).Equals(TargetName, ESearchCase::IgnoreCase))
    {
        Pawn->SetMenuOpen(false);
        UE_LOG(LogTemp, Display, TEXT("CHARACTER SELECT confirmed=%s switched=0"), *FPlayableCharacter::NameOf(Pawn));
        return Pawn;
    }
    if (AWandererCharacter* Replacement = FPlayableCharacter::SwitchPlayer(Pawn, TargetName))
    {
        Replacement->SetMenuOpen(false);
        UE_LOG(LogTemp, Display, TEXT("CHARACTER SELECT confirmed=%s switched=1"), *FPlayableCharacter::NameOf(Replacement));
        return Replacement;
    }
    return Pawn;
}

FString FJapanCharacterSelect::SelectedName()
{
    const FSelectSessionState& S = State();
    return S.Widget.IsValid() && S.Roster.IsValidIndex(S.SelectedIndex) ? S.Roster[S.SelectedIndex].Name : FString();
}

FString FJapanCharacterSelect::FocusedControl()
{
    const FString Name = SelectedName();
    return Name.IsEmpty() ? FString() : (TEXT("character_select:") + Name);
}

FString FJapanCharacterSelect::Describe()
{
    const FSelectSessionState& S = State();
    TSharedRef<FJsonObject> Root = MakeShared<FJsonObject>();
    Root->SetBoolField(TEXT("open"), S.Widget.IsValid());
    Root->SetBoolField(TEXT("startup"), S.bStartup);
    Root->SetStringField(TEXT("selected"), SelectedName());
    const AWandererCharacter* Player = S.Owner.IsValid() ? S.Owner.Get() : Cast<AWandererCharacter>(ULiveLibrary::Player());
    Root->SetStringField(TEXT("playing"), FPlayableCharacter::NameOf(Player));
    const TArray<FCardInfo> AllCards = S.Widget.IsValid() ? S.Roster : Cards();
    TArray<TSharedPtr<FJsonValue>> Items;
    for (const FCardInfo& C : AllCards)
    {
        TSharedRef<FJsonObject> Item = MakeShared<FJsonObject>();
        Item->SetStringField(TEXT("id"), C.Id);
        Item->SetStringField(TEXT("name"), C.Name);
        Item->SetStringField(TEXT("badge"), C.Badge);
        Item->SetStringField(TEXT("tagline"), C.Tagline);
        Item->SetBoolField(TEXT("default"), C.bDefault);
        Item->SetBoolField(TEXT("built"), C.bBuilt);
        Item->SetBoolField(TEXT("portrait_loaded"), C.bPortraitLoaded);
        Items.Add(MakeShared<FJsonValueObject>(Item));
    }
    Root->SetArrayField(TEXT("characters"), Items);
    FString Out;
    TSharedRef<TJsonWriter<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>> Writer = TJsonWriterFactory<TCHAR, TCondensedJsonPrintPolicy<TCHAR>>::Create(&Out);
    FJsonSerializer::Serialize(Root, Writer);
    return Out;
}

static FAutoConsoleCommandWithWorldAndArgs CmdCharacterSelect(
    TEXT("yorimichi.CharacterSelect"),
    TEXT("Open the character selection screen, or choose a character by name (yorimichi.CharacterSelect [Name])."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld*)
    {
        AWandererCharacter* Pawn = Cast<AWandererCharacter>(ULiveLibrary::Player());
        if (!Pawn) return;
        if (Args.Num() > 0 && !Args[0].IsEmpty()) FJapanCharacterSelect::Choose(Args[0]);
        else FJapanCharacterSelect::Open(Pawn, false);
    }));

