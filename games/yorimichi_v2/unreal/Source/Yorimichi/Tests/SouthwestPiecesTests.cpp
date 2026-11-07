#include "SouthwestPieces.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Dom/JsonValue.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FSouthwestMembershipTest,"Yorimichi.SouthwestPieces.CompleteMembership",
    EAutomationTestFlags::EditorContext|EAutomationTestFlags::EngineFilter)
bool FSouthwestMembershipTest::RunTest(const FString&)
{
    auto Manifest=MakeShared<FJsonObject>();auto Parents=MakeShared<FJsonObject>();
    Manifest->SetNumberField(TEXT("version"),1);Manifest->SetNumberField(TEXT("triangle_limit"),32768);
    Manifest->SetBoolField(TEXT("complete"),true);Manifest->SetObjectField(TEXT("parents"),Parents);
    for(const FString& Parent:JapanSouthwestPieces::Parents())
    {
        auto Source=MakeShared<FJsonObject>();Source->SetNumberField(TEXT("source_triangles"),12);
        TArray<TSharedPtr<FJsonValue>> Low={MakeShared<FJsonValueNumber>(-1.),MakeShared<FJsonValueNumber>(-2.),MakeShared<FJsonValueNumber>(0.)};
        TArray<TSharedPtr<FJsonValue>> High={MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(2.),MakeShared<FJsonValueNumber>(3.)};
        Source->SetArrayField(TEXT("bounds"),{MakeShared<FJsonValueArray>(Low),MakeShared<FJsonValueArray>(High)});
        auto Piece=MakeShared<FJsonObject>();Piece->SetStringField(TEXT("name"),Parent);Piece->SetNumberField(TEXT("triangles"),12);
        Source->SetArrayField(TEXT("pieces"),{MakeShared<FJsonValueObject>(Piece)});Parents->SetObjectField(Parent,Source);
    }
    TMap<FString,TArray<FString>> Result;TMap<FString,FBox> Bounds;
    TestTrue(TEXT("Complete sixteen logical owners"),JapanSouthwestPieces::Read(Manifest,Result,&Bounds));
    TestEqual(TEXT("Both lean pines retain logical membership"),Result.Num(),16);
    TestEqual(TEXT("Whole logical bounds retain metre axis conversion"),Bounds[TEXT("SW_Island")].Max,FVector(100,200,300));
    auto Island=Parents->GetObjectField(TEXT("SW_Island"));auto Piece=Island->GetArrayField(TEXT("pieces"))[0]->AsObject();
    Piece->SetStringField(TEXT("name"),TEXT("SW_Island_cell_0_0"));
    TestTrue(TEXT("Bounded island child"),JapanSouthwestPieces::Read(Manifest,Result));
    Piece->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Unbounded child refuses"),JapanSouthwestPieces::Read(Manifest,Result));
    TestEqual(TEXT("Failed read publishes no partial members"),Result.Num(),0);
    Piece->SetNumberField(TEXT("triangles"),12);Piece->SetStringField(TEXT("name"),TEXT("SW_Island_Foreign"));
    TestFalse(TEXT("Unknown member refuses"),JapanSouthwestPieces::Read(Manifest,Result));
    Piece->SetStringField(TEXT("name"),TEXT("SW_Island"));Parents->RemoveField(TEXT("Tree_PineLean_B"));
    TestFalse(TEXT("Missing lean pine never falls back to its parent"),JapanSouthwestPieces::Read(Manifest,Result));
    return true;
}
#endif
