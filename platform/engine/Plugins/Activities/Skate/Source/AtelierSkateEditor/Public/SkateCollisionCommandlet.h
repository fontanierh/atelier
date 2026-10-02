#pragma once
#include "CoreMinimal.h"
#include "Commandlets/Commandlet.h"
#include "SkateCollisionCommandlet.generated.h"
/** -run=SkateCollision -Map=/Game/Map -Catalog=/Game/SkateNative/DA_Collision [-ValidateOnly] [-Report=...] */
UCLASS()
class ATELIERSKATEEDITOR_API USkateCollisionCommandlet : public UCommandlet
{
    GENERATED_BODY()
public:
    USkateCollisionCommandlet();
    virtual int32 Main(const FString& Params) override;
};
