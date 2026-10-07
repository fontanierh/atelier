#include "JapanSession.h"
#include "JapanSkateNetwork.h"
#include "WandererCharacter.h"
#include "SkateComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Engine/NetConnection.h"
#include "Engine/ActorChannel.h"

namespace
{
bool HasFrameRoom(UNetConnection* Connection, AActor* Subject, int32 Bytes)
{
    if (!Connection || !Connection->IsNetReady()) return false;
    const auto* Channel = Connection->FindActorChannelRef(Subject);
    if (!Channel || !Channel->SpawnAcked) return false;
    // Match UE's legacy IsNetReady accounting, including its pending packet, and leave a
    // KiB for gameplay. Never touch the limiter. A complete bounded frame must fit now.
    const int64 RoomBits = -int64(Connection->QueuedBits) - Connection->SendBuffer.GetNumBits();
    return RoomBits >= int64(Bytes + 1024) * 8;
}

double Weight(double Distance)
{
    if (Distance > 20000.) return 0.;
    return Distance < 2000. ? 1. : (Distance < 6000. ? .5 : .15);
}
}

double AJapanPlayerController::SkateInterest(AWandererCharacter* Subject, bool bBodies, double& TotalWeight) const
{
    TotalWeight = 0.;
    const APawn* Viewer = GetPawn();
    const auto* Player = GetPlayerState<AJapanPlayerState>();
    if (!HasAuthority() || IsLocalController() || !Viewer || !Subject || Subject == Viewer || !Player || !Player->bWorldReady) return 0.;
    const auto* Channel = GetNetConnection() ? GetNetConnection()->FindActorChannelRef(Subject) : nullptr;
    if (!Channel || !Channel->SpawnAcked) return 0.;
    if (!Subject->IsNetRelevantFor(this, GetViewTarget(), Viewer->GetActorLocation())) return 0.;
    const double SubjectDistance = FVector::Dist(Viewer->GetActorLocation(), Subject->GetActorLocation());
    const double SubjectWeight = Weight(SubjectDistance);
    if (!SubjectWeight || (bBodies && SubjectDistance > 3000.)) return 0.;
    int32 CloserBails = 0;
    double Closest = TNumericLimits<double>::Max(), Second = Closest;
    for (TActorIterator<AWandererCharacter> It(GetWorld()); It; ++It)
    {
        if (*It == Viewer || It->IsNpc() || It->GetNetworkActivity() != EJapanActivity::Skate) continue;
        const auto* PeerChannel = GetNetConnection()->FindActorChannelRef(*It);
        if (!PeerChannel || !PeerChannel->SpawnAcked) continue;
        if (!It->IsNetRelevantFor(this, GetViewTarget(), Viewer->GetActorLocation())) continue;
        const double Distance = FVector::Dist(Viewer->GetActorLocation(), It->GetActorLocation());
        if (bBodies)
        {
            const auto* Stream = It->FindComponentByClass<UJapanSkateNetwork>();
            if (!Stream || Stream->GetHostMode() != uint8(ESkateMode::Bail) || Distance > 3000.) continue;
            if (Distance < Closest) { Second = Closest; Closest = Distance; }
            else if (Distance < Second) Second = Distance;
            if (*It != Subject && (Distance < SubjectDistance || (Distance == SubjectDistance && It->GetUniqueID() < Subject->GetUniqueID()))) ++CloserBails;
        }
        TotalWeight += Weight(Distance);
    }
    // Only the nearest two bails get body anchors. Others retain the bounded full-pose stream.
    if (bBodies && CloserBails >= 2) return 0.;
    if (bBodies) TotalWeight = Weight(Closest) + Weight(Second);
    TotalWeight = FMath::Max(TotalWeight, SubjectWeight);
    return SubjectWeight;
}

void AJapanPlayerController::DeliverSkateFrame(AWandererCharacter* Subject, const FJapanSkateFrame& Frame)
{
    double TotalWeight = 0.;
    const double Interest = SkateInterest(Subject, false, TotalWeight);
    if (!Interest) return;
    const double Now = GetWorld()->GetTimeSeconds();
    // Conservative wire allowance includes each RPC's actor reference and packet overhead.
    const int32 Count = FMath::Max(1, FMath::DivideAndRoundUp(Frame.Bones.Num(), FJapanSkateChunk::BonesPerChunk));
    const int32 Bytes = Count * 768;
    const double Interval = FMath::Max(1. / (30. * Interest), Bytes * TotalWeight / (FJapanSkateBudget::PoseRate * Interest));
    FSkateDelivery& Delivery = SkateDelivery.FindOrAdd(Subject);
    if (Now - Delivery.Pose < Interval * .8 || !HasFrameRoom(GetNetConnection(), Subject, Bytes) || !SkateBudget.Spend(Now, Bytes, false)) return;
    Delivery.Pose = Now; Delivery.bPose = false;
    for (int32 I = 0; I < Count; ++I)
    {
        FJapanSkateChunk Relay;
        Relay.Epoch = Frame.Epoch; Relay.Frame = Frame.Frame; Relay.Time = Frame.Time;
        Relay.Interval = float(FMath::Clamp(Interval, 1./120., 30.));
        Relay.TotalBones = Frame.Bones.Num(); Relay.Chunk = I;
        Relay.Root = Frame.Root; Relay.Mesh = Frame.Mesh; Relay.Deck = Frame.Deck; Relay.Shown = Frame.Shown;
        Relay.Mode = Frame.Mode; Relay.Surface = Frame.Surface; Relay.AudioFlags = Frame.AudioFlags; Relay.Velocity = Frame.Velocity;
        const int32 Start = I * FJapanSkateChunk::BonesPerChunk;
        for (int32 Bone = Start; Bone < FMath::Min(Start + FJapanSkateChunk::BonesPerChunk, Frame.Bones.Num()); ++Bone)
            Relay.Bones.Add(Frame.Bones[Bone]);
        ClientSkatePose(Subject, Relay);
    }
}

