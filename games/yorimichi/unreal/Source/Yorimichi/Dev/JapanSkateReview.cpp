#include "WandererCharacter.h"
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

// A scripted rider follows an authored road (docs/DESKTOP_PERFORMANCE.md: the benchmark and trailer routes): the steering
// that keeps it on the line, patrolling back and forth so long runs keep moving.
float AWandererCharacter::GetRoadSteering()
{
    if (SkateReviewRoad.IsEmpty())
    {
        FString Text;
        TSharedPtr<FJsonObject> Json;
        if (FFileHelper::LoadFileToString(Text,*(AtelierDataPath(TEXT("world.json")))) &&
            FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Json))
        {
            const TArray<TSharedPtr<FJsonValue>>* Route = &Json->GetArrayField(TEXT("road"));
            FString Requested;
            FParse::Value(FCommandLine::Get(),TEXT("reviewroute="),Requested);
            if (Requested == TEXT("village") || Requested == TEXT("village_loop"))
            {
                const TSharedPtr<FJsonObject>* Village = nullptr;
                if (!Json->TryGetObjectField(TEXT("village"),Village))
                { FPlatformMisc::RequestExitWithStatus(false,2); return 0.f; }
                const auto& Paths = (*Village)->GetArrayField(TEXT("paths"));
                const int32 Index = Requested == TEXT("village_loop") ? 1 : 0;
                if (!Paths.IsValidIndex(Index))
                { FPlatformMisc::RequestExitWithStatus(false,2); return 0.f; }
                Route = &Paths[Index]->AsArray();
            }
            if(Requested==TEXT("mega"))
            {
                const TSharedPtr<FJsonObject>* Mega=nullptr;
                if(!Json->TryGetObjectField(TEXT("mega"),Mega)){FPlatformMisc::RequestExitWithStatus(false,2);return 0.f;}
                Route=&(*Mega)->GetArrayField(TEXT("trail"));
            }
            TSharedPtr<FJsonObject> CityRoute;
            if(Requested==TEXT("park") || Requested==TEXT("north") || Requested==TEXT("hidamari") || Requested==TEXT("arcade") || Requested==TEXT("plaza") || Requested==TEXT("plaza_steps") || Requested==TEXT("harbor") || Requested==TEXT("harbor_pier"))
            {
                FString CityText;
                if(!FFileHelper::LoadFileToString(CityText,*(AtelierDataPath(TEXT("hidamari/city.json")))) ||
                   !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(CityText),CityRoute))
                {FPlatformMisc::RequestExitWithStatus(false,2);return 0.f;}
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
