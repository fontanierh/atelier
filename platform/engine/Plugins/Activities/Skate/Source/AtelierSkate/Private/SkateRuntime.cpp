#include "SkateComponent.h"
#include "Native/GameplaySession.h"
#include "Native/HostScalar.h"
#include "SkatePad.h"
#include <limits>
#include <cfenv>
#include "Engine/Engine.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "PhysicsEngine/BodySetup.h"
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
#include "Ride/RideSession.h"
#include "Ride/RidePhysicalRider.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"

namespace
{
    // Grab grip, tunable live: knuckle lift and outset from the deck edge (in finger widths, the rider's knuckle
    // spacing), finger flexion (MCP, PIP, DIP, cumulative from the hand's axis), thumb swing towards the fingers and
    // thumb flexion (degrees).
    TAutoConsoleVariable<FString> CVarSkateGrip(TEXT("skate.Grip"),TEXT("-.705 .94 25 75 10 40 40 15 10"),
        TEXT("Grab grip: lift out (finger widths) mcp pip dip thumbswing thumb1 thumb2 thumb3 (degrees)"));
    // The retargeted limbs against this rider's own body and the ground (RetargetRetailPose): how far each forearm and
    // hand stays out of its pelvis, spine, chest and thighs, and how far above the ground under it each foot's sole
    // stays (cm; below 0 off).
    TAutoConsoleVariable<float> CVarSkateArmClear(TEXT("skate.ArmClear"),2.f,
        TEXT("cm the hands and forearms keep clear of the rider's own pelvis, spine, chest and thighs; below 0 off"));
    TAutoConsoleVariable<float> CVarSkateFootGround(TEXT("skate.FootGround"),.5f,
        TEXT("cm each riding foot's sole stays above the ground under it; below 0 off"));
    // The native thread steps in lockstep with the game: each frame waits for the last frame's step, so no frame's
    // step or controls are skipped and the same controls replay the same ride. Its collision rebuilds install on the
    // frame after they start.
    TAutoConsoleVariable<int32> CVarSkateLockstep(TEXT("skate.Lockstep"),-1,
        TEXT("Native skating waits for each step of its thread, so a replay repeats: 1 always, 0 never, -1 under a fixed step or frame rate"));
    // The Ride backend's riding solver: Native's session rides (the board, its controls, tricks, airs, grinds, bail
    // rules and pose) while Ride keeps the body (the physical rider follows the retargeted pose), the transitions, the
    // bails and the get-up; or Ride's own kinematic board model.
    TAutoConsoleVariable<FString> CVarSkateRideSolver(TEXT("skate.RideSolver"),TEXT("Native"),
        TEXT("The Ride backend's riding solver for the next mount: Native (Native's session under Ride's body) or Ride (Ride's own board model)"));
    // QA: the hybrid's session fails on its next step, as a session error would (the bail, the relaunch, the get-up).
    TAutoConsoleVariable<int32> CVarSkateFailNative(TEXT("skate.FailNative"),0,
        TEXT("1: the Native session under the Ride body fails on its next step (QA of the failure path); clears itself"));
    bool Lockstep()
    {
        const int32 V=CVarSkateLockstep.GetValueOnGameThread();
        return V>0||(V<0&&(FApp::UseFixedTimeStep()||(GEngine&&GEngine->bUseFixedFrameRate)));
    }

    // Match the standalone runtime's floating environment (the defaults, denormals flushed to zero), and restore
    // the caller's complete environment before returning to Unreal.
    class FScopedNativeFloatEnvironment
    {
    public:
        FScopedNativeFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            SavedOkay_=std::fegetenv(&Saved_)==0;
            Ready_=SavedOkay_&&std::fesetenv(FE_DFL_ENV)==0&&atelier::skate::FlushDenormalsToZero();
        }
        ~FScopedNativeFloatEnvironment()
        {
#if defined(__clang__)
#pragma STDC FENV_ACCESS ON
#elif defined(_MSC_VER)
#pragma fenv_access(on)
#endif
            if(SavedOkay_)std::fesetenv(&Saved_);
        }
        FScopedNativeFloatEnvironment(const FScopedNativeFloatEnvironment&)=delete;
        FScopedNativeFloatEnvironment& operator=(const FScopedNativeFloatEnvironment&)=delete;
        bool IsReady() const {return Ready_;}
    private:
        std::fenv_t Saved_{};
        bool SavedOkay_=false,Ready_=false;
    };

    // Native left/up/forward metres -> UE forward/right/up centimetres (change handedness).
    FVector FromNative(const FVector& V) { return FVector(V.Z, -V.X, V.Y) * 100.; }
    FVector ToNative(const FVector& V) { return FVector(-V.Y, V.Z, V.X) * .01; }
    FTransform MatrixValue(const atelier::skate::Mat4& M)
    {
        auto Axis=[&](int I){return FVector(M[I][2],-M[I][0],M[I][1]);};
        return FTransform(FMatrix(FPlane(Axis(2),0),FPlane(-Axis(0),0),FPlane(Axis(1),0),FPlane(Axis(3)*100.,1)));
    }
    atelier::skate::Vec3 NativeVector(FVector V)
    {
        const FVector P=ToNative(V);
        const auto Scalar=[](double Value)
        {
            float Result=std::numeric_limits<float>::quiet_NaN();std::string Error;
            atelier::skate::ConvertHostScalar(Value,Result,Error);return Result;
        };
        return {Scalar(P.X),Scalar(P.Y),Scalar(P.Z)};
    }
    FString RuntimeFolder() { return FPaths::ConvertRelativePathToFull(FPaths::ProjectContentDir()/TEXT("Data/SkateNative")); }
    FString TrickLabel(FString Name)
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
    FVector SnapshotCentre(UWorld* World, const FVector& Position)
    {
        for (TActorIterator<AActor> It(World); It; ++It)
            if (It->ActorHasTag(TEXT("SkatePark")) && (Position-It->GetActorLocation()).GetAbsMax()<=6000.f)
                return It->GetActorLocation();
        return Position;
    }

    /** A static mesh's collision LOD as plain data: three mesh-space points per triangle and the authored normal (the
     *  first corner's tangent Z) of each. Copied on the game thread, so a worker never reads render data that LOD
     *  streaming may release. */
    struct FMeshSurface { TArray<FVector3f> Points, Normals; };
    using FMeshSurfaceRef=TSharedPtr<const FMeshSurface,ESPMode::ThreadSafe>;

    /** The mesh's surface, copied once per mesh and kept (game thread). Null when its collision LOD has no CPU data. */
    FMeshSurfaceRef MeshSurface(UStaticMesh* Mesh)
    {
        check(IsInGameThread());
        static TMap<TObjectKey<UStaticMesh>,FMeshSurfaceRef> Cache;
        const TObjectKey<UStaticMesh> Key(Mesh);
        if (const FMeshSurfaceRef* Found=Cache.Find(Key)) return *Found;
        if (!Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return nullptr;
        const auto& LODs=Mesh->GetRenderData()->LODResources;
        const FStaticMeshLODResources& LOD=LODs[FMath::Clamp(Mesh->LODForCollision,0,LODs.Num()-1)];
        const FPositionVertexBuffer& Positions=LOD.VertexBuffers.PositionVertexBuffer;
        if (!Positions.GetVertexData() || Positions.GetNumVertices()==0 || LOD.IndexBuffer.GetNumIndices()==0) return nullptr;
        const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();
        auto Surface=MakeShared<FMeshSurface,ESPMode::ThreadSafe>();
        Surface->Points.Reserve(Indices.Num()/3*3); Surface->Normals.Reserve(Indices.Num()/3);
        for (int32 I=0; I+2<Indices.Num(); I+=3)
        {
            for (int32 K=0;K<3;++K) Surface->Points.Add(Positions.VertexPosition(Indices[I+K]));
            const FVector4f N=LOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(Indices[I]);
            Surface->Normals.Add(FVector3f(N.X,N.Y,N.Z));
        }
        return Cache.Add(Key,FMeshSurfaceRef(Surface));
    }

    /** One collision snapshot. Add takes UE-space triangles facing out of their solid ((B-A)x(C-A) points outward) and
     *  keeps them as native points, three per triangle. Plain data, so a worker thread can write it. */
    struct FSnapshot
    {
        FBox Region=FBox(ForceInit);
        int32 Budget=500000;
        TArray<FVector3f> Points;
        TArray<TArray<FVector3f>> Rails;
        FVector3f Spawn=FVector3f::ZeroVector;
        float Heading=0;
        int32 Num() const { return Points.Num()/3; }
        bool Full() const { return Num()>Budget; }
        void Add(const FVector& A, FVector B, FVector C)
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
        }
        // A face of a convex solid, turned away from the solid's centre.
        void AddFacing(const FVector& Centre, const FVector& A, const FVector& B, const FVector& C)
        {
            if (FVector::DotProduct(FVector::CrossProduct(B-A,C-A),(A+B+C)/3.-Centre)<0) Add(A,C,B); else Add(A,B,C);
        }
        // The surface of a mesh whose collision is its own triangles (its collision LOD's, copied by MeshSurface).
        void AddSurface(const FMeshSurface& Mesh, const FTransform& T)
        {
            for (int32 I=0; I+2<Mesh.Points.Num() && !Full(); I+=3)
            {
                FVector P[3];
                for (int32 K=0;K<3;++K) P[K]=T.TransformPosition(FVector(Mesh.Points[I+K]));
                const FVector Authored=T.TransformVectorNoScale(FVector(Mesh.Normals[I/3]));
                if (FVector::DotProduct(FVector::CrossProduct(P[1]-P[0],P[2]-P[0]),Authored)<0) Swap(P[1],P[2]);
                Add(P[0],P[1],P[2]);
            }
        }
        void AddBox(const FTransform& T, const FVector& Half)
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
        void AddCapsule(const FTransform& T, double Radius, double Half)
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
        void AddHull(const FKConvexElem& Hull, const FTransform& T)
        {
            if (Hull.VertexData.IsEmpty()) return;
            const TArray<int32> Indices=Hull.IndexData.Num() ? Hull.IndexData : Hull.GetChaosConvexIndices();
            TArray<FVector> P; FVector Centre=FVector::ZeroVector;
            for (const FVector& V : Hull.VertexData) Centre+=P.Add_GetRef(T.TransformPosition(V));
            Centre/=P.Num();
            for (int32 I=0;I+2<Indices.Num();I+=3)
                if (P.IsValidIndex(Indices[I]) && P.IsValidIndex(Indices[I+1]) && P.IsValidIndex(Indices[I+2]))
                    AddFacing(Centre,P[Indices[I]],P[Indices[I+1]],P[Indices[I+2]]);
        }
    };

    /** What a gather reads on the game thread, for the triangles to be made anywhere: each colliding static mesh near
     *  the centre (its surface copied, or its body setup's shapes) with its instances' transforms, and the rails. The
     *  body setups are kept alive (Keep) until the triangles are made: a level cell may stream out meanwhile. */
    struct FGatherJob
    {
        // A part's bounds and its instances' (an instanced mesh's, else one), for each smaller snapshot to skip what
        // lies outside it as the single-pass gather did.
        struct FPart { FMeshSurfaceRef Surface; const UBodySetup* Body=nullptr; FBox Bounds; TArray<FTransform> Instances; TArray<FBox> InstanceBounds; };
        TArray<FPart> Parts;
        TArray<TPair<FBox,TArray<FVector>>> Rails;
        TArray<TStrongObjectPtr<UObject>> Keep;
        FVector Centre=FVector::ZeroVector,Spawn=FVector::ZeroVector;float Yaw=0;
        double CollectMs=0;
    };
    constexpr double GatherRadii[]={10000.,6000.,3500.,2000.};

    /** The game thread's part of a gather: the colliding static meshes within the largest snapshot of Centre. */
    void CollectWorld(UWorld* World, ACharacter* Rider, FVector Centre, FVector Spawn, float Yaw, USkateRailSubsystem* Rails, FGatherJob& Job, bool bKeep)
    {
        const double Began=FPlatformTime::Seconds();
        const FBox Region(Centre-FVector(GatherRadii[0]),Centre+FVector(GatherRadii[0]));
        Job.Centre=Centre; Job.Spawn=Spawn; Job.Yaw=Yaw;
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
     *  before the next one. Reads only the job (and the meshes it keeps), so it runs on any thread. The native solver
     *  owns its narrow phase, BVH and contact solver. */
    bool FillWorld(const FGatherJob& Job, FSnapshot& Snapshot, double& Reach)
    {
        double Radius=0; const double Began=FPlatformTime::Seconds();
        for (const double Try : GatherRadii)
        {
            Radius=Try; Snapshot.Region=FBox(Job.Centre-FVector(Radius),Job.Centre+FVector(Radius)); Snapshot.Points.Reset();
            // Each part's triangles on its own, in parallel, then joined in the parts' order: the snapshot one pass
            // makes (over budget the same way: a snapshot over it is dropped for the next radius either way).
            TArray<TArray<FVector3f>> PartPoints; PartPoints.SetNum(Job.Parts.Num());
            ParallelFor(Job.Parts.Num(), [&Job,&Snapshot,&PartPoints](int32 P)
            {
                const FGatherJob::FPart& Part=Job.Parts[P];
                if (!Part.Bounds.Intersect(Snapshot.Region)) return;
                FSnapshot Local; Local.Region=Snapshot.Region; Local.Budget=MAX_int32/4;
                for (int32 I=0; I<Part.Instances.Num(); ++I)
                {
                    const FTransform& T=Part.Instances[I];
                    if (Part.InstanceBounds.IsValidIndex(I) && !Part.InstanceBounds[I].Intersect(Local.Region)) continue;
                    if (Part.Surface) { Local.AddSurface(*Part.Surface,T); continue; }
                    const FKAggregateGeom& Geom=Part.Body->AggGeom;
                    for (const FKBoxElem& E : Geom.BoxElems) Local.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5);
                    for (const FKSphereElem& E : Geom.SphereElems) Local.AddCapsule(E.GetTransform()*T,E.Radius,0);
                    for (const FKSphylElem& E : Geom.SphylElems) Local.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5);
                    for (const FKConvexElem& E : Geom.ConvexElems) Local.AddHull(E,E.GetTransform()*T);
                }
                PartPoints[P]=MoveTemp(Local.Points);
            });
            for (const TArray<FVector3f>& Points : PartPoints) { if (Snapshot.Full()) break; Snapshot.Points.Append(Points); }
            if (!Snapshot.Full()) break;
        }
        if (Snapshot.Num()==0 || Snapshot.Full()) return false;
        Reach=Radius*.6;
        for (const auto& Rail : Job.Rails) if (Rail.Key.Intersect(Snapshot.Region))
        {
            TArray<FVector3f>& Line=Snapshot.Rails.AddDefaulted_GetRef();
            for (const FVector& P : Rail.Value) Line.Add(FVector3f(ToNative(P)));
        }
        Snapshot.Spawn=FVector3f(ToNative(Job.Spawn)); Snapshot.Heading=-FMath::DegreesToRadians(Job.Yaw);
        UE_LOG(LogTemp,Display,TEXT("SKATE retail collision: %d triangles, %d rails within %.0f m, collected in %.1f ms, made in %.1f ms%s"),
            Snapshot.Num(),Snapshot.Rails.Num(),Radius/100.,Job.CollectMs,(FPlatformTime::Seconds()-Began)*1000.,IsInGameThread() ? TEXT("") : TEXT(" off the game thread"));
        return true;
    }

    /** Both parts of a gather on the calling (game) thread. */
    bool GatherWorld(UWorld* World, ACharacter* Rider, FVector Centre, FVector Spawn, float Yaw, USkateRailSubsystem* Rails, FSnapshot& Snapshot, double& Reach)
    {
        FGatherJob Job; CollectWorld(World,Rider,Centre,Spawn,Yaw,Rails,Job,false);
        return FillWorld(Job,Snapshot,Reach);
    }

    // Preserve the former collision snapshot's seven decimal places before f32
    // publication. Removing the disk transport must not change its geometry.
    float SnapshotScalar(float V)
    {return float(double(FMath::RoundToInt64(double(V)*10000000.))/10000000.);}
    atelier::skate::Vec3 SnapshotPoint(FVector3f P)
    {return {SnapshotScalar(P.X),SnapshotScalar(P.Y),SnapshotScalar(P.Z)};}
    atelier::skate::GameplayWorldSnapshot NativeSnapshot(const FSnapshot& S)
    {
        atelier::skate::GameplayWorldSnapshot Out;Out.triangles.reserve(S.Num());
        for(int32 I=0;I<S.Points.Num();I+=3)
            Out.triangles.push_back({SnapshotPoint(S.Points[I]),SnapshotPoint(S.Points[I+1]),SnapshotPoint(S.Points[I+2])});
        for(const auto& Rail:S.Rails)
        {
            auto& Line=Out.rails.emplace_back();Line.reserve(Rail.Num());
            for(const auto& P:Rail) {const auto V=SnapshotPoint(P);Line.push_back({V.x,V.y,V.z});}
        }
        return Out;
    }
}

