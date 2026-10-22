#include "BelmonteTrainService.h"
#include "BelmonteTrainRules.h"
#include "BelmonteTrainRecovery.h"
#include "JapanActivityState.h"
#include "BelmonteTrack.h"
#include "AtelierData.h"
#include "JapanNetwork.h"
#include "Net/UnrealNetwork.h"
#include "SkateComponent.h"
#include "Algo/BinarySearch.h"
#include "Algo/Reverse.h"
#include "WandererCharacter.h"
#include "LiveLibrary.h"
#include "JapanWorld.h"   // JapanCameraArm.h needs AJapanWorld complete
#include "JapanCameraArm.h"
#include "JapanCharacterMovement.h"
#include "AdventureMoveSet.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/SpringArmComponent.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "PhysicsEngine/BodySetup.h"
#include "Dom/JsonObject.h"

static TAutoConsoleVariable<float> CVarTrainTimeScale(TEXT("train.TimeScale"), 1.f,
    TEXT("Belmonte train service clock speed (1 = the timetable; dev only, local to this machine)."));

static FAutoConsoleCommandWithWorldAndArgs TrainGoCommand(TEXT("train.Go"),
    TEXT("train.Go [belmonte|hidamari]: travel to a terminus platform as the next train starts its dwell there."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Service = ABelmonteTrainService::Find(World)) Service->GoToStation(Args.Num() ? Args[0] : FString(TEXT("belmonte")), true);
    }));

static FAutoConsoleCommandWithWorldAndArgs TrainViewCommand(TEXT("train.View"),
    TEXT("train.View [view|loop|a|b|<chainage m>]: jump the Belmonte train clock and stand beside the line where a train "
         "is about to pass (view: the longest stretch above ground; loop: the next crossing)."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Service = ABelmonteTrainService::Find(World)) Service->View(Args.Num() ? Args[0] : FString(TEXT("view")));
        else UE_LOG(LogTemp, Warning, TEXT("TRAIN VIEW no Belmonte train service in this world"));
    }));

// ------------------------------------------------------------------------------------------------------------ Line

FVector FBelmonteTrainTrack::At(double Chainage) const
{
    if (IsEmpty()) return FVector::ZeroVector;
    if (Chainage <= S[0]) return P[0];
    if (Chainage >= S.Last()) return P.Last();
    const int32 I = FMath::Clamp(Algo::UpperBound(S, Chainage) - 1, 0, S.Num() - 2);
    const double F = (Chainage - S[I]) / FMath::Max(S[I + 1] - S[I], 1e-6);
    return FMath::Lerp(P[I], P[I + 1], F);
}

static bool ReadTrack(const TArray<TSharedPtr<FJsonValue>>& Rows, FBelmonteTrainTrack& Track)
{
    for (const auto& Row : Rows)
    {
        const auto& A = Row->AsArray();
        if (A.Num() < 4) return false;
        if (Track.S.Num() && A[0]->AsNumber() <= Track.S.Last()) return false;
        Track.S.Add(A[0]->AsNumber());
        Track.P.Add(FVector(A[1]->AsNumber(), A[2]->AsNumber(), A[3]->AsNumber()));
    }
    return true;
}

bool FBelmonteTrainLine::Parse(const TSharedPtr<FJsonObject>& Root, FString& Error)
{
    *this = FBelmonteTrainLine();
    const TSharedPtr<FJsonObject>* LineData = nullptr; const TSharedPtr<FJsonObject>* ServiceData = nullptr;
    if (!Root || !Root->TryGetObjectField(TEXT("line"), LineData) || !Root->TryGetObjectField(TEXT("service"), ServiceData))
    { Error = TEXT("no line or service"); return false; }
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!(*LineData)->TryGetArrayField(TEXT("main"), Rows) || !ReadTrack(*Rows, Main) || Main.IsEmpty())
    { Error = TEXT("bad main line"); return false; }
    const TSharedPtr<FJsonObject>* LoopData = nullptr;
    if ((*LineData)->TryGetObjectField(TEXT("loop"), LoopData) && (*LoopData)->TryGetArrayField(TEXT("points"), Rows) && Rows->Num() >= 2)
    {
        if (!ReadTrack(*Rows, Loop)) { Error = TEXT("bad loop track"); return false; }
        LoopStart = Loop.S[0]; LoopEnd = Loop.S.Last();
    }
    if ((*LineData)->TryGetArrayField(TEXT("viewpoints"), Rows))
        for (const auto& V : *Rows)
        {
            const auto View = V->AsObject();
            Viewpoints.Add(View->GetNumberField(TEXT("s")));
            FString Class; double Start = 0., End = 0.;
            if (View->TryGetStringField(TEXT("class"), Class) && Class == TEXT("viaduct") &&
                View->TryGetNumberField(TEXT("start"), Start) && View->TryGetNumberField(TEXT("end"), End))
                Enclosed.Add(FVector2D(FMath::Min(Start, End), FMath::Max(Start, End)));
        }
    Cycle = (*ServiceData)->GetNumberField(TEXT("cycle_s"));
    ClockStart = (*ServiceData)->GetNumberField(TEXT("clock_start_s"));
    if (Cycle <= 1. || !(*ServiceData)->TryGetArrayField(TEXT("trains"), Rows) || Rows->IsEmpty())
    { Error = TEXT("no trains or cycle"); return false; }
    for (const auto& Value : *Rows)
    {
        const auto Object = Value->AsObject();
        FBelmonteTrainRun& Run = Trains.AddDefaulted_GetRef();
        Run.Name = Object->GetStringField(TEXT("name"));
        Run.T0 = Object->GetNumberField(TEXT("t0"));
        Run.Dt = Object->GetNumberField(TEXT("dt"));
        for (const auto& S : Object->GetArrayField(TEXT("s"))) Run.S.Add(float(S->AsNumber()));
        for (const auto& L : Object->GetArrayField(TEXT("loop_track")))
        {
            const auto& A = L->AsArray();
            if (A.Num() == 2) Run.LoopTrack.Add(FVector2D(A[0]->AsNumber(), A[1]->AsNumber()));
        }
        if (Run.Dt <= 0. || Run.S.Num() < 2) { Error = TEXT("bad train samples: ") + Run.Name; return false; }
    }
    return true;
}

int32 FBelmonteTrainLine::AddTunnels(const TSharedPtr<FJsonObject>& Track)
{
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!Track || !Track->TryGetArrayField(TEXT("tunnels"), Rows)) return 0;
    int32 Added = 0;
    for (const auto& Value : *Rows)
    {
        const TSharedPtr<FJsonObject>* Tunnel = nullptr;
        double Start = 0., End = 0.;
        if (!Value->TryGetObject(Tunnel) || !(*Tunnel)->TryGetNumberField(TEXT("start"), Start) || !(*Tunnel)->TryGetNumberField(TEXT("end"), End)) continue;
        Enclosed.Add(FVector2D(FMath::Min(Start, End), FMath::Max(Start, End)));
        ++Added;
    }
    return Added;
}

bool FBelmonteTrainLine::IsEnclosed(double From, double To) const
{
    if (From > To) Swap(From, To);
    for (const FVector2D& Range : Enclosed) if (From <= Range.Y && To >= Range.X) return true;
    return false;
}

static double LocalTime(const FBelmonteTrainRun& Run, double Cycle, double Time)
{
    return FMath::Fmod(FMath::Fmod(Time - Run.T0, Cycle) + Cycle, Cycle);
}

double FBelmonteTrainLine::Chainage(int32 Train, double Time) const
{
    if (!Trains.IsValidIndex(Train)) return 0.;
    const auto& Run = Trains[Train];
    const double F = LocalTime(Run, Cycle, Time) / Run.Dt;
    const int32 N = Run.S.Num(), I = FMath::Clamp(int32(F), 0, N - 1), J = (I + 1) % N;
    return FMath::Lerp(double(Run.S[I]), double(Run.S[J]), F - FMath::FloorToDouble(F));
}

double FBelmonteTrainLine::Speed(int32 Train, double Time) const
{
    return (Chainage(Train, Time + .25) - Chainage(Train, Time - .25)) / .5;
}

bool FBelmonteTrainLine::OnLoopTrack(int32 Train, double Time) const
{
    if (!Trains.IsValidIndex(Train) || Loop.IsEmpty()) return false;
    const double Local = LocalTime(Trains[Train], Cycle, Time);
    for (const auto& Span : Trains[Train].LoopTrack) if (Local >= Span.X && Local <= Span.Y) return true;
    return false;
}

FVector FBelmonteTrainLine::Point(double Chainage, bool bLoopTrack) const
{
    return bLoopTrack && Loop.Covers(Chainage) ? Loop.At(Chainage) : Main.At(Chainage);
}

FTransform FBelmonteTrainLine::Place(double Chainage, double BogieA, double BogieB, bool bLoopTrack) const
{
    // Vehicle +x points up the line (toward Belmonte); its bogie centres sit on the rails.
    const FVector A = Point(Chainage + BogieA, bLoopTrack), B = Point(Chainage + BogieB, bLoopTrack);
    const FVector Axis = B - A;
    const double Span = FMath::Max(BogieB - BogieA, 1e-3);
    const FVector Origin = A + Axis * (-BogieA / Span);
    return FTransform(Axis.IsNearlyZero() ? FRotator::ZeroRotator : Axis.Rotation(), Origin);
}

double FBelmonteTrainLine::NextCrossing(double From, double* Where) const
{
    if (Trains.Num() < 2) return -1.;
    double Previous = Chainage(0, From) - Chainage(1, From);
    for (double T = From + .5; T <= From + Cycle + .5; T += .5)
    {
        const double Gap = Chainage(0, T) - Chainage(1, T);
        if (Gap == 0. || (Gap > 0.) != (Previous > 0.))
        {
            if (Where) *Where = Chainage(0, T);
            return T;
        }
        Previous = Gap;
    }
    return -1.;
}

double FBelmonteTrainLine::NextPassing(double From, double At, int32* Which) const
{
    double Best = -1.;
    for (int32 Train = 0; Train < Trains.Num(); ++Train)
    {
        double Previous = Chainage(Train, From) - At;
        for (double T = From + .5; T <= From + Cycle + .5; T += .5)
        {
            const double Gap = Chainage(Train, T) - At;
            if ((Gap >= 0.) != (Previous >= 0.))
            {
                if (Best < 0. || T < Best) { Best = T; if (Which) *Which = Train; }
                break;
            }
            Previous = Gap;
        }
    }
    return Best;
}

// ------------------------------------------------------------------------------------------------------------ Service

static FVector JsonVector(const TArray<TSharedPtr<FJsonValue>>& A, int32 First = 0)
{
    if (A.Num() < First + 3) return FVector::ZeroVector;
    return FVector(A[First]->AsNumber(), A[First + 1]->AsNumber(), A[First + 2]->AsNumber());
}

static FBox JsonBox(const TArray<TSharedPtr<FJsonValue>>& A) { return FBox(JsonVector(A, 0), JsonVector(A, 3)); }

ABelmonteTrainService::ABelmonteTrainService()
{
    PrimaryActorTick.bCanEverTick = true;
    // Before the characters: riders standing on a vehicle are carried by it (based movement) in the same frame.
    PrimaryActorTick.TickGroup = TG_PrePhysics;
    bReplicates = true;
    bAlwaysRelevant = true;
    SetNetUpdateFrequency(20.f);
    SetMinNetUpdateFrequency(20.f);
    Tags.Add(TEXT("NoClimb"));   // the coaches' walls and furniture are not climbing holds (AdventureMoveSet::Climbable)
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void ABelmonteTrainService::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(ABelmonteTrainService, NetworkState);
}

void ABelmonteTrainService::BeginPlay()
{
    Super::BeginPlay();
    if (Vehicles.IsEmpty() && IsEnabled())
        Initialize(AtelierDataPath(TEXT("belmonte_train/service.json")));
}

bool ABelmonteTrainService::IsEnabled()
{
    return true;
}

ABelmonteTrainService* ABelmonteTrainService::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !IsEnabled() || !FPaths::FileExists(Path)) return nullptr;
    if (ABelmonteTrainService* Existing = Find(World)) return Existing;
    auto* Service = World->SpawnActor<ABelmonteTrainService>();
    if (Service && !Service->Initialize(Path)) { Service->Destroy(); return nullptr; }
    return Service;
}

ABelmonteTrainService* ABelmonteTrainService::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<ABelmonteTrainService> It(World);
    return It ? *It : nullptr;
}

double ABelmonteTrainService::ServiceTime() const
{
    const UWorld* World = GetWorld();
    const AGameStateBase* State = World ? World->GetGameState() : nullptr;
    const double Now = State ? State->GetServerWorldTimeSeconds() : (World ? World->GetTimeSeconds() : 0.);
    return Now + Line.ClockStart + DevOffset;
}

