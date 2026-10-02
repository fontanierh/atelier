#include "SkateCollisionWorld.h"
#include "SkateCollisionAsset.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SplineMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "Materials/MaterialInterface.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/BodySetup.h"
#include "UObject/UObjectIterator.h"
#include "Serialization/MemoryWriter.h"
#include "Async/Async.h"
#include <cfenv>
#include <cstring>
#include <limits>
#include <utility>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace
{
    class FScopedCollisionFloatEnvironment
    {
    public:
        FScopedCollisionFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            SavedOkay_=std::fegetenv(&Saved_)==0;
            Ready_=SavedOkay_&&std::fesetenv(FE_DFL_ENV)==0;
        }
        ~FScopedCollisionFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            if(SavedOkay_)std::fesetenv(&Saved_);
        }
        FScopedCollisionFloatEnvironment(const FScopedCollisionFloatEnvironment&)=delete;
        FScopedCollisionFloatEnvironment& operator=(const FScopedCollisionFloatEnvironment&)=delete;
        bool IsReady() const {return Ready_;}
    private:
        std::fenv_t Saved_{};
        bool SavedOkay_=false,Ready_=false;
    };
    struct FNativeCollisionValidationResult
    {
        bool bOkay=false;
        FString Error;
    };
    template<class Callable>
    bool RunNativeCollisionValidation(Callable&& Work,FString& Error)
    {
        // Only plain captured data reaches this thread. Match the live native
        // worker's IEEE environment and stack instead of the editor caller's.
        auto Future=AsyncThread([Work=Forward<Callable>(Work)]() mutable
        {
            FNativeCollisionValidationResult Result;
            FScopedCollisionFloatEnvironment Environment;
            if(!Environment.IsReady())
            {Result.Error=TEXT("Native collision validation floating-point environment setup failed");return Result;}
            Result.bOkay=Work(Result.Error);return Result;
        },32*1024*1024);
        auto Result=Future.Get();Error=MoveTemp(Result.Error);return Result.bOkay;
    }
    FVector ToNative(const FVector& V) {return FVector(-V.Y,V.Z,V.X)*.01;}
    const USkateCollisionMeshData* FindMesh(TConstArrayView<USkateCollisionAsset*> Catalogs,UStaticMesh* Mesh)
    {for(const auto* C:Catalogs)if(C)if(const auto* D=C->FindMesh(Mesh))return D;return nullptr;}
    FSkateCollisionTriangleMaterial ResolveMaterial(const UStaticMeshComponent* Component,int32 Slot,
        TConstArrayView<USkateCollisionAsset*> Catalogs)
    {
        FSkateCollisionTriangleMaterial Out;
        if(!Component)return Out;
        // Resolve authored material inputs without borrowing a Chaos body's
        // cached creation state. This is UE's body/component/setup/material priority.
        UPhysicalMaterial* Physical=Component->BodyInstance.GetPhysMaterialOverride();
        if(!Physical)Physical=Component->GetPhysicsMaterialOverride();
        if(!Physical&&Slot==INDEX_NONE)
            if(const UStaticMesh* Mesh=Component->GetStaticMesh())
                if(const UBodySetup* Body=Mesh->GetBodySetup())Physical=Body->PhysMaterial;
        if(!Physical)
        {
            const UMaterialInterface* Material=Slot==INDEX_NONE?Component->GetPhysicsMaterialBase():Component->GetMaterial(Slot);
            if(Material)Physical=Material->GetPhysicalMaterial();
        }
        if(!Physical&&GEngine)Physical=GEngine->DefaultPhysMaterial;
        for(const auto* Catalog:Catalogs)if(Catalog)if(const auto* P=Catalog->FindProfile(Physical))
        {
            Out.bOverride=P->bOverrideContactMaterial;Out.StaticFriction=P->StaticFriction;
            Out.DynamicFriction=P->DynamicFriction;Out.Restitution=P->Restitution;Out.Surface=uint16(P->PackedSurface);break;
        }
        return Out;
    }
    bool Eligible(const UStaticMeshComponent* C,UWorld* World,ACharacter* Rider,const FBox& Region)
    {return C->GetWorld()==World&&C->GetOwner()!=Rider&&C->IsRegistered()&&C->IsCollisionEnabled()
        &&C->GetCollisionResponseToChannel(ECC_Pawn)==ECR_Block&&C->Bounds.GetBox().Intersect(Region);}
    TArray<FTransform> Instances(UStaticMeshComponent* C,const FBox& Region)
    {
        TArray<FTransform> Out;
        if(auto* ISM=Cast<UInstancedStaticMeshComponent>(C))
            for(int32 Index:ISM->GetInstancesOverlappingBox(Region,true))
            {FTransform T;if(ISM->GetInstanceTransform(Index,T,true))Out.Add(T);}
        else Out.Add(C->GetComponentTransform());
        return Out;
    }
}
FVector SkateCollisionSnapshotCentre(UWorld* World,const FVector& Position)
{
    for(TActorIterator<AActor> It(World);It;++It)
        if(It->ActorHasTag(TEXT("SkatePark"))&&(Position-It->GetActorLocation()).GetAbsMax()<=6000.f)
            return It->GetActorLocation();
    return Position;
}

