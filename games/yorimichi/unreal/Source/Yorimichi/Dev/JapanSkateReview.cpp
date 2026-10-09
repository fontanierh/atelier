#include "WandererCharacter.h"
#include "AtelierExit.h"
#include "AtelierData.h"
#include "Camera/CameraComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "InputKeyEventArgs.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "JapanWorld.h"
#include "Framework/Application/SlateApplication.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SkateComponent.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Containers/Ticker.h"
#include "HAL/IConsoleManager.h"

// A scripted rider follows an authored road (docs/DESKTOP_PERFORMANCE.md: the benchmark and trailer routes): the steering
// that keeps it on the line, patrolling back and forth so long runs keep moving.
float AWandererCharacter::GetRoadSteering()
{
    if (SkateReviewRoad.IsEmpty())
    {
        if (const TSharedPtr<FJsonObject> Json=AtelierReadJson(AtelierDataPath(TEXT("world.json"))))
        {
            const TArray<TSharedPtr<FJsonValue>>* Route = &Json->GetArrayField(TEXT("road"));
            FString Requested;
            FParse::Value(FCommandLine::Get(),TEXT("reviewroute="),Requested);
            if (Requested == TEXT("village") || Requested == TEXT("village_loop"))
            {
                const TSharedPtr<FJsonObject>* Village = nullptr;
                if (!Json->TryGetObjectField(TEXT("village"),Village))
                { AtelierRequestExit(2); return 0.f; }
                const auto& Paths = (*Village)->GetArrayField(TEXT("paths"));
                const int32 Index = Requested == TEXT("village_loop") ? 1 : 0;
                if (!Paths.IsValidIndex(Index))
                { AtelierRequestExit(2); return 0.f; }
                Route = &Paths[Index]->AsArray();
            }
            if(Requested==TEXT("mega"))
            {
                const TSharedPtr<FJsonObject>* Mega=nullptr;
                if(!Json->TryGetObjectField(TEXT("mega"),Mega)){AtelierRequestExit(2);return 0.f;}
                Route=&(*Mega)->GetArrayField(TEXT("trail"));
            }
            TSharedPtr<FJsonObject> CityRoute;
            if(Requested==TEXT("park") || Requested==TEXT("north") || Requested==TEXT("hidamari") || Requested==TEXT("arcade") || Requested==TEXT("plaza") || Requested==TEXT("plaza_steps") || Requested==TEXT("harbor") || Requested==TEXT("harbor_pier"))
            {
                if(!(CityRoute=AtelierReadJson(AtelierDataPath(TEXT("hidamari/city.json")))))
                {AtelierRequestExit(2);return 0.f;}
                Route=&CityRoute->GetArrayField(Requested==TEXT("park") ? TEXT("park_route") : Requested==TEXT("north") ? TEXT("north_trail") : Requested==TEXT("harbor") ? TEXT("harbor_route") : Requested==TEXT("harbor_pier") ? TEXT("harbor_pier_route") : Requested==TEXT("arcade") ? TEXT("arcade_route") : Requested==TEXT("plaza") ? TEXT("plaza_route") : Requested==TEXT("plaza_steps") ? TEXT("plaza_steps") : TEXT("review_route"));
            }
            for (const auto& Value : *Route)
            {
                const auto& XYZ = Value->AsArray();
                SkateReviewRoad.Add(AJapanWorld::ToUE(XYZ[0]->AsNumber(),XYZ[1]->AsNumber(),XYZ[2]->AsNumber()));
            }
        }
    }
    if (SkateReviewRoad.Num() < 10) return 0.f;
    int32 Closest = 0; double Best = DBL_MAX;
    for (int32 I = 0; I < SkateReviewRoad.Num(); ++I)
    {
        const double Distance = FVector::DistSquared2D(GetActorLocation(),SkateReviewRoad[I]);
        if (Distance < Best) { Best = Distance; Closest = I; }
    }
    SkateReviewIndex = Closest;
    // Every authored review route is an open path whose ends are hundreds of metres apart, so
    // steering at a clamped look-ahead parks the rider on the final waypoint: a ten-minute run then
    // measures an idle camera. Patrol instead, turning around a few samples short of either end,
    // which is ordinary skate steering rather than a teleport.
    const int32 Last = SkateReviewRoad.Num()-1;
    if (SkateReviewDirection > 0 && Closest >= Last-8) { SkateReviewDirection = -1; ++SkateReviewTurns; }
    else if (SkateReviewDirection < 0 && Closest <= 8) { SkateReviewDirection = 1; ++SkateReviewTurns; }
    // Stall recovery, for the harness only. A scripted rider that meets a planter or a step keeps
    // pushing into it, and a long run then measures a parked camera. If it has not moved 1.5 m in
    // 1.2 s, turn it around and put it back on the route eight samples behind: a logged, counted
    // transfer, not a silent teleport, and never applied to a player-driven session.
    const double Now = GetWorld()->GetTimeSeconds();
    const FVector Here = GetActorLocation();
    if (SkateReviewStuckSince < 0. || FVector::DistSquared2D(Here,SkateReviewStuckAt) > 150.*150.)
    {
        SkateReviewStuckAt = Here;
        SkateReviewStuckSince = Now;
    }
    else if (Now-SkateReviewStuckSince > 1.2)
    {
        ++SkateReviewRecoveries;
        SkateReviewDirection = -SkateReviewDirection;
        const int32 Back = FMath::Clamp(Closest+8*SkateReviewDirection,0,Last);
        const FVector Ahead = SkateReviewRoad[FMath::Clamp(Back+6*SkateReviewDirection,0,Last)];
        SetActorLocation(SkateReviewRoad[Back]+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+8),
                         false,nullptr,ETeleportType::TeleportPhysics);
        SetActorRotation((Ahead-SkateReviewRoad[Back]).Rotation());
        GetCharacterMovement()->StopMovementImmediately();
        SkateReviewStuckAt = GetActorLocation();
        SkateReviewStuckSince = Now;
        UE_LOG(LogTemp,Display,TEXT("ROUTE RECOVERY {\"time\": %.2f, \"index\": %d, \"stuck_x\": %.1f, \"stuck_y\": %.1f}"),
               Now,Back,Here.X,Here.Y);
    }
    const FVector Target = SkateReviewRoad[FMath::Clamp(Closest+6*SkateReviewDirection,0,Last)];
    const float Heading = (Target-GetActorLocation()).Rotation().Yaw;
    return FMath::Clamp(FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,Heading)*.065f,-1.f,1.f);
}

