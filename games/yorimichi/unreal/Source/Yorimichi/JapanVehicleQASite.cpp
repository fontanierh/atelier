#include "JapanVehicleQASite.h"
#if !UE_BUILD_SHIPPING
#include "WandererCharacter.h"
#include "JapanGameplayCollision.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"

bool JapanVehicleQASite::Crash(AWandererCharacter* Rider,FVector& Start,float& Yaw,TSharedPtr<FJsonObject>& Evidence)
{
    UWorld* World=Rider->GetWorld();
    auto Q=JapanGameplayCollision::Query(World,SCENE_QUERY_STAT(VehicleQASite),false);Q.AddIgnoredActor(Rider);
    const FVector Home=Rider->GetActorLocation();
    auto Ground=[&](FVector At,FHitResult& Hit)
    {return World->LineTraceSingleByChannel(Hit,FVector(At.X,At.Y,Home.Z+5000),FVector(At.X,At.Y,Home.Z-5000),JapanGameplayCollision::Channel,Q)&&Hit.ImpactNormal.Z>.98;};
    int32 Queries=0;
    for(int32 X=-2;X<=2;++X)for(int32 Y=-2;Y<=2;++Y)
    {
        FHitResult Floor;++Queries;
        if(!Ground(Home+FVector(X*1500.f,Y*1500.f,0),Floor))continue;
        const FVector Origin=Floor.ImpactPoint+FVector(0,0,40);
        for(int32 A=0;A<36;++A)
        {
            FHitResult Wall;++Queries;
            if(!World->LineTraceSingleByChannel(Wall,Origin,Origin+FRotator(0,A*10.f,0).Vector()*5000,
                JapanGameplayCollision::Channel,Q)||Wall.Distance<1600||FMath::Abs(Wall.ImpactNormal.Z)>.2||
                !JapanGameplayCollision::IsFixed(Wall.GetComponent()))continue;
            const FVector Normal=Wall.ImpactNormal.GetSafeNormal2D(),Back=Wall.ImpactPoint+Normal*1800;
            FHitResult First;++Queries;if(!Ground(Back,First))continue;
            bool Flat=true;int32 Samples=0;
            for(int32 I=0;I<9&&Flat;++I)
            {
                FHitResult Foot;++Queries;++Samples;
                Flat=Ground(Back-Normal*(I*180.f),Foot)&&FMath::Abs(Foot.ImpactPoint.Z-First.ImpactPoint.Z)<3.;
            }
            if(!Flat)continue;
            const FVector Side(-Normal.Y,Normal.X,0);
            for(float Width:{-75.f,0.f,75.f})
            {
                FHitResult Ahead;++Queries;
                const FVector From(Back.X+Side.X*Width,Back.Y+Side.Y*Width,First.ImpactPoint.Z+40);
                if(!World->LineTraceSingleByChannel(Ahead,From,From-Normal*1850,JapanGameplayCollision::Channel,Q)||
                    Ahead.GetComponent()!=Wall.GetComponent()||Ahead.Distance<1650||FVector::DotProduct(Ahead.ImpactNormal,Normal)<.9f)
                {Flat=false;break;}
            }
            if(!Flat)continue;
            Start=First.ImpactPoint+FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3);
            Yaw=(-Normal).Rotation().Yaw;Evidence=MakeShared<FJsonObject>();
            Evidence->SetStringField(TEXT("owner_class"),Wall.GetActor()->GetClass()->GetName());
            const auto* Mesh=Cast<UStaticMeshComponent>(Wall.GetComponent());
            Evidence->SetStringField(TEXT("mesh"),Mesh&&Mesh->GetStaticMesh()?Mesh->GetStaticMesh()->GetPathName():FString());
            Evidence->SetNumberField(TEXT("item"),Wall.Item);Evidence->SetNumberField(TEXT("queries"),Queries);
            Evidence->SetNumberField(TEXT("flat_samples"),Samples);Evidence->SetNumberField(TEXT("approach_cm"),1800);
            Evidence->SetNumberField(TEXT("x"),Start.X);Evidence->SetNumberField(TEXT("y"),Start.Y);Evidence->SetNumberField(TEXT("z"),Start.Z);
            Evidence->SetNumberField(TEXT("yaw"),Yaw);Evidence->SetBoolField(TEXT("authored_fixed"),true);
            return true;
        }
    }
    return false;
}
#else
bool JapanVehicleQASite::Crash(AWandererCharacter*,FVector&,float&,TSharedPtr<FJsonObject>&){return false;}
#endif