void FSkateCollisionSnapshot::Add(const FVector& A, FVector B, FVector C)
        {
            if (Full()) return;
            FBox Bounds(ForceInit); Bounds+=A; Bounds+=B; Bounds+=C;
            if (!Bounds.Intersect(Region) || FVector::CrossProduct(B-A,C-A).SizeSquared()<.0001) return;
            Swap(B,C); // The coordinate reflection reverses winding.
            // The solver takes each normal from its own f32 points and refuses a flat one: drop slivers at that precision.
            const FVector3f P[3]={FVector3f(ToNative(A)),FVector3f(ToNative(B)),FVector3f(ToNative(C))};
            const FVector3d E1(P[1]-P[0]),E2(P[2]-P[0]);
            const double Twice=FVector3d::CrossProduct(E1,E2).Size();
            if (Twice<1e-9 || Twice<1e-6*E1.Size()*E2.Size()) return;
            Points.Append(P,3);
            Materials.Add(CurrentMaterial);
        }
        // A face of a convex solid, turned away from the solid's centre.
void FSkateCollisionSnapshot::AddFacing(const FVector& Centre, const FVector& A, const FVector& B, const FVector& C)
        {
            if (FVector::DotProduct(FVector::CrossProduct(B-A,C-A),(A+B+C)/3.-Centre)<0) Add(A,C,B); else Add(A,B,C);
        }
void FSkateCollisionSnapshot::AddBox(const FTransform& T, const FVector& Half)
        {
            auto Corner=[&](int32 I){ return T.TransformPosition(FVector(I&1?Half.X:-Half.X,I&2?Half.Y:-Half.Y,I&4?Half.Z:-Half.Z)); };
            static const int32 Faces[6][4]={{0,2,6,4},{1,5,7,3},{0,4,5,1},{2,3,7,6},{0,1,3,2},{4,6,7,5}};
            for (const auto& Q : Faces)
            {
                AddFacing(T.GetLocation(),Corner(Q[0]),Corner(Q[1]),Corner(Q[2]));
                AddFacing(T.GetLocation(),Corner(Q[0]),Corner(Q[2]),Corner(Q[3]));
            }
        }
        // A capsule along local Z whose hemisphere centres sit Half above and below the origin; Half 0 is a sphere.
void FSkateCollisionSnapshot::AddCapsule(const FTransform& T, double Radius, double Half)
        {
            constexpr int32 Segments=10, Steps=4;
            TArray<TArray<FVector>> Rings;
            for (int32 Top=0;Top<2;++Top) for (int32 I=0;I<=Steps;++I)
            {
                const double Lat=(Top ? double(I) : double(I-Steps))/Steps*UE_DOUBLE_HALF_PI, Ring=Radius*FMath::Cos(Lat);
                const double Z=Radius*FMath::Sin(Lat)+(Top ? Half : -Half);
                TArray<FVector>& Row=Rings.AddDefaulted_GetRef();
                for (int32 S=0;S<Segments;++S) Row.Add(T.TransformPosition(FVector(Ring*FMath::Cos(UE_DOUBLE_TWO_PI*S/Segments),Ring*FMath::Sin(UE_DOUBLE_TWO_PI*S/Segments),Z)));
            }
            for (int32 R=0;R+1<Rings.Num();++R) for (int32 S=0;S<Segments;++S)
            {
                const int32 N=(S+1)%Segments;
                AddFacing(T.GetLocation(),Rings[R][S],Rings[R][N],Rings[R+1][N]);
                AddFacing(T.GetLocation(),Rings[R][S],Rings[R+1][N],Rings[R+1][S]);
            }
        }
