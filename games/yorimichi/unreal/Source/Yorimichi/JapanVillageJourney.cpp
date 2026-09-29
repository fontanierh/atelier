#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "SkateboardComponent.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/Controller.h"
#include "Engine/GameViewportClient.h"
#include "ImageUtils.h"
#include "ImageCore.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"

// A capture-only director. It supplies normal movement, push and brake input;
// it never moves the pawn directly or changes gameplay speeds/animation clocks.
struct FVillageJourney
{
    int32 Stage=0,Point=0,PendingFrame=-1,Written=0,FinishFrame=-1;
    double Pause=-1.,StageStart=0.,LastProgress=0.;
    bool Mounted=false,Stopping=false,CameraReady=false;
    FVector Camera=FVector::ZeroVector,AerialStart=FVector::ZeroVector;
    FRotator Rotation=FRotator::ZeroRotator,AerialRotation=FRotator::ZeroRotator;
    FString Telemetry=TEXT("frame,seconds,stage,point,speed,x,y,z,falling,skating,clip,camera_x,camera_y,camera_z\n");
};

static FVector JourneyPosition(const TArray<TSharedPtr<FJsonValue>>& A)
{ return AJapanWorld::ToUE(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber()); }

void AWandererCharacter::EndVillageJourney()
{ if (VillageJourney || bMegaReview) UGameViewportClient::OnScreenshotCaptured().RemoveAll(this); }

void AWandererCharacter::SaveJourneyFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels)
{
    if (!VillageJourney || VillageJourney->PendingFrame<0) return;
    auto& J=*VillageJourney;
    const FString Path=ReviewDirectory/FString::Printf(TEXT("frame_%05d.jpg"),J.PendingFrame);
    if (Width!=1920 || Height!=1080 || !FImageUtils::SaveImageByExtension(*Path,FImageView(Pixels.GetData(),Width,Height),95))
    { UE_LOG(LogTemp,Error,TEXT("Journey frame write failed: %s"),*Path);FPlatformMisc::RequestExitWithStatus(false,2);return; }
    ++J.Written;J.PendingFrame=-1;
}