static UStaticMeshComponent* Block(AActor* Owner, USceneComponent* Parent, const FString& Name, UStaticMesh* Cube, const TSharedPtr<FJsonObject>& Spec, const FLinearColor& Colour)
{
    const auto& Size = Spec->GetArrayField(TEXT("size"));
    auto* C = NewObject<UStaticMeshComponent>(Owner, *Name);
    C->SetMobility(EComponentMobility::Static);
    C->SetupAttachment(Parent);
    C->SetStaticMesh(Cube);
    C->SetWorldLocationAndRotation(JsonVector(Spec->GetArrayField(TEXT("centre"))), FRotator(0., Spec->GetNumberField(TEXT("yaw")), 0.));
    C->SetWorldScale3D(JsonVector(Size) / 100.);
    C->SetCollisionProfileName(TEXT("BlockAll"));
    C->SetAffectDistanceFieldLighting(false);
    C->RegisterComponent();
    if (UMaterialInterface* Base = C->GetMaterial(0))
        if (UMaterialInstanceDynamic* M = C->CreateDynamicMaterialInstance(0, Base)) M->SetVectorParameterValue(TEXT("Color"), Colour);
    return C;
}

void ABelmonteTrainService::BuildStations(const TSharedPtr<FJsonObject>& Root)
{
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!Root->TryGetArrayField(TEXT("stations"), Rows)) return;
    UStaticMesh* Cube = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Cube.Cube"));
    for (const auto& Value : *Rows)
    {
        const auto S = Value->AsObject();
        FStation& Station = Stations.AddDefaulted_GetRef();
        Station.Key = S->GetStringField(TEXT("key")); Station.Name = S->GetStringField(TEXT("name"));
        Station.Chainage = S->GetNumberField(TEXT("chainage"));
        FString Side;
        if (S->TryGetStringField(TEXT("side"), Side)) Station.bLeft = Side != TEXT("r");
        const auto Arrival = S->GetObjectField(TEXT("arrival"));
        Station.Arrival = JsonVector(Arrival->GetArrayField(TEXT("location"))); Station.Yaw = float(Arrival->GetNumberField(TEXT("yaw")));
        // Extend Hidamari's authored platform. A freestanding platform only where the terminus has no station of its own
        // (Belmonte's station brings its platforms: no `platform` record).
        if (Cube)
        {
            if (S->HasTypedField<EJson::Object>(TEXT("platform")))
                Parts.Add(Block(this, RootComponent, Station.Key + TEXT("_Platform"), Cube, S->GetObjectField(TEXT("platform")), FLinearColor(.42f, .40f, .36f)));
            // The track (ABelmonteTrack, spawned first) brings its own buffer stops; the red block stands in without it.
            if (!FPaths::FileExists(AtelierDataPath(TEXT("belmonte_track/track.json"))))
                Parts.Add(Block(this, RootComponent, Station.Key + TEXT("_Buffer"), Cube, S->GetObjectField(TEXT("buffer")), FLinearColor(.55f, .08f, .05f)));
        }
    }
}

bool ABelmonteTrainService::Initialize(const FString& Path)
{
    if (bInitialized) return true;
    if (bInitFailed) return false;
    const TSharedPtr<FJsonObject> Root = AtelierReadJson(Path);
    FString Error;
    if (!Line.Parse(Root, Error)) { bInitFailed = true; UE_LOG(LogTemp, Error, TEXT("TRAIN SERVICE cannot read %s: %s"), *Path, *Error); return false; }
    // The tunnels, where nobody is set down beside a coach (Eject). Staged with the track (unreal.belmonte_track); without
    // the track there are no linings either, and the recovery probe refuses the terrain the line then clips.
    const FString TrackPath = AtelierDataPath(TEXT("belmonte_track/track.json"));
    const int32 Tunnels = FPaths::FileExists(TrackPath) ? Line.AddTunnels(AtelierReadJson(TrackPath)) : 0;
    const TSharedPtr<FJsonObject> Render = Root->GetObjectField(TEXT("render"));
    const float Cull = float(Render->GetNumberField(TEXT("cull_cm")));
    const TArray<TSharedPtr<FJsonValue>> Sizes = Render->GetArrayField(TEXT("screen_sizes"));
    const double LastLod = Sizes.Num() ? Sizes.Last()->AsNumber() : .15;
    const TSharedPtr<FJsonObject> Assets = Root->GetObjectField(TEXT("furniture"));
    int32 Missing = 0, Instances = 0, Leaves = 0;
    TMap<FString, UStaticMesh*> Meshes;
    auto Load = [&Meshes](const FString& Asset) -> UStaticMesh*
    {
        UStaticMesh*& Mesh = Meshes.FindOrAdd(Asset);
        if (!Mesh) Mesh = LoadObject<UStaticMesh>(nullptr, *Asset);
        return Mesh;
    };
    for (int32 Train = 0; Train < Line.Trains.Num(); ++Train)
        for (const auto& Value : Root->GetObjectField(TEXT("consist"))->GetArrayField(TEXT("vehicles")))
        {
            const auto V = Value->AsObject();
            const FString Name = Line.Trains[Train].Name + TEXT("_") + V->GetStringField(TEXT("name"));
            UStaticMesh* Mesh = Load(V->GetStringField(TEXT("mesh")));
            if (!Mesh) { ++Missing; UE_LOG(LogTemp, Warning, TEXT("TRAIN SERVICE missing mesh %s"), *V->GetStringField(TEXT("mesh"))); continue; }
            auto* Body = NewObject<UStaticMeshComponent>(this, *Name);
            Body->SetMobility(EComponentMobility::Movable);
            Body->SetupAttachment(RootComponent);
            Body->SetAbsolute(true, true, true);
            Body->SetStaticMesh(Mesh);
            Body->SetCollisionProfileName(TEXT("BlockAllDynamic"));
            // Vehicle objects: riders aboard keep blocking these while they ignore the world (Board), and the train
            // camera's probe stops only on them (UpdateCamera).
            Body->SetCollisionObjectType(ECC_Vehicle);
            Body->SetGenerateOverlapEvents(false);
            Body->SetCanEverAffectNavigation(false);
            Body->SetAffectDistanceFieldLighting(false);
            Body->bAffectDynamicIndirectLighting = false;
            Body->SetCachedMaxDrawDistance(Cull);
            Body->LDMaxDrawDistance = Cull;
            Body->PrimaryComponentTick.bCanEverTick = false;
            Body->SetNetAddressable();
            Body->RegisterComponent();
            Bodies.Add(Body);
            const auto& Bogies = V->GetArrayField(TEXT("bogies"));
            FVehicle& Vehicle = Vehicles.AddDefaulted_GetRef();
            Vehicle.Body = Body; Vehicle.Train = Train; Vehicle.Offset = V->GetNumberField(TEXT("offset")); Vehicle.Id = V->GetStringField(TEXT("id"));
            if (Bogies.Num() >= 2) { Vehicle.BogieA = Bogies[0]->AsNumber(); Vehicle.BogieB = Bogies[1]->AsNumber(); }
            for (const auto& GroupValue : V->GetArrayField(TEXT("furniture")))
            {
                const auto Group = GroupValue->AsObject();
                const FString Asset = Group->GetStringField(TEXT("asset"));
                const TSharedPtr<FJsonObject>* Spec = nullptr;
                if (!Assets->TryGetObjectField(Asset, Spec)) continue;
                UStaticMesh* FurnitureMesh = Load((*Spec)->GetStringField(TEXT("mesh")));
                if (!FurnitureMesh) { ++Missing; continue; }
                auto* Items = NewObject<UInstancedStaticMeshComponent>(this, *(Name + TEXT("_") + Asset));
                Items->SetMobility(EComponentMobility::Movable);
                Items->SetupAttachment(Body);
                Items->SetStaticMesh(FurnitureMesh);
                Items->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                Items->SetGenerateOverlapEvents(false);
                Items->SetCanEverAffectNavigation(false);
                Items->SetAffectDistanceFieldLighting(false);
                Items->bAffectDynamicIndirectLighting = false;
                Items->SetCastShadow((*Spec)->GetBoolField(TEXT("shadow")));
                const float FurnitureCull = float((*Spec)->GetNumberField(TEXT("cull_cm")));
                Items->SetCachedMaxDrawDistance(FurnitureCull);
                Items->LDMaxDrawDistance = FurnitureCull;
                Items->InstanceEndCullDistance = int32(FurnitureCull);
                Items->PrimaryComponentTick.bCanEverTick = false;
                for (const auto& Row : Group->GetArrayField(TEXT("instances")))
                {
                    const auto& A = Row->AsArray();
                    if (A.Num() < 4) continue;
                    Items->AddInstance(FTransform(FRotator(0., A[3]->AsNumber(), 0.), JsonVector(A)));
                    ++Instances;
                }
                Items->RegisterComponent();
                Furniture.Add(Items);
            }
            // Door leaves are drawn while the vehicle's LOD0 or LOD1 is (those levels have no doors of their own).
            const float LeafCull = float(Mesh->GetBounds().SphereRadius / FMath::Max(LastLod, .01));
            const TArray<TSharedPtr<FJsonValue>>* DoorRows = nullptr;
            if (V->TryGetArrayField(TEXT("doors"), DoorRows))
                for (const auto& DoorValue : *DoorRows)
                {
                    const auto D = DoorValue->AsObject();
                    FDoor& Door = Vehicle.Doors.AddDefaulted_GetRef();
                    Door.Id = D->GetStringField(TEXT("id")); Door.Kind = D->GetStringField(TEXT("kind"));
                    Door.bStation = D->GetStringField(TEXT("opens")) == TEXT("station");
                    Door.bLocked = D->GetBoolField(TEXT("locked"));
                    Door.bLeft = D->GetStringField(TEXT("side")) == TEXT("l");
                    for (const auto& H : D->GetArrayField(TEXT("handles"))) Door.Handles.Add(JsonVector(H->AsArray()));
                    const FBox Box = JsonBox(D->GetArrayField(TEXT("collision")));
                    auto* Shape = NewObject<UBoxComponent>(this, *FString::Printf(TEXT("%s_Door_%s"), *Name, *Door.Id));
                    Shape->SetMobility(EComponentMobility::Movable);
                    Shape->SetupAttachment(Body);
                    Shape->SetRelativeLocation(Box.GetCenter());
                    Shape->SetBoxExtent(Box.GetExtent(), false);
                    Shape->SetCollisionProfileName(TEXT("BlockAllDynamic"));
                    Shape->SetCollisionObjectType(ECC_Vehicle);
                    Shape->SetGenerateOverlapEvents(false);
                    Shape->SetCanEverAffectNavigation(false);
                    Shape->PrimaryComponentTick.bCanEverTick = false;
                    Shape->SetNetAddressable();
                    Shape->RegisterComponent();
                    Door.Box = Shape; Parts.Add(Shape);
                    for (const auto& LeafValue : D->GetArrayField(TEXT("leaves")))
                    {
                        const auto L = LeafValue->AsObject();
                        FLeaf& Leaf = Door.Leaves.AddDefaulted_GetRef();
                        Leaf.Pivot = JsonVector(L->GetArrayField(TEXT("pivot")));
                        Leaf.bSliding = L->GetStringField(TEXT("motion")) == TEXT("sliding");
                        if (Leaf.bSliding) Leaf.Offset = JsonVector(L->GetArrayField(TEXT("offset")));
                        else Leaf.Yaw = float(L->GetNumberField(TEXT("yaw")));
                        FString LeafMesh;
                        if (!L->TryGetStringField(TEXT("mesh"), LeafMesh) || LeafMesh.IsEmpty()) continue;
                        UStaticMesh* Asset = Load(LeafMesh);
                        if (!Asset) { ++Missing; continue; }
                        auto* Part = NewObject<UStaticMeshComponent>(this, *FString::Printf(TEXT("%s_Leaf_%s_%d"), *Name, *Door.Id, Door.Leaves.Num()));
                        Part->SetMobility(EComponentMobility::Movable);
                        Part->SetupAttachment(Body);
                        Part->SetStaticMesh(Asset);
                        Part->SetCollisionEnabled(ECollisionEnabled::NoCollision);
                        Part->SetCanEverAffectNavigation(false);
                        Part->SetAffectDistanceFieldLighting(false);
                        Part->SetCachedMaxDrawDistance(LeafCull);
                        Part->LDMaxDrawDistance = LeafCull;
                        Part->PrimaryComponentTick.bCanEverTick = false;
                        Part->RegisterComponent();
                        Leaf.Mesh = Part; Parts.Add(Part); ++Leaves;
                    }
                }
            const TArray<TSharedPtr<FJsonValue>>* SeatRows = nullptr;
            if (V->TryGetArrayField(TEXT("seats"), SeatRows))
                for (const auto& SeatValue : *SeatRows)
                {
                    const auto& A = SeatValue->AsObject()->GetArrayField(TEXT("at"));
                    if (A.Num() < 4) continue;
                    Vehicle.Seats.Add({SeatValue->AsObject()->GetStringField(TEXT("id")), JsonVector(A), float(A[3]->AsNumber())});
                }
            Vehicle.SeatTaken.Init(0, Vehicle.Seats.Num());
            const TArray<TSharedPtr<FJsonValue>>* InteriorRows = nullptr;
            if (V->TryGetArrayField(TEXT("interiors"), InteriorRows))
                for (const auto& InteriorValue : *InteriorRows)
                {
                    const auto I = InteriorValue->AsObject();
                    FInterior& Room = Vehicle.Interiors.AddDefaulted_GetRef();
                    Room.Box = JsonBox(I->GetArrayField(TEXT("box")));
                    I->TryGetBoolField(TEXT("no_sprint"), Room.bNoSprint);
                    I->TryGetBoolField(TEXT("no_climb"), Room.bNoClimb);
                    I->TryGetBoolField(TEXT("camera"), Room.bCamera);
                }
            const TArray<TSharedPtr<FJsonValue>>* ExteriorRows = nullptr;
            if (V->TryGetArrayField(TEXT("exteriors"), ExteriorRows)) Exteriors += ExteriorRows->Num();
            const TArray<TSharedPtr<FJsonValue>>* BoardingRows = nullptr;
            if (V->TryGetArrayField(TEXT("boarding"), BoardingRows))
                for (const auto& BoardingValue : *BoardingRows)
                {
                    const auto B = BoardingValue->AsObject();
                    FDoor* Door = Vehicle.Doors.FindByPredicate([&](const FDoor& D) { return D.Id == B->GetStringField(TEXT("door")); });
                    if (!Door) continue;
                    for (const auto& Point : B->GetArrayField(TEXT("path"))) Door->Boarding.Add(JsonVector(Point->AsArray()));
                    if (Door->Boarding.Num() < 2) Door->Boarding.Reset();
                }
        }
    BuildStations(Root);
    for (FStation& Station : Stations) Station.Stops = Line.Stops(Station.Chainage);
    BuildBoards(Root);
    TrainAtStation.Init(false, Line.Trains.Num());
    float Scale = 1.f;
    if (FParse::Value(FCommandLine::Get(), TEXT("traintimescale="), Scale)) CVarTrainTimeScale->Set(Scale);
    FString Where;
    if (FParse::Value(FCommandLine::Get(), TEXT("trainview="), Where) || FParse::Param(FCommandLine::Get(), TEXT("trainview")))
    { PendingView = Where.IsEmpty() ? FString(TEXT("view")) : Where; PendingViewDelay = 4.f; }
    Where.Reset();
    if (FParse::Value(FCommandLine::Get(), TEXT("traingo="), Where) || FParse::Param(FCommandLine::Get(), TEXT("traingo")))
    { PendingView = TEXT("go:") + (Where.IsEmpty() ? FString(TEXT("belmonte")) : Where); PendingViewDelay = 4.f; }
    PlaceVehicles(ServiceTime(), true);
    UpdateDoors(ServiceTime(), 1.f);
    UpdateBoards(ServiceTime());
    if (GetNetMode() == NM_Client) OnRep_NetworkState();
    else if (JapanNetwork::IsOnline(GetWorld())) PublishNetworkState();
    int32 Ways = 0;
    for (const FVehicle& V : Vehicles) for (const FDoor& D : V.Doors) Ways += D.Boarding.Num() > 0;
    UE_LOG(LogTemp, Display, TEXT("TRAIN SERVICE ready vehicles=%d trains=%d furniture=%d instances=%d leaves=%d stations=%d boarding=%d exteriors=%d missing=%d cycle=%.1f loop=%.0f-%.0f tunnels=%d enclosed=%d"),
        Vehicles.Num(), Line.Trains.Num(), Furniture.Num(), Instances, Leaves, Stations.Num(), Ways, Exteriors, Missing, Line.Cycle, Line.LoopStart, Line.LoopEnd,
        Tunnels, Line.Enclosed.Num());
    TrainSafe.Init(FVector::ZeroVector, Line.Trains.Num());
    bTrainSafe.Init(false, Line.Trains.Num());
    bInitialized = Vehicles.Num() > 0;
    bInitFailed = !bInitialized;
    return bInitialized;
}

