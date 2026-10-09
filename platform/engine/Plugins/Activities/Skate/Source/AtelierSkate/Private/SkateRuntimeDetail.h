#pragma once
// Shared by SkateRuntime.cpp and SkateRetarget.cpp: the adapter's helpers, the simulation worker thread and
// FSkateRuntime (one source, split in two).
#include "SkateComponent.h"
#include "Simulation/GameplaySession.h"
#include "Simulation/GroundSurfaceRuntime.h"
#include "Simulation/HostScalar.h"
#include "SkatePad.h"
#include <deque>
#include <limits>
#include <cfenv>
#include "Engine/Engine.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateMotionAdapter.h"
#include "SkateRuntimeAdapter.h"
#include "SkateFeel.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/HitResult.h"
#include "Materials/MaterialInterface.h"
#include "Engine/SkeletalMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "Chaos/TriangleMeshImplicitObject.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "HAL/Runnable.h"
#include "HAL/Event.h"
#include "HAL/RunnableThread.h"
#include "Containers/Queue.h"
#include <atomic>
#include "Misc/Paths.h"
#include "StaticMeshResources.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "TwoBoneIK.h"
#include "HAL/IConsoleManager.h"
#include "UObject/UObjectIterator.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/ObjectKey.h"
#include "Async/Async.h"
#include "Async/ParallelFor.h"
#include "Ride/RideClipPlayer.h"
#include "Ride/RidePoseMeasure.h"
#include "Ride/RideTuning.h"
#include "Ride/RidePhysicalRider.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"

namespace SkateRuntimeDetail
{
    // Grab grip, tunable live: knuckle lift and outset from the deck edge (in finger widths, the rider's knuckle
    // spacing), finger flexion (MCP, PIP, DIP, cumulative from the hand's axis), thumb swing towards the fingers and
    // thumb flexion (degrees).
    extern TAutoConsoleVariable<FString> CVarSkateGrip;
    // The retargeted limbs against this rider's own body and the ground (RetargetRiderPose): how far each forearm and
    // hand stays out of its pelvis, spine, chest and thighs, and how far above the ground under it each foot's sole
    // stays (cm; below 0 off).
    extern TAutoConsoleVariable<float> CVarSkateArmClear;
    extern TAutoConsoleVariable<float> CVarSkateFootGround;
    // The simulation thread steps in lockstep with the game: each frame waits for the last frame's step, so no frame's
    // step or controls are skipped and the same controls replay the same ride. Its collision rebuilds install on the
    // frame after they start.
    extern TAutoConsoleVariable<int32> CVarSkateLockstep;
    extern TAutoConsoleVariable<int32> CVarSkateSurfaceDebug;
    // QA: complex-as-simple meshes read their cooked collision triangles even where their render data keeps CPU copies.
    extern TAutoConsoleVariable<int32> CVarSkateCookedSurface;
    // A successful pump shows as a trick: one rise of the rider on the ground that adds this much speed
    // by the player's crouch (m/s; the simulation's own timed pumps add 2-3, mistimed ones about .3); from the next ride.
    extern TAutoConsoleVariable<float> CVarSkatePumpTrick;
    // QA: the ride's session fails on its next step, as a session error would (the bail, the relaunch, the get-up).
    extern TAutoConsoleVariable<int32> CVarSkateFailSimulation;
    inline bool Lockstep()
    {
        const int32 V=CVarSkateLockstep.GetValueOnGameThread();
        return V>0||(V<0&&(FApp::UseFixedTimeStep()||(GEngine&&GEngine->bUseFixedFrameRate)));
    }

