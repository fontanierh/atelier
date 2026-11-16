#pragma once
#include "CoreMinimal.h"
#include "InputCoreTypes.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Text/STextBlock.h"

/** The look the game's own menus share (the settings menu, the Salon's betting counter): flat panels on the WhiteBrush,
 *  rows lit while their control has focus, thin dividers and the legend with the pad's own button names. */
namespace YorimichiMenu
{
    inline const FSlateBrush* White() { return FCoreStyle::Get().GetBrush("WhiteBrush"); }

    /** A lit row's amber tint and its bar on the left. */
    inline const FLinearColor RowTint(.95f, .72f, .3f, .2f);
    inline const FLinearColor RowBar(1.f, .78f, .35f, 1.f);
    /** A divider between sections. */
    inline const FLinearColor DividerColor(1.f, 1.f, 1.f, .12f);
    /** The legend under a menu: which buttons do what. */
    inline const FLinearColor LegendColor(1.f, .9f, .6f, 1.f);

    /** A row lit while Lit says so (its control has focus): the amber tint behind it and a 4 px bar on its left, the rest of
     *  the time transparent. */
    inline TSharedRef<SWidget> LitRow(TFunction<bool()> Lit, const TSharedRef<SWidget>& Content, const FMargin& Padding = FMargin(0, 3, 8, 3))
    {
        return SNew(SBorder).Padding(Padding).BorderImage(White())
            .BorderBackgroundColor_Lambda([Lit] { return FSlateColor(Lit() ? RowTint : FLinearColor::Transparent); })
            [SNew(SHorizontalBox)
                + SHorizontalBox::Slot().AutoWidth()[SNew(SBox).WidthOverride(4)[SNew(SBorder).BorderImage(White())
                    .BorderBackgroundColor_Lambda([Lit] { return FSlateColor(Lit() ? RowBar : FLinearColor::Transparent); })]]
                + SHorizontalBox::Slot().FillWidth(1.f).Padding(8, 0, 0, 0)[Content]];
    }

    /** A 1 px divider line across the menu. */
    inline TSharedRef<SWidget> Divider()
    {
        return SNew(SBox).HeightOverride(1)[SNew(SBorder).BorderImage(White()).BorderBackgroundColor(DividerColor)];
    }

    /** A menu's text in Roboto (FCoreStyle's default font) at Size, wrapped. */
    inline TSharedRef<STextBlock> Text(TAttribute<FText> Value, int32 Size, const FLinearColor& Color, const char* Weight = "Regular",
        ETextJustify::Type Justify = ETextJustify::Left)
    {
        return SNew(STextBlock).Text(Value).Font(FCoreStyle::GetDefaultFontStyle(Weight, Size)).ColorAndOpacity(Color).AutoWrapText(true)
            .Justification(Justify);
    }

    /** A button without chrome of its own, for LitButton. */
    inline const FButtonStyle* Plain() { return &FCoreStyle::Get().GetWidgetStyle<FButtonStyle>("NoBorder"); }

    /** A button drawn as a menu row: no button chrome of its own, the row lit (LitRow) while it has focus. */
    inline TSharedRef<SWidget> LitButton(const TSharedRef<SButton>& Button)
    {
        const TWeakPtr<SWidget> Weak = Button;
        return LitRow([Weak] { const TSharedPtr<SWidget> W = Weak.Pin(); return W && W->HasAnyUserFocus().IsSet(); }, Button);
    }

    /** The pad's names for select, back and the shoulders, by AJapanHUD::CurrentControllerStyle (1 Xbox, 2 PlayStation,
     *  3 Nintendo, else physical positions). */
    struct FPadNames
    {
        const TCHAR *Accept, *Cancel, *Shoulders;
    };
    inline FPadNames PadNames(int32 Style)
    {
        switch (Style)
        {
            case 1: return {TEXT("A"), TEXT("B"), TEXT("LB / RB")};
            case 2: return {TEXT("Cross"), TEXT("Circle"), TEXT("L1 / R1")};
            case 3: return {TEXT("B"), TEXT("A"), TEXT("L / R")};
            default: return {TEXT("Bottom button"), TEXT("Right button"), TEXT("Shoulders")};
        }
    }

    /** The input in use, for a legend: a pad (and its style, AJapanHUD::CurrentControllerStyle) or the keys. It follows the
     *  last key or click, as the settings menu's legend does. */
    struct FInputKind
    {
        int32 PadStyle = 0;
        bool bPad = false;
        explicit FInputKind(int32 Style) : PadStyle(Style), bPad(Style != 0) {}
        FPadNames Pad() const { return PadNames(PadStyle); }
    };

    /** A modal window's frame: it follows the input in use (FInputKind) and closes on the right face button (B on an Xbox
     *  pad) or Escape. OnKey may take other keys first (true when taken, Repeat whether the key repeats); the keys taken
     *  are kept from the game (wave, interact, dodge, the settings menu) and from the window's focus. */
    class SMenuKeys : public SCompoundWidget
    {
    public:
        SLATE_BEGIN_ARGS(SMenuKeys) {}
            SLATE_DEFAULT_SLOT(FArguments, Content)
        SLATE_END_ARGS()

        void Construct(const FArguments& Args, TSharedRef<FInputKind> InInput, TFunction<void()> InClose,
            TFunction<bool(const FKey&, bool)> InOnKey = {})
        {
            Input = InInput;
            Close = MoveTemp(InClose);
            OnKey = MoveTemp(InOnKey);
            ChildSlot[Args._Content.Widget];
        }
        virtual FReply OnPreviewKeyDown(const FGeometry&, const FKeyEvent& E) override
        {
            Input->bPad = E.GetKey().IsGamepadKey();
            return FReply::Unhandled();
        }
        virtual FReply OnPreviewMouseButtonDown(const FGeometry&, const FPointerEvent&) override
        {
            Input->bPad = false;
            return FReply::Unhandled();
        }
        virtual FReply OnKeyDown(const FGeometry&, const FKeyEvent& E) override
        {
            if (IsClose(E.GetKey()))
            {
                if (!E.IsRepeat() && Close) Close();
                return FReply::Handled();
            }
            return OnKey && OnKey(E.GetKey(), E.IsRepeat()) ? FReply::Handled() : FReply::Unhandled();
        }
        virtual FReply OnKeyUp(const FGeometry&, const FKeyEvent& E) override
        {
            // A key taken on its way down is taken on its way up (its repeat flag does not matter here).
            return IsClose(E.GetKey()) || (OnKey && OnKey(E.GetKey(), true)) ? FReply::Handled() : FReply::Unhandled();
        }
    private:
        static bool IsClose(const FKey& K) { return K == EKeys::Gamepad_FaceButton_Right || K == EKeys::Escape; }
        TSharedPtr<FInputKind> Input;
        TFunction<void()> Close;
        TFunction<bool(const FKey&, bool)> OnKey;
    };
}
