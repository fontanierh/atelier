#pragma once
#include "CoreMinimal.h"

/** Physical button positions, named consistently for the detected controller. */
struct FMapPadLabels
{
    const TCHAR *Travel, *Close, *Zoom, *Map, *Mark, *Return, *Cycle, *Current, *Fit;
};
inline FMapPadLabels MapPadLabels(int32 Style)
{
    switch (Style)
    {
        case 1: return {TEXT("A"),TEXT("B"),TEXT("LB / RB"),TEXT("View"),TEXT("Y"),TEXT("X"),TEXT("LT / RT"),TEXT("LS click"),TEXT("RS click")};
        case 2: return {TEXT("Cross"),TEXT("Circle"),TEXT("L1 / R1"),TEXT("Touchpad"),TEXT("Triangle"),TEXT("Square"),TEXT("L2 / R2"),TEXT("L3"),TEXT("R3")};
        case 3: return {TEXT("B"),TEXT("A"),TEXT("L / R"),TEXT("Minus"),TEXT("X"),TEXT("Y"),TEXT("ZL / ZR"),TEXT("LS click"),TEXT("RS click")};
        default: return {TEXT("Bottom button"),TEXT("Right button"),TEXT("Shoulders"),TEXT("View / Select"),TEXT("Top button"),TEXT("Left button"),TEXT("Triggers"),TEXT("Left stick click"),TEXT("Right stick click")};
    }
}
