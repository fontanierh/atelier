#include "FoliageSystem.h"
#include "FoliagePatchCoverage.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "JapanPreferences.h"
#include "WandererCharacter.h"
#include "AtelierSettings.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/Material.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
TArray<FVector> CorePoints(const FBox& Bounds)
{
    TArray<FVector> Directions={FVector(1,0,0),FVector(-1,0,0),FVector(0,1,0),
        FVector(0,-1,0),FVector(0,0,1),FVector(0,0,-1)};
    const int32 Axes=Directions.Num();
    for (int32 I=0;I<Axes;++I) for (int32 J=I+1;J<Axes;++J)
        if (FVector::DotProduct(Directions[I],Directions[J])==0.) Directions.Add((Directions[I]+Directions[J]).GetSafeNormal());
    for (auto& P:Directions) P=Bounds.GetCenter()+P*Bounds.GetExtent();
    return Directions;
}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageCoverageTest,"Yorimichi.Foliage.PatchCoverage",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageCoverageTest::RunTest(const FString&)
{
    const FBox Patch(FVector(-1600,-1600,0),FVector(1600,1600,1000));
    const FBox Full(FVector(-2400,-2400,0),FVector(2400,2400,1000));
    TestTrue(TEXT("Fully covered interior accepted"),FoliagePatchCoverage::Covered(Patch,{CorePoints(Full)}));
    TArray<FoliagePatchCoverage::FCrown> Ring,Diagonal;
    for (int32 X=0;X<8;++X) for (int32 Y=0;Y<8;++Y)
    {
        const FVector C(-1400+X*400,-1400+Y*400,500),R(285,285,500);
        // Every old sample center is covered, but a narrow diagonal path between
        // centers remains open. Whole tiles must refuse it.
        const FVector PathRadius((X-Y==0 || X-Y==1)?140.:285.,(X-Y==0 || X-Y==1)?140.:285.,500.);
        Diagonal.Emplace(CorePoints(FBox(C-PathRadius,C+PathRadius)));
        if (X<3 || X>4 || Y<3 || Y>4) Ring.Emplace(CorePoints(FBox(C-R,C+R)));
    }
    TestFalse(TEXT("Central clearing cannot become a patch"),FoliagePatchCoverage::Covered(Patch,Ring));
    TestFalse(TEXT("Paths between point samples cannot become a patch"),FoliagePatchCoverage::Covered(Patch,Diagonal));
    TestFalse(TEXT("Boundary crown retains individual skyline"),FoliagePatchCoverage::Contains(Patch,
        FBox(FVector(1200,-200,0),FVector(1800,200,1000))));
    TestTrue(TEXT("Interior crown may use the certified patch"),FoliagePatchCoverage::Contains(Patch,
        FBox(FVector(-200,-200,0),FVector(200,200,1000))));
    TestFalse(TEXT("Twelve total trees with only one interior tree cannot increase distant cost"),
        FoliagePatchCoverage::Worthwhile(1,8));
    TestFalse(TEXT("Already cheap individual impostors need enough savings"),FoliagePatchCoverage::Worthwhile(8,8));
    TestTrue(TEXT("Useful 4x distant saving qualifies"),FoliagePatchCoverage::Worthwhile(16,8));
    const FoliagePatchCoverage::FCrown RotatedCircle(CorePoints(FBox(FVector(-100,-100,-100),FVector(100,100,100))),
        FTransform(FRotator(0,45,0)));
    TestTrue(TEXT("Circular crown stays circular after yaw"),RotatedCircle.Inside(FVector2D(90,0)));
    TestFalse(TEXT("Yaw cannot inflate a circular crown into a clearing"),RotatedCircle.Inside(FVector2D(120,0)));
    const FoliagePatchCoverage::FCrown RotatedOval(CorePoints(FBox(FVector(-200,-50,-100),FVector(200,50,100))),
        FTransform(FRotator(0,45,0)));
    TestTrue(TEXT("Rotated major axis retains its footprint"),RotatedOval.Inside(FVector2D(100,100)));
    TestFalse(TEXT("Rotated minor axis cannot fill a path"),RotatedOval.Inside(FVector2D(90,-90)));
    const auto Unit=CorePoints(FBox(FVector(-1,-1,-1),FVector(1,1,1)));
    const FoliagePatchCoverage::FCrown Faceted(Unit);
    TestFalse(TEXT("A smooth ellipse cannot certify the space outside a faceted core"),
        Faceted.Inside(FVector2D(.896163,.371203)));
    const FTransform Instance(FRotator(12,31,7),FVector(20,30,40),FVector(3,1,2));
    const FTransform Component(FRotator(0,41,0),FVector(100,200,300),FVector(2));
    const FTransform Pose=Instance*Component;
    const FoliagePatchCoverage::FCrown Transformed(Unit,Pose);
    const FVector Mid=Component.TransformPosition(Instance.TransformPosition(FVector::ZeroVector));
    TestTrue(TEXT("Rotated component and nonuniform instance retain the occupied center"),Transformed.Inside(FVector2D(Mid)));
    const FVector Outside=Pose.TransformPosition(FVector(10,10,0));
    TestFalse(TEXT("Rotated component cannot certify exterior space"),Transformed.Inside(FVector2D(Outside)));
    TestFalse(TEXT("Degenerate crowns cannot certify coverage"),FoliagePatchCoverage::FCrown(Unit,
        FTransform(FQuat::Identity,FVector::ZeroVector,FVector::ZeroVector)).Inside(FVector2D::ZeroVector));
    return true;
}

