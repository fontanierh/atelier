#include "JapanGameplayCollision.h"
#include "JapanGameplayCollisionWorld.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Components/StaticMeshComponent.h"
#include "Components/BoxComponent.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanFixedCollisionTest, "Yorimichi.Network.FixedCollision",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanFixedCollisionTest::RunTest(const FString&)
{
    UWorld* World=nullptr;
    for(const FWorldContext& Context:GEngine->GetWorldContexts())
        if(Context.World()&&Context.World()->IsGameWorld()){World=Context.World();break;}
    if(!TestNotNull(TEXT("Fixed collision regression has a game world"),World))return false;
    auto* Cache=World->GetSubsystem<UJapanGameplayCollisionWorld>();
    auto* Cube=LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube"));
    if(!TestNotNull(TEXT("Collision cache exists"),Cache)||!TestNotNull(TEXT("Authored test mesh exists"),Cube))return false;
    FActorSpawnParameters Spawn;Spawn.ObjectFlags|=RF_Transient;
    Spawn.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    const FVector Origin(0,0,100000);
    auto* Fixed=World->SpawnActor<AStaticMeshActor>(Origin+FVector(200,0,0),FRotator::ZeroRotator,Spawn);
    auto* Dynamic=World->SpawnActor<AActor>(Spawn);
    if(!Fixed||!Dynamic){if(Fixed)Fixed->Destroy();if(Dynamic)Dynamic->Destroy();return false;}
    ON_SCOPE_EXIT {Fixed->Destroy();Dynamic->Destroy();Cache->Install();};
    auto* Mesh=Fixed->GetStaticMeshComponent();
    Mesh->SetStaticMesh(Cube);Mesh->SetMobility(EComponentMobility::Static);
    Mesh->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Mesh->SetCollisionResponseToAllChannels(ECR_Block);
    // Mixed-case authored names expose FString's default case-insensitive sort.
    for(const FName Name:{FName(TEXT("zFixed")),FName(TEXT("AFixed"))})
    {
        auto* Part=NewObject<UBoxComponent>(Fixed,Name);Fixed->AddInstanceComponent(Part);
        Part->SetupAttachment(Mesh);Part->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        Part->SetCollisionResponseToAllChannels(ECR_Block);Part->RegisterComponent();
    }
    Cache->Install();
    // Simulate the real UE sequence: BeginPlay installs the owner, then the
    // world delivers its OnActorSpawned callback after FinishSpawning.
    Cache->Spawned(Fixed);
    TestEqual(TEXT("Late spawn notification keeps installed channel blocking"),
        Mesh->GetCollisionResponseToChannel(JapanGameplayCollision::Channel),ECR_Block);
    auto Query=JapanGameplayCollision::Query(World,TEXT("FixedRegression"),TStatId(),false);
    FHitResult Hit;
    TestTrue(TEXT("The installed owner remains visible to a real gameplay trace"),
        World->LineTraceSingleByChannel(Hit,Origin,Origin+FVector(400,0,0),JapanGameplayCollision::Channel,Query));
    TestTrue(TEXT("Trace hits the certified actor"),Hit.GetActor()==Fixed);
    // A BlockAll component created later on an ordinary dynamic owner cannot
    // sneak into the cached fixed query, even though its channel says Block.
    auto* Box=NewObject<UBoxComponent>(Dynamic);Dynamic->SetRootComponent(Box);Dynamic->AddInstanceComponent(Box);
    Box->SetBoxExtent(FVector(20));Box->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
    Box->SetCollisionResponseToAllChannels(ECR_Block);Box->RegisterComponent();Dynamic->SetActorLocation(Origin+FVector(100,0,0));
    World->LineTraceSingleByChannel(Hit,Origin,Origin+FVector(400,0,0),JapanGameplayCollision::Channel,Query);
    TestTrue(TEXT("Later dynamic geometry remains excluded"),Hit.GetActor()==Fixed);
    TArray<FString> Errors;
    const auto Inventory=JapanGameplayCollision::Inventory(World,Errors);
    TestTrue(TEXT("Installed fixed responses agree with visibility"),Errors.IsEmpty());
    for(int32 I=1;I<Inventory.Num();++I)
        TestTrue(TEXT("Inventory uses the receipt's case-sensitive order"),
            Inventory[I-1].Compare(Inventory[I],ESearchCase::CaseSensitive)<0);
    return true;
}
#endif
