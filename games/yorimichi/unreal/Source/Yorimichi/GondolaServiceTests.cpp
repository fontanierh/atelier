#include "GondolaService.h"
#include "AtelierData.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGondolaClockTest,"Yorimichi.Gondola.FittedClockAndLevelCabin",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FGondolaClockTest::RunTest(const FString&)
{
    const auto Root=AtelierReadJson(AtelierDataPath(TEXT("gondola/runtime.json")));
    if(!TestTrue(TEXT("Current staged ropeway exists"),Root.IsValid()))return false;
    const FVector Pivot(0.,18.5,-13.);
    for(const auto& V:Root->GetArrayField(TEXT("lines")))
    {
        FGondolaLine L;if(!TestTrue(TEXT("Fitted clock parses"),L.Parse(V->AsObject())))return false;
        for(double Time=0.;Time<L.Cycle;Time+=.37)
        {
            const FGondolaPose P=L.State(Time,Pivot);
            if(!TestTrue(TEXT("Cabin floor stays level"),P.Body.GetUnitAxis(EAxis::Z).Equals(FVector::UpVector,1e-8)))return false;
            if(!TestTrue(TEXT("Grip retains rope contact"),P.Grip.GetLocation().Equals(L.Point(P.Arc),1e-7)))return false;
            if(!TestTrue(TEXT("Grip and hanger share pivot"),P.Grip.TransformPosition(Pivot).Equals(P.Body.TransformPosition(Pivot),1e-7)))return false;
            if(P.Door>0.f&&!TestTrue(TEXT("Open doors stay parked at a berth"),P.Stop!=INDEX_NONE&&FMath::IsNearlyZero(P.Speed,1e-8)))return false;
        }
        for(const auto& Stop:L.Stops)
        {
            const auto A=L.State(Stop.Start+.1,Pivot),B=L.State(Stop.End-.1,Pivot);
            TestTrue(TEXT("Dwell never drifts"),A.Body.Equals(B.Body,1e-8));
        }
        TestTrue(TEXT("Clock wraps"),L.State(-.1,Pivot).Body.Equals(L.State(L.Cycle-.1,Pivot).Body,1e-7));
    }
    return true;
}
#endif
