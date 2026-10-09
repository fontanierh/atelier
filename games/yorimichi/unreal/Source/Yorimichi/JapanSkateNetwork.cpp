#include "JapanSkateNetwork.h"
#include "JapanActivityState.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "SkateComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/SkeletalMesh.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "Net/UnrealNetwork.h"

namespace
{
bool Newer(uint32 A, uint32 B) { return int32(A - B) > 0; }
bool ValidTransform(const FTransform& Transform)
{
    return !Transform.ContainsNaN() && Transform.GetLocation().GetAbsMax() <= 2000000. &&
        Transform.GetScale3D().GetMin() > 0. && Transform.GetScale3D().GetMax() <= 16.;
}
}

UJapanSkateNetwork::UJapanSkateNetwork()
{
    SetIsReplicatedByDefault(true);
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PostPhysics;
}

void UJapanSkateNetwork::BeginPlay()
{
    Super::BeginPlay();
    Rider = Cast<AWandererCharacter>(GetOwner());
    if (!Rider || Rider->IsNpc() || !JapanNetwork::IsOnline(GetWorld())) { SetComponentTickEnabled(false); return; }
    AddTickPrerequisiteComponent(Rider->GetMesh());
    AddTickPrerequisiteComponent(Rider->GetCharacterMovement());

}

void UJapanSkateNetwork::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME_CONDITION(UJapanSkateNetwork, Board, COND_SkipOwner);
}

void UJapanSkateNetwork::TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Dt, Type, Tick);
    if (!Rider) return;
    if (!Rider->IsLocallyControlled() && !Rider->GetSkate()->IsNetworkProxy() &&
        (Rider->GetLocalRole() == ROLE_SimulatedProxy || Rider->GetController()))
        Rider->GetSkate()->InitializeNetworkProxy(Rider);
    if (Rider->IsLocallyControlled() && Rider->GetSkate()->IsNetworkProxy()) Rider->GetSkate()->Initialize(Rider);
    if (Epoch != Rider->GetActivityEpoch())
    {
        Epoch = Rider->GetActivityEpoch();
        HostAssembly.Reset(); ViewAssembly.Reset(); Frames.Reset();
        ReceivedFrame = HostFrame = ReceivedBodies = HostBodies = 0; Bodies.Reset();
        bWarnedRoot = false; HostMode = 0;
        ArrivalClock = FJapanSkateClock(); Playout = FJapanSkatePlayout();
        Boards.Reset();
        if (Board.Sequence && !Rider->IsLocallyControlled())
        {
            // The retained board is a visible snapshot, not a newly arrived clock
            // sample. Its stamp may precede this rider epoch by several seconds.
            FJapanBoardState Snapshot = Board;
            Snapshot.Time = GetWorld()->GetTimeSeconds() - .5;
            Boards.Add(MoveTemp(Snapshot));
        }
        LastHostRoot = Rider->GetActorLocation(); LastHostRootTime = GetWorld()->GetTimeSeconds();
        if (!Rider->IsLocallyControlled()) Rider->GetSkate()->ClearNetworkPose();
    }
    if (Rider->HasAuthority() && !Rider->IsLocallyControlled() && Rider->GetNetworkActivity() == EJapanActivity::Skate &&
        GetWorld()->GetTimeSeconds() - LastHostRootTime > (HostFrame ? 3. : 8.))
    {
        UE_LOG(LogTemp, Warning, TEXT("Network skate stream timed out in epoch%u; returning to last accepted position"), Epoch);
        Rider->BeginNetworkActivity(EJapanActivity::OnFoot, true);
        return;
    }
    if (Rider->IsLocallyControlled()) Capture();
    else Show(Dt);
}

