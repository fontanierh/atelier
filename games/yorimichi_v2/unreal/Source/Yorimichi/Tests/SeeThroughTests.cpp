#include "SeeThrough.h"
#if WITH_DEV_AUTOMATION_TESTS && WITH_EDITOR
#include "Misc/AutomationTest.h"
#include "Components/StaticMeshComponent.h"
#include "UObject/StrongObjectPtr.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FLogicalFadeBoundsTest,"Yorimichi.CityPieces.LogicalFadeBounds",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FLogicalFadeBoundsTest::RunTest(const FString&)
{
    TStrongObjectPtr<UStaticMeshComponent> Component(NewObject<UStaticMeshComponent>());
    TestTrue(TEXT("Unpartitioned components have no override"),Component->GetCustomPrimitiveData().Data.IsEmpty());
    Component->SetCustomPrimitiveDataFloat(0,JapanSeeThrough::FadeInstances);
    const FBox Bounds(FVector(-200,-500,0),FVector(300,400,1000));
    TestTrue(TEXT("Original logical bounds accepted"),JapanSeeThrough::SetLogicalBounds(Component.Get(),Bounds));
    const TArray<float> Saved=Component->GetCustomPrimitiveData().Data;
    TestEqual(TEXT("Fade mode remains intact"),Saved[0],float(JapanSeeThrough::FadeInstances));
    const float Expected[]={50,-50,500,250,450,500,1};
    for(int32 Index=0;Index<7;++Index)
        TestEqual(FString::Printf(TEXT("Logical bound channel %d"),Index+1),Saved[Index+1],Expected[Index]);
    TestFalse(TEXT("Missing component refuses"),JapanSeeThrough::SetLogicalBounds(nullptr,Bounds));
    TestFalse(TEXT("Invalid bound refuses"),JapanSeeThrough::SetLogicalBounds(Component.Get(),FBox(ForceInit)));
    TestFalse(TEXT("Reversed bound refuses"),JapanSeeThrough::SetLogicalBounds(Component.Get(),
        FBox(FVector(3,0,0),FVector(2,1,1))));
    TestFalse(TEXT("Float channel overflow refuses"),JapanSeeThrough::SetLogicalBounds(Component.Get(),
        FBox(FVector(0,0,0),FVector(1.e100,1,1))));
    TestTrue(TEXT("Rejected bounds leave existing fade data intact"),Component->GetCustomPrimitiveData().Data==Saved);
    return true;
}
#endif
