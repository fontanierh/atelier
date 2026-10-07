#include "WandererCharacter.h"
#include "AtelierData.h"
#include "JapanWorld.h"
#include "Dev/HidamariReview.h"
#include "SkateComponent.h"
#include "SailboatComponent.h"
#include "ZeppelinService.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/HUD.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "ImageUtils.h"
#include "ImageCore.h"
#include "Serialization/JsonSerializer.h"

// Opt-in physics audit for the new traversable area, run by its preview script.
// Uses the live collision scene, not the generator's heightfield approximation.
static bool ValidateVillage(UWorld* World,AActor* Player,const FString& Directory)
{
    FString Text;
    TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text,*(AtelierDataPath(TEXT("world.json")))) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),Root)) return false;
    const TSharedPtr<FJsonObject>* Village=nullptr;
    if (!Root->TryGetObjectField(TEXT("village"),Village)) return false;
    auto Position=[](const TArray<TSharedPtr<FJsonValue>>& A)
    { return AJapanWorld::ToUE(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber()); };
    FCollisionQueryParams Params(SCENE_QUERY_STAT(VillageAudit),false,Player);
    TArray<TSharedPtr<FJsonValue>> Errors;
    int32 Samples=0,Sweeps=0,Walls=0;
    TArray<TSharedPtr<FJsonValue>> Colours;
    double MaxError=0;
    const double ProbeOffset=(*Village)->GetNumberField(TEXT("lane_width"))*50.-35.;
    const auto& Bounds=(*Village)->GetArrayField(TEXT("edit_bounds"));
    for (const auto& Path : (*Village)->GetArrayField(TEXT("surface_paths")))
    {
        const auto& Points=Path->AsArray();
        for (int32 I=0;I<Points.Num()-2;I+=2)
        {
            const FVector A=Position(Points[I]->AsArray()),B=Position(Points[I+2]->AsArray());
            const FVector Side=FVector::CrossProduct((B-A).GetSafeNormal2D(),FVector::UpVector);
            for (double Offset : {-ProbeOffset,0.,ProbeOffset})
            {
                const FVector P=A+Side*Offset;
                FHitResult Hit;
                const bool Ground=World->LineTraceSingleByChannel(Hit,P+FVector(0,0,100),P-FVector(0,0,120),ECC_Visibility,Params);
                const double Error=Ground?FMath::Abs(Hit.ImpactPoint.Z-A.Z):1000.;
                ++Samples;MaxError=FMath::Max(MaxError,Error);
                // Compare against the exported terrain-conforming surface,
                // including the original road shoulder. Offset samples allow crossfall.
                if (!Ground || Error>(Offset==0.?5.:20.))
                    Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("surface at sample %d, offset %.0f: %.1f cm"),I,Offset,Error)));
                const FVector Lift(0,0,102.);
                if (World->SweepSingleByChannel(Hit,P+Lift,B+Side*Offset+Lift,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(23.f,76.f),Params))
                    Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("blocked lane at sample %d, offset %.0f (%s)"),I,Offset,*Hit.GetComponent()->GetReadableName())));
                ++Sweeps;
            }
        }
    }
    for (const auto& Value : (*Village)->GetArrayField(TEXT("buildings")))
    {
        const auto& B=Value->AsObject();
        const FVector P=Position(B->GetArrayField(TEXT("position")))+FVector(0,0,125);
        const double Yaw=FMath::DegreesToRadians(B->GetNumberField(TEXT("yaw")));
        const FVector Front(FMath::Sin(Yaw),FMath::Cos(Yaw),0);
        FHitResult Hit;
        const bool Block=World->LineTraceSingleByChannel(Hit,P+Front*800,P,ECC_Pawn,Params);
        const UStaticMeshComponent* Mesh=Block?Cast<UStaticMeshComponent>(Hit.GetComponent()):nullptr;
        if (!Mesh || !Mesh->GetStaticMesh() || Mesh->GetStaticMesh()->GetName()!=B->GetStringField(TEXT("asset")))
            Errors.Add(MakeShared<FJsonValueString>(TEXT("missing front wall collision: ")+B->GetStringField(TEXT("asset"))));
        else
        {
            ++Walls;
            const auto& Buffer=Mesh->GetStaticMesh()->GetRenderData()->LODResources[0].VertexBuffers.ColorVertexBuffer;
            if (Buffer.GetVertexData() && Buffer.GetNumVertices()>0)
            {
                const FColor C=Buffer.VertexColor(0);
                Colours.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%s: %d,%d,%d, count %u"),*B->GetStringField(TEXT("asset")),C.R,C.G,C.B,Buffer.GetNumVertices())));
            }
        }
    }
    // Check the actual mesh root against live terrain, especially on the cut
    // forest banks. Bilinear heightfield placement alone cannot prove contact.
    int32 TreeRoots=0;
    double MaxRootGap=-10000.;
    for (TActorIterator<AJapanWorld> It(World);It;++It)
    {
        FCollisionQueryParams TreeParams(Params);
        for (auto* Group:It->Groups)
            if (Group->GetStaticMesh()->GetName().StartsWith(TEXT("Tree"))) TreeParams.AddIgnoredComponent(Group);
        for (auto* Group:It->Groups)
        {
            if (!Group->GetStaticMesh()->GetName().StartsWith(TEXT("Tree"))) continue;
            for (int32 I=0;I<Group->GetInstanceCount();++I)
            {
                FTransform X;Group->GetInstanceTransform(I,X,true);
                const FVector P=X.GetLocation();
                if (P.X<Bounds[0]->AsNumber()*100 || P.X>Bounds[1]->AsNumber()*100 ||
                    -P.Y<Bounds[2]->AsNumber()*100 || -P.Y>Bounds[3]->AsNumber()*100) continue;
                FHitResult Hit;
                // Roots are seated at the lowest point of their footprint; on a steep
                // bank the centre surface can be above the former 1.5 m probe.
                const bool Ground=World->LineTraceSingleByChannel(Hit,P+FVector(0,0,400),P-FVector(0,0,400),ECC_Visibility,TreeParams);
                const double RootZ=P.Z+Group->GetStaticMesh()->GetBoundingBox().Min.Z*X.GetScale3D().Z;
                const double Gap=Ground?RootZ-Hit.ImpactPoint.Z:1000.;
                MaxRootGap=FMath::Max(MaxRootGap,Gap);++TreeRoots;
                if (Gap>5.) Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("floating tree %s at %.1f,%.1f: %.1f cm"),*Group->GetStaticMesh()->GetName(),P.X,P.Y,Gap)));
            }
        }
    }
    TSharedRef<FJsonObject> Report=MakeShared<FJsonObject>();
    Report->SetNumberField(TEXT("ground_samples"),Samples);Report->SetNumberField(TEXT("capsule_sweeps"),Sweeps);
    Report->SetNumberField(TEXT("building_walls"),Walls);Report->SetNumberField(TEXT("max_surface_error_cm"),MaxError);
    Report->SetArrayField(TEXT("vertex_colours"),Colours);
    Report->SetNumberField(TEXT("tree_roots"),TreeRoots);Report->SetNumberField(TEXT("max_tree_root_gap_cm"),MaxRootGap);
    Report->SetArrayField(TEXT("errors"),Errors);Report->SetBoolField(TEXT("passed"),Errors.IsEmpty());
    FString Output;FJsonSerializer::Serialize(Report,TJsonWriterFactory<>::Create(&Output));
    FFileHelper::SaveStringToFile(Output,*(Directory/TEXT("village-physics.json")));
    UE_LOG(LogTemp,Display,TEXT("VILLAGE PHYSICS: %d samples, %d sweeps, %d walls, %d errors"),Samples,Sweeps,Walls,Errors.Num());
    return Errors.IsEmpty();
}

