#include "SkatePark.h"
#include "Components/StaticMeshComponent.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "SeeThrough.h"
#include "Components/BoxComponent.h"
#include "Components/PostProcessComponent.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"

ASkatePark::ASkatePark()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    Tags.Add(TEXT("SkatePark"));   // the Skate plugin rolls it as smooth park concrete
}

static TSharedPtr<FJsonObject> ReadJson(const FString& Path)
{
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *Path)) return nullptr;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()) return nullptr;
    return Root;
}

static FVector ArrayVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return FVector(A.Num() > 0 ? A[0]->AsNumber() : 0., A.Num() > 1 ? A[1]->AsNumber() : 0., A.Num() > 2 ? A[2]->AsNumber() : 0.);
}

FVector ASkatePark::LocalToWorld(double X, double Y, double Z) const
{
    // Park-local metres (Blender axes) -> rotate by the park yaw -> world metres -> UE cm (Y mirrored).
    const double R = FMath::DegreesToRadians(Yaw), C = FMath::Cos(R), S = FMath::Sin(R);
    const double WX = X * C - Y * S, WY = X * S + Y * C;
    return Origin + FVector(WX * 100., -WY * 100., Z * 100.);
}

TArray<TArray<FVector2D>> ASkatePark::LoadClearance(const FString& Path)
{
    TArray<TArray<FVector2D>> Out;
    const TSharedPtr<FJsonObject> Root = ReadJson(Path);
    const TArray<TSharedPtr<FJsonValue>>* Polygons = nullptr;
    if (!Root || !Root->TryGetArrayField(TEXT("clearance"), Polygons)) return Out;
    for (const auto& Poly : *Polygons)
    {
        TArray<FVector2D>& P = Out.AddDefaulted_GetRef();
        for (const auto& V : Poly->AsArray()) { const FVector W = ArrayVector(V->AsArray()); P.Add(FVector2D(W.X * 100., -W.Y * 100.)); }
    }
    return Out;
}

bool ASkatePark::ReadParkSpawn(const FString& Path, FVector& World, float& OutYaw)
{
    const TSharedPtr<FJsonObject> Root = ReadJson(Path);
    const TSharedPtr<FJsonObject>* Spawns = nullptr; const TSharedPtr<FJsonObject>* Park = nullptr;
    if (!Root || !Root->TryGetObjectField(TEXT("spawns"), Spawns) || !(*Spawns)->TryGetObjectField(TEXT("park"), Park)) return false;
    const FVector O = ArrayVector(Root->GetArrayField(TEXT("origin"))), L = ArrayVector((*Park)->GetArrayField(TEXT("pos")));
    const double ParkYaw = Root->HasField(TEXT("yaw_deg")) ? Root->GetNumberField(TEXT("yaw_deg")) : 0.;
    const double R = FMath::DegreesToRadians(ParkYaw), C = FMath::Cos(R), S = FMath::Sin(R);
    World = FVector(O.X + L.X * C - L.Y * S, O.Y + L.X * S + L.Y * C, O.Z + L.Z);
    OutYaw = (*Park)->GetNumberField(TEXT("yaw_deg")) + ParkYaw;
    return true;
}

bool ASkatePark::Inside(const TArray<TArray<FVector2D>>& Polygons, const FVector2D& P)
{
    for (const auto& Poly : Polygons)
    {
        bool bIn = false;
        for (int32 I = 0, J = Poly.Num() - 1; I < Poly.Num(); J = I++)
            if (((Poly[I].Y > P.Y) != (Poly[J].Y > P.Y)) && P.X < (Poly[J].X - Poly[I].X) * (P.Y - Poly[I].Y) / (Poly[J].Y - Poly[I].Y) + Poly[I].X) bIn = !bIn;
        if (bIn) return true;
    }
    return false;
}

bool ASkatePark::ContainsPlanar(const FVector& Position, float Margin) const
{
    const FVector Local = GetActorTransform().InverseTransformPosition(Position);
    return FMath::Abs(Local.X) <= DeckHalfSize.X + Margin && FMath::Abs(Local.Y) <= DeckHalfSize.Y + Margin;
}

