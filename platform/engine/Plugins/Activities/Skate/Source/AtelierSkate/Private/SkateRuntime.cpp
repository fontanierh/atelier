#include "SkateComponent.h"
#include "SkateRuntimeDetail.h"
#include "Simulation/GameplaySession.h"
#include "Simulation/GroundSurfaceRuntime.h"
#include "Simulation/HostScalar.h"
#include "SkatePad.h"
#include "SkatePadReader.h"
#include <deque>
#include <limits>
#include <cfenv>
#include "Engine/Engine.h"
#include "SkateRider.h"
#include "SkateSettings.h"
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
#include "Ride/RidePhysicalRider.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"

namespace SkateRuntimeDetail
{
    TAutoConsoleVariable<FString> CVarSkateGrip(TEXT("skate.Grip"),TEXT("-.705 .94 25 75 10 40 40 15 10"),
        TEXT("Grab grip: lift out (finger widths) mcp pip dip thumbswing thumb1 thumb2 thumb3 (degrees)"));
    TAutoConsoleVariable<float> CVarSkateArmClear(TEXT("skate.ArmClear"),2.f,
        TEXT("cm the hands and forearms keep clear of the rider's own pelvis, spine, chest and thighs; below 0 off"));
    TAutoConsoleVariable<float> CVarSkateFootGround(TEXT("skate.FootGround"),.5f,
        TEXT("cm each riding foot's sole stays above the ground under it; below 0 off"));
    TAutoConsoleVariable<int32> CVarSkateLockstep(TEXT("skate.Lockstep"),-1,
        TEXT("Skating waits for each step of its thread, so a replay repeats: 1 always, 0 never, -1 under a fixed step or frame rate"));
    TAutoConsoleVariable<int32> CVarSkateSurfaceDebug(TEXT("skate.SurfaceDebug"),0,
        TEXT("1 logs every colliding mesh's surface per material slot at the next collision gather (USkateSettings surfaces)."));
    TAutoConsoleVariable<int32> CVarSkateCookedSurface(TEXT("skate.CookedSurface"),0,
        TEXT("QA: 1 makes complex-as-simple meshes not yet gathered read their cooked collision triangles, as a cooked build without CPU render copies does."));
    TAutoConsoleVariable<float> CVarSkatePumpTrick(TEXT("skate.PumpTrick"),.5f,
        TEXT("m/s one intentional pump must add to show as Pump in the trick line, from the next ride"));
    TAutoConsoleVariable<int32> CVarSkateFailSimulation(TEXT("skate.FailSimulation"),0,
        TEXT("1: the simulation session under the Ride body fails on its next step (QA of the failure path); clears itself"));
}

ESkateSurface USkateSettings::SurfaceAt(const FHitResult& Hit)
{
    const USkateSettings& Settings=*GetDefault<USkateSettings>();
    if (const UStaticMeshComponent* C=Cast<UStaticMeshComponent>(Hit.GetComponent()))
    {
        const ESkateSurface Own=ComponentSurface(C,C->GetStaticMesh(),Settings);
        if (Own!=ESkateSurface::None) return Own;
        int32 Section=INDEX_NONE;
        if (const UMaterialInterface* Material=Hit.FaceIndex>=0 ? C->GetMaterialFromCollisionFaceIndex(Hit.FaceIndex,Section) : nullptr)
            if (const ESkateSurface* Found=Settings.SurfaceMaterials.Find(SurfaceKey(Material->GetName()))) return *Found;
    }
    return Settings.DefaultSurface;
}

