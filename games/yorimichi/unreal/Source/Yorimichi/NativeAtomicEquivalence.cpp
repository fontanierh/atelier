#include "NativeAtomicEquivalence.h"
#include "Components/StaticMeshComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Materials/MaterialInterface.h"
#include "SceneTypes.h"
#include "CollisionQueryParams.h"
#include "CollisionShape.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "StaticMeshResources.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#if WITH_EDITOR
#include "MeshDescription.h"
#include "StaticMeshAttributes.h"
#include "Chaos/TriangleMeshImplicitObject.h"
#include "Chaos/Convex.h"
#endif

namespace NativeAtomicEvidence
{
    using FValues=TArray<TSharedPtr<FJsonValue>>;
    TSharedPtr<FJsonValue> Vector(std::initializer_list<double> Values,bool& Valid)
    {
        FValues Result;for(double Value:Values)
        { if(!FMath::IsFinite(Value))Valid=false;Result.Add(MakeShared<FJsonValueNumber>(Value)); }
        return MakeShared<FJsonValueArray>(Result);
    }
    TSharedPtr<FJsonValue> Transform(const FTransform& Value,bool& Valid)
    {
        if(!Value.IsValid())Valid=false;
        const FMatrix M=Value.ToMatrixWithScale();FValues Rows;
        // JSON/NumPy use column vectors; UE matrices multiply row vectors.
        for(int32 Row=0;Row<4;++Row)Rows.Add(Vector({M.M[0][Row],M.M[1][Row],M.M[2][Row],M.M[3][Row]},Valid));
        return MakeShared<FJsonValueArray>(Rows);
    }
    FString Text(const TSharedRef<FJsonObject>& Value,bool Valid)
    {
        FString Result;return Valid && FJsonSerializer::Serialize(Value,TJsonWriterFactory<>::Create(&Result))?Result:FString();
    }
}

