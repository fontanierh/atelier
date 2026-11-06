#include "JapanFootsteps.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "HAL/PlatformMisc.h"
#include "Misc/AutomationTest.h"
#include "Sound/SoundWave.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanFootstepShuffleTest, "Yorimichi.Audio.FootstepShuffle",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanFootstepShuffleTest::RunTest(const FString&)
{
    auto Wave=[] { auto* W=NewObject<USoundWave>(); W->Duration=.2f; return W; };
    auto* Foot=NewObject<UJapanFootstepComponent>();
    TestNull(TEXT("No set, no step"),Foot->DrawStep(TEXT("grass")));
    auto* Original=NewObject<UJapanFootstepSet>();
    FJapanFootstepBank Pool;
    for(int32 I=0;I<4;++I) Pool.Steps.Add(Wave());
    Original->Surfaces.Add(TEXT("grass"),Pool);
    Foot->Set=Original;
    TestNotNull(TEXT("Original draws a real sample"),Foot->DrawStep(TEXT("grass")));
    // Feet and hoof stand-ins share one shuffled queue per surface: the rest of this round is the bag's own order,
    // every round plays each sample once, and no sample repeats back to back, across round boundaries too. (A new round
    // reshuffles at random, so it is checked as a set.)
    auto Expected=Foot->Bags[TEXT("grass")];
    USoundWave* Previous=nullptr;
    for(int32 I=0;I<3;++I)
    {
        Previous=Foot->DrawStep(TEXT("grass"));
        TestTrue(TEXT("Each draw continues the surface's single shuffle"),Previous==Pool.Steps[Expected.Draw(4)].Get());
    }
    for(int32 R=0;R<50;++R)
    {
        TSet<USoundWave*> Round;
        for(int32 I=0;I<4;++I)
        {
            USoundWave* Step=Foot->DrawStep(TEXT("grass"));
            if(Step==Previous)
            {
                AddError(FString::Printf(TEXT("Round %d draw %d repeats the previous sample"),R,I));
                return false;
            }
            Round.Add(Previous=Step);
        }
        TestEqual(TEXT("Each new round plays every sample once"),Round.Num(),4);
    }
    TestTrue(TEXT("An unknown surface falls back to the default surface's samples"),
        Pool.Steps.Contains(Foot->DrawStep(TEXT("unmapped"))));
    // The opt-in receiving canary saves this fixture with the old module before
    // changing source. Keep the ordinary shuffle unit test independent of assets.
    const FString SavedPath=FPlatformMisc::GetEnvironmentVariable(TEXT("ATELIER_AUDIO_TYPE_FIXTURE"));
    if (!SavedPath.IsEmpty())
    {
        auto* Saved=LoadObject<UJapanFootstepSet>(nullptr,*SavedPath);
        if (!TestNotNull(TEXT("Previously serialized footstep library loads"),Saved)) return false;
        TestEqual(TEXT("Saved class resolves to its new module"),Saved->GetClass()->GetPathName(),
            FString(TEXT("/Script/YorimichiAssets.JapanFootstepSet")));
        TestNotNull(TEXT("Saved attenuation survives the redirect"),Saved->Attenuation.Get());
        Foot->Set=Saved;
        Foot->Bags.Reset();
        auto* Restored=Foot->DrawStep(Saved->DefaultSurface);
        if (!TestNotNull(TEXT("Runtime consumer draws a saved imported sample"),Restored)) return false;
        TestTrue(TEXT("Saved sample retains positive duration"),Restored->Duration>0.f);
        TestEqual(TEXT("Saved default bank supplies unknown surfaces"),
            Foot->DrawStep(TEXT("compatibility_unmapped")),Restored);
        UE_LOG(LogTemp,Display,TEXT("SAVED FOOTSTEP MODULE REDIRECT consumer verified"));
    }
    return true;
}
#endif
