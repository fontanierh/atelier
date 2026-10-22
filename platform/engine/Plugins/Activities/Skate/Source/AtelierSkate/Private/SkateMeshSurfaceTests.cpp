#include "SkateRuntimeDetail.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/UObjectGlobals.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSkateReleasedShadingSurfaceTest,"AtelierSkate.Ride.ReleasedShadingSurface",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FSkateReleasedShadingSurfaceTest::RunTest(const FString&)
{
    TStrongObjectPtr<UStaticMesh> Mesh(NewObject<UStaticMesh>());
    Mesh->SetRenderData(MakeUnique<FStaticMeshRenderData>());
    auto* Data=Mesh->GetRenderData();Data->LODResources.Add(new FStaticMeshLODResources);
    auto& LOD=Data->LODResources[0];
    LOD.VertexBuffers.PositionVertexBuffer.Init(3,true);
    LOD.VertexBuffers.StaticMeshVertexBuffer.Init(3,1,true);
    const FVector3f Points[3]={FVector3f(0,0,0),FVector3f(100,0,0),FVector3f(0,100,0)};
    for (uint32 I=0;I<3;++I)
    {
        LOD.VertexBuffers.PositionVertexBuffer.VertexPosition(I)=Points[I];
        // Deliberately different from the cooked face normal: stale shading
        // pointers must not choose the render-data path after cleanup.
        LOD.VertexBuffers.StaticMeshVertexBuffer.SetVertexTangents(I,FVector3f(0,1,0),FVector3f(0,0,1),FVector3f(1,0,0));
        LOD.VertexBuffers.StaticMeshVertexBuffer.SetVertexUV(I,0,FVector2f::ZeroVector);
    }
    TArray<uint32> Indices={0,1,2};LOD.IndexBuffer.SetIndices(Indices,EIndexBufferStride::Force32Bit);
    auto& Section=LOD.Sections.AddDefaulted_GetRef();Section.NumTriangles=1;Section.MaterialIndex=7;
    Mesh->CreateBodySetup();auto* Body=Mesh->GetBodySetup();
    Chaos::FTriangleMeshImplicitObject::ParticlesType Particles;Particles.AddParticles(3);
    for (int32 I=0;I<3;++I) Particles.SetX(I,Points[I]);
    TArray<Chaos::TVec3<int32>> Faces;Faces.Emplace(0,1,2);TArray<uint16> Materials={7};
    Body->TriMeshGeometries.Add(Chaos::FTriangleMeshImplicitObjectPtr(new Chaos::FTriangleMeshImplicitObject(
        MoveTemp(Particles),MoveTemp(Faces),MoveTemp(Materials))));
    LOD.VertexBuffers.StaticMeshVertexBuffer.CleanUp();
    TestFalse(TEXT("Shading CPU storage is gone"),LOD.VertexBuffers.StaticMeshVertexBuffer.GetAllowCPUAccess());
    TestTrue(TEXT("Collision positions remain available"),LOD.VertexBuffers.PositionVertexBuffer.GetAllowCPUAccess());
    const int32 Previous=SkateRuntimeDetail::CVarSkateCookedSurface.GetValueOnGameThread();
    SkateRuntimeDetail::CVarSkateCookedSurface->Set(0,ECVF_SetByCode);
    auto Surface=SkateRuntimeDetail::MeshSurface(Mesh.Get());
    SkateRuntimeDetail::CVarSkateCookedSurface->Set(Previous,ECVF_SetByCode);
    if (!TestTrue(TEXT("Cooked surface remains available"),Surface.IsValid())) return false;
    TestEqual(TEXT("One cooked face"),Surface->Slots.Num(),1);
    if (Surface->Slots.Num()!=1 || Surface->Points.Num()!=3 || Surface->Normals.Num()!=1) return false;
    for (int32 I=0;I<3;++I) TestTrue(TEXT("Cooked corners retained"),Surface->Points[I].Equals(Points[I]));
    TestTrue(TEXT("Cooked face normal is used"),Surface->Normals[0].Equals(FVector3f(0,0,1)));
    TestEqual(TEXT("Material face ownership retained"),Surface->Slots[0],uint16(7));
    TestEqual(TEXT("CPU indices retained"),LOD.IndexBuffer.GetArrayView().Num(),3);
    TestEqual(TEXT("Physics mesh retained"),Body->TriMeshGeometries.Num(),1);
    // Exercise the real module-owned post-GC callback, not a direct prune call.
    // The gather job's plain data must outlive the UObject and cache entry.
    const TObjectKey<UStaticMesh> Key(Mesh.Get());
    auto JobSurface=Surface;
    TWeakPtr<const SkateRuntimeDetail::FMeshSurface,ESPMode::ThreadSafe> Lifetime=Surface;
    Surface.Reset();
    TestTrue(TEXT("Cache owns the live mesh surface"),SkateRuntimeDetail::MeshSurfaceCache().Contains(Key));
    Mesh.Reset();
    CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS,true);
    TestNull(TEXT("Mesh UObject collected"),Key.ResolveObjectPtr());
    TestFalse(TEXT("Post-GC released expired cache ownership"),SkateRuntimeDetail::MeshSurfaceCache().Contains(Key));
    TestTrue(TEXT("Active gather retains immutable surface"),Lifetime.IsValid());
    for (int32 I=0;I<3;++I) TestTrue(TEXT("Active gather corners survive collection"),JobSurface->Points[I].Equals(Points[I]));
    TestTrue(TEXT("Active gather normal survives collection"),JobSurface->Normals[0].Equals(FVector3f(0,0,1)));
    TestEqual(TEXT("Active gather material survives collection"),JobSurface->Slots[0],uint16(7));
    JobSurface.Reset();
    TestFalse(TEXT("Last gather releases the copied arrays"),Lifetime.IsValid());
    return true;
}
#endif