FString UNativeAtomicEquivalence::Snapshot(UStaticMesh* Mesh,const FString& Logical,int32 FirstTriangle,int32 MaximumTriangles,int32 LODIndex)
{
#if WITH_EDITOR
    using namespace NativeAtomicEvidence;
    if(!Mesh || Logical.IsEmpty() || LODIndex<0 || FirstTriangle<0 || MaximumTriangles<1 || MaximumTriangles>32768)return {};
    const auto* Description=LODIndex<Mesh->GetNumSourceModels()?Mesh->GetMeshDescription(LODIndex):nullptr;const auto* Render=Mesh->GetRenderData();
    const auto* Body=Mesh->GetBodySetup();
    if(!Render || !Render->LODResources.IsValidIndex(LODIndex) || !Body || Body->BuildScale3D!=FVector::OneVector ||
        !Body->bCreatedPhysicsMeshes || Body->bFailedToCreatePhysicsMeshes)return {};
    const auto& LOD=Render->LODResources[LODIndex];const auto Indices=LOD.IndexBuffer.GetArrayView();
    const auto& Positions=LOD.VertexBuffers.PositionVertexBuffer;const auto& Vertices=LOD.VertexBuffers.StaticMeshVertexBuffer;
    const auto& Colors=LOD.VertexBuffers.ColorVertexBuffer;
    if(!Positions.GetNumVertices() || !Positions.GetVertexData() || !Vertices.GetTangentData() ||
        (Vertices.GetNumTexCoords() && !Vertices.GetTexCoordData()) ||
        Vertices.GetNumVertices()!=Positions.GetNumVertices() ||
        (Colors.GetNumVertices() && (Colors.GetNumVertices()!=Positions.GetNumVertices() || !Colors.GetVertexData())) ||
        Indices.Num()!=int32(LOD.GetNumTriangles()*3) || Indices.Num()==0)return {};
    const int32 SourceCount=Description?Description->Triangles().Num():0,RenderCount=LOD.GetNumTriangles();
    int32 CookedCount=0;if(LODIndex==0)for(const auto& Geometry:Body->TriMeshGeometries)
    { if(!Geometry)return {};CookedCount+=Geometry->Elements().GetNumTriangles(); }
    if(FirstTriangle>=FMath::Max3(SourceCount,RenderCount,CookedCount))return {};
    bool Valid=true;
    auto Root=MakeShared<FJsonObject>();Root->SetNumberField(TEXT("schema"),1);Root->SetStringField(TEXT("logical"),Logical);
    Root->SetStringField(TEXT("asset"),Mesh->GetPathName());Root->SetNumberField(TEXT("first"),FirstTriangle);
    Root->SetNumberField(TEXT("maximum"),MaximumTriangles);Root->SetNumberField(TEXT("lod"),LODIndex);
    Root->SetBoolField(TEXT("source_available"),Description!=nullptr);Root->SetNumberField(TEXT("source_count"),SourceCount);
    Root->SetNumberField(TEXT("render_count"),RenderCount);Root->SetNumberField(TEXT("cooked_count"),CookedCount);
    const FBox Bounds=Mesh->GetBoundingBox();if(!Bounds.IsValid)return {};
    Root->SetArrayField(TEXT("bounds"),{Vector({Bounds.Min.X,Bounds.Min.Y,Bounds.Min.Z},Valid),Vector({Bounds.Max.X,Bounds.Max.Y,Bounds.Max.Z},Valid)});
    FValues Slots;TMap<FName,int32> SlotIndices;
    for(int32 Index=0;Index<Mesh->GetStaticMaterials().Num();++Index)
    {
        const auto& Slot=Mesh->GetStaticMaterials()[Index];if(!Slot.MaterialInterface || SlotIndices.Contains(Slot.ImportedMaterialSlotName))return {};
        SlotIndices.Add(Slot.ImportedMaterialSlotName,Index);auto Row=MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("name"),Slot.ImportedMaterialSlotName.ToString());Row->SetStringField(TEXT("material"),Slot.MaterialInterface->GetPathName());
        Slots.Add(MakeShared<FJsonValueObject>(Row));
    }
    if(Slots.IsEmpty())return {};Root->SetArrayField(TEXT("slots"),Slots);
    auto Settings=MakeShared<FJsonObject>();Settings->SetNumberField(TEXT("lods"),Mesh->GetNumLODs());
    Settings->SetNumberField(TEXT("collision_lod"),Mesh->LODForCollision);
    Settings->SetNumberField(TEXT("collision_trace"),int32(Body->CollisionTraceFlag));
    Settings->SetStringField(TEXT("complex_proxy"),Mesh->ComplexCollisionMesh?Mesh->ComplexCollisionMesh->GetPathName():FString());
    Settings->SetBoolField(TEXT("allow_cpu_access"),Mesh->bAllowCPUAccess);
    Settings->SetBoolField(TEXT("full_precision_uvs"),Vertices.GetUseFullPrecisionUVs());
    Settings->SetBoolField(TEXT("high_precision_tangents"),Vertices.GetUseHighPrecisionTangentBasis());
    Settings->SetBoolField(TEXT("never_cooked"),Body->bNeverNeedsCookedCollisionData);
    Root->SetObjectField(TEXT("settings"),Settings);
    if(Description)
    {
    FStaticMeshConstAttributes Attributes(*Description);const auto SourcePositions=Attributes.GetVertexPositions();
    const auto Normals=Attributes.GetVertexInstanceNormals();const auto Tangents=Attributes.GetVertexInstanceTangents();
    const auto Signs=Attributes.GetVertexInstanceBinormalSigns();const auto UVs=Attributes.GetVertexInstanceUVs();
    const auto SourceColors=Attributes.GetVertexInstanceColors();const auto Hardness=Attributes.GetEdgeHardnesses();
    const auto GroupSlots=Attributes.GetPolygonGroupMaterialSlotNames();
    auto Source=MakeShared<FJsonObject>();Source->SetStringField(TEXT("kind"),TEXT("mesh_description"));
    Source->SetNumberField(TEXT("uv_count"),UVs.GetNumChannels());Source->SetStringField(TEXT("color_encoding"),TEXT("linear_float32"));
    FValues SourceRows;int32 Ordinal=0;
    for(const FTriangleID Triangle:Description->Triangles().GetElementIDs())
    {
        if(Ordinal++<FirstTriangle)continue;if(Ordinal>FirstTriangle+MaximumTriangles)break;
        const auto Instances=Description->GetTriangleVertexInstances(Triangle);if(Instances.Num()!=3)return {};
        const FName Slot=GroupSlots[Description->GetTrianglePolygonGroup(Triangle)];const int32* Material=SlotIndices.Find(Slot);
        if(!Material)return {};auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("material"),*Material);
        FValues Corners,Edges;
        for(const auto Instance:Instances)
        {
            const auto P=SourcePositions[Description->GetVertexInstanceVertex(Instance)];const auto N=Normals[Instance];
            const auto T=Tangents[Instance];const auto C=SourceColors[Instance];auto Corner=MakeShared<FJsonObject>();
            Corner->SetArrayField(TEXT("position"),Vector({P.X,P.Y,P.Z},Valid)->AsArray());
            Corner->SetArrayField(TEXT("normal"),Vector({N.X,N.Y,N.Z},Valid)->AsArray());
            Corner->SetArrayField(TEXT("tangent"),Vector({T.X,T.Y,T.Z,Signs[Instance]},Valid)->AsArray());
            Corner->SetArrayField(TEXT("color"),Vector({C.X,C.Y,C.Z,C.W},Valid)->AsArray());
            FValues Coordinates;for(int32 Channel=0;Channel<UVs.GetNumChannels();++Channel)
            { const auto UV=UVs.Get(Instance,Channel);Coordinates.Add(Vector({UV.X,UV.Y},Valid)); }
            Corner->SetArrayField(TEXT("uvs"),Coordinates);Corners.Add(MakeShared<FJsonValueObject>(Corner));
        }
        for(const auto Edge:Description->GetTriangleEdges(Triangle))Edges.Add(MakeShared<FJsonValueBoolean>(Hardness[Edge]));
        Row->SetArrayField(TEXT("corners"),Corners);Row->SetArrayField(TEXT("hard_edges"),Edges);SourceRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    Source->SetArrayField(TEXT("triangles"),SourceRows);Root->SetObjectField(TEXT("source"),Source);
    }
    else Root->SetField(TEXT("source"),MakeShared<FJsonValueNull>());
    auto GPU=MakeShared<FJsonObject>();GPU->SetStringField(TEXT("kind"),TEXT("render_buffers"));
    GPU->SetNumberField(TEXT("uv_count"),Vertices.GetNumTexCoords());
    GPU->SetStringField(TEXT("color_encoding"),Colors.GetNumVertices()?TEXT("srgb_uint8"):TEXT("absent"));FValues RenderRows;
    for(int32 Triangle=FirstTriangle;Triangle<FMath::Min(RenderCount,FirstTriangle+MaximumTriangles);++Triangle)
    {
        int32 Material=INDEX_NONE,Owners=0;
        for(const auto& Section:LOD.Sections)if(uint32(Triangle*3)>=Section.FirstIndex && uint32(Triangle*3)<Section.FirstIndex+Section.NumTriangles*3)
        { Material=Section.MaterialIndex;++Owners; }
        if(Owners!=1 || !Mesh->GetStaticMaterials().IsValidIndex(Material))return {};
        auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("material"),Material);FValues Corners;
        for(int32 CornerIndex=0;CornerIndex<3;++CornerIndex)
        {
            const uint32 Index=Indices[Triangle*3+CornerIndex];if(Index>=Positions.GetNumVertices())return {};
            const auto P=Positions.VertexPosition(Index);const auto N=Vertices.VertexTangentZ(Index);const auto T=Vertices.VertexTangentX(Index);
            auto Corner=MakeShared<FJsonObject>();Corner->SetArrayField(TEXT("position"),Vector({P.X,P.Y,P.Z},Valid)->AsArray());
            Corner->SetArrayField(TEXT("normal"),Vector({N.X,N.Y,N.Z,N.W},Valid)->AsArray());
            Corner->SetArrayField(TEXT("tangent"),Vector({T.X,T.Y,T.Z,T.W},Valid)->AsArray());
            FValues Coordinates;for(uint32 Channel=0;Channel<Vertices.GetNumTexCoords();++Channel)
            { const auto UV=Vertices.GetVertexUV(Index,Channel);Coordinates.Add(Vector({UV.X,UV.Y},Valid)); }
            Corner->SetArrayField(TEXT("uvs"),Coordinates);
            if(Colors.GetNumVertices())
            { const auto C=Colors.VertexColor(Index);Corner->SetArrayField(TEXT("color"),Vector({double(C.R),double(C.G),double(C.B),double(C.A)},Valid)->AsArray()); }
            else Corner->SetField(TEXT("color"),MakeShared<FJsonValueNull>());
            Corners.Add(MakeShared<FJsonValueObject>(Corner));
        }
        Row->SetArrayField(TEXT("corners"),Corners);Row->SetField(TEXT("hard_edges"),MakeShared<FJsonValueNull>());RenderRows.Add(MakeShared<FJsonValueObject>(Row));
    }
    GPU->SetArrayField(TEXT("triangles"),RenderRows);Root->SetObjectField(TEXT("render"),GPU);
    FValues CookedRows;int32 CookedOffset=0;
    if(LODIndex==0)for(const auto& Geometry:Body->TriMeshGeometries)
    {
        const int32 Count=Geometry->Elements().GetNumTriangles();
        for(int32 Triangle=FMath::Max(0,FirstTriangle-CookedOffset);Triangle<FMath::Min(Count,FirstTriangle+MaximumTriangles-CookedOffset);++Triangle)
        {
            Chaos::FTriangle Tri;int32 A=0,B=0,C=0;Geometry->GetTransformedTriangle(Triangle,Chaos::FRigidTransform3::Identity,Tri,A,B,C);
            FValues Points;for(int32 I=0;I<3;++I)Points.Add(Vector({Tri[I].X,Tri[I].Y,Tri[I].Z},Valid));
            CookedRows.Add(MakeShared<FJsonValueArray>(Points));
        }
        CookedOffset+=Count;
    }
    Root->SetArrayField(TEXT("cooked"),CookedRows);FValues Hulls;
    const auto& Agg=Body->AggGeom;
    if(Agg.GetElementCount()!=Agg.ConvexElems.Num()+Agg.BoxElems.Num()+Agg.SphereElems.Num()+Agg.SphylElems.Num())return {};
    if(FirstTriangle==0 && LODIndex==0)
    {
        for(const auto& Hull:Agg.ConvexElems)
        {
            const auto& Convex=Hull.GetChaosConvexMesh();if(!Convex || Convex->NumVertices()<4 || Convex->NumPlanes()<4)return {};
            auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("kind"),TEXT("convex"));auto Data=MakeShared<FJsonObject>();
            FValues Points,Faces,Authored;
            for(int32 I=0;I<Convex->NumVertices();++I){const auto P=Convex->GetVertex(I);Points.Add(Vector({P.X,P.Y,P.Z},Valid));}
            for(int32 I=0;I<Convex->NumPlanes();++I)
            { FValues Face;if(Convex->NumPlaneVertices(I)<3)return {};for(int32 J=0;J<Convex->NumPlaneVertices(I);++J)Face.Add(MakeShared<FJsonValueNumber>(Convex->GetPlaneVertex(I,J)));Faces.Add(MakeShared<FJsonValueArray>(Face)); }
            if(Hull.VertexData.Num()<4)return {};for(const auto& P:Hull.VertexData)Authored.Add(Vector({P.X,P.Y,P.Z},Valid));
            Data->SetArrayField(TEXT("vertices"),Points);Data->SetArrayField(TEXT("faces"),Faces);Data->SetField(TEXT("matrix"),Transform(Hull.GetTransform(),Valid));
            Row->SetObjectField(TEXT("geometry"),Data);Row->SetArrayField(TEXT("authored_vertices"),Authored);Hulls.Add(MakeShared<FJsonValueObject>(Row));
        }
        auto Primitive=[&](const TCHAR* Kind,const FTransform& Matrix,const TSharedRef<FJsonObject>& Data)
        { auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("kind"),Kind);Data->SetField(TEXT("matrix"),Transform(Matrix,Valid));Row->SetObjectField(TEXT("geometry"),Data);Hulls.Add(MakeShared<FJsonValueObject>(Row)); };
        for(const auto& Hull:Agg.BoxElems)
        { auto Data=MakeShared<FJsonObject>();Data->SetArrayField(TEXT("size"),Vector({Hull.X,Hull.Y,Hull.Z},Valid)->AsArray());Primitive(TEXT("box"),Hull.GetTransform(),Data); }
        for(const auto& Hull:Agg.SphereElems)
        { auto Data=MakeShared<FJsonObject>();Data->SetNumberField(TEXT("radius"),Hull.Radius);Primitive(TEXT("sphere"),Hull.GetTransform(),Data); }
        for(const auto& Hull:Agg.SphylElems)
        { auto Data=MakeShared<FJsonObject>();Data->SetNumberField(TEXT("radius"),Hull.Radius);Data->SetNumberField(TEXT("length"),Hull.Length);Primitive(TEXT("capsule"),Hull.GetTransform(),Data); }
    }
    Root->SetArrayField(TEXT("hulls"),Hulls);Root->SetBoolField(TEXT("hulls_complete"),FirstTriangle==0 && LODIndex==0);
    return Text(Root,Valid);
