#pragma once
#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "JapanGameMode.generated.h"

UCLASS()
class YORIMICHI_API AJapanGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    AJapanGameMode();
    virtual void BeginPlay() override;
private:
    void SpawnFoxHunter(class AJapanWorld* World, class AWandererCharacter* Player);
};