void ABelmonteTrainService::EndPlay(const EEndPlayReason::Type Reason)
{
    for (FRider& Rider : Riders)
        if (Rider.Character.IsValid())
        {
            if (Rider.BoardDoor != INDEX_NONE) FinishBoarding(Rider);
            if (Rider.Seat != INDEX_NONE) StandUp(Rider);
            if (Rider.bAboard) Board(Rider, false);
            UpdateCamera(Rider, false, 1.f);
        }
    Super::EndPlay(Reason);
}

void ABelmonteTrainService::PlaceVehicles(double Time, bool bForce)
{
    TArray<double, TInlineAllocator<4>> Centre; TArray<bool, TInlineAllocator<4>> OnLoop;
    for (int32 Train = 0; Train < Line.Trains.Num(); ++Train)
    { Centre.Add(Line.Chainage(Train, Time)); OnLoop.Add(Line.OnLoopTrack(Train, Time)); }
    for (FVehicle& V : Vehicles)
    {
        const double At = Centre[V.Train] + V.Offset;
        V.Previous = V.Body->GetComponentTransform();
        V.bMoved = false;
        // A standing train is not moved again: no transform or physics update while it waits.
        if (!bForce && FMath::Abs(At - V.Placed) < 1e-4 && V.bPlacedOnLoop == OnLoop[V.Train]) continue;
        const FTransform T = Line.Place(At, V.BogieA, V.BogieB, OnLoop[V.Train]);
        V.Body->SetWorldLocationAndRotation(T.GetLocation(), T.GetRotation(), false, nullptr, ETeleportType::None);
        V.bMoved = !bForce;
        if (bForce) V.Previous = V.Body->GetComponentTransform();
        V.Placed = At; V.bPlacedOnLoop = OnLoop[V.Train];
    }
}

bool ABelmonteTrainService::AtStation(int32 Train, double Time) const
{
    // Standing now and still standing 8 s on: the doors close and lock just before departure.
    const double S = Line.Chainage(Train, Time);
    if (FMath::Abs(Line.Chainage(Train, Time + 8.) - S) > .01 || FMath::Abs(Line.Chainage(Train, Time - .5) - S) > .01) return false;
    for (const FStation& Station : Stations) if (FMath::Abs(Station.Chainage - S) < 5.) return true;
    return false;
}

void ABelmonteTrainService::UpdateDoors(double Time, float Dt)
{
    for (int32 Train = 0; Train < Line.Trains.Num(); ++Train) TrainAtStation[Train] = AtStation(Train, Time);
    for (FVehicle& V : Vehicles)
    {
        const double S = Line.Chainage(V.Train, Time);
        const FStation* Station = Stations.FindByPredicate([S](const FStation& Stop) { return FMath::Abs(Stop.Chainage - S) < 5.; });
        for (FDoor& Door : V.Doors)
        {
            Door.bPlatformSide = Station && Door.bLeft == Station->bLeft;
            // A door a rider is stepping through stays open until they are through (the move takes about two seconds;
            // AtStation already ends eight seconds before departure).
            if (Door.bStation && !Door.bBusy && (!TrainAtStation[V.Train] || !Door.bPlatformSide)) Door.bOpen = false;
            if (Door.bLocked) Door.bOpen = false;
            const float Target = Door.bOpen ? 1.f : 0.f;
            const bool bMoving = Door.Open != Target;
            Door.Open = FMath::FInterpConstantTo(Door.Open, Target, Dt, 1.4f);
            // The doorway's box follows the door: off as soon as it opens, back on as soon as it closes.
            const ECollisionEnabled::Type Wanted = Door.bOpen ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics;
            if (Door.Box && Door.Box->GetCollisionEnabled() != Wanted) Door.Box->SetCollisionEnabled(Wanted);
            if (!bMoving) continue;
            const float Ease = Door.Open * Door.Open * (3.f - 2.f * Door.Open);
            for (FLeaf& Leaf : Door.Leaves)
            {
                if (!Leaf.Mesh) continue;
                if (Leaf.bSliding) Leaf.Mesh->SetRelativeLocation(Leaf.Offset * Ease);
                else
                {
                    const FQuat R = FRotator(0., Leaf.Yaw * Ease, 0.).Quaternion();
                    Leaf.Mesh->SetRelativeLocationAndRotation(Leaf.Pivot - R.RotateVector(Leaf.Pivot), R);
                }
            }
        }
    }
}

ABelmonteTrainService::FRider& ABelmonteTrainService::RiderFor(AWandererCharacter* Character)
{
    for (FRider& R : Riders) if (R.Character.Get() == Character) return R;
    FRider& R = Riders.AddDefaulted_GetRef(); R.Character = Character; return R;
}

const ABelmonteTrainService::FRider* ABelmonteTrainService::FindRider(const AWandererCharacter* Character) const
{
    for (const FRider& R : Riders) if (R.Character.Get() == Character) return &R;
    return nullptr;
}

void ABelmonteTrainService::Board(FRider& Rider, bool bAboard)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!FTransportRiders::SetAboard(Rider, bAboard, true, ETransportVehicle::Train)) return;
    UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s %s vehicle=%s"), *C->GetName(), bAboard ? TEXT("boarded") : TEXT("left"),
        Vehicles.IsValidIndex(Rider.Vehicle) ? *Vehicles[Rider.Vehicle].Id : TEXT("-"));
}

void ABelmonteTrainService::SitDown(FRider& Rider, int32 VehicleIndex, int32 SeatIndex)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || !Vehicles.IsValidIndex(VehicleIndex) || !Vehicles[VehicleIndex].Seats.IsValidIndex(SeatIndex)) return;
    FVehicle& V = Vehicles[VehicleIndex];
    V.SeatTaken[SeatIndex] = 1;
    Rider.Vehicle = VehicleIndex; Rider.Seat = SeatIndex; Rider.Seated = 0.f;
    C->bTrainDriving = true;
    if (!Rider.bAboard) Board(Rider, true);
    auto* M = C->GetCharacterMovement();
    C->MoveIntent = FVector2D::ZeroVector; C->bJog = C->bWalk = C->bSprintHeld = false;
    M->StopMovementImmediately(); M->ClearAccumulatedForces(); M->SetMovementMode(MOVE_None);
    C->SetActorEnableCollision(false);
    C->SetAction(TEXT("SitDown"), false, .12f, true);
    UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s sat vehicle=%s seat=%s"), *C->GetName(), *V.Id, *V.Seats[SeatIndex].Id);
}

void ABelmonteTrainService::StandUp(FRider& Rider)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || !Vehicles.IsValidIndex(Rider.Vehicle) || Rider.Seat == INDEX_NONE) return;
    FVehicle& V = Vehicles[Rider.Vehicle];
    const FSeat& Seat = V.Seats[Rider.Seat];
    V.SeatTaken[Rider.Seat] = 0;
    Rider.Seat = INDEX_NONE;
    C->bTrainDriving = Rider.BoardDoor != INDEX_NONE;
    // Step forward off the seat onto the floor (1.25 m above the rail) in the coach's current frame on this machine.
    const FVector Forward = FRotator(0., Seat.Yaw, 0.).Vector();
    const FVector Local(Seat.Location.X + Forward.X * 55., Seat.Location.Y + Forward.Y * 55., 125.);
    const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    C->SetActorLocation(V.Body->GetComponentTransform().TransformPosition(Local) + FVector(0, 0, Half + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
    C->SetActorEnableCollision(true);
    auto* M = C->GetCharacterMovement();
    M->SetMovementMode(MOVE_Walking); M->bForceNextFloorCheck = true;
    C->SetBase(V.Body);
    if (JapanNetwork::IsOnline(GetWorld()))
        if (auto* JM = Cast<UJapanCharacterMovement>(M)) JM->ResetActivityPrediction();
    C->SetAction(NAME_None, false, .2f);
    UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s stood vehicle=%s seat=%s"), *C->GetName(), *V.Id, *Seat.Id);
    if (HasAuthority()) PublishNetworkState();
}

void ABelmonteTrainService::UpdateCamera(FRider& Rider, bool bInside, float Dt)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || !C->CameraArm || !C->IsLocallyControlled()) return;
    if (Rider.Camera <= 0.f && !bInside) return;
    USpringArmComponent* Arm = C->CameraArm;
    if (Rider.LastAppliedArm > 0.f && FMath::Abs(Arm->TargetArmLength - Rider.LastAppliedArm) > 1.f)
        Rider.SavedArm = Arm->TargetArmLength;
    if (Rider.Camera <= 0.f) Rider.SavedArm = Arm->TargetArmLength;
    // About 0.4 s in or out. Inside, a short arm (1.1 m) without lag that stops only on the train's own collision (its
    // walls, partitions and closed doors), so nothing the line still runs through can pull it into the rider's head.
    Rider.Camera = FMath::FInterpConstantTo(Rider.Camera, bInside ? 1.f : 0.f, Dt, 2.5f);
    const float Ease = Rider.Camera * Rider.Camera * (3.f - 2.f * Rider.Camera);
    Arm->TargetArmLength = FMath::Lerp(Rider.SavedArm, 110.f, Ease);
    Rider.LastAppliedArm = Arm->TargetArmLength;
    Arm->bDoCollisionTest = true;
    if (auto* Japan = Cast<UJapanCameraArm>(Arm)) Japan->ProbeObjectsOnly = Rider.Camera > 0.f ? ECC_Vehicle : ECC_MAX;
    if (Rider.Camera <= 0.f) { Arm->TargetArmLength = Rider.SavedArm; Rider.SavedArm = -1.f; Rider.LastAppliedArm = -1.f; }
}