// The skate ground check (packaged QA, no Python): on the authored road at two samples, and on the grass 20 or 30 m beside
// each, the rider is put on the board and launched, then thrown off it. A ride whose height over the ground drops more than
// 50 cm below where it started has gone through it; a bail or get-up whose deepest skin is over 2 cm under the ground has
// sunk into it (skate.RideSkinCheck). Readings of 20 cm and more are counted apart: the measure's probe
// starts 30 cm above each vertex, so the board or a body part above it reads that deep. A check that cannot measure fails:
// a road index without both its street and grass spot, a ride frame with no ground under it, a bail with no lying or no
// get-up reading. One SKATE GROUND line per spot, then the summary line, which is the result; `quit` then exits and
// asks for status 1 on a failure (Windows and Linux pass it on, macOS exits with 0 regardless).
// Usage: japan.SkateGroundCheck [road indices...] [quit]
namespace
{
    struct FSkateGroundCheck
    {
        struct FSpot { FString Name; FVector Ground; float Yaw; };
        TWeakObjectPtr<AWandererCharacter> Player; TArray<FSpot> Spots; bool bQuit=false;
        int32 Spot=0,Phase=-1,Failed=0,Occluded=0,Samples=0,Missed=0; float Time=0,StartRel=0,Drop=0,Skin[2]={-1e9f,-1e9f}; bool bBailed=false;
    };

    // The ground under a point: the first hit below FromZ that is not foliage (an instanced mesh: trees, bushes), and
    // whether foliage hangs over it.
    bool GroundBelow(UWorld* World,const FVector& At,double FromZ,const AActor* Ignore,FVector& Out,bool* bUnderFoliage=nullptr)
    {
        FCollisionQueryParams Params(TEXT("SkateGroundCheck"),true,Ignore);
        FVector From(At.X,At.Y,FromZ);
        for (int32 Try=0; Try<8; ++Try)
        {
            FHitResult Hit;
            if (!World->LineTraceSingleByChannel(Hit,From,FVector(At.X,At.Y,FromZ-1e5),ECC_Visibility,Params)) return false;
            if (!Cast<UInstancedStaticMeshComponent>(Hit.GetComponent())) { Out=Hit.ImpactPoint; if (bUnderFoliage) *bUnderFoliage=Try>0; return true; }
            Params.AddIgnoredComponent(Hit.GetComponent()); From=Hit.ImpactPoint;
        }
        return false;
    }

    float DebugValue(const FString& Debug,const TCHAR* Key,FString* Word=nullptr)
    {
        FString Value; if (!FParse::Value(*Debug,Key,Value)) return NAN;
        if (Word) *Word=Value;
        return FCString::Atof(*Value);
    }

