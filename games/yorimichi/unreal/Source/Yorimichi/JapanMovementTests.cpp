#include "JapanMovementNet.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/BitReader.h"
#include "Serialization/BitWriter.h"

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
    TestFalse(TEXT("A truncated transition stream cannot be applied"), MissingRelease.Serialize(Truncated));
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
#endif
