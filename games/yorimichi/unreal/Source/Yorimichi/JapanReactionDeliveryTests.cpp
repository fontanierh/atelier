#include "JapanCharacterMovement.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/BitWriter.h"
#include "Serialization/BitReader.h"
#include "JapanReactionDeliveryQA.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

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
    FJapanMovementStats Stats;
    TestFalse(TEXT("No correction does not manufacture a sample"),JapanReactionDeliveryQA::LargestCorrection(Stats).IsValid());
    Stats.LargestCorrectionCm=5.f;
    auto& Sample=Stats.LargestCorrection;
    Sample.Epoch=3; Sample.Timestamp=1.25f; Sample.DeltaTime=1.f/30.f;
    Sample.PredictedLocation=FVector(-25000.123456,-12345.987654,1000.125);
    Sample.AuthoritativeLocation=Sample.PredictedLocation+FVector(3,4,0);
    Sample.PredictedVelocity=FVector(99.9,0,0); Sample.AuthoritativeVelocity=FVector(-46.95,0,0);
    Sample.PredictedAction=TEXT("Run"); Sample.AuthoritativeAction=TEXT("HitF");
    const auto Detail=JapanReactionDeliveryQA::LargestCorrection(Stats);
    FString Text;
    TestTrue(TEXT("Largest correction JSON serializes"),FJsonSerializer::Serialize(Detail.ToSharedRef(),TJsonWriterFactory<>::Create(&Text)));
    TSharedPtr<FJsonObject> Decoded;
    if (!TestTrue(TEXT("Largest correction JSON decodes"),FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Decoded))) return false;
    TestEqual(TEXT("Sample epoch retained"),Decoded->GetNumberField(TEXT("epoch")),3.);
    TestEqual(TEXT("Sample stamp retained"),Decoded->GetNumberField(TEXT("stamp")),1.25);
    TestEqual(TEXT("Predicted XYZ remains numeric without ToString rounding"),Decoded->GetArrayField(TEXT("predicted_position"))[0]->AsNumber(),Sample.PredictedLocation.X);
    TestEqual(TEXT("Measured correction magnitude retained"),Decoded->GetNumberField(TEXT("position_error_cm")),5.);
    TestEqual(TEXT("Measured correction direction retained"),Decoded->GetArrayField(TEXT("delta_cm"))[1]->AsNumber(),4.);
    TestTrue(TEXT("Measured velocity difference retained"),FMath::IsNearlyEqual(Decoded->GetNumberField(TEXT("velocity_error_cm_s")),146.85,1.e-6));
    TestEqual(TEXT("Predicted action retained"),Decoded->GetStringField(TEXT("predicted_action")),FString(TEXT("Run")));
    TestEqual(TEXT("Authoritative action retained"),Decoded->GetStringField(TEXT("authoritative_action")),FString(TEXT("HitF")));
    return true;
}
#endif
