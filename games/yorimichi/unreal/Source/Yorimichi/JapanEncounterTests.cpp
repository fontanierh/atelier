#include "JapanEncounters.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "WandererCharacter.h"
#include "FoxHunter.h"
#include "Engine/Engine.h"
#include "Engine/World.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanEncounterReplacementTest, "Yorimichi.Network.EncounterReplacement",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanEncounterReplacementTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Encounter replacement uses a native game world"), World)) return false;
    FActorSpawnParameters Spawn; Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* From = World->SpawnActor<AWandererCharacter>(FVector(0,0,100000), FRotator::ZeroRotator, Spawn);
    auto* To = World->SpawnActor<AWandererCharacter>(FVector(0,0,100000), FRotator::ZeroRotator, Spawn);
    auto* Hunter = World->SpawnActor<AFoxHunter>(FVector(0,0,100000), FRotator::ZeroRotator, Spawn);
    auto* Other = World->SpawnActor<AActor>(Spawn);
    ON_SCOPE_EXIT { if (From) From->Destroy(); if (To) To->Destroy(); if (Hunter) Hunter->Destroy(); if (Other) Other->Destroy(); };
    if (!From || !To || !Hunter || !Other) return false;
    // A private subsystem fixture avoids leaving encounter state in the entry-map world.
    auto* Encounters = NewObject<UJapanEncounters>(World);
    for (AActor* Enemy : {static_cast<AActor*>(Hunter), Other})
    {
        auto& Entry = Encounters->Encounters.FindOrAdd(Enemy);
        Entry.Id = 41; Entry.FrozenHealth = 150;
        Entry.Updated = World->GetTimeSeconds() - 3.; Entry.AttackUntil = 17.; Entry.Attacking = From;
        auto& Member = Entry.Members.FindOrAdd(From); Member.Threat = .75f; Member.bCommitted = true;
        Entry.Members.FindOrAdd(To); // Refresh may have already added the fresh pawn.
    }
    Hunter->Target = From;
    Encounters->ReplacePlayer(From, To);
    for (AActor* Enemy : {static_cast<AActor*>(Hunter), Other})
    {
        const auto& Entry = Encounters->Encounters.FindChecked(Enemy);
        const auto* Member = Entry.Members.Find(To);
        TestTrue(TEXT("Replacement preserves threat and commitment in every encounter"),
            Member && Member->Threat == .75f && Member->bCommitted);
        TestTrue(TEXT("Replacement overwrites the fresh entry and removes the old weak key"),
            Entry.Members.Num() == 1 && !Entry.Members.Contains(From));
        TestTrue(TEXT("The active attack lease follows the player without restarting"),
            Entry.Attacking == To && Entry.AttackUntil == 17.);
        TestTrue(TEXT("Replacement does not refresh a stale encounter or rescale its health"),
            Entry.Updated == World->GetTimeSeconds() - 3. && Entry.Id == 41 && Entry.FrozenHealth == 150);
    }
    TestTrue(TEXT("An attacking hunter targets the replacement before the old pawn is destroyed"), Hunter->Target == To);
    Encounters->ReplacePlayer(From, To);
    TestEqual(TEXT("Repeated handoff retains one committed member"), Encounters->Encounters.FindChecked(Hunter).Members.Num(), 1);
    return true;
}
#endif
