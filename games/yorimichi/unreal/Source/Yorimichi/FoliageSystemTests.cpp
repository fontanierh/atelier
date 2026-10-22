#include "FoliageSystem.h"
#include "FoliagePatchCoverage.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "JapanPreferences.h"
#include "JapanWorld.h"
#include "WandererCharacter.h"
#include "AtelierSettings.h"
#include "AtelierData.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/Material.h"
#include "Engine/World.h"
#include "GameFramework/Actor.h"
#include "Dom/JsonObject.h"
#include "Misc/AutomationTest.h"
#include "UObject/StrongObjectPtr.h"
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
    TArray<FStaticMaterial> PropSlots={FStaticMaterial(nullptr,TEXT("FoliageAuthored_Pot")),
        FStaticMaterial(nullptr,TEXT("FoliageAuthored_Leaves"))};
    TestTrue(TEXT("Explicit small authored props stay ordinary"),System->OrdinaryAuthoredProp(PropSlots,100));
    TestTrue(TEXT("Authored prop budget is inclusive"),System->OrdinaryAuthoredProp(PropSlots,12288));
    TestFalse(TEXT("Oversized authored props require foliage registration"),System->OrdinaryAuthoredProp(PropSlots,12289));
    TestFalse(TEXT("Empty geometry cannot claim ordinary prop status"),System->OrdinaryAuthoredProp(PropSlots,0));
    PropSlots[1].MaterialSlotName=TEXT("FoliageRoles_Leaves");
    TestFalse(TEXT("Mixed explicit foliage roles cannot bypass conversion"),System->OrdinaryAuthoredProp(PropSlots,100));
    PropSlots.Reset();
    TestFalse(TEXT("Untagged props cannot claim the exception"),System->OrdinaryAuthoredProp(PropSlots,100));
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
    // Real saved engine assets exercise reloads/GC, not two retained pointers.
    const FString Legacy=TEXT("/Engine/BasicShapes/Cube.Cube"),Prepared=TEXT("/Engine/BasicShapes/Sphere.Sphere");
    const FString Shadow=TEXT("/Engine/BasicShapes/Plane.Plane");
    auto* Mesh=LoadObject<UStaticMesh>(nullptr,*Legacy);
    auto* Optimized=LoadObject<UStaticMesh>(nullptr,*Prepared);
    auto* ShadowMesh=LoadObject<UStaticMesh>(nullptr,*Shadow);
    if (!Mesh || !Optimized || !ShadowMesh) { World->DestroyWorld(false);return false; }
    UYorimichiFoliageSubsystem::FAsset Asset;
    Asset.Optimized=Prepared;Asset.Shadow=Shadow;Asset.Kind=TEXT("shrub");
    Asset.Triangles=Mesh->GetNumTriangles(0);Asset.ShadowTriangles=ShadowMesh->GetNumTriangles(0);
    for (int32 L=0;L<Optimized->GetNumLODs();++L) Asset.LODTriangles.Add(Optimized->GetNumTriangles(L));
    for (const auto& Material:Mesh->GetStaticMaterials()) Asset.SourceMaterials.Add(Material.MaterialInterface->GetPathName());
    System->Assets.Add(Legacy,Asset);System->ResidentSources.Add(Prepared,Legacy);
    System->ResidentSources.Add(Shadow,Legacy);System->bRegistryLoaded=true;System->bEnabled=false;
    auto* Actor=World->SpawnActor<AActor>();
    auto* Source=UYorimichiFoliageSubsystem::NewInstances(Actor);
    Actor->SetRootComponent(Source);Source->SetStaticMesh(Mesh);Source->RegisterComponent();
    Source->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Source->SetCastShadow(true);
    Source->SetMobility(EComponentMobility::Static);
    World->SetBegunPlay(true); // Exercise SetStaticMesh's registered Static mobility refusal.
    Source->bAffectDistanceFieldLighting=true;
    Source->SetEvaluateWorldPositionOffset(true);
    Source->SetCullDistances(30000,36000);Source->SetLODDistanceScale(1.7f);
    Source->SetWorldPositionOffsetDisableDistance(1234);
    const FTransform Placement(FRotator(0,31,0),FVector(300,400,50),FVector(1,2,3));
    Source->AddInstance(Placement);Source->AddInstance(FTransform(FVector(900,200,0)));
    TestTrue(TEXT("Legacy mode registers without loading prepared copies"),System->Refresh());
    TestNull(TEXT("Legacy has no prepared child"),System->Sources[0].Visual.Get());
    for (int32 Round=0;Round<3;++Round)
    {
        System->SetSourceVisibility(Source,false);
        TestTrue(TEXT("Optimization reloads live"),System->SetEnabled(true));
        System->Tick(0.f);
        TestEqual(TEXT("Primary mesh is prepared, not a retained original"),Source->GetStaticMesh()->GetPathName(),Prepared);
        TestEqual(TEXT("Canonical identity survives the replacement"),UYorimichiFoliageSubsystem::SourcePath(Source->GetStaticMesh()),Legacy);
        TestFalse(TEXT("Authored hidden state survives reload"),Source->IsVisible());
        System->SetSourceVisibility(Source,true);
        TestTrue(TEXT("Prepared mesh renders"),Source->IsVisible());
        System->SetDistances(true,.4f,0.f,80.f);
        TestTrue(TEXT("Zero tree sway retains bush player-push WPO"),bool(Source->bEvaluateWorldPositionOffset));
        TestEqual(TEXT("Zero tree sway retains authored bush WPO reach"),Source->GetWorldPositionOffsetDisableDistance(),1234);
        TestTrue(TEXT("Owned bush WPO setting passes the actual binding audit"),System->Refresh());
        TestEqual(TEXT("Prepared bush has bounded culling"),Source->InstanceEndCullDistance,20000);
        TestEqual(TEXT("Collision lives on the active component"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
        TestEqual(TEXT("Placement count retained"),Source->GetInstanceCount(),2);
        FTransform Actual;Source->GetInstanceTransform(0,Actual,false);
        TestTrue(TEXT("Authored transform retained"),Actual.Equals(Placement));
        TestTrue(TEXT("Optimization off reloads legacy"),System->SetEnabled(false));
        System->Tick(0.f);
        TestEqual(TEXT("Only legacy is bound after disabling"),Source->GetStaticMesh()->GetPathName(),Legacy);
        TestNull(TEXT("Prepared renderer reference released"),System->Sources[0].Visual.Get());
        TestNull(TEXT("Prepared shadow reference released"),System->Sources[0].Shadow.Get());
        TestTrue(TEXT("Legacy visibility restored"),Source->IsVisible());
        TestTrue(TEXT("Legacy shadow state restored"),bool(Source->CastShadow));
        TestEqual(TEXT("Legacy bush start cull restored"),Source->InstanceStartCullDistance,30000);
        TestEqual(TEXT("Legacy bush end cull restored"),Source->InstanceEndCullDistance,36000);
        TestEqual(TEXT("Legacy LOD distance scale restored"),Source->GetLODDistanceScale(),1.7f);
        TestTrue(TEXT("Legacy WPO restored"),bool(Source->bEvaluateWorldPositionOffset));
        TestEqual(TEXT("Legacy WPO reach restored"),Source->GetWorldPositionOffsetDisableDistance(),1234);
    }
    TStrongObjectPtr<UJapanPreferences> KeepPreferences(NewObject<UJapanPreferences>());
    auto* Preferences=KeepPreferences.Get();
    World->SetBegunPlay(false); // Keep the settings fixture's pawn from bootstrapping a game.
    Preferences->Owner=World->SpawnActor<AWandererCharacter>();Preferences->Values=JapanDefaultPreferences(nullptr);
    World->SetBegunPlay(true);
    const FString Directory=FPaths::ConvertRelativePathToFull(FPaths::ProjectDir(),
        TEXT("../../../build/yorimichi/foliage-tests-settings/"))+FGuid::NewGuid().ToString();
    IFileManager::Get().MakeDirectory(*Directory,true);
    const FString File=Directory/TEXT("settings.txt");Preferences->SettingsFile=File;
    TestTrue(TEXT("Settings saves prepared mode"),Preferences->SetValue(TEXT("foliage_optimization"),1.f));
    System->Tick(0.f);
    TestEqual(TEXT("On persists"),AtelierSettings::ReadFile(File).FindRef(TEXT("foliage_optimization")),FString(TEXT("1.0")));
    Preferences->SettingsFile=Directory;
    AddExpectedError(TEXT("PREFERENCES could not save"),EAutomationExpectedErrorFlags::Contains,1);
    TestFalse(TEXT("Failed save rolls mode back"),Preferences->SetValue(TEXT("foliage_optimization"),0.f));
    TestTrue(TEXT("Prepared mode restored after failed save"),System->IsEnabled());
    TestEqual(TEXT("Rollback reloads the prepared mesh"),Source->GetStaticMesh()->GetPathName(),Prepared);
    IFileManager::Get().DeleteDirectory(*Directory,false,true);
    System->Sources.Reset();World->DestroyWorld(false);return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliagePerformanceSettingsTest,"Yorimichi.Foliage.PerformanceSettings",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliagePerformanceSettingsTest::RunTest(const FString&)
{
    const auto Init=UWorld::InitializationValues().AllowAudioPlayback(false).CreatePhysicsScene(false);
    auto* World=UWorld::CreateWorld(EWorldType::Game,false,NAME_None,nullptr,true,ERHIFeatureLevel::Num,&Init);
    if (!TestNotNull(TEXT("Isolated settings world"),World)) return false;
    auto* System=World->GetSubsystem<UYorimichiFoliageSubsystem>();
    auto* Map=World->SpawnActor<AJapanWorld>();Map->bLoaded=true;System->bEnabled=false;
    for (const TCHAR* Name:{TEXT("Tree_Settings"),TEXT("Bush_Settings"),TEXT("Grass_Settings")})
    {
        auto* Group=NewObject<UHierarchicalInstancedStaticMeshComponent>(Map);
        Group->SetStaticMesh(NewObject<UStaticMesh>(Map,FName(Name)));
        Group->SetCullDistances(6000,8000);Group->SetLODDistanceScale(1.7f);
        Group->SetWorldPositionOffsetDisableDistance(1234);Group->SetEvaluateWorldPositionOffset(true);
        Map->Groups.Add(Group);
        FYorimichiFoliageSource Entry;Entry.Original=Group;Entry.EvaluateWPO=true;
        Entry.StartCullDistance=6000;Entry.EndCullDistance=8000;Entry.LODDistanceScale=1.7f;Entry.WPODisableDistance=1234;
        System->Sources.Add(Entry);
    }
    auto* Tree=Map->Groups[0];auto* Bush=Map->Groups[1];auto* Grass=Map->Groups[2];
    for (bool Performance:{true,false})
    {
        const float Sway=Performance?25.f:35.f,Detail=Performance?.3f:.6f;
        Map->ApplyPerformanceSettings(Performance,Sway,Detail,80.f);
        System->SetDistances(Performance,Detail,Sway,80.f);
        TestEqual(TEXT("Legacy Apply retains current grass setting"),Grass->InstanceEndCullDistance,Performance?5000:8000);
        TestEqual(TEXT("Legacy Apply retains current tree detail"),Tree->GetLODDistanceScale(),Detail);
        TestEqual(TEXT("Legacy Apply retains current bush WPO reach"),Bush->GetWorldPositionOffsetDisableDistance(),FMath::RoundToInt(Sway*100.f));
        // Reproduce a mode removal restoring older authored values, without a
        // settings value change to invalidate JapanWorld's cached guard.
        Grass->SetCullDistances(6000,8000);Tree->SetLODDistanceScale(1.7f);
        Bush->SetWorldPositionOffsetDisableDistance(1234);
        Map->ApplyPerformanceSettings(Performance,Sway,Detail,80.f,true);
        TestEqual(TEXT("Reload reapplies unchanged grass setting"),Grass->InstanceEndCullDistance,Performance?5000:8000);
        TestEqual(TEXT("Reload reapplies unchanged tree detail"),Tree->GetLODDistanceScale(),Detail);
        TestEqual(TEXT("Reload reapplies unchanged bush WPO reach"),Bush->GetWorldPositionOffsetDisableDistance(),FMath::RoundToInt(Sway*100.f));
    }
    System->Sources.Reset();World->DestroyWorld(false);return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageCollisionPolicyTest,"Yorimichi.Foliage.CollisionPolicy",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageCollisionPolicyTest::RunTest(const FString&)
{
    auto* System=NewObject<UYorimichiFoliageSubsystem>();System->bEnabled=true;
    auto* Source=NewObject<UStaticMeshComponent>();
    Source->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Source->SetCollisionResponseToChannel(ECC_Camera,ECR_Block);
    const FTransform Placement(FRotator(0,31,0),FVector(300,400,50),FVector(1,2,3));Source->SetRelativeTransform(Placement);
    FYorimichiFoliageSource Entry;Entry.Original=Source;Entry.SourcePath=TEXT("/Game/Test/Tree.Tree");
    Entry.Collision=Source->GetCollisionEnabled();
    UYorimichiFoliageSubsystem::FAsset Asset;Asset.SimpleTrunk=true;System->Assets.Add(Entry.SourcePath,Asset);
    System->ApplyCollision(Entry);
    TestEqual(TEXT("Authored nonblocking trees remain passable"),Source->GetCollisionEnabled(),ECollisionEnabled::NoCollision);
    TestEqual(TEXT("Authored camera response retained"),Source->GetCollisionResponseToChannel(ECC_Camera),ECR_Block);
    TestTrue(TEXT("Collision policy preserves placement"),Source->GetRelativeTransform().Equals(Placement));
    Source->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Entry.Collision=ECollisionEnabled::QueryOnly;
    System->ApplyCollision(Entry);
    TestEqual(TEXT("Authored blocking tree keeps its enablement"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
    TestEqual(TEXT("Trunk replacement does not alter camera response"),Source->GetCollisionResponseToChannel(ECC_Camera),ECR_Block);
    System->Restore(Entry);
    TestEqual(TEXT("Legacy collision retained"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
    TestEqual(TEXT("Legacy camera response restored"),Source->GetCollisionResponseToChannel(ECC_Camera),ECR_Block);
    Source->SetCollisionEnabled(ECollisionEnabled::NoCollision);Entry.Collision=ECollisionEnabled::NoCollision;
    Source->ComponentTags.Add(TEXT("FoliageBackdrop"));System->ApplyCollision(Entry);
    TestEqual(TEXT("Backdrop stays nonblocking"),Source->GetCollisionEnabled(),ECollisionEnabled::NoCollision);
    Source->ComponentTags.Reset();Entry.ShadowOnly=true;System->ApplyCollision(Entry);
    TestEqual(TEXT("Shadow-only placement stays nonblocking"),Source->GetCollisionEnabled(),ECollisionEnabled::NoCollision);
    Entry.ShadowOnly=false;System->Assets[Entry.SourcePath].SimpleTrunk=false;System->Assets[Entry.SourcePath].Passable=true;
    Source->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Entry.Collision=ECollisionEnabled::QueryOnly;
    System->ApplyCollision(Entry);TestEqual(TEXT("Bush stems remain passable"),Source->GetCollisionEnabled(),ECollisionEnabled::NoCollision);
    System->bEnabled=false;System->Apply(Entry);
    TestEqual(TEXT("Legacy graphics keeps the same passable bush policy"),Source->GetCollisionEnabled(),ECollisionEnabled::NoCollision);
    System->Restore(Entry);TestEqual(TEXT("Releasing ownership restores authored policy"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
    System->bEnabled=true;
    System->Assets[Entry.SourcePath].Passable=false;System->ApplyCollision(Entry);
    TestEqual(TEXT("Mixed rigid scenery retains collision"),Source->GetCollisionEnabled(),ECollisionEnabled::QueryOnly);
    return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FYorimichiFoliageBindingTest,"Yorimichi.Foliage.BindingChanges",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FYorimichiFoliageBindingTest::RunTest(const FString&)
{
    auto* System=NewObject<UYorimichiFoliageSubsystem>();System->bEnabled=true;
    auto* Source=NewObject<UStaticMeshComponent>();auto* Mesh=NewObject<UStaticMesh>();
    auto* Material=NewObject<UMaterial>();auto* Other=NewObject<UMaterial>();
    Mesh->GetStaticMaterials().Add(FStaticMaterial(Material,TEXT("Leaves")));Source->SetStaticMesh(Mesh);
    Source->SetEvaluateWorldPositionOffset(true);
    FYorimichiFoliageSource Entry;Entry.Original=Source;Entry.HasRigid=true;Entry.EvaluateWPO=true;
    Entry.Collision=Source->GetCollisionEnabled();
    System->CaptureBindings(Entry);TestTrue(TEXT("Current binding accepted"),System->BindingsCurrent(Entry));
    Source->SetMaterial(0,Other);TestFalse(TEXT("Live override requires explicit revalidation"),System->BindingsCurrent(Entry));
    Source->SetMaterial(0,Material);Mesh->GetStaticMaterials()[0].MaterialSlotName=TEXT("Moved");
    TestFalse(TEXT("Live slot mutation invalidates existing registration"),System->BindingsCurrent(Entry));
    Mesh->GetStaticMaterials()[0].MaterialSlotName=TEXT("Leaves");Source->SetEvaluateWorldPositionOffset(false);
    TestFalse(TEXT("Live WPO mutation invalidates existing registration"),System->BindingsCurrent(Entry));
    Source->SetEvaluateWorldPositionOffset(true);TestTrue(TEXT("Corrected binding recovers"),System->BindingsCurrent(Entry));
    Source->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    TestFalse(TEXT("External collision changes require explicit revalidation"),System->BindingsCurrent(Entry));
    Source->SetCollisionEnabled(Entry.Collision);
    Entry.Visual=Source;Entry.Kind=TEXT("tree");System->Sway=0;Source->SetEvaluateWorldPositionOffset(false);
    TestTrue(TEXT("Owned sway setting is not an external mutation"),System->BindingsCurrent(Entry));
    return true;
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
    const FString Resident=Valid.Replace(TEXT("\"version\":1"),TEXT("\"version\":2"))
        .Replace(TEXT("/Game/FoliageSystem/Tree.Tree"),TEXT("/Game/FoliageResident/Tree_Canopy.Tree_Canopy"))
        .Replace(TEXT("/Game/FoliageSystem/Tree_Shadow.Tree_Shadow"),TEXT("/Game/FoliageResident/Tree_Shadow.Tree_Shadow"))
        .Replace(TEXT("\"kind\":\"tree\""),TEXT("\"simple_trunk\":false,\"passable\":false,\"rigid\":\"/Game/FoliageResident/Tree.Tree\",\"rigid_triangles\":4,\"rigid_lod_triangles\":[4],\"source_materials\":[\"/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial\"],\"kind\":\"tree\""));
    TestTrue(TEXT("Certified empty resident shadow accepted"),Read(Resident.Replace(TEXT("\"shadow_triangles\":32"),TEXT("\"shadow_triangles\":0"))));
    TestFalse(TEXT("Negative resident shadow refuses"),Read(Resident.Replace(TEXT("\"shadow_triangles\":32"),TEXT("\"shadow_triangles\":-1"))));
    TestFalse(TEXT("Legacy shadow schema stays positive"),Read(Valid.Replace(TEXT("\"shadow_triangles\":32"),TEXT("\"shadow_triangles\":0"))));
    TestTrue(TEXT("Resident registry retains source identity without source loading"),Read(Resident));
    TestEqual(TEXT("Carrier resolves to canonical source"),System->ResidentSources.FindRef(TEXT("/Game/FoliageResident/Tree.Tree")),FString(TEXT("/Game/Test/Tree.Tree")));
    TestFalse(TEXT("Missing trunk policy refuses"),Read(Resident.Replace(TEXT("\"simple_trunk\":false"),TEXT("\"missing_trunk\":false"))));
    TestFalse(TEXT("Contradictory collision policy refuses"),Read(Resident.Replace(TEXT("\"simple_trunk\":false,\"passable\":false"),TEXT("\"simple_trunk\":true,\"passable\":true"))));
    const FString Distant=Resident.Replace(TEXT("\"rigid_lod_triangles\":[4]"),TEXT("\"rigid_lod_triangles\":[4,3,2,0]"));
    TestTrue(TEXT("Certified distant rigid LOD may be empty"),Read(Distant));
    TestFalse(TEXT("Negative distant rigid count refuses"),Read(Distant.Replace(TEXT("[4,3,2,0]"),TEXT("[4,3,2,-1]"))));
    TestFalse(TEXT("Empty rigid LOD0 cannot match a positive carrier"),Read(Distant.Replace(TEXT("[4,3,2,0]"),TEXT("[0,3,2,0]"))));
    TestFalse(TEXT("Fractional distant rigid count refuses"),Read(Distant.Replace(TEXT("[4,3,2,0]"),TEXT("[4,3,2,0.5]"))));
    const FString Five=Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,32,14]"))
        .Replace(TEXT("\"rigid_lod_triangles\":[4]"),TEXT("\"rigid_lod_triangles\":[4,3,2,1,0]"));
    TestTrue(TEXT("Complete five-level authored chain retains its far impostor"),Read(Five));
    TestFalse(TEXT("Rigid chain must match canopy chain or use one mixed carrier level"),
        Read(Five.Replace(TEXT("[4,3,2,1,0]"),TEXT("[4,3,2,0]"))));
    TestTrue(TEXT("One-level authored canopy accepted"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416]"))));
    TestTrue(TEXT("Eight-level authored canopy accepted"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,32,16,8,4,0]"))));
    TestFalse(TEXT("Unbounded authored chain refuses"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,32,16,8,4,2,1]"))));
    TestFalse(TEXT("Missing canopy chain refuses"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[]"))));
    TestFalse(TEXT("Empty canopy LOD0 refuses"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[0,0]"))));
    TestTrue(TEXT("Exactly certified empty distant canopy accepted"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416,0]"))));
    TestFalse(TEXT("Fractional distant canopy refuses"),Read(Resident.Replace(TEXT("[416,160,64,32]"),TEXT("[416,0.5]"))));
    TestFalse(TEXT("Legacy registry retains four-level schema"),Read(Valid.Replace(TEXT("[416,160,64,32]"),TEXT("[416,160,64,32,14]"))));
    TestFalse(TEXT("Absent rigid path cannot claim rigid geometry"),Read(Resident.Replace(TEXT("/Game/FoliageResident/Tree.Tree"),TEXT(""))));
    TestFalse(TEXT("Source material proof is required"),Read(Resident.Replace(TEXT("\"source_materials\""),TEXT("\"missing_materials\""))));
    const FString PublishedPath=AtelierDataPath(TEXT("foliage_residency/registry.json"));
    if (IFileManager::Get().FileExists(*PublishedPath))
    {
        System->bRegistryLoaded=false;
        TestTrue(TEXT("Current published residency registry passes the actual runtime loader"),System->LoadRegistry());
    }
    return true;
}
#endif
