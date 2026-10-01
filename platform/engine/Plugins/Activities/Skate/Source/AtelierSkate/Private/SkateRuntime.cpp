#include "SkateComponent.h"
#include "Native/GameplaySession.h"
#include "Native/HostScalar.h"
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
#include "Async/Async.h"

namespace
{
    // Grab grip, tunable live: knuckle lift and outset from the deck edge (cm), finger flexion (MCP, PIP, DIP,
    // cumulative from the hand's axis), thumb swing towards the fingers and thumb flexion (degrees).
    TAutoConsoleVariable<FString> CVarSkateGrip(TEXT("skate.Grip"),TEXT("-1.5 2 25 75 10 40 40 15 10"),
        TEXT("Grab grip: lift out mcp pip dip thumbswing thumb1 thumb2 thumb3"));

    // Match the standalone runtime's startup floating environment, and restore
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
            Ready_=SavedOkay_&&std::fesetenv(FE_DFL_ENV)==0;
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
        return FString::Join(Words,TEXT(" ")).Replace(TEXT("50 50"),TEXT("50-50"));
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
        // The surface of a mesh whose collision is its own triangles, from its collision LOD.
        void AddSurface(UStaticMesh* Mesh, const FTransform& T)
        {
            if (!Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return;
            const auto& LODs=Mesh->GetRenderData()->LODResources;
            const FStaticMeshLODResources& LOD=LODs[FMath::Clamp(Mesh->LODForCollision,0,LODs.Num()-1)];
            const FPositionVertexBuffer& Positions=LOD.VertexBuffers.PositionVertexBuffer;
            if (!Positions.GetVertexData() || Positions.GetNumVertices()==0 || LOD.IndexBuffer.GetNumIndices()==0) return;
            const FIndexArrayView Indices=LOD.IndexBuffer.GetArrayView();
            for (int32 I=0; I+2<Indices.Num() && !Full(); I+=3)
            {
                FVector P[3];
                for (int32 K=0;K<3;++K) P[K]=T.TransformPosition(FVector(Positions.VertexPosition(Indices[I+K])));
                const FVector Authored=T.TransformVectorNoScale(FVector(LOD.VertexBuffers.StaticMeshVertexBuffer.VertexTangentZ(Indices[I])));
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

    /** Snapshot the static collision a walker meets near Centre: the triangles of meshes whose collision is their own
     *  surface, and the boxes, spheres, capsules and hulls of the others (a tree's trunk, not its leaves). A dense
     *  area shrinks the snapshot until it fits the budget; Reach is how far the rider may go from Centre before the
     *  next one. The native solver owns its narrow phase, BVH and contact solver. */
    bool GatherWorld(UWorld* World, ACharacter* Rider, FVector Centre, FVector Spawn, float Yaw, USkateRailSubsystem* Rails, FSnapshot& Snapshot, double& Reach)
    {
        double Radius=0;
        for (const double Try : {10000.,6000.,3500.,2000.})
        {
            Radius=Try; Snapshot.Region=FBox(Centre-FVector(Radius),Centre+FVector(Radius)); Snapshot.Points.Reset();
            for (TObjectIterator<UStaticMeshComponent> It; It && !Snapshot.Full(); ++It)
            {
                UStaticMeshComponent* C = *It;
                if (C->GetWorld()!=World || C->GetOwner()==Rider || !C->IsRegistered() || !C->IsCollisionEnabled() ||
                    C->GetCollisionResponseToChannel(ECC_Pawn)!=ECR_Block || !C->Bounds.GetBox().Intersect(Snapshot.Region)) continue;
                UStaticMesh* Mesh=C->GetStaticMesh();
                UBodySetup* Body=Mesh ? Mesh->GetBodySetup() : nullptr;
                if (!Body) continue;
                TArray<FTransform> Instances;
                if (auto* ISM=Cast<UInstancedStaticMeshComponent>(C))
                {
                    for (int32 Index : ISM->GetInstancesOverlappingBox(Snapshot.Region,true))
                    { FTransform T; if (ISM->GetInstanceTransform(Index,T,true)) Instances.Add(T); }
                }
                else Instances.Add(C->GetComponentTransform());
                const bool bSurface=Body->GetCollisionTraceFlag()==CTF_UseComplexAsSimple;
                const FKAggregateGeom& Geom=Body->AggGeom;
                for (const FTransform& T : Instances)
                {
                    if (bSurface) { Snapshot.AddSurface(Mesh,T); continue; }
                    for (const FKBoxElem& E : Geom.BoxElems) Snapshot.AddBox(E.GetTransform()*T,FVector(E.X,E.Y,E.Z)*.5);
                    for (const FKSphereElem& E : Geom.SphereElems) Snapshot.AddCapsule(E.GetTransform()*T,E.Radius,0);
                    for (const FKSphylElem& E : Geom.SphylElems) Snapshot.AddCapsule(E.GetTransform()*T,E.Radius,E.Length*.5);
                    for (const FKConvexElem& E : Geom.ConvexElems) Snapshot.AddHull(E,E.GetTransform()*T);
                }
            }
            if (!Snapshot.Full()) break;
        }
        if (Snapshot.Num()==0 || Snapshot.Full()) return false;
        Reach=Radius*.6;
        if (Rails) for (const FSkateRail& Rail : Rails->Rails) if (Rail.Bounds.Intersect(Snapshot.Region) && Rail.Points.Num()>=2)
        {
            TArray<FVector3f>& Line=Snapshot.Rails.AddDefaulted_GetRef();
            for (const FVector& P : Rail.Points) Line.Add(FVector3f(ToNative(P)));
        }
        Snapshot.Spawn=FVector3f(ToNative(Spawn)); Snapshot.Heading=-FMath::DegreesToRadians(Yaw);
        UE_LOG(LogTemp,Display,TEXT("SKATE retail collision: %d triangles, %d rails within %.0f m"),Snapshot.Num(),Snapshot.Rails.Num(),Radius/100.);
        return true;
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
        skate_native::ContactMaterial Floor;
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
                for(auto& Pending:PendingCollisions_)
                    if(!InstallWorld(Pending,Error)){Okay=false;break;}
                PendingCollisions_.clear();
                if(Okay)Okay=Session_->Step(Command.Input,Command.Dt,Error);
                if(Okay)Okay=Publish(false,Error);
                break;
            case ECommand::Configure:
                if(!std::isfinite(Command.Preferences.Trucks)){Error="Invalid equipment";Okay=false;}
                else Okay=Configure(Command.Preferences,Error);
                break;
            case ECommand::Activate:
                if(!Finite(Command.Spawn)||!Finite(Command.Velocity)||!std::isfinite(Command.Heading)
                    ||!std::isfinite(Command.Preferences.Trucks))
                {Error="Invalid spawn or equipment";Okay=false;break;}
                Okay=Configure(Command.Preferences,Error)
                    &&Session_->Activate(Command.Spawn,Command.Heading,Error);
                if(Okay){Session_->Launch(Command.Velocity);Generation_=Command.Generation;Okay=Publish(false,Error);}
                break;
            case ECommand::World:
                if(Command.Background)PendingCollisions_.push_back(std::move(Command));
                else Okay=InstallWorld(Command,Error);
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
    bool Publish(bool Ready,std::string& Error)
    {
        if(!Session_->CheckPublishedPose(Error))return false;
        const auto& G=*Session_->gameplay;FOutput Out;Out.Ready=Ready;Out.Generation=Generation_;
        auto Pose=Session_->Pose();Out.Root=Pose.root;Out.Bones=std::move(Pose.bones);
        Out.Velocity=Pose.velocity;Out.Tick=Pose.tick;Out.State=std::move(Pose.state);
        Out.Trick=G.scoring.CurrentTrick();const auto& Score=G.scoring.session.holder.State().snapshot;
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
    struct FWorldResult
    {std::optional<skate_native::PreparedGameplayWorld> World;std::string Error;};
    TUniquePtr<FNativeSkateWorker> Worker;
    bool Ready=false,PendingActivation=false,AwaitingPose=false,HasPose=false;
    uint32 Generation=0;float FrameTime=0;
    FString State=TEXT("Loading skater"),Error,Trick;
    FVector CollisionCentre=FVector::ZeroVector,Spawn=FVector::ZeroVector,Velocity=FVector::ZeroVector;
    double CollisionReach=6000.;
    TFuture<TSharedPtr<FWorldResult,ESPMode::ThreadSafe>> PendingWorld;
    skate_native::ContactMaterial Floor;
    TOptional<FVector> PendingLaunch;
    float SpawnYaw=0,Score=0,ManualBalance=0;
    uint64 Tick=0;
    FTransform Root=FTransform::Identity,Camera=FTransform::Identity;float CameraFOV=0;
    TArray<FName> Names;TArray<FTransform> Reference,Bones;
    ~FSkateRuntime() {if(PendingWorld.IsValid())PendingWorld.Wait();Worker.Reset();}
    FNativeSkateWorker::FPreferences Preferences(bool Goofy) const
    {
        const USkateSettings* S=GetDefault<USkateSettings>();FNativeSkateWorker::FPreferences P;
        P.Difficulty=TCHAR_TO_UTF8(*S->Difficulty);P.Goofy=Goofy;P.Trucks=S->TruckTightness;
        P.Pop=S->PopHeightScale;P.Spin=S->AirSpinScale;P.PushSpeed=S->PushSpeedScale;P.PushPower=S->PushPowerScale;P.VertAssist=S->VertAssist;return P;
    }
    void FinishPendingWorld(bool Background)
    {
        if(!PendingWorld.IsValid())return;
        const auto Result=PendingWorld.Get();PendingWorld={};
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
            if(Out.Bones.empty()||Out.Bones.size()>256){Error=TEXT("Invalid native skeleton");continue;}
            Root=MatrixValue(Out.Root);Bones.Reset();for(const auto& M:Out.Bones)Bones.Add(MatrixValue(M));
            Velocity=FromNative(FVector(Out.Velocity.x,Out.Velocity.y,Out.Velocity.z));State=UTF8_TO_TCHAR(Out.State.c_str());
            Trick=TrickLabel(UTF8_TO_TCHAR(Out.Trick.c_str()));Score=Out.Score;Tick=Out.Tick;ManualBalance=Out.Manual;
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
    FTransform Bone(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Bones.IsValidIndex(I) ? Bones[I]*Root : Root;
    }
    FTransform Bind(FName Name) const
    {
        int32 I=Names.IndexOfByKey(Name); return Reference.IsValidIndex(I)?Reference[I]:FTransform::Identity;
    }
};

bool USkateComponent::LaunchNativeSession(const FVector& Where,float Yaw,FString& Failure)
{
    if(!FPaths::FileExists(RuntimeFolder()/TEXT("package-manifest.json")))
    {Failure=TEXT("Native skating data is missing from this build.");return false;}
    FSnapshot Snapshot;double Reach=0;const FVector Centre=SnapshotCentre(GetWorld(),Where);
    if(!GatherWorld(GetWorld(),Rider,Centre,Where,Yaw,RailSystem,Snapshot,Reach))
    {Failure=TEXT("Skating could not load nearby collision.");return false;}
    RetailRuntime=MakeShared<FSkateRuntime>();RetailRuntime->CollisionCentre=Centre;RetailRuntime->CollisionReach=Reach;
    RetailRuntime->Worker=MakeUnique<FNativeSkateWorker>(RuntimeFolder(),NativeSnapshot(Snapshot),
        SnapshotPoint(Snapshot.Spawn),SnapshotScalar(Snapshot.Heading));
    if(!RetailRuntime->Worker->Start()){RetailRuntime.Reset();Failure=TEXT("Native skating thread could not start.");return false;}
    return true;
}
void USkateComponent::PreloadRetailRuntime()
{
    // Decoding the animation banks takes seconds; do it while the player walks, so the first mount is immediate.
    bRetailPreloaded=true;
    FString Failure;
    if (!LaunchNativeSession(Rider->GetActorLocation(),Rider->GetActorRotation().Yaw,Failure))
    { UE_LOG(LogTemp,Display,TEXT("SKATE preload skipped: %s"),*Failure); }
    else { UE_LOG(LogTemp,Display,TEXT("SKATE preload started")); }
}
void USkateComponent::PollIdleRetail()
{
    if (!RetailRuntime || bRetailActive) return;
    RetailRuntime->Poll();
    if (!RetailRuntime->Error.IsEmpty())
    { UE_LOG(LogTemp,Warning,TEXT("SKATE preloaded session failed: %s"),*RetailRuntime->Error); RetailRuntime.Reset(); }
}
bool USkateComponent::StartRetailRuntime()
{
    FString Failure;
    if (!RetailRuntime && !LaunchNativeSession(Pos,Rot.Rotator().Yaw,Failure)) { RuntimeFailure(Failure); return false; }
    RetailRuntime->FinishPendingWorld(false);
    if ((Pos-RetailRuntime->CollisionCentre).GetAbsMax()>RetailRuntime->CollisionReach)
    {
        FSnapshot Snapshot;double Reach=0;const FVector Centre=SnapshotCentre(GetWorld(),Pos);
        if(!GatherWorld(GetWorld(),Rider,Centre,Pos,Rot.Rotator().Yaw,RailSystem,Snapshot,Reach))
        {RuntimeFailure(TEXT("Skating could not refresh nearby collision."));return false;}
        RetailRuntime->SendWorld(Snapshot);RetailRuntime->CollisionCentre=Centre;RetailRuntime->CollisionReach=Reach;
    }
    RetailRuntime->Spawn=Pos; RetailRuntime->SpawnYaw=Rot.Rotator().Yaw;
    ++RetailRuntime->Generation; RetailRuntime->HasPose=false; RetailRuntime->FrameTime=0;
    RetailRuntime->PendingLaunch=Vel;
    RetailRuntime->Activate(bGoofy); bRetailActive=true; RetailPose.Reset();
    return true;
}
void USkateComponent::SuspendRetailRuntime()
{
    if (RetailRuntime) { FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Suspend;RetailRuntime->Worker->Enqueue(MoveTemp(C)); RetailRuntime->PendingActivation=false; RetailRuntime->PendingLaunch.Reset(); RetailRuntime->FrameTime=0; RetailRuntime->HasPose=false; }
    bRetailActive=false; RetailPose.Reset();
}
void USkateComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    RetailRuntime.Reset(); Super::EndPlay(Reason);
}
void USkateComponent::LaunchRetail(const FVector& V)
{
    if (!bRetailActive || !RetailRuntime) return;
    if (!RetailRuntime->Ready || RetailRuntime->PendingActivation) { RetailRuntime->PendingLaunch=V; return; }
    FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Launch;C.Velocity=NativeVector(V);RetailRuntime->Worker->Enqueue(MoveTemp(C));
}
void USkateComponent::ConfigureRetail()
{
    if(!RetailRuntime)return;FNativeSkateWorker::FCommand C;C.Kind=FNativeSkateWorker::ECommand::Configure;
    C.Preferences=RetailRuntime->Preferences(bGoofy);RetailRuntime->Worker->Enqueue(MoveTemp(C));
}

bool USkateComponent::GetRetailCamera(FTransform& Out, float& FOV) const
{
    if (!bRetailActive || !RetailRuntime || !RetailRuntime->HasPose || RetailRuntime->CameraFOV<=0) return false;
    Out=RetailRuntime->Camera; FOV=RetailRuntime->CameraFOV; return true;
}
FString USkateComponent::GetRetailState() const
{
    return bRetailActive && RetailRuntime ? FString::Printf(TEXT("%s tick=%llu"),*RetailRuntime->State,RetailRuntime->Tick) : FString();
}

void USkateComponent::StepRetailRuntime(float Dt)
{
    ReadInput(Dt);
    ComboFade=FMath::Max(0.f,ComboFade-Dt);
    if (!bRetailActive || !RetailRuntime) return;
    const bool Changed=RetailRuntime->Poll();
    if (!RetailRuntime->Error.IsEmpty())
    {
        RuntimeFailure(RetailRuntime->Error);
        StowImmediately(); RetailRuntime.Reset(); return;
    }
    if (!RetailRuntime->Ready) return;
    if (RetailRuntime->PendingActivation) { RetailRuntime->Activate(bGoofy); return; }
    RetailRuntime->FrameTime=FMath::Min(.1f,RetailRuntime->FrameTime+Dt);
    if (!RetailRuntime->AwaitingPose)
    {
    FNativeSkateWorker::FCommand Command;Command.Kind=FNativeSkateWorker::ECommand::Step;Command.Dt=RetailRuntime->FrameTime;
    // Host transfer bit is stripped by GameplaySession before Xbox sampling.
    int32 Buttons=(In.bPush?0x1000:0)|(In.bBrake?0x2000:0)|(In.bTransfer?0x0800:0);
    int32 LeftTrigger=In.bGrabLeft?255:0,RightTrigger=In.bGrabRight?255:0;
    if (!bScripted && RiderApi && !RiderApi->IsSkateInputBlocked() && !RiderApi->IsSkateMouseFree())
        if (APlayerController* PC=Cast<APlayerController>(Rider->GetController()))
        {
            if (PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Left))
            {
                Buttons|=0x4000;
                if (!PC->IsInputKeyDown(EKeys::Gamepad_FaceButton_Bottom) && !PC->IsInputKeyDown(EKeys::W) && !PC->IsInputKeyDown(EKeys::Up)) Buttons&=~0x1000;
            }
            if (PC->IsInputKeyDown(EKeys::Gamepad_LeftShoulder)) Buttons|=0x100;
            if (PC->IsInputKeyDown(EKeys::Gamepad_RightShoulder)) Buttons|=0x200;
            if (PC->IsInputKeyDown(EKeys::Gamepad_LeftThumbstick)) Buttons|=0x40;
            if (PC->IsInputKeyDown(EKeys::Gamepad_RightThumbstick)) Buttons|=0x80;
            LeftTrigger=PC->IsInputKeyDown(EKeys::Q)?255:FMath::Clamp(FMath::RoundToInt(255*PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis)),0,255);
            RightTrigger=PC->IsInputKeyDown(EKeys::E)?255:FMath::Clamp(FMath::RoundToInt(255*PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis)),0,255);
        }
    Command.Input.buttons=uint16(Buttons);Command.Input.triggers={uint8(LeftTrigger),uint8(RightTrigger)};
    auto Stick=[](FVector2D V){return std::array<std::int16_t,2>{int16(FMath::RoundToInt(FMath::Clamp(V.X,-1.,1.)*32767)),int16(FMath::RoundToInt(FMath::Clamp(V.Y,-1.,1.)*32767))};};
    // The start query requires a rear diagonal, including a nonzero angle.
    const FVector2D Left=In.bPowerslide&&Mode==ESkateMode::Ground?FVector2D(In.Left.X<0?-.6:.6,-.8):In.Left;
    Command.Input.left=Stick(Left);Command.Input.right=Stick(In.Right);RetailRuntime->Worker->Enqueue(MoveTemp(Command));
    RetailRuntime->AwaitingPose=true; RetailRuntime->FrameTime=0;
    }
    if (!Changed) return;
    const FString& S=RetailRuntime->State;
    const ESkateMode NewMode=S.Contains(TEXT("Wipeout"))?ESkateMode::Bail:S.Contains(TEXT("Grind"))?ESkateMode::Grind:
        S.Contains(TEXT("Air"))?ESkateMode::Air:ESkateMode::Ground;
    if (NewMode!=Mode)
    {
        if (NewMode==ESkateMode::Bail) { ++Bails; PlayCue(TEXT("clatter"),1,1); }
        if (NewMode==ESkateMode::Air && Mode==ESkateMode::Ground) PlayCue(TEXT("pop"),1,1);
        if (NewMode==ESkateMode::Ground && Mode==ESkateMode::Air) { ++Landed; PlayCue(TEXT("land"),.8,1); }
        if (NewMode==ESkateMode::Grind) ++Grinds;
        ++Serial; Mode=NewMode;
    }
    const FTransform DeckWorld=RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"));
    Rot=DeckWorld.GetRotation(); Pos=DeckWorld.GetLocation()-Rot.GetUpVector()*9.05; Vel=RetailRuntime->Velocity;
    // Contact jitter at rest must not alternate the stance or the HUD every frame.
    const float Along=FVector::DotProduct(Vel,Rot.GetForwardVector());
    if (FMath::Abs(Along)>15.f) bFakie=Along<0;
    RailSpeed=Vel.Size();
    bManual=Mode==ESkateMode::Ground && FMath::Abs(RetailRuntime->ManualBalance)>.0001f;
    bNoseManual=bManual && RetailRuntime->Trick.Contains(TEXT("Nose"));
    bPushing=In.bPush; bBraking=In.bBrake; bPowerslide=S==TEXT("SlideGround");
    const FVector Travel=FVector(Vel.X,Vel.Y,0).GetSafeNormal();
    SlideAngle=bPowerslide ? FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FMath::Abs(FVector::DotProduct(Travel,Rot.GetForwardVector()))),0.f,1.f))) : 0.f;
    bSlide=S==TEXT("GrindBoardslide") || S==TEXT("GrindTipslide") || S==TEXT("GrindDarkslide");
    if (ShownCombo!=RetailRuntime->Trick || Score!=FMath::RoundToInt(RetailRuntime->Score) ||
        Mode==ESkateMode::Air || Mode==ESkateMode::Grind || bManual) ComboFade=1.5f;
    ShownCombo=RetailRuntime->Trick; Score=FMath::RoundToInt(RetailRuntime->Score); LastTrickName=FName(*ShownCombo);
    Rider->SetActorLocationAndRotation(RetailRuntime->Root.GetLocation()+FVector(0,0,BodyLift),RetailRuntime->Root.GetRotation(),false,nullptr,ETeleportType::TeleportPhysics);
    Movement()->Velocity=Vel;
    BoardRoot->SetWorldTransform(DeckWorld); Deck->SetRelativeTransform(FTransform::Identity);
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
        Trucks[I]->SetWorldTransform(Fit.GetRelativeTransform(TruckBind)*RetailRuntime->Bone(TruckNames[I]));
    }
    for (int32 I=0;I<Wheels.Num() && I<4;++I)
    {
        const FTransform WheelBind=RetailRuntime->Bind(WheelNames[I]);
        // physicswheels/default/WheelRadius is 0.031 m; the host mesh radius is 2.65 cm.
        const FTransform Fit(DeckBind.GetRotation(),WheelBind.GetLocation(),FVector(3.1/2.65));
        Wheels[I]->SetWorldTransform(Fit.GetRelativeTransform(WheelBind)*RetailRuntime->Bone(WheelNames[I]));
    }
    RetargetRetailPose();
    // Rebuild before leaving the snapshot's inner cube (60% of its half size); the rest is query margin. The ride
    // gathers here, builds on a background thread, and installs the completed world between simulation ticks.
    if (RetailRuntime->PendingWorld.IsValid())
    {
        if (RetailRuntime->PendingWorld.IsReady()) RetailRuntime->FinishPendingWorld(true);
    }
    else if ((Pos-RetailRuntime->CollisionCentre).GetAbsMax()>RetailRuntime->CollisionReach)
    {
        auto Snapshot=MakeShared<FSnapshot>(); double Reach=0; const FVector Centre=SnapshotCentre(GetWorld(),Pos);
        if (GatherWorld(GetWorld(),Rider,Centre,Pos,Rot.Rotator().Yaw,RailSystem,*Snapshot,Reach))
        {
            auto Native=NativeSnapshot(*Snapshot);const auto Material=RetailRuntime->Floor;
            RetailRuntime->PendingWorld=AsyncThread([Native=std::move(Native),Material]() mutable -> TSharedPtr<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>
            {
                FScopedNativeFloatEnvironment FloatEnvironment;
                auto Result=MakeShared<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>();
                if(!FloatEnvironment.IsReady())
                {Result->Error="Native world floating-point environment setup failed";return Result;}
                skate_native::BuildGameplayWorld(Native,Material,Result->World,Result->Error);return Result;
            },32*1024*1024);
            RetailRuntime->CollisionCentre=Centre; RetailRuntime->CollisionReach=Reach;
        }
        // Nothing to snapshot (open water): keep the old one and try again 20 m on, not on every frame.
        else { RetailRuntime->CollisionCentre=Pos; RetailRuntime->CollisionReach=2000.; }
    }
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
    TArray<FTransform> Bind,Output; Bind.SetNum(Ref.GetNum()); Output.SetNum(Ref.GetNum()); RetailPose.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I) { int32 P=Ref.GetParentIndex(I); Bind[I]=P>=0?Ref.GetRefBonePose()[I]*Bind[P]:Ref.GetRefBonePose()[I]; }
    auto Source=[&](const TCHAR* N){return RetailRuntime->Names.IndexOfByKey(FName(N));};
    const int32 Hip=Ref.FindBoneIndex(TEXT("pelvis")),Foot=Ref.FindBoneIndex(TEXT("foot_L")),SHip=Source(TEXT("HIPS")),SFoot=Source(TEXT("LEFTFOOT"));
    if (Hip<0 || Foot<0 || SHip<0 || SFoot<0) { RetailPose.Reset(); return; }
    const float Ratio=(Bind[Hip].GetLocation().Z-Bind[Foot].GetLocation().Z)*Mesh->GetComponentScale().Z /
        FMath::Max(1.,RetailRuntime->Reference[SHip].GetLocation().Z-RetailRuntime->Reference[SFoot].GetLocation().Z);
    // PhysCustom runs inside CharacterMovement's scoped move. The capsule already has the new pose, but its
    // children's cached world transforms are not propagated until the scope closes. Using that stale mesh world
    // transform adds the frame's travel to the bones a second time: at uneven frame rates the rider flickers
    // back and forth over the board. Compose from the current parent and the authored mesh-local transform.
    const FTransform MeshWorld=Mesh->GetRelativeTransform()*Rider->GetActorTransform();
    const FTransform RootToMesh=RetailRuntime->Root.GetRelativeTransform(MeshWorld);
    // Preserve sole height: the source ankle is much farther above its sole than this character's ankle.
    const float SoleOffset=(Bind[Foot].GetLocation().Z-Bind[0].GetLocation().Z)*Mesh->GetComponentScale().Z -
        (RetailRuntime->Reference[SFoot].GetLocation().Z-RetailRuntime->Reference[0].GetLocation().Z)*Ratio;
    auto InMesh=[&](FTransform T){ T.ScaleTranslation(Ratio); T.AddToTranslation(FVector(0,0,SoleOffset)); return T*RootToMesh; };
    auto Frame=[](FVector Left,FVector Right,FVector Head,FVector HipP) { FVector Up=(Head-HipP).GetSafeNormal(); return FRotationMatrix::MakeFromXZ(FVector::CrossProduct(Right-Left,Up).GetSafeNormal(),Up).ToQuat(); };
    const int32 TL=Ref.FindBoneIndex(TEXT("thigh_L")),TR=Ref.FindBoneIndex(TEXT("thigh_R")),TH=Ref.FindBoneIndex(TEXT("head"));
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
        const int32 Parent=Ref.GetParentIndex(I); const Mapping* Match=nullptr;
        for (const Mapping& M : Map) if (Ref.GetBoneName(I)==FName(M.Target)) { Match=&M; break; }
        if (Match && Source(Match->Source)>=0)
        {
            const int32 S=Source(Match->Source); const FTransform SB=InMesh(RetailRuntime->Reference[S]),SP=InMesh(RetailRuntime->Bones[S]);
            FQuat FitRotation=Base;
            // Hands and toes inherit the limb's reference alignment; a body-facing frame would twist them.
            if (!Match->Child && Parent>=0 && FCString::Strcmp(Match->Target,TEXT("head"))!=0) FitRotation=Fits[Parent];
            if (Match->Child && Source(Match->Child)>=0)
            {
                int32 Child=INDEX_NONE;
                for (const Mapping& M : Map) if (FCString::Strcmp(M.Source,Match->Child)==0) { Child=Ref.FindBoneIndex(M.Target); break; }
                if (Child>=0)
                {
                    FVector A=Base.RotateVector(Bind[Child].GetLocation()-Bind[I].GetLocation());
                    FVector B=InMesh(RetailRuntime->Reference[Source(Match->Child)]).GetLocation()-SB.GetLocation();
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
        const int32 A=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("thigh_%s"),Side)));
        const int32 B=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("shin_%s"),Side)));
        const int32 C=Ref.FindBoneIndex(FName(*FString::Printf(TEXT("foot_%s"),Side)));
        if (A<0 || B<0 || C<0) continue;
        const FQuat FootTurn=Output[C].GetRotation();
        const FVector Pole=Targets[B]+(Targets[B]-(Targets[A]+Targets[C])*.5)*2;
        AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Targets[C],false,1.f,1.f);
        Output[C].SetRotation(FootTurn);
        // The toe remains its authored distance from the ankle; it must not stretch through the deck.
        for (int32 I=C+1;I<Ref.GetNum();++I)
            if (Ref.GetParentIndex(I)==C) Output[I]=Ref.GetRefBonePose()[I]*Output[C];
    }
    // A grab closes the source hand on its own deck, but this arm only follows the source arm's directions at this
    // character's scale: the hand stops 7-13 cm short of the board with straight fingers. Where the source hand
    // reaches its deck, hold the nearest edge of the board instead (knuckles just outside it, fingers hooked under,
    // thumb over the grip tape) and solve the arm to that hand.
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
        const FTransform DeckToMesh=RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT")).GetRelativeTransform(MeshWorld);
        for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
        {
            auto Target=[&](const TCHAR* Name){ return Ref.FindBoneIndex(FName(*FString::Printf(TEXT("%s_%s"),Name,Side))); };
            const FString SourceSide=Side[0]=='L'?TEXT("LEFT"):TEXT("RIGHT");
            const int32 Upper=Target(TEXT("upperarm")),Fore=Target(TEXT("forearm")),Hand=Target(TEXT("hand"));
            const int32 Index=Target(TEXT("finger_0")),Middle=Target(TEXT("finger_1")),Pinky=Target(TEXT("finger_3")),ThumbEnd=Target(TEXT("thumb_end"));
            const int32 SHand=Source(*(SourceSide+TEXT("HAND"))),SFore=Source(*(SourceSide+TEXT("FOREARM")));
            if (Upper<0 || Fore<0 || Hand<0 || Index<0 || Middle<0 || Pinky<0 || ThumbEnd<0 || SHand<0 || SFore<0) continue;
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
            // towards the deck. The character's own frame comes from its bind: knuckle line, and the thumb's side.
            const FVector Down=(Axis-(Axis|Out)*Out).GetSafeNormal(),Palm=(-Out-((-Out)|Down)*Down).GetSafeNormal();
            const FTransform& HandBind=Bind[Hand];
            auto Local=[&](int32 Bone){ return HandBind.GetRotation().UnrotateVector(Bind[Bone].GetLocation()-HandBind.GetLocation()); };
            // The knuckle line is not square to the hand's axis: square it first, or the palm normal tilts ~20 degrees.
            const FVector LAlong=Local(Middle).GetSafeNormal(),LAcross=FVector::VectorPlaneProject(Local(Pinky)-Local(Index),LAlong).GetSafeNormal();
            FVector LPalm=Local(ThumbEnd); LPalm-=(LPalm|LAlong)*LAlong; LPalm-=(LPalm|LAcross)*LAcross; LPalm.Normalize();
            if (Down.IsNearlyZero() || Palm.IsNearlyZero() || LPalm.IsNearlyZero()) continue;
            const FQuat HandInDeck=FRotationMatrix::MakeFromXY(Down,Palm).ToQuat()*FRotationMatrix::MakeFromXY(LAlong,LPalm).ToQuat().Inverse();
            const FQuat HandRotation=DeckToMesh.GetRotation()*HandInDeck;
            const FVector KnuckleTarget=DeckToMesh.TransformPosition(Edge+Out*Grip[1]+FVector(0,0,RailTop(Edge.X)+Grip[0]));
            const FVector Wrist=KnuckleTarget-HandRotation.RotateVector(Local(Middle));
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
    // The source physical rider has adult proportions; Cairo's head and clothing extend beyond it.
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
}

void USkateComponent::RuntimeFailure(const FString& Message)
{
    UE_LOG(LogTemp,Error,TEXT("SKATE: %s"),*Message);
    if (GEngine) GEngine->AddOnScreenDebugMessage(INDEX_NONE,10.f,FColor::Orange,Message);
}
