#include "SuperUltraMegaPark.h"
#include "CairoCharacter.h"
#include "JapanHUD.h"
#include "SkateRails.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/StaticMesh.h"
#include "StaticMeshResources.h"
#include "Misc/FileHelper.h"
#include "LiveLibrary.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "GameFramework/PlayerController.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/CollisionProfile.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

ASuperUltraMegaPark::ASuperUltraMegaPark()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void ASuperUltraMegaPark::BeginPlay()
{
    Super::BeginPlay();
    // Spawned in the island, the rails arrive with the manifest after BeginPlay.
    if (!Rails.IsEmpty()) RegisterRails();
}

static FVector JsonVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return A.Num() >= 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) : FVector::ZeroVector;
}

ASuperUltraMegaPark* ASuperUltraMegaPark::Spawn(UWorld* World, const FString& Path)
{
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!World || !FFileHelper::LoadFileToString(Text, *Path)) return nullptr;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid())
    {
        UE_LOG(LogTemp, Warning, TEXT("MEGAPARK: %s is not valid JSON"), *Path);
        return nullptr;
    }
    // Children are authored at ue(native) = 100 (x, z, y); the actor turns and moves the park as one body.
    const FTransform Placement(FRotator(0., Root->GetNumberField(TEXT("yaw_deg")), 0.), JsonVector(Root->GetArrayField(TEXT("location_cm"))));
    ASuperUltraMegaPark* Park = World->SpawnActor<ASuperUltraMegaPark>(StaticClass(), Placement);
    if (!Park) return nullptr;
    Park->SourceManifestHash = Root->GetStringField(TEXT("source_sha256"));
    int32 Meshes = 0, Missing = 0;
    for (const TCHAR* Kind : {TEXT("render"), TEXT("collision")})
    {
        const bool bCollision = FCString::Strcmp(Kind, TEXT("collision")) == 0;
        for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(Kind))
        {
            const TSharedPtr<FJsonObject> Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("name"));
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/MegaPark/Meshes/%s.%s"), *Name, *Name));
            if (!Mesh) { ++Missing; continue; }
            auto* C = NewObject<UStaticMeshComponent>(Park, *Name);
            C->SetStaticMesh(Mesh); C->SetMobility(EComponentMobility::Static); C->SetupAttachment(Park->GetRootComponent());
            C->SetRelativeLocation(JsonVector(Entry->GetArrayField(TEXT("origin_cm"))));
            C->SetCanEverAffectNavigation(false);
            if (bCollision)
            {
                // The original riding surfaces: invisible, blocking, and read by the skating snapshot.
                C->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
                C->SetVisibility(false); C->SetHiddenInGame(true); C->SetCastShadow(false);
            }
            else C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            C->RegisterComponent(); ++Meshes;
        }
    }
    for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("rails")))
    {
        const TSharedPtr<FJsonObject> Entry = Value->AsObject();
        FMegaParkRail& Rail = Park->Rails.AddDefaulted_GetRef();
        Rail.SourceId = Entry->GetStringField(TEXT("id")); Rail.Closed = Entry->GetBoolField(TEXT("closed"));
        for (const TSharedPtr<FJsonValue>& Point : Entry->GetArrayField(TEXT("points_cm"))) Rail.Points.Add(JsonVector(Point->AsArray()));
    }
    Park->RegisterRails();
    const TSharedPtr<FJsonObject> Start = Root->GetObjectField(TEXT("spawn"));
    Park->SpawnLocation = JsonVector(Start->GetArrayField(TEXT("location_cm")));
    Park->SpawnYaw = Start->GetNumberField(TEXT("yaw_deg"));
    UE_LOG(LogTemp, Display, TEXT("MEGAPARK placed at %s yaw %.1f: %d meshes (%d not imported), %d rails"),
        *Placement.GetLocation().ToString(), Placement.Rotator().Yaw, Meshes, Missing, Park->Rails.Num());
    return Park;
}

