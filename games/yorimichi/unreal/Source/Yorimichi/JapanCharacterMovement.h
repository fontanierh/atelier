#pragma once
#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "JapanMovementNet.h"
#include "JapanMoveClock.h"
#include "JapanCharacterMovement.generated.h"

DECLARE_LOG_CATEGORY_EXTERN(LogJapanMovementQA, Log, All);

struct FJapanCorrectionSample
{
    double WorldTime = 0.;
    float Timestamp = 0.f, DeltaTime = 0.f;
    uint32 Epoch = 0;
    uint16 ThroughEdge = 0, PredictedEdge = 0;
    uint8 PredictedMode = 0, AuthoritativeMode = 0;
    FVector PredictedLocation = FVector::ZeroVector, AuthoritativeLocation = FVector::ZeroVector;
    FVector PredictedVelocity = FVector::ZeroVector, AuthoritativeVelocity = FVector::ZeroVector;
    FName PredictedAction, AuthoritativeAction;
    int32 CheckpointBytes = 0;
};

struct FJapanMovementStats
{
    uint32 Corrections = 0, PositionCorrections = 0, Checkpoints = 0, Rejected = 0, ReplayedMoves = 0;
    uint32 InitialForcedUpdatesSkipped = 0, MovesBeforeReady = 0, MovesBeforeAck = 0, StartedEpochs = 0;
    uint32 DeferredForcedUpdates = 0, TimeBudgetRejected = 0, StaleEpochMoves = 0;
    uint32 TimeoutCorrections = 0, TimeBudgetCorrections = 0;
    uint32 StaleProbeSent = 0, StaleProbeRejected = 0, NeutralLateGroundFrames = 0;
    float StaleProbeRootCm = 0.f, StaleProbeClockDelta = 0.f;
    float NeutralMaxAcceleration = 0.f, NeutralLateMaxSpeed = 0.f;
    uint32 ClockArrivals = 0;
    float NeutralPathCm = 0.f;
    FVector ClockHandoffRoot = FVector::ZeroVector, ClockArrivalRoot = FVector::ZeroVector;
    float FirstMoveTimestamp = -1.f;
    float LargestCorrectionCm = 0.f;
    FJapanCorrectionSample LargestCorrection;
};

struct FJapanScheduledReactionStats
{
    uint32 Issued = 0, Received = 0, Applied = 0, Replayed = 0;
    uint32 Forced = 0, InvalidPayloads = 0, InvalidOrigins = 0, FailedApply = 0, FailedRestore = 0;
    uint32 SuppressedAttacks = 0, SuppressedDefenceInputs = 0;
    uint32 Recoveries = 0, FoldedSlices = 0, RejectedResets = 0, RejectedRecoveries = 0, LethalSuperseded = 0;
};

/** The player's movement: ordinary CharacterMovement, the sailboat holding its own velocity, the skate plugin's custom
 *  movement mode (USkateComponent::MovementMode) handed to the board, and an adventure move set's (UAdventureMoveSet::MovementMode:
 *  gliding, climbing, swimming), which also sets the velocity of its hops and driven attacks, turns the character and
 *  hears what the capsule runs into. */
