#pragma once
#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/CharacterMovementReplication.h"
#include "JapanReactionTiming.h"

struct FJapanReactionMarker
{
    uint32 Sequence = 0;
    FJapanReactionOrigin Origin;
    uint16 EdgeBefore = 0, EdgeAfter = 0;
    bool operator==(const FJapanReactionMarker& Other) const
    {
        return Sequence == Other.Sequence && Origin.Previous == Other.Origin.Previous &&
            Origin.End == Other.Origin.End && Origin.DeltaTime == Other.Origin.DeltaTime &&
            EdgeBefore == Other.EdgeBefore && EdgeAfter == Other.EdgeAfter;
    }
};

/** The input sampled for one CMC move. Button transitions keep their order, including press/release in one frame. */
struct FJapanMoveInput
{
    static constexpr uint8 MaximumEdges = 16;
    enum : uint8 { Walk = 1, Jog = 2, Sprint = 4, Menu = 8, AttackHeld = 16, GuardHeld = 32, JumpHeld = 64 };
    int8 X = 0, Y = 0;
    int8 Lean = 0; // Bike rider lean; sent only while nonzero.
    uint8 Flags = 0;
    uint32 ActivityEpoch = 1;
    uint16 FirstEdge = 1; // The journal is repeated until acknowledged, independently of CMC old-move selection.
    TArray<uint8, TInlineAllocator<MaximumEdges>> Edges;
    // 511 marks an input too old for historical defence; it may still drive the live action.
    TArray<uint16, TInlineAllocator<MaximumEdges>> EdgeAgeMilliseconds;
    // Each saved Old/Pending/New move owns its marker. Retained origins repeat
    // until a checkpoint permits retirement, independently of UE OldMove choice.
    uint32 ReactionThrough = 0;
    TArray<FJapanReactionMarker, TInlineAllocator<FJapanReactionJournal::RetainedCapacity>> ReactionOrigins;
    FVector2D Stick() const { return FVector2D(X / 127., Y / 127.).GetClampedToMaxSize(1.); }
    bool Serialize(FArchive& Ar);
    void ApplyNewEdges(uint16& LastApplied, TFunctionRef<void(uint8)> Apply, TOptional<uint16> Through = {}) const;
    static int32 ButtonIndex(FName Name);
    static FName ButtonName(uint8 Index);
};

/** Owned immutable checkpoint at exactly the timestamp of a CMC adjustment. Only the server sends this state.
 *  Scalars use 32-bit little-endian fields; names and actor references use Unreal's package map separately.
 *  The session's code/content identity makes the checkpoint layout and action vocabulary identical at admission. */
struct FJapanMoveCheckpoint
{
    static constexpr uint32 MaximumBytes = 768;
    TArray<uint8> Bytes;
    FName Action;
    TWeakObjectPtr<AActor> Target, LungeTarget;
    uint32 ReactionThrough = 0;
    bool Serialize(FArchive& Ar, UPackageMap* Map);
};

class FSavedMove_Japan : public FSavedMove_Character
{
public:
    using Super = FSavedMove_Character;
    FJapanMoveInput Input;
    FJapanMoveCheckpoint PostState;
    uint16 PostEdge = 0;
    bool PostCrouch = false;
    virtual void PostUpdate(ACharacter* Character, EPostUpdateMode Mode) override;
    virtual void Clear() override;
    virtual void SetMoveFor(ACharacter* Character, float Dt, const FVector& Accel,
        FNetworkPredictionData_Client_Character& ClientData) override;
    virtual void PrepMoveFor(ACharacter* Character) override;
    virtual bool CanCombineWith(const FSavedMovePtr& NewMove, ACharacter* Character, float MaxDelta) const override;
    virtual bool IsImportantMove(const FSavedMovePtr& LastAckedMove) const override;
#if !UE_BUILD_SHIPPING
    void PrepareStaleClockProbe(ACharacter* Character, FNetworkPredictionData_Client_Character& ClientData, uint32 OldEpoch);
#endif
};

class FNetworkPredictionData_Client_Japan : public FNetworkPredictionData_Client_Character
{
public:
    explicit FNetworkPredictionData_Client_Japan(const UCharacterMovementComponent& Movement)
        : FNetworkPredictionData_Client_Character(Movement) {}
    virtual FSavedMovePtr AllocateNewMove() override { return MakeShared<FSavedMove_Japan>(); }
};

struct FJapanNetworkMoveData : FCharacterNetworkMoveData
{
    FJapanMoveInput Input;
    virtual void ClientFillNetworkMoveData(const FSavedMove_Character& Move, ENetworkMoveType Type) override;
    virtual bool Serialize(UCharacterMovementComponent& Movement, FArchive& Ar,
        UPackageMap* Map, ENetworkMoveType Type) override;
};

struct FJapanNetworkMoveContainer : FCharacterNetworkMoveDataContainer
{
    FJapanNetworkMoveData Moves[3];
    FJapanNetworkMoveContainer() { NewMoveData = &Moves[0]; PendingMoveData = &Moves[1]; OldMoveData = &Moves[2]; }
};

struct FJapanMoveResponse : FCharacterMoveResponseDataContainer
{
    FJapanMoveCheckpoint Checkpoint;
    bool bHasCheckpoint = false;
    uint16 AcknowledgedEdge = 0;
    uint32 ActivityEpoch = 1;
    virtual void ServerFillResponseData(const UCharacterMovementComponent& Movement,
        const FClientAdjustment& Adjustment) override;
    virtual bool Serialize(UCharacterMovementComponent& Movement, FArchive& Ar, UPackageMap* Map) override;
};
