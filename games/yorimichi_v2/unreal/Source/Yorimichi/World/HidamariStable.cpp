#include "HidamariStable.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Dom/JsonObject.h"
#if WITH_EDITOR
#include "StaticMeshResources.h"
#include "Serialization/JsonSerializer.h"
#include "Serialization/JsonWriter.h"
#endif

#if WITH_EDITOR
static bool StableReadLodBox(const UStaticMesh* Mesh, int32 LodIndex, FBox3f& Box)
{
    if (!Mesh || !Mesh->GetRenderData() || !Mesh->GetRenderData()->LODResources.IsValidIndex(LodIndex)) return false;
    const auto& Buffer = Mesh->GetRenderData()->LODResources[LodIndex].VertexBuffers.PositionVertexBuffer;
    if (!Buffer.GetVertexData() || Buffer.GetNumVertices() == 0) return false;
    Box = FBox3f(ForceInit);
    for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
    {
        const FVector3f Position = Buffer.VertexPosition(Index);
        if (Position.ContainsNaN()) return false;
        Box += Position;
    }
    return Box.IsValid != 0;
}
#endif

/** @cc [owner:fontanierh,label:correctness] stable-selected-render-lod-bounds
 * Warm admission MUST compare the requested actual render LOD's finite position AABB,
 * not the mesh's union, extension, logical override or a source-derived approximation.
 * Missing CPU data or invalid LODs MUST refuse. Logical union/sphere remains separate. */
FString UHidamariStableMeshComponent::MeasureLodBounds(UStaticMesh* Mesh, int32 LodIndex)
{
#if WITH_EDITOR
    FBox3f Box(ForceInit);
    if (!StableReadLodBox(Mesh, LodIndex, Box)) return {};
    auto Vector = [](const FVector3f& Value)
    {
        return TArray<TSharedPtr<FJsonValue>>{MakeShared<FJsonValueNumber>(Value.X),
            MakeShared<FJsonValueNumber>(Value.Y), MakeShared<FJsonValueNumber>(Value.Z)};
    };
    const auto Object = MakeShared<FJsonObject>();
    Object->SetArrayField(TEXT("min"), Vector(Box.Min));
    Object->SetArrayField(TEXT("max"), Vector(Box.Max));
    FString Json;
    return FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Json)) ? Json : FString();
#else
    return {};
#endif
}

FString UHidamariStableMeshComponent::MeasureLogicalBounds(const TArray<UStaticMesh*>& Lod0Parts,
    const TArray<UStaticMesh*>& Lod1Parts, const TArray<UStaticMesh*>& Lod2Parts)
{
#if WITH_EDITOR
    FBoxSphereBounds::Builder Bounds;
    TSet<const UStaticMesh*> Seen;
    for (const TArray<UStaticMesh*>* Parts : {&Lod0Parts, &Lod1Parts, &Lod2Parts})
    {
        if (Parts->Num() != 5) return {};
        FBox3f Box(ForceInit);
        for (const UStaticMesh* Mesh : *Parts)
        {
            FBox3f PartBox(ForceInit);
            if (Seen.Contains(Mesh) || !StableReadLodBox(Mesh, 0, PartBox)) return {};
            Seen.Add(Mesh);
            Box += PartBox;
        }
        // Exact installed MeshBuilder::ComputeBoundsFromVertexList arithmetic.
        const FVector3f Center = Box.GetCenter();
        float RadiusSquared = 0.f;
        for (const UStaticMesh* Mesh : *Parts)
        {
            const auto& Buffer = Mesh->GetRenderData()->LODResources[0].VertexBuffers.PositionVertexBuffer;
            for (uint32 Index = 0; Index < Buffer.GetNumVertices(); ++Index)
                RadiusSquared = FMath::Max(RadiusSquared, (Buffer.VertexPosition(Index) - Center).SizeSquared());
        }
        Bounds += FBoxSphereBounds(FVector(Center), FVector(Box.GetExtent()), FMath::Sqrt(RadiusSquared));
    }
    const FBoxSphereBounds Result = Bounds;
    if (Result.ContainsNaN() || Result.SphereRadius <= 0.) return {};
    auto Vector = [](const FVector& Value)
    {
        TArray<TSharedPtr<FJsonValue>> Values;
        Values.Add(MakeShared<FJsonValueNumber>(Value.X)); Values.Add(MakeShared<FJsonValueNumber>(Value.Y));
        Values.Add(MakeShared<FJsonValueNumber>(Value.Z)); return Values;
    };
    const auto Object = MakeShared<FJsonObject>();
    Object->SetArrayField(TEXT("origin"), Vector(Result.Origin));
    Object->SetArrayField(TEXT("extent"), Vector(Result.BoxExtent));
    Object->SetNumberField(TEXT("sphere_radius"), Result.SphereRadius);
    FString Json;
    return FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Json)) ? Json : FString();