void FSkateCollisionSnapshot::AddHull(const FKConvexElem& Hull, const FTransform& T,const TArray<int32>& Indices)
        {
            if (Hull.VertexData.IsEmpty()) return;
            TArray<FVector> P; FVector Centre=FVector::ZeroVector;
            for (const FVector& V : Hull.VertexData) Centre+=P.Add_GetRef(T.TransformPosition(V));
            Centre/=P.Num();
            for (int32 I=0;I+2<Indices.Num();I+=3)
                if (P.IsValidIndex(Indices[I]) && P.IsValidIndex(Indices[I+1]) && P.IsValidIndex(Indices[I+2]))
                    AddFacing(Centre,P[Indices[I]],P[Indices[I+1]],P[Indices[I+2]]);
        }

void FSkateCollisionSnapshot::AddSurface(const USkateCollisionMeshData& Data,const FTransform& T,
    const UStaticMeshComponent* Component,TConstArrayView<USkateCollisionAsset*> Catalogs)
{
    for(int32 I=0;I+2<Data.Indices.Num()&&!Full();I+=3)
    {
        FVector P[3];
        for(int32 K=0;K<3;++K)P[K]=T.TransformPosition(FVector(Data.Positions[Data.Indices[I+K]]));
        const FVector Authored=T.TransformVectorNoScale(FVector(FVector3f(Data.TangentZ[Data.Indices[I]])));
        if(FVector::DotProduct(FVector::CrossProduct(P[1]-P[0],P[2]-P[0]),Authored)<0)Swap(P[1],P[2]);
        CurrentMaterial=ResolveMaterial(Component,Data.TriangleMaterialSlots[I/3],Catalogs);
        Add(P[0],P[1],P[2]);
    }
}
FString FSkateCollisionDiagnostics::Summary() const
{
    return FString::Printf(TEXT("%d triangles, %d material overrides, %d nonzero surfaces, %d missing meshes, %d unsupported components, generation %llu"),
        TriangleCount,MaterialOverrideCount,NonzeroSurfaceCount,MissingCatalogCount,UnsupportedComponentCount,
        static_cast<unsigned long long>(SceneGeneration));
}
bool SkateGatherCollisionWorld(UWorld* World,ACharacter* Rider,FVector Centre,FVector Spawn,float Yaw,
    USkateRailSubsystem* Rails,TConstArrayView<USkateCollisionAsset*> Catalogs,FSkateCollisionSnapshot& Snapshot,
    double& Reach,FSkateCollisionDiagnostics& Diagnostics,uint64 SceneGeneration)
{
    check(IsInGameThread());Diagnostics={};Diagnostics.SceneGeneration=SceneGeneration;
    if(!World){Diagnostics.Errors.Add(TEXT("Missing collision world"));return false;}
    for(const auto* Catalog:Catalogs)if(Catalog&&Catalog->FormatVersion!=1)Diagnostics.Errors.Add(Catalog->GetPathName()+TEXT(": unsupported collision catalog format"));
    if(!Diagnostics.Okay())return false;
    TSet<UStaticMesh*> Missing;
    double Radius=0;
    for(const double Try:{10000.,6000.,3500.,2000.})
    {
        Radius=Try;Snapshot.Region=FBox(Centre-FVector(Radius),Centre+FVector(Radius));
        Snapshot.Points.Reset();Snapshot.Materials.Reset();Snapshot.Rails.Reset();
        // Errors from a discarded larger region must not reject the final region.
        Diagnostics.Errors.Reset();Diagnostics.Warnings.Reset();Diagnostics.UnsupportedComponentCount=0;Missing.Reset();
        for(TObjectIterator<UStaticMeshComponent> It;It&&!Snapshot.Full();++It)
        {
            UStaticMeshComponent* C=*It;if(!Eligible(C,World,Rider,Snapshot.Region))continue;
            if(Cast<USplineMeshComponent>(C))
            {
                ++Diagnostics.UnsupportedComponentCount;
                Diagnostics.Warnings.AddUnique(C->GetPathName()+TEXT(": spline deformation is not included; the former base-mesh snapshot is retained"));
            }
            for(int32 Slot=0;Slot<C->GetNumMaterials();++Slot)
                if(const UMaterialInterface* M=C->GetMaterial(Slot))if(M->GetPhysicalMaterialMask())
                    Diagnostics.Warnings.AddUnique(C->GetPathName()+TEXT(": physical material masks are unsupported; the section physical material is used"));
            UStaticMesh* Mesh=C->GetStaticMesh();UBodySetup* Body=Mesh?Mesh->GetBodySetup():nullptr;
            if(!Body)continue;
            const USkateCollisionMeshData* Data=FindMesh(Catalogs,Mesh);
            const bool Surface=Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple;
            const auto& Geom=Body->AggGeom;
            const bool NeedsBakedConvex=Geom.ConvexElems.ContainsByPredicate([](const FKConvexElem& H){return !H.VertexData.IsEmpty()&&H.IndexData.IsEmpty();});
            if((Surface||NeedsBakedConvex)&&!Data)
            {
                if(!Missing.Contains(Mesh))Diagnostics.Errors.Add(TEXT("Missing cooked skate collision data for ")+Mesh->GetPathName());
                Missing.Add(Mesh);continue;
            }
            if((Surface||NeedsBakedConvex)&&Data&&(Data->FormatVersion!=1||Data->SourceLODForCollision!=Mesh->LODForCollision||Data->SourceBodySetupGuid!=Body->BodySetupGuid||Data->ConvexIndices.Num()!=Geom.ConvexElems.Num()||(Surface&&Data->Indices.IsEmpty())))
            {Diagnostics.Errors.AddUnique(TEXT("Stale cooked skate collision data for ")+Mesh->GetPathName()+TEXT("; rebake catalog"));continue;}
            for(const FTransform& T:Instances(C,Snapshot.Region))
            {
                Snapshot.CurrentMaterial=ResolveMaterial(C,INDEX_NONE,Catalogs);
                if(Surface){Snapshot.AddSurface(*Data,T,C,Catalogs);continue;}
                for(const FKBoxElem& E:Geom.BoxElems)Snapshot.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5);
                for(const FKSphereElem& E:Geom.SphereElems)Snapshot.AddCapsule(E.GetTransform()*T,E.Radius,0);
                for(const FKSphylElem& E:Geom.SphylElems)Snapshot.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5);
                for(int32 I=0;I<Geom.ConvexElems.Num();++I)
                {
                    const FKConvexElem& E=Geom.ConvexElems[I];
                    if(E.VertexData.IsEmpty())continue;
                    const TArray<int32>& Indices=E.IndexData.IsEmpty()?Data->ConvexIndices[I].Indices:E.IndexData;
                    Snapshot.AddHull(E,E.GetTransform()*T,Indices);
                }
                if(!Geom.TaperedCapsuleElems.IsEmpty()||!Geom.LevelSetElems.IsEmpty()||!Geom.SkinnedLevelSetElems.IsEmpty()||!Geom.MLLevelSetElems.IsEmpty()||!Geom.SkinnedTriangleMeshElems.IsEmpty())
                    Diagnostics.Errors.AddUnique(TEXT("Unsupported body setup shapes in ")+Mesh->GetPathName());
            }
        }
        if(!Snapshot.Full())break;
    }
    Diagnostics.MissingCatalogCount=Missing.Num();Diagnostics.TriangleCount=Snapshot.Num();
    for(const auto& M:Snapshot.Materials)
    {Diagnostics.MaterialOverrideCount+=M.bOverride?1:0;Diagnostics.NonzeroSurfaceCount+=M.Surface!=0?1:0;}
    // Other component classes have no baked static-mesh representation.
    for(TObjectIterator<UPrimitiveComponent> It;It;++It)
        if(!Cast<UStaticMeshComponent>(*It)&&It->GetWorld()==World&&It->GetOwner()!=Rider&&It->IsRegistered()
            &&It->IsCollisionEnabled()&&It->GetCollisionResponseToChannel(ECC_Pawn)==ECR_Block&&It->Bounds.GetBox().Intersect(Snapshot.Region))
        {++Diagnostics.UnsupportedComponentCount;Diagnostics.Warnings.Add(It->GetPathName()+TEXT(": not a static/instanced mesh; collision is not included"));}
    if(Snapshot.Num()==0)Diagnostics.Errors.Add(TEXT("Collision snapshot contains no triangles"));
    if(Snapshot.Full())Diagnostics.Errors.Add(TEXT("Collision snapshot exceeds triangle budget at minimum radius"));
    if(!Diagnostics.Okay())return false;
    Reach=Radius*.6;
    if(Rails)for(const FSkateRail& Rail:Rails->Rails)if(Rail.Bounds.Intersect(Snapshot.Region)&&Rail.Points.Num()>=2)
    {
        TArray<FVector3f>& Line=Snapshot.Rails.AddDefaulted_GetRef();
        for(const FVector& P:Rail.Points)Line.Add(FVector3f(ToNative(P)));
    }
    Snapshot.Spawn=FVector3f(ToNative(Spawn));Snapshot.Heading=-FMath::DegreesToRadians(Yaw);
    return true;
}
namespace
{
    float SnapshotScalar(float V)
    {return float(double(FMath::RoundToInt64(double(V)*10000000.))/10000000.);}
    atelier::skate::Vec3 SnapshotPoint(FVector3f P)
    {return {SnapshotScalar(P.X),SnapshotScalar(P.Y),SnapshotScalar(P.Z)};}
}
atelier::skate::GameplayWorldSnapshot SkateNativeCollisionSnapshot(const FSkateCollisionSnapshot& S)
{
    atelier::skate::GameplayWorldSnapshot Out;Out.triangles.reserve(S.Num());
    for(int32 I=0;I<S.Points.Num();I+=3)
        Out.triangles.push_back({SnapshotPoint(S.Points[I]),SnapshotPoint(S.Points[I+1]),SnapshotPoint(S.Points[I+2])});
    for(const auto& Rail:S.Rails)
    {
        auto& Line=Out.rails.emplace_back();Line.reserve(Rail.Num());
        for(const auto& P:Rail){const auto V=SnapshotPoint(P);Line.push_back({V.x,V.y,V.z});}
    }
    if(S.Materials.ContainsByPredicate([](const auto& M){return M.bOverride;}))
        for(const auto& M:S.Materials)
            Out.triangle_materials.push_back(M.bOverride?std::optional<atelier::skate::ContactMaterial>(atelier::skate::ContactMaterial{M.StaticFriction,M.DynamicFriction,M.Restitution}):std::nullopt);
    if(S.Materials.ContainsByPredicate([](const auto& M){return M.Surface!=0;}))
        for(const auto& M:S.Materials)Out.triangle_surfaces.push_back(M.Surface);
    return Out;
}
bool SkateCollisionSnapshotsEqual(const FSkateCollisionSnapshot& A,const FSkateCollisionSnapshot& B,FString& Difference)
{
    auto Same=[](const auto& X,const auto& Y){return X.Num()==Y.Num()&&(X.IsEmpty()||FMemory::Memcmp(X.GetData(),Y.GetData(),X.Num()*sizeof(X[0]))==0);};
    if(!Same(A.Points,B.Points)){Difference=TEXT("raw triangle words/order differ");return false;}
    if(A.Rails.Num()!=B.Rails.Num()){Difference=TEXT("rail count differs");return false;}
    for(int32 I=0;I<A.Rails.Num();++I)if(!Same(A.Rails[I],B.Rails[I])){Difference=TEXT("rail words/order differ");return false;}
    if(FMemory::Memcmp(&A.Spawn,&B.Spawn,sizeof(A.Spawn))||FMemory::Memcmp(&A.Heading,&B.Heading,sizeof(A.Heading)))
    {Difference=TEXT("spawn/heading words differ");return false;}
    if(A.Materials.Num()!=B.Materials.Num()){Difference=TEXT("material count differs");return false;}
    for(int32 I=0;I<A.Materials.Num();++I)
    {
        const auto& X=A.Materials[I];const auto& Y=B.Materials[I];
        if(X.bOverride!=Y.bOverride||X.Surface!=Y.Surface||FMemory::Memcmp(&X.StaticFriction,&Y.StaticFriction,3*sizeof(float)))
        {Difference=TEXT("material/surface words differ");return false;}
    }
    const auto X=SkateNativeCollisionSnapshot(A),Y=SkateNativeCollisionSnapshot(B);
    if(X.triangles.size()!=Y.triangles.size()||(!X.triangles.empty()&&std::memcmp(X.triangles.data(),Y.triangles.data(),X.triangles.size()*sizeof(X.triangles[0]))))
    {Difference=TEXT("seven-decimal published triangle words differ");return false;}
    Difference.Reset();return true;
}

