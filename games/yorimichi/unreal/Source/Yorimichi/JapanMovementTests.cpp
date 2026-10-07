#include "JapanMovementNet.h"
#include "BotwNetworkState.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopedCVar.h"
#include "Serialization/BitReader.h"
#include "Serialization/BitWriter.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanMoveInputTest, "Yorimichi.Network.OrderedInput",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanMoveInputTest::RunTest(const FString&)
{
    FJapanMoveInput Input;
    Input.X = -127; Input.Y = 100; Input.Flags = FJapanMoveInput::Sprint | FJapanMoveInput::JumpHeld; Input.FirstEdge = 65535;
    Input.Edges = { uint8(FJapanMoveInput::ButtonIndex(TEXT("attack"))),
        uint8(FJapanMoveInput::ButtonIndex(TEXT("attack_release"))),
        uint8(FJapanMoveInput::ButtonIndex(TEXT("jump"))) };
    FBitWriter Writer(256, true);
    TestTrue(TEXT("Input encodes"), Input.Serialize(Writer));
    TestTrue(TEXT("Three input edges and journal identity fit in eleven bytes"), Writer.GetNumBits() <= 88);
    FBitReader Reader(Writer.GetData(), Writer.GetNumBits());
    FJapanMoveInput Decoded;
    TestTrue(TEXT("Input decodes"), Decoded.Serialize(Reader));
    TestEqual(TEXT("Raw lateral intent survives a locked move"), Decoded.X, Input.X);
    TestEqual(TEXT("Raw forward intent survives a locked move"), Decoded.Y, Input.Y);
    TestEqual(TEXT("Sprint and jump hold levels survive"), Decoded.Flags, Input.Flags);
    TestEqual(TEXT("Journal sequence survives wrap boundary"), Decoded.FirstEdge, Input.FirstEdge);
    TestTrue(TEXT("Press-release-jump ordering survives"), Decoded.Edges == Input.Edges);
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