bool ABelmonteTrainService::StartBoarding(FRider& Rider, int32 VehicleIndex, int32 DoorIndex)
{
    AWandererCharacter* C = Rider.Character.Get();
    FVehicle& V = Vehicles[VehicleIndex];
    FDoor& Door = V.Doors[DoorIndex];
    if (!C || Door.Boarding.Num() < 2 || Rider.BoardDoor != INDEX_NONE) return false;
    const FTransform& T = V.Body->GetComponentTransform();
    const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector Feet = T.InverseTransformPosition(C->GetActorLocation() - FVector(0, 0, Half));
    // The ground outside under the path's outer end: the record's outside point sits at rail level plus the steps, but
    // the platform reserve, banks and earthworks put the real ground elsewhere. Boarding starts from the rider's own feet
    // when they stand there; alighting ends on the traced world ground (WorldStatic, never the train). Steps at or below
    // that ground are not climbed.
    TArray<FVector> Way = Door.Boarding;
    Rider.bBoardUp = !Rider.bAboard;
    {
        const FVector Out = T.TransformPosition(Way[0]);
        double Z = 0.;
        if (Rider.bBoardUp && FVector::Dist2D(Way[0], Feet) < 120.)
            Way[0].Z = Feet.Z;
        // Alighting, the ground is searched from the coach floor down (the platform stands just below it, the ballast
        // about 2 m below), keeping the highest ground near the floor rather than the record's rail-level point.
        else if (Rider.bBoardUp ? GroundNear(Out, T.TransformPosition(Feet).Z, 150., C, Z)
                                : GroundNear(Out, T.TransformPosition(Way.Last()).Z, 250., C, Z))
            Way[0].Z = T.InverseTransformPosition(FVector(Out.X, Out.Y, Z)).Z;
        else if (Rider.bBoardUp)
            Way[0].Z = Feet.Z;   // no ground found: from the feet, never from below them
        const double Ground = Way[0].Z;
        for (int32 I = Way.Num() - 2; I >= 1; --I) if (Way[I].Z <= Ground + 3.) Way.RemoveAt(I);
    }
    if (!Rider.bBoardUp) Algo::Reverse(Way);
    // From where the rider stands to the path's start (unless already on it), then along it.
    Rider.BoardPath.Reset();
    Rider.BoardPath.Add(Feet);
    for (int32 I = 0; I < Way.Num(); ++I)
        if (I > 0 || FVector::Dist2D(Way[0], Feet) > 25.) Rider.BoardPath.Add(Way[I]);
    Rider.BoardLength = 0.f;
    for (int32 I = 1; I < Rider.BoardPath.Num(); ++I) Rider.BoardLength += float(FVector::Dist(Rider.BoardPath[I - 1], Rider.BoardPath[I]));
    Rider.BoardVehicle = VehicleIndex; Rider.BoardDoor = DoorIndex;
    C->bTrainDriving = true;
    Rider.BoardTime = -.55f;   // the door swings open first
    Rider.bBoardMoving = false;
    Door.bOpen = true; Door.bBusy = true;
    auto* M = C->GetCharacterMovement();
    C->MoveIntent = FVector2D::ZeroVector; C->bJog = C->bWalk = C->bSprintHeld = false;
    M->StopMovementImmediately(); M->ClearAccumulatedForces(); M->SetMovementMode(MOVE_None);
    C->SetActorEnableCollision(false);
    C->SetAction(NAME_None, false, .15f);
    UE_LOG(LogTemp, Display, TEXT("TRAIN BOARD %s %s vehicle=%s door=%s steps=%d length=%.0f"), *C->GetName(),
        Rider.bBoardUp ? TEXT("up") : TEXT("down"), *V.Id, *Door.Id, Rider.BoardPath.Num(), Rider.BoardLength);
    return true;
}

void ABelmonteTrainService::UpdateBoarding(FRider& Rider, float Dt)
{
    AWandererCharacter* C = Rider.Character.Get();
    const FVehicle& V = Vehicles[Rider.BoardVehicle];
    const FTransform& T = V.Body->GetComponentTransform();
    const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const TArray<FVector>& P = Rider.BoardPath;
    constexpr float Speed = 135.f;   // a careful walk up two steps
    Rider.BoardTime += Dt;
    float Along = FMath::Max(0.f, Rider.BoardTime) * Speed;
    if (Rider.BoardTime >= 0.f && Along >= Rider.BoardLength)
    {
        if (!JapanNetwork::IsOnline(GetWorld()) || HasAuthority()) { FinishBoarding(Rider); return; }
        Along = Rider.BoardLength;
    }
    int32 I = 1;
    while (I < P.Num() - 1 && Along > FVector::Dist(P[I - 1], P[I])) { Along -= float(FVector::Dist(P[I - 1], P[I])); ++I; }
    const FVector A = P[I - 1], B = P.IsValidIndex(I) ? P[I] : P.Last();
    const double Segment = FMath::Max(1., FVector::Dist(A, B));
    const FVector Local = A + (B - A) * FMath::Clamp(Along / Segment, 0., 1.);
    // Facing the way through the door (the path's ends), not each little segment.
    const FVector Heading = T.TransformVector(P.Last() - P[0]).GetSafeNormal2D();
    FVector Foot = T.TransformPosition(Local);
    // Stepping down onto the ground, the last segment blends to the ground under the feet: never below it.
    double Ground = 0.;
    if (!Rider.bBoardUp && I == P.Num() - 1 && GroundNear(Foot, Foot.Z, 150., C, Ground) && Ground > Foot.Z) Foot.Z = Ground;
    C->SetActorLocationAndRotation(Foot + FVector(0, 0, Half + 1.f), Heading.Rotation(), false, nullptr, ETeleportType::TeleportPhysics);
    // The walk cycle reads the movement's velocity: it walks up the steps.
    C->GetCharacterMovement()->Velocity = Rider.BoardTime >= 0.f ? T.TransformVector((B - A) / Segment) * Speed : FVector::ZeroVector;
}

void ABelmonteTrainService::FinishBoarding(FRider& Rider)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (!Vehicles.IsValidIndex(Rider.BoardVehicle)) { Rider.BoardDoor = INDEX_NONE; return; }
    FVehicle& V = Vehicles[Rider.BoardVehicle];
    FDoor& Door = V.Doors[Rider.BoardDoor];
    if (C)
    {
        const FTransform& T = V.Body->GetComponentTransform();
        const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        const FVector Heading = T.TransformVector(Rider.BoardPath.Last() - Rider.BoardPath[0]).GetSafeNormal2D();
        FVector Foot = T.TransformPosition(Rider.BoardPath.Last());
        double Ground = 0.;
        if (!Rider.bBoardUp && GroundNear(Foot, Foot.Z, 250., C, Ground)) Foot.Z = Ground;
        C->SetActorLocationAndRotation(Foot + FVector(0, 0, Half + 2.f), Heading.Rotation(), false, nullptr, ETeleportType::TeleportPhysics);
        // The boarding walk is the one way aboard (BelmonteTrainRules): on authority it admits the rider; stepping down ends that.
        if (GetNetMode() != NM_Client) { if (Rider.bBoardUp) Rider.Admission.Admit(); else Rider.Admission.Revoke(); }
        if (Rider.bBoardUp) { Rider.Vehicle = Rider.BoardVehicle; Board(Rider, true); }
        else Board(Rider, false);
        if (!Rider.bBoardUp)
        {
            // Off the train, the capsule must not start inside the platform or the bank: nudge it up until it is free.
            const UCapsuleComponent* Capsule = C->GetCapsuleComponent();
            // The ground (terrain, banks, the platform: WorldStatic) only, not the coach the rider just left.
            FCollisionQueryParams Params(SCENE_QUERY_STAT(TrainAlight), false, C);
            const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
            const FCollisionShape Shape = FCollisionShape::MakeCapsule(Capsule->GetScaledCapsuleRadius() - 1.f, Half - 1.f);
            FVector At = C->GetActorLocation();
            int32 Nudges = 0;
            while (Nudges < 30 && GetWorld()->OverlapAnyTestByObjectType(At, FQuat::Identity, Objects, Shape, Params)) { At.Z += 5.; ++Nudges; }
            if (Nudges) C->SetActorLocation(At, false, nullptr, ETeleportType::TeleportPhysics);
            UE_LOG(LogTemp, Display, TEXT("TRAIN ALIGHT %s ground=%.0f record=%.0f nudged=%d"), *C->GetName(), Foot.Z,
                T.TransformPosition(Rider.BoardPath.Last()).Z, Nudges * 5);
        }
        C->SetActorEnableCollision(true);
        auto* M = C->GetCharacterMovement();
        M->Velocity = FVector::ZeroVector;
        M->SetMovementMode(MOVE_Walking); M->bForceNextFloorCheck = true;
        UE_LOG(LogTemp, Display, TEXT("TRAIN BOARD %s %s vehicle=%s door=%s"), *C->GetName(), Rider.bBoardUp ? TEXT("aboard") : TEXT("off"), *V.Id, *Door.Id);
    }
    Door.bOpen = false; Door.bBusy = false;
    Rider.BoardDoor = Rider.BoardVehicle = INDEX_NONE;
    Rider.BoardPath.Reset();
    if (C)
    {
        C->bTrainDriving = Rider.Seat != INDEX_NONE;
        C->SetBase(Rider.bAboard && Vehicles.IsValidIndex(Rider.Vehicle) ? Vehicles[Rider.Vehicle].Body.Get() : nullptr);
        if (JapanNetwork::IsOnline(GetWorld()))
            if (auto* JM = Cast<UJapanCharacterMovement>(C->GetCharacterMovement())) JM->ResetActivityPrediction();
    }
    if (HasAuthority()) PublishNetworkState();
}

bool ABelmonteTrainService::GroundNear(const FVector& Point, double Near, double MaxOff, const AActor* Ignore, double& Z) const
{
    // The service's own makeshift platforms are WorldStatic and count as ground; its vehicles are ECC_Vehicle and do not.
    FCollisionQueryParams Params(SCENE_QUERY_STAT(TrainGround), true);
    if (Ignore) Params.AddIgnoredActor(Ignore);
    const FCollisionObjectQueryParams Objects(ECC_WorldStatic);
    auto Probe = [&](const FVector& At, double& Best) -> bool
    {
        TArray<FHitResult> Hits;
        GetWorld()->LineTraceMultiByObjectType(Hits, FVector(At.X, At.Y, Near + 400.), FVector(At.X, At.Y, Near - 400.), Objects, Params);
        bool bFound = false;
        for (const FHitResult& Hit : Hits)
            if (Hit.bBlockingHit || Hit.GetComponent())
                if (FMath::Abs(Hit.ImpactPoint.Z - Near) <= MaxOff && (!bFound || FMath::Abs(Hit.ImpactPoint.Z - Near) < FMath::Abs(Best - Near)))
                { Best = Hit.ImpactPoint.Z; bFound = true; }
        return bFound;
    };
    if (Probe(Point, Z)) return true;
    // The nearest safe ground in two rings around the point.
    for (const double Radius : {40., 80.})
    {
        double BestZ = 0.; bool bAny = false;
        for (int32 K = 0; K < 8; ++K)
        {
            const double A = K * PI / 4.;
            double Candidate = 0.;
            if (Probe(Point + FVector(FMath::Cos(A), FMath::Sin(A), 0.) * Radius, Candidate) &&
                (!bAny || FMath::Abs(Candidate - Near) < FMath::Abs(BestZ - Near))) { BestZ = Candidate; bAny = true; }
        }
        if (bAny) { Z = BestZ; return true; }
    }
    return false;
}

void ABelmonteTrainService::PublishNetworkState()
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    ++NetworkState.Serial;
    NetworkState.DevOffset = DevOffset;
    NetworkState.TimeScale = FMath::Clamp(CVarTrainTimeScale.GetValueOnGameThread(), 0.f, 100.f);
    NetworkState.OpenDoors.Reset();
    for (const FVehicle& V : Vehicles)
        for (const FDoor& D : V.Doors)
            NetworkState.OpenDoors.Add(D.bOpen ? 1 : 0);
    NetworkState.Passengers.Reset();
    for (const FRider& R : Riders)
        if (AWandererCharacter* C = R.Character.Get())
            if (R.bAboard || R.Seat != INDEX_NONE || R.BoardDoor != INDEX_NONE || R.Admission.bAdmitted)
            {
                FBelmonteTrainPassenger& P = NetworkState.Passengers.AddDefaulted_GetRef();
                P.Rider = C;
                P.Vehicle = int16(R.Vehicle);
                P.Seat = int16(R.Seat);
                P.BoardVehicle = int16(R.BoardVehicle);
                P.BoardDoor = int16(R.BoardDoor);
                P.bBoardUp = R.bBoardUp;
                P.bAboard = R.bAboard;
                P.bAdmitted = R.Admission.bAdmitted;
                P.BoardTime = R.BoardTime;
                P.BoardLength = R.BoardLength;
                P.BoardPath = R.BoardPath;
            }
    LastNetworkPublication = GetWorld()->GetTimeSeconds();
    ForceNetUpdate();
}