bool USkateComponent::LaunchSimulationSession(TSharedPtr<FSkateRuntime>& Into,const FVector& Where,float Yaw,FString& Failure)
{
    const auto* Settings=GetDefault<USkateSettings>();
    if(Settings->MotionData.IsNull()||Settings->RuntimeData.IsNull())
    {Failure=TEXT("Skating data is missing from this build.");return false;}
    // The typed data loads asynchronously, once per process; the worker waits for it off the game thread.
    FSkateMotionFuture Motion=RequestSkateMotion(Settings->MotionData);
    FSkateRuntimeFuture Runtime=RequestSkateRuntime(Settings->RuntimeData);
    FSnapshot Snapshot;double Reach=0;const FVector Centre=SnapshotCentre(GetWorld(),Where);
    if(!GatherWorld(GetWorld(),Rider,Centre,Where,Yaw,RailSystem,Snapshot,Reach))
    {Failure=TEXT("Skating could not load nearby collision.");return false;}
    Into=MakeShared<FSkateRuntime>();Into->Feel=Feel;Into->CollisionCentre=Into->WantCentre=Centre;Into->CollisionReach=Reach;
    Into->Worlds=1;Into->WorldTriangles=Snapshot.Num();
    Into->Worker=MakeUnique<FSkateSimulationWorker>(SimulationSnapshot(Snapshot),
        SnapshotPoint(Snapshot.Spawn),SnapshotScalar(Snapshot.Heading),std::move(Motion),std::move(Runtime));
    if(!Into->Worker->Start()){Into.Reset();Failure=TEXT("Skating thread could not start.");return false;}
    return true;
}
void USkateComponent::PreloadSimulation()
{
    // Decoding the animation banks takes seconds; do it while the player walks, so the first mount is immediate.
    bSimulationPreloaded=true;
    PreloadRide();
    FString Failure;
    if (!LaunchSimulationSession(RideSimulation,Rider->GetActorLocation(),Rider->GetActorRotation().Yaw,Failure))
    { UE_LOG(LogTemp,Display,TEXT("SKATE preload skipped: %s"),*Failure); }
    else { UE_LOG(LogTemp,Display,TEXT("SKATE preload started")); }
}
void USkateComponent::PollIdleSimulation()
{
    // The simulation session between rides (and loading while the player walks).
    if (RideSimulation && RideSimulation->Worker && !bSimulationActive)
    {
        RideSimulation->Poll();
        if (!RideSimulation->Error.IsEmpty())
        { UE_LOG(LogTemp,Warning,TEXT("SKATE preloaded simulation ride session failed: %s"),*RideSimulation->Error); RideSimulation.Reset(); }
        // The world follows the rider on foot, built off the game thread, so a mount does not build it (H34: 190 ms
        // where the ride started out of the last one's reach). Once loaded: the build takes the session's floor.
        else if (Rider && RideSimulation->Ready) RefreshSimulationCollision(*RideSimulation,Rider->GetActorLocation(),Rider->GetActorRotation().Yaw,true);
    }
}
bool USkateComponent::StartSimulation()
{
    // ShownRuntime publishes what the rider shows; RideSimulation is the session (StartSimulationRide).
    if (!ShownRuntime) { ShownRuntime=MakeShared<FSkateRuntime>(); ShownRuntime->Ready=true; ShownRuntime->State=TEXT("PhysicsGround"); }
    EndSimulationBoardInBail(); bSimulationBail=false;
    if (!StartRide()) { RuntimeFailure(TEXT("Ride skating could not start.")); return false; }
    ShownRuntime->HasPose=false;
    if (!StartSimulationRide()) { RuntimeFailure(TEXT("Skating could not start under the Ride body.")); return false; }
    bSimulationActive=true; RiderPose.Reset();
    return true;
}
bool USkateComponent::ActivateSimulation(FSkateRuntime& R)
{
    // A world built meanwhile goes in first. The player's mount never waits for one still building (H34): the ride
    // installs it between ticks. In lockstep (QA, replays) it is waited for.
    if (R.PendingWorld.IsValid() && (R.PendingWorld.IsReady() || Lockstep())) R.FinishPendingWorld(false);
    R.WantCentre=SnapshotCentre(GetWorld(),Pos);
    // Out of reach, or in lockstep on another place's world: gathered here, so the ride starts on this place's own world
    // as every ride from here does (H54). The player's mount in reach rides on and has it rebuilt off the game thread.
    if ((Pos-R.CollisionCentre).GetAbsMax()>R.CollisionReach || (Lockstep() && !R.WantCentre.Equals(R.CollisionCentre,1.)))
    {
        R.FinishPendingWorld(false);
        FSnapshot Snapshot;double Reach=0;
        if(!GatherWorld(GetWorld(),Rider,R.WantCentre,Pos,Rot.Rotator().Yaw,RailSystem,Snapshot,Reach))
        {RuntimeFailure(TEXT("Skating could not refresh nearby collision."));return false;}
        R.SendWorld(Snapshot);R.CollisionCentre=R.WantCentre;R.CollisionReach=Reach;R.GatherRetryAt=FVector(UE_BIG_NUMBER);
        ++R.Worlds;R.WorldTriangles=Snapshot.Num();
    }
    R.Spawn=Pos; R.SpawnYaw=Rot.Rotator().Yaw; R.IdleCell=FVector(UE_BIG_NUMBER);
    ++R.Generation; R.HasPose=false; R.FrameTime=0;
    R.PendingLaunch=Vel;
    R.Activate(bGoofy);
    return true;
}
bool USkateComponent::StartSimulationRide()
{
    // The simulation's session rides from here: placed where the ride starts (Pos, Rot) with its speed (Vel). Ride
    // places the rider on the session's first pose in this same frame (GetOnBoard measures the body's lift over its
    // root), so this waits for it: a few ticks for a session preloaded while the player walked, longer on the first
    // mount of a game whose session is still loading.
    if (RideSimulation && (!RideSimulation->Error.IsEmpty() || !RideSimulation->Worker || RideSimulation->Worker->Finished())) RideSimulation.Reset();
    FString Failure;
    if (!RideSimulation && !LaunchSimulationSession(RideSimulation,Pos,Rot.Rotator().Yaw,Failure))
    { UE_LOG(LogTemp,Warning,TEXT("SKATE simulation ride: %s"),*Failure); return false; }
    FSkateRuntime& N=*RideSimulation;
    if (!ActivateSimulation(N)) return false;
    // The wait below does not tick, so typed data still loading finishes its package loads here; its decode then
    // completes on a task thread.
    CompleteSkateMotion(GetDefault<USkateSettings>()->MotionData);
    CompleteSkateRuntime(GetDefault<USkateSettings>()->RuntimeData);
    const double Started=FPlatformTime::Seconds();
    while (!N.HasPose && N.Error.IsEmpty() && !N.Worker->Finished() && FPlatformTime::Seconds()<Started+30.)
    {
        if (N.Worker->HasOutput()) N.Poll(); else FPlatformProcess::SleepNoStats(.0002f);
        if (N.Ready && N.PendingActivation) N.Activate(bGoofy);
    }
    if (!N.HasPose)
    {
        UE_LOG(LogTemp,Warning,TEXT("SKATE simulation ride did not start: %s"),N.Error.IsEmpty()?TEXT("no pose in 30 s"):*N.Error);
        RideSimulation.Reset(); return false;
    }
    ShownRuntime->Present(N); N.Prime=true;
    ShownRuntime->PumpsSeen=N.Pumps; ShownRuntime->PumpCount=0;
    UE_LOG(LogTemp,Display,TEXT("SKATE simulation ride at (%.0f, %.0f, %.0f) speed %.0f, first pose in %.1f ms"),Pos.X,Pos.Y,Pos.Z,Vel.Size(),
        (FPlatformTime::Seconds()-Started)*1000.);
    return true;
}
void USkateComponent::SuspendSimulationRide()
{
    if (!RideSimulation || !RideSimulation->Worker) return;
    FSkateSimulationWorker::FCommand C;C.Kind=FSkateSimulationWorker::ECommand::Suspend;RideSimulation->Worker->Enqueue(MoveTemp(C));
    RideSimulation->PendingActivation=false; RideSimulation->PendingLaunch.Reset(); RideSimulation->FrameTime=0; RideSimulation->HasPose=false; RideSimulation->Prime=false;
}
void USkateComponent::RelaunchSimulationRide()
{
    // A failed session is logged and dropped; a fresh one loads off the game thread while the body falls, for the get-up
    // to take the ride back on (H10: loaded at the get-up, it held the game thread 0.7-1 s).
    RuntimeFailure(RideSimulation ? RideSimulation->Error : FString());
    RideSimulation.Reset();
    FString Failure;
    if (!LaunchSimulationSession(RideSimulation,Pos,Rot.Rotator().Yaw,Failure)) { UE_LOG(LogTemp,Warning,TEXT("SKATE simulation relaunch: %s"),*Failure); }
    else { UE_LOG(LogTemp,Display,TEXT("SKATE simulation session relaunched after a failure")); }
}
void USkateComponent::BeginSimulationBoardInBail()
{
    bSimulationBoardInBail = RideSimulation && RideSimulation->Worker && RideSimulation->Error.IsEmpty()
        && PhysicalRider && PhysicalRider->GetLooseBoard();
    if (!bSimulationBoardInBail) { SuspendSimulationRide(); return; }
    SimulationBoardLast=URidePhysicalRider::ShownTransform(BoardRoot); SimulationBoardVelocity=Vel; SimulationBoardSpin=RideSpin; SimulationBoardSince=0;
    PhysicalRider->PlaceLooseBoard(SimulationBoardLast);
}
void USkateComponent::FollowSimulationBoardInBail(float Dt)
{
    if (!bSimulationBoardInBail) return;
    if (!RideSimulation || !RideSimulation->Worker || !PhysicalRider || !PhysicalRider->IsBailing() || !PhysicalRider->GetLooseBoard())
    { EndSimulationBoardInBail(); return; }
    SimulationBoardSince+=Dt;
    bool bFailed=false;
    const bool Changed=StepSimulation(*RideSimulation,Dt,true,bFailed);
    if (bFailed) { EndSimulationBoardInBail(); RelaunchSimulationRide(); return; }
    if (!Changed) return;
    // The wipeout over (the simulation's recovery teleports its rider: Teleporting, then riding), or the board further than its
    // speed takes it (a teleport all the same): the board goes on with the motion it had, on its own.
    const FTransform SimulationDeck=RideSimulation->Bone(TEXT("SKATEBOARD_ROOT"));
    const float S=BoardScale();
    const FVector Ground=SimulationDeck.GetLocation()-SimulationDeck.GetRotation().GetUpVector()*9.05;
    const FTransform Shown=SimulationDeck*FTransform(FQuat::Identity,Ground*(1.-S),FVector(S));
    const float Reach=50.f+2.f*SimulationBoardVelocity.Size()*FMath::Max(SimulationBoardSince,.1f);
    if (!RideSimulation->State.Contains(TEXT("Wipeout")) || FVector::Dist(Shown.GetLocation(),SimulationBoardLast.GetLocation())>Reach)
    { EndSimulationBoardInBail(); return; }
    SimulationBoardLast=Shown; SimulationBoardVelocity=RideSimulation->Velocity; SimulationBoardSpin=RideSimulation->Spin; SimulationBoardSince=0;
    PhysicalRider->PlaceLooseBoard(Shown);
    // Its trucks and wheels as the simulation's board has them (the wheels roll on).
    PlaceBoardParts(Shown,RideSimulation.Get());
}
void USkateComponent::EndSimulationBoardInBail()
{
    if (!bSimulationBoardInBail) return;
    bSimulationBoardInBail=false;
    if (PhysicalRider) PhysicalRider->ReleaseLooseBoard(SimulationBoardVelocity,SimulationBoardSpin);
    UE_LOG(LogTemp,Display,TEXT("SKATE bail board let go of the simulation's at %.0f cm/s (session %s)"),SimulationBoardVelocity.Size(),
        RideSimulation ? *RideSimulation->State : TEXT("gone"));
    // A failed session is dropped where it failed (RelaunchSimulationRide).
    if (RideSimulation && RideSimulation->Error.IsEmpty()) SuspendSimulationRide();
}
bool USkateComponent::SimulationStateStarts(const TCHAR* Prefix) const
{
    return ShownRuntime && ShownRuntime->State.StartsWith(Prefix);
}
FTransform USkateComponent::RideRoot() const
{
    return ShownRuntime ? ShownRuntime->Root : FTransform::Identity;
}
FVector USkateComponent::BailVelocity() const { return Vel; }
FVector USkateComponent::BailSpin() const { return RideSpin; }
// The simulation's stance (a transition clip between rides shows none: the last ride's).
bool USkateComponent::ShownFakie() const { return ShownRuntime ? ShownRuntime->Fakie : bFakie; }
bool USkateComponent::ShownSwitch() const { return ShownRuntime && ShownRuntime->Switch; }
bool USkateComponent::ShownCrouch() const
{
    // The simulation's rider rides with 80-90 cm of hips over the deck and crouches to 30-50 (measured across the QA rows).
    constexpr float CrouchedHips=60.f;
    const float Hips=ShownRuntime ? ShownRuntime->PoseMeasure.HipBoard : 0.f;
    return Hips>0.f && Hips<CrouchedHips;
}
ERideGrab USkateComponent::RideGrab() const
{
    if (Mode != ESkateMode::Air || !ShownRuntime) return ERideGrab::None;
    const FSkateHostPad Pad = ReadHostPad();
    if (!Pad.bGrabLeft && !Pad.bGrabRight) return ERideGrab::None;
    // The grab named last in the trick line is the one held. The simulation names the plain grabs by edge: the right trigger's
    // toe-side grab is Ride's Indy, the left's heel-side its Melon; until the line names one (a grab held only a moment,
    // H6), or for a grab Ride has no step-off for, the trigger held says which edge.
    ERideGrab Held = Pad.bGrabRight ? ERideGrab::Indy : ERideGrab::Melon; int32 Latest = INDEX_NONE;
    for (const TPair<const TCHAR*, ERideGrab>& Name : {TPair<const TCHAR*, ERideGrab>(TEXT("Indy"), ERideGrab::Indy), {TEXT("Melon"), ERideGrab::Melon},
        {TEXT("FS Grab"), ERideGrab::Indy}, {TEXT("BS Grab"), ERideGrab::Melon},
        {TEXT("Christ"), ERideGrab::ChristAir}, {TEXT("Tuck"), ERideGrab::TuckKnee}})
    {
        const int32 At = ShownRuntime->Trick.Find(Name.Key, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
        if (At > Latest) { Latest = At; Held = Name.Value; }
    }
    return Held;
}
void USkateComponent::SuspendSimulation()
{
    StopRide();
    EndSimulationBoardInBail(); SuspendSimulationRide(); bSimulationBail=false;
    bSimulationActive=false; RiderPose.Reset(); PadReader.Reset();
}
void USkateComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (PhysicalRider) PhysicalRider->End();
    ReleaseRootMotion();
    ShownRuntime.Reset(); RideSimulation.Reset(); PadReader.Reset(); Super::EndPlay(Reason);
}
void USkateComponent::LaunchSimulation(const FVector& V)
{
    if (!bSimulationActive || !ShownRuntime || !RideSimulation) return;
    FSkateRuntime& R=*RideSimulation;
    if (!R.Ready || R.PendingActivation) { R.PendingLaunch=V; return; }
    FSkateSimulationWorker::FCommand C;C.Kind=FSkateSimulationWorker::ECommand::Launch;C.Velocity=SimulationVector(V);R.Worker->Enqueue(MoveTemp(C));
}
bool USkateComponent::SetFeel(const FSkateFeel& NewFeel, FString& Error)
{
    if(!NewFeel.Validate(Error))return false;
    if(bFeelSet&&NewFeel==Feel)return true;
    // Every session the rider has keeps the feel (a preloaded one activates with it); a live ride takes it at once.
    Feel=NewFeel;bFeelSet=true;
    if(ShownRuntime)ShownRuntime->Feel=Feel;
    if(RideSimulation)RideSimulation->Feel=Feel;
    if(bSimulationActive)ConfigureSimulation();
    return true;
}
void USkateComponent::ConfigureSimulation()
{
    if(!ShownRuntime||!RideSimulation||!RideSimulation->Worker)return;
    FSkateSimulationWorker::FCommand C;C.Kind=FSkateSimulationWorker::ECommand::Configure;
    C.Preferences=RideSimulation->Preferences(bGoofy);RideSimulation->Worker->Enqueue(MoveTemp(C));
}