UCLASS()
class YORIMICHI_API UJapanCharacterMovement : public UCharacterMovementComponent
{
    GENERATED_BODY()
    friend class FJapanReactionSerializationTest;
    friend class FJapanReactionTransportTest;
public:
    UJapanCharacterMovement(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    bool PredictsMoves() const;
    FJapanMoveCheckpoint CaptureMovementState() const;
    bool ApplyMovementState(const FJapanMoveCheckpoint& State);
    bool QueueMoveButton(FName Button);
    bool QueueAuthoritativeRecovery(FVector Shore, float Yaw, float Damage);
    // Publish externally resolved combat state on the next accepted movement response.
    void QueueReactionCheckpoint();
    static constexpr double MaximumReactionWait = .5;
    bool QueueScheduledReaction(const FJapanReactionValue& Value);
    bool QueueLethalReaction(const FJapanReactionValue& Value);
    void ReceiveScheduledReaction(const TArray<uint8>& Encoded);
    void RecoverScheduledReactions(uint32 Epoch, bool bClientRequest = true);
    void PrepareReactionMove(FJapanMoveInput& Input, float Timestamp, float Dt);
    bool HasScheduledReaction() const { return ReactionJournal.HasPending(); }
    uint32 GetScheduledReactionThrough() const { return ReactionJournal.Applied(); }
    uint32 GetScheduledReactionEpoch() const { return ReactionJournal.GetEpoch(); }
    uint32 GetScheduledReactionKnown() const { return ReactionJournal.Known(); }
    const FJapanScheduledReactionStats& GetScheduledReactionStats() const { return ReactionStats; }
    FJapanReactionStamp GetReactionMoveStamp() const { return ReactionCurrent; }
    bool ReactionEdgeEligible(TOptional<uint16> Edge, bool bContinuousHold = false) const;
    bool AllowScheduledAttack(TOptional<uint16> Edge);
    void RecordSuppressedDefenceInput() { ++ReactionStats.SuppressedDefenceInputs; }
    // Explicitly bypass scheduling while composing an atomic activity snapshot.
    bool bImmediateMovementReaction = false;
    // Called only after successful saving of the matching packed response.
    void MovementCheckpointSerialized(uint32 Epoch, float Timestamp);
    virtual void SendClientAdjustment() override;
    FJapanMoveInput ReadMoveInput() const;
    FJapanMoveInput ConsumeMoveInput(float Dt);
    void SetMoveInput(const FJapanMoveInput& Input) { ActiveInput = Input; bInputPrepared = true; }
    void ResetActivityPrediction();
    void RecordClockCorrection(uint8 Reason);
    void SendStaleClockProbe();
    uint32 GetActivityEpoch() const;
    virtual void ServerMove_PerformMovement(const FCharacterNetworkMoveData& MoveData) override;
    uint16 GetProcessedEdge() const { return ProcessedEdge; }
    uint16 PendingAcknowledgedEdge = 0;
    bool TraceClientStep(float Timestamp) { return Timestamp <= 6.f && ClientTraceRows++ < 512; }
    bool IsReplaying() const { return bReplaying; }
    bool IsExecutingMove() const { return bExecutingMove; }
    const FJapanMovementStats& GetNetworkStats() const { return NetworkStats; }
    FVector GetPendingLaunch() const { return PendingLaunchVelocity; }
    void SetPendingLaunch(const FVector& Value) { PendingLaunchVelocity = Value; }
    FJapanMoveCheckpoint PendingCheckpoint;
    float PendingCheckpointTime = -1.f;
    virtual FNetworkPredictionData_Client* GetPredictionData_Client() const override;
    virtual void PerformMovement(float Dt) override;
    virtual bool ForcePositionUpdate(float Dt) override;
    virtual bool VerifyClientTimeStamp(float Timestamp, FNetworkPredictionData_Server_Character& Data) override;
    virtual void TickComponent(float Dt, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction) override;
    virtual void ReplicateMoveToServer(float Dt, const FVector& NewAcceleration) override;
    virtual void SetBase(FMovementBaseInterfaceData* Base, const FName Bone = NAME_None, bool bNotifyActor = true) override;
    virtual void MoveAutonomous(float Timestamp, float Dt, uint8 Flags, const FVector& Accel) override;
    virtual bool ClientUpdatePositionAfterServerUpdate() override;
    virtual void ClientHandleMoveResponse(const FCharacterMoveResponseDataContainer& Response) override;
    virtual bool ServerCheckClientError(float Timestamp, float Dt, const FVector& Accel,
        const FVector& ClientLocation, const FVector& RelativeLocation, FMovementBaseInterfaceData* Base,
        FName Bone, uint8 Mode) override;
    virtual void ServerMoveHandleClientError(float Timestamp, float Dt, const FVector& Accel,
        const FVector& RelativeLocation, FMovementBaseInterfaceData* Base, FName Bone, uint8 Mode) override;
    virtual void CalcVelocity(float Dt, float Friction, bool bFluid, float BrakingDeceleration) override;
    virtual void PhysicsRotation(float Dt) override;
    virtual float GetMaxSpeed() const override;
    virtual void PhysCustom(float Dt, int32 Iterations) override;
    virtual void HandleImpact(const FHitResult& Hit, float TimeSlice = 0.f, const FVector& MoveDelta = FVector::ZeroVector) override;
private:
    void ResetScheduledReactions();
    void TickScheduledReactions();
    void ScheduleReactionDeadline(uint32 Sequence, double Now, double RTT, double Jitter);
    bool ReactionDeadlineExpired(double Now) const;
    bool AllowReactionRecoveryRequest(double Now, double RTT);
    void AcceptReactionMove(float Timestamp);
    void SimulateReactionMove(float Dt, TFunctionRef<void(float, float, TOptional<uint16>)> Step);
    void ApplyScheduledThrough(uint32 Through);
    void AcceptReactionCheckpoint(const FJapanMoveCheckpoint& State, uint32 Disposed, bool bAuthoritative);
    void DisposeReactionMoves(uint32 Through);
    void RetireReactionOrigins();
    FJapanReactionJournal ReactionJournal;
    FJapanScheduledReactionStats ReactionStats;
    FJapanReactionStamp ReactionPrevious, ReactionCurrent, ReactionOwnerEnd;
    TArray<FJapanReactionMarker, TInlineAllocator<FJapanReactionJournal::RetainedCapacity>> ReactionOrigins;
    TArray<TArray<uint8>> FutureReactions;
    uint32 ReactionAcceptedCheckpoint = 0, ReactionDisposed = 0;
    struct FReactionDeadline { uint32 Sequence; double At; };
    TArray<FReactionDeadline, TInlineAllocator<FJapanReactionJournal::RetainedCapacity>> ReactionDeadlines;
    double ReactionLastRecovery = -1.;
    uint32 ReactionLastRecoveredThrough = 0;
    bool bLethalReactionQueued = false;
    struct FReactionWindow
    {
        uint32 Sequence; FJapanReactionStamp Resolved, Acknowledged; bool bClosed = false;
        uint16 ResolvedEdge = 0, AcknowledgedEdge = 0;
    };
    TArray<FReactionWindow, TInlineAllocator<32>> ReactionWindows;
    void AddReactionWindow(const FJapanScheduledReaction& Event);
    void ApplyMoveInput(const FJapanMoveInput& Input);
    FJapanNetworkMoveContainer NetworkMoves;
    FJapanMoveResponse NetworkResponse;
    FJapanMoveInput ActiveInput;
    struct FPendingEdge { uint8 Button; double FirstSample = -1.; };
    TArray<FPendingEdge> PendingEdges;
    uint16 JournalFirstEdge = 1, ProcessedEdge = 0;
    uint8 HeldButtons = 0, LastServerHolds = 0;
    bool bRecoveryQueued = false, bReceivedMoveInEpoch = false;
    void AcknowledgeEdges(uint16 Through);
    bool bInputPrepared = false, bExecutingMove = false, bReplaying = false;
    bool bAcceptedDefenceMove = false;
    FJapanMoveClock MoveClock;
    bool bClockResetPending = false, bWaitingAfterClockReset = false;
    double ClockResetAt = 0.;
    void QueueClockReset(uint8 Reason);
    double LastCustomCorrection = -1.;
    bool bReactionCheckpointPending = false, bReactionCheckpointCaptured = false;
    bool bCheckpointSerialized = false;
    FJapanMovementStats NetworkStats;
    uint32 ClientTraceRows = 0, ServerTraceRows = 0, ForcedTraceRows = 0;
};