#else
    return {};
#endif
}

FString UNativeAtomicEquivalence::Probe(UStaticMeshComponent* Component,FVector Start,FVector End,FQuat Rotation,float Radius,float HalfHeight,bool TraceComplex)
{
    using namespace NativeAtomicEvidence;
    if(!Component || !Component->GetStaticMesh() || !Component->IsRegistered() || Start.ContainsNaN() || End.ContainsNaN() ||
        Start.Equals(End) || !Rotation.IsNormalized() || !FMath::IsFinite(Radius) || !FMath::IsFinite(HalfHeight) ||
        Radius<0 || (Radius>0 && HalfHeight<Radius))return {};
    FHitResult Hit;bool Blocked=false;
    if(Radius>0)Blocked=Component->SweepComponent(Hit,Start,End,Rotation,FCollisionShape::MakeCapsule(Radius,HalfHeight),TraceComplex);
    else{FCollisionQueryParams Params(SCENE_QUERY_STAT(AtomicOwnedMeshProbe),TraceComplex);Blocked=Component->LineTraceComponent(Hit,Start,End,Params);}
    bool Valid=true;auto Result=MakeShared<FJsonObject>();Result->SetBoolField(TEXT("blocking"),Blocked && Hit.bBlockingHit);
    Result->SetStringField(TEXT("component"),Component->GetPathName());Result->SetStringField(TEXT("mesh"),Component->GetStaticMesh()->GetPathName());
    Result->SetBoolField(TEXT("selected_component"),!Blocked || Hit.GetComponent()==Component);
    if(Blocked)
    {
        if(!Hit.bBlockingHit || Hit.GetComponent()!=Component)return {};
        Result->SetArrayField(TEXT("position"),Vector({Hit.ImpactPoint.X,Hit.ImpactPoint.Y,Hit.ImpactPoint.Z},Valid)->AsArray());
        Result->SetArrayField(TEXT("normal"),Vector({Hit.ImpactNormal.X,Hit.ImpactNormal.Y,Hit.ImpactNormal.Z},Valid)->AsArray());
        Result->SetNumberField(TEXT("distance"),Hit.Distance);
    }
    return Text(Result,Valid);
}