void UJapanSkateNetwork::Capture()
{
    const double Now = GetWorld()->GetTimeSeconds();
    auto* Skate = Rider->GetSkate();
    // Sender-local time is monotonic; the host maps its offset on arrival.
    // GameState clock synchronization must never retime captures mid-stream.
    const double CaptureTime = Now;
    const FTransform Deck = Skate->GetDeckWorld();
    const float Shown = Skate->GetBoardShown();
    const bool bBoardChanged = Shown != LastCapturedBoard.Shown || !Deck.Equals(LastCapturedBoard.Deck, .01);
    const double BoardInterval = Skate->GetMode() == ESkateMode::Bail ? 1./60. : .05;
    // Visible boards are smooth; a stowed board only repeats a lost final hide once per second.
    if (Now - LastBoardSent >= BoardInterval && (Shown > 0.f || bBoardChanged || Now - LastBoardSent >= 1.))
    {
        FJapanBoardState State;
        State.Sequence = ++SentBoard; State.Time = CaptureTime;
        State.Deck = Deck; State.Shown = Shown;
        LastCapturedBoard = State;
        ServerBoard(State); LastBoardSent = Now;
    }
    CaptureBodies(Now);
    const bool bHasPose = Rider->GetNetworkActivity() == EJapanActivity::Skate || !Skate->GetRiderPose().IsEmpty();
    if (bHasPose) LastActivePose = Now;
    else if (Now - LastActivePose > 1.) return; // CMC already replicates ordinary foot movement.
    // Full post-physics poses run at 30 Hz, with a separate 60 Hz stream for bail body anchors.
    if (Now - LastSent < (bHasPose ? .8/30. : .16)) return;
    LastSent = Now;
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    const auto& Pose = Mesh->GetComponentSpaceTransforms();
    if (bHasPose && (Pose.IsEmpty() || Pose.Num() > FJapanSkateChunk::MaximumBones))
    {
        if (!bWarnedSkeletonLimit) UE_LOG(LogTemp, Warning, TEXT("Network skate: skeleton has %d bones; supported range1..%d"), Pose.Num(), FJapanSkateChunk::MaximumBones);
        bWarnedSkeletonLimit = true; return;
    }
    FJapanSkateChunk Chunk;
    Chunk.Epoch = Epoch; Chunk.Frame = ++SentFrame; Chunk.Time = CaptureTime;
    Chunk.TotalBones = bHasPose ? Pose.Num() : 0;
    Chunk.Root = Rider->GetActorTransform(); Chunk.Mesh = Mesh->GetComponentTransform();
    Chunk.Deck = Deck; Chunk.Shown = Shown;
    Chunk.Mode = uint8(Skate->GetMode()); Chunk.Surface = Skate->GetNetworkSurface(); Chunk.AudioFlags = Skate->GetNetworkAudioFlags();
    Chunk.Velocity = Rider->GetCharacterMovement()->Velocity;
    const int32 Count = FMath::Max(1, FMath::DivideAndRoundUp(int32(Chunk.TotalBones), FJapanSkateChunk::BonesPerChunk));
    for (int32 I = 0; I < Count; ++I)
    {
        Chunk.Chunk = I; Chunk.Bones.Reset();
        const int32 Start = I * FJapanSkateChunk::BonesPerChunk;
        for (int32 Bone = Start; Bone < FMath::Min(Start + FJapanSkateChunk::BonesPerChunk, int32(Chunk.TotalBones)); ++Bone)
            Chunk.Bones.Add(Pose[Bone]);
        ServerPose(Chunk);
    }
}

bool UJapanSkateNetwork::ValidPeerFrame(const FJapanSkateFrame& Frame) const
{
    const auto* Mesh = Rider->GetMesh()->GetSkeletalMeshAsset();
    return Mesh && Frame.Epoch == Rider->GetActivityEpoch() && ValidTransform(Frame.Root) && ValidTransform(Frame.Mesh) && ValidTransform(Frame.Deck) &&
        FMath::IsFinite(Frame.Shown) && Frame.Shown >= 0.f && Frame.Shown <= 1.f &&
        FVector::DistSquared(Frame.Root.GetLocation(), Frame.Mesh.GetLocation()) <= FMath::Square(5000.) &&
        !Frame.Velocity.ContainsNaN() && Frame.Velocity.GetAbsMax() <= 30000. &&
        (Frame.Bones.IsEmpty() || Frame.Bones.Num() == Mesh->GetRefSkeleton().GetNum());
}

