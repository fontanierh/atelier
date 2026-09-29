#include "WandererCharacter.h"
#include "AtelierData.h"
#include "SkateboardComponent.h"
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

// Opt-in functional evidence. Real input bindings, no modification of movement
// state or speed. Fixed-step screenshots are never used to claim frame rate.
void AWandererCharacter::AdvanceSkateReview(float Dt)
{
    const float Previous = SkateReviewTime;
    SkateReviewTime += Dt;
    APlayerController* PC = CastChecked<APlayerController>(Controller);
    if (bRearSkateVideo && PC->GetHUD()) PC->GetHUD()->bShowHUD = false;
    auto Key = [&](float At,FKey K,bool Down)
    {
        if (Previous < At && SkateReviewTime >= At)
            PC->InputKey(FInputKeyEventArgs::CreateSimulated(K,Down ? IE_Pressed : IE_Released,Down ? 1.f : 0.f,1));
    };
    Key(.5f,EKeys::B,true); Key(.7f,EKeys::B,false);
    Key(2.f,EKeys::W,true); Key(13.f,EKeys::W,false);
    // Leave three clear-road pushes before the first ollie.
    Key(5.f,EKeys::SpaceBar,true); Key(5.2f,EKeys::SpaceBar,false);
    Key(5.55f,EKeys::SpaceBar,true); Key(5.65f,EKeys::SpaceBar,false); // No air boost.
    Key(7.f,EKeys::SpaceBar,true); Key(9.f,EKeys::SpaceBar,false); // Holding never repeats.
    Key(10.f,EKeys::Gamepad_FaceButton_Bottom,true); Key(10.1f,EKeys::Gamepad_FaceButton_Bottom,false);
    Key(4.4f,EKeys::C,true); Key(4.6f,EKeys::C,false);
    Key(4.8f,EKeys::LeftControl,true); Key(5.f,EKeys::LeftControl,false);
    Key(16.f,EKeys::D,true); Key(16.25f,EKeys::D,false);
    Key(17.f,EKeys::A,true); Key(17.25f,EKeys::A,false);
    Key(18.f,EKeys::S,true); Key(20.2f,EKeys::S,false);
    Key(20.4f,EKeys::SpaceBar,true); Key(20.5f,EKeys::SpaceBar,false); // Stationary pop.
    Key(21.f,EKeys::W,true); Key(24.f,EKeys::W,false);
    Key(25.f,EKeys::B,true); Key(25.2f,EKeys::B,false);
    Key(24.2f,EKeys::SpaceBar,true); Key(24.3f,EKeys::SpaceBar,false); // Stow queued in air.
    Key(29.f,EKeys::W,true); // Running is the default after stowing, too.
    Key(31.f,EKeys::W,false);
    Key(32.f,EKeys::C,true); Key(32.2f,EKeys::C,false);
    Key(33.f,EKeys::B,true); Key(33.2f,EKeys::B,false);
    Key(35.f,EKeys::W,true); Key(38.f,EKeys::W,false);
    // The settings menu must stop a rolling board, then leave controls usable.
    Key(38.2f,EKeys::Escape,true); Key(38.4f,EKeys::Escape,false);
    Key(38.05f,EKeys::SpaceBar,true); Key(38.15f,EKeys::SpaceBar,false); // Cancel preload.
    Key(40.f,EKeys::Escape,true); Key(40.2f,EKeys::Escape,false);
    Key(41.f,EKeys::B,true); Key(41.2f,EKeys::B,false);

    if (bSkateStanceReview)
    {
        Key(45.f,EKeys::B,true); Key(45.2f,EKeys::B,false);
        Key(47.f,EKeys::W,true); Key(49.2f,EKeys::W,false);
        Key(49.f,EKeys::SpaceBar,true); Key(49.2f,EKeys::SpaceBar,false);
        Key(49.5f,EKeys::Escape,true); Key(49.55f,EKeys::Escape,false);
        if (Previous < 49.6f && SkateReviewTime >= 49.6f)
        {
            // Navigate the actual settings controls, exercising OnClicked/Save.
            for (FKey K : {EKeys::Tab,EKeys::Tab,EKeys::Enter})
            {
                FKeyEvent Event(K,FModifierKeysState(),0,false,0,0);
                FSlateApplication::Get().ProcessKeyDownEvent(Event);
                FSlateApplication::Get().ProcessKeyUpEvent(Event);
            }
        }
        Key(50.2f,EKeys::Escape,true); Key(50.4f,EKeys::Escape,false);
        Key(55.f,EKeys::W,true); Key(59.f,EKeys::W,false);
        Key(61.f,EKeys::B,true); Key(61.2f,EKeys::B,false);
        for (float T : {49.8f,54.5f,56.5f,60.f})
            if (Previous < T && SkateReviewTime >= T)
                FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("stance_%04d.png"),FMath::RoundToInt(T*100)),false,false);
    }
    const bool bManualSteer = SkateReviewTime >= 15.9f && SkateReviewTime <= 17.3f;
    const float SteeringInput = Skateboard->IsEquipped() && !bManualSteer ? GetRoadSteering() : 0.f;
    PC->InputKey(FInputKeyEventArgs::CreateSimulated(EKeys::Gamepad_LeftX,IE_Axis,SteeringInput,1));
    if (SkateReviewTime < 38.f || SkateReviewTime > 40.3f)
    {
        const float Orbit = bRearSkateVideo ? 0.f : SkateReviewTime < 14.f ? -112.f : SkateReviewTime < 21.f ? -30.f : -135.f;
        const FRotator Target(-12.f,Skateboard->IsEquipped() ? GetActorRotation().Yaw+Orbit : ReviewForward.Rotation().Yaw,0.f);
        // A smooth rear-follow shot for capture only. Gameplay camera input is unchanged.
        Controller->SetControlRotation(bRearSkateVideo ? FMath::RInterpTo(Controller->GetControlRotation(),Target,Dt,8.f) : Target);
    }
    if (bSkateVideo)
    {
        // Capture the selected preview length, then continue all remaining
        // menu/crouch checks and telemetry without writing video frames.
        if (SkateReviewTime < (bRearSkateVideo ? 24.f : bOllieVideo ? 12.3f : 31.3f)) FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("frame_%05d.png"),ReviewFrame++),false,false);
    }
    else
        // PNG readbacks can stall a frame by 200 ms. Keep them outside the
        // measured opening pushes and short ollies; fixed-step video supplies
        // their pose inspection without changing the input/physics timing.
        for (float T : {1.0f,6.5f,14.5f,16.5f,18.5f,20.f,26.f,28.5f,30.f,32.5f,34.f,38.7f,42.5f})
            if (Previous < T && SkateReviewTime >= T)
                FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("skate_%04d.png"),FMath::RoundToInt(T*100)),false,false);
    if (SkateReviewTime >= (bSkateStanceReview ? 66.f : 44.f))
    {
        FFileHelper::SaveStringToFile(SkateTelemetry,*(ReviewDirectory/TEXT("skate_telemetry.csv")));
        UE_LOG(LogTemp,Display,TEXT("SKATEBOARD QA COMPLETE"));
        FPlatformMisc::RequestExit(false);
    }
}

