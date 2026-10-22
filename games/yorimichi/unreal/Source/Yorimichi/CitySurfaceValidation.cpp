#include "CitySurfaceValidation.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#if WITH_EDITOR
#include "Chaos/TriangleMeshImplicitObject.h"
#endif

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