    // Match the standalone runtime's floating environment (the defaults, denormals flushed to zero), and restore
    // the caller's complete environment before returning to Unreal.
    class FScopedSimulationFloatEnvironment
    {
    public:
        FScopedSimulationFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            SavedOkay_=std::fegetenv(&Saved_)==0;
            Ready_=SavedOkay_&&std::fesetenv(FE_DFL_ENV)==0&&atelier::skate::FlushDenormalsToZero();
        }
        ~FScopedSimulationFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            if(SavedOkay_)std::fesetenv(&Saved_);
        }
        FScopedSimulationFloatEnvironment(const FScopedSimulationFloatEnvironment&)=delete;
        FScopedSimulationFloatEnvironment& operator=(const FScopedSimulationFloatEnvironment&)=delete;
        bool IsReady() const {return Ready_;}
    private:
        std::fenv_t Saved_{};
        bool SavedOkay_=false,Ready_=false;
    };

    // The simulation left/up/forward metres -> UE forward/right/up centimetres (change handedness).
    inline FVector FromSimulation(const FVector& V) { return FVector(V.Z, -V.X, V.Y) * 100.; }
    inline FVector ToSimulation(const FVector& V) { return FVector(-V.Y, V.Z, V.X) * .01; }
    inline FTransform MatrixValue(const atelier::skate::Mat4& M)
    {
        auto Axis=[&](int I){return FVector(M[I][2],-M[I][0],M[I][1]);};
        return FTransform(FMatrix(FPlane(Axis(2),0),FPlane(-Axis(0),0),FPlane(Axis(1),0),FPlane(Axis(3)*100.,1)));
    }
    inline atelier::skate::Vec3 SimulationVector(FVector V)
    {
        const FVector P=ToSimulation(V);
        const auto Scalar=[](double Value)
        {
            float Result=std::numeric_limits<float>::quiet_NaN();std::string Error;
            atelier::skate::ConvertHostScalar(Value,Result,Error);return Result;
        };
        return {Scalar(P.X),Scalar(P.Y),Scalar(P.Z)};
    }
    inline FString TrickLabel(FString Name)
    {
        Name.RemoveFromStart(TEXT("ID_TRICK_"));
        for (const TCHAR* Family : {TEXT("GROUND_TRICK_"),TEXT("FLIP_"),TEXT("GRIND_"),TEXT("GRAB_")}) Name.RemoveFromStart(Family);
        TArray<FString> Words; Name.ParseIntoArray(Words,TEXT("_"),true);
        for (FString& Word : Words)
        {
            if (Word==TEXT("N")) Word=TEXT("Nollie");
            else if (Word!=TEXT("FS") && Word!=TEXT("BS")) { Word=Word.ToLower(); if (!Word.IsEmpty()) Word[0]=FChar::ToUpper(Word[0]); }
        }
        // The shove-its as the game shows them (its IDs say "Pop Shuvit"; the 360s drop the "Pop").
        return FString::Join(Words,TEXT(" ")).Replace(TEXT("50 50"),TEXT("50-50")).Replace(TEXT("360 Pop Shuvit"),TEXT("360 Shove-it"))
            .Replace(TEXT("Pop Shuvit"),TEXT("Pop Shove-it"));
    }
    // A park fits inside the snapshot's inner cube. Keep that cube at the park origin, so
    // skating between its corners does not rebuild identical collision on the game thread.
    // The 10 m cell a point is in (its centre): away from a park the world is snapshotted around the cell, so a place
    // always gets the same world, whatever the session gathered before (a world's triangles and their order move
    // the simulation's contacts by fractions of a millimetre, which a long ride grows into a different line).
    inline FVector GridCell(const FVector& Position)
    {
        return FVector(FMath::GridSnap(Position.X,1000.),FMath::GridSnap(Position.Y,1000.),FMath::GridSnap(Position.Z,1000.));
    }
    inline FVector SnapshotCentre(UWorld* World, const FVector& Position)
    {
        // Decided for the cell, not the point: the two sides of a park's 60 m edge inside one cell agree.
        const FVector Cell=GridCell(Position);
        for (TActorIterator<AActor> It(World); It; ++It)
            if (It->ActorHasTag(TEXT("SkatePark")) && (Cell-It->GetActorLocation()).GetAbsMax()<=6000.f)
                return It->GetActorLocation();
        return Cell;
    }

    /** A static mesh's collision LOD as plain data: three mesh-space points per triangle and the authored normal (the
     *  first corner's tangent Z) and material slot of each. Copied on the game thread, so a worker never reads render
     *  data that LOD streaming may release. */
    struct FMeshSurface { TArray<FVector3f> Points, Normals; TArray<uint16> Slots; };
    using FMeshSurfaceRef=TSharedPtr<const FMeshSurface,ESPMode::ThreadSafe>;

    /** The surface's name for QA lines (Wood), "none" for None. */
    inline FString SurfaceName(ESkateSurface Surface)
    {
        return Surface==ESkateSurface::None ? FString(TEXT("none")) : StaticEnum<ESkateSurface>()->GetNameStringByValue(int64(Surface));
    }
    /** A mesh or material name as the surface tables key it: without a leading SM_, MI_ or M_. */
    inline FString SurfaceKey(FString Name)
    {
        if (!Name.RemoveFromStart(TEXT("SM_")) && !Name.RemoveFromStart(TEXT("MI_"))) Name.RemoveFromStart(TEXT("M_"));
        return Name;
    }
    /** The surface a SkateSurface.<Surface> tag on the component or its actor names, or the mesh's in SurfaceMeshes. */
    inline ESkateSurface ComponentSurface(const UStaticMeshComponent* C, const UStaticMesh* Mesh, const USkateSettings& Settings)
    {
        auto Tagged=[](const TArray<FName>& Tags)
        {
            for (const FName& Tag : Tags)
            {
                FString Name=Tag.ToString();
                if (!Name.RemoveFromStart(TEXT("SkateSurface."))) continue;
                const int64 Value=StaticEnum<ESkateSurface>()->GetValueByNameString(Name);
                if (Value!=INDEX_NONE) return ESkateSurface(Value);
            }
            return ESkateSurface::None;
        };
        ESkateSurface Surface=Tagged(C->ComponentTags);
        if (Surface==ESkateSurface::None && C->GetOwner()) Surface=Tagged(C->GetOwner()->Tags);
        if (Surface==ESkateSurface::None && Mesh)
            if (const ESkateSurface* Found=Settings.SurfaceMeshes.Find(SurfaceKey(Mesh->GetName()))) Surface=*Found;
        return Surface;
    }
    /** A triangle's packed simulation surface: the authored ground profile it rides (1 smooth, 2 rough, 3 slow, 5 very
     *  slow) << 7 | the surface itself, which the session reports back for sounds. */
    inline uint16 PackSurface(ESkateSurface Surface)
    {
        uint16 Physics=1;
        switch (Surface)
        {
        case ESkateSurface::Asphalt: case ESkateSurface::Stone: Physics=2; break;
        case ESkateSurface::Dirt: Physics=3; break;
        case ESkateSurface::Grass: case ESkateSurface::Sand: Physics=5; break;
        default: break;
        }
        return uint16(Physics<<7 | uint8(Surface));
    }
    /** The packed surface of a component's material slot: its tag or mesh surface, else its material's, else the default. */
    inline uint16 SlotSurface(const UStaticMeshComponent* C, int32 Slot, ESkateSurface Override, const USkateSettings& Settings)
    {
        ESkateSurface Surface=Override;
        if (Surface==ESkateSurface::None)
            if (const UMaterialInterface* Material=C->GetMaterial(Slot))
                if (const ESkateSurface* Found=Settings.SurfaceMaterials.Find(SurfaceKey(Material->GetName()))) Surface=*Found;
        return PackSurface(Surface==ESkateSurface::None ? Settings.DefaultSurface : Surface);
    }

    /** The surface from the mesh's cooked collision triangles: what Chaos itself collides with, kept in a cooked build
     *  whether or not the render data keeps CPU copies. Cooking turns Unreal's render winding (clockwise seen from the
     *  front) into the physics one, so (B-A)x(C-A) of a cooked triangle points out of its front: that stands in for
     *  the authored normal. The slots are its sections'. Null when the body has none. */
    inline TSharedPtr<FMeshSurface,ESPMode::ThreadSafe> CollisionSurface(UStaticMesh* Mesh)
    {
        const UBodySetup* Body=Mesh->GetBodySetup();
        if (!Body || Body->TriMeshGeometries.IsEmpty()) return nullptr;
        auto Surface=MakeShared<FMeshSurface,ESPMode::ThreadSafe>();
        for (const Chaos::FTriangleMeshImplicitObjectPtr& TriMesh : Body->TriMeshGeometries)
        {
            if (!TriMesh) continue;
            const auto& Particles=TriMesh->Particles();
            const Chaos::FTrimeshIndexBuffer& Elements=TriMesh->Elements();
            auto AddAll=[&](const auto& Triangles)
            {
                for (int32 T=0; T<Triangles.Num(); ++T)
                {
                    const FVector3f P[3]={FVector3f(Particles.GetX(Triangles[T][0])),FVector3f(Particles.GetX(Triangles[T][1])),FVector3f(Particles.GetX(Triangles[T][2]))};
                    Surface->Points.Append(P,3);
                    Surface->Normals.Add(FVector3f::CrossProduct(P[1]-P[0],P[2]-P[0]).GetSafeNormal());
                    Surface->Slots.Add(TriMesh->GetMaterialIndex(T));
                }
            };
            if (Elements.RequiresLargeIndices()) AddAll(Elements.GetLargeIndexBuffer()); else AddAll(Elements.GetSmallIndexBuffer());
        }
        if (Surface->Slots.IsEmpty()) return nullptr;
        return Surface;
    }

    /** The mesh's surface, copied once per mesh and kept (game thread): its collision LOD's render triangles, or in a
     *  cooked build without CPU copies of them its cooked collision triangles. Null when it has neither. */
    inline FMeshSurfaceRef MeshSurface(UStaticMesh* Mesh)
    {
        check(IsInGameThread());
        static TMap<TObjectKey<UStaticMesh>,FMeshSurfaceRef> Cache;
        const TObjectKey<UStaticMesh> Key(Mesh);
        if (const FMeshSurfaceRef* Found=Cache.Find(Key)) return *Found;
        auto Collision=[&]() -> FMeshSurfaceRef
        {
            const FMeshSurfaceRef Surface=CollisionSurface(Mesh);
            if (Surface) { UE_LOG(LogTemp,Log,TEXT("SKATE surface %s: %d cooked collision triangles"),*Mesh->GetName(),Surface->Slots.Num()); }
            else { UE_LOG(LogTemp,Warning,TEXT("SKATE surface %s: no CPU render data and no cooked collision triangles; the board does not collide with it"),*Mesh->GetName()); }
            return Cache.Add(Key,Surface);
        };
        if (CVarSkateCookedSurface.GetValueOnGameThread()>0) return Collision();
        // A cooked build keeps the CPU copy of a mesh's render buffers only when the mesh allows CPU access (the engine's
        // own rule, FStaticMeshLODResources::SerializeBuffers). Without it the buffers still report their counts, but the
        // index view is empty and the vertex pointer is not to be read.
        if (FPlatformProperties::RequiresCookedData() && !Mesh->bAllowCPUAccess) return Collision();
        if (!Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return Collision();
        const auto& LODs=Mesh->GetRenderData()->LODResources;
        const FStaticMeshLODResources& LOD=LODs[FMath::Clamp(Mesh->LODForCollision,0,LODs.Num()-1)];
        const FPositionVertexBuffer& Positions=LOD.VertexBuffers.PositionVertexBuffer;
        const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();   // the indices held, not the count it reports
        if (!Positions.GetVertexData() || Positions.GetNumVertices()==0 || Indices.Num()<3) return Collision();
        auto Surface=MakeShared<FMeshSurface,ESPMode::ThreadSafe>();
        Surface->Points.Reserve(Indices.Num()/3*3); Surface->Normals.Reserve(Indices.Num()/3);
        Surface->Slots.SetNumZeroed(Indices.Num()/3);
        for (const FStaticMeshSection& Section : LOD.Sections)
            for (uint32 T=Section.FirstIndex/3, End=FMath::Min<uint32>(T+Section.NumTriangles,Surface->Slots.Num()); T<End; ++T)
                Surface->Slots[T]=uint16(FMath::Clamp(Section.MaterialIndex,0,MAX_uint16));
        for (int32 I=0; I+2<Indices.Num(); I+=3)
        {
            for (int32 K=0;K<3;++K) Surface->Points.Add(Positions.VertexPosition(Indices[I+K]));
            const FVector4f N=LOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(Indices[I]);
            Surface->Normals.Add(FVector3f(N.X,N.Y,N.Z));
        }
        return Cache.Add(Key,FMeshSurfaceRef(Surface));
    }

    /** One collision snapshot. Add takes UE-space triangles facing out of their solid ((B-A)x(C-A) points outward) and
     *  keeps them as simulation points, three per triangle. Plain data, so a worker thread can write it. */
    struct FSnapshot
    {
        FBox Region=FBox(ForceInit);
        int32 Budget=500000;
        TArray<FVector3f> Points;
        TArray<uint16> Surfaces;   // per triangle, packed (PackSurface)
        TArray<TArray<FVector3f>> Rails;
        FVector3f Spawn=FVector3f::ZeroVector;
        float Heading=0;
        int32 Num() const { return Points.Num()/3; }
        bool Full() const { return Num()>Budget; }
        void Add(const FVector& A, FVector B, FVector C, uint16 Surface)
        {
            if (Full()) return;
            FBox Bounds(ForceInit); Bounds+=A; Bounds+=B; Bounds+=C;
            if (!Bounds.Intersect(Region) || FVector::CrossProduct(B-A,C-A).SizeSquared()<.0001) return;
            Swap(B,C); // The coordinate reflection reverses winding.
            // The solver takes each normal from its own f32 points and refuses a flat one: drop slivers at that precision.
            const FVector3f P[3]={FVector3f(ToSimulation(A)),FVector3f(ToSimulation(B)),FVector3f(ToSimulation(C))};
            const FVector3d E1(P[1]-P[0]),E2(P[2]-P[0]);
            const double Twice=FVector3d::CrossProduct(E1,E2).Size();
            if (Twice<1e-9 || Twice<1e-6*E1.Size()*E2.Size()) return;
            Points.Append(P,3); Surfaces.Add(Surface);
        }
        // A face of a convex solid, turned away from the solid's centre.
        void AddFacing(const FVector& Centre, const FVector& A, const FVector& B, const FVector& C, uint16 Surface)
        {
            if (FVector::DotProduct(FVector::CrossProduct(B-A,C-A),(A+B+C)/3.-Centre)<0) Add(A,C,B,Surface); else Add(A,B,C,Surface);
        }
        // The surface of a mesh whose collision is its own triangles (its collision LOD's, copied by MeshSurface).
        void AddSurface(const FMeshSurface& Mesh, const FTransform& T, const TArray<uint16>& SlotSurfaces)
        {
            for (int32 I=0; I+2<Mesh.Points.Num() && !Full(); I+=3)
            {
                FVector P[3];
                for (int32 K=0;K<3;++K) P[K]=T.TransformPosition(FVector(Mesh.Points[I+K]));
                const FVector Authored=T.TransformVectorNoScale(FVector(Mesh.Normals[I/3]));
                if (FVector::DotProduct(FVector::CrossProduct(P[1]-P[0],P[2]-P[0]),Authored)<0) Swap(P[1],P[2]);
                const int32 Slot=Mesh.Slots.IsValidIndex(I/3) ? Mesh.Slots[I/3] : 0;
                Add(P[0],P[1],P[2],SlotSurfaces.IsValidIndex(Slot) ? SlotSurfaces[Slot] : (SlotSurfaces.Num() ? SlotSurfaces[0] : 0));
            }
        }
        void AddBox(const FTransform& T, const FVector& Half, uint16 Surface)
        {
            auto Corner=[&](int32 I){ return T.TransformPosition(FVector(I&1?Half.X:-Half.X,I&2?Half.Y:-Half.Y,I&4?Half.Z:-Half.Z)); };
            static const int32 Faces[6][4]={{0,2,6,4},{1,5,7,3},{0,4,5,1},{2,3,7,6},{0,1,3,2},{4,6,7,5}};
            for (const auto& Q : Faces)
            {
                AddFacing(T.GetLocation(),Corner(Q[0]),Corner(Q[1]),Corner(Q[2]),Surface);
                AddFacing(T.GetLocation(),Corner(Q[0]),Corner(Q[2]),Corner(Q[3]),Surface);
            }
        }
        // A capsule along local Z whose hemisphere centres sit Half above and below the origin; Half 0 is a sphere.
        void AddCapsule(const FTransform& T, double Radius, double Half, uint16 Surface)
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
                AddFacing(T.GetLocation(),Rings[R][S],Rings[R][N],Rings[R+1][N],Surface);
                AddFacing(T.GetLocation(),Rings[R][S],Rings[R+1][N],Rings[R+1][S],Surface);
            }
        }
        void AddHull(const FKConvexElem& Hull, const FTransform& T, uint16 Surface)
        {
            if (Hull.VertexData.IsEmpty()) return;
            const TArray<int32> Indices=Hull.IndexData.Num() ? Hull.IndexData : Hull.GetChaosConvexIndices();
            TArray<FVector> P; FVector Centre=FVector::ZeroVector;
            for (const FVector& V : Hull.VertexData) Centre+=P.Add_GetRef(T.TransformPosition(V));
            Centre/=P.Num();
            for (int32 I=0;I+2<Indices.Num();I+=3)
                if (P.IsValidIndex(Indices[I]) && P.IsValidIndex(Indices[I+1]) && P.IsValidIndex(Indices[I+2]))
                    AddFacing(Centre,P[Indices[I]],P[Indices[I+1]],P[Indices[I+2]],Surface);
        }
    };

    /** What a gather reads on the game thread, for the triangles to be made anywhere: each colliding static mesh near
     *  the centre (its surface copied, or its body setup's shapes) with its instances' transforms, and the rails. The
     *  body setups are kept alive (Keep) until the triangles are made: a level cell may stream out meanwhile. */
    struct FGatherJob
    {
        // A part's bounds and its instances' (an instanced mesh's, else one), for each smaller snapshot to skip what
        // lies outside it as the single-pass gather did.
        struct FPart { FMeshSurfaceRef Surface; const UBodySetup* Body=nullptr; FBox Bounds; TArray<FTransform> Instances; TArray<FBox> InstanceBounds;
                       TArray<uint16> SlotSurfaces; };   // packed, per material slot (a body's shapes ride slot 0's)
        TArray<FPart> Parts;
        TArray<TPair<FBox,TArray<FVector>>> Rails;
        TArray<TStrongObjectPtr<UObject>> Keep;
        FVector Centre=FVector::ZeroVector,Spawn=FVector::ZeroVector;float Yaw=0;
        double CollectMs=0;
    };
    constexpr double GatherRadii[]={10000.,6000.,3500.,2000.};

    /** The game thread's part of a gather: the colliding static meshes within the largest snapshot of Centre. */
    inline void CollectWorld(UWorld* World, ACharacter* Rider, FVector Centre, FVector Spawn, float Yaw, USkateRailSubsystem* Rails, FGatherJob& Job, bool bKeep)
    {
        const double Began=FPlatformTime::Seconds();
        const FBox Region(Centre-FVector(GatherRadii[0]),Centre+FVector(GatherRadii[0]));
        Job.Centre=Centre; Job.Spawn=Spawn; Job.Yaw=Yaw;
        const USkateSettings& Settings=*GetDefault<USkateSettings>();
        for (TObjectIterator<UStaticMeshComponent> It; It; ++It)
        {
            UStaticMeshComponent* C = *It;
            if (C->GetWorld()!=World || C->GetOwner()==Rider || !C->IsRegistered() || !C->IsCollisionEnabled() ||
                C->GetCollisionResponseToChannel(ECC_Pawn)!=ECR_Block || !C->Bounds.GetBox().Intersect(Region)) continue;
            UStaticMesh* Mesh=C->GetStaticMesh();
            UBodySetup* Body=Mesh ? Mesh->GetBodySetup() : nullptr;
            if (!Body) continue;
            FGatherJob::FPart Part; Part.Bounds=C->Bounds.GetBox();
            if (Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple) { Part.Surface=MeshSurface(Mesh); if (!Part.Surface) continue; }
            else { Part.Body=Body; if (bKeep) Job.Keep.Emplace(Body); }
            const ESkateSurface Override=ComponentSurface(C,Mesh,Settings);
            for (int32 Slot=0; Slot<FMath::Max(1,C->GetNumMaterials()); ++Slot) Part.SlotSurfaces.Add(SlotSurface(C,Slot,Override,Settings));
            if (CVarSkateSurfaceDebug.GetValueOnGameThread())
                for (int32 Slot=0; Slot<Part.SlotSurfaces.Num(); ++Slot)
                    UE_LOG(LogTemp,Display,TEXT("SKATE surface %s slot %d %s -> %s"),*Mesh->GetName(),Slot,
                        C->GetMaterial(Slot) ? *C->GetMaterial(Slot)->GetName() : TEXT("none"),*SurfaceName(ESkateSurface(Part.SlotSurfaces[Slot]&0x7f)));
            if (auto* ISM=Cast<UInstancedStaticMeshComponent>(C))
            {
                const FBox Local=Mesh->GetBounds().GetBox();
                for (int32 Index : ISM->GetInstancesOverlappingBox(Region,true))
                {
                    FTransform T;
                    if (ISM->GetInstanceTransform(Index,T,true)) { Part.Instances.Add(T); Part.InstanceBounds.Add(Local.TransformBy(T)); }
                }
            }
            else Part.Instances.Add(C->GetComponentTransform());
            Job.Parts.Add(MoveTemp(Part));
        }
        if (Rails) for (const FSkateRail& Rail : Rails->Rails) if (Rail.Bounds.Intersect(Region) && Rail.Points.Num()>=2)
            Job.Rails.Emplace(Rail.Bounds,Rail.Points);
        Job.CollectMs=(FPlatformTime::Seconds()-Began)*1000.;
    }

    /** Snapshot the static collision a walker meets near the job's centre: the triangles of meshes whose collision is
     *  their own surface, and the boxes, spheres, capsules and hulls of the others (a tree's trunk, not its leaves). A
     *  dense area shrinks the snapshot until it fits the budget; Reach is how far the rider may go from the centre
     *  before the next one. Reads only the job (and the meshes it keeps), so it runs on any thread. The simulation solver
     *  owns its narrow phase, BVH and contact solver. */
    inline bool FillWorld(const FGatherJob& Job, FSnapshot& Snapshot, double& Reach)
    {
        double Radius=0; const double Began=FPlatformTime::Seconds();
        for (const double Try : GatherRadii)
        {
            Radius=Try; Snapshot.Region=FBox(Job.Centre-FVector(Radius),Job.Centre+FVector(Radius)); Snapshot.Points.Reset(); Snapshot.Surfaces.Reset();
            // Each part's triangles on its own, in parallel, then joined in the parts' order: the snapshot one pass
            // makes (over budget the same way: a snapshot over it is dropped for the next radius either way).
            TArray<TArray<FVector3f>> PartPoints; PartPoints.SetNum(Job.Parts.Num());
            TArray<TArray<uint16>> PartSurfaces; PartSurfaces.SetNum(Job.Parts.Num());
            ParallelFor(Job.Parts.Num(), [&Job,&Snapshot,&PartPoints,&PartSurfaces](int32 P)
            {
                const FGatherJob::FPart& Part=Job.Parts[P];
                if (!Part.Bounds.Intersect(Snapshot.Region)) return;
                FSnapshot Local; Local.Region=Snapshot.Region; Local.Budget=MAX_int32/4;
                for (int32 I=0; I<Part.Instances.Num(); ++I)
                {
                    const FTransform& T=Part.Instances[I];
                    if (Part.InstanceBounds.IsValidIndex(I) && !Part.InstanceBounds[I].Intersect(Local.Region)) continue;
                    if (Part.Surface) { Local.AddSurface(*Part.Surface,T,Part.SlotSurfaces); continue; }
                    const uint16 Surface=Part.SlotSurfaces.Num() ? Part.SlotSurfaces[0] : 0;
                    const FKAggregateGeom& Geom=Part.Body->AggGeom;
                    for (const FKBoxElem& E : Geom.BoxElems) Local.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5,Surface);
                    for (const FKSphereElem& E : Geom.SphereElems) Local.AddCapsule(E.GetTransform()*T,E.Radius,0,Surface);
                    for (const FKSphylElem& E : Geom.SphylElems) Local.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5,Surface);
                    for (const FKConvexElem& E : Geom.ConvexElems) Local.AddHull(E,E.GetTransform()*T,Surface);
                }
                PartPoints[P]=MoveTemp(Local.Points); PartSurfaces[P]=MoveTemp(Local.Surfaces);
            });
            for (int32 P=0; P<PartPoints.Num(); ++P)
            {
                if (Snapshot.Full()) break;
                Snapshot.Points.Append(PartPoints[P]); Snapshot.Surfaces.Append(PartSurfaces[P]);
            }
            if (!Snapshot.Full()) break;
        }
        if (Snapshot.Num()==0 || Snapshot.Full()) return false;
        Reach=Radius*.6;
        for (const auto& Rail : Job.Rails) if (Rail.Key.Intersect(Snapshot.Region))
        {
            TArray<FVector3f>& Line=Snapshot.Rails.AddDefaulted_GetRef();
            for (const FVector& P : Rail.Value) Line.Add(FVector3f(ToSimulation(P)));
        }
        Snapshot.Spawn=FVector3f(ToSimulation(Job.Spawn)); Snapshot.Heading=-FMath::DegreesToRadians(Job.Yaw);
        int32 Counts[uint8(ESkateSurface::Sand)+1]={};
        for (const uint16 Surface : Snapshot.Surfaces) if ((Surface&0x7f)<=uint8(ESkateSurface::Sand)) ++Counts[Surface&0x7f];
        FString Surfaces;
        for (int32 S=1; S<=int32(ESkateSurface::Sand); ++S) if (Counts[S]) Surfaces+=FString::Printf(TEXT(" %s=%d"),*SurfaceName(ESkateSurface(S)),Counts[S]);
        UE_LOG(LogTemp,Display,TEXT("SKATE simulation collision: %d triangles, %d rails within %.0f m, collected in %.1f ms, made in %.1f ms%s; surfaces%s"),
            Snapshot.Num(),Snapshot.Rails.Num(),Radius/100.,Job.CollectMs,(FPlatformTime::Seconds()-Began)*1000.,IsInGameThread() ? TEXT("") : TEXT(" off the game thread"),*Surfaces);
        return true;
    }

    /** Both parts of a gather on the calling (game) thread. */
    inline bool GatherWorld(UWorld* World, ACharacter* Rider, FVector Centre, FVector Spawn, float Yaw, USkateRailSubsystem* Rails, FSnapshot& Snapshot, double& Reach)
    {
        FGatherJob Job; CollectWorld(World,Rider,Centre,Spawn,Yaw,Rails,Job,false);
        return FillWorld(Job,Snapshot,Reach);
    }

    // Preserve the former collision snapshot's seven decimal places before f32
    // publication. Removing the disk transport must not change its geometry.
    inline float SnapshotScalar(float V)
    {return float(double(FMath::RoundToInt64(double(V)*10000000.))/10000000.);}
    inline atelier::skate::Vec3 SnapshotPoint(FVector3f P)
    {return {SnapshotScalar(P.X),SnapshotScalar(P.Y),SnapshotScalar(P.Z)};}
    inline atelier::skate::GameplayWorldSnapshot SimulationSnapshot(const FSnapshot& S)
    {
        atelier::skate::GameplayWorldSnapshot Out;Out.triangles.reserve(S.Num());
        for(int32 I=0;I<S.Points.Num();I+=3)
            Out.triangles.push_back({SnapshotPoint(S.Points[I]),SnapshotPoint(S.Points[I+1]),SnapshotPoint(S.Points[I+2])});
        if(S.Surfaces.Num()==S.Num())Out.surfaces.assign(S.Surfaces.GetData(),S.Surfaces.GetData()+S.Surfaces.Num());
        for(const auto& Rail:S.Rails)
        {
            auto& Line=Out.rails.emplace_back();Line.reserve(Rail.Num());
            for(const auto& P:Rail) {const auto V=SnapshotPoint(P);Line.push_back({V.x,V.y,V.z});}
        }
        return Out;
    }
}
using namespace SkateRuntimeDetail;

