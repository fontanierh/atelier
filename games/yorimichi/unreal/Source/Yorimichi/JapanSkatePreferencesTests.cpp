#include "JapanSoundBanks.h"
#include "SkateComponent.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"
#include <limits>

// Host routing only, through the plugin's public API; per-voice behavior is AtelierSkate.Audio.Preferences.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanSkatePreferencesTest,"Yorimichi.Audio.SkatePreferences",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanSkatePreferencesTest::RunTest(const FString&)
{
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Isolated local audio world"),World)) return false;
    auto* Actor=World->SpawnActor<AActor>();
    if(!TestNotNull(TEXT("Local emitter owner"),Actor)) { World->DestroyWorld(false); return false; }
    auto* Pending=NewObject<USkateComponent>(Actor);
    auto* Banks=NewObject<UJapanSoundBanks>(World);
    Banks->SetSkatePreferences(true,.25f);
    TestEqual(TEXT("Board without loaded audio waits for readiness"),Pending->GetSoundVolume(),1.f);
    TestFalse(TEXT("Board without loaded audio is not softened early"),Pending->GetSoftenSounds());
    Banks->SkateReady(Pending);
    TestEqual(TEXT("Late Original board receives saved gain without loading a bank"),Pending->GetSoundVolume(),.25f);
    TestTrue(TEXT("Late Original board receives softening"),Pending->GetSoftenSounds());
    TestFalse(TEXT("Preferences do not load registry or bank"),Banks->bRegistryAttempted);
    TestNull(TEXT("Original remains delegated"),Banks->Active.Get());
    Banks->SetSkatePreferences(true,2.f);
    Banks->SkateReady(Pending);
    TestEqual(TEXT("Host clamps the saved gain"),Pending->GetSoundVolume(),1.f);
    Banks->SetSkatePreferences(true,.25f);
    Banks->SetSkatePreferences(false,std::numeric_limits<float>::quiet_NaN());
    Banks->SkateReady(Pending);
    TestTrue(TEXT("Nonfinite request keeps saved softening"),Pending->GetSoftenSounds());
    TestEqual(TEXT("Footstep preferences stay independent"),Banks->FootstepVolume,1.f);
    TestFalse(TEXT("Footstep softening stays independent"),Banks->bSoftenFootsteps);
    Banks->SetFootstepPreferences(true,.5f);
    TestEqual(TEXT("Footstep changes leave skate gain alone"),Pending->GetSoundVolume(),.25f);
    auto* Unrelated=NewObject<USkateComponent>();
    Banks->SkateReady(Unrelated);
    TestEqual(TEXT("Readiness from another world cannot inherit settings"),Unrelated->GetSoundVolume(),1.f);
    Banks->bShuttingDown=true;
    Banks->SetSkatePreferences(false,1.f);
    Banks->SkateReady(Pending);
    TestEqual(TEXT("Teardown refuses preference mutation"),Pending->GetSoundVolume(),.25f);
    World->DestroyWorld(false);
    return true;
}
bool IsSkateFeelKey(const FString& Key);   // JapanPreferences.cpp: which values the Skate feel page owns

// The Esc menu's main page lists every value the Skate feel page does not own; skate_volume must stay on it.
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanSkateVolumeMenuTest,"Yorimichi.Audio.SkateVolumeMenu",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanSkateVolumeMenuTest::RunTest(const FString&)
{
    TestFalse(TEXT("Skate volume is on the main page"),IsSkateFeelKey(TEXT("skate_volume")));
    TestFalse(TEXT("Skate softening is on the main page"),IsSkateFeelKey(TEXT("soften_skate")));
    TestTrue(TEXT("Skating mode stays on the Skate feel page"),IsSkateFeelKey(TEXT("skate_mode")));
    TestTrue(TEXT("Skate camera stays on the Skate feel page"),IsSkateFeelKey(TEXT("skate_cam_dist")));
    return true;
}
#endif