#else
    return {};
#endif
}

FBoxSphereBounds UHidamariStableMeshComponent::CalcBounds(const FTransform& LocalToWorld) const
{
    if (!bHasLogicalBounds) return Super::CalcBounds(LocalToWorld);
    FBoxSphereBounds Result = LogicalBounds.TransformBy(LocalToWorld);
    Result.BoxExtent *= BoundsScale;
    Result.SphereRadius *= BoundsScale;
    return Result;
}

static FVector StableVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return FVector(A.Num() > 0 ? A[0]->AsNumber() : 0., A.Num() > 1 ? A[1]->AsNumber() : 0., A.Num() > 2 ? A[2]->AsNumber() : 0.);
}

static FVector StableField(const TSharedPtr<FJsonObject>& O, const TCHAR* Key)
{
    const TArray<TSharedPtr<FJsonValue>>* A = nullptr;
    return O && O->TryGetArrayField(Key, A) ? StableVector(*A) : FVector::ZeroVector;
}

static TSharedPtr<FJsonObject> StableObj(const TSharedPtr<FJsonObject>& O, const TCHAR* Key)
{
    const TSharedPtr<FJsonObject>* Sub = nullptr;
    return O && O->TryGetObjectField(Key, Sub) && Sub ? *Sub : nullptr;
}

static const TArray<TSharedPtr<FJsonValue>>& StableArr(const TSharedPtr<FJsonObject>& O, const TCHAR* Key)
{
    static const TArray<TSharedPtr<FJsonValue>> Empty;
    const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
    return O && O->TryGetArrayField(Key, Arr) && Arr ? *Arr : Empty;
}

AHidamariStable::AHidamariStable()
{
    PrimaryActorTick.bCanEverTick = false;
    Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent = Root;
}

AHidamariStable* AHidamariStable::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !FPaths::FileExists(Path)) return nullptr;
    AHidamariStable* S = World->SpawnActor<AHidamariStable>();
    if (S && !S->Initialize(Path)) { S->Destroy(); return nullptr; }
    return S;
}

AHidamariStable* AHidamariStable::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<AHidamariStable> It(World);
    return It ? *It : nullptr;
}

void AHidamariStable::SetDoorOpen(int32 Stall, float Alpha)
{
    if (!Stalls.IsValidIndex(Stall) || !Stalls[Stall].Door) return;
    const FHidamariStall& S = Stalls[Stall];
    S.Door->SetWorldLocation(S.DoorClosed + S.DoorSlide * FMath::Clamp(Alpha, 0.f, 1.f));
}

void AHidamariStable::SetRoomDoorOpen(const FString& Room, float Alpha)
{
    TObjectPtr<UStaticMeshComponent>* Door = RoomDoors.Find(Room);
    const FVector* Closed = RoomDoorClosed.Find(Room);
    const FVector* Slide = RoomDoorSlide.Find(Room);
    if (!Door || !*Door || !Closed || !Slide) return;
    (*Door)->SetWorldLocation(*Closed + *Slide * FMath::Clamp(Alpha, 0.f, 1.f));
}

