#include "WandererCharacter.h"
#include "JapanWorld.h"
#include "SailboatComponent.h"
#include "SkateboardComponent.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/PrimitiveComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Dom/JsonObject.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/HUD.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Misc/CommandLine.h"
#include "Misc/App.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

struct FBuildingReviewState
{
 TSharedPtr<FJsonObject> Spec;
 TArray<TSharedPtr<FJsonValue>> Shots,Completed,Errors;
 TWeakObjectPtr<ACameraActor> Camera;
 TArray<uint8> SettingsBefore;
 FString SettingsPath,Id,File;
 int32 Index=0,Frame=0,Settle=10,DefaultSettle=10,InitialSettle=60;
 TSharedPtr<FJsonObject> Sightline;
 bool bRequested=false,bFinished=false,bSettingsExisted=false;
 double RequestTime=0,Started=0;
 int32 ProbeFailures=0;
 int32 Width=1920,Height=1080;
};

static bool WriteReviewJSON(const FString& File,const TSharedRef<FJsonObject>& Value)
{
 FString Text;FJsonSerializer::Serialize(Value,TJsonWriterFactory<>::Create(&Text));
 return FFileHelper::SaveStringToFile(Text,*File,FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

// Independent semantic checks against the live collision scene. Building parts are
// deliberately excluded from terrain support measurements, so roofs cannot masquerade as ground.
static int32 RunBuildingProbes(UWorld* World,AActor* Pawn,const TSharedPtr<FJsonObject>& Spec,const FString& Directory)
{
 const TArray<TSharedPtr<FJsonValue>>* Probes=nullptr;if(!Spec->TryGetArrayField(TEXT("probes"),Probes))return 0;
 TArray<UStaticMeshComponent*> Terrain;
 for(TActorIterator<AActor> It(World);It;++It)
 {
  TInlineComponentArray<UStaticMeshComponent*> Components;It->GetComponents(Components);
  for(auto* C:Components)if(C->GetStaticMesh())
  {
   const FString N=C->GetStaticMesh()->GetName();
   if(N==TEXT("Terrain")||N==TEXT("HD_Terrain")||N==TEXT("SW_Island")||N==TEXT("HD_NorthMountains"))Terrain.Add(C);
  }
 }
 FCollisionQueryParams Q(SCENE_QUERY_STAT(BuildingSemanticProbe),true,Pawn);
 TArray<TSharedPtr<FJsonValue>> Rows;int32 Failures=0;
 for(const auto& Value:*Probes)
 {
  auto Row=MakeShared<FJsonObject>();const TSharedPtr<FJsonObject>* Input=nullptr;
  FString Id,Kind;double Expected=0;
  const TArray<TSharedPtr<FJsonValue>>* XYZ=nullptr;
  bool Valid=Value->TryGetObject(Input)&&Input&&(*Input)->TryGetStringField(TEXT("id"),Id)&&(*Input)->TryGetStringField(TEXT("kind"),Kind)&&(*Input)->TryGetArrayField(TEXT("position"),XYZ)&&XYZ->Num()==3&&(*Input)->TryGetNumberField(TEXT("expected_z"),Expected)&&FMath::IsFinite(Expected);
  if(Valid)for(const auto& V:*XYZ){double N=0;Valid&=V->TryGetNumber(N)&&FMath::IsFinite(N);}
  if(!Valid){Row->SetStringField(TEXT("error"),TEXT("Invalid probe schema"));Row->SetBoolField(TEXT("passed"),false);++Failures;Rows.Add(MakeShared<FJsonValueObject>(Row));continue;}
  Row->Values=(*Input)->Values;
  const bool Landing=Kind==TEXT("walkable_landing"),Door=Kind==TEXT("closed_door");
  const bool Entry=Kind==TEXT("entry_tread_top")||Landing,Support=Kind==TEXT("ground_prop_foot")||Kind==TEXT("window_lower_edge")||Kind==TEXT("entry_tread_bottom");
  if(!Entry&&!Support&&!Door){Row->SetBoolField(TEXT("skipped"),true);Row->SetStringField(TEXT("reason"),TEXT("Unsupported probe kind"));Rows.Add(MakeShared<FJsonValueObject>(Row));continue;}
  const FVector Point=AJapanWorld::ToUE((*XYZ)[0]->AsNumber(),(*XYZ)[1]->AsNumber(),Expected);
  if(Door)
  {
   const TArray<TSharedPtr<FJsonValue>>* Normal=nullptr;bool Good=(*Input)->TryGetArrayField(TEXT("outward_direction"),Normal)&&Normal->Num()==3;
   FVector Out=FVector::ZeroVector;
   if(Good)
   {
    double Values[3]={};for(int I=0;I<3;++I)Good&=(*Normal)[I]->TryGetNumber(Values[I])&&FMath::IsFinite(Values[I]);
    if(Good)Out=FVector(Values[0],-Values[1],Values[2]).GetSafeNormal2D();
   }
   FHitResult DoorHit;FCollisionQueryParams Simple=Q;Simple.bTraceComplex=false;
   const bool Blocked=Good&&!Out.IsNearlyZero()&&World->LineTraceSingleByChannel(DoorHit,Point+Out*50,Point-Out*25,ECC_Pawn,Simple);
   FString ActualAsset,ExpectedAsset;(*Input)->TryGetStringField(TEXT("expected_mesh_asset"),ExpectedAsset);
   if(Blocked)
   {
    if(const auto* M=Cast<UStaticMeshComponent>(DoorHit.GetComponent());M&&M->GetStaticMesh())ActualAsset=M->GetStaticMesh()->GetName();
    Row->SetStringField(TEXT("mesh_asset"),ActualAsset);Row->SetNumberField(TEXT("instance_index"),DoorHit.Item);Row->SetNumberField(TEXT("door_centre_error_cm"),FVector::Dist(DoorHit.ImpactPoint,Point));
   }
   const bool Passed=Blocked&&FVector::Dist(DoorHit.ImpactPoint,Point)<=20&&(ExpectedAsset.IsEmpty()||ExpectedAsset==ActualAsset);
   Row->SetBoolField(TEXT("hit"),Blocked);Row->SetBoolField(TEXT("assessed"),true);Row->SetBoolField(TEXT("passed"),Passed);Row->SetStringField(TEXT("test"),TEXT("simple ECC_Pawn collision through the closed door centre"));
   if(!Passed){++Failures;UE_LOG(LogTemp,Warning,TEXT("BUILDING PROBE FAIL: %s closed door does not block pawn at expected plane"),*Id);}
   Rows.Add(MakeShared<FJsonValueObject>(Row));continue;
  }
  FHitResult Hit;bool Found=false;
  if(Entry)Found=World->LineTraceSingleByChannel(Hit,Point+FVector(0,0,5),Point-FVector(0,0,40),ECC_Visibility,Q);
  else for(auto* C:Terrain)
  {
   FHitResult H;
   if(C->LineTraceComponent(H,Point+FVector(0,0,50000),Point-FVector(0,0,50000),Q)&&(!Found||H.ImpactPoint.Z>Hit.ImpactPoint.Z)){Found=true;Hit=H;}
  }
  Row->SetBoolField(TEXT("hit"),Found);bool Passed=true;
  double Tolerance=5,Minimum=0,Maximum=0;(*Input)->TryGetNumberField(TEXT("tolerance_cm"),Tolerance);
  const bool HasMin=(*Input)->TryGetNumberField(TEXT("min_gap_cm"),Minimum),HasMax=(*Input)->TryGetNumberField(TEXT("max_gap_cm"),Maximum);
  const bool Assessed=Entry||HasMin||HasMax;Row->SetBoolField(TEXT("assessed"),Assessed);
  if(Found)
  {
   const double Gap=Point.Z-Hit.ImpactPoint.Z;
   Row->SetNumberField(TEXT("hit_z"),Hit.ImpactPoint.Z/100.);Row->SetNumberField(TEXT("gap_cm"),Gap);Row->SetNumberField(TEXT("instance_index"),Hit.Item);
   if(const auto* M=Cast<UStaticMeshComponent>(Hit.GetComponent());M&&M->GetStaticMesh())Row->SetStringField(TEXT("mesh_asset"),M->GetStaticMesh()->GetName());
   if(Entry)
   {
    Passed=FMath::Abs(Gap)<=FMath::Max(0.,Tolerance);
    // A visible tread is not enough: the pawn must stand on matching simple collision.
    FCollisionQueryParams Simple=Q;Simple.bTraceComplex=false;FHitResult PawnHit;
    const bool PawnSupport=World->LineTraceSingleByChannel(PawnHit,Point+FVector(0,0,5),Point-FVector(0,0,40),ECC_Pawn,Simple);
    Row->SetBoolField(TEXT("pawn_support_hit"),PawnSupport);
    if(PawnSupport)Row->SetNumberField(TEXT("pawn_support_gap_cm"),Point.Z-PawnHit.ImpactPoint.Z);
    Passed&=PawnSupport&&FMath::Abs(Point.Z-PawnHit.ImpactPoint.Z)<=FMath::Max(0.,Tolerance);
    if(Landing)
    {
     const auto* Capsule=Pawn->FindComponentByClass<UCapsuleComponent>();
     const auto* Movement=Pawn->FindComponentByClass<UCharacterMovementComponent>();
     const float Radius=Capsule?Capsule->GetScaledCapsuleRadius():0,Half=Capsule?Capsule->GetScaledCapsuleHalfHeight():0;
     const bool Walkable=PawnSupport&&Movement&&Movement->IsWalkable(PawnHit);
     // Upright capsule contact on an incline is above a point-ray floor by
     // R*(sec(theta)-1). Without this offset valid slopes falsely overlap.
     const float SlopeLift=Walkable?Radius*(1.f/FMath::Max(.1f,PawnHit.ImpactNormal.Z)-1.f):0.f;
     const FVector Center=PawnHit.ImpactPoint+FVector(0,0,Half+SlopeLift+3);
     const bool Clear=Capsule&&PawnSupport&&!World->OverlapBlockingTestByChannel(Center,FQuat::Identity,ECC_Pawn,FCollisionShape::MakeCapsule(Radius,Half),Simple);
     Row->SetNumberField(TEXT("actual_capsule_radius_cm"),Radius);Row->SetNumberField(TEXT("actual_capsule_half_height_cm"),Half);
     Row->SetBoolField(TEXT("walkable_support"),Walkable);Row->SetBoolField(TEXT("standing_capsule_clear"),Clear);
     Row->SetNumberField(TEXT("capsule_floor_clearance_cm"),3);Row->SetNumberField(TEXT("slope_contact_lift_cm"),SlopeLift);
     Passed&=Walkable&&Clear;
    }
   }
   if(HasMin&&Gap<Minimum)Passed=false;if(HasMax&&Gap>Maximum)Passed=false;
  }
  else if(Assessed)Passed=false;
  if(Assessed)Row->SetBoolField(TEXT("passed"),Passed);
  if(!Passed){++Failures;UE_LOG(LogTemp,Warning,TEXT("BUILDING PROBE FAIL: %s %s"),*Id,*Kind);}
  Rows.Add(MakeShared<FJsonValueObject>(Row));
 }
 auto Report=MakeShared<FJsonObject>();Report->SetBoolField(TEXT("passed"),Failures==0);Report->SetNumberField(TEXT("count"),Rows.Num());Report->SetNumberField(TEXT("failures"),Failures);Report->SetNumberField(TEXT("terrain_components"),Terrain.Num());Report->SetArrayField(TEXT("probes"),Rows);
 if(!WriteReviewJSON(Directory/TEXT("probes.json"),Report))return Failures+1;
 UE_LOG(LogTemp,Display,TEXT("BUILDING PROBES: %d probes, %d policy failures"),Rows.Num(),Failures);return Failures;
}

void AWandererCharacter::AdvanceBuildingReview(float)
{
 if(!BuildingReview)
 {
  BuildingReview=MakeShared<FBuildingReviewState>();auto& S=*BuildingReview;S.Started=FPlatformTime::Seconds();
  FParse::Value(FCommandLine::Get(),TEXT("resx="),S.Width);
  FParse::Value(FCommandLine::Get(),TEXT("resy="),S.Height);
  if(S.Width<=0||S.Height<=0)S.Errors.Add(MakeShared<FJsonValueString>(TEXT("Invalid requested screenshot dimensions")));
  FParse::Value(FCommandLine::Get(),TEXT("reviewdir="),ReviewDirectory);
  if(ReviewDirectory.IsEmpty())ReviewDirectory=FPaths::ProjectSavedDir()/TEXT("Screenshots/Buildings");
  IFileManager::Get().MakeDirectory(*ReviewDirectory,true);
  S.SettingsPath=FPaths::ProjectSavedDir()/TEXT("settings.txt");
  S.bSettingsExisted=FPaths::FileExists(S.SettingsPath);
  if(S.bSettingsExisted)FFileHelper::LoadFileToArray(S.SettingsBefore,*S.SettingsPath);
  FString Text;const TArray<TSharedPtr<FJsonValue>>* Shots=nullptr;
  if(!FFileHelper::LoadFileToString(Text,*BuildingReviewSpecPath)||!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text),S.Spec)||!S.Spec.IsValid()||!S.Spec->TryGetArrayField(TEXT("shots"),Shots)||Shots->IsEmpty())
   S.Errors.Add(MakeShared<FJsonValueString>(TEXT("Missing or invalid nonempty shots array")));
  else
  {
   S.Shots=*Shots;double Settle=10;S.Spec->TryGetNumberField(TEXT("settle_frames"),Settle);S.DefaultSettle=FMath::Clamp(FMath::RoundToInt(Settle),10,600);
   double Initial=60;S.Spec->TryGetNumberField(TEXT("initial_settle_frames"),Initial);S.InitialSettle=FMath::Clamp(FMath::RoundToInt(Initial),10,600);
   TSet<FString> IDs;
   for(int32 I=0;I<S.Shots.Num();++I)
   {
    const TSharedPtr<FJsonObject>* Shot=nullptr;FString Id;bool Valid=S.Shots[I]->TryGetObject(Shot)&&Shot&&(*Shot)->TryGetStringField(TEXT("id"),Id)&&!Id.IsEmpty();
    for(TCHAR C:Id)Valid&=FChar::IsAlnum(C)||C==TEXT('_')||C==TEXT('-');
    if(!Valid||IDs.Contains(Id)){S.Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("Invalid/duplicate shot id at index %d"),I)));continue;}
    IDs.Add(Id);
    for(const TCHAR* Key:{TEXT("camera_position"),TEXT("camera_target")})
    {
     const TArray<TSharedPtr<FJsonValue>>* A=nullptr;bool Good=(*Shot)->TryGetArrayField(Key,A)&&A->Num()==3;
     if(Good)for(const auto& V:*A){double N=0;Good&=V->TryGetNumber(N)&&FMath::IsFinite(N);}
     if(!Good)S.Errors.Add(MakeShared<FJsonValueString>(Id+TEXT(": invalid ")+Key));
    }
    if(FPaths::FileExists(ReviewDirectory/(Id+TEXT(".png"))))S.Errors.Add(MakeShared<FJsonValueString>(Id+TEXT(": output already exists; use a fresh directory")));
   }
  }
  if(S.Errors.IsEmpty())S.ProbeFailures=RunBuildingProbes(GetWorld(),this,S.Spec,ReviewDirectory);
  bCinematic=true;MoveIntent=FVector2D::ZeroVector;Skateboard->StowImmediately();Sailboat->StowImmediately();
  GetCharacterMovement()->StopMovementImmediately();GetCharacterMovement()->DisableMovement();SetActorHiddenInGame(true);SetActorEnableCollision(false);
  if(auto* PC=Cast<APlayerController>(Controller))
  {
   DisableInput(PC);if(PC->GetHUD())PC->GetHUD()->bShowHUD=false;
   S.Camera=GetWorld()->SpawnActor<ACameraActor>();if(S.Camera.IsValid())PC->SetViewTarget(S.Camera.Get());
  }
  if(!S.Camera.IsValid())S.Errors.Add(MakeShared<FJsonValueString>(TEXT("Could not create review camera/player view")));
  FApp::SetFixedDeltaTime(1./60.);FApp::SetUseFixedTimeStep(true);
  UE_LOG(LogTemp,Display,TEXT("BUILDING REVIEW START: %d shots"),S.Shots.Num());
 }
 auto& S=*BuildingReview;if(S.bFinished)return;
 auto Progress=[&](bool Finished)
 {
  auto P=MakeShared<FJsonObject>();P->SetBoolField(TEXT("complete"),Finished);P->SetNumberField(TEXT("completed"),S.Completed.Num());P->SetNumberField(TEXT("total"),S.Shots.Num());P->SetStringField(TEXT("last_id"),S.Id);P->SetNumberField(TEXT("elapsed_seconds"),FPlatformTime::Seconds()-S.Started);P->SetArrayField(TEXT("errors"),S.Errors);
  if(!WriteReviewJSON(ReviewDirectory/TEXT("progress.json"),P))UE_LOG(LogTemp,Error,TEXT("BUILDING REVIEW cannot write progress"));
 };
 auto Finish=[&]()
 {
  S.bFinished=true;TArray<uint8> After;
  if(S.ProbeFailures>0)S.Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%d native probe policies failed; see probes.json"),S.ProbeFailures)));
  const bool Exists=FPaths::FileExists(S.SettingsPath);if(Exists)FFileHelper::LoadFileToArray(After,*S.SettingsPath);
  const bool SameSettings=Exists==S.bSettingsExisted&&After==S.SettingsBefore;
  if(!SameSettings)S.Errors.Add(MakeShared<FJsonValueString>(TEXT("Saved settings changed during capture")));
  auto Manifest=MakeShared<FJsonObject>();Manifest->SetBoolField(TEXT("passed"),S.Errors.IsEmpty()&&S.Completed.Num()==S.Shots.Num());Manifest->SetBoolField(TEXT("settings_unchanged"),SameSettings);Manifest->SetStringField(TEXT("source"),BuildingReviewSpecPath);Manifest->SetStringField(TEXT("coordinates"),TEXT("Blender world metres; x east, y north, z up"));Manifest->SetArrayField(TEXT("completed_shots"),S.Completed);Manifest->SetArrayField(TEXT("errors"),S.Errors);Manifest->SetNumberField(TEXT("elapsed_seconds"),FPlatformTime::Seconds()-S.Started);
  if(!WriteReviewJSON(ReviewDirectory/TEXT("completed.json"),Manifest))S.Errors.Add(MakeShared<FJsonValueString>(TEXT("Could not write completed manifest")));
  auto Errors=MakeShared<FJsonObject>();Errors->SetArrayField(TEXT("errors"),S.Errors);WriteReviewJSON(ReviewDirectory/TEXT("errors.json"),Errors);Progress(true);
  UE_LOG(LogTemp,Display,TEXT("BUILDING REVIEW COMPLETE: %d/%d screenshots, %d errors"),S.Completed.Num(),S.Shots.Num(),S.Errors.Num());
  FPlatformMisc::RequestExitWithStatus(false,S.Errors.IsEmpty()?0:2);
 };
 if(!S.Errors.IsEmpty()||S.Index>=S.Shots.Num()){Finish();return;}
 const auto Shot=S.Shots[S.Index]->AsObject();
 if(S.Frame==0&&!S.bRequested)
 {
  S.Id=Shot->GetStringField(TEXT("id"));S.File=ReviewDirectory/(S.Id+TEXT(".png"));
  auto Position=[&](const TCHAR* Key){const auto& A=Shot->GetArrayField(Key);return AJapanWorld::ToUE(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());};
  const FVector Eye=Position(TEXT("camera_position")),Aim=Position(TEXT("camera_target"));
  if(auto* PC=Cast<APlayerController>(Controller))if(PC->PlayerCameraManager)PC->PlayerCameraManager->SetGameCameraCutThisFrame();
  if(Eye.Equals(Aim,.01)){S.Errors.Add(MakeShared<FJsonValueString>(S.Id+TEXT(": camera and target coincide")));Finish();return;}
  double FOV=65,Settle=S.DefaultSettle;Shot->TryGetNumberField(TEXT("fov"),FOV);Shot->TryGetNumberField(TEXT("settle_frames"),Settle);
  S.Settle=FMath::Clamp(FMath::RoundToInt(Settle),10,600);if(S.Index==0)S.Settle=FMath::Max(S.Settle,S.InitialSettle);
  // Record possible occlusion without moving the authored review camera or hiding world geometry.
  FHitResult Sight;FCollisionQueryParams Q(SCENE_QUERY_STAT(BuildingReviewSight),true,this);
  const bool Blocked=GetWorld()->LineTraceSingleByChannel(Sight,Eye,Aim,ECC_Visibility,Q);
  S.Sightline=MakeShared<FJsonObject>();S.Sightline->SetBoolField(TEXT("blocking_hit"),Blocked);S.Sightline->SetNumberField(TEXT("camera_to_target_cm"),FVector::Dist(Eye,Aim));
  if(Blocked)
  {
   S.Sightline->SetStringField(TEXT("actor"),GetNameSafe(Sight.GetActor()));S.Sightline->SetStringField(TEXT("component"),Sight.GetComponent()?Sight.GetComponent()->GetReadableName():TEXT("none"));
   if(const auto* HitMesh=Cast<UStaticMeshComponent>(Sight.GetComponent());HitMesh&&HitMesh->GetStaticMesh())
    S.Sightline->SetStringField(TEXT("mesh_asset"),HitMesh->GetStaticMesh()->GetName());
   S.Sightline->SetNumberField(TEXT("instance_index"),Sight.Item);S.Sightline->SetNumberField(TEXT("camera_to_hit_cm"),Sight.Distance);
  }
  S.Camera->SetActorLocationAndRotation(Eye,(Aim-Eye).Rotation());S.Camera->GetCameraComponent()->SetFieldOfView(FMath::Clamp(float(FOV),25.f,110.f));
  // Keep proximity-driven residents active for this building, without a visible/colliding player.
  SetActorLocation(Aim+FVector(0,0,300),false,nullptr,ETeleportType::TeleportPhysics);
  Progress(false);
 }
 if(!S.bRequested)
 {
  if(++S.Frame>=S.Settle)
  {
   FScreenshotRequest::RequestScreenshot(S.File,false,false);S.bRequested=true;S.RequestTime=FPlatformTime::Seconds();
  }
  return;
 }
 // Screenshot save is asynchronous with the gameplay tick. Never advance until the actual PNG is complete.
 TArray<uint8> Bytes;
 if(FPaths::FileExists(S.File)&&FFileHelper::LoadFileToArray(Bytes,*S.File)&&Bytes.Num()>24)
 {
  // A concurrent writer can expose the header before the final IEND chunk.
  if(Bytes.Num()<36||Bytes[Bytes.Num()-8]!=73||Bytes[Bytes.Num()-7]!=69||Bytes[Bytes.Num()-6]!=78||Bytes[Bytes.Num()-5]!=68)
  {
   if(FPlatformTime::Seconds()-S.RequestTime>20.){S.Errors.Add(MakeShared<FJsonValueString>(S.Id+TEXT(": incomplete PNG write timeout")));Finish();}return;
  }
  auto U32=[&](int I){return(uint32(Bytes[I])<<24)|(uint32(Bytes[I+1])<<16)|(uint32(Bytes[I+2])<<8)|uint32(Bytes[I+3]);};
  const bool PNG=Bytes[0]==137&&Bytes[1]==80&&Bytes[2]==78&&Bytes[3]==71;
  if(!PNG||U32(16)!=uint32(S.Width)||U32(20)!=uint32(S.Height)){S.Errors.Add(MakeShared<FJsonValueString>(FString::Printf(TEXT("%s: screenshot is not requested %dx%d PNG"),*S.Id,S.Width,S.Height)));Finish();return;}
  auto Done=MakeShared<FJsonObject>();Done->Values=Shot->Values;Done->SetStringField(TEXT("file"),S.File);Done->SetObjectField(TEXT("sightline"),S.Sightline);Done->SetNumberField(TEXT("bytes"),Bytes.Num());Done->SetNumberField(TEXT("settled_frames"),S.Settle);S.Completed.Add(MakeShared<FJsonValueObject>(Done));
  UE_LOG(LogTemp,Display,TEXT("BUILDING REVIEW SHOT %d/%d %s"),S.Index+1,S.Shots.Num(),*S.Id);
  ++S.Index;S.Frame=0;S.bRequested=false;Progress(false);
  if(S.Index>=S.Shots.Num())Finish();
 }
 else if(FPlatformTime::Seconds()-S.RequestTime>20.){S.Errors.Add(MakeShared<FJsonValueString>(S.Id+TEXT(": screenshot write timeout")));Finish();}
}