    void PadBail(APlayerController* PC,bool bOn)
    {
        for (const FKey& K : {EKeys::Gamepad_LeftThumbstick,EKeys::Gamepad_RightThumbstick})
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(K,bOn ? IE_Pressed : IE_Released,bOn ? 1.f : 0.f,1));
        for (const FKey& K : {EKeys::Gamepad_LeftTriggerAxis,EKeys::Gamepad_RightTriggerAxis})
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(K,IE_Axis,bOn ? 1.f : 0.f,1));
    }

    // One tick of the check: phase 0 rides 4 s at 6 m/s, phase 1 rides 0.8 s at 12 m/s, bails for 0.5 s and lies or
    // gets up for 9 s more. False when it is done.
    bool StepSkateGroundCheck(const TSharedRef<FSkateGroundCheck>& C,float Dt)
    {
        AWandererCharacter* P=C->Player.Get(); USkateComponent* Skate=P ? P->GetSkate() : nullptr;
        APlayerController* PC=P ? Cast<APlayerController>(P->GetController()) : nullptr;
        if (!Skate || !PC) { UE_LOG(LogTemp,Error,TEXT("SKATE GROUND check stopped: no player on a board")); return false; }
        const FSkateGroundCheck::FSpot& S=C->Spots[C->Spot];
        if (C->Phase<0 || C->Time<0)
        {
            C->Phase=FMath::Max(C->Phase,0); C->Time=0;
            if (!Skate->PlaceAt(S.Ground,S.Yaw)) { UE_LOG(LogTemp,Error,TEXT("SKATE GROUND %s: the rider could not be placed"),*S.Name); ++C->Failed; C->Phase=2; }
            else { Skate->Launch(FRotator(0,S.Yaw,0).Vector()*(C->Phase==0 ? 600.f : 1200.f)); C->StartRel=NAN; }
        }
        C->Time+=Dt;
        const FString Debug=Skate->GetDebug();
        if (C->Phase==0)
        {
            FVector Ground; const FVector At=P->GetActorLocation();
            if (GroundBelow(P->GetWorld(),At,At.Z+3000,P,Ground))
            {
                const float Rel=At.Z-Ground.Z;
                if (FMath::IsNaN(C->StartRel)) C->StartRel=Rel;
                C->Drop=FMath::Min(C->Drop,Rel-C->StartRel); ++C->Samples;
            }
            else ++C->Missed;   // nothing within 30 m above or below: fallen out of the world, or no ground to measure
            if (C->Time<4) return true;
            const bool bUnmeasured=!C->Samples || C->Missed, bFell=C->Drop<-50;
            C->Failed+=bUnmeasured || bFell;
            UE_LOG(LogTemp,Display,TEXT("SKATE GROUND %s ride: drop %.1f cm (%d frames over the ground, %d with none) %s"),*S.Name,C->Drop,C->Samples,C->Missed,
                bUnmeasured ? TEXT("FAIL (no ground)") : bFell ? TEXT("FAIL") : TEXT("PASS"));
            C->Phase=1; C->Time=-1; return true;
        }
        if (C->Phase==1)
        {
            if (C->Time>=.8f && C->Time-Dt<.8f) PadBail(PC,true);
            if (C->Time>=1.3f && C->Time-Dt<1.3f) PadBail(PC,false);
            FString Phys; DebugValue(Debug,TEXT("phys="),&Phys);
            const float Depth=DebugValue(Debug,TEXT("skin="));
            const int32 Which=Phys==TEXT("Bail") ? 0 : Phys==TEXT("GetUp") ? 1 : -1;
            C->bBailed|=Which==0;
            if (Which>=0 && !FMath::IsNaN(Depth)) { if (Depth>=20) ++C->Occluded; else C->Skin[Which]=FMath::Max(C->Skin[Which],Depth); }
            if (C->Time<10.3f) return true;
            const bool bSunk=C->Skin[0]>2 || C->Skin[1]>2, bUnmeasured=C->Skin[0]<-1e8f || C->Skin[1]<-1e8f;
            C->Failed+=!C->bBailed || bUnmeasured || bSunk;
            auto Shown=[](float Depth){ return Depth<-1e8f ? FString(TEXT("-")) : FString::Printf(TEXT("%.1f"),Depth); };
            UE_LOG(LogTemp,Display,TEXT("SKATE GROUND %s bail: skin %s cm under the ground lying, %s getting up (%d readings of 20+ cm set apart) %s"),
                *S.Name,*Shown(C->Skin[0]),*Shown(C->Skin[1]),C->Occluded,!C->bBailed ? TEXT("FAIL (no bail)") : bUnmeasured ? TEXT("FAIL (no reading)") : bSunk ? TEXT("FAIL") : TEXT("PASS"));
        }
        if (++C->Spot<C->Spots.Num())
        {
            C->Phase=-1; C->Drop=0; C->Skin[0]=C->Skin[1]=-1e9f; C->Occluded=C->Samples=C->Missed=0; C->bBailed=false; return true;
        }
        UE_LOG(LogTemp,Display,TEXT("SKATE GROUND CHECK %s: %d of %d spots failed"),C->Failed ? TEXT("FAIL") : TEXT("PASS"),C->Failed,C->Spots.Num());
        if (C->bQuit) AtelierRequestExit(C->Failed ? 1 : 0);
        return false;
    }
}

