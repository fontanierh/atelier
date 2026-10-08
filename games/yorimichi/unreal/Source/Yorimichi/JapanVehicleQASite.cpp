#include "JapanVehicleQASite.h"
#if !UE_BUILD_SHIPPING
#include "WandererCharacter.h"
#include "JapanGameplayCollision.h"
#include "JapanWorld.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"

bool JapanVehicleQASite::Circuit(AWandererCharacter* Rider,bool Guest,FVector& Start,TSharedPtr<FJsonObject>& Evidence)
{
    // Two separate disks in the existing Hippodrome infield. The probe never
    // creates a floor or changes an actor's collision to make the route pass.
    UWorld* World=Rider->GetWorld();
    const FVector Centre=AJapanWorld::ToUE(Guest?585.:545.,535.,0.);
    auto Q=JapanGameplayCollision::Query(World,SCENE_QUERY_STAT(VehicleQACircuit),false);Q.AddIgnoredActor(Rider);
    Evidence=MakeShared<FJsonObject>();
    Evidence->SetNumberField(TEXT("x"),Centre.X);Evidence->SetNumberField(TEXT("y"),Centre.Y);
    Evidence->SetNumberField(TEXT("radius_cm"),2400);Evidence->SetNumberField(TEXT("limit_cm"),2200);
    Evidence->SetNumberField(TEXT("grid_cm"),200);Evidence->SetBoolField(TEXT("clear"),false);
    int32 Samples=0,Blocked=0;double Low=UE_BIG_NUMBER,High=-UE_BIG_NUMBER,MinNormal=1.;
    FString Asset;
    for(int32 X=-2400;X<=2400;X+=200)for(int32 Y=-2400;Y<=2400;Y+=200)
    {
        if(X*X+Y*Y>2400*2400)continue;
        const FVector At=Centre+FVector(X,Y,0);FHitResult Floor;
        auto FailedCell=[&](const TCHAR* Reason)
        {
            Evidence->SetNumberField(TEXT("failed_x"),At.X);Evidence->SetNumberField(TEXT("failed_y"),At.Y);
            Evidence->SetStringField(TEXT("reason"),Reason);
        };
        if(!World->LineTraceSingleByChannel(Floor,At+FVector(0,0,20000),At-FVector(0,0,2000),JapanGameplayCollision::Channel,Q)||
            !JapanGameplayCollision::IsFixed(Floor.GetComponent()))
        {FailedCell(TEXT("missing fixed ground"));return false;}
        const auto* Mesh=Cast<UStaticMeshComponent>(Floor.GetComponent());
        const FString HitAsset=Mesh&&Mesh->GetStaticMesh()?Mesh->GetStaticMesh()->GetPathName():FString();
        if(HitAsset.IsEmpty()||(!Asset.IsEmpty()&&Asset!=HitAsset))
        {FailedCell(TEXT("ground asset changed"));Evidence->SetStringField(TEXT("failed_mesh"),HitAsset);return false;}
        Asset=HitAsset;++Samples;Low=FMath::Min(Low,Floor.ImpactPoint.Z);High=FMath::Max(High,Floor.ImpactPoint.Z);
        MinNormal=FMath::Min(MinNormal,double(Floor.ImpactNormal.Z));
        if(High-Low>3.||Floor.ImpactNormal.Z<.98)FailedCell(TEXT("ground is not level"));
        // Adjacent 2m cells meet; each tests the whole body-height volume, not
        // only a ray that could miss an obstacle between floor samples.
        if(World->OverlapBlockingTestByChannel(Floor.ImpactPoint+FVector(0,0,100),FQuat::Identity,
            JapanGameplayCollision::Channel,FCollisionShape::MakeBox(FVector(100,100,95)),Q))
        {++Blocked;FailedCell(TEXT("body cell obstructed"));}
    }
    Evidence->SetNumberField(TEXT("ground_samples"),Samples);Evidence->SetNumberField(TEXT("blocked_cells"),Blocked);
    Evidence->SetNumberField(TEXT("height_range_cm"),High-Low);Evidence->SetNumberField(TEXT("min_normal_z"),MinNormal);
    Evidence->SetStringField(TEXT("mesh"),Asset);Evidence->SetNumberField(TEXT("z"),High);
    const bool Clear=Samples==441&&Blocked==0&&High-Low<=3.&&MinNormal>=.98;
    Evidence->SetBoolField(TEXT("clear"),Clear);
    // Centre the measured sprint/skid route inside the unchanged checked disk.
    Start=FVector(Centre.X-1200,Centre.Y-870.,High+3.);
    return Clear;
}

