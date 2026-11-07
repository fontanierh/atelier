#include "JapanFootsteps.h"
#include "JapanAudioPreferences.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Components/AudioComponent.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Misc/AutomationTest.h"
#include "Sound/SoundWave.h"
#include <limits>

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanFootstepPreferencesTest,"Yorimichi.Audio.FootstepPreferences",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanFootstepPreferencesTest::RunTest(const FString&)
{
    auto* Foot=NewObject<UJapanFootstepComponent>();
    auto* Voice=NewObject<UAudioComponent>();
    auto* Other=NewObject<UAudioComponent>();
    Other->SetVolumeMultiplier(.7f);
    Foot->ApplyVoicePreferences(Voice,.8f);
    TestEqual(TEXT("Default preserves contact gain"),Voice->VolumeMultiplier,.8f);
    TestFalse(TEXT("Default bypasses the low-pass"),bool(Voice->bEnableLowPassFilter));
    Foot->FootstepVoices.Add(Voice,.8f);
    Foot->SetAudioPreferences(true,.5f);
    TestEqual(TEXT("Existing voice updates immediately"),Voice->VolumeMultiplier,.4f);
    TestTrue(TEXT("Existing voice enables real engine low-pass"),bool(Voice->bEnableLowPassFilter));
    TestEqual(TEXT("Soft cutoff in hertz"),Voice->LowPassFilterFrequency,3000.f);
    auto* Future=NewObject<UAudioComponent>();
    Foot->ApplyVoicePreferences(Future,.6f);
    TestEqual(TEXT("Next voice inherits gain before play"),Future->VolumeMultiplier,.3f);
    TestTrue(TEXT("Next voice inherits filter before play"),bool(Future->bEnableLowPassFilter));
    Foot->SetAudioPreferences(false,1.f);
    TestEqual(TEXT("Repeated changes use original gain without compounding"),Voice->VolumeMultiplier,.8f);
    TestFalse(TEXT("Disabling restores unfiltered voice"),bool(Voice->bEnableLowPassFilter));
    Foot->SetAudioPreferences(true,-1.f);
    TestEqual(TEXT("Zero floor mutes only owned voice"),Voice->VolumeMultiplier,0.f);
    Foot->SetAudioPreferences(false,2.f);
    TestEqual(TEXT("Upper bound restores original gain"),Voice->VolumeMultiplier,.8f);
    Foot->SetAudioPreferences(true,std::numeric_limits<float>::quiet_NaN());
    TestFalse(TEXT("Nonfinite request preserves filter"),bool(Voice->bEnableLowPassFilter));
    TestEqual(TEXT("Nonfinite request preserves gain"),Voice->VolumeMultiplier,.8f);
    TestEqual(TEXT("Unowned hoof/skate/music voice remains untouched"),Other->VolumeMultiplier,.7f);
    Foot->Set=NewObject<UJapanFootstepSet>();
    Foot->SetAudioPreferences(true,.5f);
    TestEqual(TEXT("Repeated softening keeps the existing voice's base gain"),Voice->VolumeMultiplier,.4f);
    auto* Later=NewObject<UAudioComponent>();
    Foot->ApplyVoicePreferences(Later,.5f);
    TestEqual(TEXT("Later voice inherits gain"),Later->VolumeMultiplier,.25f);
    TestTrue(TEXT("Later voice is filtered on Play"),bool(Later->bEnableLowPassFilter));
    TestEqual(TEXT("Later voice uses the soft cutoff"),Later->LowPassFilterFrequency,3000.f);
    Foot->StopFootstepVoices();
    TestTrue(TEXT("Cleanup releases owned handles"),Foot->FootstepVoices.IsEmpty());
    TestFalse(TEXT("Cleanup destroys the owned voice"),IsValid(Voice));
    TestTrue(TEXT("Cleanup retains unowned audio"),IsValid(Other));

    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false);
    UWorld* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if(!TestNotNull(TEXT("Isolated local audio world"),World)) return false;
    auto* Actor=World->SpawnActor<AActor>();
    if(!TestNotNull(TEXT("Local emitter owner"),Actor)) { World->DestroyWorld(false); return false; }
    auto* Ready=NewObject<UJapanFootstepComponent>(Actor);
    Ready->Set=NewObject<UJapanFootstepSet>();
    auto* Prefs=NewObject<UJapanAudioPreferences>(World);
    Prefs->SetFootstepPreferences(true,.25f);
    TestEqual(TEXT("Already-ready world emitter receives local gain"),Ready->FootstepVolume,.25f);
    TestTrue(TEXT("Already-ready world emitter receives softening"),Ready->bSoftenFootsteps);
    auto* Late=NewObject<UJapanFootstepComponent>(Actor);
    Late->Set=Ready->Set;
    Prefs->FootReady(Late);
    TestEqual(TEXT("Late emitter receives saved gain"),Late->FootstepVolume,.25f);
    TestTrue(TEXT("Late emitter receives softening"),Late->bSoftenFootsteps);
    auto* Unrelated=NewObject<UJapanFootstepComponent>();
    Prefs->FootReady(Unrelated);
    TestEqual(TEXT("Readiness from another world cannot inherit settings"),Unrelated->FootstepVolume,1.f);
    Prefs->bShuttingDown=true;
    Prefs->SetFootstepPreferences(false,1.f);
    TestEqual(TEXT("Teardown refuses preference mutation"),Ready->FootstepVolume,.25f);
    World->DestroyWorld(false);
    return true;
}
#endif