namespace skate_native=atelier::skate;

// All mutable simulation owners stay on this native thread. The game thread
// exchanges typed commands and completed snapshots, with no process or JSON.
class FNativeSkateWorker final : public FRunnable
{
public:
    struct FPreferences
    {std::string Difficulty;bool Goofy=false;float Trucks=.5f,Pop=1,Spin=1,PushSpeed=1,PushPower=1,VertAssist=0;};
    enum class ECommand {Step,Activate,Configure,World,Launch,Suspend};
    struct FCommand
    {
        ECommand Kind=ECommand::Step;skate_native::XboxState Input{};float Dt=0,Heading=0;
        skate_native::Vec3 Spawn{},Velocity{};uint32 Generation=0;FPreferences Preferences;
        std::optional<skate_native::GameplayWorldSnapshot> Snapshot;
        std::optional<skate_native::PreparedGameplayWorld> World;std::string Error;bool Background=false;
    };
    struct FOutput
    {
        bool Ready=false;uint32 Generation=0;uint64 Tick=0;std::string Error,State,Trick;
        skate_native::Mat4 Root{};skate_native::Vec3 Velocity{};float Score=0,Manual=0;
        std::vector<skate_native::Mat4> Bones,Reference;std::vector<std::string> Names;
        std::optional<skate_native::camera::CameraFrame> Camera;
        skate_native::ContactMaterial Floor;skate_native::Vec3 Spin{};bool Switch=false,Fakie=false;
        bool TrickSwitch=false,TrickFakie=false;   // the stance the trick native's scoring announced started in
        float StepMs=0;   // the session's step (and its collision installs) on the thread, ms
    };
    FNativeSkateWorker(FString Folder,skate_native::GameplayWorldSnapshot World,
        skate_native::Vec3 Spawn,float Heading)
        :Folder_(MoveTemp(Folder)),InitialWorld_(std::move(World)),Spawn_(Spawn),Heading_(Heading)
    {Wake_=FPlatformProcess::GetSynchEventFromPool(false);}
    ~FNativeSkateWorker()
    {
        Stop();if(Thread_){Thread_->WaitForCompletion();delete Thread_;}
        FPlatformProcess::ReturnSynchEventToPool(Wake_);
    }
    bool Start()
    {Thread_=FRunnableThread::Create(this,TEXT("AtelierSkateNative"),32*1024*1024);return Thread_!=nullptr;}
    void Stop() override {Stopping_.store(true);Wake_->Trigger();}
    void Enqueue(FCommand Command) {Commands_.Enqueue(MoveTemp(Command));Wake_->Trigger();}
    bool Poll(FOutput& Output) {return Outputs_.Dequeue(Output);}
    bool HasOutput() const {return !Outputs_.IsEmpty();}
    bool Finished() const {return Finished_.load();}
    uint32 Run() override
    {
        FScopedNativeFloatEnvironment FloatEnvironment;
        if(!FloatEnvironment.IsReady())
        {Fail("Native skating floating-point environment setup failed");Finished_.store(true);return 1;}
        std::string Error;std::shared_ptr<const skate_native::GameplayResources> Resources;
        if(!skate_native::LoadGameplayResources(std::filesystem::u8path(TCHAR_TO_UTF8(*Folder_)),Resources,Error)
            ||!skate_native::GameplaySession::Create(Resources,InitialWorld_,Spawn_,Heading_,Session_,Error)
            ||!Session_->Activate(Spawn_,Heading_,Error)||!Publish(true,Error))
        {Fail(Error);Finished_.store(true);return 1;}
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
                if(Okay)Okay=Session_->Step(Command.Input,Command.Dt,Error);
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
                Okay=Configure(Command.Preferences,Error)
                    &&Session_->Activate(Command.Spawn,Command.Heading,Error);
                if(Okay){HideTrick_=true;HiddenAnnounces_=Session_->gameplay->scoring.State().announces;}
                if(Okay){Session_->Launch(Command.Velocity);Generation_=Command.Generation;Okay=Publish(false,Error);}
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
        Session_.reset();Finished_.store(true);return 0;
    }
private:
    static bool Finite(skate_native::Vec3 V)
    {return std::isfinite(V.x)&&std::isfinite(V.y)&&std::isfinite(V.z);}
    bool InstallWorld(FCommand& Command,std::string& Error)
    {
        if(!Command.Error.empty()){Error=std::move(Command.Error);return false;}
        if(Command.Snapshot)
        {
            auto Board=skate_native::BoardPhysicsSettings::Load(Session_->gameplay->resources->settings,Error);
            if(!Board||!skate_native::BuildGameplayWorld(*Command.Snapshot,Board->floor_material,Command.World,Error))return false;
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
        return Session_->Configure(P.Difficulty,P.Goofy,P.Trucks,Error)
            &&Session_->Tune(P.Pop,P.Spin,P.PushSpeed,P.PushPower,P.VertAssist,Error);
    }
    bool Publish(bool Ready,std::string& Error,float StepMs=0)
    {
        if(!Session_->CheckPublishedPose(Error))return false;
        const auto& G=*Session_->gameplay;FOutput Out;Out.Ready=Ready;Out.Generation=Generation_;Out.StepMs=StepMs;
        auto Pose=Session_->Pose();Out.Root=Pose.root;Out.Bones=std::move(Pose.bones);
        Out.Velocity=Pose.velocity;Out.Tick=Pose.tick;Out.State=std::move(Pose.state);
        Out.Spin=G.physical->board.Bodies()[std::size_t(skate_native::BoardBodyId::Deck)].rates.angular_velocity;
        Out.Switch=G.animation->packet.riding_switch;Out.Fakie=G.animation->packet.riding_fakie;
        // A trick named before the last placement stays hidden until native announces another.
        if(HideTrick_&&G.scoring.State().announces!=HiddenAnnounces_)HideTrick_=false;
        if(!HideTrick_)Out.Trick=G.scoring.CurrentTrick();
        Out.TrickSwitch=G.scoring.State().start_stance[0];Out.TrickFakie=G.scoring.State().start_stance[1];
        const auto& Score=G.scoring.session.holder.State().snapshot;
        Out.Score=Score.completed_lines+Score.line;Out.Manual=G.animation_input.fields.balance;Out.Camera=Pose.camera;
        if(Ready)
        {
            Out.Names=std::move(Pose.names);
            if(!Session_->ReferencePose(Out.Reference,Error))return false;
            auto Board=skate_native::BoardPhysicsSettings::Load(G.resources->settings,Error);if(!Board)return false;
            Out.Floor=Board->floor_material;
        }
        Outputs_.Enqueue(MoveTemp(Out));return true;
    }
    void Fail(const std::string& Error) {FOutput Out;Out.Error=Error.empty()?"Native skating failed":Error;Outputs_.Enqueue(MoveTemp(Out));}
    FString Folder_;skate_native::GameplayWorldSnapshot InitialWorld_;skate_native::Vec3 Spawn_;float Heading_;
    FEvent* Wake_=nullptr;FRunnableThread* Thread_=nullptr;std::atomic<bool> Stopping_{false},Finished_{false};
    TQueue<FCommand,EQueueMode::Mpsc> Commands_;TQueue<FOutput,EQueueMode::Spsc> Outputs_;
    std::unique_ptr<skate_native::GameplaySession> Session_;uint32 Generation_=0;
    bool HideTrick_=false;std::uint32_t HiddenAnnounces_=0;   // the trick shown hides across a placement
    std::vector<FCommand> PendingCollisions_;
};

/** Retain the native session and decoded clips between rides. */
class FSkateRuntime
{
public:
    // Bind-space samples from the actual rendered rider. Kept only while this mesh is in use.
    struct Influence { int32 Bone; FVector Position; float Weight; };
    struct Vertex { TArray<Influence,TInlineAllocator<4>> Influences; };
    TWeakObjectPtr<USkeletalMesh> ContactMesh;
    TArray<Vertex> ContactVertices;
    // Skin samples (a bone and a point in its bind space) of each forearm's hand end with its hand, and of each foot,
    // and the bodies of this rider's pelvis, spine, chest and thighs (from its physics asset), for RetargetRetailPose.
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
    {std::optional<skate_native::PreparedGameplayWorld> World;std::string Error;bool Empty=false;FVector Centre,At;double Reach=0;int32 Triangles=0;};
    TUniquePtr<FNativeSkateWorker> Worker;
    bool Ready=false,PendingActivation=false,AwaitingPose=false,HasPose=false;
    uint32 Generation=0;float FrameTime=0;
    FString State=TEXT("Loading skater"),Error,Trick;
    // Spin: the deck's angular velocity (rad/s, UE axes; the axis change is a reflection, so the pseudovector flips).
    FVector CollisionCentre=FVector::ZeroVector,Spawn=FVector::ZeroVector,Velocity=FVector::ZeroVector,Spin=FVector::ZeroVector;
    // Native's stance (its animation packet's): riding switch, riding fakie, and how many times the stance turned.
    bool Switch=false,Fakie=false;uint32 Turns=0;
    double CollisionReach=6000.;
    // Where a gather last found nothing to snapshot (open water): the next try waits 20 m from it. The coverage
    // (CollisionCentre, CollisionReach) stays the installed world's.
    FVector GatherRetryAt=FVector(UE_BIG_NUMBER);
    TFuture<TSharedPtr<FWorldResult,ESPMode::ThreadSafe>> PendingWorld;
    TArray<TStrongObjectPtr<UObject>> PendingKeep;   // the meshes PendingWorld's gather reads, released on the game thread
    skate_native::ContactMaterial Floor;
    TOptional<FVector> PendingLaunch;
    float SpawnYaw=0,Score=0,ManualBalance=0;
    uint64 Tick=0;
    // The controls of the last step sent, and the collision snapshots sent (their count and the last one's
    // triangles): GetRetailState shows them, so a replay can check it feeds and sees what the recording did.
    skate_native::XboxState Sent{};int32 Worlds=0,WorldTriangles=0;
    // The session's step on its thread (ms): the mean and the worst of the last whole second, for GetRetailState.
    float CostMean=0,CostWorst=0;double CostSum=0,CostSince=-1;float CostPeak=0;int32 CostSteps=0;
    // A session that has just shown its start has no step in flight: StepNative primes it (FSkateRuntime::Prime).
    bool Prime=false;
    // The hybrid's air spin (Native names none; the game's HUD did): degrees turned about the rider's up since the
    // take-off, positive with the left stick; the last forward it was measured from; the name a landing gave it ("FS
    // 360") and the Native trick it follows while that trick is shown.
    float AirSpin=0;FVector SpinForward=FVector::ZeroVector;FString SpinLabel,SpinOf;
    // The shown pose's health for QA (the hybrid's: Native's bones, measured as the Ride backend measures its own).
    FRidePoseMeasure PoseMeasure;float PoseTravel=1;
    FTransform Root=FTransform::Identity,Camera=FTransform::Identity;float CameraFOV=0;
    TArray<FName> Names;TArray<FTransform> Reference,Bones;
    ~FSkateRuntime() {if(PendingWorld.IsValid())PendingWorld.Wait();PendingKeep.Reset();Worker.Reset();}
    FNativeSkateWorker::FPreferences Preferences(bool Goofy) const
    {
        const USkateSettings* S=GetDefault<USkateSettings>();FNativeSkateWorker::FPreferences P;
        P.Difficulty=TCHAR_TO_UTF8(*S->Difficulty);P.Goofy=Goofy;P.Trucks=S->TruckTightness;
        P.Pop=S->PopHeightScale;P.Spin=S->AirSpinScale;P.PushSpeed=S->PushSpeedScale;P.PushPower=S->PushPowerScale;P.VertAssist=S->VertAssist;return P;
    }
    void FinishPendingWorld(bool Background)
    {
        if(!PendingWorld.IsValid())return;
        const auto Result=PendingWorld.Get();PendingWorld={};PendingKeep.Reset();
        // Nothing to snapshot (open water): keep the old world and try again 20 m on, not on every frame.
        if(Result->Empty){GatherRetryAt=Result->At;return;}
        CollisionCentre=Result->Centre;CollisionReach=Result->Reach;++Worlds;WorldTriangles=Result->Triangles;GatherRetryAt=FVector(UE_BIG_NUMBER);
        FNativeSkateWorker::FCommand Command;Command.Kind=FNativeSkateWorker::ECommand::World;
        Command.World=std::move(Result->World);Command.Error=std::move(Result->Error);Command.Background=Background;
        Worker->Enqueue(MoveTemp(Command));
    }
    void SendWorld(const FSnapshot& Snapshot)
    {
        FNativeSkateWorker::FCommand Command;Command.Kind=FNativeSkateWorker::ECommand::World;
        Command.Snapshot=NativeSnapshot(Snapshot);Worker->Enqueue(MoveTemp(Command));
    }
    void Activate(bool Goofy)
    {
        PendingActivation=true;if(!Ready)return;
        FNativeSkateWorker::FCommand Command;Command.Kind=FNativeSkateWorker::ECommand::Activate;
        Command.Spawn=NativeVector(Spawn);Command.Heading=-FMath::DegreesToRadians(SpawnYaw);
        Command.Generation=Generation;Command.Preferences=Preferences(Goofy);
        Command.Velocity=NativeVector(PendingLaunch.Get(FVector::ZeroVector));Worker->Enqueue(MoveTemp(Command));
        PendingActivation=false;AwaitingPose=true;PendingLaunch.Reset();
    }
    bool Poll()
    {
        bool Changed=false;FNativeSkateWorker::FOutput Out;
        while(Worker->Poll(Out))
        {
            if(!Out.Error.empty()){Error=UTF8_TO_TCHAR(Out.Error.c_str());continue;}
            if(!Out.Ready&&Out.Generation!=Generation)continue;
            AwaitingPose=false;
            if(Out.StepMs>0)
            {
                const double Now=FPlatformTime::Seconds();if(CostSince<0)CostSince=Now;
                CostSum+=Out.StepMs;CostPeak=FMath::Max(CostPeak,Out.StepMs);++CostSteps;
                if(Now-CostSince>=1.){CostMean=float(CostSum/CostSteps);CostWorst=CostPeak;CostSum=0;CostPeak=0;CostSteps=0;CostSince=Now;}
            }
            if(Out.Bones.empty()||Out.Bones.size()>256){Error=TEXT("Invalid native skeleton");continue;}
            Root=MatrixValue(Out.Root);Bones.Reset();for(const auto& M:Out.Bones)Bones.Add(MatrixValue(M));
            Velocity=FromNative(FVector(Out.Velocity.x,Out.Velocity.y,Out.Velocity.z));State=UTF8_TO_TCHAR(Out.State.c_str());
            Spin=FVector(-Out.Spin.z,Out.Spin.x,-Out.Spin.y);
            if(HasPose&&Out.Switch!=Switch)++Turns;Switch=Out.Switch;Fakie=Out.Fakie;
            // The stance as the game shows it: native's IDs name the trick, its scoring the stance it was done in.
            Trick=TrickLabel(UTF8_TO_TCHAR(Out.Trick.c_str()));
            if(!Trick.IsEmpty()&&(Out.TrickFakie||Out.TrickSwitch))Trick=(Out.TrickFakie?TEXT("Fakie "):TEXT("Switch "))+Trick;
            Score=Out.Score;Tick=Out.Tick;ManualBalance=Out.Manual;
            if(Root.ContainsNaN()||Velocity.ContainsNaN()||Bones.ContainsByPredicate([](const FTransform& T){return T.ContainsNaN();}))
            {Error=TEXT("Nonfinite native output");continue;}
            if(Out.Ready)
            {
                Names.Reset();Reference.Reset();for(const auto& N:Out.Names)Names.Add(FName(UTF8_TO_TCHAR(N.c_str())));
                for(const auto& M:Out.Reference)Reference.Add(MatrixValue(M));
                Ready=Names.Num()==Bones.Num()&&Reference.Num()==Bones.Num();Floor=Out.Floor;
            }
            if(Out.Camera)
            {
                const auto& C=*Out.Camera;auto Axis=[&](int I){const auto& V=C.basis.columns[I];return FVector(V[2],-V[0],V[1]);};
                Camera=FTransform(FRotationMatrix::MakeFromXZ(Axis(2),Axis(1)).ToQuat(),FromNative(FVector(C.position[0],C.position[1],C.position[2])));
                CameraFOV=C.field_of_view_degrees;
            }
            HasPose=Out.Generation==Generation&&!PendingActivation;Changed=HasPose;
        }
        if(Error.IsEmpty()&&Worker->Finished())Error=TEXT("The native skating thread stopped");return Changed;
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
    /** Show another runtime's latest pose and state (the Ride backend's presentation of its Native session). */
    void Present(const FSkateRuntime& S)
    {
        Root=S.Root;Bones=S.Bones;Velocity=S.Velocity;Spin=S.Spin;Switch=S.Switch;Fakie=S.Fakie;Turns=S.Turns;State=S.State;Trick=S.Trick;Score=S.Score;
        ManualBalance=S.ManualBalance;Camera=S.Camera;CameraFOV=S.CameraFOV;Tick=S.Tick;Floor=S.Floor;HasPose=true;
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
    // wheels are Native's physical bodies, so this is how far they rolled (the Ride backend's wheel= for QA).
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

bool USkateComponent::RideSolverIsNative()
{
    return !CVarSkateRideSolver.GetValueOnGameThread().TrimStartAndEnd().Equals(TEXT("Ride"),ESearchCase::IgnoreCase);
}
bool USkateComponent::LaunchNativeSession(TSharedPtr<FSkateRuntime>& Into,const FVector& Where,float Yaw,FString& Failure)
{
    if(!FPaths::FileExists(RuntimeFolder()/TEXT("package-manifest.json")))
    {Failure=TEXT("Native skating data is missing from this build.");return false;}
    FSnapshot Snapshot;double Reach=0;const FVector Centre=SnapshotCentre(GetWorld(),Where);
    if(!GatherWorld(GetWorld(),Rider,Centre,Where,Yaw,RailSystem,Snapshot,Reach))
    {Failure=TEXT("Skating could not load nearby collision.");return false;}
    Into=MakeShared<FSkateRuntime>();Into->CollisionCentre=Centre;Into->CollisionReach=Reach;
    Into->Worlds=1;Into->WorldTriangles=Snapshot.Num();
    Into->Worker=MakeUnique<FNativeSkateWorker>(RuntimeFolder(),NativeSnapshot(Snapshot),
        SnapshotPoint(Snapshot.Spawn),SnapshotScalar(Snapshot.Heading));
    if(!Into->Worker->Start()){Into.Reset();Failure=TEXT("Native skating thread could not start.");return false;}
    return true;
}
void USkateComponent::PreloadRetailRuntime()
{
    // Decoding the animation banks takes seconds; do it while the player walks, so the first mount is immediate.
    bRetailPreloaded=true;
    const bool bRide=USkateSettings::ActiveBackend()==ESkateBackend::Ride;
    if (bRide) PreloadRide();
    if (bRide && !RideSolverIsNative()) return;
    FString Failure;
    if (!LaunchNativeSession(bRide?RideNative:RetailRuntime,Rider->GetActorLocation(),Rider->GetActorRotation().Yaw,Failure))
    { UE_LOG(LogTemp,Display,TEXT("SKATE preload skipped: %s"),*Failure); }
    else { UE_LOG(LogTemp,Display,TEXT("SKATE preload started")); }
}
void USkateComponent::PollIdleRetail()
{
    // The Ride backend's Native session between rides (and loading while the player walks).
    if (RideNative && RideNative->Worker && !(bRetailActive && bRideNative))
    {
        RideNative->Poll();
        if (!RideNative->Error.IsEmpty())
        { UE_LOG(LogTemp,Warning,TEXT("SKATE preloaded Native ride session failed: %s"),*RideNative->Error); RideNative.Reset(); }
        // The world follows the rider on foot, built off the game thread, so a mount does not build it (H34: 190 ms
        // where the ride started out of the last one's reach). Once loaded: the build takes the session's floor.
        else if (Rider && RideNative->Ready) RefreshNativeCollision(*RideNative,Rider->GetActorLocation(),Rider->GetActorRotation().Yaw,true);
    }
    if (!RetailRuntime || bRetailActive || !RetailRuntime->Worker) return;
    RetailRuntime->Poll();
    if (!RetailRuntime->Error.IsEmpty())
    { UE_LOG(LogTemp,Warning,TEXT("SKATE preloaded session failed: %s"),*RetailRuntime->Error); RetailRuntime.Reset(); }
}
bool USkateComponent::StartRetailRuntime()
{
    // The backend is chosen at each mount (skate.Backend, USkateSettings::Backend): a session of the other kind is
    // dropped. The Ride backend publishes through an FSkateRuntime without a native worker.
    const bool bRide=USkateSettings::ActiveBackend()==ESkateBackend::Ride;
    if (RetailRuntime && RetailRuntime->Worker.IsValid()==bRide) RetailRuntime.Reset();
    if (bRide)
    {
        if (!RetailRuntime) { RetailRuntime=MakeShared<FSkateRuntime>(); RetailRuntime->Ready=true; RetailRuntime->State=TEXT("PhysicsGround"); }
        bRideNative=RideSolverIsNative(); bNativeBail=false;
        if (!StartRide()) { RuntimeFailure(TEXT("Ride skating could not start.")); return false; }
        RetailRuntime->HasPose=false;
        // Ride's start settles onto the floor under the board, or onto one it started a little inside (a hand-off a
        // little low): Native's session starts there too, not inside the floor where its wheels find nothing.
        if (bRideNative && Ride->GetMode()!=ERideState::Air) Pos=Ride->GetPosition();
        if (bRideNative && !StartNativeRide()) { RuntimeFailure(TEXT("Native skating could not start under the Ride body.")); return false; }
        bRetailActive=true; RetailPose.Reset();
        return true;
    }
    StopRide();
    FString Failure;
    bRideNative=false; bNativeBail=false;
    if (!RetailRuntime && !LaunchNativeSession(RetailRuntime,Pos,Rot.Rotator().Yaw,Failure)) { RuntimeFailure(Failure); return false; }
    if (!ActivateNative(*RetailRuntime)) return false;
    bRetailActive=true; RetailPose.Reset();
    return true;
}
bool USkateComponent::ActivateNative(FSkateRuntime& R)
{
    R.FinishPendingWorld(false);
    if ((Pos-R.CollisionCentre).GetAbsMax()>R.CollisionReach)
    {
        FSnapshot Snapshot;double Reach=0;const FVector Centre=SnapshotCentre(GetWorld(),Pos);
        if(!GatherWorld(GetWorld(),Rider,Centre,Pos,Rot.Rotator().Yaw,RailSystem,Snapshot,Reach))
        {RuntimeFailure(TEXT("Skating could not refresh nearby collision."));return false;}
        R.SendWorld(Snapshot);R.CollisionCentre=Centre;R.CollisionReach=Reach;R.GatherRetryAt=FVector(UE_BIG_NUMBER);
        ++R.Worlds;R.WorldTriangles=Snapshot.Num();
    }
    R.Spawn=Pos; R.SpawnYaw=Rot.Rotator().Yaw;
    ++R.Generation; R.HasPose=false; R.FrameTime=0;
    R.PendingLaunch=Vel;
    R.Activate(bGoofy);
    return true;
}
bool USkateComponent::StartNativeRide()
{
    // Native's session rides from here: placed where the ride starts (Pos, Rot) with its speed (Vel). The Ride backend
    // places the rider on the session's first pose in this same frame (GetOnBoard measures the body's lift over its
    // root), so this waits for it: a few ticks for a session preloaded while the player walked, longer on the first
    // mount of a game whose session is still loading.
    if (RideNative && (!RideNative->Error.IsEmpty() || !RideNative->Worker || RideNative->Worker->Finished())) RideNative.Reset();
    FString Failure;
    if (!RideNative && !LaunchNativeSession(RideNative,Pos,Rot.Rotator().Yaw,Failure))
    { UE_LOG(LogTemp,Warning,TEXT("SKATE Native ride: %s"),*Failure); return false; }
    FSkateRuntime& N=*RideNative;
    if (!ActivateNative(N)) return false;
    const double Started=FPlatformTime::Seconds();
    while (!N.HasPose && N.Error.IsEmpty() && !N.Worker->Finished() && FPlatformTime::Seconds()<Started+30.)
    {
        if (N.Worker->HasOutput()) N.Poll(); else FPlatformProcess::SleepNoStats(.0002f);
        if (N.Ready && N.PendingActivation) N.Activate(bGoofy);
    }
    if (!N.HasPose)
    {
        UE_LOG(LogTemp,Warning,TEXT("SKATE Native ride did not start: %s"),N.Error.IsEmpty()?TEXT("no pose in 30 s"):*N.Error);
        RideNative.Reset(); return false;
    }
    RetailRuntime->Present(N); N.Prime=true;
    UE_LOG(LogTemp,Display,TEXT("SKATE Native ride at (%.0f, %.0f, %.0f) speed %.0f, first pose in %.1f ms"),Pos.X,Pos.Y,Pos.Z,Vel.Size(),
        (FPlatformTime::Seconds()-Started)*1000.);
    return true;
}
void USkateComponent::SuspendNativeRide()
{
    if (!RideNative || !RideNative->Worker) return;
    FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Suspend;RideNative->Worker->Enqueue(MoveTemp(C));
    RideNative->PendingActivation=false; RideNative->PendingLaunch.Reset(); RideNative->FrameTime=0; RideNative->HasPose=false; RideNative->Prime=false;
}
FTransform USkateComponent::RideRoot() const
{
    return bRideNative && RetailRuntime ? RetailRuntime->Root : Ride ? Ride->Root : FTransform::Identity;
}
FVector USkateComponent::BailVelocity() const { return bRideNative ? Vel : Ride ? Ride->GetBailVelocity() : FVector::ZeroVector; }
FVector USkateComponent::BailSpin() const { return bRideNative ? RideSpin : Ride ? Ride->GetBailSpin() : FVector::ZeroVector; }
// Native's pose carries its stance: the deck the run-out reads is the shown one, so the rider never counts as switch.
bool USkateComponent::RideSwitched() const { return !bRideNative && Ride && Ride->IsSwitch(); }
// Native's stance under either Native backend (the hybrid, or Native's own: not the idle Ride session a hybrid ride left).
bool USkateComponent::ShownFakie() const { return RetailRuntime && (bRideNative || RetailRuntime->Worker) ? RetailRuntime->Fakie : Ride ? Ride->IsFakie() : bFakie; }
bool USkateComponent::ShownSwitch() const { return RetailRuntime && (bRideNative || RetailRuntime->Worker) ? RetailRuntime->Switch : Ride && Ride->IsSwitch(); }
ERideGrab USkateComponent::RideGrab() const
{
    if (!bRideNative) return Ride ? Ride->GetBody().Grab : ERideGrab::None;
    if (Mode != ESkateMode::Air || !RetailRuntime) return ERideGrab::None;
    const FSkateHostPad Pad = ReadHostPad();
    if (!Pad.bGrabLeft && !Pad.bGrabRight) return ERideGrab::None;
    // The grab named last in the trick line is the one held. Native names the plain grabs by edge: the right trigger's
    // toe-side grab is Ride's Indy, the left's heel-side its Melon; until the line names one (a grab held only a moment,
    // H6), or for a grab Ride has no step-off for, the trigger held says which edge.
    ERideGrab Held = Pad.bGrabRight ? ERideGrab::Indy : ERideGrab::Melon; int32 Latest = INDEX_NONE;
    for (const TPair<const TCHAR*, ERideGrab>& Name : {TPair<const TCHAR*, ERideGrab>(TEXT("Indy"), ERideGrab::Indy), {TEXT("Melon"), ERideGrab::Melon},
        {TEXT("FS Grab"), ERideGrab::Indy}, {TEXT("BS Grab"), ERideGrab::Melon},
        {TEXT("Christ"), ERideGrab::ChristAir}, {TEXT("Tuck"), ERideGrab::TuckKnee}})
    {
        const int32 At = RetailRuntime->Trick.Find(Name.Key, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
        if (At > Latest) { Latest = At; Held = Name.Value; }
    }
    return Held;
}
void USkateComponent::SuspendRetailRuntime()
{
    StopRide();
    SuspendNativeRide(); bNativeBail=false;
    if (RetailRuntime && RetailRuntime->Worker) { FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Suspend;RetailRuntime->Worker->Enqueue(MoveTemp(C)); RetailRuntime->PendingActivation=false; RetailRuntime->PendingLaunch.Reset(); RetailRuntime->FrameTime=0; RetailRuntime->HasPose=false; }
    bRetailActive=false; RetailPose.Reset();
}
void USkateComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (PhysicalRider) PhysicalRider->End();
    ReleaseRootMotion();
    RetailRuntime.Reset(); RideNative.Reset(); Super::EndPlay(Reason);
}
void USkateComponent::LaunchRetail(const FVector& V)
{
    if (!bRetailActive || !RetailRuntime) return;
    if (!RetailRuntime->Worker && !(bRideNative && RideNative)) { if (Ride) Ride->Launch(V); return; }
    FSkateRuntime& R=RetailRuntime->Worker?*RetailRuntime:*RideNative;
    if (!R.Ready || R.PendingActivation) { R.PendingLaunch=V; return; }
    FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Launch;C.Velocity=NativeVector(V);R.Worker->Enqueue(MoveTemp(C));
}
void USkateComponent::ConfigureRetail()
{
    if(!RetailRuntime)return;
    if(!RetailRuntime->Worker)
    {
        const USkateSettings* S=GetDefault<USkateSettings>();
        if(Ride)Ride->Configure(bGoofy,{S->PopHeightScale,S->AirSpinScale,S->PushSpeedScale,S->PushPowerScale,S->VertAssist});
        if(RideNative&&RideNative->Worker)
        {
            FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Configure;
            C.Preferences=RideNative->Preferences(bGoofy);RideNative->Worker->Enqueue(MoveTemp(C));
        }
        return;
    }
    FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Configure;
    C.Preferences=RetailRuntime->Preferences(bGoofy);RetailRuntime->Worker->Enqueue(MoveTemp(C));
}

bool USkateComponent::GetRidePoseBone(FName Bone, FTransform& World) const
{
    if (!bRideNative || !RetailRuntime || !RetailRuntime->HasPose || !RetailRuntime->Names.Contains(Bone)) return false;
    World=RetailRuntime->Bone(Bone); return true;
}
bool USkateComponent::GetRetailCamera(FTransform& Out, float& FOV) const
{
    // A bail handed to the body has no session camera (the session waits): the character's own camera follows the body.
    if (!bRetailActive || !RetailRuntime || !RetailRuntime->HasPose || RetailRuntime->CameraFOV<=0 || bNativeBail) return false;
    Out=RetailRuntime->Camera; FOV=RetailRuntime->CameraFOV; return true;
}
FString USkateComponent::GetRetailState() const
{
    if (!bRetailActive || !RetailRuntime) return FString();
    // The Ride backend adds its simulation cost per 60 Hz tick (mean and worst over the last second, ms).
    if (!RetailRuntime->Worker && bRideNative)
    {
        // A session that failed is gone until the body gets up (StepRetailRuntime); the rider still rides Native.
        // cost= is Native's step on its own thread (mean and worst over the last second, ms), not the game thread's.
        static const skate_native::XboxState Idle{};
        const skate_native::XboxState& I=RideNative?RideNative->Sent:Idle;
        return FString::Printf(TEXT("%s tick=%llu backend=Ride solver=Native turns=%u lock=%d bail=%d pad=%x,%d,%d,%d,%d,%d,%d world=%d:%d cost=%.3f/%.3f spin=%.0f wheel=%.1f %s %s arm_swing=%.1f,%.1f arm_need=%.1f,%.1f"),
            *RetailRuntime->State,RetailRuntime->Tick,RetailRuntime->Turns,Lockstep()?1:0,bNativeBail?1:0,I.buttons,I.triggers[0],I.triggers[1],I.left[0],I.left[1],I.right[0],I.right[1],
            RideNative?RideNative->Worlds:0,RideNative?RideNative->WorldTriangles:0,RideNative?RideNative->CostMean:0.f,RideNative?RideNative->CostWorst:0.f,RetailRuntime->AirSpin,RetailRuntime->WheelTurn(),*RetailRuntime->PoseMeasure.Describe(),PhysicalRider?*PhysicalRider->Describe():TEXT("phys=off"),
            FMath::RadiansToDegrees(RetailRuntime->ArmSwing[0]),FMath::RadiansToDegrees(RetailRuntime->ArmSwing[1]),
            FMath::RadiansToDegrees(RetailRuntime->ArmNeed[0]),FMath::RadiansToDegrees(RetailRuntime->ArmNeed[1]));
    }
    if (!RetailRuntime->Worker && Ride)
        return FString::Printf(TEXT("%s tick=%llu backend=Ride cost=%.3f/%.3f %s %s arm_swing=%.1f,%.1f arm_need=%.1f,%.1f spin=%.1f select=%d,%.3f"),*RetailRuntime->State,RetailRuntime->Tick,
            Ride->CostMean,Ride->CostWorst,*Ride->DescribePose(),PhysicalRider?*PhysicalRider->Describe():TEXT("phys=off"),
            FMath::RadiansToDegrees(RetailRuntime->ArmSwing[0]),FMath::RadiansToDegrees(RetailRuntime->ArmSwing[1]),
            FMath::RadiansToDegrees(RetailRuntime->ArmNeed[0]),FMath::RadiansToDegrees(RetailRuntime->ArmNeed[1]),Ride->GetAirSpin(),
            Ride->SelectQueries,Ride->SelectCost);
    const skate_native::XboxState& I=RetailRuntime->Sent;
    return FString::Printf(TEXT("%s tick=%llu backend=Native lock=%d pad=%x,%d,%d,%d,%d,%d,%d world=%d:%d turns=%u wheel=%.1f %s"),*RetailRuntime->State,RetailRuntime->Tick,
        Lockstep()?1:0,I.buttons,I.triggers[0],I.triggers[1],I.left[0],I.left[1],I.right[0],I.right[1],RetailRuntime->Worlds,RetailRuntime->WorldTriangles,
        RetailRuntime->Turns,RetailRuntime->WheelTurn(),*RetailRuntime->PoseMeasure.Describe());
}

FSkateHostPad USkateComponent::ReadHostPad() const
{
    FSkateHostPad Out;
    Out.LeftX=In.Left.X;Out.LeftY=In.Left.Y;Out.RightX=In.Right.X;Out.RightY=In.Right.Y;
    Out.bPush=In.bPush;Out.bBrake=In.bBrake;Out.bTransfer=In.bTransfer;Out.bPowerslide=In.bPowerslide;
    Out.bGrabLeft=In.bGrabLeft;Out.bGrabRight=In.bGrabRight;Out.bGround=Mode==ESkateMode::Ground;
    // A scripted pull (0..1) keeps its depth; the controller's own axes replace it below.
    Out.LeftTrigger=In.LeftPull();Out.RightTrigger=In.RightPull();
    // The player's controller adds the buttons and triggers FSkateInput has no room for, unless scripted input, a
    // blocked rider or a free mouse drives the ride.
    if (!bScripted && RiderApi && !RiderApi->IsSkateInputBlocked() && !RiderApi->IsSkateMouseFree())
        if (const APlayerController* PC=Cast<APlayerController>(Rider->GetController()))
        {
            Out.bController=true;
            Out.bFaceLeft=PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Left);Out.bFaceBottom=PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Bottom);
            Out.bW=PC->IsInputKeyDown(EKeys::W);Out.bUp=PC->IsInputKeyDown(EKeys::Up);
            Out.bLeftShoulder=PC->IsInputKeyDown(EKeys::Gamepad_LeftShoulder);Out.bRightShoulder=PC->IsInputKeyDown(EKeys::Gamepad_RightShoulder);
            Out.bLeftThumb=PC->IsInputKeyDown(EKeys::Gamepad_LeftThumbstick);Out.bRightThumb=PC->IsInputKeyDown(EKeys::Gamepad_RightThumbstick);
            Out.bQ=PC->IsInputKeyDown(EKeys::Q);Out.bE=PC->IsInputKeyDown(EKeys::E);
            Out.LeftTrigger=PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis);
            Out.RightTrigger=PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis);
        }
    return Out;
}

