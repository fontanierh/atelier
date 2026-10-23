#include "TreehousePieces.h"
#include "TreehouseSurfacePieces.h"
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
IMPLEMENT_SIMPLE_AUTOMATION_TEST(FTreehouseSurfaceMembershipTest,"Yorimichi.TreehousePieces.SurfaceMembership",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FTreehouseSurfaceMembershipTest::RunTest(const FString&)
{
    auto Manifest=MakeShared<FJsonObject>();auto Parents=MakeShared<FJsonObject>();auto Assets=MakeShared<FJsonObject>();
    Manifest->SetNumberField(TEXT("schema"),1);Manifest->SetBoolField(TEXT("complete"),true);
    Manifest->SetObjectField(TEXT("parents"),Parents);Manifest->SetObjectField(TEXT("assets"),Assets);
    for(const FString& Parent:JapanTreehouseSurfacePieces::Parents())
    {
        const bool Bounded=Parent==TEXT("TH_Structure") || Parent==TEXT("TH_Dressing");
        const FString Name=Bounded?Parent+TEXT("_cell_-1_0"):Parent;
        const FString Folder=Parent==TEXT("TH_Structure")?TEXT("structure"):Parent==TEXT("TH_Dressing")?TEXT("dressing"):
            Parent==TEXT("TH_Frame")?TEXT("frame"):TEXT("trunks");
        Parents->SetArrayField(Parent,{MakeShared<FJsonValueString>(Name)});
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("parent"),Parent);
        Row->SetStringField(TEXT("fbx"),TEXT("assets/")+Folder+TEXT("/")+Name+TEXT(".fbx"));
        Row->SetStringField(TEXT("sha256"),FString::ChrN(64,TEXT('a')));Row->SetNumberField(TEXT("triangles"),12);
        Row->SetNumberField(TEXT("collision_hulls"),0);
        TArray<TSharedPtr<FJsonValue>> UVs={MakeShared<FJsonValueString>(TEXT("UVMap"))};
        if(Parent==TEXT("TH_Frame") || Parent==TEXT("TH_Dressing"))
            for(int32 I=1;I<5;++I)UVs.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("Piece%d"),I)));
        Row->SetArrayField(TEXT("uv_channels"),UVs);
        Row->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(-2.),MakeShared<FJsonValueNumber>(-1.),MakeShared<FJsonValueNumber>(0.)});
        Row->SetArrayField(TEXT("max"),{MakeShared<FJsonValueNumber>(2.),MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(3.)});
        Assets->SetObjectField(Name,Row);
    }
    TMap<FString,TArray<FString>> Paths;TMap<FString,FBox> Bounds;
    TestTrue(TEXT("Complete original four logical surfaces"),JapanTreehouseSurfacePieces::Read(Manifest,Paths,&Bounds));
    TestEqual(TEXT("Separate structure asset path"),Paths[TEXT("TH_Structure")][0],
        FString(TEXT("/Game/Japan/Treehouse/StructurePieces/TH_Structure_cell_-1_0.TH_Structure_cell_-1_0")));
    auto Structure=Assets->GetObjectField(TEXT("TH_Structure_cell_-1_0"));Structure->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Whole oversized structure cannot return"),JapanTreehouseSurfacePieces::Read(Manifest,Paths));
    TestTrue(TEXT("Failure publishes no partial native roster"),Paths.IsEmpty());
    Structure->SetNumberField(TEXT("triangles"),12);auto Frame=Assets->GetObjectField(TEXT("TH_Frame"));
    Frame->SetArrayField(TEXT("uv_channels"),{MakeShared<FJsonValueString>(TEXT("UVMap"))});
    TestFalse(TEXT("Original five-channel fade bake is mandatory"),JapanTreehouseSurfacePieces::Read(Manifest,Paths));
    return true;
}
#endif
