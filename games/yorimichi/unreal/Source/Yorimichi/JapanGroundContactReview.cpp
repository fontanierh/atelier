#include "WandererCharacter.h"
#include "Camera/CameraComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

// Opt-in deterministic support fixtures, never spawned during ordinary play.
void AWandererCharacter::AdvanceGroundContactReview(float Dt)
{
    const float Before=GroundReviewTime;GroundReviewTime+=Dt;
    const int32 Stage=int32(GroundReviewTime/3.f);
    if(Stage>=7)
    {
        FFileHelper::SaveStringToFile(GroundReviewTelemetry,*(ReviewDirectory/TEXT("ground-contact.csv")));
        UE_LOG(LogTemp,Display,TEXT("GROUND CONTACT QA COMPLETE"));
        FPlatformMisc::RequestExit(false);return;
    }
    if(Stage!=GroundReviewStage)
    {
        if(GroundReviewStage<0)
        {
            GroundReviewAnchor=GetActorLocation()+FVector(0,0,10000);
            SetMouseReleased(true);
            FollowCamera->DetachFromComponent(FDetachmentTransformRules::KeepWorldTransform);
        }
        GroundReviewStage=Stage;
        const FVector Center=Stage==6?FVector(97900,-31000,3190.1):GroundReviewAnchor+FVector(Stage*600,0,0);
        const FRotator Slopes[]={FRotator::ZeroRotator,FRotator(20,0,0),FRotator(-20,0,0),FRotator(0,0,20),FRotator(0,0,-20),FRotator::ZeroRotator};
        auto Pad=[&](FVector Top,FVector Scale,FRotator R)
        {
            auto* A=GetWorld()->SpawnActor<AStaticMeshActor>(Top-R.RotateVector(FVector(0,0,10)),R);
            auto* M=A->GetStaticMeshComponent();M->SetMobility(EComponentMobility::Movable);
            M->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Engine/BasicShapes/Cube.Cube")));
            M->SetWorldScale3D(Scale);M->SetCollisionProfileName(TEXT("BlockAll"));
        };
        if(Stage==5)
        {
            Pad(Center+FVector(0,-100,0),FVector(4,2,.2),FRotator::ZeroRotator);
            Pad(Center+FVector(0,100,12),FVector(4,2,.2),FRotator::ZeroRotator);
        }
        else if(Stage<6)Pad(Center,FVector(4,4,.2),Slopes[Stage]);
        SetActorLocation(Center+FVector(0,0,GetCapsuleComponent()->GetScaledCapsuleHalfHeight()+30),false,nullptr,ETeleportType::TeleportPhysics);
        SetActorRotation(FRotator::ZeroRotator);GetCharacterMovement()->StopMovementImmediately();
        GetCharacterMovement()->SetMovementMode(MOVE_Falling);
        FollowCamera->SetWorldLocation(Center+(Stage==6?FVector(233,-233,106):FVector(260,-340,180)));
        FollowCamera->SetWorldRotation((Center+FVector(0,0,70)-FollowCamera->GetComponentLocation()).Rotation());
    }
    if(FMath::Fmod(Before,3.f)<2.5f && FMath::Fmod(GroundReviewTime,3.f)>=2.5f)
        FScreenshotRequest::RequestScreenshot(ReviewDirectory/FString::Printf(TEXT("support_%d.png"),Stage),false,false);
}

void AWandererCharacter::RecordGroundContactPose()
{
    if(GroundReviewStage<0 || GroundReviewTime>=21 || FMath::Fmod(GroundReviewTime,3.f)<2.f)return;
    const auto* Mesh=GetMesh();
    const auto& Ref=Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    const FVector ForwardCS=Mesh->GetComponentTransform().InverseTransformVectorNoScale(GetActorForwardVector());
    const FVector RightCS=Mesh->GetComponentTransform().InverseTransformVectorNoScale(GetActorRightVector());
    for(int32 Side=0;Side<2;++Side)
    {
        const FName Name=Side?TEXT("foot_R"):TEXT("foot_L");
        const int32 Index=Ref.FindBoneIndex(Name);
        FTransform Neutral=Ref.GetRefBonePose()[Index];
        for(int32 Parent=Ref.GetParentIndex(Index);Parent!=INDEX_NONE;Parent=Ref.GetParentIndex(Parent))Neutral=Neutral*Ref.GetRefBonePose()[Parent];
        const FTransform World=Mesh->GetSocketTransform(Name);
        for(int32 Point=0;Point<5;++Point)
        {
            const float ForwardOffset=Point==1?15.1f:Point==2?-5.1f:0.f;
            FVector Sole=Neutral.GetLocation()+ForwardCS*ForwardOffset+RightCS*(Point==3?5.9f:Point==4?-5.9f:0.f);
            Sole.Z=.65;
            const FVector Position=World.TransformPosition(Neutral.InverseTransformPosition(Sole));
            FHitResult Hit;FCollisionQueryParams Query(SCENE_QUERY_STAT(GroundContactQA),false,this);
            const bool Found=GetWorld()->LineTraceSingleByChannel(Hit,Position+FVector(0,0,40),Position-FVector(0,0,60),ECC_Visibility,Query);
            const double Gap=Found?FVector::DotProduct(Position-Hit.ImpactPoint,Hit.ImpactNormal):999.;
            GroundReviewTelemetry+=FString::Printf(TEXT("%d,%.5f,%d,%d,%.5f,%d\n"),GroundReviewStage,GroundReviewTime,Side,Point,Gap,GetCharacterMovement()->IsFalling()?1:0);
        }
    }
}