void USkateComponent::StepRetailRuntime(float Dt)
{
    ReadInput(Dt);
    ComboFade=FMath::Max(0.f,ComboFade-Dt);
    if (!bRetailActive || !RetailRuntime) return;
    if (!RetailRuntime->Worker && bRideNative)
    {
        // Native rides under Ride's body. A bail handed to the body waits for it to settle (AfterNativeRideFrame);
        // a get-up holds the session's controls neutral until the rider is up.
        if (bNativeBail) { AfterNativeRideFrame(Dt); return; }
        if (!RideNative) { RuntimeFailure(TEXT("The Native ride session is gone.")); StowImmediately(); return; }
        if (CVarSkateFailNative.GetValueOnGameThread()>0)
        { CVarSkateFailNative->Set(0,ECVF_SetByConsole); RideNative->Error=TEXT("Failed on request (skate.FailNative)"); }
        bool bFailed=false;
        const bool Changed=StepNative(*RideNative,Dt,PhysicalRider && PhysicalRider->IsGettingUp(),bFailed);
        if (bFailed)
        {
            // A failed session never stows the board under a moving rider: the body falls with the momentum shown, as
            // in a wipeout, and the get-up takes the ride back on a fresh session, loaded off the game thread while the
            // body falls (H10: loaded at the get-up, it held the game thread 0.7-1 s). The failure is still logged.
            RuntimeFailure(RideNative->Error);
            RideNative.Reset();
            FString Failure;
            if (!LaunchNativeSession(RideNative,Pos,Rot.Rotator().Yaw,Failure)) { UE_LOG(LogTemp,Warning,TEXT("SKATE Native relaunch: %s"),*Failure); }
            else { UE_LOG(LogTemp,Display,TEXT("SKATE Native session relaunched after a failure")); }
            if (PhysicalRider && PhysicalRider->IsActive() && !PhysicalRider->IsBailing() && !PhysicalRider->IsGettingUp()
                && PhysicalRider->StartBail(Vel, RideSpin, URidePhysicalRider::ShownTransform(BoardRoot), BoardScale()))
            {
                bNativeBail = true;
                ++Bails; ++Serial; Mode = ESkateMode::Bail; PlayCue(TEXT("clatter"), 1, 1);
                return;
            }
            StowImmediately();
            return;
        }
        if (!Changed) { AfterNativeRideFrame(Dt); return; }
        RetailRuntime->Present(*RideNative);
    }
    else if (!RetailRuntime->Worker)
    {
        if (!Ride || !StepRide(Dt)) return;
        FSkateRuntime& O=*RetailRuntime;const FRideSession& R=*Ride;
        O.Root=R.Root;O.Bones=R.Bones;O.Velocity=R.Velocity;O.State=R.State;O.Trick=R.Trick;O.Score=R.Score;
        O.ManualBalance=R.ManualBalance;O.Camera=R.Camera;O.CameraFOV=R.CameraFOV;O.Tick=R.Ticks;O.HasPose=true;
        if (O.Names!=R.Names) { O.Names=R.Names; O.Reference=R.Reference; }
    }
    else
    {
        bool bFailed=false;
        const bool Changed=StepNative(*RetailRuntime,Dt,false,bFailed);
        if (bFailed) { RuntimeFailure(RetailRuntime->Error); StowImmediately(); RetailRuntime.Reset(); return; }
        if (!Changed) return;
    }
    const FString& S=RetailRuntime->State;
    // Under the hybrid a fallen rider getting up onto the board is still in the bail, as Ride's session is.
    const bool bRisingOntoBoard=bRideNative && PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpExit()==ERideGetUpExit::Board;
    const ESkateMode NewMode=bRisingOntoBoard||S.Contains(TEXT("Wipeout"))?ESkateMode::Bail:S.Contains(TEXT("Grind"))?ESkateMode::Grind:
        S.Contains(TEXT("Air"))?ESkateMode::Air:ESkateMode::Ground;
    const ESkateMode Was=Mode;
    if (NewMode!=Mode)
    {
        if (NewMode==ESkateMode::Bail) { ++Bails; PlayCue(TEXT("clatter"),1,1); }
        if (NewMode==ESkateMode::Air && Mode==ESkateMode::Ground) PlayCue(TEXT("pop"),1,1);
        if (NewMode==ESkateMode::Ground && Mode==ESkateMode::Air) { ++Landed; PlayCue(TEXT("land"),.8,1); }
        if (NewMode==ESkateMode::Grind) ++Grinds;
        ++Serial; Mode=NewMode;
    }
    if (bRideNative && RideNative) NameNativeSpin(Was);
    const FTransform DeckWorld=RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"));
    Rot=DeckWorld.GetRotation(); Pos=DeckWorld.GetLocation()-Rot.GetUpVector()*9.05; Vel=RetailRuntime->Velocity;
    // Contact jitter at rest must not alternate the stance or the HUD every frame.
    const float Along=FVector::DotProduct(Vel,Rot.GetForwardVector());
    if (FMath::Abs(Along)>15.f) bFakie=Along<0;
    RailSpeed=Vel.Size();
    bManual=Mode==ESkateMode::Ground && FMath::Abs(RetailRuntime->ManualBalance)>.0001f;
    bNoseManual=bManual && (RetailRuntime->Worker || bRideNative ? RetailRuntime->Trick.Contains(TEXT("Nose")) : Ride && Ride->IsNoseManual());
    bPushing=In.bPush; bBraking=In.bBrake; bPowerslide=S==TEXT("SlideGround");
    const FVector Travel=FVector(Vel.X,Vel.Y,0).GetSafeNormal();
    SlideAngle=bPowerslide ? FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FMath::Abs(FVector::DotProduct(Travel,Rot.GetForwardVector()))),0.f,1.f))) : 0.f;
    bSlide=S==TEXT("GrindBoardslide") || S==TEXT("GrindTipslide") || S==TEXT("GrindDarkslide") || S==TEXT("GrindLipslide");
    if (ShownCombo!=RetailRuntime->Trick || Score!=FMath::RoundToInt(RetailRuntime->Score) ||
        Mode==ESkateMode::Air || Mode==ESkateMode::Grind || bManual) ComboFade=1.5f;
    ShownCombo=RetailRuntime->Trick; Score=FMath::RoundToInt(RetailRuntime->Score); LastTrickName=FName(*ShownCombo);
    // No physics teleport: the Ride rider's simulated bodies (RidePhysicalRider) keep their own motion.
    Rider->SetActorLocationAndRotation(RetailRuntime->Root.GetLocation()+FVector(0,0,BodyLift),RetailRuntime->Root.GetRotation(),false,nullptr,ETeleportType::None);
    Movement()->Velocity=Vel;
    // A bigger board grows about the ground contact, so its wheels stay on the ground (ISkateRider::GetSkateBoardScale).
    PlaceBoardParts(DeckWorld*BoardGrowth());
    RetargetRetailPose();
    if (!RetailRuntime->Worker && !bRideNative) { AfterRideFrame(Dt); return; }
    {
        // The pose Native shows, measured alike on the hybrid and the Native backend (the reference it is compared to).
        // Native's root need not point along the travel (a shove-it turns the board and the root with it, the rider
        // stays regular), so the measure takes the travel from the velocity in the root's frame, held while slow, and
        // the deck reversed when its nose points back along the root.
        FSkateRuntime& O=*RetailRuntime;
        const float RootAlong=FVector::DotProduct(O.Velocity,O.Root.GetRotation().GetForwardVector());
        if (FMath::Abs(RootAlong)>15.f) O.PoseTravel=RootAlong<0?-1.f:1.f;
        const int32 DeckBone=O.PoseMeasure.DeckBone;
        const bool bDeckBack=O.Bones.IsValidIndex(DeckBone) && O.Bones[DeckBone].GetRotation().GetForwardVector().X<0;
        O.PoseMeasure.Measure(O.Names,O.Reference,O.Bones,Dt,O.PoseTravel,bDeckBack);
    }
    if (!RetailRuntime->Worker)
    {
        RideSpin=RetailRuntime->Spin;
        AfterNativeRideFrame(Dt);
        if (RideNative && !bNativeBail) RefreshNativeCollision(*RideNative,Pos,Rot.Rotator().Yaw,false);
        return;
    }
    RefreshNativeCollision(*RetailRuntime,Pos,Rot.Rotator().Yaw,false);
}

