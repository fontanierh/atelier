#include "BikeMeshComponent.h"
#include "AtomicMeshBounds.h"
#include "Engine/StaticMesh.h"
#include "PhysicsEngine/BodySetup.h"
#if WITH_EDITOR
#include "Chaos/TriangleMeshImplicitObject.h"
#endif
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"

const TArray<FName>& UBikeMeshComponent::SteeringNames()
{
    static const TArray<FName> Names{TEXT("BK_Steer_BasketFoot"), TEXT("BK_Steer_BasketRim"),
        TEXT("BK_Steer_BasketShell"), TEXT("BK_Steer_Core")};
    return Names;
}

static bool BikeGroup(const TArray<UStaticMesh*>& Parts)
{
    if (Parts.Num() != UBikeMeshComponent::SteeringNames().Num()) return false;
    TSet<FName> Names;
    for (const UStaticMesh* Mesh : Parts)
    {
        if (!Mesh || Names.Contains(Mesh->GetFName()) || !UBikeMeshComponent::SteeringNames().Contains(Mesh->GetFName())) return false;
        Names.Add(Mesh->GetFName());
    }
    return true;
}

bool UBikeMeshComponent::ReadGroupBounds(const TArray<UStaticMesh*>& Parts, FBoxSphereBounds& OutBounds)
{
    OutBounds = FBoxSphereBounds(ForceInit);
    if (!BikeGroup(Parts)) return false;
    bool First = true;
    for (UStaticMesh* Mesh : Parts)
    {
        const auto* Data = Cast<UBikeSteeringBoundsData>(Mesh->GetAssetUserDataOfClass(UBikeSteeringBoundsData::StaticClass()));
        if (!Data || Data->Members != SteeringNames() || Data->Origin.ContainsNaN() || Data->Extent.ContainsNaN()
            || Data->Extent.GetMin() < 0. || !FMath::IsFinite(Data->SphereRadius) || Data->SphereRadius <= 0.) return false;
        const FBoxSphereBounds Bound(Data->Origin, Data->Extent, Data->SphereRadius);
        if (!First && (Bound.Origin != OutBounds.Origin || Bound.BoxExtent != OutBounds.BoxExtent || Bound.SphereRadius != OutBounds.SphereRadius)) return false;
        OutBounds = Bound; First = false;
    }
    return true;
}

/** @cc [owner:fontanierh,label:correctness] bike-cooked-logical-bound-membership
 * All four current steering assets MUST carry the same complete group and exact
 * observed original single-LOD union box/true sphere as cooked asset user data.
 * Metadata MUST change only when its actual values change, and callers MUST check
 * dirty-only saves. Missing/foreign/duplicate group members MUST refuse. */
bool UBikeMeshComponent::PrepareSteeringBounds(const TArray<UStaticMesh*>& Parts)
{
#if WITH_EDITOR
    FBoxSphereBounds Bound(ForceInit);
    if (!BikeGroup(Parts) || !AtomicMeshBounds::MeasureLod0PartsBounds(Parts, Bound)) return false;
    for (UStaticMesh* Mesh : Parts)
    {
        auto* Data = Cast<UBikeSteeringBoundsData>(Mesh->GetAssetUserDataOfClass(UBikeSteeringBoundsData::StaticClass()));
        if (Data && Data->Members == SteeringNames() && Data->Origin == Bound.Origin
            && Data->Extent == Bound.BoxExtent && Data->SphereRadius == Bound.SphereRadius) continue;
        Mesh->Modify();
        if (!Data)
        {
            Data = NewObject<UBikeSteeringBoundsData>(Mesh);
            Mesh->AddAssetUserData(Data);
        }
        Data->Modify(); Data->Origin = Bound.Origin; Data->Extent = Bound.BoxExtent;
        Data->SphereRadius = Bound.SphereRadius; Data->Members = SteeringNames();
        Mesh->MarkPackageDirty();
    }
    FBoxSphereBounds Saved(ForceInit);
    return ReadGroupBounds(Parts, Saved) && Saved.Origin == Bound.Origin
        && Saved.BoxExtent == Bound.BoxExtent && Saved.SphereRadius == Bound.SphereRadius;
#else
    return false;
#endif
}

FString UBikeMeshComponent::SteeringBounds(const TArray<UStaticMesh*>& Parts)
{
    FBoxSphereBounds Bound(ForceInit);
    if (!ReadGroupBounds(Parts, Bound)) return {};
    auto Vector = [](const FVector& V)
    {
        return TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(V.X),
            MakeShared<FJsonValueNumber>(V.Y), MakeShared<FJsonValueNumber>(V.Z)};
    };
    auto Object = MakeShared<FJsonObject>();
    Object->SetArrayField(TEXT("origin"), Vector(Bound.Origin));
    Object->SetArrayField(TEXT("extent"), Vector(Bound.BoxExtent));
    Object->SetNumberField(TEXT("sphere_radius"), Bound.SphereRadius);
    FString Json;
    return FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Json)) ? Json : FString();
}

void UBikeMeshComponent::SetLogicalBounds(const FBoxSphereBounds& Bounds)
{
    LogicalBounds = Bounds; bHasLogicalBounds = true; UpdateBounds();
}

FBoxSphereBounds UBikeMeshComponent::CalcBounds(const FTransform& LocalToWorld) const
{
    if (!bHasLogicalBounds) return Super::CalcBounds(LocalToWorld);
    FBoxSphereBounds Result = LogicalBounds.TransformBy(LocalToWorld);
    Result.BoxExtent *= BoundsScale; Result.SphereRadius *= BoundsScale;
    return Result;
}


bool UBikeMeshComponent::ValidatePart(UStaticMesh* Mesh, int32 ExpectedTriangles)
{
#if WITH_EDITOR
    if (!Mesh || ExpectedTriangles < 1 || Mesh->LODForCollision != 0 || Mesh->ComplexCollisionMesh) return false;
    const auto* Body = Mesh->GetBodySetup();
    // The original Bike owner leaves the legacy importer's default trace policy intact.
    if (!Body || Body->CollisionTraceFlag != CTF_UseDefault || Body->BuildScale3D != FVector::OneVector
        || Body->AggGeom.GetElementCount() != 0 || Body->bNeverNeedsCookedCollisionData
        || !Body->bCreatedPhysicsMeshes || Body->bFailedToCreatePhysicsMeshes || Body->TriMeshGeometries.IsEmpty()) return false;
    int64 Count = 0;
    for (const auto& Geometry : Body->TriMeshGeometries)
    {
        if (!Geometry) return false;
        Count += Geometry->Elements().GetNumTriangles();
    }
    return Count == ExpectedTriangles;
#else
    return false;
#endif
}