void AWandererCharacter::AdvanceVillageJourney(float Dt)
{
    if (!VillageJourney)
    {
        VillageJourney=MakeShared<FVillageJourney>();
        UGameViewportClient::OnScreenshotCaptured().AddUObject(this,&AWandererCharacter::SaveJourneyFrame);
        TrailerHeading=GetActorRotation().Yaw;
    }
    auto& J=*VillageJourney;
    const double T=TrailerFrame/60.;
    const auto& Stages=TrailerSpec->GetArrayField(TEXT("stages"));
    const auto& Stage=Stages[FMath::Min(J.Stage,Stages.Num()-1)]->AsObject();
    const bool Aerial=Stage->GetStringField(TEXT("mode"))==TEXT("aerial");
    const bool Skate=Stage->GetStringField(TEXT("mode"))==TEXT("skate");
    MoveIntent=FVector2D::ZeroVector;bWalk=false;bJog=false;PreferredFOV=66.f;
    if (J.FinishFrame>=0)
    {
        if (TrailerFrame>J.FinishFrame+2)
        {
            FFileHelper::SaveStringToFile(J.Telemetry,*(ReviewDirectory/TEXT("telemetry.csv")));
            FFileHelper::SaveStringToFile(FString::Printf(TEXT("{\"frames\":%d,\"written\":%d,\"completed_stages\":%d,\"passed\":true}\n"),J.FinishFrame+1,J.Written,Stages.Num()),*(ReviewDirectory/TEXT("journey-complete.json")));
            UE_LOG(LogTemp,Display,TEXT("VILLAGE JOURNEY COMPLETE: %d frames"),J.FinishFrame+1);
            FPlatformMisc::RequestExit(false);
        }
        ++TrailerFrame;return;
    }
    if (T>240. || (T>J.LastProgress+25. && !Aerial))
    { UE_LOG(LogTemp,Error,TEXT("Journey stalled at stage %d point %d time %.1f"),J.Stage,J.Point,T);FPlatformMisc::RequestExitWithStatus(false,2);return; }
    if (T>=0. && !Aerial)
    {
        const auto& Path=Stage->GetArrayField(TEXT("path"));
        auto Point=[&](int32 I){return JourneyPosition(Path[FMath::Clamp(I,0,Path.Num()-1)]->AsArray());};
        const FVector Here=GetActorLocation();
        double Best=FVector::DistSquared2D(Here,Point(J.Point));int32 Closest=J.Point;
        for (int32 I=J.Point+1;I<FMath::Min(J.Point+22,Path.Num());++I)
        { const double D=FVector::DistSquared2D(Here,Point(I));if (D<Best){Best=D;Closest=I;} }
        if (Closest>J.Point){J.Point=Closest;J.LastProgress=T;}
        const double Remaining=FVector::Dist2D(Here,Point(Path.Num()-1));
        const bool AtEnd=J.Point>=Path.Num()-5 && Remaining<(Skate?210.:38.);
        if (Skate && !J.Mounted && T>.6){Skateboard->Toggle();J.Mounted=true;}
        if (AtEnd && Skate && !J.Stopping){Skateboard->Toggle();J.Stopping=true;}
        if ((AtEnd && !Skate) || (J.Stopping && !Skateboard->IsEquipped()))
        { if (J.Pause<0.) J.Pause=T; }
        if (J.Pause>=0.)
        {
            const FVector Look=JourneyPosition(Stage->GetArrayField(TEXT("look")));
            const float Yaw=(Look-Here).Rotation().Yaw;
            SetActorRotation(FRotator(0,FMath::FixedTurn(GetActorRotation().Yaw,Yaw,65.f*Dt),0));
            if (T-J.Pause>Stage->GetNumberField(TEXT("pause")))
            {
                ++J.Stage;J.Point=0;J.StageStart=T;J.LastProgress=T;J.Pause=-1.;J.Stopping=false;
                J.AerialStart=J.Camera;J.AerialRotation=J.Rotation;
                UE_LOG(LogTemp,Display,TEXT("Journey stage %d at %.2f seconds"),J.Stage,T);
            }
        }
        else if (!J.Stopping && (!Skate || T>2.0))
        {
            // Distance-based lookahead, with bounded forward progress at crossings.
            const double Speed=GetVelocity().Size2D();
            const double Lookahead=Skate?FMath::Clamp(Speed*.45,150.,330.):FMath::Clamp(Speed*.35,85.,160.);
            int32 Target=J.Point;double Distance=0.;
            while (Target<Path.Num()-1 && Distance<Lookahead)
            {Distance+=FVector::Dist2D(Point(Target),Point(Target+1));++Target;}
            ReviewForward=(Point(Target)-Here).GetSafeNormal2D();
            if (Skate)
            {
                const double Error=FMath::FindDeltaAngleDegrees(GetActorRotation().Yaw,ReviewForward.Rotation().Yaw);
                const int32 Ahead=FMath::Min(Target+10,Path.Num()-1);
                const double Bend=FMath::Abs(FMath::FindDeltaAngleDegrees((Point(Target)-Point(J.Point)).Rotation().Yaw,(Point(Ahead)-Point(Target)).Rotation().Yaw));
                const double TargetSpeed=FMath::Clamp(820.-Bend*12.-FMath::Abs(Error)*4.,300.,820.);
                const double EndSpeed=Remaining<700. && J.Point>Path.Num()-20?300.:TargetSpeed;
                const float Throttle=Speed>EndSpeed+100.?-1.f:Speed<EndSpeed-65.?1.f:0.f;
                MoveIntent=FVector2D(FMath::Clamp(Error*.065,-1.,1.),Throttle);
            }
            else MoveIntent.Y=1.f;
        }
        Controller->SetControlRotation(ReviewForward.Rotation());
    }
    if (Aerial)
    {
        const double U=FMath::Clamp((T-J.StageStart)/Stage->GetNumberField(TEXT("seconds")),0.,1.);
        const double E=U*U*(3.-2.*U);
        J.Camera=FMath::Lerp(J.AerialStart,JourneyPosition(Stage->GetArrayField(TEXT("camera"))),E);
        const FVector Look=JourneyPosition(Stage->GetArrayField(TEXT("look")));
        const FQuat EndRotation=(Look-J.Camera).Rotation().Quaternion();
        J.Rotation=FQuat::Slerp(J.AerialRotation.Quaternion(),EndRotation,E).Rotator();
        if (U>=1.) J.FinishFrame=TrailerFrame;
    }
    else
    {
        TrailerHeading=FMath::FixedTurn(TrailerHeading,GetActorRotation().Yaw,55.f*Dt);
        const FVector Focus=GetActorLocation()+FVector(0,0,60);
        const FVector Desired=Focus-FRotator(0,TrailerHeading,0).Vector()*(Skate?490.:430.)+FVector(0,0,100);
        J.Camera=J.CameraReady?FMath::VInterpTo(J.Camera,Desired,Dt,5.f):Desired;
        J.Rotation=J.CameraReady?FMath::RInterpTo(J.Rotation,(Focus-J.Camera).Rotation(),Dt,6.f):(Focus-J.Camera).Rotation();
        J.CameraReady=true;
    }
    FollowCamera->SetWorldLocationAndRotation(J.Camera,J.Rotation);
    if (TrailerFrame>=0)
    {
        const FVector P=GetActorLocation();
        J.Telemetry+=FString::Printf(TEXT("%d,%.4f,%d,%d,%.4f,%.4f,%.4f,%.4f,%d,%d,%s,%.4f,%.4f,%.4f\n"),TrailerFrame,T,J.Stage,J.Point,GetVelocity().Size2D(),P.X,P.Y,P.Z,GetCharacterMovement()->IsFalling(),Skateboard->IsEquipped(),*Skateboard->GetClipName().ToString(),J.Camera.X,J.Camera.Y,J.Camera.Z);
        const int32 Stride=FMath::Max(1,int32(TrailerSpec->GetNumberField(TEXT("frame_stride"))));
        if (TrailerFrame%Stride==0)
        {
            J.PendingFrame=TrailerFrame;
            FScreenshotRequest::RequestScreenshot(TEXT("journey.jpg"),false,false);
        }
        if (TrailerFrame%600==0) UE_LOG(LogTemp,Display,TEXT("Journey %.1fs stage %d point %d speed %.0f"),T,J.Stage,J.Point,GetVelocity().Size2D());
    }
    ++TrailerFrame;
}
