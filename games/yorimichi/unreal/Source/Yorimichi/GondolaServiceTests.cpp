#include "GondolaService.h"
#include "AtelierData.h"
#include "BelmonteRegion.h"
#include "Misc/AutomationTest.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Misc/ScopeExit.h"

#if WITH_DEV_AUTOMATION_TESTS
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGondolaClockTest,"Yorimichi.Gondola.FittedClockAndLevelCabin",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FGondolaClockTest::RunTest(const FString&)
{
    const auto Root=AtelierReadJson(AtelierDataPath(TEXT("gondola/runtime.json")));
    if(!TestTrue(TEXT("Current staged ropeway exists"),Root.IsValid()))return false;
    UWorld* World=nullptr;
    for(const FWorldContext& Context:GEngine->GetWorldContexts())
        if(Context.World()&&Context.World()->IsGameWorld()){World=Context.World();break;}
    if(!TestNotNull(TEXT("Native game world"),World))return false;
    const bool Created=AGondolaService::Find(World)==nullptr;
    auto* Service=AGondolaService::Spawn(World,AtelierDataPath(TEXT("gondola/runtime.json")));
    ON_SCOPE_EXIT{if(Created&&Service)Service->Destroy();};
    if(!TestNotNull(TEXT("Complete imported ropeway initializes"),Service))return false;
    TestTrue(TEXT("Production service is ready"),Service->bReady&&!Service->bFailed);
    TestEqual(TEXT("All three fitted lines initialize"),Service->Lines.Num(),Root->GetArrayField(TEXT("lines")).Num());
    TestEqual(TEXT("Every staged station initializes"),Service->Stations.Num(),Root->GetArrayField(TEXT("stations")).Num());
    int32 ExpectedCabins=0;
    for(const auto& Line:Service->Lines)ExpectedCabins+=Line.CabinCount;
    TestEqual(TEXT("Complete cabin roster initializes"),Service->Cabins.Num(),ExpectedCabins);
    for(const auto& Cabin:Service->Cabins)
        if(!TestTrue(TEXT("Every cabin has imported body, grip and physical door"),
            Cabin.Body!=nullptr&&Cabin.Grip!=nullptr&&Cabin.DoorBlock!=nullptr))return false;
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
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FGondolaTreeClearanceTest,"Yorimichi.Gondola.NorthTreeClearance",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FGondolaTreeClearanceTest::RunTest(const FString&)
{
    const FString Path=AtelierDataPath(TEXT("gondola/runtime.json"));const auto Data=AtelierReadJson(Path);
    if(!TestTrue(TEXT("Current ropeway data exists"),Data.IsValid()))return false;
    const auto& Segment=Data->GetArrayField(TEXT("clearance_segments_m"))[0]->AsArray();
    const double X=(Segment[0]->AsNumber()+Segment[2]->AsNumber())/2.,Y=(Segment[1]->AsNumber()+Segment[3]->AsNumber())/2.;
    auto Root=MakeShared<FJsonObject>();auto Instances=MakeShared<FJsonObject>();
    const TArray<FString> Keys={TEXT("HD_NorthTreeRust"),TEXT("HD_NorthTreeGold"),TEXT("HD_NorthTreePine"),
        TEXT("HD_NorthTreeBackdropRust"),TEXT("HD_ArcadeTree"),TEXT("HD_PlazaTreeGold"),TEXT("Tree_Pine_A"),TEXT("Bush_Green_A"),TEXT("Grass_A"),TEXT("HD_Streets")};
    for(const auto& Key:Keys)
    {
        TArray<TSharedPtr<FJsonValue>> Rows;
        for(double Offset:{0.,100000.})
        {
            TArray<TSharedPtr<FJsonValue>> Row;
            for(double Value:{X+Offset,Y,0.,0.,1.})Row.Add(MakeShared<FJsonValueNumber>(Value));
            Rows.Add(MakeShared<FJsonValueArray>(Row));
        }
        Instances->SetArrayField(Key,Rows);
    }
    Root->SetObjectField(TEXT("instances"),Instances);ABelmonteRegion::Clear(Root,Path);
    for(const auto& Key:Keys)
    {
        const auto& Rows=Instances->GetArrayField(Key);
        TestEqual(Key+TEXT(" clears only the inside vegetation"),Rows.Num(),Key==TEXT("HD_Streets")?2:1);
        if(Key!=TEXT("HD_Streets"))TestEqual(Key+TEXT(" retains outside point"),Rows[0]->AsArray()[0]->AsNumber(),X+100000.);
    }
    return true;
}
#endif
