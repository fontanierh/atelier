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

ASuperUltraMegaPark::ASuperUltraMegaPark()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void ASuperUltraMegaPark::BeginPlay()
{
    Super::BeginPlay();
    USkateRailSubsystem* Registry = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    if (!Registry) return;
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
