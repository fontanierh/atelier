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
    DynamicOwners.Reset(); InstalledOwners.Reset(); ExcludedParts.Reset(); Cached = FCollisionQueryParams();
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
    DynamicOwners.Add(Actor); Cached.AddIgnoredActor(Actor);
    TArray<UPrimitiveComponent*> Parts; Actor->GetComponents(Parts);
    for (auto* Part : Parts) Part->SetCollisionResponseToChannel(JapanGameplayCollision::Channel, ECR_Ignore);
}
void UJapanGameplayCollisionWorld::Removed(AActor* Actor)
{
    InstalledOwners.Remove(Actor);
    if (DynamicOwners.Remove(Actor)) Rebuild();
}
void UJapanGameplayCollisionWorld::Rebuild()
{
    Cached = FCollisionQueryParams();
    for (auto It = DynamicOwners.CreateIterator(); It; ++It)
        if (It->IsValid()) Cached.AddIgnoredActor(It->Get()); else It.RemoveCurrent();
    ExcludedParts.RemoveAll([](const auto& Part) { return !Part.IsValid(); });
    for (const auto& Part : ExcludedParts) Cached.AddIgnoredComponent(Part.Get());
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
FCollisionQueryParams UJapanGameplayCollisionWorld::Query(FName Tag, const TStatId& Stat, bool Complex) const
{
    FCollisionQueryParams Result = Cached;
    Result.TraceTag = Tag; Result.StatId = Stat; Result.bTraceComplex = Complex;
    return Result;
}