void ABelmonteTrainService::OnRep_NetworkState()
{
    if (Vehicles.IsEmpty() || !NetworkState.Serial) return;
    DevOffset = NetworkState.DevOffset;
    int32 DoorCursor = 0;
    for (FVehicle& V : Vehicles)
        for (FDoor& D : V.Doors)
            if (NetworkState.OpenDoors.IsValidIndex(DoorCursor))
                D.bOpen = NetworkState.OpenDoors[DoorCursor++] != 0;
    for (const FBelmonteTrainPassenger& P : NetworkState.Passengers)
    {
        AWandererCharacter* C = P.Rider.Get();
        if (!C) continue;
        FRider& R = RiderFor(C);
        if (P.BoardDoor != INDEX_NONE && R.BoardDoor != P.BoardDoor &&
            Vehicles.IsValidIndex(P.BoardVehicle) && Vehicles[P.BoardVehicle].Doors.IsValidIndex(P.BoardDoor) && P.BoardPath.Num() >= 2)
        {
            R.BoardVehicle = P.BoardVehicle; R.BoardDoor = P.BoardDoor;
            R.bBoardUp = P.bBoardUp; R.BoardTime = P.BoardTime; R.BoardLength = P.BoardLength; R.BoardPath = P.BoardPath;
            FDoor& Door = Vehicles[R.BoardVehicle].Doors[R.BoardDoor];
            Door.bOpen = true; Door.bBusy = true;
            C->bTrainDriving = true;
            auto* M = C->GetCharacterMovement();
            C->MoveIntent = FVector2D::ZeroVector; C->bJog = C->bWalk = C->bSprintHeld = false;
            M->StopMovementImmediately(); M->ClearAccumulatedForces(); M->SetMovementMode(MOVE_None);
            C->SetActorEnableCollision(false);
            C->SetAction(NAME_None, false, .15f);
        }
        else if (P.BoardDoor == INDEX_NONE && R.BoardDoor != INDEX_NONE)
            FinishBoarding(R);
        if (P.Seat != INDEX_NONE && R.Seat != P.Seat)
            SitDown(R, P.Vehicle, P.Seat);
        else if (P.Seat == INDEX_NONE && R.Seat != INDEX_NONE)
            StandUp(R);
        if (P.bAboard != R.bAboard)
        {
            R.Vehicle = P.Vehicle;
            Board(R, P.bAboard);
        }
        // The host decides who holds the ticket (BelmonteTrainRules::FAdmission); a client never grants or ends it.
        if (P.bAdmitted != R.Admission.bAdmitted) { if (P.bAdmitted) R.Admission.Admit(); else R.Admission.Revoke(); }
    }
    for (FRider& R : Riders)
        if (AWandererCharacter* C = R.Character.Get())
            if (!NetworkState.Passengers.ContainsByPredicate([C](const FBelmonteTrainPassenger& P) { return P.Rider == C; }))
                CancelLocal(R);
}

bool ABelmonteTrainService::CanInteract(const AWandererCharacter* C)
{
    const ABelmonteTrainService* Service = Find(C);
    if (!Service || !C) return false;
    if ((C->GetSkate() && C->GetSkate()->IsRiding()) || C->OnVehicle() || C->IsZeppelinPassenger()) return false;
    const FRider* Rider = Service->FindRider(C);
    if (Rider && (Rider->BoardDoor != INDEX_NONE || Rider->Seat != INDEX_NONE)) return true;
    int32 VehicleIndex, Index; bool bSeat;
    return Service->Nearest(C, VehicleIndex, Index, bSeat);
}

bool ABelmonteTrainService::IsDrivingRider(const AWandererCharacter* C)
{
    return C && C->bTrainDriving;
}

bool ABelmonteTrainService::IsBoardingRider(const AWandererCharacter* C)
{
    const auto* Service = C ? Find(C) : nullptr;
    const FRider* Rider = Service ? Service->FindRider(C) : nullptr;
    return Rider && Rider->BoardDoor != INDEX_NONE;
}

void ABelmonteTrainService::CancelLocal(FRider& Rider)
{
    AWandererCharacter* C = Rider.Character.Get();
    if (Rider.BoardDoor != INDEX_NONE)
    {
        if (Vehicles.IsValidIndex(Rider.BoardVehicle) && Vehicles[Rider.BoardVehicle].Doors.IsValidIndex(Rider.BoardDoor))
        {
            Vehicles[Rider.BoardVehicle].Doors[Rider.BoardDoor].bOpen = false;
            Vehicles[Rider.BoardVehicle].Doors[Rider.BoardDoor].bBusy = false;
        }
        Rider.BoardDoor = Rider.BoardVehicle = INDEX_NONE;
        Rider.BoardPath.Reset();
        if (C) C->SetActorEnableCollision(true);
    }
    if (Rider.Seat != INDEX_NONE)
    {
        if (Vehicles.IsValidIndex(Rider.Vehicle) && Vehicles[Rider.Vehicle].SeatTaken.IsValidIndex(Rider.Seat))
            Vehicles[Rider.Vehicle].SeatTaken[Rider.Seat] = 0;
        Rider.Seat = INDEX_NONE;
        if (C) C->SetActorEnableCollision(true);
    }
    if (Rider.bAboard) Board(Rider, false);
    Rider.Vehicle = INDEX_NONE;
    // A cancel (a teleport, a respawn, the map's travel, an ejection) ends the ticket.
    Rider.Admission.Revoke();
    Rider.TrackedVehicle = INDEX_NONE;
    if (C) C->bTrainDriving = false;
    UpdateCamera(Rider, false, 1.f);
}

void ABelmonteTrainService::Cancel(AWandererCharacter* C)
{
    if (!C) return;
    FRider* Rider = const_cast<FRider*>(FindRider(C));
    if (!Rider) return;
    CancelLocal(*Rider);
    if (HasAuthority()) PublishNetworkState();
}

bool ABelmonteTrainService::ReplacePassenger(AWandererCharacter* From, AWandererCharacter* To)
{
    if (!From || !To) return false;
    // The rider's entry, ticket included, moves to the new pawn; an entry the new pawn got the frame it spawned goes.
    const int32 Index = BelmonteTrainRules::MoveRider(Riders, From, To, [this](FRider& Stale) { ReleaseRider(Stale); });
    if (Index == INDEX_NONE) return false;
    FRider& R = Riders[Index];
    From->bTrainAboard = From->bTrainDriving = From->bNoSprint = false;
    From->AboardVehicle = ETransportVehicle::None;
    R.bTickOrdered = false;
    R.TrackedVehicle = INDEX_NONE;
    if (R.bAboard)
    {
        R.bAboard = false;
        Board(R, true);
    }
    if (R.Seat != INDEX_NONE || R.BoardDoor != INDEX_NONE)
    {
        To->bTrainDriving = true;
        To->GetCharacterMovement()->SetMovementMode(MOVE_None);
        To->SetActorEnableCollision(false);
        if (R.Seat != INDEX_NONE) To->SetAction(TEXT("SitIdle"), true, .1f, true);
    }
    UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s replaced by %s admitted=%d aboard=%d"), *From->GetName(), *To->GetName(),
        R.Admission.bAdmitted, R.bAboard);
    if (HasAuthority()) PublishNetworkState();
    return true;
}

void ABelmonteTrainService::ReleaseRider(FRider& Rider)
{
    if (Rider.Seat != INDEX_NONE && Vehicles.IsValidIndex(Rider.Vehicle) && Vehicles[Rider.Vehicle].SeatTaken.IsValidIndex(Rider.Seat))
        Vehicles[Rider.Vehicle].SeatTaken[Rider.Seat] = 0;
    if (Rider.BoardDoor != INDEX_NONE && Vehicles.IsValidIndex(Rider.BoardVehicle) && Vehicles[Rider.BoardVehicle].Doors.IsValidIndex(Rider.BoardDoor))
    {
        // A door held open for a walk nobody finishes closes again (UpdateDoors).
        FDoor& Door = Vehicles[Rider.BoardVehicle].Doors[Rider.BoardDoor];
        Door.bBusy = false; Door.bOpen = false;
    }
    Rider.Seat = Rider.BoardDoor = Rider.BoardVehicle = INDEX_NONE;
    Rider.Admission.Revoke();
}

bool ABelmonteTrainService::AnyRiderAboard() const
{
    for (const FRider& R : Riders)
        if (R.Character.IsValid() && (R.bAboard || R.Seat != INDEX_NONE || R.BoardDoor != INDEX_NONE))
            return true;
    return false;
}

void ABelmonteTrainService::UpdateRiders(float Dt)
{
    const bool bOnline = JapanNetwork::IsOnline(GetWorld());
    // Host or offline: the owner of every rider's ticket. A client follows the replicated passenger list.
    const bool bOwner = GetNetMode() != NM_Client;
    const double Time = ServiceTime();
    // A disconnected player's entry goes, ticket and all; the seat and the door they held are freed for everyone.
    bool bPublish = BelmonteTrainRules::DropVanished(Riders, [this](FRider& Gone) { ReleaseRider(Gone); }) > 0;
    for (TActorIterator<AWandererCharacter> It(GetWorld()); It; ++It)
    {
        AWandererCharacter* C = *It;
        if (C->IsNpc()) continue;
        // A pawn replicated after the passenger list that names it (a replacement pawn, a late join): apply it now.
        if (!bOwner && !FindRider(C) && NetworkState.Passengers.ContainsByPredicate([C](const FBelmonteTrainPassenger& P) { return P.Rider == C; }))
        { RiderFor(C); OnRep_NetworkState(); }
        FRider& Rider = RiderFor(C);
        FTransportRiders::OrderTick(*this, Rider);
        if (Rider.BoardDoor != INDEX_NONE) { UpdateBoarding(Rider, Dt); UpdateCamera(Rider, Rider.bAboard, Dt); continue; }
        const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        if (Rider.Seat != INDEX_NONE && Rider.Seated > 0.f && (C->IsLocallyControlled() || HasAuthority()) && FVector::Dist(C->GetActorLocation(), Rider.SeatedAt) > 300.)
        {
            // Teleported or respawned while seated: free the seat and give the character back its collision and walk.
            Vehicles[Rider.Vehicle].SeatTaken[Rider.Seat] = 0;
            Rider.Seat = INDEX_NONE;
            if (bOwner) Rider.Admission.Revoke();
            C->bTrainDriving = false;
            C->SetActorEnableCollision(true);
            C->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
            C->SetAction(NAME_None, false, .2f);
            if (HasAuthority()) PublishNetworkState();
            UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s left the seat by teleport"), *C->GetName());
        }
        if (Rider.Seat != INDEX_NONE && Vehicles.IsValidIndex(Rider.Vehicle) && Vehicles[Rider.Vehicle].Seats.IsValidIndex(Rider.Seat))
        {
            const FVehicle& V = Vehicles[Rider.Vehicle];
            const FSeat& Seat = V.Seats[Rider.Seat];
            const FTransform& T = V.Body->GetComponentTransform();
            // The seat marker is on the cushion; the sitting pose's root sits a little below it.
            C->SetActorLocationAndRotation(T.TransformPosition(Seat.Location) + FVector(0, 0, Half - 12.f),
                FRotator(0., T.Rotator().Yaw + Seat.Yaw, 0.), false, nullptr, ETeleportType::TeleportPhysics);
            Rider.SeatedAt = C->GetActorLocation();
            C->GetCharacterMovement()->Velocity = FVector::ZeroVector;
            Rider.Seated += Dt;
            if (Rider.Seated > 1.1f) C->SetAction(TEXT("SitIdle"), true, .2f);
            UpdateCamera(Rider, true, Dt);
            continue;
        }
        if (!C->IsPlayerControlled() || !(C->IsLocallyControlled() || C->HasAuthority())) continue;
        // The rider still stands where last frame left them, relative to where the vehicles stood last frame: find the
        // room in that frame. Hysteresis along the vehicle only (gangways); across it the platform is close outside.
        // Only a rider holding the ticket (the boarding walk) is carried; anyone else riding inside a coach is put back
        // outside by the host. The capsule is the authority here: a remote skater's host capsule follows the trusted
        // root its owner sends, never the rendered skater (whose pose may lag or bail away from it).
        const FVector Feet = C->GetActorLocation() - FVector(0, 0, Half - 5.);
        const int32 BaseVehicle = VehicleOf(C->GetMovementBase());
        int32 Inside = INDEX_NONE; bool bNoSprint = false, bCamera = false;
        if (Rider.Admission.bAdmitted)
        {
            Rider.TrackedVehicle = INDEX_NONE;
            Inside = InteriorAt(Feet, FVector(40., 5., 30.), bNoSprint, bCamera);
            // A gangway or a vestibule floor outside the rooms is still the train.
            if (Inside == INDEX_NONE && BaseVehicle != INDEX_NONE) { Inside = BaseVehicle; bNoSprint = true; bCamera = Rider.Camera > 0.f; }
            const bool bOnTrain = Inside != INDEX_NONE;
            if (Rider.Admission.Update(bOnTrain, false, Dt, bOwner))
            {
                bPublish = true;
                UE_LOG(LogTemp, Display, TEXT("TRAIN RIDER %s ticket ended: off the train %.1f s"), *C->GetName(), BelmonteTrainRules::FAdmission::Grace);
            }
            // Within the grace (a jump, a stumble across a gangway) the coach they were last in still carries them.
            else if (!bOnTrain && Rider.Admission.Carries() && Vehicles.IsValidIndex(Rider.Vehicle))
            { Inside = Rider.Vehicle; bNoSprint = C->bNoSprint; bCamera = Rider.Camera > 0.f; }
        }
        else if (bOwner && C->HasAuthority())
        {
            Rider.EjectCooldown = FMath::Max(0.f, Rider.EjectCooldown - Dt);
            bool bRoomSprint = false, bRoomCamera = false;
            const int32 Intruded = InteriorAt(Feet, FVector(-5., -5., 0.), bRoomSprint, bRoomCamera);
            if (Intruded == INDEX_NONE) { Rider.TrackedVehicle = INDEX_NONE; Rider.TrackedSpeed = -1.; }
            else
            {
                // The rider's speed in the coach's frame: about their own for someone riding it, the coach's for a
                // bystander it sweeps through.
                const FVector Local = Vehicles[Intruded].Previous.InverseTransformPosition(Feet);
                if (Rider.TrackedVehicle == Intruded && Dt > 0.f)
                {
                    const double Speed = FVector::Dist(Local, Rider.TrackedLocal) / Dt;
                    Rider.TrackedSpeed = Rider.TrackedSpeed < 0. ? Speed : FMath::Lerp(Rider.TrackedSpeed, Speed, .3);
                }
                else Rider.TrackedSpeed = -1.;
                Rider.TrackedVehicle = Intruded; Rider.TrackedLocal = Local;
                const FVehicle& V = Vehicles[Intruded];
                const double CoachSpeed = FMath::Abs(Line.Speed(V.Train, Time)) * 100.;
                const bool bWithCoach = BaseVehicle == Intruded || (Rider.TrackedSpeed >= 0. && BelmonteTrainRules::MovesWithCoach(Rider.TrackedSpeed, CoachSpeed));
                const bool bMovingOrDeparting = V.bMoved || CoachSpeed > 1. || !(TrainAtStation.IsValidIndex(V.Train) && TrainAtStation[V.Train]);
                const bool bZeppelin = C->IsZeppelinPassenger() || (bOnline && C->GetNetworkActivity() == EJapanActivity::Zeppelin);
                if (Rider.EjectCooldown <= 0.f && !bZeppelin &&
                    BelmonteTrainRules::MustEject(true, false, false, false, bWithCoach, bMovingOrDeparting))
                {
                    Rider.EjectCooldown = 1.f;
                    if (Eject(Rider, Intruded)) continue;
                }
            }
        }
        // Where the rider last stood on foot on walkable ground off the train: the first recovery point in a tunnel.
        if (bOwner && C->HasAuthority() && Inside == INDEX_NONE && BaseVehicle == INDEX_NONE && !OnAnyVehicle(C, bOnline))
        {
            const UCharacterMovementComponent* M = C->GetCharacterMovement();
            bool bRoomSprint = false, bRoomCamera = false;
            if (M->IsMovingOnGround() && M->CurrentFloor.IsWalkableFloor() && !IsTrainPart(M->CurrentFloor.HitResult.GetComponent()) &&
                InteriorAt(Feet, FVector::ZeroVector, bRoomSprint, bRoomCamera) == INDEX_NONE)
            { Rider.LastSafe = Feet - FVector(0, 0, 5.); Rider.bHasLastSafe = true; }
        }
        // Carried by the vehicle. Standing on its floor the character movement follows it as its base; when it does
        // not (online, a process-local train is never a network base; or a moment off the floor, jumping), the
        // service moves the rider with the vehicle itself, before the character's own movement this frame.
        if (Inside != INDEX_NONE)
        {
            const FVehicle& V = Vehicles[Inside];
            FTransportRiders::Carry(Rider, *this, V.Body, V.Previous, V.bMoved);
        }

        const bool bWasAboard = Rider.bAboard;
        Rider.Vehicle = Inside;
        Board(Rider, Inside != INDEX_NONE);
        if (HasAuthority() && Rider.bAboard != bWasAboard) PublishNetworkState();
        C->bNoSprint = Inside != INDEX_NONE && bNoSprint;
        // No climbing anywhere aboard (the walls, partitions, furniture; the terrain the line still clips).
        if (Inside != INDEX_NONE)
            if (UAdventureMoveSet* Moves = C->GetMoves()) Moves->NoClimb = FMath::Max(Moves->NoClimb, .25f);
        UpdateCamera(Rider, Inside != INDEX_NONE && bCamera, Dt);
    }
    if (bPublish && HasAuthority()) PublishNetworkState();
}

