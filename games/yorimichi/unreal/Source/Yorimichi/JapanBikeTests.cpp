#include "JapanBikeState.h"
#include "JapanBikeSubsteps.h"
#include "JapanBikeGround.h"
#if WITH_DEV_AUTOMATION_TESTS
#include "Misc/AutomationTest.h"
#include "Misc/ScopeExit.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/GameNetworkManager.h"
#include "HAL/IConsoleManager.h"
#include "Serialization/MemoryReader.h"
#include "Serialization/MemoryWriter.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FJapanBikeCheckpointTest, "Yorimichi.Network.BikeCheckpoint",
    EAutomationTestFlags_ApplicationContextMask | EAutomationTestFlags::EngineFilter)

bool FJapanBikeCheckpointTest::RunTest(const FString&)
{
    FJapanBikeState Original;
    Original.State=5;Original.Clip=TEXT("BikeCrash");Original.Resume=TEXT("BikeRide");
    Original.Serial=193;Original.Yaw=135.f;Original.ClipTime=.2f;Original.Speed=-200.f;
    Original.Steering=.35f;Original.StillTime=.1f;Original.AppliedYaw=13.f;
    Original.Crank=-354.f;Original.Coast=.3f;Original.Recoil=60.f;
    Original.Drift=-1.25f;Original.Wheelie=18.f;Original.WheelieRate=-40.f;Original.Rise=210.f;Original.Air=.4f;Original.AirFall=380.f;Original.Terminal=false;Original.Pedalling=true;
    TArray<uint8> Bytes;FMemoryWriter Writer(Bytes,true);
    TestTrue(TEXT("Recoil checkpoint encodes"),Original.SerializeCheckpoint(Writer));
    TestEqual(TEXT("Fixed bike checkpoint size"),Bytes.Num(),FJapanBikeState::CheckpointBytes);
    FJapanBikeState Restored;FMemoryReader Reader(Bytes,true);
    TestTrue(TEXT("Checkpoint decodes"),Restored.SerializeCheckpoint(Reader));
    TestEqual(TEXT("Facing is restored before replaying relative turns"),Restored.Yaw,135.f);
    TestEqual(TEXT("Crash recoil survives correction"),Restored.Recoil,60.f);
    TestEqual(TEXT("Authored crank phase survives independent of rendered blend"),Restored.Crank,-354.f);
    TestEqual(TEXT("Clip identity survives without process-local name indices"),Restored.Clip,FName(TEXT("BikeCrash")));
    TestEqual(TEXT("Transition destination survives"),Restored.Resume,FName(TEXT("BikeRide")));
    TestEqual(TEXT("One-shot serial survives"),Restored.Serial,193u);
    TestTrue(TEXT("Remote pedal audio follows the accepted input"),Restored.Pedalling);
    TestEqual(TEXT("Drift side and time survive correction"),Restored.Drift,-1.25f);
    TestEqual(TEXT("Wheelie angle and rate survive correction"),FVector2D(Restored.Wheelie,Restored.WheelieRate),FVector2D(18.f,-40.f));
    TestEqual(TEXT("Ramp rise and airtime survive correction"),FVector(Restored.Rise,Restored.Air,Restored.AirFall),FVector(210.f,.4f,380.f));
    FJapanBikeState Bad=Restored;Bad.State=2;Bad.Terminal=true;
    TestFalse(TEXT("Riding cannot be a terminal parking state"),Bad.IsValid());
    Bad=Restored;Bad.Clip=TEXT("UnknownBikeAction");TestFalse(TEXT("Unknown clip rejected"),Bad.IsValid());
    Bad=Restored;Bad.Speed=2401.f;TestFalse(TEXT("Out-of-policy velocity rejected"),Bad.IsValid());
    Bytes[1]=255;FMemoryReader BadReader(Bytes,true);FJapanBikeState Rejected;
    TestFalse(TEXT("Wire vocabulary out of bounds is rejected before lookup"),Rejected.SerializeCheckpoint(BadReader));

    // The 063828 sprint receipt had a 1.125495 cm correction: a lost packet
    // merged these two owner frames into one final-heading host chord.
    const float First=.033333778381347656f,Second=.03336524963378906f;
    auto Path=[&](bool Split,bool Substeps,float InitialSpeed,float InitialSteering,float Target,float Rate)
    {
        FVector Position=FVector::ZeroVector;
        float Speed=InitialSpeed,Steering=InitialSteering,Yaw=38.00771713256836f;
        auto Advance=[&](float Dt)
        {
            Speed=FMath::FInterpConstantTo(Speed,Target,Dt,Rate);
            Steering=FMath::FInterpTo(Steering,65.f/127.f,Dt,5.f);
            Yaw+=FMath::Clamp(FMath::RadiansToDegrees(Speed/260.f),0.f,110.f)*Steering*Dt;
            Position+=FRotator(0,Yaw,0).Vector()*Speed*Dt;
        };
        auto Move=[&](float Dt){if(Substeps)JapanBikeSubsteps::Run(Dt,Advance);else Advance(Dt);};
        if(Split){Move(First);Move(Second);}else Move(First+Second);
        return Position;
    };
    const float Sprint=1029.9212646484375f,Steer=65.f/127.f;
    const double OldError=FVector::Dist(Path(true,false,Sprint,Steer,Sprint,0),Path(false,false,Sprint,Steer,Sprint,0));
    TestTrue(TEXT("Recorded unsplit sprint chord reproduces the strict-gate failure"),OldError>1.&&FMath::Abs(OldError-1.125495)<.001);
    for(const FVector4 Case:{FVector4(Sprint,Steer,Sprint,0),FVector4(400,0,Sprint,420),FVector4(Sprint,Steer,0,950)})
        TestTrue(TEXT("Merged and split sprint, acceleration and braking stay within a tenth centimetre"),
            FVector::Dist(Path(true,true,Case.X,Case.Y,Case.Z,Case.W),Path(false,true,Case.X,Case.Y,Case.Z,Case.W))<.1);
    int32 Count=0;float Total=0.f,Largest=0.f;
    JapanBikeSubsteps::Run(1.f,[&](float Dt){++Count;Total+=Dt;Largest=FMath::Max(Largest,Dt);});
    TestEqual(TEXT("Oversized intervals stay bounded on every role"),Count,15);
    TestTrue(TEXT("The cap preserves the bounded total and maximum substep"),
        FMath::Abs(Total-JapanBikeSubsteps::MaximumDelta)<1.e-6f&&Largest<=JapanBikeSubsteps::MaximumStep);
    const auto* Scalar=IConsoleManager::Get().FindConsoleVariable(TEXT("p.NetServerMaxMoveDeltaTimeScalar"));
    TestTrue(TEXT("The bike and ordinary CMC move caps agree"),Scalar&&
        FMath::IsNearlyEqual(GetDefault<AGameNetworkManager>()->MaxMoveDeltaTime*Scalar->GetFloat(),JapanBikeSubsteps::MaximumDelta,1.e-6f));
    UWorld* World=nullptr;
    for(const FWorldContext& Context:GEngine->GetWorldContexts())
        if(Context.World()&&Context.World()->IsGameWorld()){World=Context.World();break;}
    if(!TestNotNull(TEXT("Park placement regression has a game world"),World))return false;
    FActorSpawnParameters Spawn;Spawn.ObjectFlags|=RF_Transient;
    Spawn.SpawnCollisionHandlingOverride=ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    auto* Floor=World->SpawnActor<AActor>(Spawn);
    auto* Rider=World->SpawnActor<ACharacter>(Spawn);
    if(!Floor||!Rider){if(Floor)Floor->Destroy();if(Rider)Rider->Destroy();return false;}
    ON_SCOPE_EXIT {Rider->Destroy();Floor->Destroy();};
    auto* Box=NewObject<UBoxComponent>(Floor);Floor->SetRootComponent(Box);Floor->AddInstanceComponent(Box);
    Box->SetBoxExtent(FVector(200,200,10));Box->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Box->SetCollisionResponseToAllChannels(ECR_Block);Box->RegisterComponent();
    const FVector Origin(10000,0,100000);Floor->SetActorLocation(Origin);
    auto* Movement=Rider->GetCharacterMovement();Movement->bRunPhysicsWithNoController=true;
    const double Gap=(UCharacterMovementComponent::MIN_FLOOR_DIST+UCharacterMovementComponent::MAX_FLOOR_DIST)*.5+1.0890856;
    const FVector Raised=Origin+FVector(0,0,10+Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+Gap);
    Movement->SetMovementMode(MOVE_Walking);Movement->StopMovementImmediately();
    Rider->SetActorLocation(Raised,false,nullptr,ETeleportType::TeleportPhysics);
    // Reproduce the exact-sized delayed floor adjustment without the repair.
    Movement->bForceNextFloorCheck=true;Movement->TickComponent(1.f/60.f,LEVELTICK_All,&Movement->PrimaryComponentTick);
    TestTrue(TEXT("An unsettled step-off moves more than a centimetre on its first neutral tick"),
        FVector::Dist(Raised,Rider->GetActorLocation())>1.);
    Rider->SetActorLocation(Raised,false,nullptr,ETeleportType::TeleportPhysics);
    TestTrue(TEXT("A grounded park resolves its support before snapshot"),JapanBikeGround::SettlePark(Rider));
    TestTrue(TEXT("The settled capsule is in CMC's floor-distance band"),
        Movement->CurrentFloor.FloorDist>=UCharacterMovementComponent::MIN_FLOOR_DIST&&
        Movement->CurrentFloor.FloorDist<=UCharacterMovementComponent::MAX_FLOOR_DIST);
    const FVector Settled=Rider->GetActorLocation();
    TestTrue(TEXT("The recorded vertical step-off gap is resolved before commit"),
        FMath::Abs((Raised.Z-Settled.Z)-1.0890856)<=.01);
    Movement->bForceNextFloorCheck=true;Movement->TickComponent(1.f/60.f,LEVELTICK_All,&Movement->PrimaryComponentTick);
    TestTrue(TEXT("The next neutral tick does not alter the committed grounded pose"),
        FVector::Dist(Settled,Rider->GetActorLocation())<=.01);
    Movement->SetMovementMode(MOVE_Falling);Rider->SetActorLocation(Raised,false,nullptr,ETeleportType::TeleportPhysics);
    TestFalse(TEXT("Falling exits are not settled"),JapanBikeGround::SettlePark(Rider));
    TestTrue(TEXT("Falling pose stays unchanged"),Rider->GetActorLocation().Equals(Raised,.001));
    return true;
}
#endif
