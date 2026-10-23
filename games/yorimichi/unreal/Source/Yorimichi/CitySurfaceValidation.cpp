#include "CitySurfaceValidation.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#if WITH_EDITOR
#include "Chaos/TriangleMeshImplicitObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#endif

FString UCitySurfaceValidation::CollisionVertices(UStaticMesh* Mesh)
{
#if WITH_EDITOR
    const auto* Body=Mesh?Mesh->GetBodySetup():nullptr;
    if (!Body || Body->AggGeom.GetElementCount()!=Body->AggGeom.ConvexElems.Num()) return {};
    TArray<TSharedPtr<FJsonValue>> Hulls;
    for (const auto& Hull:Body->AggGeom.ConvexElems)
    {
        const auto Transform=Hull.GetTransform();
        if (!Transform.IsValid() || Hull.VertexData.Num()<4) return {};
        TArray<TSharedPtr<FJsonValue>> Points;
        for (const auto& Vertex:Hull.VertexData)
        {
            const auto Point=Transform.TransformPosition(Vertex);
            if (Point.ContainsNaN()) return {};
            TArray<TSharedPtr<FJsonValue>> Coordinates;
            for (int32 Axis=0;Axis<3;++Axis) Coordinates.Add(MakeShared<FJsonValueNumber>(Point[Axis]));
            Points.Add(MakeShared<FJsonValueArray>(Coordinates));
        }
        Hulls.Add(MakeShared<FJsonValueArray>(Points));
    }
    FString Result;
    return FJsonSerializer::Serialize(Hulls,TJsonWriterFactory<>::Create(&Result))?Result:FString();
#else
    return {};
#endif
}

bool UCitySurfaceValidation::ValidateCollision(UStaticMesh* Mesh,int32 ExpectedTriangles,bool HasAuthoredHulls)
{
#if WITH_EDITOR
    if (!Mesh || ExpectedTriangles<1 || Mesh->LODForCollision!=0 || Mesh->ComplexCollisionMesh) return false;
    const auto* Body=Mesh->GetBodySetup();
    const auto Trace=HasAuthoredHulls?CTF_UseSimpleAndComplex:CTF_UseComplexAsSimple;
    if (!Body || Body->CollisionTraceFlag!=Trace || Body->BuildScale3D!=FVector::OneVector ||
        Body->bNeverNeedsCookedCollisionData || !Body->bCreatedPhysicsMeshes || Body->bFailedToCreatePhysicsMeshes ||
        Body->TriMeshGeometries.IsEmpty()) return false;
    int64 Triangles=0;
    for (const auto& Geometry:Body->TriMeshGeometries)
    {
        if (!Geometry) return false;
        Triangles+=Geometry->Elements().GetNumTriangles();
    }
    return Triangles==ExpectedTriangles;
#else
    return false;
#endif
}

bool UCitySurfaceValidation::ValidateSimpleBoxes(UStaticMesh* Mesh,int32 ExpectedBoxes)
{
#if WITH_EDITOR
    if(!Mesh || ExpectedBoxes<0 || Mesh->LODForCollision!=0 || Mesh->ComplexCollisionMesh)return false;
    const auto* Body=Mesh->GetBodySetup();
    if(!Body || Body->CollisionTraceFlag!=CTF_UseSimpleAsComplex || Body->BuildScale3D!=FVector::OneVector ||
       Body->bNeverNeedsCookedCollisionData || !Body->bCreatedPhysicsMeshes || Body->bFailedToCreatePhysicsMeshes ||
       Body->AggGeom.BoxElems.Num()!=ExpectedBoxes || Body->AggGeom.GetElementCount()!=ExpectedBoxes ||
       !Body->TriMeshGeometries.IsEmpty())return false;
    for(const auto& Box:Body->AggGeom.BoxElems)
        if(Box.Center.ContainsNaN() || Box.Rotation.ContainsNaN() || !FMath::IsFinite(Box.X) ||
           !FMath::IsFinite(Box.Y) || !FMath::IsFinite(Box.Z) || Box.X<=0.f || Box.Y<=0.f || Box.Z<=0.f)return false;
    return true;
#else
    return false;
#endif
}