void USkateComponent::NameNativeSpin(ESkateMode Was)
{
    // The rider's turn about its own up (the pose root's; a shove-it turns only the board) between shown frames.
    FSkateRuntime& O=*RetailRuntime;
    const FQuat Frame=O.Root.GetRotation();const FVector Up=Frame.GetUpVector();
    const FVector Forward=FVector::VectorPlaneProject(Frame.GetForwardVector(),Up).GetSafeNormal();
    if (Mode==ESkateMode::Air)
    {
        if (Was!=ESkateMode::Air) { O.AirSpin=0; O.SpinLabel.Reset(); }
        else if (!O.SpinForward.IsNearlyZero())
        {
            const FVector From=FVector::VectorPlaneProject(O.SpinForward,Up).GetSafeNormal();
            O.AirSpin+=FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(From,Forward),Up),FVector::DotProduct(From,Forward)));
        }
    }
    else if (Was==ESkateMode::Air)
    {
        // Named as Ride names it (FRideSession::SpinName): up to 30 degrees short still counts; a regular rider
        // turning toward the board's right (negative yaw) rolling forward leads with the chest, frontside.
        const float Spun=FMath::Abs(O.AirSpin);
        if (Mode==ESkateMode::Ground && Spun>=150.f)
        {
            const int32 Half=FMath::Max(1,FMath::RoundToInt((Spun-30.f)/180.f+.0001f));
            const float Stance=(bGoofy!=O.Switch)?-1.f:1.f, Travel=O.Fakie?-1.f:1.f;
            O.SpinLabel=FString::Printf(TEXT("%s %d"),O.AirSpin*Stance*Travel<0?TEXT("FS"):TEXT("BS"),Half*180);O.SpinOf=RideNative->Trick;
        }
        O.AirSpin=0;
    }
    O.SpinForward=Forward;
    // The spin is shown after the trick it came with, until Native shows another.
    if (!O.SpinLabel.IsEmpty())
    {
        if (RideNative->Trick!=O.SpinOf) O.SpinLabel.Reset();
        else O.Trick=O.SpinOf.IsEmpty()?O.SpinLabel:O.SpinOf+TEXT(" / ")+O.SpinLabel;
    }
}