int32 ABelmonteTrainService::InteriorAt(const FVector& Feet, const FVector& Margin, bool& bNoSprint, bool& bCamera) const
{
    for (int32 I = 0; I < Vehicles.Num(); ++I)
    {
        const FVehicle& V = Vehicles[I];
        if (FVector::DistSquared(V.Previous.GetLocation(), Feet) > FMath::Square(2500.)) continue;
        const FVector Local = V.Previous.InverseTransformPosition(Feet);
        for (const FInterior& Room : V.Interiors)
            if (Room.Box.ExpandBy(Margin).IsInside(Local)) { bNoSprint = Room.bNoSprint; bCamera = Room.bCamera; return I; }
    }
    return INDEX_NONE;
}

bool ABelmonteTrainService::Eject(FRider& Rider, int32 VehicleIndex)
{
    using BelmonteTrainRules::ERecovery;
    AWandererCharacter* C = Rider.Character.Get();
    if (!C || !Vehicles.IsValidIndex(VehicleIndex)) return false;
    const FVehicle& V = Vehicles[VehicleIndex];
    const FTransform& T = V.Body->GetComponentTransform();
    const UCapsuleComponent* Capsule = C->GetCapsuleComponent();
    const float Half = Capsule->GetScaledCapsuleHalfHeight();
    const FVector Local = T.InverseTransformPosition(C->GetActorLocation() - FVector(0, 0, Half));
    const double Floor = T.TransformPosition(FVector(Local.X, 0., 125.)).Z;
    // Where the coach is: within a platform, in the open, or in a tunnel or on a viaduct (never set down beside it).
    const double Chain = VehicleChainage(VehicleIndex), Length = VehicleHalfLength(VehicleIndex);
    const bool bEnclosed = Line.IsEnclosed(Chain - Length - 10., Chain + Length + 10.);
    int32 Platform = INDEX_NONE;
    for (int32 I = 0; I < Stations.Num(); ++I)
        if (FMath::Abs(Stations[I].Chainage - Chain) < 90. && (Platform == INDEX_NONE || FMath::Abs(Stations[I].Chainage - Chain) < FMath::Abs(Stations[Platform].Chainage - Chain)))
            Platform = I;
    // The sides in the coach's frame: the platform's (its doors on the station's side), else the nearer one first.
    double Near = Local.Y >= 0. ? 1. : -1., PlatformSide = Near;
    if (Platform != INDEX_NONE)
        for (const FDoor& Door : V.Doors)
            if (Door.bStation && Door.bLeft == Stations[Platform].bLeft && Door.Handles.Num()) { PlatformSide = Door.Handles[0].Y >= 0. ? 1. : -1.; break; }
    struct FCandidate { FVector Point; double Z, MaxOff; ERecovery Kind; };
    TArray<FCandidate, TInlineAllocator<24>> Candidates;
    // Beside the coach, 2.8 m from the centreline (clear of the 3.6 m body and its steps), at the player and at the doors
    // on that side (nearest first).
    auto Beside = [&](double Side, double MaxOff, ERecovery Kind)
    {
        Candidates.Add({T.TransformPosition(FVector(Local.X, Side * 280., 125.)), Floor, MaxOff, Kind});
        TArray<double, TInlineAllocator<8>> Xs;
        for (const FDoor& Door : V.Doors)
            if (Door.Handles.Num() && Door.Handles[0].Y * Side > 0. && !Door.bLocked) Xs.Add(Door.Handles[0].X);
        Xs.Sort([&](double A, double B) { return FMath::Abs(A - Local.X) < FMath::Abs(B - Local.X); });
        for (int32 I = 0; I < FMath::Min(Xs.Num(), 4); ++I)
            Candidates.Add({T.TransformPosition(FVector(Xs[I], Side * 280., 125.)), Floor, MaxOff, Kind});
    };
    for (const ERecovery Kind : BelmonteTrainRules::RecoveryOrder(Platform != INDEX_NONE, bEnclosed))
        switch (Kind)
        {
        case ERecovery::Platform:
            Beside(PlatformSide, 150., Kind);
            Candidates.Add({Stations[Platform].Arrival, Stations[Platform].Arrival.Z, 300., Kind});
            break;
        case ERecovery::DoorSide:
            Beside(Platform != INDEX_NONE ? -PlatformSide : Near, 300., Kind);
            if (Platform == INDEX_NONE) Beside(-Near, 300., Kind);
            break;
        case ERecovery::LastSafe:
            if (Rider.bHasLastSafe) Candidates.Add({Rider.LastSafe, Rider.LastSafe.Z, 100., Kind});
            break;
        case ERecovery::TrainLastSafe:
            if (bTrainSafe.IsValidIndex(V.Train) && bTrainSafe[V.Train]) Candidates.Add({TrainSafe[V.Train], TrainSafe[V.Train].Z, 100., Kind});
            break;
        case ERecovery::NextStation:
        {
            TArray<double> Chainages;
            for (const FStation& Station : Stations) Chainages.Add(Station.Chainage);
            const int32 Next = BelmonteTrainRules::NextStop(Chainages, Chain, Line.Speed(V.Train, ServiceTime()));
            if (Stations.IsValidIndex(Next)) Candidates.Add({Stations[Next].Arrival, Stations[Next].Arrival.Z, 300., Kind});
            for (int32 I = 0; I < Stations.Num(); ++I)
                if (I != Next) Candidates.Add({Stations[I].Arrival, Stations[I].Arrival.Z, 300., Kind});
            break;
        }
        }
    BelmonteTrainRecovery::FStander Stander;
    Stander.Radius = Capsule->GetScaledCapsuleRadius(); Stander.HalfHeight = Half;
    Stander.WalkableZ = C->GetCharacterMovement()->GetWalkableFloorZ(); Stander.Ignore = C;
    // Keep the camera's heading: the player is set down facing where they looked.
    const float Yaw = C->Controller ? float(C->Controller->GetControlRotation().Yaw) : float(C->GetActorRotation().Yaw);
    const bool bVehicle = OnAnyVehicle(C, JapanNetwork::IsOnline(GetWorld()));
    static const TCHAR* Names[] = {TEXT("platform"), TEXT("door_side"), TEXT("last_safe"), TEXT("train_last_safe"), TEXT("station")};
    for (const FCandidate& Candidate : Candidates)
    {
        FVector Feet;
        if (!BelmonteTrainRecovery::SafeStand(GetWorld(), Candidate.Point, Candidate.Z, Candidate.MaxOff, Stander,
                [this](const UPrimitiveComponent* Part) { return IsTrainPart(Part); }, Feet))
            continue;
        // TravelTo puts away the skateboard, bike, horse or sailboat first, cancels the rider here (the ticket and the
        // tracking end) and online hands the owner a new foot activity (the same path as the map's travel). It lands from
        // just above the verified floor, so on it.
        if (!C->TravelTo(Feet, Yaw, TEXT("train: not boarded"), 20.f)) return false;
        UE_LOG(LogTemp, Display, TEXT("TRAIN EJECT %s vehicle=%s chainage=%.0f enclosed=%d recovery=%s on_vehicle=%d at=(%.0f,%.0f,%.0f)"), *C->GetName(), *V.Id,
            Chain, bEnclosed, Names[uint8(Candidate.Kind)], bVehicle, Feet.X, Feet.Y, Feet.Z);
        const TCHAR* Msg = TEXT("On monte à pied, par une porte");
        if (C->IsLocallyControlled()) ULiveLibrary::Say(Msg, 2.f); else C->ClientActivityRejected(Msg);
        return true;
    }
    // Nowhere verified: the player is not moved blind; tried again a little later.
    Rider.EjectCooldown = 5.f;
    UE_LOG(LogTemp, Warning, TEXT("TRAIN EJECT %s vehicle=%s chainage=%.0f enclosed=%d: no safe destination among %d candidates"), *C->GetName(), *V.Id,
        Chain, bEnclosed, Candidates.Num());
    return false;
}

int32 ABelmonteTrainService::VehicleOf(const UPrimitiveComponent* Component) const
{
    if (!Component || Component->GetOwner() != this) return INDEX_NONE;
    for (int32 I = 0; I < Vehicles.Num(); ++I)
        if (Component == Vehicles[I].Body.Get() || Component->IsAttachedTo(Vehicles[I].Body.Get())) return I;
    return INDEX_NONE;
}

bool ABelmonteTrainService::IsTrainPart(const UPrimitiveComponent* Component) const
{
    return VehicleOf(Component) != INDEX_NONE;
}

double ABelmonteTrainService::VehicleChainage(int32 VehicleIndex) const
{
    if (!Vehicles.IsValidIndex(VehicleIndex)) return 0.;
    return Line.Chainage(Vehicles[VehicleIndex].Train, ServiceTime()) + Vehicles[VehicleIndex].Offset;
}

