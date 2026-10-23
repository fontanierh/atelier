#include "BikeMeshComponent.h"
#include "AtomicMeshBounds.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Actor.h"
#include "PhysicsEngine/BodySetup.h"
#if WITH_EDITOR
#include "Chaos/TriangleMeshImplicitObject.h"
#include "MeshBuild.h"
#include "MeshDescription.h"
#include "StaticMeshAttributes.h"
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


bool UBikeMeshComponent::UseSavedSteeringBounds(const TArray<UStaticMesh*>& Parts)
{
    bHasLogicalBounds = false; LogicalBounds = FBoxSphereBounds(ForceInit); UpdateBounds();
    FBoxSphereBounds Bounds(ForceInit);
    if (!Parts.Contains(GetStaticMesh()) || !ReadGroupBounds(Parts, Bounds)) return false;
    SetLogicalBounds(Bounds);
    return true;
}

UBikeMeshComponent* UBikeMeshComponent::CreateEvidenceComponent(AActor* Owner, UStaticMesh* Mesh,
    const TArray<UStaticMesh*>& Parts)
{
#if WITH_EDITOR
    FBoxSphereBounds Bounds(ForceInit);
    if (!Owner || !Owner->GetWorld() || !Mesh || !Parts.Contains(Mesh) || !ReadGroupBounds(Parts, Bounds)) return nullptr;
    auto* Component = NewObject<UBikeMeshComponent>(Owner);
    if (Owner->GetRootComponent()) Component->SetupAttachment(Owner->GetRootComponent());
    else Owner->SetRootComponent(Component);
    Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Component->SetGenerateOverlapEvents(false); Component->SetCanEverAffectNavigation(false);
    Component->SetStaticMesh(Mesh); Component->SetLogicalBounds(Bounds);
    Component->RegisterComponent();
    return Component;
#else
    return nullptr;
#endif
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


bool UBikeMeshComponent::ValidatePart(UStaticMesh* Mesh, int32 ExpectedSourceTriangles)
{
#if WITH_EDITOR
    if (!Mesh || ExpectedSourceTriangles < 1 || Mesh->GetNumLODs() != 1
        || Mesh->LODForCollision != 0 || Mesh->ComplexCollisionMesh) return false;
    const FMeshDescription* Description = Mesh->GetMeshDescription(0);
    if (!Description || Description->Triangles().Num() < 1
        || Description->Triangles().Num() > ExpectedSourceTriangles) return false;
    // Legacy FBX import and MeshBuilder may remove duplicate-point pole/cap triangles.
    // Derive the exact render target from saved source geometry and the actual build policy,
    // using MeshBuilder's predicate rather than treating the export's fan count as rendered.
    const auto Positions = FStaticMeshConstAttributes(*Description).GetVertexPositions();
    const bool RemoveDegenerates = Mesh->GetSourceModel(0).BuildSettings.bRemoveDegenerates;
    int32 ExpectedBuiltTriangles = 0;
    for (const FTriangleID Triangle : Description->Triangles().GetElementIDs())
    {
        const auto Vertices = Description->GetTriangleVertices(Triangle);
        const FVector3f A = Positions[Vertices[0]], B = Positions[Vertices[1]], C = Positions[Vertices[2]];
        if (A.ContainsNaN() || B.ContainsNaN() || C.ContainsNaN()) return false;
        if (!PointsEqual(A, B, RemoveDegenerates) && !PointsEqual(A, C, RemoveDegenerates)
            && !PointsEqual(B, C, RemoveDegenerates)) ++ExpectedBuiltTriangles;
    }
    if (ExpectedBuiltTriangles < 1 || Mesh->GetNumTriangles(0) != ExpectedBuiltTriangles) return false;
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
    return Count == ExpectedBuiltTriangles;
#else
    return false;
#endif
}