bool USkateComponent::StepNative(FSkateRuntime& R, float Dt, bool bNeutral, bool& bFailed)
{
    bool Changed=Lockstep() && R.AwaitingPose && R.AwaitPose();
    Changed|=R.Poll();
    if (!R.Error.IsEmpty()) { bFailed=true; return false; }
    if (!R.Ready) return false;
    if (R.PendingActivation) { R.Activate(bGoofy); return false; }
    R.FrameTime=FMath::Min(.1f,R.FrameTime+Dt);
    if (R.AwaitingPose) return Changed;
    // The canonical pad (SkatePad.h); GameplaySession takes the host transfer bit off before Xbox sampling.
    const skate_native::XboxState Input=bNeutral?skate_native::XboxState{}:atelier::skate_pad::Pack(ReadHostPad());
    auto Send=[&R,&Input]()
    {
        FNativeSkateWorker::FCommand Command;Command.Kind=FNativeSkateWorker::ECommand::Step;Command.Dt=R.FrameTime;
        Command.Input=Input;R.Sent=Input;R.Worker->Enqueue(MoveTemp(Command));
        R.AwaitingPose=true; R.FrameTime=0;
    };
    Send();
    // A session that has just shown its start (StartNativeRide) has no step in flight, so this frame would show the
    // start again. Its first step is waited for and shown now, and the next is sent at once: the first frame moves on
    // by its time as every later frame does, and the pose shown keeps up with real time rather than a frame behind.
    if (R.Prime)
    {
        R.Prime=false;
        Changed|=R.AwaitPose();
        if (!R.Error.IsEmpty()) { bFailed=true; return false; }
        if (!R.AwaitingPose) { R.FrameTime=Dt; Send(); }
    }
    return Changed;
}

void USkateComponent::RefreshNativeCollision(FSkateRuntime& R, const FVector& At, float Yaw, bool bIdle)
{
    // Rebuild before leaving the snapshot's inner cube (60% of its half size); the rest is query margin. The ride
    // lists the meshes here, makes their triangles and builds on a background thread, and installs the completed world
    // between simulation ticks; an idle session (the rider on foot) installs it as soon as it is built.
    if (R.PendingWorld.IsValid())
    {
        if (R.PendingWorld.IsReady() || Lockstep()) R.FinishPendingWorld(!bIdle);
    }
    else if ((At-R.CollisionCentre).GetAbsMax()>R.CollisionReach && (At-R.GatherRetryAt).GetAbsMax()>2000.)
    {
        // The game thread only lists the meshes (a few ms); their triangles are made with the build (H11: the whole
        // gather took 13 ms of a frame).
        auto Job=MakeShared<FGatherJob,ESPMode::ThreadSafe>();
        CollectWorld(GetWorld(),Rider,SnapshotCentre(GetWorld(),At),At,Yaw,RailSystem,*Job,true);
        R.PendingKeep=MoveTemp(Job->Keep);
        const auto Material=R.Floor;
        R.PendingWorld=AsyncThread([Job,Material,At]() mutable -> TSharedPtr<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>
        {
            auto Result=MakeShared<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>();
            Result->Centre=Job->Centre; Result->At=At;
            FSnapshot Snapshot;
            if (!FillWorld(*Job,Snapshot,Result->Reach)) { Result->Empty=true; return Result; }
            Result->Triangles=Snapshot.Num();
            FScopedNativeFloatEnvironment FloatEnvironment;
            if(!FloatEnvironment.IsReady())
            {Result->Error="Native world floating-point environment setup failed";return Result;}
            skate_native::BuildGameplayWorld(NativeSnapshot(Snapshot),Material,Result->World,Result->Error);return Result;
        },32*1024*1024);
    }
}

void USkateComponent::PlaceBoardParts(const FTransform& DeckWorldScaled)
{
    // The parts keep their place relative to the source deck, wherever the visible deck is (under the rider, or in a
    // hand off the board). The deck's scale is uniform, so this is the riding placement composed in another order.
    const FTransform SourceDeck=RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"));
    BoardRoot->SetWorldTransform(DeckWorldScaled); Deck->SetRelativeTransform(FTransform::Identity);
    const TCHAR* TruckNames[]={TEXT("TRUCK_FRONT"),TEXT("TRUCK_BACK")};
    const TCHAR* WheelNames[]={TEXT("RIGHT_WHEELFRONT"),TEXT("LEFT_WHEELFRONT"),TEXT("RIGHT_WHEELBACK"),TEXT("LEFT_WHEELBACK")};
    // Fit the host board's mesh pivots to the source rig; preserve the native truck lean and wheel spin.
    const FTransform DeckBind=RetailRuntime->Bind(TEXT("SKATEBOARD_ROOT"));
    for (int32 I=0;I<Trucks.Num() && I<2;++I)
    {
        const FTransform TruckBind=RetailRuntime->Bind(TruckNames[I]);
        const FVector A=RetailRuntime->Bind(WheelNames[I*2]).GetLocation(),B=RetailRuntime->Bind(WheelNames[I*2+1]).GetLocation();
        const FVector Axle=(A+B)*.5;
        const float Height=FMath::Max(.1f,float(DeckBind.GetLocation().Z-1.2-Axle.Z));
        const FTransform Fit(FQuat(FVector::UpVector,I==0?0.f:PI)*DeckBind.GetRotation(),
            Axle+DeckBind.GetRotation().GetUpVector()*Height,FVector(1,FVector::Distance(A,B)/18.6,Height/5.15));
        Trucks[I]->SetWorldTransform(Fit.GetRelativeTransform(TruckBind)*RetailRuntime->Bone(TruckNames[I]).GetRelativeTransform(SourceDeck)*DeckWorldScaled);
    }
    for (int32 I=0;I<Wheels.Num() && I<4;++I)
    {
        const FTransform WheelBind=RetailRuntime->Bind(WheelNames[I]);
        // physicswheels/default/WheelRadius is 0.031 m; the host mesh radius is 2.65 cm.
        const FTransform Fit(DeckBind.GetRotation(),WheelBind.GetLocation(),FVector(3.1/2.65));
        Wheels[I]->SetWorldTransform(Fit.GetRelativeTransform(WheelBind)*RetailRuntime->Bone(WheelNames[I]).GetRelativeTransform(SourceDeck)*DeckWorldScaled);
    }
}

bool USkateComponent::PublishOffBoardPose(float Lift, bool bPlaceBoard)
{
    // Off the board (RideTransition.cpp) the Ride session's clip pose is retargeted like a ride's, without starting
    // the ride: its root is the clips' trajectory on the floor, and the board goes where the clip has it (unless it
    // lies elsewhere or flies on its own).
    if (!Ride || !Rider) return false;
    if (RetailRuntime && RetailRuntime->Worker) RetailRuntime.Reset();
    if (!RetailRuntime) { RetailRuntime=MakeShared<FSkateRuntime>(); RetailRuntime->Ready=true; RetailRuntime->State=TEXT("PhysicsGround"); }
    FSkateRuntime& O=*RetailRuntime; const FRideSession& R=*Ride;
    O.Root=R.Root; O.Bones=R.Bones; O.HasPose=true;
    if (O.Names!=R.Names) { O.Names=R.Names; O.Reference=R.Reference; }
    if (O.Bones.Num()!=O.Names.Num()) { RetailPose.Reset(); return false; }
    bOffBoardPose=true; OffBoardLift=FMath::Clamp(Lift,0.f,1.f);
    RetargetRetailPose();
    bOffBoardPose=false;
    if (RetailPose.IsEmpty()) return false;
    if (bPlaceBoard) PlaceBoardParts(OffBoardDeck);
    return true;
}

// The skin of the limbs RetargetRetailPose keeps out of the body and the ground: the vertices skinned (most) to each
// hand or the hand's half of its forearm, and to each foot or toe, 48 farthest-point picks per limb (its extremes first:
// finger and toe tips, heels, then filling between).
static void SampleLimbSkin(FSkateRuntime& Runtime,USkeletalMesh* Asset,const FReferenceSkeleton& Ref,const TArray<FTransform>& Bind,
    const int32 Roots[4],const int32 Hands[2])
{
    Runtime.LimbMesh=Asset;
    for (TArray<FSkateRuntime::FSkinPoint>& Samples : Runtime.LimbSkin) Samples.Reset();
    Runtime.bArmsValid=false;
    const FSkeletalMeshRenderData* Data=Asset->GetResourceForRendering();
    if (!Data || Data->LODRenderData.IsEmpty()) return;
    const FSkeletalMeshLODRenderData& LOD=Data->LODRenderData[0];
    const auto& Positions=LOD.StaticVertexBuffers.PositionVertexBuffer;
    const FSkinWeightVertexBuffer* Weights=LOD.GetSkinWeightVertexBuffer();
    if (!Positions.GetVertexData() || !Weights || !Weights->GetDataVertexBuffer()->GetWeightData()) return;
    TArray<TPair<int32,FVector>> All[4];
    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
    {
        const TConstArrayView<FBoneIndexType> Bones=Section.HasUnifiedBoneMap()?LOD.GetUnifiedBoneMap():MakeArrayView(Section.BoneMap);
        for (uint32 V=Section.BaseVertexIndex;V<Section.BaseVertexIndex+Section.NumVertices;++V)
        {
            int32 Bone=INDEX_NONE; uint32 Most=0;
            for (uint32 K=0;K<Weights->GetMaxBoneInfluences();++K)
            {
                const uint32 Weight=Weights->GetBoneWeight(V,K),Local=Weights->GetBoneIndex(V,K);
                if (Weight>Most && Bones.IsValidIndex(Local) && Bind.IsValidIndex(Bones[Local])) { Most=Weight; Bone=Bones[Local]; }
            }
            if (Bone<0) continue;
            const FVector Position(Positions.VertexPosition(V));
            for (int32 L=0;L<4;++L)
            {
                if (Roots[L]<0) continue;
                bool bHand=false; int32 Up=Bone;
                while (Up>Roots[L]) { bHand|=L<2 && Up==Hands[L]; Up=Ref.GetParentIndex(Up); }
                if (Up!=Roots[L]) continue;
                // The forearm's elbow half stays out: an elbow by the waist is not a hand in the thigh.
                if (L<2 && !bHand && Hands[L]>=0)
                {
                    const FVector Axis=Bind[Hands[L]].GetLocation()-Bind[Roots[L]].GetLocation();
                    if (((Position-Bind[Roots[L]].GetLocation())|Axis)<.4*Axis.SizeSquared()) break;
                }
                All[L].Add({Bone,Position});
                break;
            }
        }
    }
    for (int32 L=0;L<4;++L)
    {
        const TArray<TPair<int32,FVector>>& Points=All[L];
        if (Points.IsEmpty()) continue;
        TArray<double> Near; Near.Init(TNumericLimits<double>::Max(),Points.Num());
        const FVector Root=Bind[Roots[L]].GetLocation();
        int32 Next=0;
        for (int32 I=1;I<Points.Num();++I) if (FVector::DistSquared(Points[I].Value,Root)>FVector::DistSquared(Points[Next].Value,Root)) Next=I;
        while (Runtime.LimbSkin[L].Num()<FMath::Min(L<2?96:48,Points.Num()))
        {
            const TPair<int32,FVector> Pick=Points[Next];
            Runtime.LimbSkin[L].Add({Pick.Key,Bind[Pick.Key].InverseTransformPosition(Pick.Value)});
            double Far=-1;
            for (int32 I=0;I<Points.Num();++I)
            {
                Near[I]=FMath::Min(Near[I],FVector::DistSquared(Points[I].Value,Pick.Value));
                if (Near[I]>Far) { Far=Near[I]; Next=I; }
            }
        }
    }
}