double ABelmonteTrainService::VehicleHalfLength(int32 VehicleIndex) const
{
    const UStaticMesh* Mesh = Vehicles.IsValidIndex(VehicleIndex) && Vehicles[VehicleIndex].Body ? Vehicles[VehicleIndex].Body->GetStaticMesh() : nullptr;
    return Mesh ? Mesh->GetBounds().BoxExtent.X / 100. : 15.;
}

bool ABelmonteTrainService::OnAnyVehicle(const AWandererCharacter* C, bool bOnline)
{
    if (!C) return false;
    if (bOnline) return C->GetNetworkActivity() != EJapanActivity::OnFoot;
    return C->OnVehicle() || (C->GetSkate() && C->GetSkate()->IsRiding()) || C->IsZeppelinPassenger();
}

void ABelmonteTrainService::RecordTrainSafe(double Time)
{
    // A nominal standing capsule; every use re-verifies the point with the player's own (Eject).
    BelmonteTrainRecovery::FStander Stander;
    for (int32 Train = 0; Train < Line.Trains.Num() && Train < TrainSafe.Num(); ++Train)
    {
        // The middle vehicle, beside its centre on either side, while the whole train runs in the open.
        TArray<int32, TInlineAllocator<8>> Mine;
        for (int32 I = 0; I < Vehicles.Num(); ++I) if (Vehicles[I].Train == Train) Mine.Add(I);
        if (Mine.IsEmpty() || FMath::Abs(Line.Speed(Train, Time)) < .5) continue;
        const double Centre = Line.Chainage(Train, Time);
        const double Reach = FMath::Abs(Vehicles[Mine[0]].Offset - Vehicles[Mine.Last()].Offset) / 2. + 40.;
        if (Line.IsEnclosed(Centre - Reach, Centre + Reach)) continue;
        const FVehicle& V = Vehicles[Mine[Mine.Num() / 2]];
        const FTransform& T = V.Body->GetComponentTransform();
        const double Floor = T.TransformPosition(FVector(0., 0., 125.)).Z;
        for (const double Side : {1., -1.})
        {
            FVector Feet;
            if (BelmonteTrainRecovery::SafeStand(GetWorld(), T.TransformPosition(FVector(0., Side * 280., 125.)), Floor, 300., Stander,
                    [this](const UPrimitiveComponent* Part) { return IsTrainPart(Part); }, Feet))
            { TrainSafe[Train] = Feet; bTrainSafe[Train] = true; break; }
        }
    }
}

bool ABelmonteTrainService::Nearest(const AWandererCharacter* C, int32& VehicleIndex, int32& Index, bool& bSeat) const
{
    VehicleIndex = Index = INDEX_NONE; bSeat = false;
    if (!C) return false;
    const FVector At = C->GetActorLocation();
    const FVector Feet = At - FVector(0, 0, C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const FRider* Rider = FindRider(C);
    const bool bAboard = Rider && Rider->bAboard;
    const FVector Facing = C->GetActorForwardVector().GetSafeNormal2D();
    double Best = TNumericLimits<double>::Max();
    for (int32 I = 0; I < Vehicles.Num(); ++I)
    {
        const FVehicle& V = Vehicles[I];
        if (FVector::DistSquared(V.Body->GetComponentLocation(), At) > FMath::Square(2000.)) continue;
        const FTransform& T = V.Body->GetComponentTransform();
        for (int32 D = 0; D < V.Doors.Num(); ++D)
        {
            const FDoor& Door = V.Doors[D];
            // In a vestibule three doors are within reach: the one the player faces wins, and a door that can't open
            // now (the far side's exterior door, a moving train's) only answers when nothing else is in reach.
            const bool bShut = Door.bLocked || (Door.bStation && (!TrainAtStation[V.Train] || !Door.bPlatformSide));
            for (const FVector& Handle : Door.Handles)
            {
                const FVector Point = T.TransformPosition(Handle);
                const double Distance = FVector::Dist(Point, At);
                const double Score = Distance + (bShut ? 300. : 0.) + 60. * (1. - FVector::DotProduct(Facing, (Point - At).GetSafeNormal2D()));
                if (Distance < 150. && Score < Best) { Best = Score; VehicleIndex = I; Index = D; bSeat = false; }
            }
            // A door with steps is also reached from where its way starts: outside on the ground, inside at the top.
            if (Door.Boarding.Num())
            {
                const FVector End = T.TransformPosition(bAboard ? Door.Boarding.Last() : Door.Boarding[0]);
                const double Distance = FVector::Dist2D(End, Feet);
                const double Score = Distance + (bShut ? 300. : 0.) + 60. * (1. - FVector::DotProduct(Facing, (End - Feet).GetSafeNormal2D()));
                if (Distance < 140. && FMath::Abs(End.Z - Feet.Z) < (bAboard ? 60. : 200.) && Score < Best) { Best = Score; VehicleIndex = I; Index = D; bSeat = false; }
            }
        }
        // Only from inside: a seat behind the wall is not one to sit on from the platform.
        for (int32 S = 0; bAboard && S < V.Seats.Num(); ++S)
        {
            if (V.SeatTaken[S]) continue;
            const FVector Seat = T.TransformPosition(V.Seats[S].Location);
            const double Distance = FVector::Dist2D(Seat, Feet);
            // Seats win over a door handle at the same distance (a door is usually a step further), and like doors
            // the one the player faces wins.
            const double Score = Distance - 25. + 60. * (1. - FVector::DotProduct(Facing, (Seat - At).GetSafeNormal2D()));
            if (Distance < 100. && FMath::Abs(Seat.Z - Feet.Z) < 120. && Score < Best) { Best = Score; VehicleIndex = I; Index = S; bSeat = true; }
        }
    }
    return VehicleIndex != INDEX_NONE;
}

bool ABelmonteTrainService::TryInteract(AWandererCharacter* C)
{
    ABelmonteTrainService* Service = Find(C);
    if (!Service || !C) return false;
    if ((C->GetSkate() && C->GetSkate()->IsRiding()) || C->OnVehicle() || C->IsZeppelinPassenger()) return false;
    FRider& Rider = Service->RiderFor(C);
    if (Rider.BoardDoor != INDEX_NONE) return true;
    if (Rider.Seat != INDEX_NONE) { Service->StandUp(Rider); return true; }
    int32 VehicleIndex, Index; bool bSeat;
    if (!Service->Nearest(C, VehicleIndex, Index, bSeat)) return false;
    if (bSeat) { Service->SitDown(Rider, VehicleIndex, Index); Service->PublishNetworkState(); return true; }
    FVehicle& V = Service->Vehicles[VehicleIndex];
    FDoor& Door = V.Doors[Index];
    if (Door.bLocked) { const FString Msg = Door.Kind == TEXT("staff") ? TEXT("Réservé au personnel") : TEXT("Porte verrouillée"); if (C->IsLocallyControlled()) ULiveLibrary::Say(Msg, 2.f); else C->ClientActivityRejected(Msg); return true; }
    if (Door.bStation && (!Service->TrainAtStation[V.Train] || !Door.bPlatformSide)) { if (C->IsLocallyControlled()) ULiveLibrary::Say(TEXT("Fermé"), 2.f); else C->ClientActivityRejected(TEXT("Fermé")); return true; }
    // Station doors with steps: Monter from the platform, Descendre from inside.
    if (Door.Boarding.Num())
    {
        const bool bStarted = Service->StartBoarding(Rider, VehicleIndex, Index);
        if (bStarted) Service->PublishNetworkState();
        return bStarted;
    }
    Door.bOpen = !Door.bOpen;
    UE_LOG(LogTemp, Display, TEXT("TRAIN DOOR %s %s %s"), *V.Id, *Door.Id, Door.bOpen ? TEXT("open") : TEXT("closed"));
    // A crossing has a gangway door on each coach: one Interact opens (or shuts) both, so the way through is one press.
    if (Door.Kind == TEXT("gangway"))
    {
        const FTransform& T = V.Body->GetComponentTransform();
        for (FVehicle& Other : Service->Vehicles)
        {
            if (&Other == &V || Other.Train != V.Train) continue;
            const FTransform& OT = Other.Body->GetComponentTransform();
            for (FDoor& Facing : Other.Doors)
                if (Facing.Kind == TEXT("gangway") && !Facing.bLocked && Facing.Handles.Num() && Door.Handles.Num()
                    && FVector::Dist(OT.TransformPosition(Facing.Handles[0]), T.TransformPosition(Door.Handles[0])) < 300.)
                    Facing.bOpen = Door.bOpen;
        }
    }
    Service->PublishNetworkState();
    return true;
}

FString ABelmonteTrainService::Hint(const AWandererCharacter* C)
{
    const ABelmonteTrainService* Service = Find(C);
    if (!Service || !C) return FString();
    if ((C->GetSkate() && C->GetSkate()->IsRiding()) || C->OnVehicle() || C->IsZeppelinPassenger()) return FString();
    const FRider* Rider = Service->FindRider(C);
    if (Rider && Rider->BoardDoor != INDEX_NONE) return FString();
    if (Rider && Rider->Seat != INDEX_NONE) return TEXT("Use: se lever");
    int32 VehicleIndex, Index; bool bSeat;
    if (!Service->Nearest(C, VehicleIndex, Index, bSeat)) return FString();
    if (bSeat) return TEXT("Use: s'asseoir");
    const FVehicle& V = Service->Vehicles[VehicleIndex];
    const FDoor& Door = V.Doors[Index];
    if (Door.bLocked) return Door.Kind == TEXT("staff") ? TEXT("Réservé au personnel") : TEXT("Porte verrouillée");
    if (Door.bStation && (!Service->TrainAtStation[V.Train] || !Door.bPlatformSide)) return TEXT("Fermé");
    if (Door.Boarding.Num()) return Rider && Rider->bAboard ? TEXT("Use: descendre") : TEXT("Use: monter");
    return Door.bOpen ? TEXT("Use: fermer la porte") : TEXT("Use: ouvrir la porte");
}

FString ABelmonteTrainService::Status(const AWandererCharacter* C) const
{
    const FRider* Rider = FindRider(C);
    if (!Rider) return TEXT("none");
    return FString::Printf(TEXT("aboard=%d vehicle=%s seat=%s nosprint=%d"), Rider->bAboard,
        Vehicles.IsValidIndex(Rider->Vehicle) ? *Vehicles[Rider->Vehicle].Id : TEXT("-"),
        Rider->Seat != INDEX_NONE && Vehicles.IsValidIndex(Rider->Vehicle) ? *Vehicles[Rider->Vehicle].Seats[Rider->Seat].Id : TEXT("-"), C ? C->bNoSprint : 0);
}

void ABelmonteTrainService::Report(double Time) const
{
    FString Text;
    for (int32 Train = 0; Train < Line.Trains.Num(); ++Train)
    {
        const double S = Line.Chainage(Train, Time), V = Line.Speed(Train, Time);
        const FVector P = Line.Point(S, Line.OnLoopTrack(Train, Time));
        Text += FString::Printf(TEXT(" %s: s=%.1f v=%.1fkm/h %s track=%s station=%d at=(%.0f,%.0f,%.0f)"), *Line.Trains[Train].Name, S, FMath::Abs(V) * 3.6,
            FMath::Abs(V) < .05 ? TEXT("stopped") : V > 0. ? TEXT("up") : TEXT("down"), Line.OnLoopTrack(Train, Time) && Line.Loop.Covers(S) ? TEXT("loop") : TEXT("main"),
            TrainAtStation.IsValidIndex(Train) && TrainAtStation[Train], P.X, P.Y, P.Z);
    }
    for (const FRider& Rider : Riders)
        if (const AWandererCharacter* C = Rider.Character.Get())
        {
            const FVector L = C->GetActorLocation();
            Text += FString::Printf(TEXT(" rider %s %s at=(%.0f,%.0f,%.0f)"), *C->GetName(), *Status(C), L.X, L.Y, L.Z);
        }
    UE_LOG(LogTemp, Display, TEXT("TRAIN SERVICE vehicles=%d time=%.1f cycle=%.1f scale=%.2f%s"), Vehicles.Num(),
        FMath::Fmod(Time, Line.Cycle), Line.Cycle, CVarTrainTimeScale.GetValueOnGameThread(), *Text);
}

void ABelmonteTrainService::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    const float Scale = FMath::Clamp(CVarTrainTimeScale.GetValueOnGameThread(), 0.f, 100.f);
    if (Scale != 1.f && HasAuthority()) DevOffset += double(DeltaSeconds) * (Scale - 1.);
    if (PendingViewDelay >= 0.f && (PendingViewDelay -= DeltaSeconds) < 0.f)
    {
        const bool bDone = PendingView.StartsWith(TEXT("go:")) ? GoToStation(PendingView.Mid(3), true) : View(PendingView);
        if (!bDone) PendingViewDelay = 1.f;
    }
    const double Time = ServiceTime();
    PlaceVehicles(Time, false);
    UpdateDoors(Time, DeltaSeconds);
    UpdateRiders(DeltaSeconds);
    if (GetNetMode() != NM_Client && GetWorld()->GetTimeSeconds() >= NextSafeRecord) { NextSafeRecord = GetWorld()->GetTimeSeconds() + 1.; RecordTrainSafe(Time); }
    // A dev clock speed keeps the clients' offset in step; its change back to 1 is published too (the boards use it).
    if (HasAuthority() && JapanNetwork::IsOnline(GetWorld()) && (Scale != 1.f || NetworkState.TimeScale != Scale) &&
        GetWorld()->GetTimeSeconds() - LastNetworkPublication >= .2)
        PublishNetworkState();
    const double Now = GetWorld()->GetRealTimeSeconds();
    if (Now >= NextBoardUpdate) { NextBoardUpdate = Now + 1.; UpdateBoards(Time); }
    if (Now >= NextReport) { NextReport = Now + 5.; Report(Time); }
}