namespace skate_simulation=atelier::skate;

// All mutable simulation owners stay on this simulation thread. The game thread
// exchanges typed commands and completed snapshots, with no process or JSON.
class FSkateSimulationWorker final : public FRunnable
{
public:
    struct FPreferences
    {std::string Difficulty;bool Goofy=false;float Trucks=.5f,Pop=1,Spin=1,PushSpeed=1,PushPower=1,VertAssist=0,PumpTrick=.5f;skate_simulation::FeelTuning Feel;};
    enum class ECommand {Step,Activate,Configure,World,Launch,Suspend};
    struct FCommand
    {
        ECommand Kind=ECommand::Step;skate_simulation::XboxState Input{};float Dt=0,Heading=0;
        std::vector<skate_simulation::StickReading> Readings;   // a Step's 120 Hz stick readings (empty: the packet's)
        skate_simulation::Vec3 Spawn{},Velocity{};uint32 Generation=0;FPreferences Preferences;
        std::optional<skate_simulation::GameplayWorldSnapshot> Snapshot;
        std::optional<skate_simulation::PreparedGameplayWorld> World;std::string Error;bool Background=false;
    };
    struct FOutput
    {
        bool Ready=false;uint32 Generation=0;uint64 Tick=0;std::string Error,State,Trick;
        skate_simulation::Mat4 Root{};skate_simulation::Vec3 Velocity{};float Score=0,Manual=0;
        std::vector<skate_simulation::Mat4> Bones,Reference;std::vector<std::string> Names;
        std::optional<skate_simulation::camera::CameraFrame> Camera;
        skate_simulation::ContactMaterial Floor;skate_simulation::Vec3 Spin{};bool Switch=false,Fakie=false;
        bool TrickSwitch=false,TrickFakie=false;   // the stance the trick the simulation's scoring announced started in
        float StepMs=0;   // the session's step (and its collision installs) on the thread, ms
        float RenewMs=0;   // a placement's new runtime on the thread, ms
        uint32 Pumps=0;float PumpGain=0;   // the session's successful pumps and the last one's gain (m/s)
        uint8 Surface=0,Wheels=0;   // the surface the wheels are on (ESkateSurface, 0 untagged) and the wheels in contact
    };
    FSkateSimulationWorker(skate_simulation::GameplayWorldSnapshot World,skate_simulation::Vec3 Spawn,float Heading,
        FSkateMotionFuture Motion,FSkateRuntimeFuture Runtime)
        :Motion_(std::move(Motion)),Runtime_(std::move(Runtime)),InitialWorld_(std::move(World)),Spawn_(Spawn),Heading_(Heading)
    {Wake_=FPlatformProcess::GetSynchEventFromPool(false);}
    ~FSkateSimulationWorker()
    {
        Stop();if(Thread_){Thread_->WaitForCompletion();delete Thread_;}
        FPlatformProcess::ReturnSynchEventToPool(Wake_);
    }
    bool Start()
    {Thread_=FRunnableThread::Create(this,TEXT("AtelierSkateSimulation"),32*1024*1024);return Thread_!=nullptr;}
    void Stop() override {Stopping_.store(true);Wake_->Trigger();}
    void Enqueue(FCommand Command) {Commands_.Enqueue(MoveTemp(Command));Wake_->Trigger();}
    bool Poll(FOutput& Output) {return Outputs_.Dequeue(Output);}
    bool HasOutput() const {return !Outputs_.IsEmpty();}
    bool Finished() const {return Finished_.load();}
    uint32 Run() override
    {
        FScopedSimulationFloatEnvironment FloatEnvironment;
        if(!FloatEnvironment.IsReady())
        {Fail("Skating floating-point environment setup failed");Finished_.store(true);return 1;}
        std::string Error;std::shared_ptr<const skate_simulation::GameplayResources> Resources;
        auto Wait=[this](const auto& Future)
        {
            while(Future.wait_for(std::chrono::milliseconds(20))!=std::future_status::ready)if(Stopping_.load())return false;
            return true;
        };
        if(!Wait(Motion_)||!Wait(Runtime_)){Finished_.store(true);return 1;}
        const auto& Motion=Motion_.get();
        if(!Motion.Source){Fail(Motion.Error.empty()?"Skate motion could not load":Motion.Error);Finished_.store(true);return 1;}
        const auto& Runtime=Runtime_.get();
        if(!Runtime.Payloads){Fail(Runtime.Error.empty()?"Skate runtime data could not load":Runtime.Error);Finished_.store(true);return 1;}
        if(!skate_simulation::LoadGameplayResources(*Runtime.Payloads,*Motion.Source,Resources,Error)
            ||!skate_simulation::GameplaySession::Create(Resources,InitialWorld_,Spawn_,Heading_,Session_,Error)
            ||!Session_->Activate(Spawn_,Heading_,Error)||!Publish(true,Error))
        {Fail(Error);Finished_.store(true);return 1;}
        Resources_=Resources;MakeSpare();MakeSpare();
        // Initial collision points can be large; their immutable copy is no
        // longer needed after the BVH and spline provider have been built.
        InitialWorld_={};
        while(!Stopping_.load())
        {
            FCommand Command;
            if(!Commands_.Dequeue(Command)){Wake_->Wait();continue;}
            bool Okay=true;
            switch(Command.Kind)
            {
            case ECommand::Step:
                if(!std::isfinite(Command.Dt)||Command.Dt<0)
                {Error="Invalid frame interval";Okay=false;break;}
            {
                const double Began=FPlatformTime::Seconds();
                for(auto& Pending:PendingCollisions_)
                    if(!InstallWorld(Pending,Error)){Okay=false;break;}
                PendingCollisions_.clear();
                if(Okay)Okay=Session_->Step(Command.Input,Command.Dt,Command.Readings,Error);
                if(Okay)Okay=Publish(false,Error,float((FPlatformTime::Seconds()-Began)*1000.));
                break;
            }
            case ECommand::Configure:
                if(!std::isfinite(Command.Preferences.Trucks)){Error="Invalid equipment";Okay=false;}
                else Okay=Configure(Command.Preferences,Error);
                break;
            case ECommand::Activate:
                if(!Finite(Command.Spawn)||!Finite(Command.Velocity)||!std::isfinite(Command.Heading)
                    ||!std::isfinite(Command.Preferences.Trucks))
                {Error="Invalid spawn or equipment";Okay=false;break;}
                // A world queued while riding (installed between steps) is the one the mount's reach was checked against.
                for(auto& Pending:PendingCollisions_)
                    if(!InstallWorld(Pending,Error)){Okay=false;break;}
                PendingCollisions_.clear();
                if(!Okay)break;
                // Every ride starts on a new session, made ahead on no world, that takes over this one's collision:
                // the same controls from the same place ride the same way whatever was ridden before.
            {
                const double Began=FPlatformTime::Seconds();
                if(Spares_.empty())MakeSpare();
                const auto Made=Spares_.front().Get();Spares_.pop_front();
                if(!Made->Session){Error=Made->Error;Okay=false;}
                else if((Okay=Made->Session->AdoptWorld(*Session_,Error)))Session_=std::move(Made->Session);
                RenewMs_=float((FPlatformTime::Seconds()-Began)*1000.);
                if(Okay)MakeSpare();
            }
                if(!Okay)break;
                Okay=Configure(Command.Preferences,Error)
                    &&Session_->Activate(Command.Spawn,Command.Heading,Error);
                if(Okay){HideTrick_=true;HiddenAnnounces_=Session_->gameplay->scoring.State().announces;}
                if(Okay){Session_->Launch(Command.Velocity);Generation_=Command.Generation;Okay=Publish(false,Error,0,RenewMs_);}
                break;
            case ECommand::World:
                if(Command.Background)PendingCollisions_.push_back(std::move(Command));
                // A world installed at once (an idle session's, a mount's) is newer than any still deferred.
                else {PendingCollisions_.clear();Okay=InstallWorld(Command,Error);}
                break;
            case ECommand::Launch:
                if(!Finite(Command.Velocity)){Error="Invalid launch velocity";Okay=false;}
                else Session_->Launch(Command.Velocity);
                break;
            case ECommand::Suspend:Session_->SuspendInput();break;
            }
            if(!Okay){Fail(Error);break;}
        }
        for(auto& Spare:Spares_)Spare.Wait();
        Session_.reset();Finished_.store(true);return 0;
    }
private:
    struct FSpare {std::unique_ptr<skate_simulation::GameplaySession> Session;std::string Error;};
    /** A next ride's session, made on its own thread while this one rides (CreateBlank: about 40 ms). Two are kept,
     *  so a placement (a mount, then the start at its exact point, in one frame) does not wait for one. */
    void MakeSpare()
    {
        Spares_.push_back(AsyncThread([Resources=Resources_]() -> TSharedPtr<FSpare,ESPMode::ThreadSafe>
        {
            auto Out=MakeShared<FSpare,ESPMode::ThreadSafe>();
            FScopedSimulationFloatEnvironment FloatEnvironment;
            if(!FloatEnvironment.IsReady())Out->Error="Skating floating-point environment setup failed";
            else if(!skate_simulation::GameplaySession::CreateBlank(Resources,Out->Session,Out->Error))Out->Session.reset();
            return Out;
        },32*1024*1024));
    }
    static bool Finite(skate_simulation::Vec3 V)
    {return std::isfinite(V.x)&&std::isfinite(V.y)&&std::isfinite(V.z);}
    bool InstallWorld(FCommand& Command,std::string& Error)
    {
        if(!Command.Error.empty()){Error=std::move(Command.Error);return false;}
        if(Command.Snapshot)
        {
            auto Board=skate_simulation::BoardPhysicsSettings::Load(Session_->gameplay->resources->settings,Error);
            if(!Board||!skate_simulation::BuildGameplayWorld(*Command.Snapshot,Board->floor_material,Command.World,Error))return false;
        }
        return Command.World&&Session_->InstallCollision(std::move(*Command.World),Error);
    }
    bool Configure(const FPreferences& P,std::string& Error)
    {
        // The former JSON command parser rejected nonfinite numbers before configuration.
        // Finite range errors still follow Configure, matching the original command order.
        if(!std::isfinite(P.Pop)||!std::isfinite(P.Spin)||!std::isfinite(P.PushSpeed)
            ||!std::isfinite(P.PushPower)||!std::isfinite(P.VertAssist))
        {Error="Invalid skating tuning";return false;}
        Session_->pumps.minimum_gain=std::isfinite(P.PumpTrick)?P.PumpTrick:.5f;
        return Session_->Configure(P.Difficulty,P.Goofy,P.Trucks,Error)
            &&Session_->Tune(P.Pop,P.Spin,P.PushSpeed,P.PushPower,P.VertAssist,Error)
            &&Session_->Feel(P.Feel,Error);
    }
    bool Publish(bool Ready,std::string& Error,float StepMs=0,float RenewMs=0)
    {
        if(!Session_->CheckPublishedPose(Error))return false;
        const auto& G=*Session_->gameplay;FOutput Out;Out.Ready=Ready;Out.Generation=Generation_;Out.StepMs=StepMs;Out.RenewMs=RenewMs;
        auto Pose=Session_->Pose();Out.Root=Pose.root;Out.Bones=std::move(Pose.bones);
        Out.Velocity=Pose.velocity;Out.Tick=Pose.tick;Out.State=std::move(Pose.state);
        Out.Spin=G.physical->board.Bodies()[std::size_t(skate_simulation::BoardBodyId::Deck)].rates.angular_velocity;
        Out.Switch=G.animation->packet.riding_switch;Out.Fakie=G.animation->packet.riding_fakie;
        // A trick named before the last placement stays hidden until the simulation announces another.
        if(HideTrick_&&G.scoring.State().announces!=HiddenAnnounces_)HideTrick_=false;
        if(!HideTrick_)Out.Trick=G.scoring.CurrentTrick();
        Out.TrickSwitch=G.scoring.State().start_stance[0];Out.TrickFakie=G.scoring.State().start_stance[1];
        Out.Pumps=Session_->pumps.count;Out.PumpGain=Session_->pumps.last_gain;
        const auto Ground=skate_simulation::ReportGroundSurface(G.physical->riding);Out.Surface=uint8(Ground.sound);Out.Wheels=uint8(Ground.wheels);
        const auto& Score=G.scoring.session.holder.State().snapshot;
        Out.Score=Score.completed_lines+Score.line;Out.Manual=G.animation_input.fields.balance;Out.Camera=Pose.camera;
        if(Ready)
        {
            Out.Names=std::move(Pose.names);
            if(!Session_->ReferencePose(Out.Reference,Error))return false;
            auto Board=skate_simulation::BoardPhysicsSettings::Load(G.resources->settings,Error);if(!Board)return false;
            Out.Floor=Board->floor_material;
        }
        Outputs_.Enqueue(MoveTemp(Out));return true;
    }
    void Fail(const std::string& Error) {FOutput Out;Out.Error=Error.empty()?"Skating failed":Error;Outputs_.Enqueue(MoveTemp(Out));}
    FSkateMotionFuture Motion_;
    FSkateRuntimeFuture Runtime_;skate_simulation::GameplayWorldSnapshot InitialWorld_;skate_simulation::Vec3 Spawn_;float Heading_;
    FEvent* Wake_=nullptr;FRunnableThread* Thread_=nullptr;std::atomic<bool> Stopping_{false},Finished_{false};
    TQueue<FCommand,EQueueMode::Mpsc> Commands_;TQueue<FOutput,EQueueMode::Spsc> Outputs_;
    std::unique_ptr<skate_simulation::GameplaySession> Session_;uint32 Generation_=0;
    bool HideTrick_=false;std::uint32_t HiddenAnnounces_=0;   // the trick shown hides across a placement
    float RenewMs_=0;   // the last placement's change of session, ms (published with its pose)
    std::shared_ptr<const skate_simulation::GameplayResources> Resources_;
    std::deque<TFuture<TSharedPtr<FSpare,ESPMode::ThreadSafe>>> Spares_;
    std::vector<FCommand> PendingCollisions_;
};

