#include "TreehousePieces.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTreehousePieceMembershipTest,"Yorimichi.TreehousePieces.CompleteMembership",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FTreehousePieceMembershipTest::RunTest(const FString&)
{
    auto Root=MakeShared<FJsonObject>();Root->SetNumberField(TEXT("version"),1);
    Root->SetBoolField(TEXT("complete"),true);Root->SetStringField(TEXT("parent"),TEXT("TH_Dressing"));
    Root->SetNumberField(TEXT("triangle_limit"),32768);Root->SetNumberField(TEXT("cell_metres"),64);
    Root->SetNumberField(TEXT("source_triangles"),2);Root->SetNumberField(TEXT("collision_boxes"),0);
    TArray<TSharedPtr<FJsonValue>> UVs;
    for(const TCHAR* Name:{TEXT("UVMap"),TEXT("Piece1"),TEXT("Piece2"),TEXT("Piece3"),TEXT("Piece4")})
        UVs.Add(MakeShared<FJsonValueString>(Name));
    Root->SetArrayField(TEXT("uv_channels"),UVs);
    TArray<TSharedPtr<FJsonValue>> Pieces;
    for(int32 I=0;I<2;++I)
    {
        auto Row=MakeShared<FJsonObject>();Row->SetNumberField(TEXT("triangles"),1);
        Row->SetStringField(TEXT("name"),FString::Printf(TEXT("TH_Dressing_cell_-1_%d"),I));
        Pieces.Add(MakeShared<FJsonValueObject>(Row));
    }
    Root->SetArrayField(TEXT("pieces"),Pieces);
    TArray<FString> Paths;
    TestTrue(TEXT("Complete original-frame membership loads"),JapanTreehousePieces::Read(Root,Paths));
    TestEqual(TEXT("Every bounded child path"),Paths.Num(),2);
    Root->SetNumberField(TEXT("source_triangles"),3);
    TestFalse(TEXT("Missing face refuses"),JapanTreehousePieces::Read(Root,Paths));
    TestTrue(TEXT("No partial fallback"),Paths.IsEmpty());
    Root->SetNumberField(TEXT("source_triangles"),2);
    UVs[4]=MakeShared<FJsonValueString>(TEXT("RecomputedFade"));Root->SetArrayField(TEXT("uv_channels"),UVs);
    TestFalse(TEXT("Changed capsule channel refuses"),JapanTreehousePieces::Read(Root,Paths));
    UVs[4]=MakeShared<FJsonValueString>(TEXT("Piece4"));Root->SetArrayField(TEXT("uv_channels"),UVs);
    Pieces[1]->AsObject()->SetStringField(TEXT("name"),TEXT("TH_Dressing"));
    TestFalse(TEXT("Whole parent cannot enter bounded roster"),JapanTreehousePieces::Read(Root,Paths));
    return true;
}
#endif