TArray<FJapanPreference> JapanDefaultPreferences(TArray<FString>* Errors);

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageClassificationTest,"Yorimichi.Foliage.Classification",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageClassificationTest::RunTest(const FString&)
{
    auto* System=NewObject<UYorimichiFoliageSubsystem>();
    System->Words={TEXT("tree"),TEXT("bush"),TEXT("grass"),TEXT("leaf"),TEXT("leaves"),TEXT("plant"),TEXT("fern"),TEXT("cover_leaf")};
    auto* Source=NewObject<UStaticMeshComponent>();
    // Real export names and adversarial words exercise the runtime matcher,
    // including the HD_Streets false positive that would corrupt preparation.
    for (const TCHAR* Name:{TEXT("HD_Streets"),TEXT("SM_CityStreet"),TEXT("SM_Backstreet"),
                           TEXT("Treehouse_Floor"),TEXT("SM_BarrelPlanter"),TEXT("SM_PineappleCrate")})
    {
        Source->SetStaticMesh(NewObject<UStaticMesh>(GetTransientPackage(),FName(Name)));
        TestFalse(Name,System->RequiresRegistration(Source));
    }
    for (const TCHAR* Name:{TEXT("StreetTree02"),TEXT("SM_Trees"),TEXT("SM_Bushes"),TEXT("HD_Grasses"),
                           TEXT("UnderstoryFern"),TEXT("SM_BC_Plant_CoverLeaf1"),TEXT("Treehouse_Leaves")})
    {
        Source->SetStaticMesh(NewObject<UStaticMesh>(GetTransientPackage(),FName(Name)));
        TestTrue(Name,System->RequiresRegistration(Source));
    }
    auto* Rigid=NewObject<UStaticMesh>();Rigid->GetStaticMaterials().Add(FStaticMaterial(nullptr,FName(TEXT("Ground"))));
    Source->SetStaticMesh(Rigid);
    TestFalse(TEXT("Rigid verdict cached"),System->CachedRequiresRegistration(Source));
    TestEqual(TEXT("Only this component is cached"),System->ClassificationCache.Num(),1);
    TestFalse(TEXT("Unchanged non-foliage stays cached"),System->CachedRequiresRegistration(Source));
    auto* Leaf=NewObject<UMaterial>(GetTransientPackage(),TEXT("M_LeafMid"));
    Source->SetMaterial(0,Leaf);
    TestTrue(TEXT("Changed material invalidates a negative verdict"),System->CachedRequiresRegistration(Source));
    Source->SetMaterial(0,nullptr);
    TestFalse(TEXT("Removing the leaf material reclassifies"),System->CachedRequiresRegistration(Source));
    Rigid->GetStaticMaterials()[0].MaterialSlotName=TEXT("FoliageRoles_Ground");
    TestTrue(TEXT("New role certification invalidates a negative verdict"),System->CachedRequiresRegistration(Source));
    Rigid->GetStaticMaterials()[0].MaterialSlotName=TEXT("FoliageRigid_Ground");
    TestFalse(TEXT("Explicit rigid certification replaces the verdict"),System->CachedRequiresRegistration(Source));
    Source->SetStaticMesh(NewObject<UStaticMesh>(GetTransientPackage(),TEXT("Tree_CacheReplacement")));
    TestTrue(TEXT("A mesh swap invalidates a negative verdict"),System->CachedRequiresRegistration(Source));
    Source->ComponentTags.Add(TEXT("DetachedFoliageParticle"));
    TestFalse(TEXT("Owned particles never enter the scenery owner"),System->CachedRequiresRegistration(Source));
    Source->ComponentTags.Remove(TEXT("DetachedFoliageParticle"));
    TestTrue(TEXT("Removing an ownership tag resumes classification"),System->CachedRequiresRegistration(Source));
    return true;
}

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
    System->SetSourceVisibility(Source,false);
    TestFalse(TEXT("Diagnostic hide reaches generated visual"),Entry.Visual->IsVisible());
    TestFalse(TEXT("Diagnostic hide reaches generated shadows"),bool(Entry.Shadow->CastShadow));
    System->SetEnabled(false);
    TestFalse(TEXT("Hidden state survives switching to originals"),Source->IsVisible());
    System->SetSourceVisibility(Source,true);
    TestTrue(TEXT("Diagnostic show reaches originals"),Source->IsVisible());
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
    System->Sources[0].CastShadow=false;Source->SetCastShadow(false);
    System->SetEnabled(true);
    TestFalse(TEXT("A visual source without shadows must not duplicate its separate shadow owner"),bool(Entry.Shadow->CastShadow));
    System->SetEnabled(false);
    TestFalse(TEXT("A source's disabled shadows remain disabled in original mode"),bool(Source->CastShadow));
    System->Sources[0].CastShadow=true;Source->SetCastShadow(true);
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
        "kind":"tree","aggregate":false,"coverage":[],"source_triangles":900,"shadow_triangles":32,
        "triangles":[416,160,64,32],"canopy_bounds":[[0,0,0],[100,100,100]]}]})");
    TestTrue(TEXT("Complete registry accepted"),Read(Valid));
    TestFalse(TEXT("Aggregation requires certified core geometry"),Read(Valid.Replace(TEXT("\"aggregate\":false"),TEXT("\"aggregate\":true"))));
    TestFalse(TEXT("Truncated coverage refuses"),Read(Valid.Replace(TEXT("\"coverage\":[]"),TEXT("\"coverage\":[[]]"))));
    TestFalse(TEXT("Fractional version refuses"),Read(Valid.Replace(TEXT("\"version\":1"),TEXT("\"version\":1.5"))));
    TestFalse(TEXT("Fractional source count refuses"),Read(Valid.Replace(TEXT("\"source_triangles\":900"),TEXT("\"source_triangles\":900.5"))));
    TestFalse(TEXT("Overflowing shadow count refuses"),Read(Valid.Replace(TEXT("\"shadow_triangles\":32"),TEXT("\"shadow_triangles\":4294967328"))));
    TestFalse(TEXT("Truncated bounds refuse without indexing"),Read(Valid.Replace(TEXT("[[0,0,0],[100,100,100]]"),TEXT("[]"))));
    TestFalse(TEXT("Non-numeric bounds refuse"),Read(Valid.Replace(TEXT("[0,0,0]"),TEXT("[null,0,0]"))));
    TestFalse(TEXT("Unbounded variant refuses"),Read(Valid.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,-1]"))));
    TestFalse(TEXT("Unowned generated path refuses"),Read(Valid.Replace(TEXT("/Game/FoliageSystem/Tree.Tree"),TEXT("/Game/Other/Tree.Tree"))));
    TestTrue(TEXT("Correction recovers after invalid registry"),Read(Valid));
    return true;
}
#endif
