#pragma once
#include "CoreMinimal.h"
#include "CollisionQueryParams.h"
#include "Subsystems/WorldSubsystem.h"
#include "JapanGameplayCollisionWorld.generated.h"
class UPrimitiveComponent;

/** Cached dynamic-owner exclusions survive components added after actor spawn. */
UCLASS()
class UJapanGameplayCollisionWorld : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    void Install();
    FCollisionQueryParams Query(FName Tag, const TStatId& Stat, bool Complex) const;
protected:
    virtual bool DoesSupportWorldType(const EWorldType::Type Type) const override
    { return Type == EWorldType::Game || Type == EWorldType::PIE; }
private:
    friend class FJapanFixedCollisionTest;
    void Spawned(AActor* Actor);
    void Removed(AActor* Actor);
    void Rebuild();
    FDelegateHandle SpawnHandle, DestroyHandle, RemoveHandle;
    TSet<TWeakObjectPtr<AActor>> DynamicOwners;
    TSet<TWeakObjectPtr<AActor>> InstalledOwners;
    TArray<TWeakObjectPtr<UPrimitiveComponent>> ExcludedParts;
    FCollisionQueryParams Cached;
};