namespace
{
    // The spots, once the player stands in the world with a board: from world.json's road at each index, and the grass
    // beside it clear of trees (a body lying under a canopy measures the branches above it). False, with the reason
    // logged, unless every index gives both.
    bool FindSkateGroundSpots(FSkateGroundCheck& C,UWorld* Game,const TArray<int32>& Indices)
    {
        const TArray<TSharedPtr<FJsonValue>>* Road=nullptr;
        const TSharedPtr<FJsonObject> Json=AtelierReadJson(AtelierDataPath(TEXT("world.json")));
        if (!Json || !Json->TryGetArrayField(TEXT("road"),Road)) return false;
        auto Point=[&](int32 I){ const auto& XYZ=(*Road)[I]->AsArray(); return AJapanWorld::ToUE(XYZ[0]->AsNumber(),XYZ[1]->AsNumber(),XYZ[2]->AsNumber()); };
        for (int32 I : Indices)
        {
            if (!Road->IsValidIndex(I) || !Road->IsValidIndex(I+1))
            { UE_LOG(LogTemp,Error,TEXT("SKATE GROUND road index %d is outside world.json's road (%d points)"),I,Road->Num()); return false; }
            const FVector A=Point(I),Dir=(Point(I+1)-A).GetSafeNormal2D(); const float Yaw=Dir.Rotation().Yaw;
            FVector Ground; bool bUnder=true;
            if (!GroundBelow(Game,A,A.Z+5000,C.Player.Get(),Ground))
            { UE_LOG(LogTemp,Error,TEXT("SKATE GROUND street_%d: no ground under the road"),I); return false; }
            C.Spots.Add({FString::Printf(TEXT("street_%d"),I),Ground,Yaw});
            const int32 Found=C.Spots.Num();
            for (const double Side : {2000.,-2000.,3000.,-3000.})
                if (GroundBelow(Game,A+FVector(-Dir.Y,Dir.X,0)*Side,A.Z+5000,C.Player.Get(),Ground,&bUnder) && !bUnder)
                { C.Spots.Add({FString::Printf(TEXT("grass_%d"),I),Ground,Yaw}); break; }
            if (C.Spots.Num()==Found)
            { UE_LOG(LogTemp,Error,TEXT("SKATE GROUND grass_%d: no ground clear of trees 20 or 30 m beside the road"),I); return false; }
        }
        return true;
    }
}

// Run from the command line as -ExecCmds="japan.SkateGroundCheck quit": it waits up to a minute for the player and its
// board, then 10 s more for the world around the start to load, before the first spot.
static FAutoConsoleCommandWithWorldAndArgs SkateGroundCheckCommand(TEXT("japan.SkateGroundCheck"),
    TEXT("Packaged QA: ride and bail on the road and the grass beside it, logging SKATE GROUND lines. Args: [road indices...] [quit]."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        auto C=MakeShared<FSkateGroundCheck>();
        TArray<int32> Indices;
        for (const FString& Arg : Args) { if (Arg==TEXT("quit")) C->bQuit=true; else if (Arg.IsNumeric()) Indices.Add(FCString::Atoi(*Arg)); }
        if (Indices.IsEmpty()) Indices={150,300};
        if (IConsoleVariable* Skin=IConsoleManager::Get().FindConsoleVariable(TEXT("skate.RideSkinCheck"))) Skin->Set(1,ECVF_SetByConsole);
        TWeakObjectPtr<UWorld> World=Game; float Waited=0,Settled=-1;
        FTSTicker::GetCoreTicker().AddTicker(TEXT("SkateGroundCheck"),0.f,[C,World,Indices,Waited,Settled](float Dt) mutable
        {
            if (C->Spots.IsEmpty())
            {
                const APlayerController* PC=World.IsValid() ? World->GetFirstPlayerController() : nullptr;
                C->Player=PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
                Waited+=Dt;
                if (C->Player.IsValid() && C->Player->GetSkate()) Settled=Settled<0 ? 0 : Settled+Dt;
                else if (Waited>60)
                {
                    UE_LOG(LogTemp,Error,TEXT("SKATE GROUND CHECK FAIL: no player with a board after 60 s"));
                    if (C->bQuit) AtelierRequestExit(1);
                    return false;
                }
                if (Settled<10) return true;
                if (!FindSkateGroundSpots(*C,World.Get(),Indices))
                {
                    UE_LOG(LogTemp,Error,TEXT("SKATE GROUND CHECK FAIL: not every street and grass spot was found"));
                    if (C->bQuit) AtelierRequestExit(1);
                    return false;
                }
                UE_LOG(LogTemp,Display,TEXT("SKATE GROUND CHECK: %d spots"),C->Spots.Num());
                return true;
            }
            return StepSkateGroundCheck(C,Dt);
        });
    }));

