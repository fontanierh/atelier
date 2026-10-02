#include "SkateCollisionAsset.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "PhysicalMaterials/PhysicalMaterial.h"

bool USkateCollisionMeshData::Validate(TArray<FString>& Errors) const
{
    const int32 Before=Errors.Num();
    auto Error=[&](const FString& Text){Errors.Add(GetPathName()+TEXT(": ")+Text);};
    if(FormatVersion!=1) Error(TEXT("unsupported collision format"));
    if(SourceMesh.IsNull()) Error(TEXT("missing source mesh"));
    if(Indices.Num()%3!=0) Error(TEXT("index count is not a multiple of three"));
    if(TangentZ.Num()!=Positions.Num()) Error(TEXT("tangent/position count differs"));
    if(TriangleMaterialSlots.Num()!=Indices.Num()/3) Error(TEXT("triangle/material-slot count differs"));
    for(int32 I=0;I<Positions.Num();++I)
        if(Positions[I].ContainsNaN()||!FMath::IsFinite(Positions[I].X)||!FMath::IsFinite(Positions[I].Y)||!FMath::IsFinite(Positions[I].Z))
            {Error(FString::Printf(TEXT("non-finite position %d"),I));break;}
    for(int32 I=0;I<TangentZ.Num();++I)
        if(TangentZ[I].ContainsNaN()||!FMath::IsFinite(TangentZ[I].X)||!FMath::IsFinite(TangentZ[I].Y)||!FMath::IsFinite(TangentZ[I].Z))
            {Error(FString::Printf(TEXT("non-finite tangent %d"),I));break;}
    for(int32 I:Indices) if(!Positions.IsValidIndex(I)) {Error(TEXT("index outside vertex array"));break;}
    if(UStaticMesh* Mesh=SourceMesh.Get())
    {
        const UBodySetup* Body=Mesh->GetBodySetup();
        if(Mesh->LODForCollision!=SourceLODForCollision) Error(TEXT("collision LOD changed; rebake catalog"));
        if(!Body||Body->BodySetupGuid!=SourceBodySetupGuid) Error(TEXT("body setup changed; rebake catalog"));
        if(Body&&Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple&&Indices.IsEmpty()) Error(TEXT("complex collision has no baked triangles"));
        if(Body&&Body->AggGeom.ConvexElems.Num()!=ConvexIndices.Num()) Error(TEXT("convex element count changed; rebake catalog"));
        if(Body) for(int32 H=0;H<ConvexIndices.Num()&&H<Body->AggGeom.ConvexElems.Num();++H)
        {
            if(ConvexIndices[H].Indices.Num()%3!=0) Error(TEXT("convex index count is not a multiple of three"));
            for(int32 I:ConvexIndices[H].Indices)
                if(!Body->AggGeom.ConvexElems[H].VertexData.IsValidIndex(I)) {Error(TEXT("convex index outside vertex array"));break;}
        }
    }
    return Errors.Num()==Before;
}
const USkateCollisionMeshData* USkateCollisionAsset::FindMesh(const UStaticMesh* Mesh) const
{
    for(const USkateCollisionMeshData* Data:Meshes) if(Data&&Data->SourceMesh.ToSoftObjectPath()==FSoftObjectPath(Mesh)) return Data;
    return nullptr;
}
const FSkateCollisionSurfaceProfile* USkateCollisionAsset::FindProfile(const UPhysicalMaterial* Material) const
{
    if(Material) for(const auto& Profile:SurfaceProfiles) if(Profile.PhysicalMaterial==Material) return &Profile;
    return nullptr;
}
bool USkateCollisionAsset::Validate(TArray<FString>& Errors) const
{
    const int32 Before=Errors.Num();
    if(FormatVersion!=1) Errors.Add(GetPathName()+TEXT(": unsupported catalog format"));
    TSet<FSoftObjectPath> Seen;
    for(const USkateCollisionMeshData* Data:Meshes)
    {
        if(!Data) {Errors.Add(GetPathName()+TEXT(": null mesh data"));continue;}
        if(Seen.Contains(Data->SourceMesh.ToSoftObjectPath())) Errors.Add(GetPathName()+TEXT(": duplicate mesh ")+Data->SourceMesh.ToString());
        Seen.Add(Data->SourceMesh.ToSoftObjectPath());Data->Validate(Errors);
    }
    TSet<const UPhysicalMaterial*> Materials;
    for(const auto& P:SurfaceProfiles)
    {
        if(!P.PhysicalMaterial||Materials.Contains(P.PhysicalMaterial.Get())) Errors.Add(GetPathName()+TEXT(": missing or duplicate physical material profile"));
        Materials.Add(P.PhysicalMaterial.Get());
        if(P.PackedSurface<0||P.PackedSurface>65535) Errors.Add(GetPathName()+TEXT(": packed surface outside uint16 range"));
        if(P.bOverrideContactMaterial&&(!FMath::IsFinite(P.StaticFriction)||!FMath::IsFinite(P.DynamicFriction)||!FMath::IsFinite(P.Restitution)
            ||P.StaticFriction<0||P.DynamicFriction<0||P.Restitution<0||P.Restitution>1)) Errors.Add(GetPathName()+TEXT(": invalid contact material profile"));
    }
    return Errors.Num()==Before;
}
