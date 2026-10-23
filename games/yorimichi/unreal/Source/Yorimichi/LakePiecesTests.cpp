#include "LakePieces.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Dom/JsonValue.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FLakeMembershipTest,"Yorimichi.LakePieces.CompleteMembership",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FLakeMembershipTest::RunTest(const FString&)
{
    auto Manifest=MakeShared<FJsonObject>();auto Parents=MakeShared<FJsonObject>();auto Assets=MakeShared<FJsonObject>();
    Manifest->SetNumberField(TEXT("schema"),2);Manifest->SetBoolField(TEXT("complete"),true);
    Manifest->SetObjectField(TEXT("parents"),Parents);Manifest->SetObjectField(TEXT("assets"),Assets);
    for(const FString& Parent:JapanLakePieces::Parents())
    {
        const FString Name=Parent+TEXT("_cell_-1_0");
        Parents->SetArrayField(Parent,{MakeShared<FJsonValueString>(Name)});
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("parent"),Parent);
        Row->SetStringField(TEXT("fbx"),TEXT("assets/")+Name+TEXT(".fbx"));Row->SetStringField(TEXT("sha256"),FString::ChrN(64,TEXT('a')));
        Row->SetNumberField(TEXT("triangles"),12);Row->SetNumberField(TEXT("collision_boxes"),0);
        Row->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(-2.),MakeShared<FJsonValueNumber>(-1.),MakeShared<FJsonValueNumber>(0.)});
        Row->SetArrayField(TEXT("max"),{MakeShared<FJsonValueNumber>(2.),MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(3.)});
        Assets->SetObjectField(Name,Row);
    }
    TMap<FString,TArray<FString>> Result;TMap<FString,FBox> Bounds;
    TestTrue(TEXT("All five owners have separate native pieces"),JapanLakePieces::Read(Manifest,Result,&Bounds));
    TestEqual(TEXT("All five logical bounds"),Bounds.Num(),5);
    TestEqual(TEXT("Original metre axes retained"),Bounds[TEXT("Lake_Cabin")].Min,FVector(-200,-100,0));
    auto Cabin=Assets->GetObjectField(TEXT("Lake_Cabin_cell_-1_0"));Cabin->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Oversized child refuses"),JapanLakePieces::Read(Manifest,Result));
    TestEqual(TEXT("Failed read publishes no partial paths"),Result.Num(),0);
    Cabin->SetNumberField(TEXT("triangles"),12);Cabin->SetNumberField(TEXT("collision_boxes"),1);
    TestFalse(TEXT("New collision ownership refuses"),JapanLakePieces::Read(Manifest,Result));
    Cabin->SetNumberField(TEXT("collision_boxes"),0);Assets->SetObjectField(TEXT("Foreign"),Cabin);
    TestFalse(TEXT("Extra native mesh refuses"),JapanLakePieces::Read(Manifest,Result));
    Assets->RemoveField(TEXT("Foreign"));Parents->RemoveField(TEXT("Lake_Plants"));
    TestFalse(TEXT("Missing logical owner never falls back to a parent"),JapanLakePieces::Read(Manifest,Result));
    return true;
}
#endif
