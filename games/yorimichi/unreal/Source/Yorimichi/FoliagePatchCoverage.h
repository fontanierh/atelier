#pragma once
#include "CoreMinimal.h"

namespace FoliagePatchCoverage
{
struct FCrown
{
    TArray<FVector2D> Hull;
    static double Cross(const FVector2D& A,const FVector2D& B,const FVector2D& C)
    {
        return (B.X-A.X)*(C.Y-A.Y)-(B.Y-A.Y)*(C.X-A.X);
    }
    // Points MUST be vertices of one certified opaque closed convex generated
    // core, never a source mesh or masked proxy. Its projected hull is precisely
    // its occupied footprint; a circumscribed ellipse would fill faceting gaps.
    FCrown(const TArray<FVector>& Points,const FTransform& Pose=FTransform::Identity)
    {
        if (Pose.ContainsNaN()) return;
        TArray<FVector2D> Sorted;
        for (const FVector& Point:Points)
        {
            const FVector P=Pose.TransformPosition(Point);
            if (P.ContainsNaN()) return;
            Sorted.Add(FVector2D(P.X,P.Y));
        }
        Sorted.Sort([](const FVector2D& A,const FVector2D& B){return A.X==B.X?A.Y<B.Y:A.X<B.X;});
        TArray<FVector2D> Unique;
        for (const auto& P:Sorted) if (Unique.IsEmpty() || P!=Unique.Last()) Unique.Add(P);
        if (Unique.Num()<3) return;
        for (const auto& P:Unique)
        {
            while (Hull.Num()>=2 && Cross(Hull[Hull.Num()-2],Hull.Last(),P)<=0.) Hull.Pop(EAllowShrinking::No);
            Hull.Add(P);
        }
        const int32 Lower=Hull.Num();
        for (int32 I=Unique.Num()-2;I>=0;--I)
        {
            const auto& P=Unique[I];
            while (Hull.Num()>Lower && Cross(Hull[Hull.Num()-2],Hull.Last(),P)<=0.) Hull.Pop(EAllowShrinking::No);
            Hull.Add(P);
        }
        Hull.Pop(EAllowShrinking::No);
        if (Hull.Num()<3) Hull.Reset();
    }
    bool Inside(const FVector2D& Point) const
    {
        if (Hull.Num()<3 || Point.ContainsNaN()) return false;
        for (int32 I=0;I<Hull.Num();++I)
            if (Cross(Hull[I],Hull[(I+1)%Hull.Num()],Point)<0.) return false;
        return true;
    }
    bool Contains(const FBox& Box) const
    {
        for (double X:{Box.Min.X,Box.Max.X}) for (double Y:{Box.Min.Y,Box.Max.Y})
            if (!Inside(FVector2D(X,Y))) return false;
        return true;
    }
};

inline bool Worthwhile(int32 InteriorTrees,int32 IndividualTriangles)
{
    // A 32-triangle patch must remove several instances and save at least 4x
    // the certified distant geometry. Cell population alone proves neither.
    return InteriorTrees>=8 && int64(InteriorTrees)*IndividualTriangles>=128;
}

inline bool Inside(const FVector2D& Point,const FBox& Crown)
{
    const FVector C=Crown.GetCenter(),R=Crown.GetExtent();
    return R.X>0. && R.Y>0. &&
        FMath::Square((Point.X-C.X)/R.X)+FMath::Square((Point.Y-C.Y)/R.Y)<=1.;
}

inline bool Contains(const FBox& Ellipse,const FBox& Box)
{
    for (double X:{Box.Min.X,Box.Max.X}) for (double Y:{Box.Min.Y,Box.Max.Y})
        if (!Inside(FVector2D(X,Y),Ellipse)) return false;
    return true;
}

// Each <=2 m tile must fit inside ONE certified opaque convex core. Checking its four
// corners proves coverage of the entire tile, including paths between samples.
// Certify the full bounding rectangle: it contains the generated patch footprint.
inline bool Covered(const FBox& Patch,const TArray<FCrown>& Crowns)
{
    const FVector Span=Patch.GetSize();
    if (!FMath::IsFinite(Span.X) || !FMath::IsFinite(Span.Y) ||
        Span.X<=0. || Span.Y<=0. || Span.X>12800. || Span.Y>12800.) return false;
    const int32 NX=FMath::CeilToInt(Span.X/200.),NY=FMath::CeilToInt(Span.Y/200.);
    for (int32 X=0;X<NX;++X) for (int32 Y=0;Y<NY;++Y)
    {
        const FBox Tile(Patch.Min+FVector(X*Span.X/NX,Y*Span.Y/NY,0.),
                        Patch.Min+FVector((X+1)*Span.X/NX,(Y+1)*Span.Y/NY,Span.Z));
        if (!Crowns.ContainsByPredicate([&Tile](const FCrown& Crown){return Crown.Contains(Tile);})) return false;
    }
    return true;
}
}
