#include "JapanAtlasNames.h"
#include "JapanAtlasLabels.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/ScopeExit.h"
#include "HAL/FileManager.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanAtlasNamesTest,"Yorimichi.Map.StableNames",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FJapanAtlasNamesTest::RunTest(const FString&)
{
    const FString Dir=FPaths::ProjectSavedDir()/TEXT("Automation/Atlas")/FGuid::NewGuid().ToString(EGuidFormats::Digits);
    const FString File=Dir/TEXT("names.json");
    ON_SCOPE_EXIT { IFileManager::Get().DeleteDirectory(*Dir,false,true); };
    FJapanAtlasNames Store;Store.Load(File);
    TestEqual(TEXT("An untouched stable uses its English default"),Store.Get(TEXT("alder_stables"),TEXT("Alder Stables")),FString(TEXT("Alder Stables")));
    TestTrue(TEXT("A stable can be renamed"),Store.Rename(TEXT("alder_stables"),TEXT("Willow Run")));
    TestTrue(TEXT("A second stable keeps its independent name"),Store.Rename(TEXT("home_stables"),TEXT("Riverside")));
    TestFalse(TEXT("Blank names cannot erase a label"),Store.Rename(TEXT("alder_stables"),TEXT("   ")));
    TestFalse(TEXT("Control characters cannot enter the atlas"),Store.Rename(TEXT("alder_stables"),TEXT("Bad\nName")));
    TestFalse(TEXT("Stable identities cannot become paths"),Store.Rename(TEXT("../names"),TEXT("Oops")));
    FJapanAtlasNames Reloaded;Reloaded.Load(File);
    TestEqual(TEXT("Stable names persist on a fresh load"),Reloaded.Get(TEXT("alder_stables"),TEXT("Alder Stables")),FString(TEXT("Willow Run")));
    TestEqual(TEXT("Renaming another stable does not replace the first"),Reloaded.Get(TEXT("home_stables"),TEXT("Home Stables")),FString(TEXT("Riverside")));
    TestTrue(TEXT("Reset removes just the selected override"),Reloaded.Reset(TEXT("alder_stables")));
    FJapanAtlasNames Reset;Reset.Load(File);
    TestEqual(TEXT("Reset restores the English default"),Reset.Get(TEXT("alder_stables"),TEXT("Alder Stables")),FString(TEXT("Alder Stables")));
    TestEqual(TEXT("Reset preserves other names"),Reset.Get(TEXT("home_stables"),TEXT("Home Stables")),FString(TEXT("Riverside")));
    const FString Corrupt=Dir/TEXT("corrupt.json");FFileHelper::SaveStringToFile(TEXT("{broken"),*Corrupt);
    FJapanAtlasNames Protected;Protected.Load(Corrupt);
    TestFalse(TEXT("An unreadable prior save cannot be overwritten"),Protected.Rename(TEXT("home_stables"),TEXT("Replacement")));
    FString Original;FFileHelper::LoadFileToString(Original,*Corrupt);
    TestEqual(TEXT("The unreadable save remains byte-for-byte intact"),Original,FString(TEXT("{broken")));
    const FString Blocker=Dir/TEXT("not-a-directory");FFileHelper::SaveStringToFile(TEXT("keep"),*Blocker);
    FJapanAtlasNames Unwritable;Unwritable.Load(Blocker/TEXT("names.json"));
    TestFalse(TEXT("A failed save reports failure"),Unwritable.Rename(TEXT("home_stables"),TEXT("Unavailable")));
    TestEqual(TEXT("A failed save does not publish an in-memory rename"),Unwritable.Get(TEXT("home_stables"),TEXT("Home Stables")),FString(TEXT("Home Stables")));
    return true;
}
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanAtlasLabelLayoutTest,"Yorimichi.Map.LabelLayout",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)
bool FJapanAtlasLabelLayoutTest::RunTest(const FString&)
{
    TArray<FAtlasLabelRequest> Requests;
    auto AddLabel=[&Requests](float X,float Y,int32 Priority)
    {
        FAtlasLabelRequest R; R.Anchor=FVector2D(X,Y); R.Size=FVector2D(90,26); R.Priority=Priority; Requests.Add(R);
    };
    AddLabel(100,100,10); AddLabel(110,104,9); AddLabel(105,108,8); AddLabel(300,210,7);
    const auto Placements=AtlasLabelLayout::LayOut(Requests,{},FVector2D(420,300));
    TArray<FAtlasLabelBox> Boxes;
    for (int32 I=0;I<Requests.Num();++I) if (Placements[I].bVisible)
        Boxes.Add(AtlasLabelLayout::BoxAt(Placements[I].Position,Requests[I].Size));
    TestTrue(TEXT("Clustered labels should use the available space"),Boxes.Num()>=3);
    for (int32 I=0;I<Boxes.Num();++I) for (int32 J=I+1;J<Boxes.Num();++J)
        TestFalse(TEXT("Visible labels must not overlap each other"),Boxes[I].Intersects(Boxes[J]));

    TArray<FAtlasLabelBox> Full;
    Full.Add(AtlasLabelLayout::BoxAt(FVector2D(0,0),FVector2D(420,300)));
    Requests[0].bForce=true;
    const auto Forced=AtlasLabelLayout::LayOut(Requests,Full,FVector2D(420,300));
    TestTrue(TEXT("The hovered label stays visible when every position collides"),Forced[0].bVisible);
    TestFalse(TEXT("A non-forced label may be hidden when every position collides"),Forced[1].bVisible);

    TArray<FAtlasLabelRequest> Centred;
    FAtlasLabelRequest Region; Region.Anchor=FVector2D(200,150); Region.Size=FVector2D(100,30); Region.bCentered=true;
    Centred.Add(Region);
    const auto CentredPlacement=AtlasLabelLayout::LayOut(Centred,{},FVector2D(420,300));
    TestTrue(TEXT("A region caption is visible with room around it"),CentredPlacement[0].bVisible);
    TestTrue(TEXT("A region caption stays centred on its anchor"),
        (CentredPlacement[0].Position+FVector2D(50,15)-FVector2D(200,150)).Size()<.1f);

    TArray<FAtlasLabelRequest> Edge;
    FAtlasLabelRequest Corner; Corner.Anchor=FVector2D(0,0); Corner.Size=FVector2D(90,26); Corner.Priority=1;
    Edge.Add(Corner);
    const auto EdgePlacement=AtlasLabelLayout::LayOut(Edge,{},FVector2D(420,300));
    TestTrue(TEXT("A corner label stays inside the sheet"),EdgePlacement[0].bVisible);
    TestTrue(TEXT("A corner label is inset from the sheet edge"),EdgePlacement[0].Position.X>=8.f-0.1f&&EdgePlacement[0].Position.Y>=8.f-0.1f);
    return true;
}
#endif