// The rider's own pelvis, spine, chest and thigh bodies, in their bones' spaces (fitted to its skin when the physical
// rider fits them), with a bounding sphere each. A hull whose planes are not cooked yet (a body asset fitted this frame)
// counts as its box and leaves the set incomplete: it is gathered again on the next frames (up to 120 times).
static void GatherBodies(FSkateRuntime& Runtime,USkeletalMesh* Asset,UPhysicsAsset* Physics,const FReferenceSkeleton& Ref,TFunctionRef<int32(const FString&)> Index)
{
    if (Runtime.BodiesFor.Get()!=Physics || Runtime.BodiesMesh.Get()!=Asset) { Runtime.BodiesTries=0; Runtime.bArmsValid=false; }
    ++Runtime.BodiesTries;
    Runtime.BodiesFor=Physics; Runtime.BodiesMesh=Asset; Runtime.Bodies.Reset(); Runtime.bBodiesComplete=true;
    for (const TCHAR* Contract : {TEXT("pelvis"),TEXT("spine"),TEXT("spine_mid"),TEXT("chest"),TEXT("thigh_L"),TEXT("thigh_R")})
    {
        const int32 Bone=Index(Contract);
        const int32 Body=Bone>=0?Physics->FindBodyIndex(Ref.GetBoneName(Bone)):INDEX_NONE;
        if (!Physics->SkeletalBodySetups.IsValidIndex(Body) || !Physics->SkeletalBodySetups[Body]) continue;
        const FKAggregateGeom& Geom=Physics->SkeletalBodySetups[Body]->AggGeom;
        FSkateRuntime::FBody B; B.Bone=Bone;
        TArray<FSphere> Bounds;
        for (const FKConvexElem& E : Geom.ConvexElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=0; S.Local=E.GetTransform(); E.GetPlanes(S.Planes);
            Bounds.Add(FSphere(S.Local.TransformPosition(E.ElemBox.GetCenter()),E.ElemBox.GetExtent().Size()));
            if (S.Planes.IsEmpty())
            {
                // Not cooked yet: its box until it is.
                Runtime.bBodiesComplete=false;
                if (!E.ElemBox.IsValid) continue;
                S.Kind=3; S.Local=FTransform(E.ElemBox.GetCenter())*E.GetTransform(); S.Half=E.ElemBox.GetExtent();
            }
            B.Shapes.Add(MoveTemp(S));
        }
        for (const FKSphylElem& E : Geom.SphylElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=1; S.Local=E.GetTransform(); S.Half=FVector(0,0,E.Length*.5); S.Radius=E.Radius;
            Bounds.Add(FSphere(E.Center,E.Length*.5+E.Radius)); B.Shapes.Add(MoveTemp(S));
        }
        for (const FKSphereElem& E : Geom.SphereElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=2; S.Local=FTransform(E.Center); S.Radius=E.Radius;
            Bounds.Add(FSphere(E.Center,E.Radius)); B.Shapes.Add(MoveTemp(S));
        }
        for (const FKBoxElem& E : Geom.BoxElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=3; S.Local=E.GetTransform(); S.Half=FVector(E.X,E.Y,E.Z)*.5;
            Bounds.Add(FSphere(E.Center,S.Half.Size())); B.Shapes.Add(MoveTemp(S));
        }
        if (B.Shapes.IsEmpty()) continue;
        for (const FSphere& S : Bounds) B.Centre+=S.Center/Bounds.Num();
        for (const FSphere& S : Bounds) B.Reach=FMath::Max(B.Reach,FVector::Dist(B.Centre,S.Center)+S.W);
        Runtime.Bodies.Add(MoveTemp(B));
    }
    if (Runtime.bBodiesComplete || Runtime.BodiesTries==120)
    {
        FString Names;
        for (const FSkateRuntime::FBody& B : Runtime.Bodies) Names+=FString::Printf(TEXT(" %s:%d"),*Ref.GetBoneName(B.Bone).ToString(),B.Shapes.Num());
        UE_LOG(LogTemp,Display,TEXT("SKATE arms keep clear of %d bodies of %s (%s), %s after %d gathers:%s"),Runtime.Bodies.Num(),*Physics->GetName(),
            *Asset->GetName(),Runtime.bBodiesComplete?TEXT("complete"):TEXT("hulls without planes"),Runtime.BodiesTries,*Names);
    }
}

// Signed distance (bone units, below 0 inside) from a point in a body's bone space to its shapes, and the way out.
static double BodyDistance(const FSkateRuntime::FBody& Body,const FVector& Q,FVector& Out)
{
    double D=TNumericLimits<double>::Max();
    for (const FSkateRuntime::FBodyShape& S : Body.Shapes)
    {
        const FVector P=S.Local.InverseTransformPosition(Q);
        double Shape=-TNumericLimits<double>::Max(); FVector N=FVector::UpVector;
        switch (S.Kind)
        {
        case 0:
            for (const FPlane& Plane : S.Planes) if (const double Dot=Plane.PlaneDot(P); Dot>Shape) { Shape=Dot; N=FVector(Plane.X,Plane.Y,Plane.Z); }
            break;
        case 1:
        {
            const FVector Axis(0,0,FMath::Clamp(P.Z,-S.Half.Z,S.Half.Z));
            N=(P-Axis).GetSafeNormal(); Shape=(P-Axis).Size()-S.Radius;
            break;
        }
        case 2: N=P.GetSafeNormal(); Shape=P.Size()-S.Radius; break;
        default:
        {
            const FVector Excess=P.GetAbs()-S.Half,Outside=Excess.ComponentMax(FVector::ZeroVector);
            if (Outside.IsNearlyZero())
            {
                const int32 Axis=Excess.X>Excess.Y?(Excess.X>Excess.Z?0:2):(Excess.Y>Excess.Z?1:2);
                N=FVector::ZeroVector; N[Axis]=P[Axis]<0?-1.:1.; Shape=Excess[Axis];
            }
            else { N=(Outside*P.GetSignVector()).GetSafeNormal(); Shape=Outside.Size(); }
        }
        }
        if (Shape<D) { D=Shape; Out=S.Local.TransformVectorNoScale(N); }
    }
    return D;
}

// Each arm swings out about its shoulder (the whole arm, its bend kept) just far enough that its hand's and forearm's
// skin is Margin (component units) out of the rider's own body, at most 30 degrees. The swing is one abduction per arm,
// about the axis that carries a hanging arm straight out from the body's midline (across the torso, pelvis to chest), so
// it turns smoothly with the pose: no face or way out is chosen per frame. The angle needed is the smallest that clears
// every sample (a 2.5 degree scan, then the crossing found inside its step), and the arm follows it through a critically
// damped spring (half-life 0.05 s out, 0.15 s back) whose speed (170 degrees/s) and acceleration are capped, so a fast
// move may graze the body for a moment but the arm never snaps. Dt below 0 or over 0.25 s starts it afresh.
static void ClearArms(FSkateRuntime& Runtime,const FReferenceSkeleton& Ref,TArray<FTransform>& Output,const int32 Uppers[2],int32 Pelvis,int32 Chest,
    double Margin,double Dt)
{
    constexpr double Degree=UE_DOUBLE_PI/180.,Step=2.5*Degree,MaxSwing=30.*Degree;
    constexpr double RiseHalfLife=.05,FallHalfLife=.15,MaxRate=170.*Degree,MaxAccel=6000.*Degree;
    if (Pelvis<0 || Chest<0 || Uppers[0]<0 || Uppers[1]<0) return;
    const FVector Spine=(Output[Chest].GetLocation()-Output[Pelvis].GetLocation()).GetSafeNormal();
    const FVector Across=FVector::VectorPlaneProject(Output[Uppers[1]].GetLocation()-Output[Uppers[0]].GetLocation(),Spine).GetSafeNormal();
    if (Spine.IsNearlyZero() || Across.IsNearlyZero()) return;
    const bool bFresh=!Runtime.bArmsValid || Dt<0 || Dt>.25;
    for (int32 H=0;H<2;++H)
    {
        const int32 Upper=Uppers[H];
        const TArray<FSkateRuntime::FSkinPoint>& Skin=Runtime.LimbSkin[H];
        if (Skin.IsEmpty()) continue;
        const FVector Shoulder=Output[Upper].GetLocation();
        // Out from the midline on this arm's side (left shoulder to right is +Across); the axis turns -Spine toward it.
        const FVector Axis=FVector::CrossProduct(-Spine,H?Across:-Across);
        TArray<FVector,TInlineAllocator<128>> Points;
        double Arm=0;
        for (const FSkateRuntime::FSkinPoint& Point : Skin)
        {
            Points.Add(Output[Point.Bone].TransformPosition(Point.Local)-Shoulder);
            Arm=FMath::Max(Arm,Points.Last().Size());
        }
        // The bodies the arm can reach at any swing (a swing keeps each sample's distance from the shoulder).
        TArray<const FSkateRuntime::FBody*,TInlineAllocator<8>> Near;
        for (const FSkateRuntime::FBody& Body : Runtime.Bodies)
        {
            const FTransform& Frame=Output[Body.Bone];
            if (FVector::Dist(Frame.TransformPosition(Body.Centre),Shoulder)<=Arm+Body.Reach*Frame.GetMaximumAxisScale()+2.*Margin) Near.Add(&Body);
        }
        // The arm's clearance turned by Angle: the least over its samples and the bodies of the distance out of the body
        // less Margin, capped at Margin (a sample beyond a body's bounding sphere by that much counts as the cap, so the
        // cull keeps it continuous).
        const auto Clearance=[&](double Angle)
        {
            const FQuat Turn(Axis,Angle);
            double Least=Margin;
            for (const FSkateRuntime::FBody* Each : Near)
            {
                const FSkateRuntime::FBody& Body=*Each;
                const FTransform& Frame=Output[Body.Bone];
                const double Scale=Frame.GetMaximumAxisScale(),Reach=Body.Reach*Scale+2.*Margin;
                const FVector Centre=Frame.TransformPosition(Body.Centre);
                for (const FVector& Point : Points)
                {
                    const FVector P=Shoulder+Turn.RotateVector(Point);
                    if (FVector::DistSquared(P,Centre)>Reach*Reach) continue;
                    FVector Way;
                    Least=FMath::Min(Least,BodyDistance(Body,Frame.InverseTransformPosition(P),Way)*Scale-Margin);
                }
            }
            return Least;
        };
        double Need=0;
        if (double Low=Clearance(0.); Low<0)
        {
            Need=MaxSwing;
            for (double Angle=Step;Angle<=MaxSwing+1e-9;Angle+=Step)
            {
                double High=Clearance(Angle);
                if (High<0) { Low=High; continue; }
                // The crossing inside this step: halve it three times, then interpolate.
                double From=Angle-Step,To=Angle;
                for (int32 I=0;I<3;++I)
                {
                    const double Mid=(From+To)*.5,At=Clearance(Mid);
                    if (At<0) { From=Mid; Low=At; } else { To=Mid; High=At; }
                }
                Need=From+(To-From)*(-Low)/FMath::Max(High-Low,1e-9);
                break;
            }
        }
        Runtime.ArmNeed[H]=Need;
        double& Swing=Runtime.ArmSwing[H];
        double& Rate=Runtime.ArmRate[H];
        if (bFresh) { Swing=Need; Rate=0; }
        else
        {
            // A critically damped spring toward the need ((1 + wt) e^-wt halves the gap at wt = 1.678), in steps of at
            // most 1/120 s.
            for (double Left=Dt;Left>1e-6;)
            {
                const double Sub=FMath::Min(Left,1./120.),W=1.678/(Need>Swing?RiseHalfLife:FallHalfLife);
                const double Accel=FMath::Clamp(W*W*(Need-Swing)-2.*W*Rate,-MaxAccel,MaxAccel);
                Rate=FMath::Clamp(Rate+Accel*Sub,-MaxRate,MaxRate);
                Swing+=Rate*Sub;
                if (Swing<0) { Swing=0; Rate=FMath::Max(Rate,0.); }
                else if (Swing>MaxSwing) { Swing=MaxSwing; Rate=FMath::Min(Rate,0.); }
                Left-=Sub;
            }
        }
        if (Swing<=1e-6) continue;
        const FQuat Turn(Axis,Swing);
        for (int32 I=Upper;I<Ref.GetNum();++I)
        {
            int32 Above=I;
            while (Above>Upper) Above=Ref.GetParentIndex(Above);
            if (Above!=Upper) continue;
            Output[I].SetRotation(Turn*Output[I].GetRotation());
            Output[I].SetLocation(Shoulder+Turn.RotateVector(Output[I].GetLocation()-Shoulder));
        }
    }
    Runtime.bArmsValid=true;
}