bool USkateComponent::GetSimulationCamera(FTransform& Out, float& FOV) const
{
    // A bail handed to the body has no session camera (the session waits): the character's own camera follows the body.
    if (!bSimulationActive || !ShownRuntime || !ShownRuntime->HasPose || ShownRuntime->CameraFOV<=0 || bSimulationBail) return false;
    Out=ShownRuntime->Camera; FOV=ShownRuntime->CameraFOV;
    // The player's camera (FSkateFeel): nearer or farther along the line to the rider, a wider or narrower view.
    if(Feel.CameraDistance!=1.f)
    {
        const FVector Pivot=ShownRuntime->Root.GetLocation()+FVector(0,0,90);
        Out.SetLocation(Pivot+(Out.GetLocation()-Pivot)*Feel.CameraDistance);
    }
    if(Feel.CameraFOV!=0.f)FOV=FMath::Clamp(FOV+Feel.CameraFOV,20.f,140.f);
    return true;
}
FString USkateComponent::GetSimulationState() const
{
    if (!bSimulationActive || !ShownRuntime) return FString();
    // A session that failed is gone until the body gets up (TickSimulation); the rider still shows the last simulation state.
    // cost= is the simulation's step on its own thread (mean and worst over the last second, ms), not the game thread's.
    static const skate_simulation::XboxState Idle{};
    const skate_simulation::XboxState& I=RideSimulation?RideSimulation->Sent:Idle;
    return FString::Printf(TEXT("%s tick=%llu surface=%s:%d turns=%u lock=%d bail=%d pad=%x,%d,%d,%d,%d,%d,%d world=%d:%d cost=%.3f/%.3f pump=%u,%.2f spin=%.0f wheel=%.1f %s %s arm_swing=%.1f,%.1f arm_need=%.1f,%.1f"),
        *ShownRuntime->State,ShownRuntime->Tick,*SurfaceName(ShownRuntime->Surface),ShownRuntime->Wheels,ShownRuntime->Turns,Lockstep()?1:0,bSimulationBail?1:0,I.buttons,I.triggers[0],I.triggers[1],I.left[0],I.left[1],I.right[0],I.right[1],
        RideSimulation?RideSimulation->Worlds:0,RideSimulation?RideSimulation->WorldTriangles:0,RideSimulation?RideSimulation->CostMean:0.f,RideSimulation?RideSimulation->CostWorst:0.f,
        RideSimulation?RideSimulation->Pumps:0u,RideSimulation?RideSimulation->PumpGain:0.f,ShownRuntime->AirSpin,ShownRuntime->WheelTurn(),*ShownRuntime->PoseMeasure.Describe(),PhysicalRider?*PhysicalRider->Describe():TEXT("phys=off"),
        FMath::RadiansToDegrees(ShownRuntime->ArmSwing[0]),FMath::RadiansToDegrees(ShownRuntime->ArmSwing[1]),
        FMath::RadiansToDegrees(ShownRuntime->ArmNeed[0]),FMath::RadiansToDegrees(ShownRuntime->ArmNeed[1]));
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

void USkateComponent::TickSimulation(float Dt)
{
    ReadInput(Dt);
    ComboFade=FMath::Max(0.f,ComboFade-Dt);
    if (!bSimulationActive || !ShownRuntime) return;
    // Simulation rides under Ride's body. A bail handed to the body waits for it to settle (AfterSimulationRideFrame), the
    // board going on with the session's wipeout; a get-up holds the session's controls neutral until the rider is up.
    if (CVarSkateFailSimulation.GetValueOnGameThread()>0 && RideSimulation && (!bSimulationBail || bSimulationBoardInBail))
    { CVarSkateFailSimulation->Set(0,ECVF_SetByConsole); RideSimulation->Error=TEXT("Failed on request (skate.FailSimulation)"); }
    if (bSimulationBail) { FollowSimulationBoardInBail(Dt); AfterSimulationRideFrame(Dt); return; }
    if (!RideSimulation) { RuntimeFailure(TEXT("The simulation ride session is gone.")); StowImmediately(); return; }
    bool bFailed=false;
    const bool Changed=StepSimulation(*RideSimulation,Dt,PhysicalRider && PhysicalRider->IsGettingUp(),bFailed);
    if (bFailed)
    {
        // A failed session never stows the board under a moving rider: the body falls with the momentum shown, as
        // in a wipeout, and the get-up takes the ride back on a fresh session, loaded off the game thread while the
        // body falls (H10: loaded at the get-up, it held the game thread 0.7-1 s). The failure is still logged.
        RelaunchSimulationRide();
        if (PhysicalRider && PhysicalRider->IsActive() && !PhysicalRider->IsBailing() && !PhysicalRider->IsGettingUp()
            && PhysicalRider->StartBail(Vel, RideSpin, URidePhysicalRider::ShownTransform(BoardRoot), BoardScale()))
        {
            bSimulationBail = true;
            ++Bails; ++Serial; Mode = ESkateMode::Bail; PlayCue(TEXT("clatter"), 1, 1);
            return;
        }
        StowImmediately();
        return;
    }
    if (!Changed) { AfterSimulationRideFrame(Dt); return; }
    ShownRuntime->Present(*RideSimulation);
    const FString& S=ShownRuntime->State;
    // A fallen rider getting up onto the board is still in the bail.
    const bool bRisingOntoBoard=PhysicalRider && PhysicalRider->IsGettingUp() && PhysicalRider->GetGetUpExit()==ERideGetUpExit::Board;
    const ESkateMode NewMode=bRisingOntoBoard||S.Contains(TEXT("Wipeout"))?ESkateMode::Bail:S.Contains(TEXT("Grind"))?ESkateMode::Grind:
        S.Contains(TEXT("Air"))?ESkateMode::Air:ESkateMode::Ground;
    const ESkateMode Was=Mode;
    Surface=ShownRuntime->Surface;
    if (NewMode!=Mode)
    {
        if (NewMode==ESkateMode::Bail) { ++Bails; PlayCue(TEXT("clatter"),1,1); }
        if (NewMode==ESkateMode::Air && Mode==ESkateMode::Ground) PlaySurfaceCue(TEXT("pop"),1,1);
        if (NewMode==ESkateMode::Ground && Mode==ESkateMode::Air) { ++Landed; PlaySurfaceCue(TEXT("land"),.8,1); }
        if (NewMode==ESkateMode::Grind) ++Grinds;
        ++Serial; Mode=NewMode;
    }
    if (RideSimulation) { NameSimulationSpin(Was); NameSimulationPump(); }
    const FTransform DeckWorld=ShownRuntime->Bone(TEXT("SKATEBOARD_ROOT"));
    Rot=DeckWorld.GetRotation(); Pos=DeckWorld.GetLocation()-Rot.GetUpVector()*9.05; Vel=ShownRuntime->Velocity;
    // Contact jitter at rest must not alternate the stance or the HUD every frame.
    const float Along=FVector::DotProduct(Vel,Rot.GetForwardVector());
    if (FMath::Abs(Along)>15.f) bFakie=Along<0;
    RailSpeed=Vel.Size();
    bManual=Mode==ESkateMode::Ground && FMath::Abs(ShownRuntime->ManualBalance)>.0001f;
    bNoseManual=bManual && ShownRuntime->Trick.Contains(TEXT("Nose"));
    bPushing=In.bPush; bBraking=In.bBrake; bPowerslide=S==TEXT("SlideGround");
    const FVector Travel=FVector(Vel.X,Vel.Y,0).GetSafeNormal();
    SlideAngle=bPowerslide ? FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FMath::Abs(FVector::DotProduct(Travel,Rot.GetForwardVector()))),0.f,1.f))) : 0.f;
    bSlide=S==TEXT("GrindBoardslide") || S==TEXT("GrindTipslide") || S==TEXT("GrindDarkslide") || S==TEXT("GrindLipslide");
    if (ShownCombo!=ShownRuntime->Trick || Score!=FMath::RoundToInt(ShownRuntime->Score) ||
        Mode==ESkateMode::Air || Mode==ESkateMode::Grind || bManual) ComboFade=1.5f;
    ShownCombo=ShownRuntime->Trick; Score=FMath::RoundToInt(ShownRuntime->Score); LastTrickName=FName(*ShownCombo);
    // No physics teleport: the Ride rider's simulated bodies (RidePhysicalRider) keep their own motion.
    Rider->SetActorLocationAndRotation(ShownRuntime->Root.GetLocation()+FVector(0,0,BodyLift),ShownRuntime->Root.GetRotation(),false,nullptr,ETeleportType::None);
    Movement()->Velocity=Vel;
    // A bigger board grows about the ground contact, so its wheels stay on the ground (ISkateRider::GetSkateBoardScale).
    PlaceBoardParts(DeckWorld*BoardGrowth());
    RetargetRiderPose();
    {
        // The pose the simulation shows, measured for QA.
        // The simulation's root need not point along the travel (a shove-it turns the board and the root with it, the rider
        // stays regular), so the measure takes the travel from the velocity in the root's frame, held while slow, and
        // the deck reversed when its nose points back along the root.
        FSkateRuntime& O=*ShownRuntime;
        const float RootAlong=FVector::DotProduct(O.Velocity,O.Root.GetRotation().GetForwardVector());
        if (FMath::Abs(RootAlong)>15.f) O.PoseTravel=RootAlong<0?-1.f:1.f;
        const int32 DeckBone=O.PoseMeasure.DeckBone;
        const bool bDeckBack=O.Bones.IsValidIndex(DeckBone) && O.Bones[DeckBone].GetRotation().GetForwardVector().X<0;
        O.PoseMeasure.Measure(O.Names,O.Reference,O.Bones,Dt,O.PoseTravel,bDeckBack);
    }
    RideSpin=ShownRuntime->Spin;
    if (TakeSimulationOnFoot(Dt)) return;
    AfterSimulationRideFrame(Dt);
    if (RideSimulation && !bSimulationBail) RefreshSimulationCollision(*RideSimulation,Pos,Rot.Rotator().Yaw,false);
}