bool JapanVehicleQASite::Crash(AWandererCharacter* Rider,FVector& Start,float& Yaw,TSharedPtr<FJsonObject>& Evidence)
{
    UWorld* World=Rider->GetWorld();
    auto Q=JapanGameplayCollision::Query(World,SCENE_QUERY_STAT(VehicleQASite),false);Q.AddIgnoredActor(Rider);
    const FVector Home=Rider->GetActorLocation();
    Evidence=MakeShared<FJsonObject>();Evidence->SetBoolField(TEXT("authored_fixed"),false);
    // This map's supported ground lies inside -20m..200m. Anything outside
    // that range fails the fixture instead of accepting an untraced surface.
    auto Ground=[&](FVector At,FHitResult& Hit)
    {return World->LineTraceSingleByChannel(Hit,FVector(At.X,At.Y,20000),FVector(At.X,At.Y,-2000),JapanGameplayCollision::Channel,Q)&&
        Hit.ImpactNormal.Z>.98&&JapanGameplayCollision::IsFixed(Hit.GetComponent());};
    // The coastal spawn is sloped. Search the existing flat Hippodrome infield
    // and stable yard as well; every candidate still has to pass the same wall,
    // 18m approach, ground and width checks. No geometry is created or altered.
    const TArray<FVector> Centres={Home,AJapanWorld::ToUE(600.,535.,0.),AJapanWorld::ToUE(715.,520.,0.)};
    int32 Queries=0,Regions=0,Origins=0,GroundRejected=0,WallCandidates=0,ApproachRejected=0,WidthRejected=0,ObserverRejected=0;
    auto Counters=[&]()
    {
        Evidence->SetNumberField(TEXT("queries"),Queries);Evidence->SetNumberField(TEXT("regions"),Regions);
        Evidence->SetNumberField(TEXT("origins"),Origins);Evidence->SetNumberField(TEXT("ground_rejected"),GroundRejected);
        Evidence->SetNumberField(TEXT("wall_candidates"),WallCandidates);Evidence->SetNumberField(TEXT("approach_rejected"),ApproachRejected);
        Evidence->SetNumberField(TEXT("width_rejected"),WidthRejected);
        Evidence->SetNumberField(TEXT("observer_rejected"),ObserverRejected);
    };
    auto Rejected=[&](const TCHAR* Reason,const FVector& At)
    {
        Evidence->SetStringField(TEXT("last_rejection"),Reason);
        Evidence->SetNumberField(TEXT("last_x"),At.X);Evidence->SetNumberField(TEXT("last_y"),At.Y);
        Evidence->SetNumberField(TEXT("last_z"),At.Z);
    };
    for(const FVector& Centre:Centres)
    {
        ++Regions;
        for(int32 X=-2;X<=2;++X)for(int32 Y=-2;Y<=2;++Y)
        {
            const FVector At=Centre+FVector(X*1500.f,Y*1500.f,0);
            FHitResult Floor;++Queries;++Origins;
            if(!Ground(At,Floor)){++GroundRejected;Rejected(TEXT("origin has no level fixed ground"),At);continue;}
            const FVector Origin=Floor.ImpactPoint+FVector(0,0,40);
            for(int32 A=0;A<36;++A)
            {
                FHitResult Wall;++Queries;
                if(!World->LineTraceSingleByChannel(Wall,Origin,Origin+FRotator(0,A*10.f,0).Vector()*5000,
                    JapanGameplayCollision::Channel,Q)||Wall.Distance<1600||FMath::Abs(Wall.ImpactNormal.Z)>.2||
                    !JapanGameplayCollision::IsFixed(Wall.GetComponent()))continue;
                ++WallCandidates;
                const FVector Normal=Wall.ImpactNormal.GetSafeNormal2D(),Back=Wall.ImpactPoint+Normal*1800;
                FHitResult First;++Queries;
                if(!Ground(Back,First)){++ApproachRejected;Rejected(TEXT("approach has no level fixed ground"),Back);continue;}
                bool Flat=true;int32 Samples=0;
                for(int32 I=0;I<9&&Flat;++I)
                {
                    FHitResult Foot;++Queries;++Samples;
                    Flat=Ground(Back-Normal*(I*180.f),Foot)&&FMath::Abs(Foot.ImpactPoint.Z-First.ImpactPoint.Z)<3.;
                }
                if(!Flat){++ApproachRejected;Rejected(TEXT("approach changes height"),Back);continue;}
                const FVector Side(-Normal.Y,Normal.X,0);
                for(float Width:{-75.f,0.f,75.f})
                {
                    FHitResult Ahead;++Queries;
                    const FVector From(Back.X+Side.X*Width,Back.Y+Side.Y*Width,First.ImpactPoint.Z+40);
                    if(!World->LineTraceSingleByChannel(Ahead,From,From-Normal*1850,JapanGameplayCollision::Channel,Q)||
                        Ahead.GetComponent()!=Wall.GetComponent()||Ahead.Item!=Wall.Item||Ahead.Distance<1650||FVector::DotProduct(Ahead.ImpactNormal,Normal)<.9f)
                    {Flat=false;break;}
                }
                if(!Flat){++WidthRejected;Rejected(TEXT("approach width obstructed or wall identity changed"),Back);continue;}
                // Keep the host observer close enough to remain relevant, but
                // twenty metres beside the approach so it cannot trigger the ray.
                FVector ObserverStart;bool ObserverClear=false;
                const float HalfHeight=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
                const float Radius=Rider->GetCapsuleComponent()->GetScaledCapsuleRadius();
                for(float Offset:{2000.f,-2000.f})
                {
                    FHitResult ObserverFloor;++Queries;
                    if(!Ground(Back+Side*Offset,ObserverFloor)||FMath::Abs(ObserverFloor.ImpactPoint.Z-First.ImpactPoint.Z)>=3.)continue;
                    ObserverStart=ObserverFloor.ImpactPoint+FVector(0,0,HalfHeight+3);
                    ++Queries;
                    if(!World->OverlapBlockingTestByChannel(ObserverStart,FQuat::Identity,JapanGameplayCollision::Channel,
                        FCollisionShape::MakeCapsule(Radius,HalfHeight),Q)){ObserverClear=true;break;}
                }
                if(!ObserverClear){++ObserverRejected;Rejected(TEXT("no supported clear observer position"),Back);continue;}
                Start=First.ImpactPoint+FVector(0,0,Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+3);
                Yaw=(-Normal).Rotation().Yaw;Counters();
                Evidence->SetBoolField(TEXT("observer_clear"),true);
                Evidence->SetNumberField(TEXT("observer_x"),ObserverStart.X);Evidence->SetNumberField(TEXT("observer_y"),ObserverStart.Y);
                Evidence->SetNumberField(TEXT("observer_z"),ObserverStart.Z);
                Evidence->SetStringField(TEXT("owner_class"),Wall.GetActor()->GetClass()->GetName());
                const auto* Mesh=Cast<UStaticMeshComponent>(Wall.GetComponent());
                Evidence->SetStringField(TEXT("mesh"),Mesh&&Mesh->GetStaticMesh()?Mesh->GetStaticMesh()->GetPathName():FString());
                Evidence->SetNumberField(TEXT("item"),Wall.Item);
                Evidence->SetNumberField(TEXT("flat_samples"),Samples);Evidence->SetNumberField(TEXT("approach_cm"),1800);
                Evidence->SetNumberField(TEXT("x"),Start.X);Evidence->SetNumberField(TEXT("y"),Start.Y);Evidence->SetNumberField(TEXT("z"),Start.Z);
                Evidence->SetNumberField(TEXT("yaw"),Yaw);Evidence->SetBoolField(TEXT("authored_fixed"),true);
                return true;
            }
        }
    }
    Counters();
    return false;
}
#else
bool JapanVehicleQASite::Circuit(AWandererCharacter*,bool,FVector&,TSharedPtr<FJsonObject>&){return false;}
bool JapanVehicleQASite::Crash(AWandererCharacter*,FVector&,float&,TSharedPtr<FJsonObject>&){return false;}
#endif
