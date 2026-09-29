#include "HidamariReview.h"
#include "AtelierData.h"
#include "JapanWorld.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Components/StaticMeshComponent.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

bool ValidateHidamari(UWorld* World,AActor* Player,const FString& Directory)
{
    FString Text;TSharedPtr<FJsonObject> City;
    if(!FFileHelper::LoadFileToString(Text,*(AtelierDataPath(TEXT("hidamari/city.json")))) ||
       !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),City)) return false;
    auto P=[](const TSharedPtr<FJsonValue>& V){const auto& A=V->AsArray();return AJapanWorld::ToUE(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());};
    FCollisionQueryParams Params(SCENE_QUERY_STAT(HidamariAudit),false,Player);
    TArray<TSharedPtr<FJsonValue>> Errors;int32 Samples=0,Sweeps=0;double MaxError=0;
    for(const auto& Road:City->GetArrayField(TEXT("roads")))
    {
        const auto& Points=Road->AsArray();
        for(int32 I=0;I+2<Points.Num();I+=2)
        {
            const FVector A=P(Points[I]),B=P(Points[I+2]);
            const FVector Side=FVector::CrossProduct((B-A).GetSafeNormal2D(),FVector::UpVector);
            for(double Offset:{-250.,0.,250.})
            {
                const FVector Q=A+Side*Offset;FHitResult Hit;
                const bool Ground=World->LineTraceSingleByChannel(Hit,Q+FVector(0,0,250),Q-FVector(0,0,300),ECC_Visibility,Params);
                const double Error=Ground?FMath::Abs(Hit.ImpactPoint.Z-(A.Z+6.5)):1000.;
                ++Samples;MaxError=FMath::Max(MaxError,Error);
                if(!Ground || Error>25.) Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("ground %.1f,%.1f offset %.0f error %.1f"),A.X,A.Y,Offset,Error)));
                if(World->SweepSingleByChannel(Hit,Q+FVector(0,0,110),B+Side*Offset+FVector(0,0,110),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(24,78),Params))
                    Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("blocked %.1f,%.1f offset %.0f"),A.X,A.Y,Offset)));
                ++Sweeps;
            }
        }
    }
    // The road audit cannot detect floating kit forecourts or a station porch
    // hidden inside a stale collider. Probe their actual pawn support separately.
    int32 KitPads=0,KitGroundChecks=0,KitSweeps=0,KitEntranceGroundChecks=0,KitEntranceSweeps=0;
    double MaxKitError=0.;int32 KitCornerChecks=0,PropPads=0;
    UStaticMeshComponent* Terrain=nullptr;
    UStaticMeshComponent* Park=nullptr;int32 ShoreFootingChecks=0;
    for(TActorIterator<AJapanWorld> It(World);It;++It)
    {
        TArray<UStaticMeshComponent*> Components;It->GetComponents(Components);
        for(auto* Component:Components)
            if(Component->GetStaticMesh())
            {
                if(Component->GetStaticMesh()->GetName()==TEXT("HD_Terrain")) Terrain=Component;
                if(Component->GetStaticMesh()->GetName()==TEXT("HD_Park")) Park=Component;
            }
    }
    auto KitGround=[&](const FString& Label,const FVector& Q,bool bEntrance=false,bool bTerrainOnly=false,bool bShoreFooting=false)
    {
        FHitResult Hit;++KitGroundChecks;
        if(bEntrance) ++KitEntranceGroundChecks;
        FCollisionQueryParams TerrainParams=Params;TerrainParams.bTraceComplex=true;
        bool Ground=bTerrainOnly
            ? (Terrain && Terrain->LineTraceComponent(Hit,Q+FVector(0,0,120),Q-FVector(0,0,150),TerrainParams))
            : World->LineTraceSingleByChannel(Hit,Q+FVector(0,0,120),Q-FVector(0,0,150),ECC_Pawn,Params);
        // A declared shore footing replaces excavated terrain under one
        // pavilion corner. Trace its actual park mesh; roofs, props and water
        // cannot satisfy this fallback, and the same 8 cm height limit applies.
        if(bShoreFooting)
        {
            ++ShoreFootingChecks;FHitResult ShoreHit;
            if(Park && Park->LineTraceComponent(ShoreHit,Q+FVector(0,0,120),Q-FVector(0,0,150),TerrainParams) &&
               (!Ground || FMath::Abs(ShoreHit.ImpactPoint.Z-Q.Z)<FMath::Abs(Hit.ImpactPoint.Z-Q.Z)))
            {Hit=ShoreHit;Ground=true;}
        }
        const double Error=Ground?FMath::Abs(Hit.ImpactPoint.Z-Q.Z):1000.;
        MaxKitError=FMath::Max(MaxKitError,Error);
        // Road paving is 4.5--6.5 cm proud; pad paving and porch nosings are
        // 1--3 cm proud. Eight cm catches a missing 12 cm terrace step too.
        if(!Ground || Error>8.)
            Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("kit support %s at %.1f,%.1f expected %.1f error %.1f"),*Label,Q.X,Q.Y,Q.Z,Error)));
    };
    auto KitSweep=[&](const FString& Label,const FVector& A,const FVector& B,bool bEntrance=false)
    {
        ++KitSweeps;if(bEntrance) ++KitEntranceSweeps;
        FHitResult Hit;
        // Same capsule width/height as the road audit, with only 12 cm of
        // foot clearance: enough for paving, not enough to ignore a bench.
        if(World->SweepSingleByChannel(Hit,A+FVector(0,0,90),B+FVector(0,0,90),FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(24,78),Params))
            Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("kit approach blocked %s at %.1f,%.1f"),*Label,Hit.Location.X,Hit.Location.Y)));
    };
    int32 ExpectedKitPads=0;
    for(const auto& Building:City->GetArrayField(TEXT("buildings")))
    {
        bool bSupported=false;
        if(Building->AsObject()->TryGetBoolField(TEXT("terrain_pad"),bSupported) && bSupported) ++ExpectedKitPads;
    }
    const TArray<TSharedPtr<FJsonValue>>* Pads=nullptr;
    bool bStationChecked=false,bShrineChecked=false;
    if(City->TryGetArrayField(TEXT("terrain_pads"),Pads))
    for(const auto& Pad:*Pads)
    {
        const TSharedPtr<FJsonObject> O=Pad->AsObject();
        FString Asset,Group;double X,Y,Z,Yaw,Front,Back,HalfWidth;
        if(!O.IsValid() || !O->TryGetStringField(TEXT("asset"),Asset) ||
           !O->TryGetNumberField(TEXT("x"),X) || !O->TryGetNumberField(TEXT("y"),Y) ||
           !O->TryGetNumberField(TEXT("z"),Z) || !O->TryGetNumberField(TEXT("yaw"),Yaw) ||
           !O->TryGetNumberField(TEXT("front"),Front) || !O->TryGetNumberField(TEXT("back"),Back) || !O->TryGetNumberField(TEXT("half_width"),HalfWidth))
        {
            Errors.Add(MakeShared<FJsonValueString>(TEXT("kit pad metadata incomplete")));
            continue;
        }
        ++KitPads;O->TryGetStringField(TEXT("group"),Group);if(Group==TEXT("props")) ++PropPads;
        const double Angle=FMath::DegreesToRadians(Yaw),C=FMath::Cos(Angle),S=FMath::Sin(Angle);
        auto Local=[&](double LX,double LY,double LZ=0.)
        {
            return AJapanWorld::ToUE(X+LX*C-LY*S,Y+LX*S+LY*C,Z+LZ);
        };
        const FString Label=FString::Printf(TEXT("%s lot %.3f,%.3f"),*Asset,X,Y);
        // A narrow strip just outside the attached-prop envelope; do not demand
        // that the entire storefront be empty (benches/displays are intentional).
        const double Span=FMath::Min(6.,FMath::Max(.25,HalfWidth-.5));
        // Arcade pad fronts end at the wall/street boundary; their attached
        // displays project another 1.3 m. Keep approach tests ahead of them.
        const double Approach=Group==TEXT("arcade")?Front-1.6:Front-.2;
        for(double LX:{-Span,0.,Span}) KitGround(Label,Local(LX,Approach));
        const double SweepHalf=FMath::Min(.6,Span);
        KitSweep(Label,Local(-SweepHalf,Approach),Local(SweepHalf,Approach));
        // Trace the terrain component itself at all four pad corners. A shrine
        // stair or adjoining shop wall can legitimately cover a support corner;
        // it must not conceal missing ground or make a support probe hit a roof.
        for(double LX:{-HalfWidth,HalfWidth}) for(double LY:{Front,Back})
        {
            const bool ShoreCorner=Asset==TEXT("HD_Pavilion") && FMath::Abs(X-985.)<.01 &&
                FMath::Abs(Y-265.)<.01 && LX>0. && LY>0.;
            KitGround(Label+TEXT(" footprint corner"),Local(LX,LY),false,true,ShoreCorner);++KitCornerChecks;
        }
        if(Asset==TEXT("HD_Pavilion") && FMath::Abs(X-985.)<.01 && FMath::Abs(Y-265.)<.01)
        {
            // All four edges of the real 25 cm square post must also have
            // masonry support, not only the more generous lot rectangle.
            for(double LX:{4.875,5.125}) for(double LY:{3.875,4.125})
                KitGround(Label+TEXT(" shore post footing"),Local(LX,LY),false,true,true);
        }

        if(Asset==TEXT("HD_Station"))
        {
            bStationChecked=true;
            // Centre aisle between porch columns x=+/-2.9 and door pots x=+/-2.
            // Stop before the closed front wall at y=-7.5; the station is scenery.
            for(double LY:{Front,-10.5,-9.5,-8.1})
                KitGround(Label+TEXT(" centre porch"),Local(0,LY),true);
            KitSweep(Label+TEXT(" centre porch"),Local(0,Front),Local(0,-8.1),true);
        }
        else if(Asset==TEXT("HD_Shrine"))
        {
            bShrineChecked=true;
            // The restored torii posts are x=+/-4. Centreline remains clear of
            // the basin and stone lantern, ending before the terrace steps.
            for(double LY:{Front,-8.,-6.,-4.5})
                KitGround(Label+TEXT(" torii approach"),Local(0,LY),true);
            KitSweep(Label+TEXT(" through torii"),Local(0,Front),Local(0,-4.5),true);
            // Check each authored landing/riser's actual collider. A straight
            // capsule sweep up these stairs would falsely treat walkable risers
            // as walls, so the clearance sweep above stays on the level approach.
            KitGround(Label+TEXT(" lower terrace"),Local(0,-4.09,.12),true);
            KitGround(Label+TEXT(" upper terrace"),Local(0,-3.71,.22),true);
            KitGround(Label+TEXT(" terrace landing"),Local(0,-3.15,.30),true);
            for(int32 K=0;K<5;++K)
                KitGround(Label+FString::Printf(TEXT(" stair %d"),K),Local(0,-1.05-.3*(K+.5),1.23-.155*(K+1)),true);
        }
    }
    if(ExpectedKitPads<=0 || KitPads!=ExpectedKitPads+PropPads || !bStationChecked || !bShrineChecked)
        Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("kit audit coverage: %d pads / %d supported buildings, station %d shrine %d; regenerate city.json"),KitPads,ExpectedKitPads,bStationChecked,bShrineChecked)));
    int32 NorthChecks=0;
    const TArray<TSharedPtr<FJsonValue>>* North=nullptr;
    if(City->TryGetArrayField(TEXT("north_trail"),North))
    {
        for(const auto& Point:*North)
        {
            const FVector Q=P(Point);FHitResult Hit;++NorthChecks;
            const bool Ground=World->LineTraceSingleByChannel(Hit,Q+FVector(0,0,150),Q-FVector(0,0,150),ECC_Pawn,Params);
            if(!Ground || FMath::Abs(Hit.ImpactPoint.Z-Q.Z)>20.)
                Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("north trail gap %.1f,%.1f"),Q.X,Q.Y)));
        }
    }
    int32 BridgeChecks=0;
    for(double X=983.;X<=1077.;X+=.5)
    {
        const double T=FMath::Clamp((X-984.)/92.,0.,1.);
        const double Z=30.925+1.5*FMath::Sin(PI*T);
        for(double Y:{283.,284.,285.})
        {
            const FVector Q=AJapanWorld::ToUE(X,Y,Z);FHitResult Hit;++BridgeChecks;
            const bool Ground=World->LineTraceSingleByChannel(Hit,Q+FVector(0,0,100),Q-FVector(0,0,100),ECC_Pawn,Params);
            if(!Ground || FMath::Abs(Hit.ImpactPoint.Z-Q.Z)>25.)
                Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("bridge gap %.1f,%.1f"),X,Y)));
        }
    }
    int32 WaterChecks=0;
    for(const auto& Probe:City->GetArrayField(TEXT("water_probes")))
    {
        const FVector Q=P(Probe);FHitResult Hit;++WaterChecks;
        if(World->LineTraceSingleByChannel(Hit,Q+FVector(0,0,10),Q-FVector(0,0,10),ECC_Pawn,Params))
            Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("solid water %.1f,%.1f"),Q.X,Q.Y)));
    }
    auto Result=MakeShared<FJsonObject>();Result->SetNumberField(TEXT("north_ground_samples"),NorthChecks);Result->SetNumberField(TEXT("ground_samples"),Samples);Result->SetNumberField(TEXT("capsule_sweeps"),Sweeps);Result->SetNumberField(TEXT("bridge_ground_samples"),BridgeChecks);Result->SetNumberField(TEXT("water_checks"),WaterChecks);Result->SetNumberField(TEXT("max_ground_error_cm"),MaxError);Result->SetArrayField(TEXT("errors"),Errors);Result->SetBoolField(TEXT("passed"),Errors.IsEmpty());
    Result->SetNumberField(TEXT("kit_pad_checks"),KitPads);
    Result->SetNumberField(TEXT("kit_footprint_corner_samples"),KitCornerChecks);
    Result->SetNumberField(TEXT("shore_footing_samples"),ShoreFootingChecks);
    Result->SetNumberField(TEXT("park_prop_pad_checks"),PropPads);
    Result->SetNumberField(TEXT("kit_ground_samples"),KitGroundChecks);
    Result->SetNumberField(TEXT("kit_capsule_sweeps"),KitSweeps);
    Result->SetNumberField(TEXT("kit_entrance_ground_samples"),KitEntranceGroundChecks);
    Result->SetNumberField(TEXT("kit_entrance_sweeps"),KitEntranceSweeps);
    Result->SetNumberField(TEXT("max_kit_ground_error_cm"),MaxKitError);
    FString Output;FJsonSerializer::Serialize(Result,TJsonWriterFactory<>::Create(&Output));FFileHelper::SaveStringToFile(Output,*(Directory/TEXT("hidamari-physics.json")));
    UE_LOG(LogTemp,Display,TEXT("HIDAMARI PHYSICS: %d samples, %d sweeps, %d errors"),Samples,Sweeps,Errors.Num());return Errors.IsEmpty();
}