FString UNativeAtomicEquivalence::ComponentPolicy(UStaticMeshComponent* Component)
{
    using namespace NativeAtomicEvidence;if(!Component || !Component->GetStaticMesh())return {};
    bool Valid=true;auto Result=MakeShared<FJsonObject>();Result->SetStringField(TEXT("component"),Component->GetPathName());
    Result->SetStringField(TEXT("mesh"),Component->GetStaticMesh()->GetPathName());Result->SetField(TEXT("matrix"),Transform(Component->GetComponentTransform(),Valid));
    Result->SetNumberField(TEXT("collision_enabled"),int32(Component->GetCollisionEnabled()));
    Result->SetNumberField(TEXT("object_channel"),int32(Component->GetCollisionObjectType()));
    FValues Responses;for(int32 I=0;I<ECC_MAX;++I)Responses.Add(MakeShared<FJsonValueNumber>(int32(Component->GetCollisionResponseToChannel(ECollisionChannel(I)))));
    Result->SetArrayField(TEXT("responses"),Responses);Result->SetBoolField(TEXT("cast_shadow"),Component->CastShadow);
    Result->SetNumberField(TEXT("min_draw_distance"),Component->MinDrawDistance);Result->SetNumberField(TEXT("max_draw_distance"),Component->LDMaxDrawDistance);
    Result->SetBoolField(TEXT("visible"),Component->IsVisible());Result->SetNumberField(TEXT("materials"),Component->GetNumMaterials());
    FValues MaterialBindings;for(int32 Index=0;Index<Component->GetNumMaterials();++Index)
    { const auto* Material=Component->GetMaterial(Index);if(!Material)return {};MaterialBindings.Add(MakeShared<FJsonValueString>(Material->GetPathName())); }
    Result->SetArrayField(TEXT("material_bindings"),MaterialBindings);
    const FBox MeshBounds=Component->GetStaticMesh()->GetBoundingBox();if(!MeshBounds.IsValid)return {};
    Result->SetArrayField(TEXT("mesh_bounds"),{Vector({MeshBounds.Min.X,MeshBounds.Min.Y,MeshBounds.Min.Z},Valid),Vector({MeshBounds.Max.X,MeshBounds.Max.Y,MeshBounds.Max.Z},Valid)});
    Result->SetNumberField(TEXT("wpo_disable_distance"),Component->GetWorldPositionOffsetDisableDistance());
    Result->SetArrayField(TEXT("lighting_channels"),{MakeShared<FJsonValueBoolean>(bool(Component->LightingChannels.bChannel0)),
        MakeShared<FJsonValueBoolean>(bool(Component->LightingChannels.bChannel1)),MakeShared<FJsonValueBoolean>(bool(Component->LightingChannels.bChannel2))});
    FValues PrimitiveData;for(float Value:Component->GetCustomPrimitiveData().Data)PrimitiveData.Add(MakeShared<FJsonValueNumber>(Value));
    Result->SetArrayField(TEXT("primitive_data"),PrimitiveData);FValues Tags;
    for(const auto& Tag:Component->ComponentTags)Tags.Add(MakeShared<FJsonValueString>(Tag.ToString()));Result->SetArrayField(TEXT("tags"),Tags);
    if(const auto* Instanced=Cast<UInstancedStaticMeshComponent>(Component))
    {
        FValues Instances;for(int32 Index=0;Index<Instanced->GetInstanceCount();++Index)
        { FTransform Matrix;if(!Instanced->GetInstanceTransform(Index,Matrix,true))return {};Instances.Add(Transform(Matrix,Valid)); }
        Result->SetArrayField(TEXT("instances"),Instances);Result->SetNumberField(TEXT("instance_min_draw"),Instanced->InstanceMinDrawDistance);
        Result->SetNumberField(TEXT("instance_start_cull"),Instanced->InstanceStartCullDistance);Result->SetNumberField(TEXT("instance_end_cull"),Instanced->InstanceEndCullDistance);
        Result->SetNumberField(TEXT("instance_lod_scale"),Instanced->InstanceLODDistanceScale);
    }
    else Result->SetArrayField(TEXT("instances"),{});
    return Text(Result,Valid);
}