/** Retain the simulation session and decoded clips between rides. */
class FSkateRuntime
{
public:
    // Bind-space samples from the actual rendered rider. Kept only while this mesh is in use.
    struct Influence { int32 Bone; FVector Position; float Weight; };
    struct Vertex { TArray<Influence,TInlineAllocator<4>> Influences; };
    TWeakObjectPtr<USkeletalMesh> ContactMesh;
    TArray<Vertex> ContactVertices;
    // Skin samples (a bone and a point in its bind space) of each forearm's hand end with its hand, and of each foot,
    // and the bodies of this rider's pelvis, spine, chest and thighs (from its physics asset), for RetargetRiderPose.
    struct FSkinPoint { int32 Bone; FVector Local; };
    struct FBodyShape { uint8 Kind=0; FTransform Local; FVector Half=FVector::ZeroVector; double Radius=0; TArray<FPlane> Planes; };
    struct FBody { int32 Bone=INDEX_NONE; FVector Centre=FVector::ZeroVector; double Reach=0; TArray<FBodyShape> Shapes; };
    TWeakObjectPtr<USkeletalMesh> LimbMesh,BodiesMesh;
    TWeakObjectPtr<UPhysicsAsset> BodiesFor;
    bool bBodiesComplete=false;
    int32 BodiesTries=0;
    TArray<FSkinPoint> LimbSkin[4];   // forearm_L, forearm_R, foot_L, foot_R
    TArray<FBody> Bodies;
    // Each arm's swing out of the body (ClearArms): the angle it needs this frame, the angle shown and its rate
    // (radians, per second), and the world time of the last frame; invalid after a bail or a new rider.
    double ArmNeed[2]={0,0},ArmSwing[2]={0,0},ArmRate[2]={0,0},ArmTime=-1;
    bool bArmsValid=false;
    // A world built off the game thread: Empty when its gather found nothing to snapshot (open water), with the centre
    // and reach it covers, and its triangles.
    struct FWorldResult
    {std::optional<skate_simulation::PreparedGameplayWorld> World;std::string Error;bool Empty=false;FVector Centre,At;double Reach=0;int32 Triangles=0;};
    TUniquePtr<FSkateSimulationWorker> Worker;
    bool Ready=false,PendingActivation=false,AwaitingPose=false,HasPose=false;
    uint32 Generation=0;float FrameTime=0;
    // The next step's 120 Hz stick readings (USkateComponent::ReadFineSticks), when the last step was sent, and which
    // the last controller-driven step read (logged when it changes): -1 neither yet, 0 the packet, 1 the readings.
    std::vector<skate_simulation::StickReading> Readings;double LastSend=0;int8 FineSource=-1;
    FString State=TEXT("Loading skater"),Error,Trick;
    // Spin: the deck's angular velocity (rad/s, UE axes; the axis change is a reflection, so the pseudovector flips).
    FVector CollisionCentre=FVector::ZeroVector,Spawn=FVector::ZeroVector,Velocity=FVector::ZeroVector,Spin=FVector::ZeroVector;
    // The simulation's stance (its animation packet's): riding switch, riding fakie, and how many times the stance turned.
    bool Switch=false,Fakie=false;uint32 Turns=0;
    double CollisionReach=6000.;
    // Where a gather last found nothing to snapshot (open water): the next try waits 20 m from it. The coverage
    // (CollisionCentre, CollisionReach) stays the installed world's.
    FVector GatherRetryAt=FVector(UE_BIG_NUMBER);
    // Where the world should be centred (SnapshotCentre): on foot the rider's cell, from a mount its place, past the
    // reach where the ride has come to. A world centred elsewhere is rebuilt off the game thread (RefreshSimulationCollision),
    // so a ride from a place starts on that place's own world, whatever was gathered before (H54). IdleCell: the cell
    // the rider on foot was last seen in.
    FVector WantCentre=FVector::ZeroVector,IdleCell=FVector(UE_BIG_NUMBER);
    TFuture<TSharedPtr<FWorldResult,ESPMode::ThreadSafe>> PendingWorld;
    TArray<TStrongObjectPtr<UObject>> PendingKeep;   // the meshes PendingWorld's gather reads, released on the game thread
    skate_simulation::ContactMaterial Floor;
    TOptional<FVector> PendingLaunch;
    float SpawnYaw=0,Score=0,ManualBalance=0;
    uint64 Tick=0;
    // The controls of the last step sent, and the collision snapshots sent (their count and the last one's
    // triangles): GetSimulationState shows them, so a replay can check it feeds and sees what the recording did.
    skate_simulation::XboxState Sent{};int32 Worlds=0,WorldTriangles=0;
    // The session's step on its thread (ms): the mean and the worst of the last whole second, for GetSimulationState.
    float CostMean=0,CostWorst=0;double CostSum=0,CostSince=-1;float CostPeak=0;int32 CostSteps=0;
    // A session that has just shown its start has no step in flight: StepSimulation primes it (FSkateRuntime::Prime).
    bool Prime=false;
    // The air spin (the simulation names none; the game's HUD did): degrees turned about the rider's up since the
    // take-off, positive with the left stick; the last forward it was measured from; the name a landing gave it ("FS
    // 360") and the simulation trick it follows while that trick is shown.
    float AirSpin=0;FVector SpinForward=FVector::ZeroVector;FString SpinLabel,SpinOf;
    // The pumps: the session's count and last gain; those already shown; the repeats in the line, the simulation
    // trick they follow while it is shown, and whether they started a line of their own (the last one had faded).
    uint32 Pumps=0;float PumpGain=0;uint32 PumpsSeen=0;int32 PumpCount=0;FString PumpOf;bool PumpAlone=false;
    // The surface under the wheels (ESkateSurface; None off the ground or on untagged collision) and the wheels on it.
    ESkateSurface Surface=ESkateSurface::None;int32 Wheels=0;
    // The shown pose's health for QA (the simulation's bones).
    FRidePoseMeasure PoseMeasure;float PoseTravel=1;
    FTransform Root=FTransform::Identity,Camera=FTransform::Identity;float CameraFOV=0;
    // The rider's feel (USkateComponent::SetFeel), sent with every Activate and Configure.
    FSkateFeel Feel=FSkateFeel::Defaults();
    TArray<FName> Names;TArray<FTransform> Reference,Bones;
    ~FSkateRuntime() {if(PendingWorld.IsValid())PendingWorld.Wait();PendingKeep.Reset();Worker.Reset();}
    FSkateSimulationWorker::FPreferences Preferences(bool Goofy) const
    {
        const FSkateFeel& S=Feel;FSkateSimulationWorker::FPreferences P;
        P.Difficulty=TCHAR_TO_UTF8(*S.Difficulty);P.Goofy=Goofy;P.Trucks=S.TruckTightness;
        P.Pop=S.Pop;P.Spin=S.Spin;P.PushSpeed=S.PushSpeed;P.PushPower=S.PushPower;P.VertAssist=S.VertAssist;
        P.PumpTrick=CVarSkatePumpTrick.GetValueOnAnyThread();
        auto& N=P.Feel;
        N.flick_radius=S.FlickRadius;N.flick_window=S.FlickWindow;N.flick_pace=S.FlickPace;N.tight_flicks=S.TightFlicks;N.flick_120hz=S.Flick120Hz;
        N.gravity=S.Gravity;N.boneless=S.Boneless;N.hippy=S.Hippy;
        N.rail_magnetism=S.RailMagnetism;N.grind_pop=S.GrindPop;N.grind_friction=S.GrindFriction;
        N.braking=S.Braking;N.steering=S.Steering;N.carve=S.Carve;N.grip=S.Grip;N.powerslide=S.Powerslide;
        N.rolling_friction=S.RollingFriction;N.hill_speed=S.HillSpeed;N.pump=S.Pump;
        N.wobble=S.Wobble;N.wobble_onset=S.WobbleOnset;N.manual_drift=S.ManualDrift;
        N.landing=S.Landing;N.impact=S.Impact;N.auto_push=S.AutoPush;N.assisted_air=S.AssistedAir;
        return P;
    }
    void FinishPendingWorld(bool Background)
    {
        if(!PendingWorld.IsValid())return;
        const auto Result=PendingWorld.Get();PendingWorld={};PendingKeep.Reset();
        // Nothing to snapshot (open water): keep the old world and try again 20 m on, not on every frame.
        if(Result->Empty){GatherRetryAt=Result->At;return;}
        CollisionCentre=Result->Centre;CollisionReach=Result->Reach;++Worlds;WorldTriangles=Result->Triangles;GatherRetryAt=FVector(UE_BIG_NUMBER);
        FSkateSimulationWorker::FCommand Command;Command.Kind=FSkateSimulationWorker::ECommand::World;
        Command.World=std::move(Result->World);Command.Error=std::move(Result->Error);Command.Background=Background;
        Worker->Enqueue(MoveTemp(Command));
    }
    void SendWorld(const FSnapshot& Snapshot)
    {
        FSkateSimulationWorker::FCommand Command;Command.Kind=FSkateSimulationWorker::ECommand::World;
        Command.Snapshot=SimulationSnapshot(Snapshot);Worker->Enqueue(MoveTemp(Command));
    }
    void Activate(bool Goofy)
    {
        PendingActivation=true;if(!Ready)return;
        FSkateSimulationWorker::FCommand Command;Command.Kind=FSkateSimulationWorker::ECommand::Activate;
        Command.Spawn=SimulationVector(Spawn);Command.Heading=-FMath::DegreesToRadians(SpawnYaw);
        Command.Generation=Generation;Command.Preferences=Preferences(Goofy);
        Command.Velocity=SimulationVector(PendingLaunch.Get(FVector::ZeroVector));Worker->Enqueue(MoveTemp(Command));
        PendingActivation=false;AwaitingPose=true;PendingLaunch.Reset();
    }
    bool Poll()
    {
        bool Changed=false;FSkateSimulationWorker::FOutput Out;
        while(Worker->Poll(Out))
        {
            if(!Out.Error.empty()){Error=UTF8_TO_TCHAR(Out.Error.c_str());continue;}
            if(!Out.Ready&&Out.Generation!=Generation)continue;
            AwaitingPose=false;
            if(Out.RenewMs>0)UE_LOG(LogTemp,Display,TEXT("SKATE simulation ride on a new session (made ahead) in %.1f ms"),Out.RenewMs);
            if(Out.StepMs>0)
            {
                const double Now=FPlatformTime::Seconds();if(CostSince<0)CostSince=Now;
                CostSum+=Out.StepMs;CostPeak=FMath::Max(CostPeak,Out.StepMs);++CostSteps;
                if(Now-CostSince>=1.){CostMean=float(CostSum/CostSteps);CostWorst=CostPeak;CostSum=0;CostPeak=0;CostSteps=0;CostSince=Now;}
            }
            if(Out.Bones.empty()||Out.Bones.size()>256){Error=TEXT("Invalid simulation skeleton");continue;}
            Root=MatrixValue(Out.Root);Bones.Reset();for(const auto& M:Out.Bones)Bones.Add(MatrixValue(M));
            Velocity=FromSimulation(FVector(Out.Velocity.x,Out.Velocity.y,Out.Velocity.z));State=UTF8_TO_TCHAR(Out.State.c_str());
            Spin=FVector(-Out.Spin.z,Out.Spin.x,-Out.Spin.y);
            if(HasPose&&Out.Switch!=Switch)++Turns;Switch=Out.Switch;Fakie=Out.Fakie;
            // The stance as the game shows it: the simulation's IDs name the trick, its scoring the stance it was done in.
            Trick=TrickLabel(UTF8_TO_TCHAR(Out.Trick.c_str()));
            if(!Trick.IsEmpty()&&(Out.TrickFakie||Out.TrickSwitch))Trick=(Out.TrickFakie?TEXT("Fakie "):TEXT("Switch "))+Trick;
            Score=Out.Score;Tick=Out.Tick;ManualBalance=Out.Manual;Pumps=Out.Pumps;PumpGain=Out.PumpGain;
            Surface=Out.Surface<=uint8(ESkateSurface::Sand)?ESkateSurface(Out.Surface):ESkateSurface::None;Wheels=Out.Wheels;
            if(Root.ContainsNaN()||Velocity.ContainsNaN()||Bones.ContainsByPredicate([](const FTransform& T){return T.ContainsNaN();}))
            {Error=TEXT("Nonfinite simulation output");continue;}
            if(Out.Ready)
            {
                Names.Reset();Reference.Reset();for(const auto& N:Out.Names)Names.Add(FName(UTF8_TO_TCHAR(N.c_str())));
                for(const auto& M:Out.Reference)Reference.Add(MatrixValue(M));
                Ready=Names.Num()==Bones.Num()&&Reference.Num()==Bones.Num();Floor=Out.Floor;
            }
            if(Out.Camera)
            {
                const auto& C=*Out.Camera;auto Axis=[&](int I){const auto& V=C.basis.columns[I];return FVector(V[2],-V[0],V[1]);};
                Camera=FTransform(FRotationMatrix::MakeFromXZ(Axis(2),Axis(1)).ToQuat(),FromSimulation(FVector(C.position[0],C.position[1],C.position[2])));
                CameraFOV=C.field_of_view_degrees;
            }
            HasPose=Out.Generation==Generation&&!PendingActivation;Changed=HasPose;
        }
        if(Error.IsEmpty()&&Worker->Finished())Error=TEXT("The skating thread stopped");return Changed;
    }
    /** Lockstep: wait (at most 2 s) for the pose of the step sent last; whether it changed the shown pose. */
    bool AwaitPose()
    {
        bool Changed=false;const double Until=FPlatformTime::Seconds()+2.;
        while(AwaitingPose&&Error.IsEmpty()&&!Worker->Finished()&&FPlatformTime::Seconds()<Until)
        {
            if(Worker->HasOutput())Changed|=Poll();
            else FPlatformProcess::SleepNoStats(0.f);
        }
        return Changed;
    }
    /** Show another runtime's latest pose and state (Ride's presentation of its simulation session). */
    void Present(const FSkateRuntime& S)
    {
        Root=S.Root;Bones=S.Bones;Velocity=S.Velocity;Spin=S.Spin;Switch=S.Switch;Fakie=S.Fakie;Turns=S.Turns;State=S.State;Trick=S.Trick;Score=S.Score;
        ManualBalance=S.ManualBalance;Camera=S.Camera;CameraFOV=S.CameraFOV;Tick=S.Tick;Floor=S.Floor;HasPose=true;
        Surface=S.Surface;Wheels=S.Wheels;
        if(Names!=S.Names){Names=S.Names;Reference=S.Reference;}
    }
    FTransform Bone(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Bones.IsValidIndex(I) ? Bones[I]*Root : Root;
    }
    FTransform Bind(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Reference.IsValidIndex(I)?Reference[I]:FTransform::Identity;
    }
    // The front right wheel's turn on the deck from its reference pose, about the deck's axle (its Y), in degrees: the
    // wheels are the simulation's physical bodies, so this is how far they rolled (wheel= for QA).
    float WheelTurn() const
    {
        static const FName Deck(TEXT("SKATEBOARD_ROOT")),Wheel(TEXT("RIGHT_WHEELFRONT"));
        if(!Names.Contains(Deck)||!Names.Contains(Wheel))return 0;
        const FQuat Now=Bone(Deck).GetRotation().Inverse()*Bone(Wheel).GetRotation();
        const FQuat Rest=Bind(Deck).GetRotation().Inverse()*Bind(Wheel).GetRotation();
        FQuat Swing,Twist;(Now*Rest.Inverse()).ToSwingTwist(FVector::RightVector,Swing,Twist);
        return FMath::RadiansToDegrees(Twist.GetTwistAngle(FVector::RightVector));
    }
};
