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

/** The player's movement: ordinary CharacterMovement, the sailboat holding its own velocity, the skate plugin's custom
 *  movement mode (USkateComponent::MovementMode) handed to the board, and a BOTW move set's (UBotwMoveSet::MovementMode:
 *  gliding, climbing, swimming), which also sets the velocity of its hops and driven attacks, turns the character and
 *  hears what the capsule runs into. */
UCLASS()
class YORIMICHI_API UJapanCharacterMovement : public UCharacterMovementComponent
{
    GENERATED_BODY()
public:
    UJapanCharacterMovement(const FObjectInitializer& ObjectInitializer = FObjectInitializer::Get());
    bool PredictsMoves() const;
    bool QueueMoveButton(FName Button);
    bool QueueAuthoritativeRecovery(FVector Shore, float Yaw, float Damage);
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
    bool TraceClientStep(float Timestamp) { return Timestamp <= .8f && ClientTraceRows++ < 64; }
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
    FJapanMovementStats NetworkStats;
    uint32 ClientTraceRows = 0, ServerTraceRows = 0, ForcedTraceRows = 0;
};
