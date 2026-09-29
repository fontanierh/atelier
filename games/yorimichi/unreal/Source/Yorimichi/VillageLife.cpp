#include "VillageLife.h"
#include "JapanWorld.h"
#include "WandererDefinition.h"
#include "Animation/AnimSequence.h"
#include "Animation/BlendSpace.h"
#include "Animation/AnimSingleNodeInstance.h"
#include "Components/SkeletalMeshComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Engine/World.h"
#include "Dom/JsonObject.h"

AVillageLife::AVillageLife()
{
    PrimaryActorTick.bCanEverTick=true;
    PrimaryActorTick.TickInterval=1.f/30.f;
    RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
}

void AVillageLife::Initialize(AJapanWorld* Landscape,const TSharedPtr<FJsonObject>& Village)
{
    Ground=Landscape;
    Definition=LoadObject<UWandererDefinition>(nullptr,TEXT("/Game/Wanderer/DA_Wanderer.DA_Wanderer"));
    UMaterialInterface* Palette=LoadObject<UMaterialInterface>(nullptr,TEXT("/Game/Japan/Materials/M_VillageResident.M_VillageResident"));
    if (!Definition || !Definition->Mesh || !Definition->Locomotion || !Palette) { SetActorTickEnabled(false);return; }
    const TArray<TSharedPtr<FJsonValue>>* Specs=nullptr;
    if (!Village->TryGetArrayField(TEXT("residents"),Specs)) {SetActorTickEnabled(false);return;}
    auto Position=[](const TArray<TSharedPtr<FJsonValue>>& A){return AJapanWorld::ToUE(A[0]->AsNumber(),A[1]->AsNumber(),A[2]->AsNumber());};
    for (const auto& Value:*Specs)
    {
        const auto& S=Value->AsObject();
        auto* Mesh=NewObject<USkeletalMeshComponent>(this);
        Mesh->SetupAttachment(RootComponent);Mesh->SetSkeletalMeshAsset(Definition->Mesh);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetCanEverAffectNavigation(false);
        Mesh->VisibilityBasedAnimTickOption=EVisibilityBasedAnimTickOption::OnlyTickPoseWhenRendered;
        Mesh->SetWorldLocationAndRotation(Position(S->GetArrayField(TEXT("position"))),FRotator(0,-S->GetNumberField(TEXT("yaw")),0));
        Mesh->SetWorldScale3D(FVector(S->GetNumberField(TEXT("scale"))));
        Mesh->SetCullDistance(18000.f);
        Mesh->RegisterComponent();
        auto* Material=UMaterialInstanceDynamic::Create(Palette,this);
        const auto& C=S->GetArrayField(TEXT("colour"));
        Material->SetVectorParameterValue(TEXT("ClothTint"),FLinearColor(C[0]->AsNumber(),C[1]->AsNumber(),C[2]->AsNumber()));
        Mesh->SetMaterial(0,Material);
        const FString Action=S->GetStringField(TEXT("action"));
        if (Action==TEXT("Walk"))
        {
            WalkA=Position(S->GetArrayField(TEXT("position")));
            WalkB=Position(S->GetArrayField(TEXT("destination")));
            Mesh->PlayAnimation(Definition->Locomotion,true);
        }
        else if (UAnimSequence* Clip=Definition->FindAction(FName(*Action)))
        {
            Mesh->PlayAnimation(Clip,true);
            Mesh->SetPlayRate(Action==TEXT("Interact")?.35f:.75f);
            Mesh->SetPosition(.4f*Residents.Num(),false);
        }
        Residents.Add(Mesh);
    }
    UE_LOG(LogTemp,Display,TEXT("Village life: %d cosmetic residents"),Residents.Num());
}

void AVillageLife::Tick(float Dt)
{
    Super::Tick(Dt);
    if (Residents.IsEmpty()) return;
    const auto* Camera=UGameplayStatics::GetPlayerCameraManager(this,0);
    const bool Near=Camera && FVector::DistSquared(Camera->GetCameraLocation(),Residents[0]->GetComponentLocation())<FMath::Square(16000.f);
    if (Near!=bActive)
    {
        bActive=Near;SetActorTickInterval(Near?1.f/30.f:1.f);
        for (const auto& Resident:Residents) Resident->bPauseAnims=!Near;
    }
    if (!Near) return;
    Elapsed+=Dt;
    // A slow stroll on a household apron, with long unequal rests at each end.
    // The return trip uses the same clear path and turns while standing.
    auto* Walker=Residents.Last().Get();
    auto* Animation=Walker->GetSingleNodeInstance();
    if (!Animation || !Cast<UBlendSpace>(Animation->GetCurrentAsset())) return;
    const float T=FMath::Fmod(Elapsed,40.f);
    const bool Outward=T<20.f;
    const float U=FMath::Clamp((T-(Outward?5.f:25.f))/7.f,0.f,1.f);
    const float Smooth=U*U*(3.f-2.f*U);
    const float Alpha=Outward?Smooth:1.f-Smooth;
    FVector P=FMath::Lerp(WalkA,WalkB,Alpha);
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(VillageResident),false,this);
    if (GetWorld()->LineTraceSingleByChannel(Hit,P+FVector(0,0,100),P-FVector(0,0,160),ECC_Visibility,Params)) P.Z=Hit.ImpactPoint.Z+1.5f;
    Walker->SetWorldLocation(P);
    const float Speed=(WalkB-WalkA).Size2D()*6.f*U*(1.f-U)/7.f;
    Animation->SetBlendSpacePosition(FVector(Speed,0,0));
    const FVector Direction=Outward?WalkB-WalkA:WalkA-WalkB;
    FRotator Target=Direction.Rotation();Target.Yaw-=90.f;Target.Pitch=0.f;
    Walker->SetWorldRotation(FMath::RInterpTo(Walker->GetComponentRotation(),Target,Dt,2.0f));
}