void USkateComponent::RetargetRetailPose()
{
    USkeletalMeshComponent* Mesh=Rider->GetMesh();
    if (!Mesh || !Mesh->GetSkeletalMeshAsset()) return;
    const FReferenceSkeleton& Ref=Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    struct Mapping { const TCHAR* Target; const TCHAR* Source; const TCHAR* Child; };
    static const Mapping Map[]={
        {TEXT("pelvis"),TEXT("HIPS"),TEXT("SPINE")},{TEXT("spine"),TEXT("SPINE"),TEXT("SPINE1")},
        {TEXT("spine_mid"),TEXT("SPINE1"),TEXT("SPINE3")},{TEXT("chest"),TEXT("SPINE3"),TEXT("NECK")},
        {TEXT("neck"),TEXT("NECK"),TEXT("HEAD")},{TEXT("head"),TEXT("HEAD"),nullptr},
        {TEXT("clavicle_L"),TEXT("LEFTSHOULDER"),TEXT("LEFTARM")},{TEXT("upperarm_L"),TEXT("LEFTARM"),TEXT("LEFTFOREARM")},
        {TEXT("forearm_L"),TEXT("LEFTFOREARM"),TEXT("LEFTHAND")},{TEXT("hand_L"),TEXT("LEFTHAND"),nullptr},
        {TEXT("clavicle_R"),TEXT("RIGHTSHOULDER"),TEXT("RIGHTARM")},{TEXT("upperarm_R"),TEXT("RIGHTARM"),TEXT("RIGHTFOREARM")},
        {TEXT("forearm_R"),TEXT("RIGHTFOREARM"),TEXT("RIGHTHAND")},{TEXT("hand_R"),TEXT("RIGHTHAND"),nullptr},
        {TEXT("thigh_L"),TEXT("LEFTUPLEG"),TEXT("LEFTLEG")},{TEXT("shin_L"),TEXT("LEFTLEG"),TEXT("LEFTFOOT")},
        {TEXT("foot_L"),TEXT("LEFTFOOT"),TEXT("LEFTTOEBASE")},{TEXT("toe_L"),TEXT("LEFTTOEBASE"),nullptr},
        {TEXT("thigh_R"),TEXT("RIGHTUPLEG"),TEXT("RIGHTLEG")},{TEXT("shin_R"),TEXT("RIGHTLEG"),TEXT("RIGHTFOOT")},
        {TEXT("foot_R"),TEXT("RIGHTFOOT"),TEXT("RIGHTTOEBASE")},{TEXT("toe_R"),TEXT("RIGHTTOEBASE"),nullptr}
    };
    // The rider names its own bone for each contract role (ISkateRider::GetSkateBone).
    auto Index=[&](const FString& Contract){ const FName Bone=RiderApi?RiderApi->GetSkateBone(FName(*Contract)):FName(*Contract); return Bone.IsNone()?INDEX_NONE:Ref.FindBoneIndex(Bone); };
    TArray<const Mapping*> Matches; Matches.Init(nullptr,Ref.GetNum());
    for (const Mapping& M : Map) if (const int32 Bone=Index(M.Target); Bone>=0) Matches[Bone]=&M;
    TArray<FTransform> Bind,Output; Bind.SetNum(Ref.GetNum()); Output.SetNum(Ref.GetNum()); RetailPose.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I) { int32 P=Ref.GetParentIndex(I); Bind[I]=P>=0?Ref.GetRefBonePose()[I]*Bind[P]:Ref.GetRefBonePose()[I]; }
    auto Source=[&](const TCHAR* N){return RetailRuntime->Names.IndexOfByKey(FName(N));};
    const int32 Hip=Index(TEXT("pelvis")),Foot=Index(TEXT("foot_L")),SHip=Source(TEXT("HIPS")),SFoot=Source(TEXT("LEFTFOOT"));
    if (Hip<0 || Foot<0 || SHip<0 || SFoot<0) { RetailPose.Reset(); return; }
    const float Ratio=(Bind[Hip].GetLocation().Z-Bind[Foot].GetLocation().Z)*Mesh->GetComponentScale().Z /
        FMath::Max(1.,RetailRuntime->Reference[SHip].GetLocation().Z-RetailRuntime->Reference[SFoot].GetLocation().Z);
    // PhysCustom runs inside CharacterMovement's scoped move. The capsule already has the new pose, but its
    // children's cached world transforms are not propagated until the scope closes. Using that stale mesh world
    // transform adds the frame's travel to the bones a second time: at uneven frame rates the rider flickers
    // back and forth over the board. Compose from the current parent and the authored mesh-local transform.
    const FTransform MeshWorld=Mesh->GetRelativeTransform()*Rider->GetActorTransform();
    const FTransform RootToMesh=RetailRuntime->Root.GetRelativeTransform(MeshWorld);
    // Preserve sole height: the source ankle is much farther above its sole than this character's ankle. A bigger
    // board's deck is higher by its extra deck height (9.05 cm at the source's size).
    // Off the board the clips' root is on the ground: standing on the deck (OffBoardLift 1) the body rises onto the
    // visible deck, which is not scaled with the body.
    const float DeckLift=bOffBoardPose?OffBoardLift*((BoardScale()-1.f)*9.05f+(1.f-Ratio)*8.9f):(BoardScale()-1.f)*9.05f;
    const float SoleOffset=(Bind[Foot].GetLocation().Z-Bind[0].GetLocation().Z)*Mesh->GetComponentScale().Z -
        (RetailRuntime->Reference[SFoot].GetLocation().Z-RetailRuntime->Reference[0].GetLocation().Z)*Ratio+DeckLift;
    auto InMesh=[&](FTransform T){ T.ScaleTranslation(Ratio); T.AddToTranslation(FVector(0,0,SoleOffset)); return T*RootToMesh; };
    // The visible deck off the board: on the ground it is where the clip has it, grown about its contact like a
    // ridden board; held, it goes with the body's hands (scaled with the body). Between the two by its height.
    if (bOffBoardPose)
    {
        const int32 SD=Source(TEXT("SKATEBOARD_ROOT"));
        const float S=BoardScale();
        if (SD>=0)
        {
            const FTransform Clip=RetailRuntime->Bones[SD]*RetailRuntime->Root;
            const FVector Contact=Clip.GetLocation()-Clip.GetRotation().GetUpVector()*9.05;
            const FTransform Ground=Clip*FTransform(FQuat::Identity,Contact*(1.-S),FVector(S));
            FTransform Held=InMesh(RetailRuntime->Bones[SD])*MeshWorld; Held.SetScale3D(FVector(S));
            OffBoardDeck.Blend(Ground,Held,FMath::SmoothStep(15.f,45.f,float(RetailRuntime->Bones[SD].GetLocation().Z)));
        }
        else OffBoardDeck=FTransform(RetailRuntime->Root.GetRotation(),RetailRuntime->Root.GetLocation(),FVector(S));
        // A board just taken off a hand of the character's own pose eases from there (RideTransition.cpp).
        if (OffBoardDeckBlend<1.f) { const FTransform To=OffBoardDeck; OffBoardDeck.Blend(OffBoardDeckFrom,To,FMath::SmoothStep(0.f,1.f,OffBoardDeckBlend)); }
    }
    auto Frame=[](FVector Left,FVector Right,FVector Head,FVector HipP) { FVector Up=(Head-HipP).GetSafeNormal(); return FRotationMatrix::MakeFromXZ(FVector::CrossProduct(Right-Left,Up).GetSafeNormal(),Up).ToQuat(); };
    const int32 TL=Index(TEXT("thigh_L")),TR=Index(TEXT("thigh_R")),TH=Index(TEXT("head"));
    if (TL<0 || TR<0 || TH<0 || Source(TEXT("LEFTUPLEG"))<0 || Source(TEXT("RIGHTUPLEG"))<0 || Source(TEXT("HEAD"))<0)
    { RetailPose.Reset(); return; }
    // Imported meshes can carry a 180-degree facing correction. Joint names alone cannot recover it.
    const FQuat TargetFrame=FRotationMatrix::MakeFromXZ(SavedMeshRotation.UnrotateVector(FVector::ForwardVector),
        (Bind[TH].GetLocation()-Bind[Hip].GetLocation()).GetSafeNormal()).ToQuat();
    const FQuat Base=Frame(InMesh(RetailRuntime->Reference[Source(TEXT("LEFTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("RIGHTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("HEAD"))]).GetLocation(),InMesh(RetailRuntime->Reference[SHip]).GetLocation()) * TargetFrame.Inverse();
    TArray<FQuat> Fits; Fits.Init(Base,Ref.GetNum());
    TArray<FVector> Targets; Targets.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I); const Mapping* Match=Matches[I];
        if (Match && Source(Match->Source)>=0)
        {
            const int32 S=Source(Match->Source); const FTransform SB=InMesh(RetailRuntime->Reference[S]),SP=InMesh(RetailRuntime->Bones[S]);
            FQuat FitRotation=Base;
            // Hands and toes inherit the limb's reference alignment; a body-facing frame would twist them.
            if (!Match->Child && Parent>=0 && FCString::Strcmp(Match->Target,TEXT("head"))!=0) FitRotation=Fits[Parent];
            if (Match->Child && Source(Match->Child)>=0)
            {
                // A rider without the next contract bone (a spine one segment shorter) aims at the one after it.
                const TCHAR* ChildSource=Match->Child; int32 Child=INDEX_NONE;
                while (ChildSource && Child<0)
                {
                    const Mapping* Next=nullptr;
                    for (const Mapping& M : Map) if (FCString::Strcmp(M.Source,ChildSource)==0) { Next=&M; break; }
                    if (!Next) break;
                    Child=Index(Next->Target);
                    if (Child<0) ChildSource=Next->Child;
                }
                if (Child>=0 && Source(ChildSource)>=0)
                {
                    FVector A=Base.RotateVector(Bind[Child].GetLocation()-Bind[I].GetLocation());
                    FVector B=InMesh(RetailRuntime->Reference[Source(ChildSource)]).GetLocation()-SB.GetLocation();
                    // The source ankle/toe height difference is anatomical, not a toe-down foot rotation.
                    if (FCString::Strncmp(Match->Target,TEXT("foot_"),5)==0)
                    {
                        const FVector Up=RootToMesh.GetRotation().GetUpVector();
                        A=FVector::VectorPlaneProject(A,Up); B=FVector::VectorPlaneProject(B,Up);
                    }
                    FitRotation=FQuat::FindBetweenNormals(A.GetSafeNormal(),B.GetSafeNormal())*Base;
                }
            }
            const FTransform Fit(FitRotation,SB.GetLocation()-FitRotation.RotateVector(Bind[I].GetLocation()));
            Fits[I]=FitRotation;
            Output[I]=Bind[I]*Fit*SB.Inverse()*SP;
            Output[I].SetScale3D(Bind[I].GetScale3D());
        }
        else Output[I]=Parent>=0?Ref.GetRefBonePose()[I]*Output[Parent]:Ref.GetRefBonePose()[I];
        Targets[I]=Output[I].GetLocation();
        // Transfer motion, not adult bone lengths. In particular the source has an extra spine segment.
        if (Parent>=0 && I!=Hip)
            Output[I].SetLocation(Output[Parent].TransformPosition(Ref.GetRefBonePose()[I].GetLocation()));
    }
    // Preserve the source foot contacts while solving with this character's actual thigh/shin lengths.
    for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
    {
        const int32 A=Index(FString::Printf(TEXT("thigh_%s"),Side));
        const int32 B=Index(FString::Printf(TEXT("shin_%s"),Side));
        const int32 C=Index(FString::Printf(TEXT("foot_%s"),Side));
        if (A<0 || B<0 || C<0) continue;
        const FQuat FootTurn=Output[C].GetRotation();
        const FVector Pole=Targets[B]+(Targets[B]-(Targets[A]+Targets[C])*.5)*2;
        AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Targets[C],false,1.f,1.f);
        Output[C].SetRotation(FootTurn);
        // The toe remains its authored distance from the ankle; it must not stretch through the deck.
        for (int32 I=C+1;I<Ref.GetNum();++I)
            if (Ref.GetParentIndex(I)==C) Output[I]=Ref.GetRefBonePose()[I]*Output[C];
    }
    // The limbs against this rider's own body and the ground, outside bails (which keep the skin up themselves).
    if (Mode!=ESkateMode::Bail)
    {
        const int32 Roots[4]={Index(TEXT("forearm_L")),Index(TEXT("forearm_R")),Index(TEXT("foot_L")),Index(TEXT("foot_R"))};
        const int32 Hands[2]={Index(TEXT("hand_L")),Index(TEXT("hand_R"))},Uppers[2]={Index(TEXT("upperarm_L")),Index(TEXT("upperarm_R"))};
        USkeletalMesh* Asset=Mesh->GetSkeletalMeshAsset();
        if (RetailRuntime->LimbMesh.Get()!=Asset) SampleLimbSkin(*RetailRuntime,Asset,Ref,Bind,Roots,Hands);
        // A source foot steps on the source's ground plane (pushing, braking), which on this rider's proportions can be
        // under the real ground: each foot whose sole goes under the ground below it lifts out, the leg solved to it.
        if (const float Above=CVarSkateFootGround.GetValueOnGameThread(); Above>=0.f && !bOffBoardPose)
        {
            FCollisionQueryParams Query(SCENE_QUERY_STAT(SkateFootGround),false,Rider);
            for (int32 S=0;S<2;++S)
            {
                const TArray<FSkateRuntime::FSkinPoint>& Sole=RetailRuntime->LimbSkin[2+S];
                const int32 A=Index(S?TEXT("thigh_R"):TEXT("thigh_L")),B=Index(S?TEXT("shin_R"):TEXT("shin_L")),C=Roots[2+S];
                if (Sole.IsEmpty() || A<0 || B<0 || C<0) continue;
                const FVector Ankle=MeshWorld.TransformPosition(Output[C].GetLocation());
                FHitResult Hit;
                if (!GetWorld()->LineTraceSingleByChannel(Hit,Ankle+FVector(0,0,20),Ankle-FVector(0,0,80),ECC_Pawn,Query) || Hit.bStartPenetrating || Hit.ImpactNormal.Z<.5)
                    continue;
                double Under=0;
                for (const FSkateRuntime::FSkinPoint& Point : Sole)
                    Under=FMath::Max(Under,double((FVector(Hit.ImpactPoint)-MeshWorld.TransformPosition(Output[Point.Bone].TransformPosition(Point.Local)))|FVector(Hit.ImpactNormal))+Above);
                // Deeper than a sole goes is not a foot in the ground (a ledge or rail over the ankle).
                if (Under<=0 || Under>15.) continue;
                const FQuat FootTurn=Output[C].GetRotation();
                const FVector Knee=Output[B].GetLocation(),Pole=Knee+(Knee-(Output[A].GetLocation()+Output[C].GetLocation())*.5)*2;
                const FVector Target=Output[C].GetLocation()+MeshWorld.InverseTransformVector(FVector(Hit.ImpactNormal)*Under);
                AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Target,false,1.f,1.f);
                Output[C].SetRotation(FootTurn);
                for (int32 I=C+1;I<Ref.GetNum();++I)
                {
                    int32 Up=I;
                    while (Up>C) Up=Ref.GetParentIndex(Up);
                    if (Up==C) Output[I]=Ref.GetRefBonePose()[I]*Output[Ref.GetParentIndex(I)];
                }
            }
        }
        // The source's arms hang beside an adult's hips; beside wider hips and thighs the hands sink into them. Each arm
        // swings out until its hand and forearm clear the rider's own body by skate.ArmClear (ClearArms), smoothed over
        // the frames (the world's clock). A grab solves after this, so it still reaches its board.
        const double Now=GetWorld()?GetWorld()->GetTimeSeconds():0.,ArmDt=RetailRuntime->ArmTime>=0?Now-RetailRuntime->ArmTime:-1.;
        RetailRuntime->ArmTime=Now;
        if (const float Clear=CVarSkateArmClear.GetValueOnGameThread(); Clear>=0.f)
        {
            UPhysicsAsset* Physics=Mesh->GetPhysicsAsset();
            if (Physics && (RetailRuntime->BodiesFor.Get()!=Physics || RetailRuntime->BodiesMesh.Get()!=Asset || (!RetailRuntime->bBodiesComplete && RetailRuntime->BodiesTries<120))) GatherBodies(*RetailRuntime,Asset,Physics,Ref,Index);
            if (Physics && !RetailRuntime->Bodies.IsEmpty())
                ClearArms(*RetailRuntime,Ref,Output,Uppers,Index(TEXT("pelvis")),Index(TEXT("chest")),Clear/FMath::Max(Mesh->GetComponentScale().GetMax(),1e-4),ArmDt);
            else RetailRuntime->bArmsValid=false;
        }
        else RetailRuntime->bArmsValid=false;
    }
    else RetailRuntime->bArmsValid=false;
    // A grab closes the source hand on its own deck, but this arm only follows the source arm's directions at this
    // character's scale, so the hand stops short of the board with straight fingers. Where the source hand reaches
    // its deck, hold the nearest edge of the board instead (knuckles just outside it, fingers hooked under, thumb
    // over the grip tape) and solve the arm to that hand. The grip is sized by the rider's own hand.
    const int32 SDeck=Source(TEXT("SKATEBOARD_ROOT"));
    if (Mode!=ESkateMode::Bail && SDeck>=0 && Deck && Deck->GetStaticMesh())
    {
        TArray<float> Grip;
        {
            TArray<FString> Words; CVarSkateGrip.GetValueOnGameThread().ParseIntoArrayWS(Words);
            for (const FString& Word : Words) Grip.Add(FCString::Atof(*Word));
            Grip.SetNumZeroed(9);
        }
        // The deck mesh's frame is the source deck's (SM_SkateDeck: origin at the deck-top centre, nose +X).
        const FBox Box=Deck->GetStaticMesh()->GetBoundingBox();
        const double HalfWidth=Box.GetExtent().Y,HalfLength=Box.GetExtent().X,Flat=HalfLength-HalfWidth,KickStart=.675*HalfLength;
        constexpr double Concave=.9,Thickness=1.2,SourceKnuckle=9.;
        // Top of the deck's rail: the concave lifts the sides, and the kicks rise to the ends.
        auto RailTop=[&](double X){ const double T=FMath::Clamp((FMath::Abs(X)-KickStart)/(HalfLength-KickStart),0.,1.); return Concave+T*T*(Box.Max.Z-Concave); };
        // The visible deck: a bigger board's outline scales with it, the grip offsets stay at the hand's size.
        const FTransform DeckToMesh=(bOffBoardPose?OffBoardDeck:RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"))*BoardGrowth()).GetRelativeTransform(MeshWorld);
        for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
        {
            auto Target=[&](const TCHAR* Name){ return Index(FString::Printf(TEXT("%s_%s"),Name,Side)); };
            const FString SourceSide=Side[0]=='L'?TEXT("LEFT"):TEXT("RIGHT");
            const int32 Upper=Target(TEXT("upperarm")),Fore=Target(TEXT("forearm")),Hand=Target(TEXT("hand")),ThumbEnd=Target(TEXT("thumb_end"));
            const int32 SHand=Source(*(SourceSide+TEXT("HAND"))),SFore=Source(*(SourceSide+TEXT("FOREARM")));
            if (Upper<0 || Fore<0 || Hand<0 || SHand<0 || SFore<0) continue;
            // The source hand and its length axis in its deck's frame; its knuckles are about 9 cm down that axis.
            const FTransform SourceHand=RetailRuntime->Bones[SHand].GetRelativeTransform(RetailRuntime->Bones[SDeck]);
            const FTransform& SourceRef=RetailRuntime->Reference[SHand];
            const FVector Axis=SourceHand.GetRotation().RotateVector(SourceRef.GetRotation().UnrotateVector(
                (SourceRef.GetLocation()-RetailRuntime->Reference[SFore].GetLocation()).GetSafeNormal()));
            const FVector Knuckle=SourceHand.GetLocation()+Axis*SourceKnuckle;
            // The nearest point of the deck's outline (straight rails, round ends) and its outward normal.
            const double Along=FMath::Clamp(Knuckle.X,-Flat,Flat);
            FVector Out=FVector(Knuckle.X-Along,Knuckle.Y,0).GetSafeNormal();
            if (Out.IsNearlyZero()) continue;
            const FVector Edge=FVector(Along,0,0)+Out*HalfWidth;
            const float Weight=1.f-FMath::SmoothStep(4.f,20.f,float(FVector::Dist(Knuckle,Edge+FVector(0,0,RailTop(Edge.X)-Thickness*.5))));
            if (Weight<=0.f) continue;
            // Hand frame on the board: fingers down the source hand's axis, kept in the plane across the edge; palm
            // towards the deck.
            const FVector Down=(Axis-(Axis|Out)*Out).GetSafeNormal(),Palm=(-Out-((-Out)|Down)*Down).GetSafeNormal();
            const FTransform& HandBind=Bind[Hand];
            auto Local=[&](int32 Bone){ return HandBind.GetRotation().UnrotateVector(Bind[Bone].GetLocation()-HandBind.GetLocation()); };
            // The rider's own hand frame and size come from its bind. Fingers are optional in the humanoid contract:
            // with them, the hand's axis runs to the middle knuckle (or the knuckles' mean), the knuckle line crosses
            // it, the palm is on the thumb's side and a finger's width is the knuckle spacing. Without them, the hand
            // continues the forearm, its palm faces the bind's floor and its size follows the upper arm.
            TArray<int32> Knuckles,Numbers;
            for (int32 N=0;N<4;++N)
                if (const int32 K=Target(*FString::Printf(TEXT("finger_%d"),N)); K>=0) { Knuckles.Add(K); Numbers.Add(N); }
            const double UpperLength=FVector::Dist(Bind[Upper].GetLocation(),Bind[Fore].GetLocation());
            FVector KnuckleLocal=HandBind.GetRotation().UnrotateVector(HandBind.GetLocation()-Bind[Fore].GetLocation()).GetSafeNormal()*UpperLength*.45;
            double FingerWidth=UpperLength*.1;
            if (const int32 Middle=Target(TEXT("finger_1")); Middle>=0) KnuckleLocal=Local(Middle);
            else if (!Knuckles.IsEmpty())
            {
                KnuckleLocal=FVector::ZeroVector;
                for (const int32 K : Knuckles) KnuckleLocal+=Local(K)/Knuckles.Num();
            }
            const FVector LAlong=KnuckleLocal.GetSafeNormal();
            FVector LAcross=FVector::ZeroVector;
            if (Knuckles.Num()>=2)
            {
                // The knuckle line is not square to the hand's axis: square it first, or the palm normal tilts with it.
                const FVector Line=Local(Knuckles.Last())-Local(Knuckles[0]);
                LAcross=FVector::VectorPlaneProject(Line,LAlong).GetSafeNormal();
                FingerWidth=Line.Size()/(Numbers.Last()-Numbers[0]);
            }
            FVector LPalm=ThumbEnd>=0?Local(ThumbEnd):HandBind.GetRotation().UnrotateVector(FVector::DownVector);
            LPalm-=(LPalm|LAlong)*LAlong; LPalm-=(LPalm|LAcross)*LAcross; LPalm.Normalize();
            if (Down.IsNearlyZero() || Palm.IsNearlyZero() || LAlong.IsNearlyZero() || LPalm.IsNearlyZero()) continue;
            const FQuat HandInDeck=FRotationMatrix::MakeFromXY(Down,Palm).ToQuat()*FRotationMatrix::MakeFromXY(LAlong,LPalm).ToQuat().Inverse();
            const FQuat HandRotation=DeckToMesh.GetRotation()*HandInDeck;
            const double Width=FingerWidth*Mesh->GetComponentScale().Z/BoardScale();
            const FVector KnuckleTarget=DeckToMesh.TransformPosition(Edge+Out*Grip[1]*Width+FVector(0,0,RailTop(Edge.X)+Grip[0]*Width));
            const FVector Wrist=KnuckleTarget-HandRotation.RotateVector(KnuckleLocal);
            const FQuat Retargeted=Output[Hand].GetRotation();
            const FVector Pole=Targets[Fore]+(Targets[Fore]-(Targets[Upper]+Targets[Hand])*.5)*2;
            AnimationCore::SolveTwoBoneIK(Output[Upper],Output[Fore],Output[Hand],Pole,FMath::Lerp(Output[Hand].GetLocation(),Wrist,double(Weight)),false,1.f,1.f);
            Output[Hand].SetRotation(FQuat::Slerp(Retargeted,HandRotation,Weight));
            // Curl each finger towards the palm about its own knuckle axis. Finger angles are absolute (cumulative from
            // the hand's axis, so the bind's own curl does not add up); the thumb swings towards the fingers first.
            const FQuat HandNow=Output[Hand].GetRotation();
            TMap<int32,FQuat> Turns;
            for (int32 Digit=0;Digit<5;++Digit)
            {
                const bool Thumb=Digit==4;
                const int32 Joints[3]={Thumb?Target(TEXT("thumb")):Target(*FString::Printf(TEXT("finger_%d"),Digit)),
                    Thumb?Target(TEXT("thumb_tip")):Target(*FString::Printf(TEXT("finger_tip_%d"),Digit)),
                    Thumb?ThumbEnd:Target(*FString::Printf(TEXT("finger_end_%d"),Digit))};
                if (Joints[0]<0 || Joints[1]<0 || Joints[2]<0) continue;
                const FVector Segments[3]={(Local(Joints[1])-Local(Joints[0])).GetSafeNormal(),(Local(Joints[2])-Local(Joints[1])).GetSafeNormal(),(Local(Joints[2])-Local(Joints[1])).GetSafeNormal()};
                const FVector SwingAxis=(Segments[0]^LAlong).GetSafeNormal();
                const double Swing=Thumb?FMath::DegreesToRadians(Grip[5]*Weight):0.;
                const FVector Bend=(FQuat(SwingAxis,Swing).RotateVector(Segments[0])^LPalm).GetSafeNormal();
                double Applied=0,Wanted=0;
                for (int32 J=0;J<3;++J)
                {
                    const double BindAngle=FMath::RadiansToDegrees(FMath::Atan2(Segments[J]|LPalm,Segments[J]|LAlong));
                    Wanted+=Grip[Thumb?6+J:2+J];
                    const double Delta=Thumb?Grip[6+J]:(Wanted-BindAngle)-Applied; Applied+=Delta;
                    FQuat Turn=FQuat(HandNow.RotateVector(Bend),FMath::DegreesToRadians(Delta*Weight));
                    if (J==0 && Thumb) Turn=Turn*FQuat(HandNow.RotateVector(SwingAxis),Swing);
                    Turns.Add(Joints[J],Turn);
                }
            }
            for (int32 I=Hand+1;I<Ref.GetNum();++I)
            {
                int32 Up=Ref.GetParentIndex(I);
                while (Up>Hand) Up=Ref.GetParentIndex(Up);
                if (Up!=Hand) continue;
                Output[I]=Ref.GetRefBonePose()[I]*Output[Ref.GetParentIndex(I)];
                if (const FQuat* Turn=Turns.Find(I)) Output[I].SetRotation(*Turn*Output[I].GetRotation());
            }
        }
    }
    // The source physical rider has adult proportions; the character's head and clothing can extend beyond it.
    // During a bail, keep the retargeted skin above the supporting surface without changing bone lengths
    // or feeding visual corrections back into the recovered rigid-body solver.
    RetailFloorClearance=0.f;
    if (Mode==ESkateMode::Bail)
    {
        USkeletalMesh* Asset=Mesh->GetSkeletalMeshAsset();
        if (RetailRuntime->ContactMesh.Get()!=Asset)
        {
            RetailRuntime->ContactMesh=Asset; RetailRuntime->ContactVertices.Reset();
            const FSkeletalMeshRenderData* Data=Asset->GetResourceForRendering();
            if (Data && !Data->LODRenderData.IsEmpty())
            {
                const FSkeletalMeshLODRenderData& LOD=Data->LODRenderData[0];
                const auto& Positions=LOD.StaticVertexBuffers.PositionVertexBuffer;
                const FSkinWeightVertexBuffer* Weights=LOD.GetSkinWeightVertexBuffer();
                if (Positions.GetVertexData() && Weights && Weights->GetDataVertexBuffer()->GetWeightData())
                    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
                    {
                        const TConstArrayView<FBoneIndexType> Bones=Section.HasUnifiedBoneMap()?LOD.GetUnifiedBoneMap():MakeArrayView(Section.BoneMap);
                        for (uint32 V=Section.BaseVertexIndex;V<Section.BaseVertexIndex+Section.NumVertices;++V)
                        {
                            FSkateRuntime::Vertex Vertex; float Sum=0;
                            for (uint32 K=0;K<Weights->GetMaxBoneInfluences();++K)
                            {
                                const float Weight=Weights->GetBoneWeight(V,K)/65535.f;
                                if (Weight<=0) continue;
                                const uint32 LocalBone=Weights->GetBoneIndex(V,K);
                                if (!Bones.IsValidIndex(LocalBone) || !Bind.IsValidIndex(Bones[LocalBone])) continue;
                                const int32 Bone=Bones[LocalBone];
                                Vertex.Influences.Add({Bone,Bind[Bone].InverseTransformPosition(FVector(Positions.VertexPosition(V))),Weight}); Sum+=Weight;
                            }
                            if (Sum>0)
                            {
                                for (auto& Influence : Vertex.Influences) Influence.Weight/=Sum;
                                RetailRuntime->ContactVertices.Add(MoveTemp(Vertex));
                            }
                        }
                    }
            }
        }
        // Keep the lowest skinned vertex in each 12cm footprint cell. This includes shoes, hands, hair
        // and the enlarged head, and bounds the scene-query count without a coarse whole-body hover box.
        TMap<FIntPoint,FVector> Support;
        for (const auto& Vertex : RetailRuntime->ContactVertices)
        {
            FVector Point=FVector::ZeroVector;
            for (const auto& I : Vertex.Influences) Point+=Output[I.Bone].TransformPosition(I.Position)*I.Weight;
            Point=MeshWorld.TransformPosition(Point);
            const FIntPoint Cell(FMath::FloorToInt(Point.X/12.),FMath::FloorToInt(Point.Y/12.));
            FVector* Existing=Support.Find(Cell);
            if (!Existing) Support.Add(Cell,Point);
            else if (Point.Z<Existing->Z) *Existing=Point;
        }
        double Clearance=MAX_dbl;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(SkateBailSkin),true,Rider);
        for (const auto& Sample : Support)
        {
            const FVector Point=Sample.Value; FHitResult Hit;
            if (GetWorld()->LineTraceSingleByChannel(Hit,Point+FVector(0,0,200),Point-FVector(0,0,200),ECC_Pawn,Query) && Hit.ImpactNormal.Z>.25)
                Clearance=FMath::Min(Clearance,Point.Z-Hit.ImpactPoint.Z);
        }
        if (Clearance!=MAX_dbl)
        {
            const float Required=FMath::Max(0.,.5-Clearance);
            BailVisualLift=FMath::Max(Required,FMath::FInterpTo(BailVisualLift,Required,GetWorld()->GetDeltaSeconds(),14.f));
            RetailFloorClearance=Clearance+BailVisualLift;
        }
        const FVector Lift=MeshWorld.InverseTransformVector(FVector(0,0,BailVisualLift));
        for (FTransform& Bone : Output) Bone.AddToTranslation(Lift);
    }
    else BailVisualLift=0.f;
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I);
        RetailPose[I]=Parent>=0?Output[I].GetRelativeTransform(Output[Parent]):Output[I];
        RetailPose[I].NormalizeRotation();
    }
    // A blend asked for this pose (the ride's first after a mount) goes with it (RequestPoseBlendWithNextPose).
    if (PendingPoseBlend>0.f) RequestPoseBlend(PendingPoseBlend);
}

void USkateComponent::RuntimeFailure(const FString& Message)
{
    UE_LOG(LogTemp,Error,TEXT("SKATE: %s"),*Message);
    if (GEngine) GEngine->AddOnScreenDebugMessage(INDEX_NONE,10.f,FColor::Orange,Message);
}
