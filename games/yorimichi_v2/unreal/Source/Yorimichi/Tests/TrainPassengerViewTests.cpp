#include "TrainPassengerView.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "WandererCharacter.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTrainPassengerViewStateTest, "Yorimichi.Belmonte.TrainViewState",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FTrainPassengerViewStateTest::RunTest(const FString&)
{
    FTrainPassengerView View;
    bool Preference = false, OtherPreference = false;
    TestFalse(TEXT("Toggle is unavailable outside passenger state"), View.Toggle(false, Preference));
    View.Update(true, Preference, .25f);
    TestFalse(TEXT("Third person by default"), View.IsFirstPerson());
    TestTrue(TEXT("Passenger can choose first person"), View.Toggle(true, Preference));
    View.Update(true, Preference, .1f);
    TestFalse(TEXT("The body stays visible early in the blend"), View.HidesBody());
    View.Update(true, Preference, .15f);
    TestTrue(TEXT("First person hides the body only in the view"), View.HidesBody());
    View.Update(false, Preference, .25f);
    TestFalse(TEXT("Leaving or entering a boarding walk releases first person"), View.IsFirstPerson());
    TestFalse(TEXT("The transition completely releases body hiding"), View.HidesBody());
    TestTrue(TEXT("The controller preference is retained"), Preference);
    FTrainPassengerView Replacement;
    Replacement.Update(true, Preference, .25f);
    TestTrue(TEXT("Replacement pawn inherits the same controller choice"), Replacement.IsFirstPerson());
    FTrainPassengerView Other;
    Other.Update(true, OtherPreference, .25f);
    TestFalse(TEXT("Another controller keeps its own third-person choice"), Other.IsFirstPerson());
    TestTrue(TEXT("Toggle back to third person"), Replacement.Toggle(true, Preference));
    Replacement.Update(true, Preference, .25f);
    TestFalse(TEXT("Third person restores the view"), Replacement.HidesBody());
    TestFalse(TEXT("Third person is remembered"), Preference);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTrainPassengerViewBodyTest, "Yorimichi.Belmonte.TrainViewBody",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FTrainPassengerViewBodyTest::RunTest(const FString&)
{
    UWorld* World = nullptr;
    for (const FWorldContext& Context : GEngine->GetWorldContexts())
        if (Context.World() && Context.World()->IsGameWorld()) { World = Context.World(); break; }
    if (!TestNotNull(TEXT("Native world"), World)) return false;
    FActorSpawnParameters Spawn;
    Spawn.ObjectFlags |= RF_Transient; Spawn.bDeferConstruction = true;
    Spawn.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Rider = World->SpawnActor<AWandererCharacter>(FVector(20000,30000,10000), FRotator::ZeroRotator, Spawn);
    auto* Held = World->SpawnActor<AActor>(Spawn);
    ON_SCOPE_EXIT { if (Held) Held->Destroy(); if (Rider) Rider->Destroy(); };
    if (!Rider || !Held) return false;
    auto* Body = NewObject<UBoxComponent>(Rider);
    Body->SetMobility(EComponentMobility::Movable);
    Rider->AddInstanceComponent(Body); Body->SetupAttachment(Rider->GetRootComponent()); Body->RegisterComponent();
    Body->SetOwnerNoSee(true);
    TSet<FPrimitiveComponentId> FirstView, OtherView;
    FTrainPassengerView::AddHiddenBodyComponents(*Rider, FirstView);
    TestTrue(TEXT("Registered fixture has a primitive id"), Body->GetPrimitiveSceneId().IsValid());
    TestTrue(TEXT("Body is hidden in the selected view"), FirstView.Contains(Body->GetPrimitiveSceneId()));
    TestTrue(TEXT("Another view is untouched"), OtherView.IsEmpty());
    TestFalse(TEXT("Physics capsule is not hidden by the camera"), FirstView.Contains(Rider->GetCapsuleComponent()->GetPrimitiveSceneId()));
    // New equipment after first-person entry, with no ownership chain to the pawn.
    auto* Equipment = NewObject<UBoxComponent>(Held);
    Equipment->SetMobility(EComponentMobility::Movable);
    Equipment->SetHiddenInGame(false); // Shape components default to hidden in game; this fixture is visible equipment.
    Held->SetRootComponent(Equipment); Held->AddInstanceComponent(Equipment); Equipment->RegisterComponent();
    Held->AttachToComponent(Rider->GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);
    TestNull(TEXT("Attachment does not need a gameplay owner"), Held->GetOwner());
    TSet<FPrimitiveComponentId> NextView;
    FTrainPassengerView::AddHiddenBodyComponents(*Rider, NextView);
    TestTrue(TEXT("A late attachment is included"), NextView.Contains(Equipment->GetPrimitiveSceneId()));
    TestTrue(TEXT("Pre-existing OwnerNoSee stays set"), Body->bOwnerNoSee);
    TestFalse(TEXT("Visible equipment retains its visibility flags"), Equipment->bOwnerNoSee);
    TestFalse(TEXT("Equipment was not hidden globally"), Equipment->bHiddenInGame);
    return true;
}
#endif