void AWandererCharacter::RecordSkatePose()
{
    if (!bSkateReview || !bReady || SkateReviewTime <= 0.f) return;
    const FVector P = GetActorLocation();
    const FVector Left = GetMesh()->GetSocketLocation(TEXT("foot_L"));
    const FVector Right = GetMesh()->GetSocketLocation(TEXT("foot_R"));
    const FVector Push = Skateboard->IsGoofy() ? Left : Right;
    const FVector Contact = Skateboard->GetContactLocation();
    const FVector LocalLeft = GetActorTransform().InverseTransformPosition(Left);
    const FVector LocalRight = GetActorTransform().InverseTransformPosition(Right);
    const FTransform Board = Skateboard->GetBoardTransform();
    const FVector BoardLeft = Board.InverseTransformPosition(Left), BoardRight = Board.InverseTransformPosition(Right);
    const bool bChild = GetMesh()->DoesSocketExist(TEXT("bag"));
    const FTransform Bag = GetMesh()->GetSocketTransform(bChild ? TEXT("bag") : TEXT("bag_R"),RTS_ParentBoneSpace);
    const FName ClothBone = GetMesh()->DoesSocketExist(TEXT("scarf_R")) ? TEXT("scarf_R") :
        (bChild ? TEXT("sash_R") : TEXT("scarf_01"));
    const FTransform Cloth = GetMesh()->GetSocketTransform(ClothBone,RTS_ParentBoneSpace);
    SkateTelemetry += FString::Printf(TEXT("%.5f,%s,%.5f,%.4f,%d,%d,%d,%d,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%d,%d,%d,%d,%d\n"),
        SkateReviewTime,*Skateboard->GetClipName().ToString(),Skateboard->GetPoseTime(),GetVelocity().Size2D(),
        Skateboard->IsEquipped(),GetCharacterMovement()->IsFalling(),bIsCrouched,bMenuOpen,
        GetActorRotation().Yaw,P.X,P.Y,P.Z,LocalLeft.X,LocalLeft.Y,LocalLeft.Z,LocalRight.X,LocalRight.Y,LocalRight.Z,
        Push.X,Push.Y,Push.Z,Contact.X,Contact.Y,Contact.Z,Skateboard->GetContactWeight(),
        GetVelocity().Z,BoardLeft.Z,BoardRight.Z,Board.Rotator().Pitch,Board.GetLocation().Z,
        Bag.Rotator().Pitch,Bag.GetLocation().Z,Cloth.Rotator().Pitch,
        Skateboard->GetBoardStencil(),GetMesh()->CustomDepthStencilValue,Skateboard->IsGoofy(),Skateboard->IsPreferredGoofy(),Skateboard->IsContinuousPush());
}

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
