#pragma once
#include "CoreMinimal.h"

/** A screen-space box used by the atlas label layout. Min is top-left. */
struct FAtlasLabelBox
{
    FVector2D Min = FVector2D::ZeroVector;
    FVector2D Max = FVector2D::ZeroVector;
    FVector2D GetSize() const { return Max - Min; }
    bool Intersects(const FAtlasLabelBox& Other) const
    {
        return Min.X < Other.Max.X && Max.X > Other.Min.X && Min.Y < Other.Max.Y && Max.Y > Other.Min.Y;
    }
};

struct FAtlasLabelRequest
{
    FVector2D Anchor = FVector2D::ZeroVector;
    FVector2D Size = FVector2D::ZeroVector;
    int32 Priority = 0;
    /** The hovered or selected label is always drawn, even when every candidate collides. */
    bool bForce = false;
    /** Region captions are centred on the anchor rather than sitting above it. */
    bool bCentered = false;
};

struct FAtlasLabelPlacement
{
    FVector2D Position = FVector2D::ZeroVector;
    bool bVisible = false;
    /** Draw a leader from the anchor because the label moved to a side or diagonal. */
    bool bLeader = false;
};

namespace AtlasLabelLayout
{
inline FAtlasLabelBox BoxAt(const FVector2D& Position, const FVector2D& Size)
{
    return FAtlasLabelBox{Position, Position + Size};
}

inline float OverlapArea(const FAtlasLabelBox& A, const FAtlasLabelBox& B)
{
    const float X = FMath::Max(0.f, FMath::Min(A.Max.X, B.Max.X) - FMath::Max(A.Min.X, B.Min.X));
    const float Y = FMath::Max(0.f, FMath::Min(A.Max.Y, B.Max.Y) - FMath::Max(A.Min.Y, B.Min.Y));
    return X * Y;
}

/** Lay out non-overlapping labels around their anchors, dropping low-priority labels when space runs out. */
inline TArray<FAtlasLabelPlacement> LayOut(const TArray<FAtlasLabelRequest>& Requests,
                                           const TArray<FAtlasLabelBox>& Obstacles,
                                           const FVector2D& Area,
                                           float Gap = 16.f, float Edge = 8.f)
{
    TArray<FAtlasLabelPlacement> Result;
    Result.SetNum(Requests.Num());
    TArray<int32> Order;
    Order.Reserve(Requests.Num());
    for (int32 I = 0; I < Requests.Num(); ++I) Order.Add(I);
    Order.Sort([&Requests](int32 A, int32 B)
    {
        if (Requests[A].Priority != Requests[B].Priority) return Requests[A].Priority > Requests[B].Priority;
        if (Requests[A].Anchor.Y != Requests[B].Anchor.Y) return Requests[A].Anchor.Y < Requests[B].Anchor.Y;
        if (Requests[A].Anchor.X != Requests[B].Anchor.X) return Requests[A].Anchor.X < Requests[B].Anchor.X;
        return A < B;
    });

    TArray<FAtlasLabelBox> Placed;
    for (const int32 Index : Order)
    {
        const FAtlasLabelRequest& R = Requests[Index];
        const FVector2D Half = R.Size * .5f;
        const float Shift = 18.f;
        TArray<FVector2D> Candidates;
        if (R.bCentered)
        {
            const FVector2D C = R.Anchor - Half;
            Candidates = {
                C,
                C - FVector2D(0, Half.Y + Shift),
                C + FVector2D(0, Half.Y + Shift),
                C + FVector2D(Half.X + Shift, 0),
                C - FVector2D(Half.X + Shift, 0),
                C + FVector2D(Half.X + Shift, Half.Y + Shift),
                C - FVector2D(Half.X + Shift, Half.Y + Shift),
                C + FVector2D(Half.X + Shift, -Half.Y - Shift),
                C - FVector2D(Half.X + Shift, -Half.Y - Shift)
            };
        }
        else
        {
            Candidates = {
                R.Anchor - FVector2D(Half.X, R.Size.Y + Gap),
                R.Anchor + FVector2D(-Half.X, Gap),
                R.Anchor + FVector2D(Gap, -Half.Y),
                R.Anchor - FVector2D(R.Size.X + Gap, Half.Y),
                R.Anchor + FVector2D(Gap, -R.Size.Y - Gap),
                R.Anchor - FVector2D(R.Size.X + Gap, R.Size.Y + Gap),
                R.Anchor + FVector2D(Gap, Gap),
                R.Anchor - FVector2D(R.Size.X + Gap, -Gap)
            };
        }

        FVector2D BestPosition = Candidates[0];
        float BestOverlap = TNumericLimits<float>::Max();
        int32 BestCandidate = 0;
        bool bFound = false;
        for (int32 Candidate = 0; Candidate < Candidates.Num(); ++Candidate)
        {
            FVector2D Position = Candidates[Candidate];
            if (Area.X > R.Size.X + Edge * 2.f)
                Position.X = FMath::Clamp(Position.X, Edge, Area.X - R.Size.X - Edge);
            else
                Position.X = Edge;
            if (Area.Y > R.Size.Y + Edge * 2.f)
                Position.Y = FMath::Clamp(Position.Y, Edge, Area.Y - R.Size.Y - Edge);
            else
                Position.Y = Edge;
            if (Position.X < Edge - .1f || Position.Y < Edge - .1f ||
                Position.X + R.Size.X > Area.X - Edge + .1f || Position.Y + R.Size.Y > Area.Y - Edge + .1f)
                continue;

            const FAtlasLabelBox Box = BoxAt(Position, R.Size);
            float Overlap = 0.f;
            for (const FAtlasLabelBox& Obstacle : Obstacles) Overlap += OverlapArea(Box, Obstacle);
            for (const FAtlasLabelBox& Existing : Placed) Overlap += OverlapArea(Box, Existing);
            if (Overlap <= 0.f)
            {
                BestPosition = Position;
                BestCandidate = Candidate;
                bFound = true;
                break;
            }
            if (Overlap < BestOverlap)
            {
                BestOverlap = Overlap;
                BestPosition = Position;
                BestCandidate = Candidate;
            }
        }

        if (!bFound && !R.bForce) continue;
        if (!bFound) BestCandidate = BestCandidate < 2 ? 2 : BestCandidate;
        Result[Index].Position = BestPosition;
        Result[Index].bVisible = true;
        Result[Index].bLeader = !R.bCentered && BestCandidate >= 2;
        Placed.Add(BoxAt(BestPosition, R.Size));
    }
    return Result;
}
} // namespace AtlasLabelLayout
