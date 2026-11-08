#include "MegaRamp.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
AMegaRamp::AMegaRamp(){RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));}
UStaticMeshComponent* AMegaRamp::MakePiece(UObject* Outer, USceneComponent* Parent, bool bTrim)
{
 auto* C=NewObject<UStaticMeshComponent>(Outer,bTrim?TEXT("Trim"):TEXT("Ramp"));
 C->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,bTrim?TEXT("/Game/Japan/Assets/Mega_Trim.Mega_Trim"):TEXT("/Game/Japan/Assets/Mega_Ramp.Mega_Ramp")));
 C->SetupAttachment(Parent);
 if(bTrim) C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
 else {C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);C->SetCollisionResponseToAllChannels(ECR_Block);C->SetCollisionResponseToChannel(ECC_Camera,ECR_Block);}
 return C;
}
void AMegaRamp::Initialize(const TSharedPtr<FJsonObject>& Data)
{
 const auto& O=Data->GetArrayField(TEXT("origin"));SetActorLocation(FVector(O[0]->AsNumber()*100,-O[1]->AsNumber()*100,O[2]->AsNumber()*100));
 auto* Mesh=MakePiece(this,RootComponent,false);Mesh->RegisterComponent();
 // The seams and coping are look only: a wheel never catches on them (Mega_Ramp alone is ridden).
 auto* Trim=MakePiece(this,RootComponent,true);Trim->RegisterComponent();
 bGameplayReady = Mesh->GetStaticMesh() != nullptr && Trim->GetStaticMesh() != nullptr;
 UE_LOG(LogTemp,Display,TEXT("MEGA MESH bounds=%s extent=%s scale=%s trim=%d"),*Mesh->Bounds.Origin.ToString(),*Mesh->Bounds.BoxExtent.ToString(),*Mesh->GetComponentScale().ToString(),Trim->GetStaticMesh()!=nullptr);
}