// The skate pier check (packaged QA, no Python): every rail, ledge and curb in the staged skatepark/park.json must be
// registered with the skate rail subsystem under its id, and a surface with collision must lie on its line: a complex
// trace down at its middle (3 cm inside a ledge's lip) finds a surface within 3 cm of the line's height. This proves the
// fetched pier modules (their meshes, collision and grind lines) made it into the package. One SKATE PIER line per
// line, then the summary line, which is the result; `quit` then exits and asks for status 1 on a failure (macOS exits
// with 0 regardless). Usage: japan.SkatePierCheck [quit]
static FAutoConsoleCommandWithWorldAndArgs SkatePierCheckCommand(TEXT("japan.SkatePierCheck"),
    TEXT("Packaged QA: the skate pier's grind lines are registered and lie on surfaces with collision, logging SKATE PIER lines. Args: [quit]."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        const bool bQuit=Args.Contains(TEXT("quit"));
        TWeakObjectPtr<UWorld> World=Game; float Waited=0;
        FTSTicker::GetCoreTicker().AddTicker(TEXT("SkatePierCheck"),0.f,[World,bQuit,Waited](float Dt) mutable
        {
            auto Finish=[bQuit](int32 Failed){ if (bQuit) AtelierRequestExit(Failed ? 1 : 0); return false; };
            UWorld* W=World.Get(); USkateRailSubsystem* Registry=W ? W->GetSubsystem<USkateRailSubsystem>() : nullptr;
            Waited+=Dt;
            if (!Registry || Registry->Rails.IsEmpty())
            {
                if (Waited<60) return true;
                UE_LOG(LogTemp,Error,TEXT("SKATE PIER CHECK FAIL: no rails registered after 60 s")); return Finish(1);
            }
            if (Waited<10) return true;   // the world around the player loads first
            const TArray<TSharedPtr<FJsonValue>>* Lines=nullptr;
            const TSharedPtr<FJsonObject> Json=AtelierReadJson(AtelierDataPath(TEXT("skatepark/park.json")));
            if (!Json || !Json->TryGetArrayField(TEXT("rails"),Lines))
            { UE_LOG(LogTemp,Error,TEXT("SKATE PIER CHECK FAIL: skatepark/park.json is missing or has no rails")); return Finish(1); }
            int32 Failed=0,Checked=0;
            for (const auto& Value : *Lines)
            {
                const TSharedPtr<FJsonObject> Line=Value->AsObject();
                const FString Id=Line->GetStringField(TEXT("id")), Kind=Line->GetStringField(TEXT("kind"));
                if (Kind==TEXT("coping")) continue;   // the transitions' lips are not the modules'
                ++Checked;
                const FSkateRail* Rail=Registry->Rails.FindByPredicate([&](const FSkateRail& R){ return R.Id==FName(*Id); });
                if (!Rail || Rail->Points.Num()<2)
                { ++Failed; UE_LOG(LogTemp,Display,TEXT("SKATE PIER %s %s: not registered FAIL"),*Id,*Kind); continue; }
                FVector Tangent; const FVector Mid=Registry->Sample(int32(Rail-Registry->Rails.GetData()),Rail->Length()*.5f,Tangent);
                // Each line is tried on it (a thin round rail) and 3 cm to either side (a ledge's or curved ledge's
                // lip); the nearest surface counts.
                const FVector Across=FVector(-Tangent.Y,Tangent.X,0).GetSafeNormal();
                const TArray<FVector,TInlineAllocator<3>> Tries={Mid,Mid+Across*3.f,Mid-Across*3.f};
                FHitResult Hit; FCollisionQueryParams Params(TEXT("SkatePierCheck"),true);
                bool bHit=false; float Off=NAN;
                for (const FVector& At : Tries)
                {
                    FHitResult Try;
                    if (!W->LineTraceSingleByChannel(Try,At+FVector(0,0,40),At-FVector(0,0,40),ECC_Visibility,Params)) continue;
                    const float TryOff=float(Try.ImpactPoint.Z-Mid.Z);
                    if (!bHit || FMath::Abs(TryOff)<FMath::Abs(Off)) { bHit=true; Off=TryOff; Hit=Try; }
                }
                const bool bOk=bHit && FMath::Abs(Off)<=3.f;
                Failed+=!bOk;
                UE_LOG(LogTemp,Display,TEXT("SKATE PIER %s %s: %d points, %.1f m, surface %s cm from the line (%s) %s"),*Id,*Kind,Rail->Points.Num(),
                    Rail->Length()/100.f,bHit ? *FString::Printf(TEXT("%.1f"),Off) : TEXT("-"),
                    bHit && Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("nothing"),bOk ? TEXT("PASS") : TEXT("FAIL"));
            }
            if (!Checked)   // a package gate: no line to check is a failure, not a pass
            { UE_LOG(LogTemp,Error,TEXT("SKATE PIER CHECK FAIL: skatepark/park.json has no rail, ledge or curb lines")); return Finish(1); }
            UE_LOG(LogTemp,Display,TEXT("SKATE PIER CHECK %s: %d of %d lines failed"),Failed ? TEXT("FAIL") : TEXT("PASS"),Failed,Checked);
            return Finish(Failed);
        });
    }));

