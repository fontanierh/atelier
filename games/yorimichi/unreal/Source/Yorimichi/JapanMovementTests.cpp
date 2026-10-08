#include "JapanMovementNet.h"
#include "BotwNetworkState.h"
#include "JapanMoveClock.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopedCVar.h"
#include "Serialization/BitReader.h"
#include "Serialization/BitWriter.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameNetworkManager.h"
#include "HAL/IConsoleManager.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanMoveClockTest, "Yorimichi.Network.MoveClock",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanMoveClockTest::RunTest(const FString&)
{
    FJapanMoveClock Clock;
    double Now = 10.;
    for (int32 I = 0; I < 30; ++I)
    {
        Now += 1. / 30.;
        TestTrue(TEXT("Normal owner steps fit host real time"), Clock.Allows(Now, 1. / 30.));
        Clock.Accepted(Now, 1. / 30.);
    }
    const double Last = Now;
    Now += .229;
    TestFalse(TEXT("229ms client hitch does not expire the epoch"), Clock.Expired(Now));
    // Pending pre-hitch move, capped hitch move and following move arrive together.
    for (double Dt : {1. / 30., .125, 1. / 30.})
    {
        TestTrue(TEXT("Late real moves fit without inventing a forced timestamp"), Clock.Allows(Now, Dt));
        Clock.Accepted(Now, Dt);
    }
    TestFalse(TEXT("Boundary below the named timeout waits"), Clock.Expired(Now + FJapanMoveClock::Timeout - .001));
    TestTrue(TEXT("Timeout boundary requires a new epoch"), Clock.Expired(Now + FJapanMoveClock::Timeout));
    TestTrue(TEXT("Actual hitch exceeded zero time"), Now > Last);
    FJapanMoveClock Burst;
    double Accepted = 0.;
    for (int32 I = 0; I < 1000; ++I)
        if (Burst.Allows(20., .025)) { Burst.Accepted(20., .025); Accepted += .025; }
    TestTrue(TEXT("One receive frame cannot bank more than initial host slack"), Accepted <= .125001);
    TestFalse(TEXT("Excess burst is rejected"), Burst.Allows(20., .025));
    Burst.Refill(120.);
    TestEqual(TEXT("A long outage cannot bank more than the timeout"), Burst.Credit, FJapanMoveClock::Timeout);
    TestFalse(TEXT("Nonfinite elapsed input is refused"), Burst.Allows(120., std::numeric_limits<double>::infinity()));
    FJapanMoveClock Recovery;
    Recovery.BeginEpoch(20.);
    TestTrue(TEXT("The first capped move includes host time since the epoch handoff"), Recovery.Allows(20.299, .125));
    Recovery.Accepted(20.299, .125);
    // Recorded recovery: the .125 first step consumed all initial slack when
    // refilling began at first arrival. Ordinary arrival jitter then reset again.
    for (int32 I = 1; I <= 30; ++I)
    {
        const double Arrival = 20.299 + I * .033;
        TestTrue(TEXT("Normal recovery frames fit after the capped first move"), Recovery.Allows(Arrival, 1. / 30.));
        Recovery.Accepted(Arrival, 1. / 30.);
    }
    Recovery.BeginEpoch(30.);
    TestFalse(TEXT("Old epoch acceptance does not start the new timeout"), Recovery.Expired(31.));
    TestEqual(TEXT("An epoch clears old credit"), Recovery.Credit, FJapanMoveClock::InitialSlack);
    double RecoveryAccepted = 0.;
    for (int32 I = 0; I < 100; ++I)
        if (Recovery.Allows(30.299, .025)) { Recovery.Accepted(30.299, .025); RecoveryAccepted += .025; }
    TestTrue(TEXT("Recovery burst cannot exceed elapsed host time plus unchanged slack"),
        RecoveryAccepted <= .299 + FJapanMoveClock::InitialSlack + 1.e-6);
    TestFalse(TEXT("Recovery burst beyond its budget is still rejected"), Recovery.Allows(30.299, .025));
    Recovery.BeginEpoch(40.);
    Recovery.Refill(42.);
    TestEqual(TEXT("First-arrival waiting cannot bank more than the existing cap"), Recovery.Credit, FJapanMoveClock::Timeout);
#if !UE_BUILD_SHIPPING
    UWorld* TestWorld = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { TestWorld = Context.World(); break; }
    if (!TestNotNull(TEXT("Stale move regression has a native game world"), TestWorld)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Character = TestWorld->SpawnActor<ACharacter>(FVector(200., 300., 400.), FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Stale move regression owns a character"), Character)) return false;
    ON_SCOPE_EXIT { Character->Destroy(); };
    auto* Movement = Character->GetCharacterMovement();
    FNetworkPredictionData_Client_Japan Client(*Movement);
    Client.CurrentTimeStamp = .625f;
    const FVector Before = Character->GetActorLocation();
    FSavedMovePtr Storage = Client.CreateSavedMove();
    auto& Probe = static_cast<FSavedMove_Japan&>(*Storage);
    Probe.CharacterOwner = nullptr; // Deterministic negative for the old Clear-only construction.
    Probe.PrepareStaleClockProbe(Character, Client, 4);
    if (!TestTrue(TEXT("Stale probe initializes UE's required character owner"), Probe.CharacterOwner == Character)) return false;
    FJapanNetworkMoveData Data;
    Data.ClientFillNetworkMoveData(Probe, FCharacterNetworkMoveData::ENetworkMoveType::NewMove);
    TestEqual(TEXT("Stale probe retains its adversarial timestamp"), Data.TimeStamp, 123.25f);
    TestEqual(TEXT("Stale probe retains its old activity epoch"), Data.Input.ActivityEpoch, uint32(4));
    TestEqual(TEXT("Stale probe retains its unique diagnostic marker"), Data.Input.FirstEdge, uint16(60000));
    TestTrue(TEXT("Stale probe sends its large absolute displacement"), Data.Location.Equals(Before + FVector(1000., 0., 0.)));
    TestTrue(TEXT("Stale probe preserves acceleration in the real packet builder"), Data.Acceleration.Equals(FVector(1000., 0., 0.)));
    TestEqual(TEXT("Stale probe captures the real movement mode"), Data.MovementMode, Movement->PackNetworkMovementMode());
    TestEqual(TEXT("Probe construction leaves the live client clock unchanged"), Client.CurrentTimeStamp, .625f);
    TestTrue(TEXT("Probe construction does not move the character"), Character->GetActorLocation().Equals(Before));
    TestEqual(TEXT("Probe is not retained as a real predicted move"), Client.SavedMoves.Num(), 0);
    Client.FreeMove(Storage);
#endif
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanMoveInputTest, "Yorimichi.Network.OrderedInput",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanMoveInputTest::RunTest(const FString&)
{
    FJapanMoveInput Input;
    Input.X = -127; Input.Y = 100; Input.Flags = FJapanMoveInput::Sprint | FJapanMoveInput::JumpHeld; Input.FirstEdge = 65535;
    Input.Edges = { uint8(FJapanMoveInput::ButtonIndex(TEXT("attack"))),
        uint8(FJapanMoveInput::ButtonIndex(TEXT("attack_release"))),
        uint8(FJapanMoveInput::ButtonIndex(TEXT("jump"))) };
    Input.EdgeAgeMilliseconds = {0, 67, 511};
    FBitWriter Writer(256, true);
    TestTrue(TEXT("Input encodes"), Input.Serialize(Writer));
    TestTrue(TEXT("Three timed edges plus reaction identity fit in twenty bytes"), Writer.GetNumBits() <= 160);
    FBitReader Reader(Writer.GetData(), Writer.GetNumBits());
    FJapanMoveInput Decoded;
    TestTrue(TEXT("Input decodes"), Decoded.Serialize(Reader));
    TestEqual(TEXT("Raw lateral intent survives a locked move"), Decoded.X, Input.X);
    TestEqual(TEXT("Raw forward intent survives a locked move"), Decoded.Y, Input.Y);
    TestEqual(TEXT("Sprint and jump hold levels survive"), Decoded.Flags, Input.Flags);
    TestEqual(TEXT("Journal sequence survives wrap boundary"), Decoded.FirstEdge, Input.FirstEdge);
    TestTrue(TEXT("Press-release-jump ordering survives"), Decoded.Edges == Input.Edges);
    TestTrue(TEXT("Press ages and the expired marker survive"), Decoded.EdgeAgeMilliseconds == Input.EdgeAgeMilliseconds);
    TestTrue(TEXT("Diagonal input is normalized"), Decoded.Stick().Size() <= 1.000001);

    FBitReader Truncated(Writer.GetData(), Writer.GetNumBits() - 4);
    FJapanMoveInput MissingRelease;
    {
        // Malformed-input coverage expects the reader error, rather than triggering a handled ensure.
        FScopedCVar<int32> OverflowLog(TEXT("net.BitReader.EnsureOnOverflow"), 0);
        AddExpectedErrorPlain(TEXT("FBitReader::SetOverflowed() called!"));
        TestFalse(TEXT("A truncated transition stream cannot be applied"), MissingRelease.Serialize(Truncated));
        TestTrue(TEXT("Truncation leaves the archive rejected"), Truncated.IsError());
    }
    FBitWriter Malformed(128, true);
    int8 X = 0, Y = 0; uint8 Flags = 0, Count = 17;
    uint16 FirstEdge = 1;
    Malformed << X << Y; Malformed.SerializeBits(&Flags, 7); Malformed << FirstEdge; uint32 Epoch = 1; Malformed << Epoch; Malformed.SerializeBits(&Count, 5);
    FBitReader TooMany(Malformed.GetData(), Malformed.GetNumBits());
    FJapanMoveInput Rejected;
    TestFalse(TEXT("Oversized edge count is rejected before allocation"), Rejected.Serialize(TooMany));
    // The first packet may vanish before CMC has any ack. A later packet repeats the whole unacked journal.
    FJapanMoveInput Journal;
    Journal.FirstEdge = 1;
    Journal.Edges = { uint8(FJapanMoveInput::ButtonIndex(TEXT("attack"))), uint8(FJapanMoveInput::ButtonIndex(TEXT("attack_release"))) };
    uint16 LastApplied = 0;
    TArray<uint8> Delivered;
    const auto Deliver = [&](uint8 Edge) { Delivered.Add(Edge); };
    Journal.ApplyNewEdges(LastApplied, Deliver);
    Journal.ApplyNewEdges(LastApplied, Deliver);
    TestEqual(TEXT("Repeated lost-packet recovery applies both edges once"), Delivered.Num(), 2);
    TestEqual(TEXT("Release closes the sequence"), LastApplied, uint16(2));
    FJapanMoveInput Future;
    Future.FirstEdge = 4; Future.Edges.Add(uint8(FJapanMoveInput::ButtonIndex(TEXT("jump"))));
    Future.ApplyNewEdges(LastApplied, Deliver);
    TestEqual(TEXT("An out-of-order journal cannot skip a missing edge"), LastApplied, uint16(2));
    Journal.FirstEdge = 3; Journal.ApplyNewEdges(LastApplied, Deliver);
    TestEqual(TEXT("The contiguous retransmit repairs the gap"), LastApplied, uint16(4));
    LastApplied = 65534; Journal.FirstEdge = 65535;
    Journal.ApplyNewEdges(LastApplied, Deliver);
    TestEqual(TEXT("Sequences wrap through zero"), LastApplied, uint16(0));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanCheckpointTest, "Yorimichi.Network.TraversalCheckpoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanCheckpointTest::RunTest(const FString&)
{
    // Exercise UE's actual timestamp/cap paths. A hitch used to simulate 125 ms
    // on the owner but 218.75 ms on the host, producing a 9.37 cm walking snap.
    UWorld* TestWorld = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { TestWorld = Context.World(); break; }
    if (!TestNotNull(TEXT("Movement timing regression has a native game world"), TestWorld)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Character = TestWorld->SpawnActor<ACharacter>(FVector::ZeroVector, FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Movement timing regression owns a temporary character"), Character)) return false;
    ON_SCOPE_EXIT { Character->Destroy(); };
    auto* Movement = Character->GetCharacterMovement();
    FNetworkPredictionData_Client_Character Client(*Movement);
    FNetworkPredictionData_Server_Character Server(*Movement);
    const auto* Scalar = IConsoleManager::Get().FindConsoleVariable(TEXT("p.NetServerMaxMoveDeltaTimeScalar"));
    TestNotNull(TEXT("Server move cap scalar exists"), Scalar);
    TestTrue(TEXT("Initial clock slack admits UE's maximum first move at current dilation"), Scalar &&
        FJapanMoveClock::InitialSlack + 1.e-6 >= GetDefault<AGameNetworkManager>()->MaxMoveDeltaTime *
            Scalar->GetFloat() * Character->GetActorTimeDilation());
    for (float FrameDelta : {1.f / 30.f, .22f, 1.f / 30.f})
    {
        const float ClientDelta = Client.UpdateTimeStampAndDeltaTime(FrameDelta, *Character, *Movement);
        const float ServerDelta = Server.GetServerMoveDeltaTime(Client.CurrentTimeStamp, Character->GetActorTimeDilation());
        TestTrue(TEXT("Owner and host simulate the same step before, during and after a hitch"),
            FMath::IsNearlyEqual(ClientDelta, ServerDelta, .000001f));
        Server.CurrentClientTimeStamp = Client.CurrentTimeStamp;
    }
    FBotwNetworkState State;
    State.MeshBaseRotation = FQuat::Identity;
    State.Stamina.Capacity = 2.f; State.Stamina.Units = 1.25f;
    State.Clock = 40.f; State.ActionTime = .35f;
    State.DriveOrigin = FVector(1200., -400., 75.); State.DriveScale = FVector(1., 2., 3.);
    State.DrivePrevious = .3f; State.GlideSpeed = 875.f; State.GlideYaw = 123.f; State.GlideTurn = -.4f;
    State.bGuardHeld = true; State.WallPoint = FVector(60., 30., 200.); State.ClimbShift = 24.f;
    State.PendingLaunch = FVector(0., 0., 340.);
    TArray<uint8> Bytes;
    FMemoryWriter Writer(Bytes, true);
    TestTrue(TEXT("A complete traversal checkpoint encodes"), State.Serialize(Writer));
    TestTrue(TEXT("The full checkpoint fits the correction payload cap"), Bytes.Num() <= FJapanMoveCheckpoint::MaximumBytes);
    FMemoryReader Reader(Bytes, true);
    FBotwNetworkState Restored;
    TestTrue(TEXT("A complete traversal checkpoint decodes"), Restored.Serialize(Reader));
    TestEqual(TEXT("Action phase survives a correction"), Restored.ActionTime, State.ActionTime);
    TestEqual(TEXT("Previous authored-path time survives"), Restored.DrivePrevious, State.DrivePrevious);
    TestTrue(TEXT("Path origin and scale survive"), Restored.DriveOrigin.Equals(State.DriveOrigin) && Restored.DriveScale.Equals(State.DriveScale));
    TestEqual(TEXT("Glide speed survives"), Restored.GlideSpeed, State.GlideSpeed);
    TestEqual(TEXT("Glide turn survives"), Restored.GlideTurn, State.GlideTurn);
    TestTrue(TEXT("Climb anchor and pending launch survive"), Restored.WallPoint.Equals(State.WallPoint) && Restored.PendingLaunch.Equals(State.PendingLaunch));
    TestTrue(TEXT("Stamina and held guard survive"), Restored.Stamina.Units == State.Stamina.Units && Restored.bGuardHeld);
    Bytes[0] = 255;
    FMemoryReader BadSchema(Bytes, true);
    FBotwNetworkState Rejected;
    TestFalse(TEXT("A mismatched checkpoint schema is rejected"), Rejected.Serialize(BadSchema));
    return true;
}

#endif
