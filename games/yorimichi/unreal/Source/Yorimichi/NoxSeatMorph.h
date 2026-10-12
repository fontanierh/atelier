#pragma once

// Nox's seat correctives: morph targets NoxSeat_L{m25,0,35,70,105}_R{...} on a 5 x 5 grid of left and right hip
// flexions (degrees, forward positive), blended bilinearly and faded in by the deeper hip's flexion. Standing,
// walking and gliding (both hips under 35 degrees) are exact no-ops. Self-contained (no engine types), so the
// garment candidate's CPU interpolation can be checked against it directly.
namespace NoxSeat
{
    constexpr int Size = 5;
    constexpr int Count = Size * Size;
    constexpr float Grid[Size] = {-25.f, 0.f, 35.f, 70.f, 105.f};
    constexpr const char* Labels[Size] = {"m25", "0", "35", "70", "105"};
    constexpr float GateFrom = 35.f, GateTo = 60.f;

    /** Target index for grid cell (L, R), in the order of garment-candidate.json's morph_names. */
    constexpr int Index(int L, int R) { return L * Size + R; }

    /** Whether cell (L, R)'s target moves vertices: a hip at 70 degrees or more. The others are exact zeros, which
     *  the model need not carry as native targets. */
    constexpr bool Moves(int L, int R) { return Grid[L] >= 70.f || Grid[R] >= 70.f; }

    /** smoothstep(35, 60, max(L, R)): 0 while both hips stay under 35 degrees, 1 from 60. */
    inline float Gate(float FlexL, float FlexR)
    {
        const float Deeper = FlexL > FlexR ? FlexL : FlexR;
        float T = (Deeper - GateFrom) / (GateTo - GateFrom);
        T = T < 0.f ? 0.f : T > 1.f ? 1.f : T;
        return T * T * (3.f - 2.f * T);
    }

    /** The cell below Flex (clamped to the grid's ends) and the fraction T (0..1) towards the next grid value. */
    inline void Cell(float Flex, int& Below, float& T)
    {
        int Under = 0;
        for (int I = 0; I < Size; ++I) Under += Grid[I] < Flex ? 1 : 0;
        Below = Under - 1 < 0 ? 0 : Under - 1 > Size - 2 ? Size - 2 : Under - 1;
        T = (Flex - Grid[Below]) / (Grid[Below + 1] - Grid[Below]);
        T = T < 0.f ? 0.f : T > 1.f ? 1.f : T;
    }

    /** Each target's weight for these flexions (Out[Index(L, R)]): the four bilinear neighbours scaled by Gate, so
     *  every weight is nonnegative and they sum to Gate. False, with every weight 0, below the gate or for a flexion
     *  that is not finite. */
    inline bool Weights(float FlexL, float FlexR, float Out[Count])
    {
        for (int I = 0; I < Count; ++I) Out[I] = 0.f;
        if (!(FlexL > -1e30f && FlexL < 1e30f && FlexR > -1e30f && FlexR < 1e30f)) return false;
        const float Scale = Gate(FlexL, FlexR);
        if (Scale <= 0.f) return false;
        int L, R; float TL, TR;
        Cell(FlexL, L, TL);
        Cell(FlexR, R, TR);
        Out[Index(L, R)] = Scale * (1.f - TL) * (1.f - TR);
        Out[Index(L, R + 1)] = Scale * (1.f - TL) * TR;
        Out[Index(L + 1, R)] = Scale * TL * (1.f - TR);
        Out[Index(L + 1, R + 1)] = Scale * TL * TR;
        return true;
    }
}
