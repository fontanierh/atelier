#include "SuperUltraMegaPark.h"
#include "PlayableCharacter.h"
#include "WandererCharacter.h"
#include "JapanHUD.h"
#include "SkateRails.h"
#include "SkateAssistZones.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Engine/StaticMesh.h"
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
#include "Misc/PackageName.h"
#include "Misc/Paths.h"
#include "AtelierData.h"
#include "V2ScenePatch.h"

ASuperUltraMegaPark::ASuperUltraMegaPark()
{
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void ASuperUltraMegaPark::BeginPlay()
{
    Super::BeginPlay();
    // Spawned in the island, the rails arrive with the manifest after BeginPlay.
    if (!Layout.Rails.IsEmpty()) RegisterRails();
}

static FVector JsonVector(const TArray<TSharedPtr<FJsonValue>>& A)
{
    return A.Num() >= 3 ? FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()) : FVector::ZeroVector;
}

UStaticMeshComponent* ASuperUltraMegaPark::MakePiece(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Entry,
    UStaticMesh* Mesh, bool bCollision)
{
    const FString Name = Entry->GetStringField(TEXT("name"));
    auto* C = NewObject<UStaticMeshComponent>(Outer, *Name);
    C->SetStaticMesh(Mesh); C->SetMobility(EComponentMobility::Static); C->SetupAttachment(Parent);
    C->SetRelativeLocation(JsonVector(Entry->GetArrayField(TEXT("origin_cm"))));
    C->SetCanEverAffectNavigation(false);
    if (bCollision)
    {
        // The original riding surfaces: invisible and blocking (the riding traces and the skating ground read them).
        C->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
        C->SetVisibility(false); C->SetHiddenInGame(true); C->SetCastShadow(false);
    }
    else C->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    return C;
}

UHierarchicalInstancedStaticMeshComponent* ASuperUltraMegaPark::MakeTreeGroup(UObject* Outer, USceneComponent* Parent,
    const FString& Key, UStaticMesh* Mesh)
{
    auto* H = NewObject<UHierarchicalInstancedStaticMeshComponent>(Outer, *Key);
    H->SetStaticMesh(Mesh); H->SetMobility(EComponentMobility::Static); H->SetupAttachment(Parent);
    H->SetCanEverAffectNavigation(false);
    H->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    // Like the island's trees, they fade where they hide Cairo (docs/CAMERA.md).
    const int32 Fade = JapanSeeThrough::FadeMode(Key, Mesh);
    if (Fade != JapanSeeThrough::FadeSolid) H->SetCustomPrimitiveDataFloat(0, float(Fade));
    if (Key.StartsWith(TEXT("Bush"))) H->SetCullDistances(30000, 36000);
    H->SetWorldPositionOffsetDisableDistance(18000);
    return H;
}

bool ASuperUltraMegaPark::TreeTransform(const TSharedPtr<FJsonValue>& Value, FTransform& Out)
{
    const TArray<TSharedPtr<FJsonValue>>& A = Value->AsArray();
    if (A.Num() < 5) return false;
    Out = FTransform(FRotator(0., A[3]->AsNumber(), 0.), FVector(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber()),
        FVector(A[4]->AsNumber()));
    return true;
}

