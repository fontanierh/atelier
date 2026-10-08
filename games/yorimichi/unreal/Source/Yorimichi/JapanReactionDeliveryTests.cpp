#include "JapanCharacterMovement.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/BitWriter.h"
#include "Serialization/BitReader.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReactionSerializationTest,"Yorimichi.Network.ReactionDelivery",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)

bool FJapanReactionSerializationTest::RunTest(const FString&)
{
    auto* Movement=NewObject<UJapanCharacterMovement>();
    Movement->PendingCheckpointTime=2.f;
    Movement->bReactionCheckpointPending=Movement->bReactionCheckpointCaptured=true;
    FJapanMoveResponse Response;
    Response.ClientAdjustment.bAckGoodMove=false;
    Response.ClientAdjustment.TimeStamp=2.f;
    Response.ActivityEpoch=Movement->GetActivityEpoch();
    Response.bHasCheckpoint=true;
    Response.Checkpoint.Action=TEXT("HitF");
    Response.Checkpoint.Bytes.Add(1);
    FBitWriter MissingMap(8192,true);
    TestFalse(TEXT("Missing package map fails the actual packed checkpoint serializer"),Response.Serialize(*Movement,MissingMap,nullptr));
    TestTrue(TEXT("Failed checkpoint serialization reports its archive error"),MissingMap.IsError());
    TestFalse(TEXT("Failed serialization must not mark a reaction as sent"),Movement->bCheckpointSerialized);
    TestTrue(TEXT("Failed serialization retains the pending reaction"),Movement->bReactionCheckpointPending);
    Movement->MovementCheckpointSerialized(Response.ActivityEpoch+1,2.f);
    TestFalse(TEXT("An old epoch cannot certify the current response"),Movement->bCheckpointSerialized);
    Movement->MovementCheckpointSerialized(Response.ActivityEpoch,1.f);
    TestFalse(TEXT("An old response stamp cannot certify the current capture"),Movement->bCheckpointSerialized);
    Movement->MovementCheckpointSerialized(Response.ActivityEpoch,2.f);
    TestTrue(TEXT("The matching successful-serializer callback identifies this capture"),Movement->bCheckpointSerialized);
    // No owner means UE sends nothing. The real override still resets the marker
    // before calling UE, so an earlier successful send cannot consume this queue.
    Movement->SendClientAdjustment();
    TestFalse(TEXT("Every send attempt clears the previous serialization result"),Movement->bCheckpointSerialized);
    TestTrue(TEXT("A send attempt without a response retains pending state"),Movement->bReactionCheckpointPending);
    Response.ClientAdjustment.bAckGoodMove=true;
    Response.bHasCheckpoint=false;
    FBitWriter GoodAck(8192,true);
    TestTrue(TEXT("A good ACK serializes normally without a checkpoint"),Response.Serialize(*Movement,GoodAck,nullptr));
    TestFalse(TEXT("A good ACK cannot certify a reaction checkpoint"),Movement->bCheckpointSerialized);
    TestTrue(TEXT("A good ACK does not discard the pending reaction"),Movement->bReactionCheckpointPending);
    FJapanMoveResponse Reused;
    Reused.bHasCheckpoint=true;
    Reused.Checkpoint.Action=TEXT("HitF");
    Reused.Checkpoint.Bytes.Add(1);
    FBitReader AckReader(GoodAck.GetData(),GoodAck.GetNumBits());
    TestTrue(TEXT("Good ACK decodes into the previously used correction container"),Reused.Serialize(*Movement,AckReader,nullptr));
    TestTrue(TEXT("Decoded response is a good ACK"),Reused.IsGoodMove());
    TestFalse(TEXT("Good ACK does not retain a previous checkpoint flag"),Reused.bHasCheckpoint);
    TestTrue(TEXT("Good ACK does not retain a previous checkpoint payload"),Reused.Checkpoint.Bytes.IsEmpty());
    TestTrue(TEXT("Good ACK does not retain a previous checkpoint action"),Reused.Checkpoint.Action.IsNone());
    Response.ClientAdjustment.bAckGoodMove=false;
    Response.bHasCheckpoint=false;
    FBitWriter EmptyCorrection(8192,true);
    TestTrue(TEXT("Correction without a checkpoint serializes normally"),Response.Serialize(*Movement,EmptyCorrection,nullptr));
    Reused.bHasCheckpoint=true;
    Reused.Checkpoint.Action=TEXT("GuardHit");
    Reused.Checkpoint.Bytes.Add(2);
    FBitReader CorrectionReader(EmptyCorrection.GetData(),EmptyCorrection.GetNumBits());
    TestTrue(TEXT("Correction without checkpoint decodes into used container"),Reused.Serialize(*Movement,CorrectionReader,nullptr));
    TestTrue(TEXT("Decoded response remains a correction"),Reused.IsCorrection());
    TestFalse(TEXT("Correction without checkpoint clears the prior flag"),Reused.bHasCheckpoint);
    TestTrue(TEXT("Correction without checkpoint clears prior payload"),Reused.Checkpoint.Bytes.IsEmpty());
    TestTrue(TEXT("Correction without checkpoint clears prior action"),Reused.Checkpoint.Action.IsNone());
    return true;
}
#endif
