#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "JapanSkateWire.h"
#include "JapanSkateClock.h"
#include "JapanSkateNetwork.generated.h"

class AWandererCharacter;

/** Trusted-owner skating transport. Physics runs only on the owner; every other copy is a bounded visual proxy. */
UCLASS()
class YORIMICHI_API UJapanSkateNetwork : public UActorComponent
{
    GENERATED_BODY()
public:
    UJapanSkateNetwork();
    virtual void BeginPlay() override;
    bool AcceptsRoot(const FVector& Location) const;
    uint32 GetReceivedFrameCount() const { return ReceivedFrameCount; }
    uint32 GetAppliedFrameCount() const { return AppliedFrameCount; }
    uint32 GetInterpolatedFrameCount() const { return InterpolatedFrameCount; }
    uint32 GetHeldFrameCount() const { return HeldFrameCount; }
    uint32 GetBeforeBufferCount() const { return BeforeBufferCount; }
    uint32 GetAfterBufferCount() const { return AfterBufferCount; }
    uint32 GetTimestampDropCount() const { return TimestampDropCount; }
    uint8 GetHostMode() const { return HostMode; }
    uint32 GetAcceptedFrameCount() const { return AcceptedFrameCount; }
    virtual void TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick) override;
    virtual void GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const override;
    UFUNCTION(Server, Unreliable) void ServerPose(const FJapanSkateChunk& Chunk);
    void ReceivePose(const FJapanSkateChunk& Chunk);
    UFUNCTION(Server, Unreliable) void ServerBodies(const FJapanSkateBodies& State);
    void ReceiveBodies(const FJapanSkateBodies& State);
    UFUNCTION(Server, Unreliable) void ServerBoard(const FJapanBoardState& State);
private:
    UPROPERTY() TObjectPtr<AWandererCharacter> Rider;
    UPROPERTY(ReplicatedUsing=OnRep_Board) FJapanBoardState Board;
    UFUNCTION() void OnRep_Board();
    TArray<FJapanBoardState> Boards;
    FJapanBoardState LastCapturedBoard;
    FVector LastHostRoot = FVector::ZeroVector;
    double LastHostRootTime = 0.;
    bool bWarnedBodyLimit = false, bWarnedSkeletonLimit = false, bWarnedRoot = false;
    double LastActivePose = -2.;
    FJapanSkateClock ArrivalClock;
    FJapanSkatePlayout Playout;
    uint32 InterpolatedFrameCount = 0, HeldFrameCount = 0;
    uint32 BeforeBufferCount = 0, AfterBufferCount = 0;
    uint32 TimestampDropCount = 0;
    void ShowBoard(double ShowAt);
    FJapanSkateAssembly HostAssembly, ViewAssembly;
    TArray<FJapanSkateFrame> Frames;
    TArray<FJapanSkateBodies> Bodies;
    uint32 SentBodies = 0, HostBodies = 0, ReceivedBodies = 0;
    double LastBodiesSent = -1.;
    int32 ReceivedBodyPackets = 0;
    void CaptureBodies(double Now);
    bool ValidBodies(const FJapanSkateBodies& State) const;
    void ShowBodies(double ShowAt, TArray<FTransform>& Pose, FTransform& Mesh, FTransform& Deck, float& Shown);
    uint8 HostMode = 0;
    uint32 AcceptedFrameCount = 0, ReceivedFrameCount = 0, AppliedFrameCount = 0;
    uint32 LastAppliedEpoch = 0, LastAppliedFrame = 0;
    uint32 SentFrame = 0, ReceivedFrame = 0, HostFrame = 0, Epoch = 0, SentBoard = 0;
    double LastSent = -1., LastBoardSent = -1., RateWindow = 0.;
    int32 ReceivedChunks = 0, ReceivedBoards = 0;
    void Capture();
    void Show(float Dt);
    void Accept(const FJapanSkateFrame& Frame);
    bool ValidPeerFrame(const FJapanSkateFrame& Frame) const;
};
