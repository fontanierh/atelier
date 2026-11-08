#include "Hippodrome.h"
#include "AtelierData.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Misc/FileHelper.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/PackageName.h"
#include "V2ScenePatch.h"

static TSharedPtr<FJsonObject> ReadHippodromeJson(const FString& Path)
{
    return AtelierReadJson(Path);
}

static FVector HorseJsonVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return FVector(A.Num() > 0 ? A[0]->AsNumber() : 0., A.Num() > 1 ? A[1]->AsNumber() : 0., A.Num() > 2 ? A[2]->AsNumber() : 0.);
}

// A mesh's place relative to the course origin, which is the actor's location: Blender metres to Unreal cm, as
// FHippodromeCourse::World maps them, without the origin and height it adds.
static FVector PieceOffset(const TSharedPtr<FJsonObject>& Entry)
{
    const FVector At = HorseJsonVector(Entry->GetArrayField(TEXT("at")));
    return FVector(At.X * 100., -At.Y * 100., At.Z * 100.);
}

static FRotator PieceRotation(const TSharedPtr<FJsonObject>& Entry)
{
    return FRotator(0, -Entry->GetNumberField(TEXT("yaw")), 0);
}

// ------------------------------------------------------------------------------------------------------------ Course

FVector FHippodromeCourse::At(double S, double Offset, float* Yaw) const
{
    S = FMath::Fmod(S, Lap); if (S < 0.) S += Lap;
    const double R = Radius + Offset, Ox = Origin.X, Oy = Origin.Y;
    double X, Y, Heading;
    if (S < Half) { X = FinishX + S; Y = Oy - R; Heading = 0.; }                      // home straight, east
    else if ((S -= Half) < PI * Radius)                                                  // east turn
    { const double A = -HALF_PI + S / Radius; X = Ox + Half + R * FMath::Cos(A); Y = Oy + R * FMath::Sin(A); Heading = A + HALF_PI; }
    else if ((S -= PI * Radius) < 2. * Half) { X = Ox + Half - S; Y = Oy + R; Heading = PI; }   // back straight, west
    else if ((S -= 2. * Half) < PI * Radius)                                             // west turn
    { const double A = HALF_PI + S / Radius; X = Ox - Half + R * FMath::Cos(A); Y = Oy + R * FMath::Sin(A); Heading = A + HALF_PI; }
    else { S -= PI * Radius; X = Ox - Half + S; Y = Oy - R; Heading = 0.; }              // home straight to the post
    if (Yaw) *Yaw = float(-FMath::RadiansToDegrees(Heading));
    return World(X, Y);
}

bool FHippodromeCourse::InTurn(double S) const
{
    S = FMath::Fmod(S, Lap); if (S < 0.) S += Lap;
    return !(S < Half || (Half + PI * Radius <= S && S < 3. * Half + PI * Radius) || S >= Lap - Half);
}

double FHippodromeCourse::CurvatureScale(double S, double Offset) const { return InTurn(S) ? (Radius + Offset) / Radius : 1.; }

// ------------------------------------------------------------------------------------------------------------ Venue

AHippodrome::AHippodrome()
{
    PrimaryActorTick.bCanEverTick = false;
    Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent = Root;
}

AHippodrome* AHippodrome::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !FPaths::FileExists(Path)) return nullptr;
    AHippodrome* H = World->SpawnActor<AHippodrome>();
    if (H && !H->Initialize(Path)) { H->Destroy(); return nullptr; }
    return H;
}

UStaticMeshComponent* AHippodrome::MakePiece(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Entry,
    UStaticMesh* Mesh)
{
    bool bBlocks = true; Entry->TryGetBoolField(TEXT("blocks"), bBlocks);
    auto* Component = NewObject<UStaticMeshComponent>(Outer, *Entry->GetStringField(TEXT("name")));
    Component->SetStaticMesh(Mesh); Component->SetupAttachment(Parent);
    Component->SetRelativeLocationAndRotation(PieceOffset(Entry), PieceRotation(Entry));
    Component->SetCollisionEnabled(bBlocks ? ECollisionEnabled::QueryOnly : ECollisionEnabled::NoCollision);
    Component->SetCollisionResponseToAllChannels(ECR_Block);
    Component->SetCanEverAffectNavigation(false);
    return Component;
}

AHippodrome* AHippodrome::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<AHippodrome> It(World);
    return It ? *It : nullptr;
}