void UJapanSkateNetwork::ServerPose_Implementation(const FJapanSkateChunk& Chunk)
{
    if (!Rider || Chunk.Epoch != Rider->GetActivityEpoch() || !Newer(Chunk.Frame, HostFrame)) return;
    const auto* Rules = GetWorld()->GetGameState<AJapanGameState>();
    if (!Rules || !Rules->bTrustedSkating) return;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - RateWindow >= 1.) { RateWindow = Now; ReceivedChunks = ReceivedBoards = ReceivedBodyPackets = 0; }
    if (++ReceivedChunks > 360) return;
    FJapanSkateFrame Complete;
    if (!HostAssembly.Add(Chunk, Complete) || !ValidPeerFrame(Complete)) return;
    if (Rider->GetNetworkActivity() == EJapanActivity::Skate)
    {
        if (!AcceptsRoot(Complete.Root.GetLocation()))
        {
            if (!bWarnedRoot) UE_LOG(LogTemp, Warning, TEXT("Network skate root rejected in epoch%u: displacement%.1fcm"), Epoch, FVector::Dist(Complete.Root.GetLocation(), LastHostRoot));
            bWarnedRoot = true; return;
        }
        LastHostRoot = Complete.Root.GetLocation(); LastHostRootTime = Now;
    }
    HostFrame = Complete.Frame; ++AcceptedFrameCount;
    // Trust applies to the skate activity only. An on-foot board/carry pose cannot move the authoritative capsule.
    if (Rider->GetNetworkActivity() == EJapanActivity::Skate && !Rider->IsLocallyControlled())
    {
        Rider->SetActorTransform(Complete.Root, false, nullptr, ETeleportType::TeleportPhysics);
        Rider->GetCharacterMovement()->Velocity = Complete.Velocity;
    }
    const double ServerTime = Rules->GetServerWorldTimeSeconds();
    Complete.Time = ArrivalClock.Map(Complete.Time, ServerTime);
    HostMode = Complete.Mode;
    // Listen-host visuals consume the validated frame locally, with no network echo to its owner.
    if (!Rider->IsLocallyControlled() && GetWorld()->GetNetMode() != NM_DedicatedServer) Accept(Complete);
    for (auto It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
        if (auto* Player = Cast<AJapanPlayerController>(It->Get())) Player->SendSkateFrame(Rider, Complete);
}

void UJapanSkateNetwork::ReceivePose(const FJapanSkateChunk& Chunk)
{
    if (!Rider || Rider->IsLocallyControlled() || Chunk.Epoch != Rider->GetActivityEpoch() || !Newer(Chunk.Frame, ReceivedFrame)) return;
    FJapanSkateFrame Complete;
    if (ViewAssembly.Add(Chunk, Complete) && ValidPeerFrame(Complete)) Accept(Complete);
}

void UJapanSkateNetwork::Accept(const FJapanSkateFrame& Frame)
{
    ReceivedFrame = Frame.Frame;
    const double Arrival = GetWorld()->GetTimeSeconds();
    FJapanSkateFrame Local = Frame;
    // A newly joined client's replicated GameState clock can lag or lead while
    // loading. Presentation needs capture spacing on this observer's clock,
    // including outbound transit, rather than an assumed world-clock offset.
    Local.Time = Playout.Map(Frame.Time, Arrival);
    if (!Frames.IsEmpty() && Local.Time <= Frames.Last().Time) { ++TimestampDropCount; return; }
    ++ReceivedFrameCount;
    Playout.ReceivePose(Local.Time, Arrival, Frame.Interval);
    Frames.Add(MoveTemp(Local));
    // Keep enough history for the bounded 500 ms age plus interpolation delay
    // at 30 Hz. Six frames discarded the target during a jitter burst.
    while (Frames.Num() > 32) Frames.RemoveAt(0, 1, EAllowShrinking::No);
}