void USkateComponent::NameSimulationSpin(ESkateMode Was)
{
    // The rider's turn about its own up (the pose root's; a shove-it turns only the board) between shown frames.
    FSkateRuntime& O=*ShownRuntime;
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
        // Up to 30 degrees short still counts; a regular rider
        // turning toward the board's right (negative yaw) rolling forward leads with the chest, frontside.
        const float Spun=FMath::Abs(O.AirSpin);
        if (Mode==ESkateMode::Ground && Spun>=150.f)
        {
            const int32 Half=FMath::Max(1,FMath::RoundToInt((Spun-30.f)/180.f+.0001f));
            const float Stance=(bGoofy!=O.Switch)?-1.f:1.f, Travel=O.Fakie?-1.f:1.f;
            O.SpinLabel=FString::Printf(TEXT("%s %d"),O.AirSpin*Stance*Travel<0?TEXT("FS"):TEXT("BS"),Half*180);O.SpinOf=RideSimulation->Trick;
        }
        O.AirSpin=0;
    }
    O.SpinForward=Forward;
    // The spin is shown after the trick it came with, until the simulation shows another.
    if (!O.SpinLabel.IsEmpty())
    {
        if (RideSimulation->Trick!=O.SpinOf) O.SpinLabel.Reset();
        else O.Trick=O.SpinOf.IsEmpty()?O.SpinLabel:O.SpinOf+TEXT(" / ")+O.SpinLabel;
    }
}

