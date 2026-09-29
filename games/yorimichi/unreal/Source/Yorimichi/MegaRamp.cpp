#include "MegaRamp.h"
#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
AMegaRamp::AMegaRamp(){RootComponent=CreateDefaultSubobject<USceneComponent>(TEXT("Root"));}
void AMegaRamp::Initialize(const TSharedPtr<FJsonObject>& Data)
{
 const auto& O=Data->GetArrayField(TEXT("origin"));SetActorLocation(FVector(O[0]->AsNumber()*100,-O[1]->AsNumber()*100,O[2]->AsNumber()*100));
 HalfWidth=Data->GetNumberField(TEXT("width"))*50;
 for(const auto& A:Data->GetArrayField(TEXT("profiles")))
 {
  FMegaSection P;float Length=0;
  for(const auto& V:A->AsArray()) {const auto& XY=V->AsArray();FVector2D Q(XY[0]->AsNumber()*100,XY[1]->AsNumber()*100);if(!P.Points.IsEmpty())Length+=(Q-P.Points.Last()).Size();P.Points.Add(Q);P.Lengths.Add(Length);}
  Sections.Add(MoveTemp(P));
 }
 for(const auto& V:Data->GetArrayField(TEXT("rollout")))
 {
  const auto& A=V->AsArray();FVector P(A[0]->AsNumber()*100,-A[1]->AsNumber()*100,A[2]->AsNumber()*100);
  RolloutLengths.Add(RolloutPoints.IsEmpty()?0:RolloutLengths.Last()+FVector::Dist(P,RolloutPoints.Last()));RolloutPoints.Add(P);
 }
 auto* Mesh=NewObject<UStaticMeshComponent>(this,TEXT("Ramp"));Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,TEXT("/Game/Japan/Assets/Mega_Ramp.Mega_Ramp")));
 Mesh->SetupAttachment(RootComponent);Mesh->SetCollisionEnabled(ECollisionEnabled::QueryOnly);Mesh->SetCollisionResponseToAllChannels(ECR_Block);Mesh->SetCollisionResponseToChannel(ECC_Camera,ECR_Block);Mesh->RegisterComponent();
 UE_LOG(LogTemp,Display,TEXT("MEGA MESH bounds=%s extent=%s scale=%s"),*Mesh->Bounds.Origin.ToString(),*Mesh->Bounds.BoxExtent.ToString(),*Mesh->GetComponentScale().ToString());
}
FVector AMegaRamp::Sample(int32 Section,float S,float Lateral,FVector& T,FVector& N) const
{
 const auto& P=Sections[Section];int32 I=1;while(I<P.Lengths.Num()-1&&P.Lengths[I]<S)++I;
 const float U=FMath::Clamp((S-P.Lengths[I-1])/(P.Lengths[I]-P.Lengths[I-1]),0.f,1.f);
 const FVector2D Q=FMath::Lerp(P.Points[I-1],P.Points[I],U),D=(P.Points[I]-P.Points[I-1]).GetSafeNormal();
 T=FVector(D.X,0,D.Y);N=FVector(-D.Y,0,D.X);
 return GetActorLocation()+FVector(Q.X,Lateral,Q.Y);
}
bool AMegaRamp::CrossSurface(const FVector& From,const FVector& To,int32& Section,float& S,float& Alpha) const
{
 const FVector A=From-GetActorLocation(),B=To-GetActorLocation();bool Found=false;Alpha=2;
 for(int32 K=0;K<Sections.Num();++K){const auto& P=Sections[K];for(int32 I=1;I<P.Points.Num();++I){
  FVector2D C=P.Points[I-1],D=P.Points[I]-C,N(-D.Y,D.X);N.Normalize();
  float DA=FVector2D::DotProduct(FVector2D(A.X,A.Z)-C,N),DB=FVector2D::DotProduct(FVector2D(B.X,B.Z)-C,N);
  if(DA<-.1f||DB>0||DA-DB<KINDA_SMALL_NUMBER)continue;
  float T=DA/(DA-DB);FVector Q=FMath::Lerp(A,B,T);float U=FVector2D::DotProduct(FVector2D(Q.X,Q.Z)-C,D)/D.SizeSquared();
  if(T<Alpha&&U>=0&&U<=1&&FMath::Abs(Q.Y)<HalfWidth-12){Found=true;Alpha=T;Section=K;S=FMath::Lerp(P.Lengths[I-1],P.Lengths[I],U);}
 }}return Found;
}

FVector AMegaRamp::SampleRollout(float S,FVector& T) const
{
 int32 I=1;while(I<RolloutLengths.Num()-1&&RolloutLengths[I]<S)++I;
 T=(RolloutPoints[I]-RolloutPoints[I-1]).GetSafeNormal();
 float U=FMath::Clamp((S-RolloutLengths[I-1])/(RolloutLengths[I]-RolloutLengths[I-1]),0.f,1.f);
 return GetActorLocation()+FMath::Lerp(RolloutPoints[I-1],RolloutPoints[I],U);
}
