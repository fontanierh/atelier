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
    /** -rider=<Name> plays as a BOTW character (BotwRider.h). */
    virtual UClass* GetDefaultPawnClassForController_Implementation(AController* Controller) override;
private:
    void SpawnFoxHunter(class AJapanWorld* World, class AWandererCharacter* Player);
    void SpawnBotwCamp(class AJapanWorld* World, class AWandererCharacter* Player);
};
