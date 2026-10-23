#include "VillagePieces.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Dom/JsonValue.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FVillageMembershipTest,"Yorimichi.VillagePieces.CompleteMembership",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FVillageMembershipTest::RunTest(const FString&)
{
    auto Manifest=MakeShared<FJsonObject>();auto Parents=MakeShared<FJsonObject>();
    Manifest->SetNumberField(TEXT("schema"),1);Manifest->SetBoolField(TEXT("complete"),true);
    Manifest->SetObjectField(TEXT("parents"),Parents);
    for(const FString& Parent:JapanVillagePieces::Parents())
    {
        auto Source=MakeShared<FJsonObject>();auto Piece=MakeShared<FJsonObject>();
        Source->SetNumberField(TEXT("source_triangles"),12);Source->SetNumberField(TEXT("source_collision_hulls"),0);
        Source->SetStringField(TEXT("collision"),Parent==TEXT("Village_Ground")?TEXT("complex_as_simple"):TEXT("simple_and_complex"));
        Source->SetArrayField(TEXT("slots"),{MakeShared<FJsonValueString>(TEXT("VillagePalette"))});
        Piece->SetStringField(TEXT("name"),Parent+TEXT("_cell_-1_0"));Piece->SetNumberField(TEXT("triangles"),12);
        Piece->SetNumberField(TEXT("collision_hulls"),0);Piece->SetStringField(TEXT("sha256"),FString::ChrN(64,TEXT('a')));
        Piece->SetArrayField(TEXT("uv_channels"),{MakeShared<FJsonValueString>(TEXT("UVMap"))});
        Piece->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(-2.),MakeShared<FJsonValueNumber>(-1.),MakeShared<FJsonValueNumber>(0.)});
        Piece->SetArrayField(TEXT("max"),{MakeShared<FJsonValueNumber>(2.),MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(3.)});
        Source->SetArrayField(TEXT("pieces"),{MakeShared<FJsonValueObject>(Piece)});Parents->SetObjectField(Parent,Source);
    }
    TMap<FString,TArray<FString>> Result;TMap<FString,FBox> Bounds;
    TestTrue(TEXT("All twelve original owners have native children"),JapanVillagePieces::Read(Manifest,Result,&Bounds));
    TestEqual(TEXT("Complete original logical bounds"),Bounds.Num(),12);
    TestEqual(TEXT("Original metre axes retained"),Bounds[TEXT("Village_Sign")].Min,FVector(-200,-100,0));
    auto Sign=Parents->GetObjectField(TEXT("Village_Sign"));
    auto Piece=Sign->GetArrayField(TEXT("pieces"))[0]->AsObject();
    Piece->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Oversized children refuse"),JapanVillagePieces::Read(Manifest,Result));
    TestEqual(TEXT("Refusal never publishes partial membership"),Result.Num(),0);
    Piece->SetNumberField(TEXT("triangles"),12);Piece->SetNumberField(TEXT("collision_hulls"),1);
    TestFalse(TEXT("Invented collision owner refuses"),JapanVillagePieces::Read(Manifest,Result));
    Piece->SetNumberField(TEXT("collision_hulls"),0);Sign->SetNumberField(TEXT("source_triangles"),13);
    TestFalse(TEXT("Missing original triangles refuse"),JapanVillagePieces::Read(Manifest,Result));
    Sign->SetNumberField(TEXT("source_triangles"),12);Parents->RemoveField(TEXT("Village_Ground"));
    TestFalse(TEXT("Missing original owner never falls back"),JapanVillagePieces::Read(Manifest,Result));
    return true;
}
#endif
