#include "JapanZeppelinManifest.h"

#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

namespace
{
FJapanZeppelinAdmission ZeppelinReady(uint32 Epoch = 1, int32 Station = 0)
{
    FJapanZeppelinAdmission H; H.Epoch = Epoch; H.Station = Station;
    H.bReady = H.bOnFoot = H.bGrounded = H.bNearStation = true; return H;
}
bool ZeppelinSafeExit(const FJapanZeppelinPassenger&) { return true; }
bool ZeppelinBlockedExit(const FJapanZeppelinPassenger&) { return false; }
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanZeppelinManifestTest, "Yorimichi.Network.ZeppelinManifest",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanZeppelinManifestTest::RunTest(const FString&)
{
    using Reply = EJapanZeppelinReply;
    using Phase = EJapanZeppelinPhase;
    {
        FJapanZeppelinManifest M; M.Initialize(3, 0);
        AddExpectedError(TEXT("Zeppelin committed admission without advancing the epoch"),
            EAutomationExpectedErrorFlags::Contains, 0);
        TestTrue(TEXT("Committed callback is never refused after mutation"),
            M.Board(TEXT("bad-adapter"), 1, M.GetTrip(), 0., ZeppelinReady(),
                [](int32) -> uint32 { return 1; }) == Reply::Accepted);
        TestTrue(TEXT("Even an adapter invariant failure retains safe release"),
            M.Release(TEXT("bad-adapter"), 1, 0., ZeppelinSafeExit));
    }
    {
        FJapanZeppelinManifest M; M.Initialize(3, 0);
        auto Enter = [](int32) -> uint32 { return 2; };
        const uint32 Trip = M.GetTrip();
        M.Board(TEXT("slow"), 1, Trip, 0., ZeppelinReady(), Enter);
        M.Board(TEXT("ready"), 1, Trip, 0., ZeppelinReady(), Enter);
        TestTrue(TEXT("Second passenger can become ready first"), M.ReachedSlot(TEXT("ready"), 2, 1.));
        TestTrue(TEXT("Slow boarder cannot monopolize the boarding lease"), M.GetController() == TEXT("ready"));
        TestTrue(TEXT("Ready controller can select destination before departure"),
            M.SelectDestination(TEXT("ready"), 2, Trip, M.GetLease(), 2, 1.) == Reply::Accepted);
        TestTrue(TEXT("Destination change stales old concurrent boarding snapshot"),
            M.Board(TEXT("late"), 1, Trip, 1., ZeppelinReady(), Enter) == Reply::Stale);
        auto H = ZeppelinReady(); H.MinimumBoardingSeconds = 2.;
        TestTrue(TEXT("Admission closes if the walk cannot fit"),
            M.Board(TEXT("late"), 1, M.GetTrip(), 7., H, Enter) == Reply::BoardingClosed);
        TestEqual(TEXT("Expired slow first boarder safely removed"), M.ExpireBoarding(8., ZeppelinSafeExit), 1);
        TestTrue(TEXT("Ready controller survives expiry"), M.GetController() == TEXT("ready"));
        M.Depart(8., true); M.Arrive(20.);
        M.Disconnect(TEXT("ready"), 20.);
        TestTrue(TEXT("Disembark disconnect stays at destination"), M.GetPhase() == Phase::Disembarking);
        TestEqual(TEXT("Disembark disconnect retains arrived dock"), M.GetDock(), 2);
        TestTrue(TEXT("Disconnected final passenger permits dock completion"), M.FinishDisembarking(20., 0));
    }
    {
        FJapanZeppelinManifest M; M.Initialize(3, 0);
        auto Enter = [](int32) -> uint32 { return 2; };
        M.Board(TEXT("a"), 1, M.GetTrip(), 0., ZeppelinReady(), Enter);
        const uint32 Lease = M.GetLease();
        M.Board(TEXT("b"), 1, M.GetTrip(), 0., ZeppelinReady(), Enter);
        TestEqual(TEXT("Another reservation does not renew unchanged lease"), M.GetLease(), Lease);
        TestEqual(TEXT("Only controller has a safe expiry location"), M.ExpireBoarding(8.,
            [](const FJapanZeppelinPassenger& P) { return P.Player == TEXT("a"); }), 1);
        TestTrue(TEXT("Expired controller's unsafe companion inherits lease"), M.GetController() == TEXT("b"));
        TestTrue(TEXT("Unsafe companion remains protected"), M.Find(TEXT("b")) != nullptr);
        TestEqual(TEXT("Next tick retries safe expiry"), M.ExpireBoarding(8.1, ZeppelinSafeExit), 1);
        TestTrue(TEXT("All expired passengers return ship to docked"), M.GetPhase() == Phase::Docked);
    }
    {
        FJapanZeppelinManifest M;
        TestFalse(TEXT("Reject incomplete line"), M.Initialize(1, 0));
        TestFalse(TEXT("Reject unbounded capacity"), M.Initialize(3, 0, 9));
        TestTrue(TEXT("Initialize a two-slot test deck"), M.Initialize(3, 0, 2));
        TestFalse(TEXT("Never reset an initialized service"), M.Initialize(3, 1));
        const uint32 Trip = M.GetTrip();
        int32 Handoffs = 0;
        auto Enter = [&](int32) -> uint32 { ++Handoffs; return 2; };
        auto H = ZeppelinReady(); H.bPendingContact = true;
        TestTrue(TEXT("Registered hit wins before admission"), M.Board(TEXT("a"), 1, Trip, 1., H, Enter) == Reply::PendingContact);
        H.bPendingContact = false; H.bEncounterHeld = true;
        TestTrue(TEXT("Encounter prevents scripted escape"), M.Board(TEXT("a"), 1, Trip, 1., H, Enter) == Reply::Encounter);
        H = ZeppelinReady(1, 1);
        TestTrue(TEXT("A different station cannot board"), M.Board(TEXT("a"), 1, Trip, 1., H, Enter) == Reply::Unavailable);
        H = ZeppelinReady(); H.bGrounded = false;
        TestTrue(TEXT("Airborne caller refused"), M.Board(TEXT("a"), 1, Trip, 1., H, Enter) == Reply::Unavailable);
        H = ZeppelinReady();
        TestTrue(TEXT("Stale request refused before handoff"), M.Board(TEXT("a"), 9, Trip, 1., H, Enter) == Reply::Stale);
        TestEqual(TEXT("Refusals never enter protected activity"), Handoffs, 0);
        TestTrue(TEXT("Adapter's final combat recheck can refuse"),
            M.Board(TEXT("a"), 1, Trip, 1., H, [](int32) -> uint32 { return 0; }) == Reply::Unsafe);
        TestEqual(TEXT("Failed atomic handoff has no reservation"), M.GetPassengers().Num(), 0);
        TestTrue(TEXT("First protected passenger accepted"), M.Board(TEXT("a"), 1, Trip, 1., H, Enter) == Reply::Accepted);
        TestEqual(TEXT("Visible eight-second deadline"), M.GetBoardingDeadline(), 9.);
        TestTrue(TEXT("First passenger immediately has protected epoch"), M.Find(TEXT("a")) && M.Find(TEXT("a"))->Epoch == 2);
        TestTrue(TEXT("First passenger is route controller"), M.GetController() == TEXT("a"));
        TestTrue(TEXT("Simultaneous second request uses same trip"), M.Board(TEXT("b"), 1, Trip, 1., H, Enter) == Reply::Accepted);
        TestEqual(TEXT("Second boarding does not extend deadline"), M.GetBoardingDeadline(), 9.);
        TestTrue(TEXT("A full deck refuses"), M.Board(TEXT("c"), 1, Trip, 1., H, Enter) == Reply::Full);
        TestTrue(TEXT("Retransmitted admission is idempotent"),
            M.Board(TEXT("a"), 1, Trip, 1., ZeppelinReady(2), Enter) == Reply::Duplicate);
        TestEqual(TEXT("Exactly one epoch handoff per passenger"), Handoffs, 2);
        TestFalse(TEXT("Wrong epoch cannot release passenger"), M.Release(TEXT("a"), 1, 2., ZeppelinSafeExit));
        TestFalse(TEXT("Blocked exit retains protected passenger"), M.Release(TEXT("a"), 2, 2., ZeppelinBlockedExit));
        TestTrue(TEXT("Validated personal exit succeeds"), M.Release(TEXT("a"), 2, 2., ZeppelinSafeExit));
        if (!TestNotNull(TEXT("Remaining passenger record"), M.Find(TEXT("b")))) return false;
        TestEqual(TEXT("Remaining slot never compacts"), M.Find(TEXT("b"))->Slot, 1);
        TestTrue(TEXT("A freed slot can be reserved"), M.Board(TEXT("c"), 1, Trip, 2., H, Enter) == Reply::Accepted);
        if (!TestNotNull(TEXT("Replacement passenger record"), M.Find(TEXT("c")))) return false;
        TestEqual(TEXT("Only freed slot is reused"), M.Find(TEXT("c"))->Slot, 0);
        TestTrue(TEXT("Ready passenger reaches slot"), M.ReachedSlot(TEXT("b"), 2, 3.));
        TestTrue(TEXT("Oldest ready passenger inherits control"), M.GetController() == TEXT("b"));
        TestFalse(TEXT("Ready passengers cannot leave before deadline"), M.Depart(3., true));
        TestFalse(TEXT("Late progress cannot revive an expired reservation"), M.ReachedSlot(TEXT("c"), 2, 9.));
        TestEqual(TEXT("Unsafe expiry cannot drop passenger"), M.ExpireBoarding(9., ZeppelinBlockedExit), 0);
        TestFalse(TEXT("Unsafe expired passenger blocks departure"), M.Depart(9., true));
        TestEqual(TEXT("Safe expiry removes only the unready passenger"), M.ExpireBoarding(9., ZeppelinSafeExit), 1);
        TestTrue(TEXT("Ready passenger remains"), M.Find(TEXT("b")) != nullptr);
        TestFalse(TEXT("Unreserved gangway bystander blocks departure"), M.Depart(9., false));
        TestTrue(TEXT("Clear ready deck departs"), M.Depart(9., true));
        const int32 Destination = M.GetDestination();
        M.Disconnect(TEXT("b"), 10.);
        TestTrue(TEXT("Last disconnect cannot reset flight"), M.GetPhase() == Phase::Flying);
        TestEqual(TEXT("Empty ship retains its safe destination"), M.GetDestination(), Destination);
        TestTrue(TEXT("Empty ship arrives normally"), M.Arrive(20.));
        TestTrue(TEXT("Empty ship finishes dock handoff"), M.FinishDisembarking(20., 2));
    }
    {
        FJapanZeppelinManifest M; M.Initialize(3, 0);
        auto Enter = [](int32) -> uint32 { return 2; };
        const uint32 BoardingTrip = M.GetTrip();
        M.Board(TEXT("a"), 1, BoardingTrip, 0., ZeppelinReady(), Enter);
        M.Board(TEXT("b"), 1, BoardingTrip, 0., ZeppelinReady(), Enter);
        M.ReachedSlot(TEXT("a"), 2, 1.); M.ReachedSlot(TEXT("b"), 2, 1.);
        const uint32 InitialLease = M.GetLease();
        TestTrue(TEXT("Non-controller cannot change route"),
            M.SelectDestination(TEXT("b"), 2, BoardingTrip, InitialLease, 2, 2.) == Reply::NotController);
        TestTrue(TEXT("Controller selects authored destination"),
            M.SelectDestination(TEXT("a"), 2, BoardingTrip, InitialLease, 2, 2.) == Reply::Accepted);
        TestTrue(TEXT("Queued old route command is stale"),
            M.SelectDestination(TEXT("a"), 2, BoardingTrip, InitialLease, 1, 2.) == Reply::Stale);
        TestTrue(TEXT("Departure keeps chosen destination"), M.Depart(8., true));
        TestEqual(TEXT("Chosen destination retained"), M.GetDestination(), 2);
        const uint32 FlyingTrip = M.GetTrip();
        TestTrue(TEXT("Boarding vote cannot leak into flight"),
            M.VoteSkip(TEXT("a"), 2, BoardingTrip, M.GetRoster(), true, 9.) == Reply::Stale);
        TestTrue(TEXT("First passenger consents"), M.VoteSkip(TEXT("a"), 2, FlyingTrip, M.GetRoster(), true, 9.) == Reply::Accepted);
        TestFalse(TEXT("No skip without every passenger"), M.WantsSkip(9.));
        M.VoteSkip(TEXT("b"), 2, FlyingTrip, M.GetRoster(), true, 9.);
        TestTrue(TEXT("Unanimous current votes allow safe docking request"), M.WantsSkip(9.));
        M.VoteSkip(TEXT("b"), 2, FlyingTrip, M.GetRoster(), false, 10.);
        TestFalse(TEXT("Vote revocation takes effect immediately"), M.WantsSkip(10.));
        M.VoteSkip(TEXT("b"), 2, FlyingTrip, M.GetRoster(), true, 10.);
        TestFalse(TEXT("Vote expires at ten seconds"), M.WantsSkip(19.));
        TestTrue(TEXT("Active lease cannot be stolen"), M.RequestControl(TEXT("b"), 2, FlyingTrip, 20.) == Reply::NotController);
        TestTrue(TEXT("Inactive lease transfers on request"), M.RequestControl(TEXT("b"), 2, FlyingTrip, 32.) == Reply::Accepted);
        TestTrue(TEXT("Old lease cannot adjust speed"),
            M.SelectSpeed(TEXT("a"), 2, FlyingTrip, InitialLease, 4, 32.) == Reply::Stale);
        TestTrue(TEXT("New controller can adjust speed"),
            M.SelectSpeed(TEXT("b"), 2, FlyingTrip, M.GetLease(), 4, 32.) == Reply::Accepted);
        TestEqual(TEXT("Speed is bounded authored index"), M.GetSpeedIndex(), 4);
        TestTrue(TEXT("Invalid speed refused"),
            M.SelectSpeed(TEXT("b"), 2, FlyingTrip, M.GetLease(), 6, 32.) == Reply::Invalid);
        TestTrue(TEXT("Destination cannot change in flight"),
            M.SelectDestination(TEXT("b"), 2, FlyingTrip, M.GetLease(), 1, 32.) == Reply::Unavailable);
        M.VoteSkip(TEXT("a"), 2, FlyingTrip, M.GetRoster(), true, 33.); M.VoteSkip(TEXT("b"), 2, FlyingTrip, M.GetRoster(), true, 33.);
        const uint32 OldRoster = M.GetRoster();
        M.Disconnect(TEXT("a"), 34.);
        TestTrue(TEXT("Queued pre-disconnect vote cannot restore consent"),
            M.VoteSkip(TEXT("b"), 2, FlyingTrip, OldRoster, true, 34.) == Reply::Stale);
        TestFalse(TEXT("Roster change clears all inherited consent"), M.WantsSkip(34.));
        TestTrue(TEXT("Remaining passenger still protected"), M.Find(TEXT("b")) != nullptr);
        M.Arrive(40.);
        TestFalse(TEXT("No on-foot ship state until all safe releases finish"), M.FinishDisembarking(40., 1));
        TestFalse(TEXT("Final scripted frame keeps unsafe passenger protected"), M.Release(TEXT("b"), 2, 40., ZeppelinBlockedExit));
        TestTrue(TEXT("Safe final release changes only its passenger"), M.Release(TEXT("b"), 2, 41., ZeppelinSafeExit));
        TestTrue(TEXT("Dock can finish after last safe release"), M.FinishDisembarking(41., 1));
        TestFalse(TEXT("Time cannot run backwards"), M.DispatchCall(40., true));
    }
    {
        FJapanZeppelinManifest M; M.Initialize(3, 0);
        for (int32 I = 0; I < FJapanZeppelinManifest::MaximumCalls; ++I)
            TestTrue(TEXT("Bounded dock calls accepted"), M.Call(FString::Printf(TEXT("p%d"), I), 1,
                1, 1., ZeppelinReady(1, 1)) == Reply::Accepted);
        TestTrue(TEXT("Ninth distinct caller refused"), M.Call(TEXT("overflow"), 1, 1, 1., ZeppelinReady(1, 1)) == Reply::Full);
        TestTrue(TEXT("Repeat call idempotent even while full"), M.Call(TEXT("p0"), 1, 1, 1., ZeppelinReady(1, 1)) == Reply::Duplicate);
        TestTrue(TEXT("Same caller cannot queue another station"), M.Call(TEXT("p0"), 1, 2, 1., ZeppelinReady(1, 2)) == Reply::Stale);
        TestFalse(TEXT("Call cannot remove a bystander's floor"), M.DispatchCall(2., false));
        TestTrue(TEXT("Clear empty ship serves oldest call"), M.DispatchCall(2., true));
        TestTrue(TEXT("Active call remains unserved until arrival"), M.GetActiveCall().Player == TEXT("p0"));
        TestTrue(TEXT("In-flight duplicate cannot create a second request"),
            M.Call(TEXT("p0"), 1, 1, 3., ZeppelinReady(1, 1)) == Reply::Duplicate);
        TestTrue(TEXT("Active call counts against total bound"),
            M.Call(TEXT("overflow"), 1, 1, 3., ZeppelinReady(1, 1)) == Reply::Full);
        TestFalse(TEXT("Stale call cancellation cannot remove current pickup"), M.CancelCall(TEXT("p0"), 99, 4.));
        TestTrue(TEXT("Personal travel cancels only its call"), M.CancelCall(TEXT("p0"), 1, 4.));
        M.Disconnect(TEXT("p0"), 4.);
        TestTrue(TEXT("Caller disconnect cannot reset in-flight service"), M.GetPhase() == Phase::Flying);
        TestEqual(TEXT("Other queued callers remain"), M.GetCalls().Num(), 7);
        TestTrue(TEXT("Vacated request slot can be filled"),
            M.Call(TEXT("next"), 1, 2, 4., ZeppelinReady(1, 2)) == Reply::Accepted);
        TestFalse(TEXT("Another call cannot teleport active flight"), M.DispatchCall(4., true));
        M.Arrive(10.); M.FinishDisembarking(10., 2);
        TestTrue(TEXT("Already fulfilled same-dock calls drained before next station"), M.DispatchCall(11., true));
        TestEqual(TEXT("Next distinct station served in order"), M.GetDestination(), 2);
        TestEqual(TEXT("All same-dock calls consumed"), M.GetCalls().Num(), 0);
    }
    return true;
}
#endif
