#include "IslandPieces.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIslandPiecesMembershipTest,"Yorimichi.IslandPieces.CompleteMembership",
    EAutomationTestFlags_ApplicationContextMask|EAutomationTestFlags::EngineFilter)
bool FIslandPiecesMembershipTest::RunTest(const FString&)
{
    auto Manifest=MakeShared<FJsonObject>();Manifest->SetNumberField(TEXT("schema"),1);
    Manifest->SetBoolField(TEXT("complete"),true);
    Manifest->SetArrayField(TEXT("origin"),{MakeShared<FJsonValueNumber>(0.),MakeShared<FJsonValueNumber>(0.),MakeShared<FJsonValueNumber>(0.)});
    auto Parents=MakeShared<FJsonObject>();Manifest->SetObjectField(TEXT("parents"),Parents);
    const TArray<FString> Names={TEXT("Terrain"),TEXT("Road"),TEXT("Lane"),TEXT("Guardrail"),TEXT("Wires"),TEXT("FarHills"),TEXT("Sea")};
    TSharedPtr<FJsonObject> Terrain,Sea;
    for(const FString& Name:Names)
    {
        auto Group=MakeShared<FJsonObject>();Parents->SetObjectField(Name,Group);
        Group->SetBoolField(TEXT("collision"),Name!=TEXT("Sea"));Group->SetBoolField(TEXT("cast_shadow"),Name!=TEXT("Sea"));
        auto Row=MakeShared<FJsonObject>();Row->SetStringField(TEXT("name"),Name);
        Row->SetStringField(TEXT("asset"),TEXT("/Game/Experiments/IslandTerrain/v1_atomic/")+Name);
        Row->SetStringField(TEXT("sha256"),FString::ChrN(64,TEXT('a')));Row->SetNumberField(TEXT("triangles"),1);
        Row->SetArrayField(TEXT("min"),{MakeShared<FJsonValueNumber>(0.),MakeShared<FJsonValueNumber>(0.),MakeShared<FJsonValueNumber>(0.)});
        Row->SetArrayField(TEXT("max"),{MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(1.),MakeShared<FJsonValueNumber>(1.)});
        Group->SetArrayField(TEXT("meshes"),{MakeShared<FJsonValueObject>(Row)});
        if(Name==TEXT("Terrain"))Terrain=Row;
        if(Name==TEXT("Sea"))Sea=Group;
    }
    TMap<FString,TArray<FString>> Result;
    TestTrue(TEXT("Complete separate island membership"),JapanIslandPieces::Read(Manifest,Result));
    TestEqual(TEXT("Every production logical parent"),Result.Num(),7);
    TestEqual(TEXT("Sea uses separate current asset"),Result.FindChecked(TEXT("Sea"))[0],
        FString(TEXT("/Game/Experiments/IslandTerrain/v1_atomic/Sea.Sea")));
    Parents->RemoveField(TEXT("Road"));
    TestFalse(TEXT("Missing original component refuses"),JapanIslandPieces::Read(Manifest,Result));
    TestTrue(TEXT("No partial membership after refusal"),Result.IsEmpty());
    // Rebuild the missing owner from its retained exact object, not a fallback.
    auto Road=MakeShared<FJsonObject>();Road->SetBoolField(TEXT("collision"),true);Road->SetBoolField(TEXT("cast_shadow"),true);
    auto RoadRow=MakeShared<FJsonObject>(*Terrain);RoadRow->SetStringField(TEXT("name"),TEXT("Road"));
    RoadRow->SetStringField(TEXT("asset"),TEXT("/Game/Experiments/IslandTerrain/v1_atomic/Road"));
    Road->SetArrayField(TEXT("meshes"),{MakeShared<FJsonValueObject>(RoadRow)});Parents->SetObjectField(TEXT("Road"),Road);
    TestTrue(TEXT("Exact repaired roster"),JapanIslandPieces::Read(Manifest,Result));
    Terrain->SetNumberField(TEXT("triangles"),32769);
    TestFalse(TEXT("Oversized atomic primary refuses"),JapanIslandPieces::Read(Manifest,Result));
    Terrain->SetNumberField(TEXT("triangles"),1.5);
    TestFalse(TEXT("Fractional count refuses"),JapanIslandPieces::Read(Manifest,Result));
    Terrain->SetNumberField(TEXT("triangles"),1);
    Terrain->SetStringField(TEXT("asset"),TEXT("/Game/Japan/Terrain"));
    TestFalse(TEXT("Combined parent cannot substitute"),JapanIslandPieces::Read(Manifest,Result));
    Terrain->SetStringField(TEXT("asset"),TEXT("/Game/Experiments/IslandTerrain/v1_atomic/Terrain"));
    Sea->SetBoolField(TEXT("collision"),true);
    TestFalse(TEXT("Sea must remain nonblocking"),JapanIslandPieces::Read(Manifest,Result));
    Sea->SetBoolField(TEXT("collision"),false);Sea->SetBoolField(TEXT("cast_shadow"),true);
    TestFalse(TEXT("Sea must remain shadow-free"),JapanIslandPieces::Read(Manifest,Result));
    Sea->SetBoolField(TEXT("cast_shadow"),false);
    TestTrue(TEXT("All current semantics restored"),JapanIslandPieces::Read(Manifest,Result));
    return true;
}
#endif
