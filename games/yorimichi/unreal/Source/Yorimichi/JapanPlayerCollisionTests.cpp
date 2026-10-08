#include "JapanNetwork.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Components/CapsuleComponent.h"
#include "Components/BoxComponent.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanPlayerCollisionTest, "Yorimichi.Network.PlayerCollision",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanPlayerCollisionTest::RunTest(const FString&)
{
    UWorld* World=nullptr;
    for(const FWorldContext& Context:GEngine->GetWorldContexts())
        if(Context.World()&&Context.World()->IsGameWorld()){World=Context.World();break;}
    if(!TestNotNull(TEXT("Collision regression has a native physics world"),World))return false;
    FActorSpawnParameters Spawn;Spawn.ObjectFlags|=RF_Transient;
    Spawn.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Victim=World->SpawnActor<AActor>(Spawn);
    auto* Wall=World->SpawnActor<AActor>(Spawn);
    if(!Victim||!Wall){if(Victim)Victim->Destroy();if(Wall)Wall->Destroy();return false;}
    ON_SCOPE_EXIT {Victim->Destroy();Wall->Destroy();};
    auto* Capsule=NewObject<UCapsuleComponent>(Victim);
    Victim->SetRootComponent(Capsule);Victim->AddInstanceComponent(Capsule);
    Capsule->SetCapsuleSize(20.f,50.f);
    Capsule->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Capsule->SetCollisionObjectType(ECC_Pawn);Capsule->SetCollisionResponseToAllChannels(ECR_Block);
    Capsule->SetCollisionResponseToChannel(ECC_Pawn,ECR_Ignore);
    Capsule->RegisterComponent();
    const FVector Origin(0,0,100000);
    Victim->SetActorLocation(Origin+FVector(100,0,0));
    const FVector End=Origin+FVector(200,0,0);
    const FCollisionShape Claw=FCollisionShape::MakeSphere(14.f);
    FCollisionQueryParams Params(SCENE_QUERY_STAT(NetworkClawRegression),false);
    TArray<FHitResult> Hits;
    const auto SawCapsule=[&](){return Hits.ContainsByPredicate([&](const FHitResult& H){return H.GetComponent()==Capsule;});};
    World->SweepMultiByChannel(Hits,Origin,End,FQuat::Identity,ECC_Pawn,Claw,Params);
    TestFalse(TEXT("Previous online Ignore response makes the claw miss"),SawCapsule());
    JapanNetwork::ConfigurePlayerCollision(Capsule);
    World->SweepMultiByChannel(Hits,Origin,End,FQuat::Identity,ECC_Pawn,Claw,Params);
    TestTrue(TEXT("Real authored claw sweep sees the configured player capsule"),SawCapsule());
    for(const FHitResult& Hit:Hits)
        if(Hit.GetComponent()==Capsule)TestFalse(TEXT("Player contact never blocks another pawn"),Hit.bBlockingHit);
    FHitResult Blocking;
    TestFalse(TEXT("Movement blocking sweep passes through players"),
        World->SweepSingleByChannel(Blocking,Origin,End,FQuat::Identity,ECC_Pawn,Claw,Params));
    TestFalse(TEXT("Blocking clearance remains clear at the player"),
        World->OverlapBlockingTestByChannel(Victim->GetActorLocation(),FQuat::Identity,ECC_Pawn,Claw,Params));
    auto* Box=NewObject<UBoxComponent>(Wall);
    Wall->SetRootComponent(Box);Wall->AddInstanceComponent(Box);
    Box->SetBoxExtent(FVector(5,100,100));Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Box->SetCollisionObjectType(ECC_WorldStatic);Box->SetCollisionResponseToAllChannels(ECR_Block);
    Box->RegisterComponent();Wall->SetActorLocation(Origin+FVector(50,0,0));
    World->SweepMultiByChannel(Hits,Origin,End,FQuat::Identity,ECC_Pawn,Claw,Params);
    TestFalse(TEXT("A blocking wall still shields the player from the claw sweep"),SawCapsule());
    TestTrue(TEXT("The same query reports the shielding wall"),
        Hits.ContainsByPredicate([&](const FHitResult& H){return H.GetComponent()==Box&&H.bBlockingHit;}));
    return true;
}
#endif