void UJapanSkateNetwork::Show(float Dt)
{
    const double Now = GetWorld()->GetTimeSeconds();
    const double RequestedTime = Playout.Advance(Now);
    if (Frames.IsEmpty()) { ShowBoard(RequestedTime); Rider->GetSkate()->ApplyNetworkAudio(0,0,0,FVector::ZeroVector,Dt); return; }
    const auto Sample = FJapanSkatePlayout::Sample(Frames, RequestedTime, [](const auto& Frame) { return double(Frame.Time); });
    const FJapanSkateFrame& A = Frames[Sample.A];
    const FJapanSkateFrame& B = Frames[Sample.B];
    if (B.Bones.IsEmpty()) { Rider->GetSkate()->ClearNetworkPose(); ShowBoard(RequestedTime); Rider->GetSkate()->ApplyNetworkAudio(0,0,0,FVector::ZeroVector,Dt); return; }
    if (Now - Playout.LastPose > FMath::Max(.5, 2.5 * Playout.Interval + .1))
    {
        if (Rider->GetNetworkActivity() == EJapanActivity::Skate) { ++HeldFrameCount; ++AfterBufferCount; }
        Rider->GetSkate()->SilenceNetworkAudio(Dt);
        if (Rider->GetNetworkActivity() == EJapanActivity::OnFoot) Rider->GetSkate()->ClearNetworkPose();
        ShowBoard(RequestedTime);
        return; // Freeze a stale skater; never extrapolate through the ground.
    }
    const float Alpha = Sample.Alpha;
    TArray<FTransform> Pose = B.Bones;
    FTransform Mesh = B.Mesh, Deck = B.Deck;
    float Shown = B.Shown;
    if (A.Bones.Num() == B.Bones.Num())
    {
        for (int32 I = 0; I < Pose.Num(); ++I) Pose[I].Blend(A.Bones[I], B.Bones[I], Alpha);
        Mesh.Blend(A.Mesh, B.Mesh, Alpha);
        Deck.Blend(A.Deck, B.Deck, Alpha); Shown = FMath::Lerp(A.Shown, B.Shown, Alpha);
    }
    ShowBodies(RequestedTime, Pose, Mesh, Deck, Shown);
    Rider->GetSkate()->ApplyNetworkBoard(Deck, Shown);
    if (Rider->GetSkate()->ApplyNetworkPose(Pose, Mesh))
    {
        if (Sample.bBefore) ++BeforeBufferCount;
        if (Sample.bAfter) ++AfterBufferCount;
        if (Alpha > 0.f && Alpha < 1.f) ++InterpolatedFrameCount; else ++HeldFrameCount;
        const auto& Applied = Alpha < .5f ? A : B;
        if (LastAppliedEpoch != Applied.Epoch || LastAppliedFrame != Applied.Frame)
        {
            ++AppliedFrameCount; LastAppliedEpoch = Applied.Epoch; LastAppliedFrame = Applied.Frame;
        }
    }
    const auto& Heard = Alpha < .5f ? A : B;
    Rider->GetSkate()->ApplyNetworkAudio(Heard.Mode, Heard.Surface, Heard.AudioFlags, FMath::Lerp(A.Velocity, B.Velocity, Alpha), Dt);
}

void UJapanSkateNetwork::ServerBoard_Implementation(const FJapanBoardState& State)
{
    if (!Rider || !Newer(State.Sequence, Board.Sequence) || !ValidTransform(State.Deck) ||
        !FMath::IsFinite(State.Time) || !FMath::IsFinite(State.Shown) || State.Shown < 0.f || State.Shown > 1.f) return;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - RateWindow >= 1.) { RateWindow = Now; ReceivedChunks = ReceivedBoards = ReceivedBodyPackets = 0; }
    if (++ReceivedBoards > 90) return;
    Board = State;
    Board.Time = ArrivalClock.Map(State.Time, Now);
    OnRep_Board();
}