bool ASkatePark::Initialize(const FString& Path)
{
    const TSharedPtr<FJsonObject> Root = ReadJson(Path);
    if (!Root) { UE_LOG(LogTemp, Warning, TEXT("Skate park: %s not found"), *Path); return false; }
    FString AssetRoot(TEXT("/Game/SkatePark"));
    Root->TryGetStringField(TEXT("asset_root"), AssetRoot);
    if (!AssetRoot.StartsWith(TEXT("/Game/"))) { UE_LOG(LogTemp, Warning, TEXT("Skate park: %s asset_root %s is outside /Game/"), *Path, *AssetRoot); return false; }
    FString ParkKey(TEXT("skatepier"));
    Root->TryGetStringField(TEXT("key"), ParkKey);
    Tags.AddUnique(FName(*ParkKey));
    const FVector O = ArrayVector(Root->GetArrayField(TEXT("origin")));
    Origin = FVector(O.X * 100., -O.Y * 100., O.Z * 100.);
    Yaw = Root->HasField(TEXT("yaw_deg")) ? Root->GetNumberField(TEXT("yaw_deg")) : 0.f;
    SetActorLocationAndRotation(Origin, FRotator(0, -Yaw, 0));
    RootComponent->SetMobility(EComponentMobility::Static);
    const auto Deck = Root->GetObjectField(TEXT("deck"));
    DeckHalfSize = FVector2D(Deck->GetArrayField(TEXT("x"))[1]->AsNumber(), Deck->GetArrayField(TEXT("y"))[1]->AsNumber()) * 100.;
    auto* Bounds = NewObject<UBoxComponent>(this, TEXT("PierLookBounds"));
    Bounds->SetMobility(EComponentMobility::Static); Bounds->SetupAttachment(RootComponent);
    Bounds->SetBoxExtent(FVector(DeckHalfSize.X+400, DeckHalfSize.Y+400, 10000));
    Bounds->SetCollisionEnabled(ECollisionEnabled::QueryOnly); Bounds->SetCollisionResponseToAllChannels(ECR_Ignore);
    Bounds->SetGenerateOverlapEvents(false); Bounds->SetCanEverAffectNavigation(false); Bounds->RegisterComponent();
    auto* Look = NewObject<UPostProcessComponent>(this, TEXT("PierLook"));
    Look->SetupAttachment(Bounds); Look->bUnbound=false; Look->BlendRadius=400; Look->Priority=4;
    // Lumen's cache of these large thin riding surfaces leaks coarse tan patches
    // across the decks. Baked vertex AO, skylight and direct shadows provide the
    // park's matte lighting without that unstable indirect pass.
    Look->Settings.bOverride_DynamicGlobalIlluminationMethod=true;
    Look->Settings.DynamicGlobalIlluminationMethod=EDynamicGlobalIlluminationMethod::None;
    Look->RegisterComponent();

    int32 Meshes = 0;
    for (const auto& Entry : Root->GetArrayField(TEXT("meshes")))
    {
        FString Name; bool bBlocks = true;
        if (Entry->Type == EJson::String) Name = Entry->AsString();
        else { Name = Entry->AsObject()->GetStringField(TEXT("name")); Entry->AsObject()->TryGetBoolField(TEXT("blocks"), bBlocks); }
        UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name));
        if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("Skate park: mesh %s is not imported"), *Name); continue; }
        auto* C = NewObject<UStaticMeshComponent>(this, *Name);
        // Static children only attach to a static root: the root is placed first, then fixed.
        C->SetStaticMesh(Mesh); C->SetMobility(EComponentMobility::Static); C->SetupAttachment(RootComponent);
        C->SetCollisionEnabled(bBlocks ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
        C->SetCollisionResponseToAllChannels(ECR_Block);
        C->SetCanEverAffectNavigation(false);
        C->RegisterComponent(); ++Meshes;
    }
    // Reuse the island's detailed trees in the perimeter stone gardens. Their
    // canopies frame the skating; the separate foliage has no riding collision.
    const TSharedPtr<FJsonObject>* Trees = nullptr;
    if (Root->TryGetObjectField(TEXT("trees"), Trees))
        for (const auto& Pair : (*Trees)->Values)
        {
            const FString Key(Pair.Key);
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr,
                *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Key, *Key));
            if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("Skate park: missing tree %s"), *Key); continue; }
            auto* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(this, *Key);
            H->SetStaticMesh(Mesh); H->SetMobility(EComponentMobility::Static); H->SetupAttachment(RootComponent);
            H->SetCollisionEnabled(ECollisionEnabled::NoCollision); H->SetCanEverAffectNavigation(false);
            const int32 Fade = JapanSeeThrough::FadeMode(Key, Mesh);
            if (Fade != JapanSeeThrough::FadeSolid) H->SetCustomPrimitiveDataFloat(0, float(Fade));
            H->SetWorldPositionOffsetDisableDistance(18000);
            H->RegisterComponent();
            for (const auto& Value : Pair.Value->AsArray())
            {
                const auto& A = Value->AsArray();
                if (A.Num() != 5) continue;
                H->AddInstance(FTransform(FRotator(0, -A[3]->AsNumber(), 0),
                    FVector(A[0]->AsNumber()*100., -A[1]->AsNumber()*100., A[2]->AsNumber()*100.),
                    FVector(A[4]->AsNumber())));
            }
        }
    USkateRailSubsystem* Registry = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    const TArray<TSharedPtr<FJsonValue>>* Rails = nullptr;
    if (Registry && Root->TryGetArrayField(TEXT("rails"), Rails))
        for (const auto& Value : *Rails)
        {
            const TSharedPtr<FJsonObject> R = Value->AsObject();
            FSkateRail Rail; Rail.Id = FName(*R->GetStringField(TEXT("id")));
            const FString Kind = R->GetStringField(TEXT("kind"));
            Rail.Kind = Kind == TEXT("ledge") ? ESkateRailKind::Ledge : Kind == TEXT("coping") ? ESkateRailKind::Coping : Kind == TEXT("curb") ? ESkateRailKind::Curb : ESkateRailKind::Rail;
            for (const auto& P : R->GetArrayField(TEXT("points"))) { const FVector L = ArrayVector(P->AsArray()); Rail.Points.Add(LocalToWorld(L.X, L.Y, L.Z)); }
            double Radius = 2.5; if (R->TryGetNumberField(TEXT("radius"), Radius)) Rail.Radius = Radius * 100.;
            const TArray<TSharedPtr<FJsonValue>>* Side = nullptr;
            if (R->TryGetArrayField(TEXT("side"), Side) && Side->Num() >= 2)
                Rail.Side = (LocalToWorld((*Side)[0]->AsNumber(), (*Side)[1]->AsNumber(), 0.) - LocalToWorld(0., 0., 0.)).GetSafeNormal2D();
            if (Registry->Add(MoveTemp(Rail)) != INDEX_NONE) ++RailCount;
        }
    const TSharedPtr<FJsonObject>* Spawns = nullptr;
    if (Root->TryGetObjectField(TEXT("spawns"), Spawns))
    {
        const TSharedPtr<FJsonObject>* Park = nullptr; const TSharedPtr<FJsonObject>* Top = nullptr;
        if ((*Spawns)->TryGetObjectField(TEXT("park"), Park))
        {
            const FVector L = ArrayVector((*Park)->GetArrayField(TEXT("pos")));
            ParkSpawn = LocalToWorld(L.X, L.Y, L.Z); ParkSpawnYaw = -((*Park)->GetNumberField(TEXT("yaw_deg")) + Yaw);
        }
        if ((*Spawns)->TryGetObjectField(TEXT("path_top"), Top))
        {
            const FVector W = ArrayVector((*Top)->GetArrayField(TEXT("pos")));
            PathTop = FVector(W.X * 100., -W.Y * 100., W.Z * 100.); PathTopYaw = -(*Top)->GetNumberField(TEXT("yaw_deg"));
        }
    }
    UE_LOG(LogTemp, Display, TEXT("SKATE PARK loaded: %d meshes, %d rails, spawn %s"), Meshes, RailCount, *ParkSpawn.ToString());
    return true;
}
