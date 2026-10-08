#include "JapanReactionJournal.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanReactionJournalTest, "Yorimichi.Network.ReactionJournal",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanReactionJournalTest::RunTest(const FString&)
{
    using EReceive = FJapanReactionJournal::EReceive;
    FJapanReactionJournal Host, Owner;
    Host.Reset(7); Owner.Reset(7);
    FJapanReactionValue Hit{TEXT("HitF"), {1, 2, 3}};
    FJapanReactionValue Guard{TEXT("GuardHit"), {4, 5}};
    FJapanScheduledReaction First, Second;
    FJapanReactionValue Empty, Oversized = Hit;
    Oversized.Bytes.SetNum(FJapanReactionValue::MaximumBytes + 1);
    TestFalse(TEXT("Empty payload cannot enter the host journal"), Host.Issue({0, 1.f}, Empty, First));
    TestFalse(TEXT("Oversized payload cannot enter the host journal"), Host.Issue({0, 1.f}, Oversized, First));
    TestFalse(TEXT("Nonfinite origin cannot enter the host journal"),
        Host.Issue({0, std::numeric_limits<float>::quiet_NaN()}, Hit, First));
    TestFalse(TEXT("Negative origin cannot enter the host journal"), Host.Issue({0, -1.f}, Hit, First));
    TestEqual(TEXT("Invalid values allocate no sequence"), Host.Known(), 0u);
    TestTrue(TEXT("Host freezes the first value"), Host.Issue({0, 1.f}, Hit, First));
    TestTrue(TEXT("Host freezes the second value"), Host.Issue({0, 1.1f}, Guard, Second));
    Hit.Bytes[0] = 99;
    TestEqual(TEXT("Caller mutation cannot alter the queued payload"), Host.Find(1)->Value.Bytes[0], uint8(1));
    FJapanReactionJournal Gapped;
    Gapped.Reset(7);
    TestTrue(TEXT("Future sequence cannot skip an undelivered value"), Gapped.Receive(Second) == EReceive::Gap);
    TestEqual(TEXT("Gap cannot advance the known sequence"), Gapped.Known(), 0u);
    TestTrue(TEXT("Gap requires counted host reconciliation"), Gapped.NeedsRecovery());
    TestEqual(TEXT("Gap counts one recovery request"), Gapped.RecoveryRequests, 1u);
    TestTrue(TEXT("First delivery is added"), Owner.Receive(First) == EReceive::Added);
    TestTrue(TEXT("Exact duplicate is idempotent"), Owner.Receive(First) == EReceive::Duplicate);
    auto Changed = First; Changed.Value.Bytes[0] = 9;
    TestTrue(TEXT("Conflicting duplicate cannot replace a frozen value"), Owner.Receive(Changed) == EReceive::Invalid);
    Changed = Second; Changed.Value = Oversized;
    TestTrue(TEXT("Oversized received value is rejected before allocation"), Owner.Receive(Changed) == EReceive::Invalid);
    Changed = Second; Changed.Sequence = 0;
    TestTrue(TEXT("Zero event id is invalid"), Owner.Receive(Changed) == EReceive::Invalid);
    Changed = Second; Changed.Epoch = 6;
    TestTrue(TEXT("Old epoch cannot enter this journal"), Owner.Receive(Changed) == EReceive::WrongEpoch);
    TestTrue(TEXT("Second delivery is added"), Owner.Receive(Second) == EReceive::Added);

    TArray<uint32> Applied;
    FName Action;
    auto Apply = [&](const FJapanScheduledReaction& Item) { Applied.Add(Item.Sequence); Action = Item.Value.Action; };
    TestFalse(TEXT("Unknown acknowledgement cannot partially apply known values"), Owner.Apply(3, Apply));
    TestTrue(TEXT("Invalid range has no callbacks"), Applied.IsEmpty());
    TestTrue(TEXT("Old move keeps its own zero marker"), Owner.Apply(0, Apply));
    TestTrue(TEXT("Pending move keeps its own zero marker"), Owner.Apply(0, Apply));
    TestTrue(TEXT("New move applies both received events"), Owner.Apply(2, Apply));
    TestTrue(TEXT("Ascending composition is exactly once"), Applied == TArray<uint32>({1, 2}));
    TestEqual(TEXT("Last action wins without replaying health or cues"), Action, Guard.Action);
    TestTrue(TEXT("Repeated marker does not repeat movement reaction"), Owner.Apply(2, Apply));
    TestEqual(TEXT("Exactly two callbacks before replay"), Applied.Num(), 2);
    TestTrue(TEXT("Correction before the events restores their applied marker"), Owner.Restore(0));
    TestTrue(TEXT("Replay re-applies both immutable values"), Owner.Apply(2, Apply));
    TestTrue(TEXT("Replay preserves event order"), Applied == TArray<uint32>({1, 2, 1, 2}));

    Owner.Retire(2, 0);
    TestEqual(TEXT("Good ACK disposal alone retains replay payloads"), Owner.Num(), 2);
    Owner.Retire(0, 1);
    TestEqual(TEXT("Checkpoint retires only the independently disposed prefix"), Owner.Retired(), 1u);
    TestEqual(TEXT("Later payload remains retained"), Owner.Num(), 1);
    TestFalse(TEXT("A stale checkpoint cannot restore retired history"), Owner.Restore(0));
    TestTrue(TEXT("An accepted but unreplayable checkpoint requires recovery"), Owner.NeedsRecovery());
    TestEqual(TEXT("Failed restore is counted"), Owner.FailedRestores, 1u);
    TestTrue(TEXT("A newer authoritative checkpoint can reconcile the journal"), Owner.Restore(2));
    Owner.Retire(2, 2);
    TestEqual(TEXT("Both conditions retire all covered values"), Owner.Num(), 0);
    TestTrue(TEXT("Retired retransmission is covered, never reapplied"), Owner.Receive(First) == EReceive::Covered);

    Owner.Reset(8);
    TestTrue(TEXT("An accepted checkpoint may overtake reliable delivery"), Owner.Restore(2));
    First.Epoch = 8; Second.Epoch = 8;
    TestTrue(TEXT("Late covered first payload is ignored"), Owner.Receive(First) == EReceive::Covered);
    TestTrue(TEXT("Late covered second payload is ignored"), Owner.Receive(Second) == EReceive::Covered);
    const int32 Before = Applied.Num();
    TestTrue(TEXT("Covered marker is already applied"), Owner.Apply(2, Apply));
    TestEqual(TEXT("No second apparent hit after overtaking checkpoint"), Applied.Num(), Before);
    TestFalse(TEXT("Covered checkpoint creates no pending motion"), Owner.HasPending());
    TestEqual(TEXT("Overtaking checkpoint advances sampling marker"), Owner.Known(), 2u);

    Host.Reset(9);
    for (int32 I = 0; I < FJapanReactionJournal::Capacity; ++I)
        TestTrue(TEXT("Bounded pending event fits"), Host.Issue({0, 2.f}, Guard, First));
    TestFalse(TEXT("Ninth pending event requests fallback without eviction"), Host.Issue({0, 2.f}, Guard, First));
    TestEqual(TEXT("Overflow cannot lose the oldest event"), Host.Find(1)->Sequence, 1u);
    TestEqual(TEXT("Overflow leaves sequence unchanged"), Host.Known(), 8u);
    TestTrue(TEXT("Apply one event but retain it until checkpoint"), Host.Apply(1, [](const auto&) {}));
    TestTrue(TEXT("One retained plus eight pending fits"), Host.Issue({0, 2.f}, Guard, First));
    TestTrue(TEXT("Accepted events can all be applied"), Host.Apply(9, [](const auto&) {}));
    TestFalse(TEXT("Retention capacity prevents silent replay-history eviction"), Host.Issue({0, 2.f}, Guard, First));
    Host.Retire(9, 0);
    TestFalse(TEXT("Unsent checkpoint does not free host payloads"), Host.Issue({0, 2.f}, Guard, First));
    Host.Retire(9, 9);
    TestTrue(TEXT("Successfully sent checkpoint permits next sequence"), Host.Issue({0, 3.f}, Guard, First));
    TestEqual(TEXT("Retirement never reuses an event id"), First.Sequence, 10u);
    Host.Reset(10);
    TestFalse(TEXT("Epoch replacement cancels pending motion"), Host.HasPending());
    TestEqual(TEXT("Epoch replacement empties retained payloads"), Host.Num(), 0);
    TestTrue(TEXT("Old epoch cannot resurrect cancelled motion"), Host.Receive(First) == EReceive::WrongEpoch);
    TestFalse(TEXT("Same epoch reset cannot erase the journal"), Host.Reset(10));
    TestFalse(TEXT("Late epoch reset cannot reopen cancelled history"), Host.Reset(9));
    TestFalse(TEXT("Zero epoch is never a replacement"), Host.Reset(0));
    TestEqual(TEXT("Rejected resets are counted"), Host.RejectedResets, 3u);
    TestTrue(TEXT("Accepted terminal sequence can be restored"), Host.Restore(MAX_uint32));
    TestFalse(TEXT("Sequence exhaustion requests replacement rather than wrapping"), Host.Issue({0, 4.f}, Guard, First));
    TestEqual(TEXT("Exhaustion cannot wrap through zero"), Host.Known(), MAX_uint32);

    FJapanReactionJournal AheadHost, LaggedOwner;
    AheadHost.Reset(20); LaggedOwner.Reset(20);
    for (int32 I = 0; I < FJapanReactionJournal::Capacity; ++I)
    {
        TestTrue(TEXT("Host issues the initial window"), AheadHost.Issue({0, 5.f}, Guard, First));
        TestTrue(TEXT("Owner receives the initial window"), LaggedOwner.Receive(First) == EReceive::Added);
    }
    TestTrue(TEXT("Host applies the initial window"), AheadHost.Apply(8, [](const auto&) {}));
    TestTrue(TEXT("Owner applies the initial window"), LaggedOwner.Apply(8, [](const auto&) {}));
    AheadHost.Retire(8, 8); // Serialized host checkpoint is lost before the owner accepts it.
    LaggedOwner.Retire(8, 0);
    TestTrue(TEXT("Host can issue while the owner retains applied values"), AheadHost.Issue({0, 5.1f}, Guard, First));
    TestTrue(TEXT("The owner's one retained spare fits"), LaggedOwner.Receive(First) == EReceive::Added);
    TestTrue(TEXT("Host advances its next event"), AheadHost.Apply(9, [](const auto&) {}));
    AheadHost.Retire(9, 9);
    TestTrue(TEXT("Host issues beyond the owner's retained capacity"), AheadHost.Issue({0, 5.2f}, Guard, First));
    TestTrue(TEXT("Reliable delivery overflow is explicit"), LaggedOwner.Receive(First) == EReceive::Full);
    TestTrue(TEXT("Overflow cannot silently lose reliable delivery"), LaggedOwner.NeedsRecovery());
    TestTrue(TEXT("Recovery blocks voluntary activity admission"), LaggedOwner.HasPending());
    TestTrue(TEXT("Correction can restore an earlier retained marker during recovery"), LaggedOwner.Restore(7));
    TArray<uint32> RecoveryReplay;
    TestTrue(TEXT("Recovery still replays every present contiguous payload"),
        LaggedOwner.Apply(9, [&](const auto& Item) { RecoveryReplay.Add(Item.Sequence); }));
    TestTrue(TEXT("Mid-recovery replay applies exactly the retained suffix"), RecoveryReplay == TArray<uint32>({8, 9}));
    TestTrue(TEXT("Replaying known values does not clear missed-delivery recovery"), LaggedOwner.NeedsRecovery());
    TestTrue(TEXT("Host may still advance before reconciliation"), AheadHost.Apply(10, [](const auto&) {}));
    AheadHost.Retire(10, 10);
    TestTrue(TEXT("Another in-flight reliable event is issued"), AheadHost.Issue({0, 5.3f}, Guard, First));
    TestTrue(TEXT("Subsequent missed values extend the recovery prefix"), LaggedOwner.Receive(First) == EReceive::Recovering);
    TestTrue(TEXT("Checkpoint before the last missed value is insufficient"), LaggedOwner.Restore(10));
    TestTrue(TEXT("Partial reconciliation stays blocked"), LaggedOwner.NeedsRecovery());
    TestTrue(TEXT("Forced host checkpoint covers every missed value"), LaggedOwner.Restore(11));
    TestFalse(TEXT("Complete reconciliation releases the latch"), LaggedOwner.NeedsRecovery());
    LaggedOwner.Retire(11, 11); // CMC discarded the covered moves and accepted this checkpoint.
    TestEqual(TEXT("Recovery remains a named non-pass after repair"), LaggedOwner.RecoveryRequests, 1u);
    TestEqual(TEXT("Reconciled history is bounded and empty"), LaggedOwner.Num(), 0);
    TestTrue(TEXT("Host applies event eleven"), AheadHost.Apply(11, [](const auto&) {}));
    AheadHost.Retire(11, 11);
    TestTrue(TEXT("Host resumes after recovery"), AheadHost.Issue({0, 5.4f}, Guard, First));
    TestTrue(TEXT("Owner resumes at the next sequence without a permanent gap"), LaggedOwner.Receive(First) == EReceive::Added);
    return true;
}
#endif