bool AHippodrome::Initialize(const FString& Path)
{
    const TSharedPtr<FJsonObject> Root_ = ReadHippodromeJson(Path);
    if (!Root_) { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: cannot read %s"), *Path); return false; }
    FString AssetRoot(TEXT("/Game/Hippodrome"));
    Root_->TryGetStringField(TEXT("asset_root"), AssetRoot);
    const FVector O = HorseJsonVector(Root_->GetArrayField(TEXT("origin")));
    const TSharedPtr<FJsonObject> C = Root_->GetObjectField(TEXT("course"));
    Course.Origin = FVector2D(O.X, O.Y); Course.Z = O.Z;
    Course.Half = C->GetNumberField(TEXT("half")); Course.Radius = C->GetNumberField(TEXT("radius"));
    Course.Width = C->GetNumberField(TEXT("width")); Course.Lap = C->GetNumberField(TEXT("lap"));
    Course.FinishX = C->GetNumberField(TEXT("finish_x"));
    SetActorLocation(Course.World(O.X, O.Y));
    Tags.AddUnique(TEXT("hippodrome"));
    // Meshes a saved unit holds (UV2Migration::MigrateHippodromePieces) are not placed again: the map's manifest lists them
    // as "hippodrome:<mesh>". A standalone map has no manifest and places every mesh, as before.
    const AV2WorldManifest* Manifest = AV2WorldManifest::Find(GetWorld());
    const FName SavedTag(TEXT("hippodrome"));
    int32 Placed = 0;
    Course.Grounds = FBox(ForceInit);
    // The saved patch that holds a mesh (one of its components names it) and how far the editor has moved it since the
    // migration saved it (AV2ScenePatch::MovedBy). Identity while unmoved, so the bounds below are the course's own.
    auto SavedMove = [this](const FString& MeshName) -> FTransform
    {
        for (TActorIterator<AV2ScenePatch> It(GetWorld()); It; ++It)
        {
            if (!It->SourceKey.StartsWith(TEXT("hippodrome:"))) continue;
            TArray<UStaticMeshComponent*> Components;
            It->GetComponents(Components);
            for (const UStaticMeshComponent* C : Components)
                if (C->GetStaticMesh() && C->GetStaticMesh()->GetName() == MeshName) return It->MovedBy();
        }
        return FTransform::Identity;
    };
    for (const TSharedPtr<FJsonValue>& Entry : Root_->GetArrayField(TEXT("meshes")))
    {
        const TSharedPtr<FJsonObject>& M = Entry->AsObject();
        const FString Name = M->GetStringField(TEXT("name"));
        FString LogicalParent;
        M->TryGetStringField(TEXT("logical_parent"), LogicalParent);
        const bool bGround = Name == TEXT("SM_HD_Ground") || LogicalParent == TEXT("SM_HD_Ground");
        if (Manifest && Manifest->CoversGroup(SavedTag, Name))
        {
            // Its saved unit draws it; its mesh must still be committed content (checked without loading it). The
            // ground's bounds, which the racing course reads, come from its mesh at the place the course gives it.
            if (!FPackageName::DoesPackageExist(FString::Printf(TEXT("%s/%s"), *AssetRoot, *Name)))
            {
                UE_LOG(LogTemp, Error, TEXT("Hippodrome: saved mesh %s is missing"), *Name);
                continue;
            }
            ++Placed;
            if (bGround)
            {
                if (UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name)))
                {
                    FTransform Place(PieceRotation(M), GetActorLocation() + PieceOffset(M));
                    const FTransform Moved = SavedMove(Name);
                    if (!Moved.Equals(FTransform::Identity, 0.)) Place = Moved.TransformFTransform(Place);
                    Course.Grounds += Mesh->GetBounds().TransformBy(Place).GetBox();
                }
            }
            continue;
        }
        UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AssetRoot, *Name, *Name));
        if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("Hippodrome: mesh %s is not imported"), *Name); continue; }
        auto* Component = MakePiece(this, RootComponent, M, Mesh);
        Component->RegisterComponent(); ++Placed;
        if (bGround) Course.Grounds += Component->Bounds.GetBox();
    }
    RootComponent->SetMobility(EComponentMobility::Static);
    bGameplayReady = Placed > 0 && Placed == Root_->GetArrayField(TEXT("meshes")).Num();
    if (Placed == 0) return false;
    auto Spot = [&](const TCHAR* Key, FVector& Out, float& Yaw)
    {
        const TSharedPtr<FJsonObject> S = Root_->GetObjectField(Key);
        const FVector L = HorseJsonVector(S->GetArrayField(TEXT("at")));
        Out = Course.World(O.X + L.X, O.Y + L.Y, L.Z); Yaw = -float(S->GetNumberField(TEXT("yaw")));
    };
    Spot(TEXT("return"), ReturnGround, ReturnYaw);
    UE_LOG(LogTemp, Display, TEXT("Hippodrome: %d meshes at %s, lap %.1f m"), Placed, *GetActorLocation().ToString(), Course.Lap);
    return true;
}