void ASuperUltraMegaPark::RegisterRails()
{
    USkateRailSubsystem* Registry = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    if (!Registry || bRailsRegistered) return;
    bRailsRegistered = true;
    int32 Count = 0;
    for (const FMegaParkRail& Source : Rails)
    {
        if (Source.Points.Num() < 2) continue;
        FSkateRail Rail;
        Rail.Id = FName(*Source.SourceId);
        Rail.Kind = ESkateRailKind::Rail;
        Rail.Radius = 2.5f;
        for (const FVector& Point : Source.Points)
            Rail.Points.Add(GetActorTransform().TransformPosition(Point));
        if (Source.Closed && !Rail.Points[0].Equals(Rail.Points.Last(), .01f))
            Rail.Points.Add(Rail.Points[0]);
        if (Registry->Add(MoveTemp(Rail)) != INDEX_NONE) ++Count;
    }
    UE_LOG(LogTemp, Display, TEXT("MEGAPARK registered %d original grind paths"), Count);
}

AMegaParkGameMode::AMegaParkGameMode()
{
    DefaultPawnClass = ACairoCharacter::StaticClass();
    HUDClass = AJapanHUD::StaticClass();
}

void AMegaParkGameMode::BeginPlay()
{
    Super::BeginPlay();
    for (TActorIterator<AMegaParkWorld> It(GetWorld()); It; ++It)
        if (AWandererCharacter* Player = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0)))
        {
            // GameMode BeginPlay can precede level actor BeginPlay.
            It->PlayerStart = FTransform(FRotator(0.f, It->SpawnYaw, 0.f), It->SpawnGround);
            It->bLoaded = true;
            Player->EnterWorld(*It);
            break;
        }
}

AMegaParkWorld::AMegaParkWorld()
{
    PrimaryActorTick.bCanEverTick = false;
}

void AMegaParkWorld::BeginPlay()
{
    // AJapanWorld::BeginPlay generates the island. This level already owns its geometry.
    AActor::BeginPlay();
    PlayerStart = FTransform(FRotator(0.f, SpawnYaw, 0.f), SpawnGround);
    bLoaded = true;
}

bool UMegaParkValidation::DumpMeshTriangles(UStaticMesh* Mesh, FVector Origin, const FString& Path)
{
    if (!Mesh || !Mesh->GetRenderData() || Mesh->GetRenderData()->LODResources.IsEmpty()) return false;
    const FStaticMeshLODResources& LOD = Mesh->GetRenderData()->LODResources[0];
    const FIndexArrayView Indices = LOD.IndexBuffer.GetArrayView();
    const FPositionVertexBuffer& Positions = LOD.VertexBuffers.PositionVertexBuffer;
    TArray<uint8> Bytes;
    Bytes.Reserve(Indices.Num() * 3 * sizeof(double));
    for (int32 Index = 0; Index < Indices.Num(); ++Index)
    {
        const FVector P = Origin + FVector(Positions.VertexPosition(Indices[Index]));
        for (double Value : {P.X, P.Y, P.Z})
            Bytes.Append(reinterpret_cast<const uint8*>(&Value), sizeof(double));
    }
    return FFileHelper::SaveArrayToFile(Bytes, *Path);
}

bool UMegaParkValidation::ReviewCamera(FVector Location, FVector Target, float Fov)
{
    UWorld* World = ULiveLibrary::GameWorld();
    APlayerController* Controller = World ? UGameplayStatics::GetPlayerController(World, 0) : nullptr;
    if (!Controller) return false;
    ACameraActor* Camera = nullptr;
    const FName Tag(TEXT("MegaParkReviewCamera"));
    for (TActorIterator<ACameraActor> It(World); It; ++It)
        if (It->ActorHasTag(Tag)) { Camera = *It; break; }
    if (!Camera)
    {
        Camera = World->SpawnActor<ACameraActor>();
        if (!Camera) return false;
        Camera->Tags.Add(Tag);
    }
    Camera->SetActorLocationAndRotation(Location, (Target-Location).Rotation());
    Camera->GetCameraComponent()->SetFieldOfView(Fov);
    Controller->SetViewTarget(Camera);
    return true;
}

void UMegaParkValidation::RestorePlayerCamera()
{
    if (APawn* Player = ULiveLibrary::Player())
        if (APlayerController* Controller = Cast<APlayerController>(Player->GetController()))
            Controller->SetViewTarget(Player);
}