void UJapanSkateNetwork::CaptureBodies(double Now)
{
    auto* Skate = Rider->GetSkate();
    if (Skate->GetMode() != ESkateMode::Bail || Now - LastBodiesSent < .8/60.) return;
    auto* Mesh = Rider->GetMesh();
    const auto* Physics = Mesh->GetPhysicsAsset();
    if (!Physics || Physics->SkeletalBodySetups.IsEmpty()) return;
    if (Physics->SkeletalBodySetups.Num() > 32)
    {
        if (!bWarnedBodyLimit) UE_LOG(LogTemp, Warning, TEXT("Network bail: %d bodies exceed packet limit; using full-pose stream"), Physics->SkeletalBodySetups.Num());
        bWarnedBodyLimit = true; return;
    }
    const auto& ComponentPose = Mesh->GetComponentSpaceTransforms();
    FJapanSkateBodies State;
    State.Pose.Epoch = Epoch; State.Pose.Frame = ++SentBodies; State.Pose.Time = Now;
    State.Pose.Root = Rider->GetActorTransform(); State.Pose.Mesh = Mesh->GetComponentTransform();
    State.Pose.Velocity = Rider->GetCharacterMovement()->Velocity;
    State.Pose.Deck = Skate->GetDeckWorld(); State.Pose.Shown = Skate->GetBoardShown();
    for (const TObjectPtr<USkeletalBodySetup>& Body : Physics->SkeletalBodySetups)
    {
        const int32 Index = Body ? Mesh->GetBoneIndex(Body->BoneName) : INDEX_NONE;
        if (Index < 0 || Index >= 256 || !ComponentPose.IsValidIndex(Index)) return;
        State.Indices.Add(uint8(Index)); State.Pose.Bones.Add(ComponentPose[Index]);
    }
    State.Pose.TotalBones = State.Indices.Num();
    ServerBodies(State); LastBodiesSent = Now;
}

bool UJapanSkateNetwork::ValidBodies(const FJapanSkateBodies& State) const
{
    const auto* Mesh = Rider->GetMesh()->GetSkeletalMeshAsset();
    if (!Mesh || State.Pose.Epoch != Rider->GetActivityEpoch() || State.Pose.Chunk != 0 ||
        State.Indices.IsEmpty() || State.Indices.Num() > 32 || State.Indices.Num() != State.Pose.Bones.Num() ||
        !ValidTransform(State.Pose.Root) || !ValidTransform(State.Pose.Mesh) || !ValidTransform(State.Pose.Deck) ||
        !FMath::IsFinite(State.Pose.Shown) || State.Pose.Shown < 0.f || State.Pose.Shown > 1.f) return false;
    bool Used[256] = {};
    for (uint8 Index : State.Indices)
    {
        if (Index >= Mesh->GetRefSkeleton().GetNum() || Used[Index]) return false;
        Used[Index] = true;
    }
    return true;
}

void UJapanSkateNetwork::ServerBodies_Implementation(const FJapanSkateBodies& State)
{
    if (!Rider || Rider->GetNetworkActivity() != EJapanActivity::Skate || !Newer(State.Pose.Frame, HostBodies) || !ValidBodies(State)) return;
    const auto* Rules = GetWorld()->GetGameState<AJapanGameState>();
    if (!Rules || !Rules->bTrustedSkating) return;
    const double Now = GetWorld()->GetTimeSeconds();
    if (Now - RateWindow >= 1.) { RateWindow = Now; ReceivedChunks = ReceivedBoards = ReceivedBodyPackets = 0; }
    if (++ReceivedBodyPackets > 90) return;
    HostBodies = State.Pose.Frame;
    FJapanSkateBodies Relay = State;
    Relay.Pose.Time = ArrivalClock.Map(State.Pose.Time, Now);
    if (GetWorld()->GetNetMode() != NM_DedicatedServer) ReceiveBodies(Relay);
    for (auto It = GetWorld()->GetPlayerControllerIterator(); It; ++It)
        if (auto* Player = Cast<AJapanPlayerController>(It->Get())) Player->SendSkateBodies(Rider, Relay);
}

void UJapanSkateNetwork::ReceiveBodies(const FJapanSkateBodies& State)
{
    if (!Rider || Rider->IsLocallyControlled() || !Newer(State.Pose.Frame, ReceivedBodies) || !ValidBodies(State)) return;
    ReceivedBodies = State.Pose.Frame;
    FJapanSkateBodies Local = State;
    Local.Pose.Time = Playout.Map(State.Pose.Time, GetWorld()->GetTimeSeconds());
    if (!Bodies.IsEmpty() && Local.Pose.Time <= Bodies.Last().Pose.Time) { ++TimestampDropCount; return; }
    Bodies.Add(MoveTemp(Local));
    while (Bodies.Num() > 64) Bodies.RemoveAt(0, 1, EAllowShrinking::No);
}

