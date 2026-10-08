#include "JapanBikeSupport.h"
#include "CompGeom/ConvexHull3.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"

bool JapanBikeSupport::Build(TConstArrayView<FVector> Vertices, TArray<FVector>& Points)
{
    Points.Reset();
    if(Vertices.Num()<4)return false;
    for(const FVector& Point:Vertices)if(Point.ContainsNaN())return false;
    UE::Geometry::FConvexHull3d Hull;
    // Keep the reduction below a millimetre. The point budget is a failure bound,
    // not permission to silently approximate a different wheel with fewer points.
    Hull.SimplificationSettings.SkipAtHullDistanceAbsolute=.05;
    Hull.SimplificationSettings.MaxHullVertices=1025; // One over budget detects overflow instead of truncating it.
    if(!Hull.Solve(Vertices.Num(),[&](int32 Index){return Vertices[Index];}))return false;
    TSet<int32> Used;
    for(const auto& Face:Hull.GetTriangles())
    {
        Used.Add(Face.A);Used.Add(Face.B);Used.Add(Face.C);
        const FVector A=Vertices[Face.A];
        // GeometryCore hull faces use Unreal's winding: outward is C-A cross
        // B-A (also used by VectorUtil::Normal), not the opposite inward normal.
        const FVector Normal=FVector::CrossProduct(Vertices[Face.C]-A,Vertices[Face.B]-A).GetSafeNormal();
        if(Normal.IsNearlyZero())return false;
        for(const FVector& Point:Vertices)
            if(FVector::DotProduct(Point-A,Normal)>.051)return false;
    }
    if(Used.Num()>1024)return false;
    TArray<int32> Ordered=Used.Array();Ordered.Sort();
    for(int32 Index:Ordered)Points.Add(Vertices[Index]);
    return Points.Num()>=4;
}

bool JapanBikeSupport::Load(UStaticMesh* Mesh, TArray<FVector>& Points)
{
    Points.Reset();
    if(!Mesh||!Mesh->GetRenderData()||Mesh->GetRenderData()->LODResources.IsEmpty())return false;
    const auto& Buffer=Mesh->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
    if(!Buffer.GetAllowCPUAccess()||!Buffer.GetVertexData()||Buffer.GetNumVertices()==0)return false;
    TArray<FVector> Vertices;Vertices.Reserve(Buffer.GetNumVertices());
    for(uint32 Index=0;Index<Buffer.GetNumVertices();++Index)Vertices.Add(FVector(Buffer.VertexPosition(Index)));
    return Build(Vertices,Points);
}

double JapanBikeSupport::Gap(TConstArrayView<FVector> Points,const FTransform& Transform,
    TFunctionRef<bool(const FVector&,double&)> GroundHeight)
{
    if(Points.IsEmpty()||Transform.ContainsNaN())return InvalidGap;
    double Minimum=InvalidGap;
    for(const FVector& Local:Points)
    {
        const FVector Point=Transform.TransformPosition(Local);double Ground=0.;
        if(Point.ContainsNaN()||!GroundHeight(Point,Ground)||!FMath::IsFinite(Ground))return InvalidGap;
        Minimum=FMath::Min(Minimum,Point.Z-Ground);
    }
    return Minimum;
}