bool ASuperUltraMegaPark::LoadTreeOwners(const TSharedPtr<FJsonObject>& Root, const FString& ParkPath, FParkTreeOwners& Out)
{
    Out = FParkTreeOwners();
    const auto Owners = AtelierReadJson(FPaths::Combine(FPaths::GetPath(ParkPath), TEXT("tree_units.json")));
    const TSharedPtr<FJsonObject>* Pieces = nullptr;
    if (!Owners || !Owners->TryGetObjectField(TEXT("pieces"), Pieces)) return false;
    FParkTreeOwners Loaded;
    if (const TArray<TSharedPtr<FJsonValue>>* Unsaved = nullptr; Owners->TryGetArrayField(TEXT("unsaved_trees"), Unsaved))
        for (const TSharedPtr<FJsonValue>& Value : *Unsaved) Loaded.UnsavedSpecies.Add(Value->AsString());
    for (const TCHAR* Kind : {TEXT("render"), TEXT("collision")})
        for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(Kind))
        {
            const TSharedPtr<FJsonObject> Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("name"));
            FString Unit;
            if (!(*Pieces)->TryGetStringField(Name, Unit) || Unit.IsEmpty()) return false;
            const TArray<TSharedPtr<FJsonValue>>& Origin = Entry->GetArrayField(TEXT("origin_cm"));
            Loaded.Pieces.Add({Unit, Origin[0]->AsNumber(), Origin[1]->AsNumber()});
        }
    Out = MoveTemp(Loaded);
    return true;
}

FString ASuperUltraMegaPark::TreeUnit(const FParkTreeOwners& Owners, const FString& Species, const FVector& Location)
{
    if (Owners.UnsavedSpecies.Contains(Species)) return FString();
    return NearestUnit(Owners, Location);
}

FString ASuperUltraMegaPark::NearestUnit(const FParkTreeOwners& Owners, const FVector& Location)
{
    FString Best;
    double BestDistance = 0.;
    for (const FParkTreeOwners::FPiece& Piece : Owners.Pieces)
    {
        // The strict comparison keeps the earlier piece on a tie, as parks.py's min over (distance, index) does.
        const double Dx = Piece.X - Location.X, Dy = Piece.Y - Location.Y;
        const double Distance = Dx * Dx + Dy * Dy;
        if (Best.IsEmpty() || Distance < BestDistance) { Best = Piece.Unit; BestDistance = Distance; }
    }
    return Best;
}

namespace
{
    // A park-local point (or direction) moved with its unit: the unit moved by Moved in the world, which the park's placement
    // carries into its own frame as ParkInverse * Moved * Park.
    FTransform LocalMoveOf(const FTransform& Park, const FTransform& Moved)
    {
        return Park * Moved * Park.Inverse();   // park-local -> world, the world move, back to park-local (UE order)
    }
}