void UJapanSkateNetwork::ShowBodies(double ShowAt, TArray<FTransform>& Pose, FTransform& Mesh, FTransform& Deck, float& Shown)
{
    if (Bodies.IsEmpty() || Pose.IsEmpty()) return;
    const auto Sample = FJapanSkatePlayout::Sample(Bodies, ShowAt, [](const auto& Frame) { return double(Frame.Pose.Time); });
    const auto& A = Bodies[Sample.A]; const auto& B = Bodies[Sample.B];
    if (!FJapanSkatePlayout::CanApplyBodies(Sample, ShowAt, A.Pose.Time, B.Pose.Time) || A.Indices != B.Indices) return;
    const float Alpha = Sample.Alpha;
    const auto& Skeleton = Rider->GetMesh()->GetSkeletalMeshAsset()->GetRefSkeleton();
    TArray<FTransform> Local; Local.SetNum(Pose.Num());
    for (int32 I = 0; I < Pose.Num(); ++I)
    {
        const int32 Parent = Skeleton.GetParentIndex(I);
        Local[I] = Parent < 0 ? Pose[I] : Pose[I].GetRelativeTransform(Pose[Parent]);
    }
    int32 BodyForBone[256]; for (int32& Body : BodyForBone) Body = INDEX_NONE;
    for (int32 I = 0; I < B.Indices.Num(); ++I) BodyForBone[B.Indices[I]] = I;
    for (int32 I = 0; I < Pose.Num(); ++I)
    {
        const int32 Body = BodyForBone[I], Parent = Skeleton.GetParentIndex(I);
        if (Body >= 0) Pose[I].Blend(A.Pose.Bones[Body], B.Pose.Bones[Body], Alpha);
        else if (Parent >= 0) Pose[I] = Local[I] * Pose[Parent];
    }
    Mesh.Blend(A.Pose.Mesh, B.Pose.Mesh, Alpha);
    Deck.Blend(A.Pose.Deck, B.Pose.Deck, Alpha); Shown = FMath::Lerp(A.Pose.Shown, B.Pose.Shown, Alpha);
}

void UJapanSkateNetwork::OnRep_Board()
{
    if (!Boards.IsEmpty() && !Newer(Board.Sequence, Boards.Last().Sequence)) return;
    FJapanBoardState Local = Board;
    Local.Time = Playout.Map(Board.Time, GetWorld()->GetTimeSeconds());
    if (!Boards.IsEmpty() && Local.Time <= Boards.Last().Time) { ++TimestampDropCount; return; }
    Boards.Add(MoveTemp(Local));
    while (Boards.Num() > 64) Boards.RemoveAt(0, 1, EAllowShrinking::No);
}

void UJapanSkateNetwork::ShowBoard(double ShowAt)
{
    if (Boards.IsEmpty()) return;
    const auto Sample = FJapanSkatePlayout::Sample(Boards, ShowAt, [](const auto& Frame) { return double(Frame.Time); });
    const auto& A = Boards[Sample.A]; const auto& B = Boards[Sample.B];
    const float Alpha = Sample.Alpha;
    if (A.Shown == 0.f && B.Shown == 0.f && Rider->GetSkate()->GetBoardShown() == 0.f) return;
    FTransform Deck; Deck.Blend(A.Deck, B.Deck, Alpha);
    Rider->GetSkate()->ApplyNetworkBoard(Deck, FMath::Lerp(A.Shown, B.Shown, Alpha));
}

bool UJapanSkateNetwork::AcceptsRoot(const FVector& Location) const
{
    if (!Rider || Location.ContainsNaN() || Location.GetAbsMax() > 2000000.) return false;
    const double Elapsed = FMath::Clamp(GetWorld()->GetTimeSeconds() - LastHostRootTime, 1./120., .5);
    return FVector::Dist(Location, LastHostRoot) <= 30000. * Elapsed + 500.;
}
