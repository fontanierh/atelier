#include "MegaRamp.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
AMegaRamp::AMegaRamp(){RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));}
void AMegaRamp::Initialize(const TSharedPtr<FJsonObject>& Data)
{
 const auto& O=Data->GetArrayField(TEXT("origin"));SetActorLocation(FVector(O[0]->AsNumber()*100,-O[1]->AsNumber()*100,O[2]->AsNumber()*100));
 auto* Mesh=NewObject<UStaticMeshComponent>(this,TEXT("Ramp"));Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Game/Japan/Assets/Mega_Ramp.Mega_Ramp")));
 Mesh->SetupAttachment(RootComponent);Mesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Mesh->SetCollisionResponseToAllChannels(ECR_Block);Mesh->SetCollisionResponseToChannel(ECC_Camera,ECR_Block);Mesh->RegisterComponent();
 // The seams and coping are look only: a wheel never catches on them (Mega_Ramp alone is ridden).
 auto* Trim=NewObject<UStaticMeshComponent>(this,TEXT("Trim"));Trim->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Game/Japan/Assets/Mega_Trim.Mega_Trim")));
 Trim->SetupAttachment(RootComponent);Trim->SetCollisionEnabled(ECollisionEnabled::NoCollision);Trim->RegisterComponent();
 bGameplayReady = Mesh->GetStaticMesh() != nullptr && Trim->GetStaticMesh() != nullptr;
 UE_LOG(LogTemp,Display,TEXT("MEGA MESH bounds=%s extent=%s scale=%s trim=%d"),*Mesh->Bounds.Origin.ToString(),*Mesh->Bounds.BoxExtent.ToString(),*Mesh->GetComponentScale().ToString(),Trim->GetStaticMesh()!=nullptr);
}
