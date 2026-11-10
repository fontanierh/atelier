#include "JapanGameplayCollisionWorld.h"
#include "JapanGameplayCollision.h"
#include "Components/PrimitiveComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"

void UJapanGameplayCollisionWorld::Initialize(FSubsystemCollectionBase& Collection)
{
    Super::Initialize(Collection);
    SpawnHandle = GetWorld()->AddOnActorSpawnedHandler(FOnActorSpawned::FDelegate::CreateUObject(this, &ThisClass::Spawned));
    DestroyHandle = GetWorld()->AddOnActorDestroyedHandler(FOnActorDestroyed::FDelegate::CreateUObject(this, &ThisClass::Removed));
    RemoveHandle = GetWorld()->AddOnActorRemovedFromWorldHandler(FOnActorRemovedFromWorld::FDelegate::CreateUObject(this, &ThisClass::Removed));
    for (TActorIterator<AActor> It(GetWorld()); It; ++It) Spawned(*It);
}
void UJapanGameplayCollisionWorld::Deinitialize()
{
    GetWorld()->RemoveOnActorSpawnedHandler(SpawnHandle);
    GetWorld()->RemoveOnActorDestroyedHandler(DestroyHandle);
    GetWorld()->RemoveOnActorRemovedFromWorldHandler(RemoveHandle);
    DynamicOwners.Reset(); InstalledOwners.Reset(); ExcludedParts.Reset();
    Cached = FCollisionQueryParams(); bDirty = false;
    Super::Deinitialize();
}
void UJapanGameplayCollisionWorld::Spawned(AActor* Actor)
{
    if (!Actor) return;
    // UE sends OnActorSpawned after BeginPlay. JapanWorld completes Install in
    // BeginPlay, so that late notification must not undo its certified channels.
    if (InstalledOwners.Contains(Actor)) return;
    // A newly spawned actor is dynamic until static-world Install certifies its
    // final authored class/mobility. Deferred constructors may add parts later.
    DynamicOwners.Add(Actor);
    if (!bDirty) Cached.AddIgnoredActor(Actor);
    TArray<UPrimitiveComponent*> Parts; Actor->GetComponents(Parts);
    for (auto* Part : Parts) Part->SetCollisionResponseToChannel(JapanGameplayCollision::Channel, ECR_Ignore);
}
void UJapanGameplayCollisionWorld::Removed(AActor* Actor)
{
    if (!Actor) return;
    const bool bWasInstalled = InstalledOwners.Remove(Actor) > 0;
    const bool bWasDynamic = DynamicOwners.Remove(Actor) > 0;
    if (bWasDynamic || (bWasInstalled && !ExcludedParts.IsEmpty())) bDirty = true;
}
void UJapanGameplayCollisionWorld::RemoveFixed(AActor* Actor)
{
    Removed(Actor);
}
void UJapanGameplayCollisionWorld::Rebuild()
{
    Cached = FCollisionQueryParams();
    for (auto It = DynamicOwners.CreateIterator(); It; ++It)
        if (It->IsValid()) Cached.AddIgnoredActor(It->Get()); else It.RemoveCurrent();
    for (auto It = ExcludedParts.CreateIterator(); It; ++It)
        if (It->IsValid()) Cached.AddIgnoredComponent(It->Get()); else It.RemoveCurrent();
    bDirty = false;
}
void UJapanGameplayCollisionWorld::Install()
{
    DynamicOwners.Reset(); InstalledOwners.Reset(); ExcludedParts.Reset();
    for (TActorIterator<AActor> It(GetWorld()); It; ++It)
    {
        const bool FixedOwner = JapanGameplayCollision::IsFixed(*It);
        if (FixedOwner) InstalledOwners.Add(*It);
        if (!FixedOwner) DynamicOwners.Add(*It);
        TArray<UPrimitiveComponent*> Parts; It->GetComponents(Parts);
        for (auto* Part : Parts)
        {
            const bool Fixed = JapanGameplayCollision::IsFixed(Part);
            if (FixedOwner && !Fixed) ExcludedParts.Add(Part);
            Part->SetCollisionResponseToChannel(JapanGameplayCollision::Channel,
                Fixed && Part->GetCollisionResponseToChannel(ECC_Visibility) == ECR_Block ? ECR_Block : ECR_Ignore);
        }
    }
    Rebuild();
}
void UJapanGameplayCollisionWorld::InstallFixed(AActor* Actor)
{
    if (!Actor || !JapanGameplayCollision::IsFixed(Actor)) return;
    InstalledOwners.Add(Actor);
    if (DynamicOwners.Remove(Actor) > 0) bDirty = true;
    TArray<UPrimitiveComponent*> Parts; Actor->GetComponents(Parts);
    for (auto* Part : Parts)
    {
        const bool Fixed = JapanGameplayCollision::IsFixed(Part);
        if (!Fixed)
        {
            bool bAlready = false;
            ExcludedParts.Add(Part, &bAlready);
            if (!bAlready) bDirty = true;
        }
        Part->SetCollisionResponseToChannel(JapanGameplayCollision::Channel,
            Fixed && Part->GetCollisionResponseToChannel(ECC_Visibility) == ECR_Block ? ECR_Block : ECR_Ignore);
    }
}
FCollisionQueryParams UJapanGameplayCollisionWorld::Query(FName Tag, const TStatId& Stat, bool Complex) const
{
    if (bDirty) const_cast<UJapanGameplayCollisionWorld*>(this)->Rebuild();
    FCollisionQueryParams Result = Cached;
    Result.TraceTag = Tag; Result.StatId = Stat; Result.bTraceComplex = Complex;
    return Result;
}
