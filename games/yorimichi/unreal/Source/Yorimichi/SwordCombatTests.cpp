#include "SwordCombatRules.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "AdventureMoveSet.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "SwordTrainer.h"
#include "RoninProjectile.h"
#include "Components/BoxComponent.h"
#include "JapanDefenceTimeline.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSwordCombatRulesTest, "Yorimichi.Combat.Rules",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FSwordCombatRulesTest::RunTest(const FString&)
{
    const FVector2f Window(.10f, .13f);
    for (float Hz : {15.f, 30.f, 60.f, 120.f})
    {
        int32 Contacts = 0;
        bool HitThisSwing = false;
        for (float Before = 0.f; Before < .3f; Before += 1.f / Hz)
            if (!HitThisSwing && SwordCombat::CrossesWindow(Before, Before + 1.f / Hz, Window))
            { ++Contacts; HitThisSwing = true; }
        TestEqual(TEXT("A narrow active window lands once at every supported frame rate"), Contacts, 1);
    }
    TestFalse(TEXT("Windup cannot strike early"), SwordCombat::CrossesWindow(0.f, .09f, Window));
    TestFalse(TEXT("Recovery cannot reopen contact"), SwordCombat::CrossesWindow(.14f, .2f, Window));
    SwordCombat::FGuardPressure Pressure;
    for (int32 I = 0; I < 3; ++I)
        TestFalse(TEXT("The first three quick blocks hold"), Pressure.Block(10.f, I * .4, 25.f));
    TestTrue(TEXT("The fourth quick block breaks guard"), Pressure.Block(10.f, 1.2, 25.f));
    TestEqual(TEXT("A break consumes accumulated pressure"), Pressure.At(1.2), 0.f);
    TestTrue(TEXT("A heavy hit can break a fresh guard"), Pressure.Block(28.f, 2., 25.f));
    Pressure.Block(10.f, 3., 25.f); Pressure.Block(10.f, 3.4, 25.f);
    const float Loaded = Pressure.At(3.4);
    TestEqual(TEXT("Short pauses do not erase defensive pressure"), Pressure.At(4.), Loaded);
    TestTrue(TEXT("Disengagement restores guard"), Pressure.At(6.) < Loaded);
    Pressure.Parry(3.5);
    TestTrue(TEXT("Precise defence relieves pressure"), Pressure.At(3.5) < Loaded);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSwordCombatContactTest, "Yorimichi.Combat.Contacts",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FSwordCombatContactTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Contact regression runs in a native game world"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Player = World->SpawnActor<AWandererCharacter>(FVector(0, 0, 100000), FRotator::ZeroRotator, Spawn);
    auto* Npc = World->SpawnActor<ASwordTrainer>(FVector(200, 0, 100000), FRotator::ZeroRotator, Spawn);
    ON_SCOPE_EXIT { if (Player) Player->Destroy(); if (Npc) Npc->Destroy(); };
    if (!Player || !Npc) return false;
    auto* Moves = NewObject<UAdventureMoveSet>(Player); Moves->Character = Player;
    auto* Enemy = NewObject<UAdventureMoveSet>(Npc); Enemy->Character = Npc;
    Player->Moves = Moves; Npc->Moves = Enemy;
    Player->GetSword()->Initialize(Player); Npc->GetSword()->Initialize(Npc);
    const FVector Front = Player->GetActorLocation() + FVector(100, 0, 0);
    Moves->DefenceOverride = EJapanDefence::Guard;
    for (int32 I = 0; I < 4; ++I) Moves->IncomingStrike(Npc, 10.f, Front);
    TestEqual(TEXT("Repeated ordinary blocks resolve a real guard break"), Moves->GuardBreakCount, 1);
    TestTrue(TEXT("Broken guard has a vulnerable recovery"), Moves->GuardBroken > 0.f);
    TestEqual(TEXT("Blocked hits do not deal health damage"), Player->GetSword()->GetHealth(), 100.f);
    Moves->DefenceOverride.Reset(); Moves->GuardBroken = 0.f; Moves->Pressure = {};
    Moves->bArmed = Moves->bGuardHeld = true;
    FAdventureMove Parry; Parry.Name = TEXT("SwordParry"); Parry.Guard.Add(FVector2f(.0333f, .3f));
    Moves->Moves.Add(Parry.Name, Parry);
    Player->AnimationAction = Parry.Name; Player->ActionTime = .08f; Player->ActionSerial = 10;
    TestEqual(TEXT("A precise front contact perfect-parries"), Moves->IncomingStrike(Npc, 10.f, Front), 1);
    TestEqual(TEXT("One attempt cannot perfect-parry a second contact"), Moves->IncomingStrike(Npc, 10.f, Front), 3);
    TestEqual(TEXT("The second contact strains the held guard"), Moves->ParryCount, 1);
    ++Player->ActionSerial;
    TestEqual(TEXT("A rear contact bypasses a parry"), Moves->IncomingStrike(Npc, 10.f,
        Player->GetActorLocation() - FVector(100, 0, 0)), 0);
    Moves->Invulnerable = 0.f;
    ++Player->ActionSerial; Player->ActionTime = .22f;
    TestEqual(TEXT("An early parry expires into an ordinary held block"), Moves->IncomingStrike(Npc, 10.f, Front), 3);
    TestEqual(TEXT("Only the precise attempt counted as a parry"), Moves->ParryCount, 1);
    Player->AnimationAction = NAME_None;
    Moves->bGuardHeld = false; Moves->Invulnerable = 0.f;
    Moves->IncomingStrike(Npc, 10.f, Front);
    TestEqual(TEXT("Player keeps the ordinary hit recovery"), Moves->Invulnerable, .7f);
    const FVector EnemyFront = Npc->GetActorLocation() + FVector(100, 0, 0);
    Enemy->IncomingStrike(Player, 10.f, EnemyFront);
    TestEqual(TEXT("NPC contact uses short combo-compatible recovery"), Enemy->Invulnerable, .1f);
    TestEqual(TEXT("An immediate duplicate still meets NPC recovery"), Enemy->IncomingStrike(Player, 10.f, EnemyFront), 3);
    Enemy->Invulnerable = 0.f;
    TestEqual(TEXT("The next separate cut lands on the NPC"), Enemy->IncomingStrike(Player, 10.f, EnemyFront), 0);
    TestEqual(TEXT("Both separate NPC hits took health"), Npc->GetSword()->GetHealth(), 80.f);

    FJapanDefenceTimeline Timeline;
    FJapanDefenceSample Sample;
    Sample.Time = 10.; Sample.bGround = Sample.bArmed = Sample.bCanParry = Sample.bGuardHeld = true;
    Timeline.Record(Sample); Timeline.Add(1, 10., EJapanDefence::Parry, .0333, .1533);
    Sample.Time = 10.08; Timeline.Record(Sample);
    uint16 Edge = 0;
    TestEqual(TEXT("Server history cannot parry a rear contact"),
        Timeline.Resolve(10.08, FVector(-100, 0, 0), .5f, Edge), EJapanDefence::None);
    TestEqual(TEXT("Rear contact does not consume the front-facing parry"),
        Timeline.Resolve(10.08, FVector(100, 0, 0), .5f, Edge), EJapanDefence::Parry);

    Player->GetSword()->RestoreHealth(); Moves->Invulnerable = 0.f; Moves->Pressure = {};
    Moves->bGuardHeld = true; Player->AnimationAction = Parry.Name;
    ++Player->ActionSerial; Player->ActionTime = .08f;
    auto* Shot = ARoninProjectile::Throw(Npc, Player);
    if (!TestNotNull(TEXT("The scout launches an actual projectile"), Shot)) return false;
    Shot->Tick(.2f);
    TestTrue(TEXT("A swept projectile contact is reflected by a perfect parry"), Shot->bReflected && !Shot->IsActorBeingDestroyed());
    Enemy->Invulnerable = 0.f;
    const float EnemyHealth = Npc->GetSword()->GetHealth();
    Shot->Tick(.2f);
    TestTrue(TEXT("The reflected blade reaches its thrower"), Shot->IsActorBeingDestroyed());
    TestEqual(TEXT("Reflection deals real resolved damage"), Npc->GetSword()->GetHealth(), EnemyHealth - 18.f);

    Shot = ARoninProjectile::Throw(Npc, Player);
    if (!TestNotNull(TEXT("A second projectile launches before cover enters its path"), Shot)) return false;
    auto* Cover = World->SpawnActor<AActor>(FVector(100, 0, 100015), FRotator::ZeroRotator);
    ON_SCOPE_EXIT { if (Cover) Cover->Destroy(); if (Shot && !Shot->IsActorBeingDestroyed()) Shot->Destroy(); };
    auto* Wall = NewObject<UBoxComponent>(Cover);
    Cover->SetRootComponent(Wall); Wall->SetBoxExtent(FVector(4, 100, 100));
    Wall->SetCollisionEnabled(ECollisionEnabled::QueryOnly); Wall->SetCollisionResponseToAllChannels(ECR_Block);
    Wall->RegisterComponent(); Wall->SetWorldLocation(FVector(100, 0, 100015));
    Shot->Tick(.2f);
    TestTrue(TEXT("Cover intercepts the blade between ticks"), Shot->IsActorBeingDestroyed());
    TestEqual(TEXT("Cover protects player health"), Player->GetSword()->GetHealth(), 100.f);
    Cover->Destroy();
    Shot = ARoninProjectile::Throw(Npc, Player);
    if (!TestNotNull(TEXT("The next shot commits to the original target point"), Shot)) return false;
    Player->SetActorLocation(Player->GetActorLocation() + FVector(0, 300, 0));
    Shot->Tick(.2f);
    TestFalse(TEXT("Stepping off the committed line avoids contact"), Shot->IsActorBeingDestroyed());
    TestTrue(TEXT("Flight cannot home after release"), FMath::Abs(Shot->Velocity.Y) < .001f);
    return true;
}
#endif
