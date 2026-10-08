#include "BotwMovementReaction.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "BotwMoveSet.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "JapanCharacterMovement.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReactionPayloadTest, "Yorimichi.Network.ReactionPayload",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanReactionPayloadTest::RunTest(const FString&)
{
    FBotwMovementReaction Hit;
    Hit.Flags = FBotwMovementReaction::ClearCharge | FBotwMovementReaction::SetVelocity |
        FBotwMovementReaction::Immunity | FBotwMovementReaction::Flinch;
    Hit.Action = TEXT("HitF"); Hit.Blend = .05f; Hit.PlayRate = 1.25f; Hit.SourceStart = .2f;
    Hit.Impulse = FVector(-159.43, 13.6, 0.); Hit.Invulnerable = .7f;
    Hit.FlinchAxis = FVector(.1, -.99, 0.); Hit.FlinchAngle = 15.f; Hit.FlinchPeak = .07f;
    Hit.FlinchTwist = -.45f;
    FJapanReactionValue Encoded;
    TestTrue(TEXT("Resolved movement-only effects encode"), Hit.Encode(Encoded));
    TestEqual(TEXT("Payload has one bounded fixed layout"), Encoded.Bytes.Num(), FBotwMovementReaction::WireBytes);
    FBotwMovementReaction Decoded;
    TestTrue(TEXT("Movement-only effects decode"), FBotwMovementReaction::Decode(Encoded, Decoded));
    FJapanReactionValue Reencoded;
    TestTrue(TEXT("Decoded effects encode again"), Decoded.Encode(Reencoded));
    TestTrue(TEXT("Frozen direction, rate and every scalar survive without quantization"), Encoded == Reencoded);
    // A sender changing its working value cannot alter the already issued event.
    Hit.Impulse = FVector(300., 0., 0.); Hit.Action = TEXT("GuardHit");
    TestTrue(TEXT("Encoded contact remains immutable"), Decoded.Impulse.X == -159.43 && Decoded.Action == TEXT("HitF"));
    for (int32 Size = 0; Size < Encoded.Bytes.Num(); ++Size)
    {
        auto Truncated = Encoded; Truncated.Bytes.SetNum(Size);
        Decoded = Hit;
        TestFalse(TEXT("Truncation is refused before MemoryReader reads fields"), FBotwMovementReaction::Decode(Truncated, Decoded));
        TestTrue(TEXT("Failure clears a reused movement payload"), Decoded.Flags == 0 && Decoded.Action.IsNone());
    }
    auto Extra = Encoded; Extra.Bytes.Add(0);
    TestFalse(TEXT("Trailing bytes cannot smuggle a second effect"), FBotwMovementReaction::Decode(Extra, Decoded));
    Hit.Flags |= FBotwMovementReaction::Launch;
    TestFalse(TEXT("A reaction cannot both replace velocity and queue a launch"), Hit.Encode(Extra));
    Hit.Flags = FBotwMovementReaction::Flinch;
    Hit.FlinchPeak = std::numeric_limits<float>::quiet_NaN();
    TestFalse(TEXT("Nonfinite movement values cannot enter the journal"), Hit.Encode(Extra));
    TestTrue(TEXT("Failed encoding clears old bytes"), Extra.Bytes.IsEmpty());
    Hit = FBotwMovementReaction(); Hit.Flags = 32768;
    TestFalse(TEXT("Unknown effect flags fail closed"), Hit.Encode(Extra));
    Hit.Flags = FBotwMovementReaction::SetVelocity; Hit.Impulse.X = 10001.;
    TestFalse(TEXT("Finite but excessive movement effects are refused"), Hit.Encode(Extra));

    UWorld* TestWorld = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { TestWorld = Context.World(); break; }
    if (!TestNotNull(TEXT("Application equivalence uses a native game world"), TestWorld)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = TestWorld->SpawnActor<AWandererCharacter>(FVector(0., 0., 100000.), FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Application fixture owns a deferred actor with real movement"), Rider)) return false;
    ON_SCOPE_EXIT { Rider->Destroy(); };
    auto* Movement = CastChecked<UJapanCharacterMovement>(Rider->GetCharacterMovement());
    auto* Moves = NewObject<UBotwMoveSet>(Rider); Moves->Character = Rider;
    const float Health = Rider->GetSword()->GetHealth();
    const int32 Hits = Rider->GetSword()->HitsTaken();
    FBotwMovementReaction Direct;
    if (!FBotwMovementReaction::Decode(Encoded, Direct)) return false;
    Direct.Action = NAME_None; // No clip asset is needed; None must never call Play.
    Direct.Flags |= FBotwMovementReaction::Down | FBotwMovementReaction::ClearLunge | FBotwMovementReaction::ResetCombo;
    const auto ResetFixture = [&]()
    {
        Moves->bCharging = true; Moves->AttackBuffer = .25f; Moves->LungeTime = .3f;
        Moves->Combo = 2; Moves->Invulnerable = .1f; Moves->bDown = false; Moves->DownTime = 9.f;
        Moves->FlinchTime = -1.f; Moves->Clock = 42.f; Moves->JumpBuffer = .123f;
        Moves->GuardBroken = 0.f; Moves->FlurryTime = 0.f; Moves->FlurryPoint = FVector::ZeroVector;
        Moves->bFlurryPoint = false; Moves->bHopInvulnerability = true; Moves->bArmed = false;
        Movement->SetPendingLaunch(FVector::ZeroVector);
        Movement->Velocity = FVector(100., 20., 0.);
    };
    ResetFixture(); Moves->ApplyMovementReaction(Direct);
    const FVector ExpectedVelocity = Movement->Velocity, ExpectedAxis = Moves->FlinchAxis;
    const float ExpectedInvulnerable = Moves->Invulnerable, ExpectedAngle = Moves->FlinchAngle;
    const float ExpectedPeak = Moves->FlinchPeak, ExpectedTwist = Moves->FlinchTwist;
    TestTrue(TEXT("Direct application applies the resolved recoil"), ExpectedVelocity == Direct.Impulse);
    TestTrue(TEXT("Direct application resets the relevant action state"), !Moves->bCharging && Moves->AttackBuffer == 0.f &&
        Moves->LungeTime == 0.f && Moves->Combo == 0 && Moves->bDown && Moves->DownTime == 0.f && Moves->FlinchTime == 0.f);
    Direct.Encode(Extra); FBotwMovementReaction Wire;
    if (!TestTrue(TEXT("Application payload decodes"), FBotwMovementReaction::Decode(Extra, Wire))) return false;
    ResetFixture(); Moves->ApplyMovementReaction(Wire);
    TestTrue(TEXT("Decoded application produces identical movement and reaction state"), Movement->Velocity == ExpectedVelocity &&
        Moves->FlinchAxis == ExpectedAxis && Moves->Invulnerable == ExpectedInvulnerable && Moves->FlinchAngle == ExpectedAngle &&
        Moves->FlinchPeak == ExpectedPeak && Moves->FlinchTwist == ExpectedTwist && Moves->FlinchTime == 0.f &&
        !Moves->bCharging && Moves->AttackBuffer == 0.f && Moves->LungeTime == 0.f && Moves->Combo == 0 &&
        Moves->bDown && Moves->DownTime == 0.f);
    TestTrue(TEXT("Application never transplants unrelated prediction state"), Moves->Clock == 42.f && Moves->JumpBuffer == .123f);
    TestTrue(TEXT("Application and replay do not deal damage or count a second hit"),
        Rider->GetSword()->GetHealth() == Health && Rider->GetSword()->HitsTaken() == Hits);
    using R = FBotwMovementReaction;
    const uint16 Cases[] = {R::Launch | R::Down, R::BreakGuard | R::ClearCharge,
        R::PerfectDodge | R::HasFlurryPoint | R::ClearHop, R::ClearHop, R::Immunity};
    for (const uint16 Flags : Cases)
    {
        auto Variant = Direct; Variant.Flags = Flags;
        Variant.Impulse = FVector(380., 0., 280.); Variant.GuardBroken = 1.f;
        Variant.FlurryTime = 1.4f; Variant.Invulnerable = 1.4f; Variant.FlurryPoint = FVector(200., 150., 50.);
        ResetFixture(); Moves->ApplyMovementReaction(Variant);
        const FJapanMoveCheckpoint Expected = Moves->CaptureNetworkState();
        const FVector ExpectedLaunch = Movement->GetPendingLaunch();
        if (Flags & R::Launch) TestTrue(TEXT("Launch queues the frozen velocity"), ExpectedLaunch == Variant.Impulse);
        if (Flags & R::BreakGuard) TestTrue(TEXT("Guard break duration is frozen"), Moves->GuardBroken == Variant.GuardBroken);
        if (Flags & R::PerfectDodge) TestTrue(TEXT("Perfect dodge restores point, duration and equipment without a cue"),
            Moves->FlurryTime == Variant.FlurryTime && Moves->FlurryPoint == Variant.FlurryPoint &&
            Moves->bFlurryPoint && Moves->bArmed && Moves->Invulnerable == Variant.Invulnerable);
        if (Flags & R::ClearHop) TestFalse(TEXT("Reaction clears hop immunity"), Moves->bHopInvulnerability);
        if (!Variant.Encode(Extra) || !FBotwMovementReaction::Decode(Extra, Wire)) return false;
        ResetFixture(); Moves->ApplyMovementReaction(Wire);
        const FJapanMoveCheckpoint Actual = Moves->CaptureNetworkState();
        TestTrue(TEXT("Every reaction variant gives the identical full move-set checkpoint after decode"),
            !Expected.Bytes.IsEmpty() && Expected.Bytes == Actual.Bytes && Expected.Action == Actual.Action &&
            Expected.Target == Actual.Target && Expected.LungeTarget == Actual.LungeTarget && Movement->GetPendingLaunch() == ExpectedLaunch);
        TestTrue(TEXT("No application variant replays health or damage counters"),
            Rider->GetSword()->GetHealth() == Health && Rider->GetSword()->HitsTaken() == Hits);
    }
    return true;
}
#endif