UStaticMeshComponent* ASuperUltraMegaPark::MakeProp(UObject* Outer, USceneComponent* Parent, const TSharedPtr<FJsonObject>& Entry,
    UStaticMesh* Mesh)
{
    const FString Name = Entry->GetStringField(TEXT("mesh"));
    const FMatrix Basis = FRotationMatrix::MakeFromXZ(JsonVector(Entry->GetArrayField(TEXT("forward"))),
                                                       JsonVector(Entry->GetArrayField(TEXT("up"))));
    auto* C = NewObject<UStaticMeshComponent>(Outer, *Name);
    C->SetStaticMesh(Mesh); C->SetMobility(EComponentMobility::Static); C->SetupAttachment(Parent);
    C->SetRelativeTransform(FTransform(Basis.Rotator(), JsonVector(Entry->GetArrayField(TEXT("location_cm")))));
    C->SetCollisionProfileName(UCollisionProfile::BlockAll_ProfileName);
    C->SetCanEverAffectNavigation(false);
    return C;
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
    Park->Layout.SourceManifestHash = Root->GetStringField(TEXT("source_sha256"));
    // Another park (Crater Park, docs/CRATERPARK.md) names its own mesh folder and log tag, and may have no grind paths.
    FString MeshRoot = TEXT("/Game/MegaPark/Meshes"), Tag = TEXT("MEGAPARK");
    bool bRailsRequired = true;
    Root->TryGetStringField(TEXT("mesh_root"), MeshRoot);
    Root->TryGetStringField(TEXT("name"), Tag);
    Root->TryGetBoolField(TEXT("rails_required"), bRailsRequired);
    // Pieces a saved unit holds (UV2Migration::MigrateParkPieces) are not spawned again: the map's manifest lists them as
    // "<tag>:<mesh>". A standalone park map has no manifest and spawns every piece, as before.
    const AV2WorldManifest* Manifest = AV2WorldManifest::Find(World);
    const FName SavedTag(*Tag.ToLower());
    int32 Meshes = 0, Missing = 0;
    // A saved unit the editor moved (AV2ScenePatch::MovedBy from the placement the migration saved it at): its rails and zones
    // follow it, below. An unmoved unit is absent here, so its rails and zones are built exactly as before.
    TMap<FString, FTransform> MovedUnits;
    bool bTreesSaved = false;
    if (Manifest)
    {
        const FString Prefix = Tag.ToLower() + TEXT(":");
        for (TActorIterator<AV2ScenePatch> It(World); It; ++It)
        {
            const FString Source = It->SourceKey;
            if (!Source.StartsWith(Prefix)) continue;
            const FString Unit = Source.Mid(Prefix.Len());
            if (Unit.Contains(TEXT("/"))) continue;   // a unit's trees and props, not its pieces
            const FTransform Moved = It->MovedBy();
            if (!Moved.Equals(FTransform::Identity, 0.)) MovedUnits.Add(Unit, Moved);
        }
        const FString TreePrefix = Tag.ToLower() + TEXT(":trees/");
        for (const FString& Group : Manifest->MigratedGroups)
            if (Group.StartsWith(TreePrefix)) { bTreesSaved = true; break; }
    }
    // The unit owners (tree_units.json) place the saved trees and the rails and zones of a moved unit.
    FParkTreeOwners TreeOwners;
    bool bOwners = true;
    if (bTreesSaved || !MovedUnits.IsEmpty()) bOwners = LoadTreeOwners(Root, Path, TreeOwners);
    if (!bOwners)
    {
        // Without the owners the saved trees would spawn beside themselves, and a moved unit's rails would stay behind: not ready.
        ++Missing; UE_LOG(LogTemp, Error, TEXT("%s has saved units but its tree_units.json does not name their pieces"), *Tag);
    }
    for (const TCHAR* Kind : {TEXT("render"), TEXT("collision")})
    {
        const bool bCollision = FCString::Strcmp(Kind, TEXT("collision")) == 0;
        for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(Kind))
        {
            const TSharedPtr<FJsonObject> Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("name"));
            if (Manifest && Manifest->CoversGroup(SavedTag, Name))
            {
                // Its saved unit draws it; its mesh must still be committed content (checked without loading it).
                if (FPackageName::DoesPackageExist(FString::Printf(TEXT("%s/%s"), *MeshRoot, *Name))) ++Meshes;
                else { ++Missing; UE_LOG(LogTemp, Error, TEXT("%s missing saved piece %s"), *Tag, *Name); }
                continue;
            }
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *MeshRoot, *Name, *Name));
            if (!Mesh) { ++Missing; continue; }
            MakePiece(Park, Park->GetRootComponent(), Entry, Mesh, bCollision)->RegisterComponent(); ++Meshes;
        }
    }
    for (const TSharedPtr<FJsonValue>& Value : Root->GetArrayField(TEXT("rails")))
    {
        const TSharedPtr<FJsonObject> Entry = Value->AsObject();
        FMegaParkRail& Rail = Park->Layout.Rails.AddDefaulted_GetRef();
        Rail.SourceId = Entry->GetStringField(TEXT("id")); Rail.Closed = Entry->GetBoolField(TEXT("closed"));
        for (const TSharedPtr<FJsonValue>& Point : Entry->GetArrayField(TEXT("points_cm"))) Rail.Points.Add(JsonVector(Point->AsArray()));
    }
    // A rail follows the unit that owns it (the piece nearest its first point) when the editor moved that unit.
    if (bOwners && !MovedUnits.IsEmpty())
        for (FMegaParkRail& Rail : Park->Layout.Rails)
        {
            if (Rail.Points.IsEmpty()) continue;
            const FTransform* Moved = MovedUnits.Find(NearestUnit(TreeOwners, Rail.Points[0]));
            if (!Moved) continue;
            const FTransform Local = LocalMoveOf(Placement, *Moved);
            for (FVector& Point : Rail.Points) Point = Local.TransformPosition(Point);
        }
    Park->RegisterRails();
    // Where the rider's vert assist is limited (docs/CRATERPARK.md, "Assist zones"): boxes in world centimetres, turned
    // yaw_deg about up. The kickers into a big gap's landing limit it, so the air goes forward, not back into the ramp.
    // Boost zones ("Boost zones") are the same boxes with a boost scale: pumping and powersliding on their transitions
    // gain speed (the bowls the owner chose).
    int32 Zones = 0, Boosts = 0;
    if (USkateAssistSubsystem* Assist = World->GetSubsystem<USkateAssistSubsystem>())
        for (const bool bBoost : {false, true})
        {
            const TCHAR* const ListField = bBoost ? TEXT("boost_zones") : TEXT("assist_zones");
            const TCHAR* const ValueField = bBoost ? TEXT("boost") : TEXT("vert_assist_max");
            const TArray<TSharedPtr<FJsonValue>>* ZoneList = nullptr;
            if (!Root->TryGetArrayField(ListField, ZoneList)) continue;
            for (const TSharedPtr<FJsonValue>& Value : *ZoneList)
            {
                const TSharedPtr<FJsonObject> Entry = Value->AsObject();
                const TArray<TSharedPtr<FJsonValue>>* Centre = nullptr; const TArray<TSharedPtr<FJsonValue>>* Half = nullptr;
                double Number = 1.;
                if (!Entry.IsValid() || !Entry->TryGetArrayField(TEXT("center_cm"), Centre) || !Entry->TryGetArrayField(TEXT("half_extent_cm"), Half)
                    || !Entry->TryGetNumberField(ValueField, Number) || Centre->Num() < 3 || Half->Num() < 3)
                { UE_LOG(LogTemp, Warning, TEXT("%s: a %s entry without center_cm, half_extent_cm and %s is skipped"), *Tag, ListField, ValueField); continue; }
                FSkateAssistZone Zone;
                Zone.Id = FName(Entry->HasField(TEXT("id")) ? Entry->GetStringField(TEXT("id")) : FString::Printf(TEXT("zone_%d"), Zones + Boosts));
                Zone.Centre = JsonVector(*Centre); Zone.HalfExtent = JsonVector(*Half);
                Zone.YawDeg = Entry->HasField(TEXT("yaw_deg")) ? float(Entry->GetNumberField(TEXT("yaw_deg"))) : 0.f;
                if (bOwners && !MovedUnits.IsEmpty())
                    if (const FTransform* Moved = MovedUnits.Find(NearestUnit(TreeOwners, Zone.Centre)))
                    {
                        // The box follows its unit: its centre and yaw move; its extent does not.
                        const FTransform Local = LocalMoveOf(Placement, *Moved);
                        Zone.Centre = Local.TransformPosition(Zone.Centre);
                        Zone.YawDeg += float(Local.Rotator().Yaw);
                    }
                if (bBoost) Zone.Boost = float(Number); else Zone.VertAssistMax = float(Number);
                Zone.Owner = Park;
                Assist->Add(MoveTemp(Zone)); ++(bBoost ? Boosts : Zones);
            }
        }
    if (Zones || Boosts) UE_LOG(LogTemp, Display, TEXT("%s: %d assist zones, %d boost zones"), *Tag, Zones, Boosts);
    // The island trees and bushes where the original desert plants stood. They have no collision, so the riding
    // surfaces and the skating snapshot stay the original ones (docs/MEGAPARK.md, "Restyle").
    // Trees a saved unit holds (UV2MigrationParkDressing::MigrateParkTrees) are not spawned again: TreeUnit names the unit a
    // tree belongs to, and the manifest lists that unit as "<tag>:trees/<unit>". A standalone park map spawns every tree.
    int32 Trees = 0, SavedTreeCount = 0;
    const TSharedPtr<FJsonObject>* TreeGroups = nullptr;
    if (Root->TryGetObjectField(TEXT("trees"), TreeGroups))
        for (const auto& Pair : (*TreeGroups)->Values)
        {
            const FString Key(Pair.Key);
            TArray<FTransform> Xs;
            bool bSkipped = false;
            const TArray<TSharedPtr<FJsonValue>>& List = Pair.Value->AsArray();
            for (int32 Index = 0; Index < List.Num(); ++Index)
            {
                FTransform X;
                if (!TreeTransform(List[Index], X)) continue;
                const FString Unit = bTreesSaved && bOwners ? TreeUnit(TreeOwners, Key, X.GetLocation()) : FString();
                if (!Unit.IsEmpty() && Manifest->CoversGroup(SavedTag, FString(TEXT("trees/")) + Unit))
                {
                    ++SavedTreeCount; bSkipped = true;
                    continue;
                }
                Xs.Add(X);
            }
            if (bSkipped && !FPackageName::DoesPackageExist(FString::Printf(TEXT("/Game/Japan/Assets/%s"), *Key)))
            {
                // Its saved unit draws it; its mesh must still be committed content (checked without loading it).
                ++Missing; UE_LOG(LogTemp, Error, TEXT("%s missing saved tree mesh %s"), *Tag, *Key);
            }
            if (Xs.IsEmpty()) continue;
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Key, *Key));
            if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("MEGAPARK: missing tree mesh %s"), *Key); continue; }
            auto* H = MakeTreeGroup(Park, Park->GetRootComponent(), Key, Mesh);
            H->RegisterComponent();
            H->AddInstances(Xs, false, false, false);
            Trees += Xs.Num();
        }
    Trees += SavedTreeCount;
    // The kei cars in the car park's bays, where the original traffic cars stood. They are solid, so Cairo walks round
    // them and the board stops against them (docs/MEGAPARK.md, "Restyle").
    int32 Props = 0;
    const TArray<TSharedPtr<FJsonValue>>* PropList = nullptr;
    if (Root->TryGetArrayField(TEXT("props"), PropList))
        for (const TSharedPtr<FJsonValue>& Value : *PropList)
        {
            const TSharedPtr<FJsonObject> Entry = Value->AsObject();
            const FString Name = Entry->GetStringField(TEXT("mesh"));
            // A kei car saved as its own object (UV2MigrationParkDressing::MigrateParkProps) is not spawned again.
            if (Manifest && Manifest->CoversGroup(SavedTag, Name))
            {
                if (FPackageName::DoesPackageExist(FString::Printf(TEXT("/Game/Japan/Assets/%s"), *Name))) ++Props;
                else { ++Missing; UE_LOG(LogTemp, Error, TEXT("%s missing saved prop %s"), *Tag, *Name); }
                continue;
            }
            UStaticMesh* Mesh = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/Japan/Assets/%s.%s"), *Name, *Name));
            if (!Mesh) { ++Missing; UE_LOG(LogTemp, Warning, TEXT("MEGAPARK: missing prop mesh %s"), *Name); continue; }
            UStaticMeshComponent* C = MakeProp(Park, Park->GetRootComponent(), Entry, Mesh);
            C->RegisterComponent(); ++Props;
        }
    const TSharedPtr<FJsonObject> Start = Root->GetObjectField(TEXT("spawn"));
    Park->Layout.SpawnGround = JsonVector(Start->GetArrayField(TEXT("location_cm")));
    Park->Layout.SpawnYaw = Start->GetNumberField(TEXT("yaw_deg"));
    UE_LOG(LogTemp, Display, TEXT("%s placed at %s yaw %.1f: %d meshes (%d not imported), %d rails, %d trees, %d props"),
        *Tag, *Placement.GetLocation().ToString(), Placement.Rotator().Yaw, Meshes, Missing, Park->Layout.Rails.Num(), Trees, Props);
    Park->bGameplayReady = Missing == 0 && Meshes > 0 && (!bRailsRequired || !Park->Layout.Rails.IsEmpty())
        && Park->RegisteredRailCount == Park->Layout.Rails.Num();
    return Park;
}

