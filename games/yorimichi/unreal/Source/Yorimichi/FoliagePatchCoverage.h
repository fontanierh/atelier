#pragma once
#include "CoreMinimal.h"

namespace FoliagePatchCoverage
{
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

// Each <=2 m tile must fit inside ONE convex crown ellipse. Checking its four
// corners proves coverage of the entire tile, including paths between samples.
// Certify the full bounding rectangle: it contains the generated patch footprint.
inline bool Covered(const FBox& Patch,const TArray<FBox>& Crowns)
{
    const FVector Span=Patch.GetSize();
    if (!FMath::IsFinite(Span.X) || !FMath::IsFinite(Span.Y) ||
        Span.X<=0. || Span.Y<=0. || Span.X>12800. || Span.Y>12800.) return false;
    const int32 NX=FMath::CeilToInt(Span.X/200.),NY=FMath::CeilToInt(Span.Y/200.);
    for (int32 X=0;X<NX;++X) for (int32 Y=0;Y<NY;++Y)
    {
        const FBox Tile(Patch.Min+FVector(X*Span.X/NX,Y*Span.Y/NY,0.),
                        Patch.Min+FVector((X+1)*Span.X/NX,(Y+1)*Span.Y/NY,Span.Z));
        if (!Crowns.ContainsByPredicate([&Tile](const FBox& Crown){return Contains(Crown,Tile);})) return false;
    }
    return true;
}
}