// The skate bowl check (packaged QA, no Python): the ground and pier checks never ride the community park's bowl, so
// this one does. From the measured bowl start (world.json 1263.5, 576.2, 46.012 m; UE yaw 180) the rider is put on the
// board, left standing 3 s, then launched at 600 and then 1000 cm/s and left to coast for 10 s (the strike measured at
// 1000 cm/s came at 6.24 s; `seconds=` changes it). From placement to the end of each run the board takes scripted, empty
// input, so a pad or keyboard cannot steer it; it is handed back on every way out. Before each run the player travels to
// the start and waits up to 30 s for the bowl to stream in: ground under the start within 1 m of its measured height,
// where the board is placed. Every game frame of the coast logs the route (the rider's location in world.json metres,
// 3 decimals), the board's mode and whether there is ground under it. From 0.5 s after the launch, a change of the
// board's velocity over 150 cm/s (`shock=`) between two frames both rolling on the ground is a shock, logged with the
// velocities before and after in UE cm/s; the same change into or out of the air or a grind (a take-off, a landing) is
// logged as a jolt and does not fail. A run fails on a bail or a shock, and fails as unmeasured on anything it cannot
// measure: a start whose ground never streams, a placement that fails, no coast frame, a route under 1 m, a frame with no
// ground under the rider or with the rider off the board before any bail, a launch that never takes (the board never
// reaches half its speed). Each failure is logged where it happened. One SKATE BOWL line per run, then
// the summary line, which is the result; `quit` then exits and asks for status 1 on a failure (Windows and Linux pass
// it on, macOS exits with 0 regardless). Lists take commas or slashes: -ExecCmds splits its commands at commas, so
// there write -ExecCmds="japan.SkateBowlCheck speeds=600/1000 quit".
// Usage: japan.SkateBowlCheck [at=X,Y,Z (world.json m)] [yaw=DEG] [speeds=CM/S,...] [shock=CM/S] [seconds=S] [quit]
namespace
{
    struct FSkateBowlCheck
    {
        TWeakObjectPtr<AWandererCharacter> Player; TArray<float> Speeds; FVector Start=FVector::ZeroVector,Ground=FVector::ZeroVector,End=FVector::ZeroVector,Before=FVector::ZeroVector;
        float Yaw=180,Shock=150,Seconds=10,Waited=0,Top=0; bool bQuit=false,bTravelled=false;
        int32 Run=0,Phase=-1,Failed=0,Frames=0,Bare=0,Off=0,Shocks=0,Jolts=0,Bails=0,Bailed=0,PrevMode=-1,Modes[5]={}; double Since=0,Last=0;
        FVector Prev=FVector::ZeroVector; float Travel=0; TWeakObjectPtr<USkateComponent> Held;
    };

    // Hand the board back to the player's input (the check holds it with empty scripted input while a run is on).
    void ReleaseSkateBowlInput(FSkateBowlCheck& C) { if (USkateComponent* S=C.Held.Get()) S->SetScriptedInput(nullptr); C.Held=nullptr; }

    // A UE point in world.json's frame and metres (X/100, -Y/100, Z/100), as the bowl's receipts give it.
    FString BowlMetres(const FVector& V,const TCHAR* Sep=TEXT(" ")) { return FString::Printf(TEXT("%.3f%s%.3f%s%.3f"),V.X/100.,Sep,-V.Y/100.,Sep,V.Z/100.); }
    const TCHAR* BowlMode(int32 Mode)   // ESkateMode
    {
        static const TCHAR* Names[]={TEXT("Off"),TEXT("Ground"),TEXT("Air"),TEXT("Grind"),TEXT("Bail")};
        return Mode>=0 && Mode<5 ? Names[Mode] : TEXT("?");
    }

    // The next run, or the summary line when every run is done. False when it is done.
    bool NextSkateBowlRun(const TSharedRef<FSkateBowlCheck>& C)
    {
        ReleaseSkateBowlInput(*C);
        if (++C->Run<C->Speeds.Num())
        {
            C->Phase=-1; C->bTravelled=false; C->Waited=C->Top=C->Travel=0; C->Frames=C->Bare=C->Off=C->Shocks=C->Jolts=C->Bailed=0; C->PrevMode=-1;
            for (int32& M : C->Modes) M=0;
            return true;
        }
        UE_LOG(LogTemp,Display,TEXT("SKATE BOWL CHECK %s: %d of %d runs failed"),C->Failed ? TEXT("FAIL") : TEXT("PASS"),C->Failed,C->Speeds.Num());
        if (C->bQuit) AtelierRequestExit(C->Failed ? 1 : 0);
        return false;
    }