void ASuperUltraMegaPark::RegisterRails()
{
    USkateRailSubsystem* Registry = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    // Runtime-spawned client worlds can BeginPlay before Spawn has filled the manifest.
    // Do not mark an empty list registered and permanently lose its grind paths.
    if (!Registry || bRailsRegistered || Layout.Rails.IsEmpty()) return;
    bRailsRegistered = true;
    int32 Count = 0;
    for (const FMegaParkRail& Source : Layout.Rails)
    {
        if (Source.Points.Num() < 2) continue;
        FSkateRail Rail;
        Rail.Id = FName(*Source.SourceId);
        for (const FVector& Point : Source.Points)
            Rail.Points.Add(GetActorTransform().TransformPosition(Point));
        if (Source.Closed && !Rail.Points[0].Equals(Rail.Points.Last(), .01f))
        {
            const FVector First = Rail.Points[0];       // a copy: Add may reallocate the array the reference points into
            Rail.Points.Add(First);
        }
        if (Registry->Add(MoveTemp(Rail)) != INDEX_NONE) ++Count;
    }
    UE_LOG(LogTemp, Display, TEXT("MEGAPARK registered %d original grind paths"), Count);
    RegisteredRailCount = Count;
}

UClass* AMegaParkGameMode::GetDefaultPawnClassForController_Implementation(AController* Controller)
{
    if (UClass* Rider = FPlayableCharacter::PawnOverride()) return Rider;
    // Resolved here, not in the constructor: the characters register from their records once the game is running.
    if (UClass* Player = FPlayableCharacter::Default().Class()) return Player;
    return Super::GetDefaultPawnClassForController_Implementation(Controller);
}