// High-quality JPEG capture avoids spending most of a UHD take compressing PNGs.
// Only opted-in trailer sessions bind this readback; ordinary gameplay is unaffected.
void AWandererCharacter::SaveTrailerFilmFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels)
{
    if(TrailerPending<0 || !TrailerSpec)return;
    double ExpectedWidth=1920,ExpectedHeight=1080;
    TrailerSpec->TryGetNumberField(TEXT("width"),ExpectedWidth);
    TrailerSpec->TryGetNumberField(TEXT("height"),ExpectedHeight);
    const FString Path=ReviewDirectory/FString::Printf(TEXT("frame_%05d.jpg"),TrailerPending);
    if(Width!=ExpectedWidth || Height!=ExpectedHeight ||
       !FImageUtils::SaveImageByExtension(*Path,FImageView(Pixels.GetData(),Width,Height),98))
    { FPlatformMisc::RequestExitWithStatus(false,2);return; }
    TrailerPending=-1;
}

static FString TrailerCSVField(FString Value)
{
    Value.ReplaceInline(TEXT("\""),TEXT("\"\""));
    return TEXT("\"")+Value+TEXT("\"");
}

// Deliberate camera moves over the real world and gameplay. Capture at 60 Hz;
// PNG readbacks slow wall-clock rendering and are not performance evidence.
void AWandererCharacter::AdvanceTrailer(float Dt)
{
    if (!TrailerSpec)
    {
        FString Text;
        if (!FFileHelper::LoadFileToString(Text,*TrailerSpecPath) ||
            !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),TrailerSpec))
        {
            UE_LOG(LogTemp,Error,TEXT("Invalid trailer shot: %s"),*TrailerSpecPath);
            FPlatformMisc::RequestExitWithStatus(false,2); return;
        }
        FString Format;TrailerSpec->TryGetStringField(TEXT("format"),Format);
        if(Format==TEXT("jpg"))UGameViewportClient::OnScreenshotCaptured().AddUObject(this,&AWandererCharacter::SaveTrailerFilmFrame);
        double Warmup=3.; TrailerSpec->TryGetNumberField(TEXT("warmup"),Warmup);
        TrailerFrame=-FMath::RoundToInt(FMath::Clamp(Warmup,3.,90.)*60.);
        if (auto* PC = Cast<APlayerController>(Controller); PC && PC->GetHUD()) PC->GetHUD()->bShowHUD = false;
        FString CameraMode;TrailerSpec->TryGetStringField(TEXT("camera_mode"),CameraMode);
        if(CameraMode!=TEXT("") && CameraMode!=TEXT("player"))
        {UE_LOG(LogTemp,Error,TEXT("Unknown trailer camera_mode"));FPlatformMisc::RequestExitWithStatus(false,2);return;}
        bFixedView=CameraMode!=TEXT("player");
        if(bFixedView)FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        bool AuditCity=false;
        TrailerSpec->TryGetBoolField(TEXT("validate_hidamari"),AuditCity);
        if(AuditCity && !ValidateHidamari(GetWorld(),this,ReviewDirectory))
        {FPlatformMisc::RequestExitWithStatus(false,2);return;}
        bool AuditVillage=false;
        TrailerSpec->TryGetBoolField(TEXT("validate_village"),AuditVillage);
        if (AuditVillage && !ValidateVillage(GetWorld(),this,ReviewDirectory))
        { FPlatformMisc::RequestExitWithStatus(false,2); return; }
        GetRoadSteering(); // Load the authored road using the existing capture helper.
        const int32 Road = FMath::Clamp(int32(TrailerSpec->GetNumberField(TEXT("road_index"))),0,SkateReviewRoad.Num()-2);
        if (!SkateReviewRoad.IsValidIndex(Road+1))
        { FPlatformMisc::RequestExitWithStatus(false,2); return; }
        SetActorLocation(SkateReviewRoad[Road]+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+8),false,nullptr,ETeleportType::TeleportPhysics);
        ReviewForward = (SkateReviewRoad[Road+1]-SkateReviewRoad[Road]).GetSafeNormal2D();
        const TArray<TSharedPtr<FJsonValue>>* CustomStart=nullptr;
        if(TrailerSpec->TryGetArrayField(TEXT("player_position"),CustomStart) && CustomStart->Num()==3)
            SetActorLocation(AJapanWorld::ToUE((*CustomStart)[0]->AsNumber(),(*CustomStart)[1]->AsNumber(),(*CustomStart)[2]->AsNumber())+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+8),false,nullptr,ETeleportType::TeleportPhysics);
        double CustomYaw=0;
        if(TrailerSpec->TryGetNumberField(TEXT("player_yaw"),CustomYaw)) ReviewForward=FRotator(0,-CustomYaw,0).Vector();
        SetActorRotation(ReviewForward.Rotation());
        GetCharacterMovement()->StopMovementImmediately();
        TrailerHeading = GetActorRotation().Yaw;
        if(!bFixedView)
        {
            double Pitch=-14.;TrailerSpec->TryGetNumberField(TEXT("camera_pitch"),Pitch);
            Controller->SetControlRotation(FRotator(Pitch,TrailerHeading,0));
        }
    }
    auto Number = [&](const TCHAR* Name,double Default) { double Value=Default; TrailerSpec->TryGetNumberField(Name,Value); return Value; };
    FString CameraMode;TrailerSpec->TryGetStringField(TEXT("camera_mode"),CameraMode);
    const bool PlayerCamera=CameraMode==TEXT("player");
    const bool FollowRoad=Number(TEXT("follow_road"),1)>.5;
    const int32 Frames = FMath::RoundToInt(Number(TEXT("seconds"),5)*60);
    const int32 CaptureFPS=Number(TEXT("capture_fps"),60)==30?30:60;
    const int32 CaptureStride=60/CaptureFPS;
    if (TrailerFrame >= Frames)
    {
        // Give the final request one full frame to reach disk before exiting.
        if (TrailerFrame++ > Frames)
        {
            FFileHelper::SaveStringToFile(TrailerTelemetry,*(ReviewDirectory/TEXT("telemetry.csv")));
            UE_LOG(LogTemp,Display,TEXT("TRAILER SHOT COMPLETE: %d frames"),Frames);
            FPlatformMisc::RequestExit(false);
        }
        return;
    }
    const double T = TrailerFrame/60.0;
    const double Progress = FMath::Clamp(T/(Frames/60.0),0.0,1.0);
    const double Ease = Progress*Progress*(3.0-2.0*Progress);
    const bool Environment = TrailerSpec->GetStringField(TEXT("kind")) == TEXT("world");
    const bool Skate = TrailerSpec->GetStringField(TEXT("kind")) == TEXT("skate");
    const auto& Events = TrailerSpec->GetArrayField(TEXT("events"));
    for (const auto& Event : Events)
    {
        const auto& E = Event->AsObject();
        const int32 EventFrame=FMath::RoundToInt(E->GetNumberField(TEXT("time"))*60);
        if(E->GetStringField(TEXT("action"))==TEXT("jump") && TrailerFrame==EventFrame+2) ReleaseJump(FInputActionValue());
        if (TrailerFrame != EventFrame) continue;
        const FString Action = E->GetStringField(TEXT("action"));
        if (Action == TEXT("equip")) ToggleSkateboard(FInputActionValue());
        if(Action==TEXT("launch"))
        {
            double Speed=0.;E->TryGetNumberField(TEXT("speed"),Speed);
            if(!SkateRide->IsRiding() || !FMath::IsFinite(Speed) || Speed<=0.)
            {UE_LOG(LogTemp,Error,TEXT("TRAILER LAUNCH requires an equipped board and positive speed in cm/s"));FPlatformMisc::RequestExitWithStatus(false,2);return;}
            const FSkateInput Coast;SkateRide->SetScriptedInput(&Coast);
            const FVector Velocity=ReviewForward*Speed;
            SkateRide->Launch(Velocity);
            UE_LOG(LogTemp,Display,TEXT("TRAILER LAUNCH frame=%d speed=%.3f at=%s velocity=%s"),TrailerFrame,Speed,*GetActorLocation().ToString(),*Velocity.ToString());
        }
        if (Action == TEXT("jump")) RequestJump(FInputActionValue());
        if (Action == TEXT("wave")) Wave(FInputActionValue());
        if (Action == TEXT("use")) Interact(FInputActionValue());
        if (Action == TEXT("sailboat")) ToggleSailboat(FInputActionValue());
        if (Action == TEXT("dodge")) Dodge(FInputActionValue());
        if (Action == TEXT("crouch")) ToggleCrouch(FInputActionValue());
    }
    const bool Moving = T >= Number(TEXT("move_start"),1000) && T < Number(TEXT("move_end"),1000);
    bWalk = Number(TEXT("walk"),0) > .5;
    bJog = Number(TEXT("jog"),0) > .5;
    bSprintHeld = Number(TEXT("sprint"),0) > .5;
    const bool Sailing=Sailboat->IsEquipped();
    const float Steer=T>=Number(TEXT("steer_start"),0) && T<Number(TEXT("steer_end"),1000)?Number(TEXT("steer"),0):0.;
    MoveIntent = FVector2D(Skate && FollowRoad ? GetRoadSteering()+Steer : Steer,Moving ? 1.f : 0.f);
    if (!Skate && !Sailing && !IsZeppelinPassenger() && Moving && FollowRoad)
        ReviewForward = FRotator(0,GetActorRotation().Yaw+GetRoadSteering()*120.f*Dt,0).Vector();
    if(!PlayerCamera)Controller->SetControlRotation(ReviewForward.Rotation());
    PreferredFOV = Number(TEXT("fov"),PlayerCamera?PreferredFOV:55);
    FVector Camera;
    FRotator Rotation;
    const TArray<TSharedPtr<FJsonValue>>* CustomCamera=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* CustomTarget=nullptr;
    const TArray<TSharedPtr<FJsonValue>>* Keys=nullptr;
    if(PlayerCamera)
    {
        // The normal camera owns its spring arm and native ride blend. Log the last rendered view.
        const auto* PC=Cast<APlayerController>(Controller);
        Camera=PC && PC->PlayerCameraManager?PC->PlayerCameraManager->GetCameraLocation():FollowCamera->GetComponentLocation();
        Rotation=PC && PC->PlayerCameraManager?PC->PlayerCameraManager->GetCameraRotation():FollowCamera->GetComponentRotation();
    }
    else if(Environment && TrailerSpec->TryGetArrayField(TEXT("keys"),Keys) && Keys->Num()>=2)
    {
        // A camera path: keys [seconds, camera x y z, target x y z, fov] in Blender metres, through which camera and
        // target follow Catmull-Rom curves (the tree house tour glides along bridges and up the lookout stairs).
        auto Key=[&](int32 I)->const TArray<TSharedPtr<FJsonValue>>& { return (*Keys)[FMath::Clamp(I,0,Keys->Num()-1)]->AsArray(); };
        int32 I=0;
        while(I<Keys->Num()-2 && Key(I+1)[0]->AsNumber()<=T) ++I;
        const double T0=Key(I)[0]->AsNumber(),T1=Key(I+1)[0]->AsNumber();
        const double U=FMath::Clamp((T-T0)/FMath::Max(T1-T0,1e-3),0.,1.);
        auto At=[&](int32 J,int32 O){ const auto& K=Key(J); return AJapanWorld::ToUE(K[O]->AsNumber(),K[O+1]->AsNumber(),K[O+2]->AsNumber()); };
        auto Curve=[&](int32 O)
        {
            const FVector P0=At(I-1,O),P1=At(I,O),P2=At(I+1,O),P3=At(I+2,O);
            return .5*(2.*P1+(P2-P0)*U+(2.*P0-5.*P1+4.*P2-P3)*U*U+(3.*P1-P0-3.*P2+P3)*U*U*U);
        };
        Camera=Curve(1);
        Rotation=(Curve(4)-Camera).Rotation();
        if(Key(I).Num()>7 && Key(I+1).Num()>7) PreferredFOV=FMath::Lerp(Key(I)[7]->AsNumber(),Key(I+1)[7]->AsNumber(),U*U*(3.-2.*U));
    }
    else if(Environment && TrailerSpec->TryGetArrayField(TEXT("camera_position"),CustomCamera) && CustomCamera->Num()==3 &&
       TrailerSpec->TryGetArrayField(TEXT("camera_target"),CustomTarget) && CustomTarget->Num()==3)
    {
        Camera=AJapanWorld::ToUE((*CustomCamera)[0]->AsNumber(),(*CustomCamera)[1]->AsNumber(),(*CustomCamera)[2]->AsNumber());
        const FVector Target=AJapanWorld::ToUE((*CustomTarget)[0]->AsNumber(),(*CustomTarget)[1]->AsNumber(),(*CustomTarget)[2]->AsNumber());
        Rotation=(Target-Camera).Rotation();
        Camera+=Rotation.Vector()*Number(TEXT("dolly"),0)*Ease
            + FRotationMatrix(Rotation).GetUnitAxis(EAxis::Y)*Number(TEXT("slide"),0)*Ease
            + FVector(0,0,Number(TEXT("lift"),0)*Ease);
        Rotation+=FRotator(Number(TEXT("tilt"),0)*Ease,Number(TEXT("pan"),0)*Ease,0);
    }
    else if (Environment)
    {
        const int32 Index = int32(Number(TEXT("world_shot"),0));
        if (!Landscape->Shots.IsValidIndex(Index))
        { FPlatformMisc::RequestExitWithStatus(false,2); return; }
        const FWorldShot& Shot = Landscape->Shots[Index];
        const FVector Forward = Shot.Rotation.Vector();
        const FVector Right = FRotationMatrix(Shot.Rotation).GetUnitAxis(EAxis::Y);
        Camera = Shot.Location + Forward*Number(TEXT("dolly"),150)*Ease
            + Right*Number(TEXT("slide"),0)*Ease + FVector(0,0,Number(TEXT("lift"),0)*Ease);
        Rotation = Shot.Rotation+FRotator(Number(TEXT("tilt"),0)*Ease,Number(TEXT("pan"),0)*Ease,0);
    }
    else
    {
        TrailerHeading = FMath::FixedTurn(TrailerHeading,GetActorRotation().Yaw,90.f*Dt);
        const double Orbit = FMath::Lerp(Number(TEXT("orbit_start"),20),Number(TEXT("orbit_end"),35),Ease);
        const double Distance = FMath::Lerp(Number(TEXT("distance_start"),430),Number(TEXT("distance_end"),400),Ease);
        FString Anchor;TrailerSpec->TryGetStringField(TEXT("camera_anchor"),Anchor);
        const FVector Origin=Anchor==TEXT("zeppelin")&&GetZeppelin()?GetZeppelin()->ShipPosition():GetActorLocation();
        const FVector Focus = Origin+FVector(0,0,Number(TEXT("focus_z"),10));
        Camera = Focus + FRotator(0,TrailerHeading+Orbit,0).Vector()*Distance+FVector(0,0,Number(TEXT("camera_height"),25));
        Rotation = (Focus-Camera).Rotation();
    }
    if(!PlayerCamera)FollowCamera->SetWorldLocationAndRotation(Camera,Rotation);
    if (TrailerFrame >= 0 && TrailerFrame%CaptureStride==0)
    {
        const FVector P = GetActorLocation();
        TrailerTelemetry += FString::Printf(TEXT("%d,%.4f,%.4f,%.4f,%.4f,%d,%d,%s,%.4f,%.4f,%.4f,%s,%d,%d,%.4f,%d,%.4f\n"),
            TrailerFrame/CaptureStride,GetVelocity().Size2D(),P.X,P.Y,P.Z,GetCharacterMovement()->IsFalling(),SkateRide->IsRiding(),
            *TrailerCSVField(SkateRide->GetRetailState()),Camera.X,Camera.Y,Camera.Z,*TrailerCSVField(AnimationAction.ToString()),
            Stamina.Sprinting,Sailing,Sailboat->GetSailAmount(),GetZeppelin()?GetZeppelin()->GetStage():-1,
            GetZeppelin()?GetZeppelin()->GetPropellerAngle():0.f);
        TrailerPending=TrailerFrame/CaptureStride;
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("frame_%05d.png"),TrailerPending),false,false);
    }
    ++TrailerFrame;
}
