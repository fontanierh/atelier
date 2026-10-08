#include "JapanCharacterMovement.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "BotwMoveSet.h"
#include "BotwMovementReaction.h"
#include "WandererCharacter.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReactionTransportTest, "Yorimichi.Network.ReactionTransport",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanReactionTransportTest::RunTest(const FString&)
{
    UWorld* TestWorld = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { TestWorld = Context.World(); break; }
    if (!TestNotNull(TEXT("Transport fixture uses a game world"), TestWorld)) return false;
    FActorSpawnParameters Spawn; Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = TestWorld->SpawnActor<AWandererCharacter>(FVector(0., 0., 100000.), FRotator::ZeroRotator, Spawn);
    if (!TestNotNull(TEXT("Transport fixture owns a real character"), Rider)) return false;
    ON_SCOPE_EXIT { Rider->Destroy(); };
    auto* Movement = CastChecked<UJapanCharacterMovement>(Rider->GetCharacterMovement());
    Movement->SetUpdatedComponent(Rider->GetCapsuleComponent()); Movement->Activate(true);
    Rider->Moves = NewObject<UBotwMoveSet>(Rider); Rider->Moves->Character = Rider;
    auto Reset = [&]()
    {
        ++Rider->NetworkActivity.Epoch;
        Movement->ResetActivityPrediction();
        Movement->SetMovementMode(MOVE_Walking);
    };
    FBotwMovementReaction Hit; Hit.Flags = FBotwMovementReaction::SetVelocity;
    Hit.Impulse = FVector(-46.9, 0., 0.);
    FJapanReactionValue Value; if (!TestTrue(TEXT("Transport uses the actual payload codec"), Hit.Encode(Value))) return false;
    FJapanScheduledReaction Event;
    TestTrue(TEXT("Freshly spawned host can issue before any activity reset"), Movement->ReactionJournal.Issue({0, 0.f}, Value, Event));
    TestEqual(TEXT("Initial journal matches the character's already-applied spawn epoch"), Event.Epoch, Rider->GetActivityEpoch());
    auto* FreshOwnerMovement = NewObject<UJapanCharacterMovement>();
    TestTrue(TEXT("Fresh owner journal receives the same initial-epoch event without an activity reset"),
        FreshOwnerMovement->ReactionJournal.Receive(Event) == FJapanReactionJournal::EReceive::Added);
    TestEqual(TEXT("Constructor initialization is not a rejected reset"), Movement->ReactionStats.RejectedResets, 0u);
    Reset();
    const float Step = 1.f / 30.f;
    TestTrue(TEXT("Host resolves a reaction before a lost predecessor"), Movement->ReactionJournal.Issue({0, 0.f}, Value, Event));
    Movement->ReactionCurrent = {0, Step * 3.f}; Movement->ReactionPrevious = {0, 0.f};
    Movement->ActiveInput.ReactionThrough = 1;
    Movement->ActiveInput.ReactionOrigins.Add({1, {{0, Step}, {0, 2.f * Step}, Step}, 0, 0});
    Movement->ActiveInput.Edges.Add(uint8(FJapanMoveInput::ButtonIndex(TEXT("attack"))));
    Movement->ActiveInput.EdgeAgeMilliseconds.Add(0); // The edge is in N+1, after the lost marked N.
    Movement->Velocity = FVector(99.9, 0., 0.);
    uint16 AppliedEdge = 0; double Position = 0.; bool EdgeSawReaction = false;
    TArray<float> Slices;
    Movement->SimulateReactionMove(3.f * Step, [&](float Dt, float Remaining, TOptional<uint16> EdgeThrough)
    {
        Movement->ActiveInput.ApplyNewEdges(AppliedEdge, [&](uint8)
        {
            EdgeSawReaction = Movement->ReactionJournal.Applied() == 1;
            Movement->Velocity.X = 300.; // An action after the reaction changes motion.
        }, EdgeThrough);
        Position += Movement->Velocity.X * Dt; Slices.Add(Dt);
    });
    const double Original = 99.9 * Step - 46.9 * Step + 300. * Step;
    TestTrue(TEXT("Lost N-1 and N retain the newest attack after the reaction"), EdgeSawReaction && AppliedEdge == 1);
    TestTrue(TEXT("Actual host split reproduces the owner's three movement intervals"), Slices.Num() == 3 && FMath::Abs(Position - Original) < .001);
    TestEqual(TEXT("Valid loss split uses no fallback"), Movement->ReactionStats.InvalidOrigins, 0u);

    for (const TArray<uint16>& Ages : {TArray<uint16>{32, 34, 0}, TArray<uint16>{34, 32, 0}, TArray<uint16>{511, 511, 0}})
    {
        Reset();
        Movement->ReactionJournal.Issue({0, 0.f}, Value, Event);
        Movement->ReactionWindows.Add({1, {0, 0.f}, {}, false, 0, 0});
        Movement->ReactionCurrent = {0, Step * 3.f}; Movement->ReactionPrevious = {0, 0.f};
        auto& Input = Movement->ActiveInput; Input.ReactionThrough = 1;
        Input.ReactionOrigins.Add({1, {{0, Step}, {0, Step * 2.f}, Step}, 1, 2});
        Input.Edges = {0, 5, 3}; // pre-origin jump, origin guard, later attack
        Input.EdgeAgeMilliseconds.Append(Ages);
        TArray<uint32> WhenApplied;
        bool OriginGuardEligible = false;
        Movement->SimulateReactionMove(Step * 3.f, [&](float Dt, float Remaining, TOptional<uint16> EdgeThrough)
        {
            Input.ApplyNewEdges(Movement->ProcessedEdge, [&](uint8 Edge)
            {
                WhenApplied.Add(Movement->ReactionJournal.Applied());
                if (Edge == 5) OriginGuardEligible = Movement->ReactionEdgeEligible(Movement->ProcessedEdge);
            }, EdgeThrough);
        });
        TestTrue(TEXT("Edges on either side of a wall-clock rounding boundary retain their saved-move order"),
            WhenApplied == TArray<uint32>({0, 1, 1}));
        TestTrue(TEXT("Origin-frame guard is eligible after the reaction boundary"), OriginGuardEligible);
        TestFalse(TEXT("The lost pre-origin input stays in the pending eligibility window"), Movement->ReactionEdgeEligible(1));
        TestFalse(TEXT("A buffered attack keeps its ineligible original edge after the window closes"), Movement->AllowScheduledAttack(1));
        TestTrue(TEXT("A fresh attack after the apply boundary is eligible"), Movement->AllowScheduledAttack(3));
    }

    Reset();
    auto* DefenceMoves = Rider->Moves.Get();
    for (const uint16 Age : {uint16(0), uint16(511)})
    {
        DefenceMoves->ResetDefence(); // Includes the first press before any clock mapping.
        DefenceMoves->PressNetwork(TEXT("attack"), 7, Age);
        DefenceMoves->PressNetwork(TEXT("guard"), 8, Age);
        TestTrue(TEXT("Unmapped or stale historical time never disables a live attack without a window"),
            DefenceMoves->ReactionAttackEdge.IsSet() && Movement->AllowScheduledAttack(DefenceMoves->ReactionAttackEdge));
        TestTrue(TEXT("Unmapped or stale historical time still permits the held guard"),
            DefenceMoves->bGuardHeld && Movement->ReactionEdgeEligible(DefenceMoves->ReactionGuardEdge, true));
    }
    Movement->ReactionWindows.Add({1, {0, 0.f}, {}, false, 65534, 0});
    TestTrue(TEXT("Missing action origin is eligible even near edge wrap"), Movement->AllowScheduledAttack({}));
    TestTrue(TEXT("Missing guard origin is eligible even near edge wrap"), Movement->ReactionEdgeEligible({}, true));
    TestFalse(TEXT("Wrapped edge zero is a real pending input"), Movement->AllowScheduledAttack(uint16(0)));
    Movement->ReactionWindows.Reset();
    Movement->ReactionWindows.Add({1, {0, 0.f}, {}, false, 0, 0});
    Movement->ReactionWindows.Add({2, {0, Step}, {}, false, 1, 0});
    DefenceMoves->ResetDefence();
    DefenceMoves->PressNetwork(TEXT("guard"), 2, 511);
    DefenceMoves->DefenceTimeline.Hold(2, 10., false);
    auto ResolveHeldGuard = [&](double At)
    {
        FJapanDefenceSample S; S.Time = At; S.ThroughEdge = 2;
        S.bGround = S.bArmed = S.bCanParry = true; S.Forward = FVector::ForwardVector;
        S.bGuardHeld = DefenceMoves->bGuardHeld && Movement->ReactionEdgeEligible(DefenceMoves->ReactionGuardEdge, true);
        DefenceMoves->DefenceTimeline.Record(S);
        uint16 Used = 0;
        return DefenceMoves->DefenceTimeline.Resolve(At, FVector(100., 0., 0.), .5f, Used);
    };
    TestTrue(TEXT("Guard pressed in a pending interval does not block before ACK"), ResolveHeldGuard(10.01) == EJapanDefence::None);
    Movement->ReactionWindows[0].bClosed = true; Movement->ReactionWindows[0].AcknowledgedEdge = 2;
    TestTrue(TEXT("Closing only one overlapping window cannot restore the guard"), ResolveHeldGuard(10.02) == EJapanDefence::None);
    Movement->ReactionWindows[1].bClosed = true; Movement->ReactionWindows[1].AcknowledgedEdge = 2;
    TestTrue(TEXT("Held guard blocks at the second ACK sample without gaining a parry"), ResolveHeldGuard(10.03) == EJapanDefence::Guard);
    TestTrue(TEXT("Holding for another second remains guard, never a new parry"), ResolveHeldGuard(11.03) == EJapanDefence::Guard);
    TestFalse(TEXT("The same closed-window origin remains ineligible for a buffered attack"), Movement->AllowScheduledAttack(2));

    Reset();
    Movement->ReactionJournal.Issue({0, 0.f}, Value, Event);
    // Exercise the insertion shared by ordinary and forced capacity recovery:
    // an event applied before its window is added cannot leave a new open mask.
    Movement->ApplyScheduledThrough(Event.Sequence);
    Movement->ProcessedEdge = 7;
    Movement->AddReactionWindow(Event);
    TestTrue(TEXT("Already-applied event is inserted closed at the current edge"), Movement->ReactionWindows.Last().bClosed &&
        Movement->ReactionWindows.Last().AcknowledgedEdge == 7 && Movement->ReactionEdgeEligible(8));

    Reset();
    // CMC and journal reset are one boundary. The first origin really starts at
    // zero, including a capped first owner move after an activity replacement.
    const float Cap = Movement->GetPredictionData_Server_Character()->MaxMoveDeltaTime;
    const FJapanReactionOrigin First{{0, 0.f}, {0, .4f}, Cap};
    const auto Plan = JapanReactionTiming::Plan({0, 0.f}, {0, 0.f}, {0, .4f}, Cap, Cap,
        Movement->MinTimeBetweenTimeStampResets, First, true);
    TestTrue(TEXT("Capped first move in the new epoch is reconstructed exactly"), Plan.Result == JapanReactionTiming::EResult::Exact && Plan.Before == 0.f && Plan.Reaction == Cap);
    Event.Resolved = {1, .02f};
    TestTrue(TEXT("Wrapped old epoch cannot enter the replacement"), Movement->ReactionJournal.Receive(Event) == FJapanReactionJournal::EReceive::WrongEpoch);
    Movement->ReactionOwnerEnd = Movement->ReactionCurrent = {1, .2f};
    Movement->ResetScheduledReactions();
    TestTrue(TEXT("Rejected same-epoch reset preserves the movement clock"), Movement->ReactionOwnerEnd == FJapanReactionStamp{1, .2f} && Movement->ReactionCurrent == Movement->ReactionOwnerEnd);
    TestEqual(TEXT("Rejected reset has its own counter"), Movement->ReactionStats.RejectedResets, 1u);
    Reset();
    TestTrue(TEXT("Accepted activity reset clears both CMC and reaction clock origins"), Movement->ReactionOwnerEnd == FJapanReactionStamp{} &&
        Movement->GetPredictionData_Client_Character()->CurrentTimeStamp == 0.f && Movement->GetPredictionData_Server_Character()->CurrentClientTimeStamp == 0.f);

    TestTrue(TEXT("Checkpoint fixture issues one payload"), Movement->ReactionJournal.Issue({0, .1f}, Value, Event));
    Movement->ApplyScheduledThrough(1);
    FJapanMoveCheckpoint OwnPostState; OwnPostState.ReactionThrough = 1;
    Movement->AcceptReactionCheckpoint(OwnPostState, 1, false);
    TestTrue(TEXT("Plain correction restores state without pretending the host accepted it"),
        Movement->ReactionJournal.Applied() == 1 && Movement->ReactionAcceptedCheckpoint == 0 && Movement->ReactionJournal.Num() == 1);
    FJapanMoveCheckpoint Earlier; Earlier.ReactionThrough = 0;
    Movement->AcceptReactionCheckpoint(Earlier, 0, false);
    TestEqual(TEXT("Earlier plain correction can replay the retained payload"), Movement->ReactionStats.FailedRestore, 0u);
    Movement->ApplyScheduledThrough(1);
    Movement->AcceptReactionCheckpoint(OwnPostState, 1, true);
    TestTrue(TEXT("Only an accepted authority checkpoint permits retirement"), Movement->ReactionAcceptedCheckpoint == 1 && Movement->ReactionJournal.Num() == 0);

    Reset();
    Movement->ReactionJournal.Issue({0, .1f}, Value, Event);
    Movement->ScheduleReactionDeadline(1, 10., 0., 0.); // Unknown RTT permits the maximum half second.
    Movement->ReactionJournal.Issue({0, .5f}, Value, Event);
    Movement->ScheduleReactionDeadline(2, 10.4, .05, 0.);
    Movement->ApplyScheduledThrough(1); // First ACK arrives; the second is only 50 ms old.
    TestFalse(TEXT("An older reaction deadline cannot force a newer pending event"), Movement->ReactionDeadlineExpired(10.51));
    TestTrue(TEXT("The newer event keeps its own bounded deadline"), Movement->ReactionDeadlineExpired(10.651));
    TestTrue(TEXT("First genuine recovery request is admitted"), Movement->AllowReactionRecoveryRequest(10.45, .05));
    TestFalse(TEXT("Repeated reliable requests cannot force work within one RTT"), Movement->AllowReactionRecoveryRequest(10.46, .05));
    Movement->ApplyScheduledThrough(2);
    TestFalse(TEXT("Covered prefix cannot be repeatedly force-applied"), Movement->AllowReactionRecoveryRequest(10.6, .05));
    TestFalse(TEXT("Fully acknowledged events leave no deadline"), Movement->ReactionDeadlineExpired(100.));
    Reset();
    Movement->ScheduleReactionDeadline(1, 20., .15, 0.);
    Movement->ScheduleReactionDeadline(2, 20.1, .03, 0.);
    TestTrue(TEXT("A later event's earlier deadline fires after an RTT reduction"), Movement->ReactionDeadlineExpired(20.36));
    TestFalse(TEXT("No event is expired before the minimum deadline"), Movement->ReactionDeadlineExpired(20.34));

    auto* Moves = Rider->Moves.Get();
    Moves->bDefenceGetUpPending = true;
    TestTrue(TEXT("Get-up receives protection on its first post-step sample"), Moves->GetUpProtectedAt(30. + Step));
    const double GetUpEnd = Moves->DefenceGetUpUntil;
    TestTrue(TEXT("Get-up sampling adds at most the admitted step to its one second"), GetUpEnd >= 31. && GetUpEnd <= 31. + Step);
    FBotwMovementReaction Dodge; Dodge.Flags = FBotwMovementReaction::PerfectDodge;
    Dodge.FlurryTime = Dodge.Invulnerable = 1.4f;
    Moves->ApplyMovementReaction(Dodge);
    TestTrue(TEXT("Perfect dodge at get-up plus .3 does not rewrite get-up's damage deadline"),
        Moves->GetUpProtectedAt(30.3) && Moves->DefenceGetUpUntil == GetUpEnd && Moves->Invulnerable == 1.4f);
    TestFalse(TEXT("Get-up protection expires independently of the rewritten animation timer"), Moves->GetUpProtectedAt(GetUpEnd + .001));
    FJapanDefenceSample Sample; Sample.Time = 40.; Sample.Forward = FVector::ForwardVector;
    Moves->DefenceTimeline.Reset(); Moves->DefenceTimeline.Record(Sample);
    Moves->DefenceTimeline.Reaction(40., FBotwMovementReaction::HitImmunitySeconds, 0.);
    Sample.Time = 40.69; Moves->DefenceTimeline.Record(Sample);
    uint16 Edge = 0;
    TestTrue(TEXT("Second contact before .7 is immune even without a reaction ACK"),
        Moves->DefenceTimeline.Resolve(40.69, FVector(100., 0., 0.), .5f, Edge) == EJapanDefence::Recovering);
    Sample.Time = 40.71; Moves->DefenceTimeline.Record(Sample);
    TestTrue(TEXT("Second contact after .7 is eligible even while the animation timer remains positive"),
        Moves->DefenceTimeline.Resolve(40.71, FVector(100., 0., 0.), .5f, Edge) == EJapanDefence::None);
    return true;
}
#endif
