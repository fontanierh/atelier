#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "MegaRamp.generated.h"
class FJsonObject;
struct FMegaSection { TArray<FVector2D> Points; TArray<float> Lengths; };
UCLASS()
class YORIMICHI_API AMegaRamp : public AActor
{
    GENERATED_BODY()
public:
    AMegaRamp();
    void Initialize(const TSharedPtr<FJsonObject>& Data);
    TArray<FMegaSection> Sections;
    TArray<FVector> RolloutPoints;
    TArray<float> RolloutLengths;
    FVector SampleRollout(float S,FVector& Tangent) const;
    float HalfWidth=400.f;
    FVector Sample(int32 Section,float S,float Lateral,FVector& Tangent,FVector& Normal) const;
    bool CrossSurface(const FVector& From,const FVector& To,int32& Section,float& S,float& Alpha) const;
    FVector LadderBottom() const { return GetActorLocation()+FVector(-205,555,0); }
    FVector DeckStart() const { return GetActorLocation()+FVector(-180,0,1070); }
};