namespace
{
    template<class T> void Put(FArchive& W,const T& Value)
    {W.Serialize(const_cast<T*>(&Value),sizeof(T));}
    void PutString(FArchive& W,FString Value){W<<Value;}
    void PutVector(FArchive& W,const FVector& V){Put(W,V.X);Put(W,V.Y);Put(W,V.Z);}
    void PutTransform(FArchive& W,const FTransform& T)
    {
        PutVector(W,T.GetTranslation());PutVector(W,T.GetScale3D());
        const FQuat Q=T.GetRotation();Put(W,Q.X);Put(W,Q.Y);Put(W,Q.Z);Put(W,Q.W);
    }
    void PutProfile(FArchive& W,const FSkateCollisionTriangleMaterial& M)
    {Put(W,M.bOverride);Put(W,M.StaticFriction);Put(W,M.DynamicFriction);Put(W,M.Restitution);Put(W,M.Surface);}
    void PutBody(FArchive& W,const UBodySetup& Body)
    {
        Put(W,Body.BodySetupGuid);const auto Flag=Body.GetCollisionTraceFlag();Put(W,Flag);
        const auto& G=Body.AggGeom;
        Put(W,G.BoxElems.Num());for(const auto& E:G.BoxElems){PutTransform(W,E.GetTransform());Put(W,E.X);Put(W,E.Y);Put(W,E.Z);}
        Put(W,G.SphereElems.Num());for(const auto& E:G.SphereElems){PutTransform(W,E.GetTransform());Put(W,E.Radius);}
        Put(W,G.SphylElems.Num());for(const auto& E:G.SphylElems){PutTransform(W,E.GetTransform());Put(W,E.Radius);Put(W,E.Length);}
        Put(W,G.ConvexElems.Num());for(const auto& E:G.ConvexElems)
        {
            PutTransform(W,E.GetTransform());Put(W,E.VertexData.Num());for(const auto& V:E.VertexData)PutVector(W,V);
            Put(W,E.IndexData.Num());for(int32 I:E.IndexData)Put(W,I);
        }
        Put(W,G.TaperedCapsuleElems.Num());Put(W,G.LevelSetElems.Num());Put(W,G.SkinnedLevelSetElems.Num());
        Put(W,G.MLLevelSetElems.Num());Put(W,G.SkinnedTriangleMeshElems.Num());
    }
}
FSkateCollisionSceneState SkateCaptureCollisionSceneState(UWorld* World,ACharacter* Rider,const FBox& Region,
    USkateRailSubsystem* Rails,TConstArrayView<USkateCollisionAsset*> Catalogs)
{
    check(IsInGameThread());FSkateCollisionSceneState Out;FMemoryWriter W(Out.Bytes);
    PutVector(W,Region.Min);PutVector(W,Region.Max);Put(W,Catalogs.Num());
    for(const auto* Catalog:Catalogs)
    {
        Put(W,reinterpret_cast<UPTRINT>(Catalog));if(!Catalog)continue;
        Put(W,Catalog->FormatVersion);Put(W,Catalog->Revision);Put(W,Catalog->Meshes.Num());
        // Validated baked geometry is immutable between revisions. Compare
        // pointers directly for editable Blueprint membership changes, without
        // rebuilding large path/hash signatures on each scene scan.
        for(const USkateCollisionMeshData* Data:Catalog->Meshes)
            Put(W,reinterpret_cast<UPTRINT>(Data));
        Put(W,Catalog->SurfaceProfiles.Num());for(const auto& P:Catalog->SurfaceProfiles)
        {
            Put(W,reinterpret_cast<UPTRINT>(P.PhysicalMaterial.Get()));Put(W,P.PackedSurface);Put(W,P.bOverrideContactMaterial);
            Put(W,P.StaticFriction);Put(W,P.DynamicFriction);Put(W,P.Restitution);
        }
    }
    TSet<const UBodySetup*> Bodies;
    for(TObjectIterator<UStaticMeshComponent> It;It;++It)
    {
        UStaticMeshComponent* C=*It;if(!Eligible(C,World,Rider,Region))continue;
        Put(W,reinterpret_cast<UPTRINT>(C));PutTransform(W,C->GetComponentTransform());
        PutVector(W,C->Bounds.GetBox().Min);PutVector(W,C->Bounds.GetBox().Max);
        UStaticMesh* Mesh=C->GetStaticMesh();Put(W,reinterpret_cast<UPTRINT>(Mesh));
        UBodySetup* Body=Mesh?Mesh->GetBodySetup():nullptr;Put(W,reinterpret_cast<UPTRINT>(Body));
        if(Body)
        {
            const bool First=!Bodies.Contains(Body);Put(W,First);
            if(First){Bodies.Add(Body);PutBody(W,*Body);}
        }
        if(Mesh)Put(W,Mesh->LODForCollision);
        const auto Transforms=Instances(C,Region);Put(W,Transforms.Num());for(const auto& T:Transforms)PutTransform(W,T);
        PutProfile(W,ResolveMaterial(C,INDEX_NONE,Catalogs));Put(W,C->GetNumMaterials());
        for(int32 Slot=0;Slot<C->GetNumMaterials();++Slot)PutProfile(W,ResolveMaterial(C,Slot,Catalogs));
    }
    Put(W,Rails?Rails->Rails.Num():0);
    if(Rails)for(const auto& Rail:Rails->Rails)if(Rail.Bounds.Intersect(Region)&&Rail.Points.Num()>=2)
    {
        PutString(W,Rail.Id.ToString());PutVector(W,Rail.Bounds.Min);PutVector(W,Rail.Bounds.Max);
        Put(W,Rail.Points.Num());for(const auto& P:Rail.Points)PutVector(W,P);
    }
    return Out;
}
bool FSkateCollisionSceneTracker::Poll(UWorld* World,ACharacter* Rider,const FBox& Region,USkateRailSubsystem* Rails,
    TConstArrayView<USkateCollisionAsset*> Catalogs,double NowSeconds)
{
    check(IsInGameThread());
    if(State_.IsSet()&&NowSeconds>=LastScanSeconds_&&NowSeconds-LastScanSeconds_<FMath::Max(0.,ScanPeriodSeconds))return false;
    LastScanSeconds_=NowSeconds;
    auto Next=SkateCaptureCollisionSceneState(World,Rider,Region,Rails,Catalogs);
    if(State_.IsSet()&&State_.GetValue()==Next)return false;
    State_=MoveTemp(Next);++Generation_;return true;
}
void FSkateCollisionSceneTracker::Reset()
{State_.Reset();LastScanSeconds_=-DBL_MAX;Generation_=0;}