void AJapanPlayerController::DeliverSkateBodies(AWandererCharacter* Subject, const FJapanSkateBodies& State)
{
    double TotalWeight = 0.;
    const double Interest = SkateInterest(Subject, true, TotalWeight);
    if (!Interest) return;
    const double Now = GetWorld()->GetTimeSeconds();
    const int32 Bytes = 224 + State.Indices.Num() * 17;
    const double Interval = FMath::Max(1. / 60., Bytes * TotalWeight / (FJapanSkateBudget::BodyRate * Interest));
    FSkateDelivery& Delivery = SkateDelivery.FindOrAdd(Subject);
    if (Now - Delivery.Bodies < Interval * .8 || !HasFrameRoom(GetNetConnection(), Subject, Bytes) || !SkateBudget.Spend(Now, Bytes, true)) return;
    Delivery.Bodies = Now; Delivery.bBodies = false;
    ClientSkateBodies(Subject, State);
}

void AJapanPlayerController::ClientSkatePose_Implementation(AWandererCharacter* Subject, const FJapanSkateChunk& Chunk)
{
    if (Subject && !Subject->IsLocallyControlled())
        if (auto* Stream = Subject->FindComponentByClass<UJapanSkateNetwork>()) Stream->ReceivePose(Chunk);
}
void AJapanPlayerController::ClientSkateBodies_Implementation(AWandererCharacter* Subject, const FJapanSkateBodies& State)
{
    if (Subject && !Subject->IsLocallyControlled())
        if (auto* Stream = Subject->FindComponentByClass<UJapanSkateNetwork>()) Stream->ReceiveBodies(State);
}

void AJapanPlayerController::SendSkateFrame(AWandererCharacter* Subject, const FJapanSkateFrame& Frame)
{
    if (!HasAuthority() || IsLocalController() || !Subject || Subject == GetPawn()) return;
    auto& Delivery = SkateDelivery.FindOrAdd(Subject);
    Delivery.LatestPose = Frame; Delivery.bPose = true;
}
void AJapanPlayerController::SendSkateBodies(AWandererCharacter* Subject, const FJapanSkateBodies& State)
{
    if (!HasAuthority() || IsLocalController() || !Subject || Subject == GetPawn()) return;
    auto& Delivery = SkateDelivery.FindOrAdd(Subject);
    Delivery.LatestBodies = State; Delivery.bBodies = true;
}
void AJapanPlayerController::DrainSkateFrames()
{
    TArray<TWeakObjectPtr<AWandererCharacter>> Subjects;
    for (auto It = SkateDelivery.CreateIterator(); It; ++It)
    {
        if (!It.Key().IsValid()) It.RemoveCurrent();
        else Subjects.Add(It.Key());
    }
    if (Subjects.IsEmpty()) return;
    Subjects.Sort([](const auto& A, const auto& B) { return A.Get()->GetUniqueID() < B.Get()->GetUniqueID(); });
    const int32 Start = SkateRoundRobin % Subjects.Num();
    SkateRoundRobin = (Start + 1) % Subjects.Num();
    for (int32 I = 0; I < Subjects.Num(); ++I)
    {
        auto* Subject = Subjects[(Start + I) % Subjects.Num()].Get();
        auto& Delivery = SkateDelivery.FindChecked(Subject);
        if (Delivery.bPose)
        {
            if (Delivery.LatestPose.Epoch != Subject->GetActivityEpoch()) Delivery.bPose = false;
            else DeliverSkateFrame(Subject, Delivery.LatestPose);
        }
        if (Delivery.bBodies)
        {
            if (Delivery.LatestBodies.Pose.Epoch != Subject->GetActivityEpoch()) Delivery.bBodies = false;
            else DeliverSkateBodies(Subject, Delivery.LatestBodies);
        }
    }
}
