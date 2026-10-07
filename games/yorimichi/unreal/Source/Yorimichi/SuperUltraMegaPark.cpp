#include "SuperUltraMegaPark.h"
#include "BotwRider.h"
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
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "SeeThrough.h"
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
    // The island trees and bushes where the original desert plants stood. They have no collision, so the riding
    // surfaces and the skating snapshot stay the original ones (docs/MEGAPARK.md, "Restyle").
    int32 Trees = 0;
    const TSharedPtr<FJsonObject>* TreeGroups = nullptr;
    if (Root->TryGetObjectField(TEXT("trees"), TreeGroups))
        for (const auto& Pair : (*TreeGroups)->Values)
        {
            const FString Key(Pair.Key);
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Key, *Key));
            if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("MEGAPARK: missing tree mesh %s"), *Key); continue; }
            TArray<FTransform> Xs;
            for (const TSharedPtr<FJsonValue>& Value : Pair.Value->AsArray())
            {
                const TArray<TSharedPtr<FJsonValue>>& A = Value->AsArray();
                if (A.Num() < 5) continue;
                Xs.Add(FTransform(FRotator(0., A[3]->AsNumber(), 0.), FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()),
                    FVector(A[4]->AsNumber())));
            }
            auto* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(Park, *Key);
            H->SetStaticMesh(Mesh); H->SetMobility(EComponentMobility::Static); H->SetupAttachment(Park->GetRootComponent());
            H->SetCanEverAffectNavigation(false);
            H->SetCollisionEnabled(ECollisionEnabled::NoCollision);
            // Like the island's trees, they fade where they hide Cairo (docs/CAMERA.md).
            const int32 Fade = JapanSeeThrough::FadeMode(Key, Mesh);
            if (Fade != JapanSeeThrough::FadeSolid) H->SetCustomPrimitiveDataFloat(0, float(Fade));
            if (Key.StartsWith(TEXT("Bush"))) H->SetCullDistances(30000, 36000);
            H->SetWorldPositionOffsetDisableDistance(18000);
            H->RegisterComponent();
            H->AddInstances(Xs, false, false, false);
            Trees += Xs.Num();
        }
    // The kei cars in the car park's bays, where the original traffic cars stood. They are solid, so Cairo walks round
    // them and the board stops against them (docs/MEGAPARK.md, "Restyle").
    int32 Props = 0;
    const TArray<TSharedPtr<FJsonValue>>* PropList = nullptr;
    if (Root->TryGetArrayField(TEXT("props"), PropList))
        for (const TSharedPtr<FJsonValue>& Value : *PropList)
        {
            const TSharedPtr<FJsonObject> Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("mesh"));
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Name, *Name));
            if (!Mesh) { ++Missing; UE_LOG(LogTemp, Warning, TEXT("MEGAPARK: missing prop mesh %s"), *Name); continue; }
            const FMatrix Basis = FRotationMatrix::MakeFromXZ(JsonVector(Entry->GetArrayField(TEXT("forward"))),
                                                               JsonVector(Entry->GetArrayField(TEXT("up"))));
            auto* C = NewObject<UStaticMeshComponent>(Park, *Name);
            C->SetStaticMesh(Mesh); C->SetMobility(EComponentMobility::Static); C->SetupAttachment(Park->GetRootComponent());
            C->SetRelativeTransform(FTransform(Basis.Rotator(), JsonVector(Entry->GetArrayField(TEXT("location_cm")))));
            C->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
            C->SetCanEverAffectNavigation(false);
            C->RegisterComponent(); ++Props;
        }
    const TSharedPtr<FJsonObject> Start = Root->GetObjectField(TEXT("spawn"));
    Park->SpawnLocation = JsonVector(Start->GetArrayField(TEXT("location_cm")));
    Park->SpawnYaw = Start->GetNumberField(TEXT("yaw_deg"));
    UE_LOG(LogTemp, Display, TEXT("MEGAPARK placed at %s yaw %.1f: %d meshes (%d not imported), %d rails, %d trees, %d props"),
        *Placement.GetLocation().ToString(), Placement.Rotator().Yaw, Meshes, Missing, Park->Rails.Num(), Trees, Props);
    Park->bGameplayReady = Missing == 0 && Meshes > 0 && !Park->Rails.IsEmpty() && Park->RegisteredRailCount == Park->Rails.Num();
    return Park;
}

void ASuperUltraMegaPark::RegisterRails()
{
    USkateRailSubsystem* Registry = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    // Runtime-spawned client worlds can BeginPlay before Spawn has filled the manifest.
    // Do not mark an empty list registered and permanently lose its grind paths.
    if (!Registry || bRailsRegistered || Rails.IsEmpty()) return;
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
    RegisteredRailCount = Count;
}

UClass* AMegaParkGameMode::GetDefaultPawnClassForController_Implementation(AController* Controller)
{
    if (UClass* Rider = ABotwRider::PawnOverride()) return Rider;
    return Super::GetDefaultPawnClassForController_Implementation(Controller);
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