    // One tick of a run: phase -1 travels to the start and waits for its ground, 0 stands 3 s on the board, 1 coasts.
    // False when every run is done.
    bool StepSkateBowlCheck(const TSharedRef<FSkateBowlCheck>& C,float Dt)
    {
        AWandererCharacter* P=C->Player.Get(); USkateComponent* Skate=P ? P->GetSkate() : nullptr; UWorld* W=P ? P->GetWorld() : nullptr;
        if (!Skate || !W)
        {
            UE_LOG(LogTemp,Error,TEXT("SKATE BOWL check stopped: no player on a board"));
            C->Failed+=C->Speeds.Num()-C->Run; C->Run=C->Speeds.Num()-1; return NextSkateBowlRun(C);
        }
        const float Speed=C->Speeds[C->Run];
        const FString Name=FString::Printf(TEXT("run%d_%.0f"),C->Run+1,Speed);
        if (C->Phase<0)
        {
            // Ground is looked for only on a tick after the travel, 3 m above the start down (the bowl has no roof).
            C->Waited+=Dt;
            const bool bWas=C->bTravelled;
            if (!C->bTravelled) C->bTravelled=P->TravelTo(C->Start,C->Yaw,TEXT("skate bowl check"));
            if (!bWas || !GroundBelow(W,C->Start,C->Start.Z+300,P,C->Ground) || FMath::Abs(C->Ground.Z-C->Start.Z)>100)
            {
                if (C->Waited<30) return true;
                UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s: no ground within 1 m of the start (%s m) after 30 s, %s FAIL (unmeasured)"),*Name,*BowlMetres(C->Start),
                    C->bTravelled ? TEXT("travelled there") : TEXT("could not travel there"));
                ++C->Failed; return NextSkateBowlRun(C);
            }
            UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s: ground at (%s m), %.1f cm from the measured start, after %.1f s"),*Name,*BowlMetres(C->Ground),
                C->Ground.Z-C->Start.Z,C->Waited);
            if (!Skate->PlaceAt(C->Ground,C->Yaw))
            { UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s: the rider could not be placed FAIL (unmeasured)"),*Name); ++C->Failed; return NextSkateBowlRun(C); }
            static const FSkateInput Still;   // no stick, no button: the board coasts on what the bowl gives it
            Skate->SetScriptedInput(&Still); C->Held=Skate;
            C->Phase=0; C->Since=C->Last=W->GetTimeSeconds(); C->Bails=Skate->GetBailCount(); return true;
        }
        // Settling and the coast run on the world's clock, so a hitch or a pause does not cut them short.
        const double Now=W->GetTimeSeconds();
        if (C->Phase==0)
        {
            if (Now-C->Since<3) return true;
            UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s settled: mode %s, bails %d, speed %.0f cm/s, at (%s m)"),*Name,BowlMode(int32(Skate->GetMode())),
                Skate->GetBailCount()-C->Bails,Skate->GetSpeed(),*BowlMetres(P->GetActorLocation()));
            C->Before=FRotator(0,C->Yaw,0).Vector()*Speed;
            Skate->Launch(C->Before);
            C->Phase=1; C->Since=C->Last=Now; return true;
        }
        if (Now<=C->Last) return true;   // no game frame since the last tick (paused): nothing moved, nothing to compare
        C->Last=Now;
        const float T=float(Now-C->Since);
        const FVector At=P->GetActorLocation(),V=Skate->GetBoardVelocity(); const int32 Mode=int32(Skate->GetMode());
        FVector Under; const bool bBare=!GroundBelow(W,At,At.Z+300,P,Under);
        const int32 BailsNow=Skate->GetBailCount()-C->Bails;
        if (C->Frames) C->Travel+=float(FVector::Dist(At,C->Prev));
        ++C->Frames; ++C->Modes[FMath::Clamp(Mode,0,4)]; C->End=At; C->Prev=At; C->Top=FMath::Max(C->Top,float(V.Size()));
        UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s route t=%.3f %s mode=%d ground=%d"),*Name,T,*BowlMetres(At),Mode,!bBare);
        // Where a run fails, as it happens: the first frame without ground, off the board (before a bail, after which
        // the rider is off by design), and each bail.
        if (bBare && !C->Bare++) UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s unmeasured: no ground under the rider t=%.3f at=(%s m)"),*Name,T,*BowlMetres(At,TEXT(",")));
        if (Mode==int32(ESkateMode::Off) && !C->Bailed && !C->Off++)
            UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s unmeasured: off the board t=%.3f at=(%s m)"),*Name,T,*BowlMetres(At,TEXT(",")));
        if (BailsNow>C->Bailed || (Mode==int32(ESkateMode::Bail) && C->PrevMode!=Mode && !C->Bailed))
        {
            C->Bailed=FMath::Max(BailsNow,C->Bailed+1);
            UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s bail t=%.3f at=(%s m) mode %s speed %.0f cm/s"),*Name,T,*BowlMetres(At,TEXT(",")),BowlMode(Mode),V.Size());
        }
        // The launch itself is a step from rest; past the first half second a jump in one frame rolling on the ground
        // is the bowl's. Into or out of the air or a grind it is a take-off or a landing: logged, not failed.
        const float Delta=float((V-C->Before).Size());
        if (T>.5f && Delta>C->Shock)
        {
            const bool bRolling=Mode==int32(ESkateMode::Ground) && C->PrevMode==Mode;
            (bRolling ? C->Shocks : C->Jolts)++;
            UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s %s t=%.3f delta=%.2f m/s at=(%s m) modes %s->%s before=(%.0f,%.0f,%.0f) after=(%.0f,%.0f,%.0f)"),*Name,
                bRolling ? TEXT("shock") : TEXT("jolt"),T,Delta/100.f,*BowlMetres(At,TEXT(",")),BowlMode(C->PrevMode),BowlMode(Mode),
                C->Before.X,C->Before.Y,C->Before.Z,V.X,V.Y,V.Z);
        }
        C->Before=V; C->PrevMode=Mode;
        if (T<C->Seconds) return true;
        const int32 Bails=FMath::Max(Skate->GetBailCount()-C->Bails,C->Bailed);
        const bool bUnmeasured=!C->Frames || C->Bare || C->Off || C->Travel<100.f || C->Top<Speed*.5f, bBailed=Bails>0;
        const bool bFail=bUnmeasured || bBailed || C->Shocks;
        C->Failed+=bFail;
        FString Modes;
        for (int32 M=0; M<5; ++M) if (C->Modes[M]) Modes+=FString::Printf(TEXT("%s%s %d"),Modes.IsEmpty() ? TEXT("") : TEXT(", "),BowlMode(M),C->Modes[M]);
        UE_LOG(LogTemp,Display,TEXT("SKATE BOWL %s: %d frames, %d without ground, %d off the board, modes {%s}, bails %d, %d shocks, %d jolts, top %.0f cm/s, route %.2f m, start (%s m) end (%s m), %s"),
            *Name,C->Frames,C->Bare,C->Off,*Modes,Bails,C->Shocks,C->Jolts,C->Top,C->Travel/100.f,*BowlMetres(C->Ground),*BowlMetres(C->End),
            bBailed ? TEXT("FAIL (bail)") : C->Shocks ? TEXT("FAIL") : bUnmeasured ? TEXT("FAIL (unmeasured)") : TEXT("PASS"));
        return NextSkateBowlRun(C);
    }
}