double ABelmonteTrainService::ClockScale() const
{
    if (GetNetMode() == NM_Client) return NetworkState.Serial ? NetworkState.TimeScale : 1.;
    return FMath::Clamp(CVarTrainTimeScale.GetValueOnGameThread(), 0.f, 100.f);
}

bool ABelmonteTrainService::GoToStation(const FString& Where, bool bWaitForTrain)
{
    const FStation* Station = Stations.FindByPredicate([&](const FStation& S) { return S.Key.Contains(Where) || S.Name.Contains(Where); });
    if (!Station) { UE_LOG(LogTemp, Warning, TEXT("TRAIN GO no station %s"), *Where); return true; }
    UWorld* World = GetWorld();
    APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
    auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    if (!Player) return false;
    double Wait = -1.;
    if (bWaitForTrain && !JapanNetwork::IsOnline(World) && !AnyRiderAboard())
    {
        // The start of the next dwell there (or now, if a train already stands there with time to spare).
        const double Now = ServiceTime();
        for (double T = Now; T < Now + Line.Cycle + 1. && Wait < 0.; T += 1.)
            for (int32 Train = 0; Train < Line.Trains.Num(); ++Train)
                if (FMath::Abs(Line.Chainage(Train, T) - Station->Chainage) < 1. && AtStation(Train, T + 45.))
                { Wait = T - Now; break; }
        if (Wait > 0.) { DevOffset += Wait - 2.; PublishNetworkState(); }
    }
    // The arrival record is at platform height. Search below its canopy, rather than landing on the roof.
    const bool bMoved = Player->TravelTo(Station->Arrival, Station->Yaw, TEXT("train station"), 200.f);
    UE_LOG(LogTemp, Display, TEXT("TRAIN GO %s moved=%d skipped=%.0fs at=(%.0f,%.0f,%.0f)"), *Station->Name, bMoved, FMath::Max(Wait, 0.), Station->Arrival.X, Station->Arrival.Y, Station->Arrival.Z);
    PlaceVehicles(ServiceTime(), true);
    return bMoved;
}

bool ABelmonteTrainService::View(const FString& Where)
{
    UWorld* World = GetWorld();
    APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
    auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    if (!Player) return false;
    const double Now = ServiceTime();
    double At = Line.Viewpoints.Num() ? Line.Viewpoints[0] : Line.Main.S[Line.Main.S.Num() / 2];
    double When = -1.; int32 Train = 0; double Lead = 20.;
    if (Where.Equals(TEXT("loop"), ESearchCase::IgnoreCase))
        When = Line.NextCrossing(Now + 1., &At);
    else if (Where.Equals(TEXT("a"), ESearchCase::IgnoreCase) || Where.Equals(TEXT("b"), ESearchCase::IgnoreCase))
    {
        Train = FMath::Min(Where.Equals(TEXT("a"), ESearchCase::IgnoreCase) ? 0 : 1, Line.Trains.Num() - 1);
        At = Line.Chainage(Train, Now) + 60.; When = Now + Lead;   // ahead of the head, without moving the clock
    }
    else
    {
        if (Where.IsNumeric()) At = FCString::Atod(*Where);
        When = Line.NextPassing(Now + 1., At, &Train);
    }
    if (When >= 0. && !JapanNetwork::IsOnline(World) && !AnyRiderAboard()) DevOffset += (When - Lead) - Now;
    // Stand 14 m to the side of the main line, on the side away from the loop's second track, facing the rails.
    const FVector Rail = Line.Point(At, false), Ahead = Line.Point(At + 5., false);
    FVector Side = FVector::CrossProduct(FVector::UpVector, (Ahead - Rail).GetSafeNormal2D());
    if (Line.Loop.Covers(At) && FVector::DotProduct(Line.Loop.At(At) - Rail, Side) > 0.) Side = -Side;
    const FVector Spot = Rail + Side * 1400.;
    const float Yaw = float((Rail - Spot).Rotation().Yaw) + 25.f;
    const bool bMoved = Player->TravelTo(Spot, Yaw, TEXT("train view"), 6000.f);
    UE_LOG(LogTemp, Display, TEXT("TRAIN VIEW %s chainage=%.0f train=%s passes_in=%.0fs moved=%d at=(%.0f,%.0f,%.0f) rail_z=%.0f"), *Where, At,
        Line.Trains.IsValidIndex(Train) ? *Line.Trains[Train].Name : TEXT("-"), When >= 0. ? Lead : -1., bMoved, Spot.X, Spot.Y, Spot.Z, Rail.Z);
    PlaceVehicles(ServiceTime(), true);
    return bMoved;
}

// ------------------------------------------------------------------------------------------------------------ Live

FString ABelmonteTrainService::StateJson() const
{
    const double Time = ServiceTime();
    FString Trains;
    for (int32 Train = 0; Train < Line.Trains.Num(); ++Train)
        Trains += FString::Printf(TEXT("%s{\"name\":\"%s\",\"s\":%.2f,\"kmh\":%.2f,\"station\":%s,\"loop\":%s}"), Train ? TEXT(",") : TEXT(""),
            *Line.Trains[Train].Name, Line.Chainage(Train, Time), Line.Speed(Train, Time) * 3.6,
            AtStation(Train, Time) ? TEXT("true") : TEXT("false"), Line.OnLoopTrack(Train, Time) && Line.Loop.Covers(Line.Chainage(Train, Time)) ? TEXT("true") : TEXT("false"));
    FString BoardText;
    for (const FBoard& Board : Boards)
        BoardText += FString::Printf(TEXT("%s{\"id\":\"%s\",\"station\":\"%s\",\"next\":\"%s\",\"after\":\"%s\"}"), BoardText.IsEmpty() ? TEXT("") : TEXT(","),
            *Board.Id, Stations.IsValidIndex(Board.Station) ? *Stations[Board.Station].Key : TEXT(""), *Board.Shown[0], *Board.Shown[1]);
    const APlayerController* PC = GetWorld()->GetFirstPlayerController();
    const auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    const FRider* Rider = FindRider(Player);
    FVector At = Player ? Player->GetActorLocation() : FVector::ZeroVector;
    FString Base = Player && Player->GetMovementBase() ? Player->GetMovementBase()->GetName() : FString();
    // The player in their vehicle's frame (cm, same frame as the rest of this state): drift checks need both at once.
    const FVector Local = Rider && Vehicles.IsValidIndex(Rider->Vehicle) ? Vehicles[Rider->Vehicle].Body->GetComponentTransform().InverseTransformPosition(At) : FVector::ZeroVector;
    return FString::Printf(TEXT("{\"time\":%.2f,\"scale\":%.2f,\"trains\":[%s],\"boards\":[%s],\"player\":[%.1f,%.1f,%.1f],\"aboard\":%s,\"vehicle\":\"%s\",\"train\":%d,\"seat\":\"%s\",\"nosprint\":%s,\"base\":\"%s\",\"mode\":%d,\"action\":\"%s\",\"boarding\":%s,\"camera\":%.2f,\"arm\":%.0f,\"yaw\":%.1f,\"local\":[%.1f,%.1f,%.1f],\"admitted\":%s,\"first_person\":%s,\"on_vehicle\":%s}"),
        Time, ClockScale(), *Trains, *BoardText, At.X, At.Y, At.Z, Rider && Rider->bAboard ? TEXT("true") : TEXT("false"),
        Rider && Vehicles.IsValidIndex(Rider->Vehicle) ? *Vehicles[Rider->Vehicle].Id : TEXT(""),
        Rider && Vehicles.IsValidIndex(Rider->Vehicle) ? Vehicles[Rider->Vehicle].Train : -1,
        Rider && Rider->Seat != INDEX_NONE ? *Vehicles[Rider->Vehicle].Seats[Rider->Seat].Id : TEXT(""),
        Player && Player->bNoSprint ? TEXT("true") : TEXT("false"), *Base,
        Player ? int32(Player->GetCharacterMovement()->MovementMode.GetValue()) : -1, Player ? *Player->GetAnimationAction().ToString() : TEXT(""),
        Rider && Rider->BoardDoor != INDEX_NONE ? TEXT("true") : TEXT("false"), Rider ? Rider->Camera : 0.f,
        Player && Player->CameraArm ? Player->CameraArm->TargetArmLength : 0.f, Player ? Player->GetActorRotation().Yaw : 0.f,
        Local.X, Local.Y, Local.Z, Rider && Rider->Admission.bAdmitted ? TEXT("true") : TEXT("false"),
        Player && Player->IsTrainFirstPerson() ? TEXT("true") : TEXT("false"),
        OnAnyVehicle(Player, JapanNetwork::IsOnline(GetWorld())) ? TEXT("true") : TEXT("false"));
}

FVector ABelmonteTrainService::PointOn(int32 Train, const FString& Vehicle, const FString& What) const
{
    for (const FVehicle& V : Vehicles)
    {
        if (V.Train != Train || V.Id != Vehicle) continue;
        const FTransform& T = V.Body->GetComponentTransform();
        TArray<FString> Parts_; What.ParseIntoArray(Parts_, TEXT(":"));
        if (Parts_.IsEmpty() || Parts_[0] == TEXT("centre")) return T.TransformPosition(FVector(0, 0, 125));
        if (Parts_[0] == TEXT("local") && Parts_.Num() > 2)   // vehicle metres, y to the left, on the floor
            return T.TransformPosition(FVector(FCString::Atod(*Parts_[1]) * 100., -FCString::Atod(*Parts_[2]) * 100., 125));
        if (Parts_[0] == TEXT("floor") && Parts_.Num() > 1) return T.TransformPosition(FVector(FCString::Atod(*Parts_[1]) * 100., 0, 125));
        if (Parts_[0] == TEXT("seat") && Parts_.Num() > 1)
        {
            const int32 I = FCString::Atoi(*Parts_[1]);
            return V.Seats.IsValidIndex(I) ? T.TransformPosition(V.Seats[I].Location) : FVector::ZeroVector;
        }
        if (Parts_[0] == TEXT("door") && Parts_.Num() > 2)
            for (const FDoor& Door : V.Doors)
                if (Door.Id == Parts_[1])
                {
                    const int32 I = FCString::Atoi(*Parts_[2]);
                    return Door.Handles.IsValidIndex(I) ? T.TransformPosition(Door.Handles[I]) : FVector::ZeroVector;
                }
        if (Parts_[0] == TEXT("board") && Parts_.Num() > 2)   // a door's boarding path: 0 outside, -1 inside
            for (const FDoor& Door : V.Doors)
                if (Door.Id == Parts_[1] && Door.Boarding.Num())
                {
                    const int32 I = FCString::Atoi(*Parts_[2]);
                    return T.TransformPosition(Door.Boarding[I < 0 ? Door.Boarding.Num() + I : FMath::Min(I, Door.Boarding.Num() - 1)]);
                }
    }
    return FVector::ZeroVector;
}

FString UBelmonteTrainLive::TrainState()
{
    const ABelmonteTrainService* Service = ABelmonteTrainService::Find(ULiveLibrary::GameWorld());
    return Service ? Service->StateJson() : FString(TEXT("{}"));
}

FVector UBelmonteTrainLive::TrainPoint(int32 Train, const FString& Vehicle, const FString& What)
{
    const ABelmonteTrainService* Service = ABelmonteTrainService::Find(ULiveLibrary::GameWorld());
    return Service ? Service->PointOn(Train, Vehicle, What) : FVector::ZeroVector;
}

FString UBelmonteTrainLive::TrainPrompt()
{
    const auto* Player = Cast<AWandererCharacter>(ULiveLibrary::Player());
    return Player ? ABelmonteTrainService::Hint(Player) : FString();
}

// ------------------------------------------------------------------------------------------------------------ Import

int32 UBelmonteTrainImportLibrary::SetSimpleBoxes(UStaticMesh* Mesh, const TArray<FBox>& Boxes)
{
#if WITH_EDITOR
    if (!Mesh) return -1;
    if (!Mesh->GetBodySetup()) Mesh->CreateBodySetup();
    UBodySetup* Body = Mesh->GetBodySetup();
    Body->Modify();
    Body->RemoveSimpleCollision();
    for (const FBox& Box : Boxes)
    {
        const FVector Size = Box.GetSize();
        FKBoxElem Element(Size.X, Size.Y, Size.Z);
        Element.Center = Box.GetCenter();
        Body->AggGeom.BoxElems.Add(Element);
    }
    Body->CollisionTraceFlag = CTF_UseSimpleAsComplex;
    Body->InvalidatePhysicsData();
    Body->CreatePhysicsMeshes();
    Mesh->bCustomizedCollision = true;
    Mesh->MarkPackageDirty();
    return Body->AggGeom.BoxElems.Num();
#else
    return -1;
#endif
}
