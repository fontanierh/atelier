#include "WandererCharacter.h"
#include "JapanCharacterMovement.h"
#include "MegaRamp.h"
#include "SkateboardComponent.h"
#include "WandererDefinition.h"
#include "EngineUtils.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputKeyEventArgs.h"
#include "Engine/GameViewportClient.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "ImageUtils.h"
#include "ImageCore.h"
#include "GameFramework/HUD.h"

void AWandererCharacter::SaveMegaFilmFrame(int32 Width,int32 Height,const TArray<FColor>& Pixels)
{
 if(MegaFilmPending<0)return;
 const FString Path=ReviewDirectory/FString::Printf(TEXT("frame_%05d.jpg"),MegaFilmPending);
 int32 ExpectedWidth=1920,ExpectedHeight=1080;FParse::Value(FCommandLine::Get(),TEXT("resx="),ExpectedWidth);FParse::Value(FCommandLine::Get(),TEXT("resy="),ExpectedHeight);
 if(Width!=ExpectedWidth||Height!=ExpectedHeight||!FImageUtils::SaveImageByExtension(*Path,FImageView(Pixels.GetData(),Width,Height),95))
 {FPlatformMisc::RequestExitWithStatus(false,2);return;}
 MegaFilmPending=-1;
}

void AWandererCharacter::AdvanceMegaReview(float Dt)
{
 const bool Film=FParse::Param(FCommandLine::Get(),TEXT("megafilm"));
 const float Before=MegaReviewTime;MegaReviewTime+=Dt;
 auto* M=CastChecked<UJapanCharacterMovement>(GetCharacterMovement());auto* PC=CastChecked<APlayerController>(Controller);
 if(Before==0)
 {
  FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory);
  IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
  TActorIterator<AMegaRamp> It(GetWorld());if(It)SetActorLocation((FParse::Param(FCommandLine::Get(),TEXT("megadeck"))?It->DeckStart():It->LadderBottom()+FVector(0,90,0))+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+5));
  M->StopMovementImmediately();CameraArm->TargetArmLength=600;
  if(Film){UGameViewportClient::OnScreenshotCaptured().AddUObject(this,&AWandererCharacter::SaveMegaFilmFrame);if(PC->GetHUD())PC->GetHUD()->bShowHUD=false;PreferredFOV=65;}
 }
 auto Key=[&](float At,FKey K,bool Down){if(Before<At&&MegaReviewTime>=At)PC->InputKey(FInputKeyEventArgs::CreateSimulated(K,Down?IE_Pressed:IE_Released,Down?1.f:0.f,1));};
 if(FParse::Param(FCommandLine::Get(),TEXT("megadeck")))
 {
  PC->SetControlRotation(FRotator(0,0,0));
  if(MegaReviewTime<1)SetActorRotation(FRotator::ZeroRotator);
  Key(1,EKeys::B,true);Key(1.2,EKeys::B,false);Key(3,EKeys::W,true);Key(6,EKeys::W,false);
 }
 else {Key(1,EKeys::E,true);Key(1.2,EKeys::E,false);Key(21,EKeys::W,true);Key(24,EKeys::W,false);}
 // A straight drop-in must complete the line without a corrective steering script.
 if(M->RolloutExits>0){MoveIntent.Y=-1;}
 float CameraYaw=-65;FParse::Value(FCommandLine::Get(),TEXT("megayaw="),CameraYaw);
 PC->SetControlRotation(FMath::RInterpTo(PC->GetControlRotation(),FRotator(-15,M->IsMegaClimbing()?-125.f:CameraYaw,0),Dt,5.f));
 const FVector P=GetActorLocation();
 const float HeadDistance=FVector::Dist(GetMesh()->GetSocketLocation(TEXT("head")),GetMesh()->GetComponentLocation());
 float FootError=0;
 if(M->IsMega()&&M->MegaStage()>=2)
 for(const TCHAR* Bone:{TEXT("foot_L"),TEXT("foot_R")})
  FootError=FMath::Max(FootError,float(FMath::Abs(Skateboard->GetBoardTransform().InverseTransformPosition(GetMesh()->GetSocketLocation(Bone)).Z-9.3f-Definition->SkateAnkleHeight)));

 float GripError=-1;
 if(M->IsMega()&&M->MegaStage()==3&&Skateboard->GetPoseTime()>.19f&&Skateboard->GetPoseTime()<.39f)
 {
  const FVector Hand=Skateboard->GetBoardTransform().InverseTransformPosition(GetMesh()->GetSocketLocation(Skateboard->IsGoofy()?TEXT("hand_L"):TEXT("hand_R")));
  GripError=FVector::Dist(Hand,FVector(-2.5f,Skateboard->IsGoofy()?-15.5f:15.5f,14.9f));
 }
 MegaTelemetry+=FString::Printf(TEXT("%.4f,%d,%d,%.3f,%.3f,%.3f,%.3f,%.3f,%d,%d,%s,%.3f,%.3f,%.3f\n"),MegaReviewTime,M->IsMega()?M->MegaStage():-1,M->MegaSection(),M->MegaProgress(),M->MegaSpeed(),P.X,P.Y,P.Z,M->GapLandings,M->VertLandings,*Skateboard->GetClipName().ToString(),HeadDistance,FootError,GripError);
 if(Film)
 {
  // Record selected editorial windows while the complete line runs normally.
  const bool HalfRate=FParse::Param(FCommandLine::Get(),TEXT("film30"));
  if((!HalfRate||MegaFilmFrame%2==0)&&((MegaFilmFrame>=360&&MegaFilmFrame<540)||(MegaFilmFrame>=1260&&MegaFilmFrame<2100)))
  {MegaFilmPending=MegaFilmFrame;FScreenshotRequest::RequestScreenshot(false);}
  ++MegaFilmFrame;
 }
 if(!Film&&!FParse::Param(FCommandLine::Get(),TEXT("megashotless"))) for(float At:{.5f,7.f,20.f,24.f,26.f,28.f,28.4f,28.7f,29.f,29.3f,30.f,32.f,34.f,38.f})
 if(Before<At&&MegaReviewTime>=At){FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("mega_%04d.png"),FMath::RoundToInt(At*100)),false,false);
 FHitResult Probe;FCollisionQueryParams Query(SCENE_QUERY_STAT(MegaView),true,this);const FVector BP=Skateboard->GetBoardTransform().GetLocation();GetWorld()->LineTraceSingleByChannel(Probe,BP+FVector(0,0,2000),BP-FVector(0,0,2000),ECC_Visibility,Query);
 UE_LOG(LogTemp,Display,TEXT("MEGA RENDER meshscale=%s extent=%s head=%s main=%d ownernosee=%d onlyowner=%d cameraRot=%s"),*GetMesh()->GetComponentScale().ToString(),*GetMesh()->Bounds.BoxExtent.ToString(),*GetMesh()->GetSocketLocation(TEXT("head")).ToString(),GetMesh()->bRenderInMainPass,GetMesh()->bOwnerNoSee,GetMesh()->bOnlyOwnerSee,*FollowCamera->GetComponentRotation().ToString());
 UE_LOG(LogTemp,Display,TEXT("MEGA SURFACE board=%s hit=%s actor=%s"),*BP.ToString(),*Probe.ImpactPoint.ToString(),*GetNameSafe(Probe.GetActor()));
 UE_LOG(LogTemp,Display,TEXT("MEGA VIEW %.1f actor=%s mesh=%s bounds=%s camera=%s visible=%d hidden=%d board=%s"),At,*GetActorLocation().ToString(),*GetMesh()->GetComponentLocation().ToString(),*GetMesh()->Bounds.Origin.ToString(),*FollowCamera->GetComponentLocation().ToString(),GetMesh()->IsVisible(),IsHidden(),*Skateboard->GetBoardTransform().GetLocation().ToString());}
 if(MegaReviewTime>43)
 {
  IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
  FFileHelper::SaveStringToFile(MegaTelemetry,*(ReviewDirectory/TEXT("mega.csv")));
  FFileHelper::SaveStringToFile(FString::Printf(TEXT("{\"gap_landings\":%d,\"vert_landings\":%d,\"rollout_exits\":%d,\"passed\":%s}\n"),M->GapLandings,M->VertLandings,M->RolloutExits,M->GapLandings>0&&M->VertLandings>0&&M->RolloutExits>0?TEXT("true"):TEXT("false")),*(ReviewDirectory/TEXT("mega-checks.json")));
  FPlatformMisc::RequestExit(false);
 }
}
