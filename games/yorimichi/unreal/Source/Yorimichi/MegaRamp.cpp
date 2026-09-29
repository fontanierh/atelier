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
 UE_LOG(LogTemp,Display,TEXT("MEGA MESH bounds=%s extent=%s scale=%s"),*Mesh->Bounds.Origin.ToString(),*Mesh->Bounds.BoxExtent.ToString(),*Mesh->GetComponentScale().ToString());
}