bool SkateValidateNativeCollisionSnapshot(const FSkateCollisionSnapshot& Snapshot,FString& Error)
{
    auto Native=SkateNativeCollisionSnapshot(Snapshot);
    return RunNativeCollisionValidation([Native=std::move(Native)](FString& WorkerError) mutable
    {
        std::optional<atelier::skate::PreparedGameplayWorld> Prepared;std::string Message;
        const bool Okay=atelier::skate::BuildGameplayWorld(Native,{},Prepared,Message);
        WorkerError=UTF8_TO_TCHAR(Message.c_str());return Okay;
    },Error);
}

void FSkateCollisionSceneTracker::AcceptSnapshot(UWorld* World,ACharacter* Rider,const FBox& Region,
    USkateRailSubsystem* Rails,TConstArrayView<USkateCollisionAsset*> Catalogs,double NowSeconds)
{
    check(IsInGameThread());State_=SkateCaptureCollisionSceneState(World,Rider,Region,Rails,Catalogs);LastScanSeconds_=NowSeconds;
}

bool SkateValidateCollisionMaterialTransport(FString& Error)
{
    return RunNativeCollisionValidation([](FString& Error)
    {
        using namespace atelier::skate;
        const ContactMaterial Stock{.8f,.6f,.125f},Override{.375f,.25f,.5f};
        GameplayWorldSnapshot Input;
        Input.triangles.push_back({Vec3{0,0,0},Vec3{0,0,1},Vec3{1,0,0}});
        Input.triangles.push_back({Vec3{2,0,0},Vec3{2,0,1},Vec3{3,0,0}});
        std::optional<PreparedGameplayWorld> Out;std::string Message;
        auto Require=[&](bool Okay,const TCHAR* Text){if(!Okay)Error=Text;return Okay;};
        auto Same=[](ContactMaterial A,ContactMaterial B){return std::memcmp(&A.static_friction,&B.static_friction,sizeof(float))==0
            &&std::memcmp(&A.dynamic_friction,&B.dynamic_friction,sizeof(float))==0&&std::memcmp(&A.restitution,&B.restitution,sizeof(float))==0;};
        if(!BuildGameplayWorld(Input,Stock,Out,Message)){Error=UTF8_TO_TCHAR(Message.c_str());return false;}
        const char* Diagnostic=nullptr;const auto* Default=Out->collision.Metadata(Diagnostic);
        if(!Require(Default&&Default->packed_surfaces==std::vector<uint16>({0,0}),TEXT("default surface metadata changed")))return false;
        for(const auto& T:Out->collision.Triangles())if(!Require(T.tag==0&&Same(T.material,Stock),TEXT("default stock contact material changed")))return false;
        constexpr uint16 Packed=uint16((8u<<7)|17u);
        Input.triangle_materials={std::nullopt,Override};Input.triangle_surfaces={0,Packed};
        if(!BuildGameplayWorld(Input,Stock,Out,Message)){Error=UTF8_TO_TCHAR(Message.c_str());return false;}
        const auto& Triangles=Out->collision.Triangles();const auto* Metadata=Out->collision.Metadata(Diagnostic);
        if(!Require(Metadata&&Metadata->packed_surfaces==Input.triangle_surfaces&&Triangles[0].tag==0&&Triangles[1].tag==Packed
            &&Same(Triangles[0].material,Stock)&&Same(Triangles[1].material,Override),TEXT("per-triangle material/surface publication differs")))return false;
        if(!Require((Triangles[1].tag&0x7f)==17&&((Triangles[1].tag>>7)&31)==8,TEXT("packed surface material/category bits changed")))return false;
        Input.triangle_materials.pop_back();
        if(!Require(!BuildGameplayWorld(Input,Stock,Out,Message)&&Same(Out->collision.Triangles()[1].material,Override),TEXT("mismatched material count was accepted or mutated output")))return false;
        Input.triangle_materials={std::nullopt,Override};Input.triangle_surfaces.pop_back();
        if(!Require(!BuildGameplayWorld(Input,Stock,Out,Message),TEXT("mismatched surface count was accepted")))return false;
        Input.triangle_surfaces={0,Packed};Input.triangle_materials[1]->static_friction=std::numeric_limits<float>::infinity();
        if(!Require(!BuildGameplayWorld(Input,Stock,Out,Message)&&Same(Out->collision.Triangles()[1].material,Override),TEXT("non-finite override was accepted or mutated output")))return false;
        Error.Reset();return true;
    },Error);
}
