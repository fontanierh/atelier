#pragma once
#include "CoreMinimal.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"

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
}