void USkateComponent::NameSimulationPump()
{
    // Each successful pump the session counted (GameplayPumps) joins the line after the simulation trick shown, "Pump x2"
    // when repeated, until the simulation shows another; once the line has faded, a pump starts one of its own.
    FSkateRuntime& O=*ShownRuntime;const uint32 Pumps=RideSimulation->Pumps;
    if (Pumps<O.PumpsSeen) O.PumpsSeen=Pumps;
    if (Pumps>O.PumpsSeen)
    {
        const bool bFaded=ComboFade<=0.f;
        if (bFaded || O.PumpCount==0 || RideSimulation->Trick!=O.PumpOf) { O.PumpCount=0; O.PumpOf=RideSimulation->Trick; O.PumpAlone=bFaded; }
        O.PumpCount+=int32(Pumps-O.PumpsSeen); O.PumpsSeen=Pumps;
    }
    if (O.PumpCount==0) return;
    if (RideSimulation->Trick!=O.PumpOf) { O.PumpCount=0; return; }
    const FString Label=O.PumpCount>1?FString::Printf(TEXT("Pump x%d"),O.PumpCount):FString(TEXT("Pump"));
    O.Trick=O.PumpAlone||O.Trick.IsEmpty()?Label:O.Trick+TEXT(" + ")+Label;
}

