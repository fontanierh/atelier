#include "FoliageSystem.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "JapanPreferences.h"
#include "WandererCharacter.h"
#include "AtelierSettings.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

TArray<FJapanPreference> JapanDefaultPreferences(TArray<FString>* Errors);

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageToggleTest,"Yorimichi.Foliage.Toggle",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageToggleTest::RunTest(const FString&)
{
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false);
    auto* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if (!TestNotNull(TEXT("Isolated foliage world"),World)) return false;
    auto* System=World->GetSubsystem<UYorimichiFoliageSubsystem>();
    if (!TestNotNull(TEXT("Runtime subsystem"),System)) { World->DestroyWorld(false);return false; }
    // This test isolates switching from registry I/O and asset generation.
    System->bRegistryLoaded=true;
    auto* Actor=World->SpawnActor<AActor>();
    auto* Source=UYorimichiFoliageSubsystem::NewInstances(Actor);
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    if (!TestNotNull(TEXT("Engine fixture mesh"),Mesh)) { World->DestroyWorld(false);return false; }
    Source->SetStaticMesh(Mesh);Actor->SetRootComponent(Source);Source->RegisterComponent();
    Source->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Source->SetCastShadow(true);
    Source->bAffectDistanceFieldLighting=true;
    const FTransform Placement(FRotator(0,31,0),FVector(300,400,50),FVector(1,2,3));
    Source->AddInstance(Placement);Source->AddInstance(FTransform(FVector(900,200,0)));
    const auto NewRender=[Actor,Source,Mesh]()
    {
        auto* Result=UYorimichiFoliageSubsystem::NewInstances(Actor);
        Result->SetStaticMesh(Mesh);Result->SetupAttachment(Source);
        Result->ComponentTags.Add(TEXT("FoliageSystemOwned"));Result->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Result->RegisterComponent();return Result;
    };
    FYorimichiFoliageSource Entry;
    Entry.Original=Source;Entry.SourceMesh=Mesh;Entry.InstanceCount=2;
    Entry.Visual=NewRender();Entry.NearVisual=NewRender();Entry.Patches=NewRender();Entry.Shadow=NewRender();
    Entry.Visible=true;Entry.CastShadow=true;Entry.DistanceField=true;Entry.Kind=TEXT("tree");
    System->Sources.Add(Entry);
    for (int32 Round=0;Round<3;++Round)
    {
        TestTrue(TEXT("Optimization turns on live"),System->SetEnabled(true));
        TestFalse(TEXT("Original renderer is hidden"),Source->IsVisible());
        TestFalse(TEXT("Original shadow work stops"),bool(Source->CastShadow));
        TestTrue(TEXT("Generated visual renders"),Entry.Visual->IsVisible());
        TestTrue(TEXT("Generated shadow renders"),bool(Entry.Shadow->CastShadow));
        TestEqual(TEXT("Dense interiors honor sway setting"),Entry.NearVisual->GetWorldPositionOffsetDisableDistance(),6000);
        TestTrue(TEXT("Optimization turns off live"),System->SetEnabled(false));
        TestTrue(TEXT("Original visibility restored"),Source->IsVisible());
        TestTrue(TEXT("Original shadows restored"),bool(Source->CastShadow));
        TestTrue(TEXT("Original distance fields restored"),bool(Source->bAffectDistanceFieldLighting));
        TestFalse(TEXT("Generated visual stops"),Entry.Visual->IsVisible());
        TestFalse(TEXT("Generated near visual stops"),Entry.NearVisual->IsVisible());
        TestFalse(TEXT("Generated patch stops"),Entry.Patches->IsVisible());
        TestFalse(TEXT("Generated shadow stops"),bool(Entry.Shadow->CastShadow));
        TestEqual(TEXT("Collision remains on its source"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
        TestTrue(TEXT("Original mesh retained"),Source->GetStaticMesh()==Mesh);
        TestEqual(TEXT("Placement count retained"),Source->GetInstanceCount(),2);
        FTransform Actual;Source->GetInstanceTransform(0,Actual,false);
        TestTrue(TEXT("Authored transform retained"),Actual.Equals(Placement));
    }
    System->SetDistances(true,.4f,0.f,0.f);System->SetEnabled(true);
    TestFalse(TEXT("Zero sway disables vertex motion"),bool(Entry.Visual->bEvaluateWorldPositionOffset));
    TestFalse(TEXT("Zero sway disables dense-cell motion"),bool(Entry.NearVisual->bEvaluateWorldPositionOffset));
    TestFalse(TEXT("Zero shadow distance cannot mean infinite shadows"),bool(Entry.Shadow->CastShadow));
    System->SetEnabled(false);
    TestTrue(TEXT("Disabling restores source after zero shadow setting"),bool(Source->CastShadow));
    // Exercise the actual persistent menu control, including a failed atomic
    // save after the renderer has switched: both its value and rendering roll back.
    auto* Preferences=NewObject<UJapanPreferences>();
    Preferences->Owner=World->SpawnActor<AWandererCharacter>();
    Preferences->Values=JapanDefaultPreferences(nullptr);
    const FString Directory=FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(),
        TEXT("../../../build/yorimichi/foliage-tests-settings/"))+FGuid::NewGuid().ToString();
    IFileManager::Get().MakeDirectory(*Directory,true);
    const FString File=Directory/TEXT("settings.txt");Preferences->SettingsFile=File;
    System->SetEnabled(true);
    TestTrue(TEXT("Settings switch saves off"),Preferences->SetValue(TEXT("foliage_optimization"),0.f));
    TestFalse(TEXT("Settings switch restores originals"),System->IsEnabled());
    TestEqual(TEXT("Off persists to disk"),AtelierSettings::ReadFile(File).FindRef(TEXT("foliage_optimization")),FString(TEXT("0.0")));
    TestTrue(TEXT("Settings switch saves on"),Preferences->SetValue(TEXT("foliage_optimization"),1.f));
    TestTrue(TEXT("Settings switch restores optimization"),System->IsEnabled());
    Preferences->SettingsFile=Directory; // An existing directory cannot become a settings file.
    AddExpectedError(TEXT("PREFERENCES could not save"),EAutomationExpectedErrorFlags::Contains,1);
    TestFalse(TEXT("Failed save refuses the setting"),Preferences->SetValue(TEXT("foliage_optimization"),0.f));
    TestTrue(TEXT("Failed save restores previous renderer"),System->IsEnabled());
    TestEqual(TEXT("Failed save restores menu value"),Preferences->Get(TEXT("foliage_optimization")),1.f);
    TestEqual(TEXT("Failed save preserves disk value"),AtelierSettings::ReadFile(File).FindRef(TEXT("foliage_optimization")),FString(TEXT("1.0")));
    IFileManager::Get().DeleteDirectory(*Directory,false,true);
    System->Sources.Reset();World->DestroyWorld(false);return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageRegistryTest,"Yorimichi.Foliage.Registry",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageRegistryTest::RunTest(const FString&)
{
    auto* System=NewObject<UYorimichiFoliageSubsystem>();
    const auto Read=[System](const FString& Text)
    {
        TSharedPtr<FJsonObject> Json;FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Json);
        return System->ReadRegistry(Json);
    };
    TestFalse(TEXT("Missing registry refuses safely"),System->ReadRegistry(nullptr));
    TestFalse(TEXT("Missing fields refuse safely"),Read(TEXT("{}")));
    const FString Valid=TEXT(R"({"version":1,"words":["tree"],"materials":[],"assets":[{
        "source":"/Game/Test/Tree.Tree","optimized":"/Game/FoliageSystem/Tree.Tree",
        "shadow":"/Game/FoliageSystem/Tree_Shadow.Tree_Shadow","patch":"/Game/FoliageSystem/Tree_Patch.Tree_Patch",
        "kind":"tree","aggregate":true,"source_triangles":900,"shadow_triangles":32,
        "triangles":[416,160,64,32],"canopy_bounds":[[0,0,0],[100,100,100]]}]})");
    TestTrue(TEXT("Complete registry accepted"),Read(Valid));
    TestFalse(TEXT("Truncated bounds refuse without indexing"),Read(Valid.Replace(TEXT("[[0,0,0],[100,100,100]]"),TEXT("[]"))));
    TestFalse(TEXT("Non-numeric bounds refuse"),Read(Valid.Replace(TEXT("[0,0,0]"),TEXT("[null,0,0]"))));
    TestFalse(TEXT("Unbounded variant refuses"),Read(Valid.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,-1]"))));
    TestFalse(TEXT("Unowned generated path refuses"),Read(Valid.Replace(TEXT("/Game/FoliageSystem/Tree.Tree"),TEXT("/Game/Other/Tree.Tree"))));
    TestTrue(TEXT("Correction recovers after invalid registry"),Read(Valid));
    return true;
}
#endif