// Run from the command line as -ExecCmds="japan.SkateBowlCheck quit": it waits up to a minute for the player and its
// board, then 10 s more for the world around it to load and the skate runtime to preload, before the first run.
static FAutoConsoleCommandWithWorldAndArgs SkateBowlCheckCommand(TEXT("japan.SkateBowlCheck"),
    TEXT("Packaged QA: coast through the community park's bowl from its measured start, logging SKATE BOWL lines. Args: [at=X,Y,Z] [yaw=DEG] [speeds=CM/S,...] [shock=CM/S] [seconds=S] [quit]."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args,UWorld* Game)
    {
        auto C=MakeShared<FSkateBowlCheck>();
        C->Start=AJapanWorld::ToUE(1263.5,576.2,46.012);
        FString Bad;
        for (const FString& Arg : Args)
        {
            if (Arg==TEXT("quit")) { C->bQuit=true; continue; }
            FString Key,Value; TArray<FString> List; bool bOk=Arg.Split(TEXT("="),&Key,&Value);
            const TCHAR* Separators[]={TEXT(","),TEXT("/")}; Value.ParseIntoArray(List,Separators,2);
            for (const FString& Number : List) bOk&=Number.IsNumeric();
            auto At=[&](int32 I){ return float(FCString::Atod(*List[I])); };
            if (bOk && Key==TEXT("at") && List.Num()==3) C->Start=AJapanWorld::ToUE(FCString::Atod(*List[0]),FCString::Atod(*List[1]),FCString::Atod(*List[2]));
            else if (bOk && Key==TEXT("yaw") && List.Num()==1) C->Yaw=At(0);
            else if (bOk && Key==TEXT("speeds") && List.Num()) { for (int32 I=0; I<List.Num(); ++I) { C->Speeds.Add(At(I)); bOk&=At(I)>0; } }
            else if (bOk && Key==TEXT("shock") && List.Num()==1) { C->Shock=At(0); bOk=C->Shock>0; }
            else if (bOk && Key==TEXT("seconds") && List.Num()==1) { C->Seconds=At(0); bOk=C->Seconds>.5f; }
            else bOk=false;
            if (!bOk) Bad+=TEXT(" ")+Arg;
        }
        if (C->Speeds.IsEmpty()) C->Speeds={600.f,1000.f};
        if (!Bad.IsEmpty())   // a mistyped argument would quietly ride the defaults: fail instead
        {
            UE_LOG(LogTemp,Error,TEXT("SKATE BOWL CHECK FAIL: bad arguments:%s"),*Bad);
            if (C->bQuit) AtelierRequestExit(1);
            return;
        }
        TWeakObjectPtr<UWorld> World=Game; float Waited=0,Settled=-1;
        FTSTicker::GetCoreTicker().AddTicker(TEXT("SkateBowlCheck"),0.f,[C,World,Waited,Settled](float Dt) mutable
        {
            if (Settled<10)
            {
                const APlayerController* PC=World.IsValid() ? World->GetFirstPlayerController() : nullptr;
                C->Player=PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
                Waited+=Dt;
                if (C->Player.IsValid() && C->Player->GetSkate()) Settled=Settled<0 ? 0 : Settled+Dt;
                else if (Waited>60)
                {
                    UE_LOG(LogTemp,Error,TEXT("SKATE BOWL CHECK FAIL: no player with a board after 60 s"));
                    if (C->bQuit) AtelierRequestExit(1);
                    return false;
                }
                if (Settled<10) return true;
                UE_LOG(LogTemp,Display,TEXT("SKATE BOWL CHECK: %d runs from (%s m) yaw %.1f, %.1f s coasts, shocks over %.0f cm/s"),C->Speeds.Num(),*BowlMetres(C->Start),
                    C->Yaw,C->Seconds,C->Shock);
                return true;
            }
            return StepSkateBowlCheck(C,Dt);
        });
    }));