bool AHidamariStable::Initialize(const FString& Path)
{
    const TSharedPtr<FJsonObject> Data = AtelierReadJson(Path);
    if (!Data) { UE_LOG(LogTemp, Warning, TEXT("Hidamari stable: cannot read %s"), *Path); return false; }
    FString AssetRoot(TEXT("/Game/HidamariStable"));
    Data->TryGetStringField(TEXT("asset_root"), AssetRoot);
    bool bAtomic = false;
    if (!Data->TryGetBoolField(TEXT("atomic"), bAtomic) || !bAtomic
        || AssetRoot != TEXT("/Game/HidamariStable/Atomic")) return false;
    Origin = StableField(StableObj(Data, TEXT("site")), TEXT("origin"));
    SetActorLocation(World(FVector::ZeroVector));
    Tags.AddUnique(TEXT("hidamari_stable"));
    auto Load = [&](const FString& Name)
    {
        UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name));
        if (!Mesh) UE_LOG(LogTemp, Warning, TEXT("Hidamari stable: mesh %s is not imported"), *Name);
        return Mesh;
    };
    TOptional<FBoxSphereBounds> LogicalBounds;
    const auto Logical = StableObj(Data, TEXT("logical_stable_bounds_cm"));
    if (Data->HasField(TEXT("atomic")))
    {
        if (!Logical) return false;
        for (const TCHAR* Key : {TEXT("origin"), TEXT("extent")})
        {
            const auto& Coordinates = StableArr(Logical, Key);
            if (Coordinates.Num() != 3) return false;
            for (const auto& Coordinate : Coordinates)
                if (!Coordinate || Coordinate->Type != EJson::Number || !FMath::IsFinite(Coordinate->AsNumber())) return false;
        }
        const FVector Center = StableField(Logical, TEXT("origin")), Extent = StableField(Logical, TEXT("extent"));
        double Radius = 0.;
        if (!Logical->TryGetNumberField(TEXT("sphere_radius"), Radius) || !FMath::IsFinite(Radius) || Radius <= 0.
            || Center.ContainsNaN() || Extent.ContainsNaN() || Extent.GetMin() <= 0.
            || Radius < Extent.GetMax() || Radius > Extent.Size()) return false;
        LogicalBounds = FBoxSphereBounds(Center, Extent, Radius);
        static const TSet<FString> Expected = {TEXT("SM_HS_Barn"), TEXT("SM_HS_BarnRoof"), TEXT("SM_HS_Gate"), TEXT("SM_HS_Yard"),
            TEXT("SM_HS_Paddock"), TEXT("SM_HS_Ground"), TEXT("SM_HS_Road"), TEXT("SM_HS_RoadSign"),
            TEXT("SM_HS_StallDoor"), TEXT("SM_HS_RoomDoor")};
        TSet<FString> Found;
        for (const auto& Value : StableArr(Data, TEXT("meshes")))
        {
            const auto M = Value ? Value->AsObject() : nullptr;
            FString Name;
            if (!M || !M->TryGetStringField(TEXT("name"), Name) || !Expected.Contains(Name) || Found.Contains(Name)
                || !Load(Name)) return false;
            Found.Add(Name);
        }
        if (Found.Num() != Expected.Num()) return false;
    }
    auto Place = [&](UStaticMesh* Mesh, const FString& Name, const FVector& Local, float Yaw, bool bBlocks, bool bLogical = false)
    {
        UStaticMeshComponent* Component;
        if (bLogical && LogicalBounds.IsSet())
        {
            auto* Part = NewObject<UHidamariStableMeshComponent>(this, *Name);
            Part->LogicalBounds = LogicalBounds.GetValue(); Part->bHasLogicalBounds = true; Component = Part;
        }
        else Component = NewObject<UStaticMeshComponent>(this, *Name);
        Component->SetMobility(EComponentMobility::Static);
        Component->SetStaticMesh(Mesh); Component->SetupAttachment(RootComponent);
        Component->SetWorldLocationAndRotation(World(Local), FRotator(0, -Yaw, 0));
        Component->SetCollisionEnabled(bBlocks ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
        Component->SetCollisionResponseToAllChannels(ECR_Block);
        Component->SetCanEverAffectNavigation(false);
        Component->RegisterComponent();
        return Component;
    };
    int32 Placed = 0, Wanted = 0;
    for (const TSharedPtr<FJsonValue>& Entry : StableArr(Data, TEXT("meshes")))
    {
        const TSharedPtr<FJsonObject> M = Entry ? Entry->AsObject() : nullptr;
        if (!M) continue;
        if (M->HasField(TEXT("instances"))) continue;            // the door leaves, placed per door below
        ++Wanted;
        const FString Name = M->GetStringField(TEXT("name"));
        if (UStaticMesh* Mesh = Load(Name))
        {
            bool bBlocks = true; M->TryGetBoolField(TEXT("blocks"), bBlocks);
            const bool bLogical = Name == TEXT("SM_HS_Barn") || Name == TEXT("SM_HS_BarnRoof") || Name == TEXT("SM_HS_Gate")
                || Name == TEXT("SM_HS_Yard") || Name == TEXT("SM_HS_Paddock");
            Place(Mesh, Name, StableField(M, TEXT("at")), float(M->GetNumberField(TEXT("yaw"))), bBlocks, bLogical); ++Placed;
        }
    }
    // stalls: name plates and horse spots, then every door leaf (stall doors keep a pointer for SetDoorOpen)
    TMap<FString, int32> StallIndex;
    for (const TSharedPtr<FJsonValue>& Entry : StableArr(Data, TEXT("stalls")))
    {
        const TSharedPtr<FJsonObject> S = Entry ? Entry->AsObject() : nullptr;
        if (!S) continue;
        FHidamariStall& Stall = Stalls.AddDefaulted_GetRef();
        Stall.Id = S->GetStringField(TEXT("id"));
        const TSharedPtr<FJsonObject> P = StableObj(S, TEXT("plaque"));
        const FVector N = StableField(P, TEXT("normal")), Size = StableField(P, TEXT("size"));
        Stall.Plaque = FTransform(FVector(N.X, -N.Y, 0.).Rotation(), World(StableField(P, TEXT("centre"))));
        Stall.PlaqueSize = FVector2D(Size.X * 100., Size.Y * 100.);
        const TSharedPtr<FJsonObject> Horse = StableObj(S, TEXT("horse"));
        Stall.Horse = FTransform(FRotator(0, -(Horse ? Horse->GetNumberField(TEXT("yaw")) : 0.), 0), World(StableField(Horse, TEXT("at"))));
        StallIndex.Add(Stall.Id, Stalls.Num() - 1);
    }
    for (const TSharedPtr<FJsonValue>& Entry : StableArr(Data, TEXT("doors")))
    {
        const TSharedPtr<FJsonObject> D = Entry ? Entry->AsObject() : nullptr;
        if (!D) continue;
        const FString Name = TEXT("SM_HS_") + D->GetStringField(TEXT("mesh"));
        ++Wanted;
        UStaticMesh* Mesh = Load(Name);
        if (!Mesh) continue;
        auto* Leaf = Place(Mesh, D->GetStringField(TEXT("id")), StableField(D, TEXT("pivot")), float(D->GetNumberField(TEXT("yaw"))), true);
        ++Placed;
        FString Stall;
        if (D->TryGetStringField(TEXT("stall"), Stall) && StallIndex.Contains(Stall))
        {
            const FVector Slide = StableField(D, TEXT("slide")) * D->GetNumberField(TEXT("travel"));
            Leaf->SetMobility(EComponentMobility::Movable);      // it slides; the rest of the stable stays static
            Stalls[StallIndex[Stall]].Door = Leaf;
            Stalls[StallIndex[Stall]].DoorClosed = Leaf->GetComponentLocation();
            Stalls[StallIndex[Stall]].DoorSlide = FVector(Slide.X * 100., -Slide.Y * 100., Slide.Z * 100.);
        }
        FString Room;
        if (D->TryGetStringField(TEXT("room"), Room) && !Room.IsEmpty())
        {
            const FVector Slide = StableField(D, TEXT("slide")) * D->GetNumberField(TEXT("travel"));
            Leaf->SetMobility(EComponentMobility::Movable);
            RoomDoors.Add(Room, Leaf);
            RoomDoorClosed.Add(Room, Leaf->GetComponentLocation());
            RoomDoorSlide.Add(Room, FVector(Slide.X * 100., -Slide.Y * 100., Slide.Z * 100.));
            SetRoomDoorOpen(Room, 1.f);
        }
    }
    RootComponent->SetMobility(EComponentMobility::Static);
    // anchors for the racing game
    const TSharedPtr<FJsonObject> SignData = StableObj(Data, TEXT("sign"));
    const FVector SN = StableField(SignData, TEXT("normal"));
    Sign = FTransform(FVector(SN.X, -SN.Y, 0.).Rotation(), World(StableField(SignData, TEXT("centre"))));
    const TSharedPtr<FJsonObject> Board = StableObj(Data, TEXT("notice_board"));
    const FVector BN = StableField(Board, TEXT("normal"));
    NoticeBoard = FTransform(FVector(BN.X, -BN.Y, 0.).Rotation(), World(StableField(Board, TEXT("centre"))));
    const TSharedPtr<FJsonObject> Spots = StableObj(Data, TEXT("spots"));
    const TSharedPtr<FJsonObject> ArrivalData = StableObj(Spots, TEXT("arrival"));
    Arrival = FTransform(FRotator(0, -(ArrivalData ? ArrivalData->GetNumberField(TEXT("yaw")) : 0.), 0), World(StableField(ArrivalData, TEXT("at"))));
    for (const TSharedPtr<FJsonValue>& Entry : StableArr(Spots, TEXT("npc")))
    {
        const TSharedPtr<FJsonObject> S = Entry ? Entry->AsObject() : nullptr;
        if (!S) continue;
        NpcSpots.Add(S->GetStringField(TEXT("id")), FTransform(FRotator(0, -S->GetNumberField(TEXT("yaw")), 0), World(StableField(S, TEXT("at")))));
    }
    bGameplayReady = Placed > 0 && Placed == Wanted;
    if (Placed == 0) return false;
    UE_LOG(LogTemp, Display, TEXT("Hidamari stable: %d of %d meshes at %s, %d stalls"), Placed, Wanted, *GetActorLocation().ToString(), Stalls.Num());
    return true;
}