bool USkateComponent::StepSimulation(FSkateRuntime& R, float Dt, bool bNeutral, bool& bFailed)
{
    bool Changed=Lockstep() && R.AwaitingPose && R.AwaitPose();
    Changed|=R.Poll();
    if (!R.Error.IsEmpty()) { bFailed=true; return false; }
    if (!R.Ready) return false;
    if (R.PendingActivation) { R.Activate(bGoofy); return false; }
    R.FrameTime=FMath::Min(.1f,R.FrameTime+Dt);
    if (R.AwaitingPose) return Changed;
    // The canonical pad (SkatePad.h); GameplaySession takes the host transfer bit off before Xbox sampling.
    const FSkateHostPad Pad=ReadHostPad();
    const skate_simulation::XboxState Input=bNeutral?skate_simulation::XboxState{}:atelier::skate_pad::Pack(Pad);
    auto Send=[this,&R,&Input,&Pad,bNeutral]()
    {
        FSkateSimulationWorker::FCommand Command;Command.Kind=FSkateSimulationWorker::ECommand::Step;Command.Dt=R.FrameTime;
        R.Readings.clear();
        if (!bNeutral) ReadFineSticks(R,R.FrameTime,Pad);
        Command.Readings=std::move(R.Readings);R.Readings.clear();R.LastSend=FPlatformTime::Seconds();
        Command.Input=Input;R.Sent=Input;R.Worker->Enqueue(MoveTemp(Command));
        R.AwaitingPose=true; R.FrameTime=0;
    };
    Send();
    // A session that has just shown its start (StartSimulationRide) has no step in flight, so this frame would show the
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

void USkateComponent::ReadFineSticks(FSkateRuntime& R, float Dt, const FSkateHostPad& Pad)
{
    // The 120 Hz flick reading (README.md, "120 Hz flicks"): each tick's gestures read the sticks at its middle and its
    // end. Off, the reader stops; without one (or readings that disagree with the frame) the ticks read the packet.
    if (!Feel.Flick120Hz) { PadReader.Reset(); return; }
    if (!PadReader) PadReader=FSkatePadReader::Acquire();
    const FSkateFrameSticks& F=FrameSticks;
    if (!PadReader || !F.bValid || Dt<=0.f) return;
    // The step's end is now; its Dt of session time spans the wall time since the last step, unless that is far off
    // (slow motion, a hitch, the first step): then the readings of the last Dt stand in, at their own pace.
    const double Now=FPlatformTime::Seconds();
    double Span=Now-R.LastSend,Scale=Dt/FMath::Max(Span,1e-6);
    if (R.LastSend<=0. || Span>.25 || Scale<.25 || Scale>4.) { Span=Dt; Scale=1.; }
    const double Since=Now-Span;
    TArray<FSkatePadReading> Got;
    PadReader->Read(FMath::Min(Since,F.Time-.05),Got);
    // The readings are the controller the frame read only if one of the 50 ms before ReadInput is what the engine
    // read (its raw axes: GameController's, RightY negated by the viewport). Injected or replayed input, or another
    // controller, keeps the packet.
    bool bAgree=false;
    for (int32 I=0;I<Got.Num() && Got[I].Time<=F.Time+.002 && !bAgree;++I)
    {
        if (I+1<Got.Num() && Got[I+1].Time<F.Time-.05) continue;
        const FSkatePadReading& G=Got[I];
        bAgree=FMath::Abs(G.LeftX-F.Raw[0])<=.01f && FMath::Abs(G.LeftY-F.Raw[1])<=.01f
            && FMath::Abs(G.RightX-F.Raw[2])<=.01f && FMath::Abs(-G.RightY-F.Raw[3])<=.01f;
    }
    if (int8(bAgree)!=R.FineSource)
    {
        R.FineSource=int8(bAgree);
        UE_LOG(LogTemp,Display,TEXT("SKATE 120 Hz flicks read %s"),bAgree?TEXT("the controller's readings"):TEXT("each frame's sticks (no controller readings agree)"));
    }
    if (!bAgree) return;
    // Each reading as ReadInput reads the frame: the engine's massage (UPlayerInput::MassageAxisInput), the keys on
    // the left stick, the dead zone undone, the feel's stick travel, then the mouse or the space bar if larger.
    const auto Massage=[&F](int32 A,float V)
    {
        if (F.DeadZone[A]>0.f) V=V>0.f?FMath::Max(0.f,V-F.DeadZone[A])/(1.f-F.DeadZone[A]):-FMath::Max(0.f,-V-F.DeadZone[A])/(1.f-F.DeadZone[A]);
        if (F.Exponent[A]!=1.f) V=FMath::Sign(V)*FMath::Pow(FMath::Abs(V),F.Exponent[A]);
        return V*F.Scale[A];
    };
    using atelier::skate_pad::Unsqueeze;
    const bool bRetravel=Feel.StickDeadZone!=.25f || Feel.StickReach!=.95f;
    int32 First=0;
    for (int32 I=0;I<Got.Num();++I) if (Got[I].Time<=Since) First=I;
    R.Readings.reserve(Got.Num()-First);
    for (int32 I=First;I<Got.Num();++I)
    {
        const FSkatePadReading& G=Got[I];
        float LX=Unsqueeze(FMath::Clamp(Massage(0,G.LeftX)+F.KeysX,-1.f,1.f)),LY=Unsqueeze(Massage(1,G.LeftY));
        float RX=Unsqueeze(Massage(2,G.RightX)),RY=-Unsqueeze(Massage(3,-G.RightY));
        if (bRetravel)
        {
            atelier::skate_pad::Retravel(LX,LY,Feel.StickDeadZone,Feel.StickReach);
            atelier::skate_pad::Retravel(RX,RY,Feel.StickDeadZone,Feel.StickReach);
        }
        FVector2D Right(RX,RY);
        if (F.Mouse.Size()>Right.Size()) Right=F.Mouse;
        if (F.Keys.Size()>Right.Size()) Right=F.Keys;
        FSkateHostPad P=Pad;P.LeftX=LX;P.LeftY=LY;P.RightX=Right.X;P.RightY=Right.Y;
        const skate_simulation::XboxState Packed=atelier::skate_pad::Pack(P);
        skate_simulation::StickReading Reading;Reading.age=float(FMath::Max(0.,(Now-G.Time)*Scale));
        Reading.left=Packed.left;Reading.right=Packed.right;
        R.Readings.push_back(Reading);
    }
}

void USkateComponent::RefreshSimulationCollision(FSkateRuntime& R, const FVector& At, float Yaw, bool bIdle)
{
    // Rebuild before leaving the snapshot's inner cube (60% of its half size); the rest is query margin. The ride
    // lists the meshes here, makes their triangles and builds on a background thread, and installs the completed world
    // between simulation ticks; an idle session (the rider on foot) installs it as soon as it is built.
    // On foot the world also follows the rider from cell to cell (its centre is where a mount there would gather). A
    // world that lands centred elsewhere (built for a cell the rider has left) is built again.
    if (bIdle)
    {
        const FVector Cell=GridCell(At);
        if (Cell!=R.IdleCell) { R.IdleCell=Cell; R.WantCentre=SnapshotCentre(GetWorld(),At); }
    }
    if (R.PendingWorld.IsValid())
    {
        if (R.PendingWorld.IsReady() || Lockstep()) R.FinishPendingWorld(!bIdle);
        return;
    }
    if ((At-R.GatherRetryAt).GetAbsMax()<=2000.) return;
    if ((At-R.CollisionCentre).GetAbsMax()>R.CollisionReach) R.WantCentre=SnapshotCentre(GetWorld(),At);
    if (!R.WantCentre.Equals(R.CollisionCentre,1.))
    {
        // The game thread only lists the meshes (a few ms); their triangles are made with the build (H11: the whole
        // gather took 13 ms of a frame).
        auto Job=MakeShared<FGatherJob,ESPMode::ThreadSafe>();
        CollectWorld(GetWorld(),Rider,R.WantCentre,At,Yaw,RailSystem,*Job,true);
        R.PendingKeep=MoveTemp(Job->Keep);
        const auto Material=R.Floor;
        R.PendingWorld=AsyncThread([Job,Material,At]() mutable -> TSharedPtr<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>
        {
            auto Result=MakeShared<FSkateRuntime::FWorldResult,ESPMode::ThreadSafe>();
            Result->Centre=Job->Centre; Result->At=At;
            FSnapshot Snapshot;
            if (!FillWorld(*Job,Snapshot,Result->Reach)) { Result->Empty=true; return Result; }
            Result->Triangles=Snapshot.Num();
            FScopedSimulationFloatEnvironment FloatEnvironment;
            if(!FloatEnvironment.IsReady())
            {Result->Error="Simulation world floating-point environment setup failed";return Result;}
            skate_simulation::BuildGameplayWorld(SimulationSnapshot(Snapshot),Material,Result->World,Result->Error);return Result;
        },32*1024*1024);
    }
}

void USkateComponent::PlaceBoardParts(const FTransform& DeckWorldScaled, const FSkateRuntime* Source)
{
    const FSkateRuntime& From=Source?*Source:*ShownRuntime;
    // The parts keep their place relative to the source deck, wherever the visible deck is (under the rider, or in a
    // hand off the board). The deck's scale is uniform, so this is the riding placement composed in another order.
    const FTransform SourceDeck=From.Bone(TEXT("SKATEBOARD_ROOT"));
    BoardRoot->SetWorldTransform(DeckWorldScaled); Deck->SetRelativeTransform(FTransform::Identity);
    const TCHAR* TruckNames[]={TEXT("TRUCK_FRONT"),TEXT("TRUCK_BACK")};
    const TCHAR* WheelNames[]={TEXT("RIGHT_WHEELFRONT"),TEXT("LEFT_WHEELFRONT"),TEXT("RIGHT_WHEELBACK"),TEXT("LEFT_WHEELBACK")};
    // Fit the host board's mesh pivots to the source rig; preserve the simulation truck lean and wheel spin.
    const FTransform DeckBind=From.Bind(TEXT("SKATEBOARD_ROOT"));
    for (int32 I=0;I<Trucks.Num() && I<2;++I)
    {
        const FTransform TruckBind=From.Bind(TruckNames[I]);
        const FVector A=From.Bind(WheelNames[I*2]).GetLocation(),B=From.Bind(WheelNames[I*2+1]).GetLocation();
        const FVector Axle=(A+B)*.5;
        const float Height=FMath::Max(.1f,float(DeckBind.GetLocation().Z-1.2-Axle.Z));
        const FTransform Fit(FQuat(FVector::UpVector,I==0?0.f:PI)*DeckBind.GetRotation(),
            Axle+DeckBind.GetRotation().GetUpVector()*Height,FVector(1,FVector::Distance(A,B)/18.6,Height/5.15));
        Trucks[I]->SetWorldTransform(Fit.GetRelativeTransform(TruckBind)*From.Bone(TruckNames[I]).GetRelativeTransform(SourceDeck)*DeckWorldScaled);
    }
    for (int32 I=0;I<Wheels.Num() && I<4;++I)
    {
        const FTransform WheelBind=From.Bind(WheelNames[I]);
        // physicswheels/default/WheelRadius is 0.031 m; the host mesh radius is 2.65 cm.
        const FTransform Fit(DeckBind.GetRotation(),WheelBind.GetLocation(),FVector(3.1/2.65));
        Wheels[I]->SetWorldTransform(Fit.GetRelativeTransform(WheelBind)*From.Bone(WheelNames[I]).GetRelativeTransform(SourceDeck)*DeckWorldScaled);
    }
}

bool USkateComponent::PublishOffBoardPose(float Lift, bool bPlaceBoard)
{
    // Off the board (RideTransition.cpp) the clip player's pose is retargeted like a ride's, without starting the
    // ride: its root is the clips' trajectory on the floor, and the board goes where the clip has it (unless it lies
    // elsewhere or flies on its own).
    if (!Clips || !Rider) return false;
    if (!ShownRuntime) { ShownRuntime=MakeShared<FSkateRuntime>(); ShownRuntime->Ready=true; ShownRuntime->State=TEXT("PhysicsGround"); }
    FSkateRuntime& O=*ShownRuntime; const FRideClipPlayer& R=*Clips;
    O.Root=R.Root; O.Bones=R.Bones; O.HasPose=true;
    if (O.Names!=R.Names) { O.Names=R.Names; O.Reference=R.Reference; }
    if (O.Bones.Num()!=O.Names.Num()) { RiderPose.Reset(); return false; }
    bOffBoardPose=true; OffBoardLift=FMath::Clamp(Lift,0.f,1.f);
    RetargetRiderPose();
    bOffBoardPose=false;
    if (RiderPose.IsEmpty()) return false;
    if (bPlaceBoard) PlaceBoardParts(OffBoardDeck);
    return true;
}

void USkateComponent::RuntimeFailure(const FString& Message)
{
    UE_LOG(LogTemp,Error,TEXT("SKATE: %s"),*Message);
    if (GEngine) GEngine->AddOnScreenDebugMessage(INDEX_NONE,10.f,FColor::Orange,Message);
}
