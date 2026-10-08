#pragma once
#include "CoreMinimal.h"
class UWorld;
class AWandererCharacter;
namespace JapanVehicleQA
{
    bool Tick(UWorld* World,bool Server,const FString& Folder,FString& Error);
    bool Finalize(const FString& Folder,FString& Error);
    /** Test stimulus at the real terminal boundary, before the production predicate re-reads activity. */
    void BeforeBikePark(AWandererCharacter* Rider);
}
