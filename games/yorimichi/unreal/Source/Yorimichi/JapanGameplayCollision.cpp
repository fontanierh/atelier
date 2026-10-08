#include "JapanGameplayCollision.h"
#include "JapanGameplayCollisionWorld.h"
#include "JapanWorld.h"
#include "SkatePark.h"
#include "MegaRamp.h"
#include "SuperUltraMegaPark.h"
#include "Hippodrome.h"
#include "Components/PrimitiveComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/StaticMeshActor.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/SecureHash.h"

bool JapanGameplayCollision::IsFixed(const AActor* Actor)
{
    if (!Actor || Actor->ActorHasTag(TEXT("LiveTest"))) return false;
    if (Actor->IsA<AJapanWorld>() || Actor->IsA<ASkatePark>() || Actor->IsA<AMegaRamp>() ||
        Actor->IsA<ASuperUltraMegaPark>() || Actor->IsA<AHippodrome>()) return true;
    // Map-authored static actors, not movable LiveTest boxes or dynamic vehicle parts.
    const auto* MeshActor = Cast<AStaticMeshActor>(Actor);
    return MeshActor && MeshActor->GetRootComponent() &&
        MeshActor->GetRootComponent()->Mobility == EComponentMobility::Static;
}

bool JapanGameplayCollision::IsFixed(const UPrimitiveComponent* Component)
{
    if (!Component || !IsFixed(Component->GetOwner())) return false;
    // Racing toggles this gate. It cannot enter a deterministic static query until
    // that service has replicated state; the other hippodrome meshes remain fixed.
    return !(Component->GetOwner()->IsA<AHippodrome>() && Component->GetFName() == TEXT("SM_HD_StartingGate"));
}

void JapanGameplayCollision::Install(UWorld* World)
{
    if (World) if (auto* Cache = World->GetSubsystem<UJapanGameplayCollisionWorld>()) Cache->Install();
}

FCollisionQueryParams JapanGameplayCollision::Query(UWorld* World, FName Tag, const TStatId& Stat, bool Complex)
{
    FCollisionQueryParams Result(Tag, Stat, Complex);
    if (!ensureMsgf(World, TEXT("A fixed-geometry query needs a world"))) return Result;
    if (auto* Cache = World->GetSubsystem<UJapanGameplayCollisionWorld>()) return Cache->Query(Tag, Stat, Complex);
    // Dev tools may trace editor/preview worlds where game subsystems do not exist.
    // This explicit slow fallback configures the same authored boundary; no hot
    // game path scans the actor list.
    ensureMsgf(!World->IsGameWorld(), TEXT("Missing gameplay collision cache"));
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (!IsFixed(*It)) Result.AddIgnoredActor(*It);
        TArray<UPrimitiveComponent*> Parts; It->GetComponents(Parts);
        for (auto* Part : Parts)
        {
            const bool Fixed = IsFixed(Part);
            Part->SetCollisionResponseToChannel(Channel,
                Fixed && Part->GetCollisionResponseToChannel(ECC_Visibility) == ECR_Block ? ECR_Block : ECR_Ignore);
            if (IsFixed(*It) && !Fixed) Result.AddIgnoredComponent(Part);
        }
    }
    return Result;
}

TArray<FString> JapanGameplayCollision::Inventory(UWorld* World, TArray<FString>& Errors)
{
    TArray<FString> Records;
    if (!World) { Errors.Add(TEXT("No world")); return Records; }
    for (TActorIterator<AActor> It(World); It; ++It)
    {
        if (!IsFixed(*It)) continue;
        TArray<UPrimitiveComponent*> Parts; It->GetComponents(Parts);
        for (const auto* Part : Parts)
        {
            if (!IsFixed(Part)) continue;
            const bool Queries = Part->IsQueryCollisionEnabled();
            const bool Visible = Part->GetCollisionResponseToChannel(ECC_Visibility) == ECR_Block;
            const bool Vehicle = Part->GetCollisionResponseToChannel(Channel) == ECR_Block;
            // Visual-only sky, water and post-process bounds may differ by renderer/server.
            if (!Queries || (!Visible && !Vehicle)) continue;
            const FVector P = Part->GetComponentLocation();
            const FRotator R = Part->GetComponentRotation();
            const FVector S = Part->GetComponentScale();
            const auto* Instances = Cast<UInstancedStaticMeshComponent>(Part);
            const auto* Mesh = Cast<UStaticMeshComponent>(Part);
            const FString Asset = Mesh && Mesh->GetStaticMesh() ? Mesh->GetStaticMesh()->GetPathName() : FString();
            FString InstanceDigest;
            if (Instances)
            {
                FSHA1 Hash;
                for (int32 I = 0; I < Instances->GetInstanceCount(); ++I)
                {
                    FTransform Transform;
                    if (!Instances->GetInstanceTransform(I, Transform, true))
                    { Errors.Add(TEXT("Unreadable fixed instance: ") + Asset); continue; }
                    const FVector Location = Transform.GetLocation(), Scale = Transform.GetScale3D();
                    const FQuat Q = Transform.GetRotation();
                    FTCHARToUTF8 Row(*FString::Printf(TEXT("%.3f,%.3f,%.3f:%.6f,%.6f,%.6f,%.6f:%.6f,%.6f,%.6f;"),
                        Location.X, Location.Y, Location.Z, Q.X, Q.Y, Q.Z, Q.W, Scale.X, Scale.Y, Scale.Z));
                    Hash.Update(reinterpret_cast<const uint8*>(Row.Get()), Row.Length());
                }
                Hash.Final(); uint8 Bytes[20]; Hash.GetHash(Bytes); InstanceDigest = BytesToHex(Bytes, 20).ToLower();
            }
            // HISM_N allocation names depend on how many visual components a
            // dedicated server omitted. Asset + actual instances is the identity.
            const FString Name = Instances ? TEXT("instances") : Part->GetName();
            const FString Key = FString::Printf(TEXT("%s:%s:%s:%s:%.3f,%.3f,%.3f:%.3f,%.3f,%.3f:%.3f,%.3f,%.3f:q%d:v%d:g%d:n%d"),
                *It->GetClass()->GetName(), *Name, *Asset, *InstanceDigest, P.X, P.Y, P.Z, R.Pitch, R.Yaw, R.Roll,
                S.X, S.Y, S.Z, Queries, Visible, Vehicle, Instances ? Instances->GetInstanceCount() : 1);
            Records.Add(Key);
            if (Queries && Visible != Vehicle) Errors.Add(Key);
        }
    }
    // FString's default ordering ignores case; the cross-language receipt uses
    // exact asset/component spelling and a case-sensitive canonical order.
    Records.Sort([](const FString& A, const FString& B) { return A.Compare(B, ESearchCase::CaseSensitive) < 0; });
    return Records;
}
