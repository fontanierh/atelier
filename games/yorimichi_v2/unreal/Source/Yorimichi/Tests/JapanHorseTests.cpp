#include "JapanHorseState.h"
#include "JapanHorseAppearance.h"
#include "JapanBikeSubsteps.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanHorseCheckpointTest, "Yorimichi.Network.HorseCheckpoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanHorseCheckpointTest::RunTest(const FString&)
{
    FJapanHorseState Original;
    Original.Phase = 2; Original.Role = 9; Original.ForcedIdle = 0; Original.Serial = 4011;
    Original.Yaw = -172.5f; Original.Speed = 1180.f; Original.Steering = -.6f; Original.PhaseTime = 3.25f;
    Original.GaitPhase = .875f; Original.IdleTimer = 0.f; Original.IdleCooldown = 9.7f;
    Original.Sprint = true; Original.ReinIn = true;
    TArray<uint8> Bytes; FMemoryWriter Writer(Bytes, true);
    TestTrue(TEXT("A sprinting gallop encodes"), Original.SerializeCheckpoint(Writer));
    TestEqual(TEXT("Fixed horse checkpoint size"), Bytes.Num(), FJapanHorseState::CheckpointBytes);
    FJapanHorseState Restored; FMemoryReader Reader(Bytes, true);
    TestTrue(TEXT("Checkpoint decodes"), Restored.SerializeCheckpoint(Reader) && Reader.AtEnd());
    TestTrue(TEXT("Phase, role and idle variant survive as fixed indices"), Restored.Phase == 2 && Restored.Role == 9 && Restored.ForcedIdle == 0);
    TestEqual(TEXT("Clip serial survives"), Restored.Serial, 4011u);
    TestEqual(TEXT("Facing is restored before replaying relative turns"), Restored.Yaw, -172.5f);
    TestEqual(TEXT("Speed and steering survive"), FVector2D(Restored.Speed, Restored.Steering), FVector2D(1180.f, -.6f));
    TestEqual(TEXT("Clocks survive"), FVector(Restored.PhaseTime, Restored.GaitPhase, Restored.IdleCooldown), FVector(3.25f, .875f, 9.7f));
    TestTrue(TEXT("Sprint and reins survive; not terminal"), Restored.Sprint && Restored.ReinIn && !Restored.Terminal);
    TestEqual(TEXT("The checkpoint action names the rider's clip"), FJapanHorseState::RoleName(Restored.Role), FName(TEXT("HorseGallop")));
    TestTrue(TEXT("No name past the role vocabulary"), FJapanHorseState::RoleName(FJapanHorseState::RoleCount).IsNone());

    FJapanHorseState Idling = Original;
    Idling.Role = 3; Idling.ForcedIdle = 3; Idling.IdleTimer = 2.4f; Idling.Speed = 0.f; Idling.Sprint = false;
    TArray<uint8> IdleBytes; FMemoryWriter IdleWriter(IdleBytes, true);
    FJapanHorseState IdleRestored; FMemoryReader IdleReader(IdleBytes, true);
    TestTrue(TEXT("An idle variant with its timer round-trips"), Idling.SerializeCheckpoint(IdleWriter) &&
        IdleRestored.SerializeCheckpoint(IdleReader) && IdleRestored.ForcedIdle == 3 && IdleRestored.IdleTimer == 2.4f);
    FJapanHorseState Ended; Ended.Phase = 3; Ended.Role = FJapanHorseState::DismountRole; Ended.Terminal = true; Ended.PhaseTime = 1.42f; Ended.GaitPhase = 1.f;
    TestTrue(TEXT("A finished dismount is terminal"), Ended.IsValid());
    TestTrue(TEXT("The default (stowed) state is valid for other activities' handoffs"), FJapanHorseState().IsValid());

    for (int32 Length = 0; Length < Bytes.Num(); ++Length)
    {
        TArray<uint8> Short = Bytes; Short.SetNum(Length);
        FMemoryReader Truncated(Short, true); FJapanHorseState Rejected;
        TestFalse(TEXT("A truncated checkpoint cannot be applied"), Rejected.SerializeCheckpoint(Truncated));
    }
    // Byte 0 phase, 1 role, 2 idle variant, 3 flags: each out of range is rejected before any lookup.
    const int32 CorruptAt[] = {0, 1, 1, 2, 3, 3};
    const uint8 CorruptTo[] = {4, 13, 255, 6, 8, 255};
    for (int32 I = 0; I < UE_ARRAY_COUNT(CorruptAt); ++I)
    {
        TArray<uint8> Bad = Bytes; Bad[CorruptAt[I]] = CorruptTo[I];
        FMemoryReader BadReader(Bad, true); FJapanHorseState Rejected;
        TestFalse(TEXT("Wire vocabulary out of bounds is rejected"), Rejected.SerializeCheckpoint(BadReader));
    }
    FJapanHorseState Bad = Original; Bad.Terminal = true;
    TestFalse(TEXT("Only a dismount can be terminal"), Bad.IsValid());
    TArray<uint8> Unsaved; FMemoryWriter BadWriter(Unsaved, true);
    TestFalse(TEXT("An invalid state is never saved"), Bad.SerializeCheckpoint(BadWriter));
    Bad = Original; Bad.Role = FJapanHorseState::MountRole; TestFalse(TEXT("Riding cannot play the mount"), Bad.IsValid());
    Bad = Original; Bad.Phase = 1; TestFalse(TEXT("Mounting plays only the mount"), Bad.IsValid());
    Bad = Original; Bad.Phase = 0; TestFalse(TEXT("A stowed horse rests at Idle"), Bad.IsValid());
    Bad = Original; Bad.Speed = std::numeric_limits<float>::quiet_NaN(); TestFalse(TEXT("NaN speed cannot enter movement"), Bad.IsValid());
    Bad = Original; Bad.Speed = std::numeric_limits<float>::infinity(); TestFalse(TEXT("Infinite speed cannot enter movement"), Bad.IsValid());
    Bad = Original; Bad.Speed = 1481.f; TestFalse(TEXT("Past the sprint's top speed is rejected"), Bad.IsValid());
    Bad = Original; Bad.Speed = -1.f; TestFalse(TEXT("The horse never runs backwards"), Bad.IsValid());
    Bad = Original; Bad.Yaw = std::numeric_limits<float>::quiet_NaN(); TestFalse(TEXT("NaN yaw rejected"), Bad.IsValid());
    Bad = Original; Bad.GaitPhase = 1.01f; TestFalse(TEXT("Gait phase is a share of the clip"), Bad.IsValid());
    Bad = Original; Bad.IdleCooldown = 13.f; TestFalse(TEXT("Idle cooldown is bounded"), Bad.IsValid());
    Bad = Original; Bad.IdleTimer = -.1f; TestFalse(TEXT("Idle timer is never negative"), Bad.IsValid());
    TArray<uint8> Over = Bytes; const float Huge = 5000.f; FMemory::Memcpy(&Over[12], &Huge, sizeof(float));
    FMemoryReader OverReader(Over, true); FJapanHorseState OverSpeed;
    TestFalse(TEXT("An over-limit speed on the wire is rejected"), OverSpeed.SerializeCheckpoint(OverReader));

    // The horse turns at a rate set by its speed (UHorseComponent::AdvanceSimulation), so a host move merged from two owner
    // frames must split into the same bounded substeps as the owner's prediction.
    const float First = .033333778381347656f, Second = .03336524963378906f;
    auto Path = [&](bool Split, float InitialSpeed, float Steering, float Target, float Rate)
    {
        FVector Position = FVector::ZeroVector;
        float Speed = InitialSpeed, Yaw = 38.00771713256836f;
        auto Advance = [&](float Dt)
        {
            Speed = FMath::FInterpConstantTo(Speed, Target, Dt, Rate);
            Yaw += FMath::Lerp(135.f, 68.f, FMath::Clamp(Speed / 1480.f, 0.f, 1.f)) * Steering * Dt;
            Position += FRotator(0, Yaw, 0).Vector() * Speed * Dt;
        };
        auto Move = [&](float Dt) { JapanBikeSubsteps::Run(Dt, Advance); };
        if (Split) { Move(First); Move(Second); } else Move(First + Second);
        return Position;
    };
    for (const FVector4 Case : {FVector4(1480, 65. / 127., 1480, 720), FVector4(300, -1, 1180, 520), FVector4(1180, .5, 0, 1400)})
        TestTrue(TEXT("Merged and split sprint, gallop and reining in stay within a tenth centimetre"),
            FVector::Dist(Path(true, Case.X, Case.Y, Case.Z, Case.W), Path(false, Case.X, Case.Y, Case.Z, Case.W)) < .1);

    // The look is roster indices, each within its list; an empty list leaves only the imported look (index 0).
    FJapanHorseAppearance Look; Look.Breed = 5; Look.Tack = 6; Look.Coat = 16; Look.Mask = 4; Look.HairColor = 18; Look.HairPattern = 3; Look.Tint = 4;
    TestTrue(TEXT("The last of every list is in range"), Look.IsWithin(6, 7, 17, 5, 19, 4, 5));
    FJapanHorseAppearance Out = Look; Out.Coat = 17;
    TestFalse(TEXT("A coat past the variants is rejected"), Out.IsWithin(6, 7, 17, 5, 19, 4, 5));
    Out = Look; Out.Breed = 6; TestFalse(TEXT("A breed past the roster is rejected"), Out.IsWithin(6, 7, 17, 5, 19, 4, 5));
    TestTrue(TEXT("Empty lists keep only index 0"), FJapanHorseAppearance().IsWithin(0, 0, 1, 0, 0, 0, 0));
    Out = FJapanHorseAppearance(); Out.Tint = 1; TestFalse(TEXT("Index 1 of an empty list is rejected"), Out.IsWithin(1, 1, 1, 1, 1, 1, 0));
    Out = Look; Out.bChosen = true; TestTrue(TEXT("The chosen flag is not part of the look"), Out.SameLook(Look));
    Out.Mask = 0; TestFalse(TEXT("A different mask is a different look"), Out.SameLook(Look));
    return true;
}
#endif