AMegaParkGameMode::AMegaParkGameMode()
{
    HUDClass = AJapanHUD::StaticClass();
}

void AMegaParkGameMode::StartPlay()
{
    // Before Super::StartPlay begins play, so the spawned actors begin it with the level's.
    TActorIterator<AMegaParkLayout> Source(GetWorld());
    if (!Source)
    {
        const FString Message = FString::Printf(TEXT("MEGAPARK: %s was saved before its layout (AMegaParkLayout) and has "
            "no grind paths or player services; run atelier build yorimichi"), *GetWorld()->GetMapName());
        UE_LOG(LogTemp, Error, TEXT("%s"), *Message);
        if (GEngine) GEngine->AddOnScreenDebugMessage(-1, 600.f, FColor::Red, Message);
    }
    else
    {
        if (auto* Park = GetWorld()->SpawnActor<ASuperUltraMegaPark>(ASuperUltraMegaPark::StaticClass(), Source->GetActorTransform()))
            Park->Layout = Source->Layout;
        if (auto* Services = GetWorld()->SpawnActor<AMegaParkWorld>())
            Services->PlayerStart = FTransform(FRotator(0.f, Source->Layout.SpawnYaw, 0.f), Source->Layout.SpawnGround);
    }
    Super::StartPlay();
}

void AMegaParkGameMode::BeginPlay()
{
    Super::BeginPlay();
    for (TActorIterator<AMegaParkWorld> It(GetWorld()); It; ++It)
        if (AWandererCharacter* Player = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0)))
        {
            // GameMode BeginPlay can precede level actor BeginPlay.
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
    // AJapanWorld::BeginPlay generates the island. This level already owns its geometry; the game mode set PlayerStart.
    AActor::BeginPlay();
    bLoaded = true;
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
