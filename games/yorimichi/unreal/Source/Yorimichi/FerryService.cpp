#include "FerryService.h"
#include "FoliageSystem.h"
#include "AtelierData.h"
#include "JapanNetwork.h"
#include "LiveLibrary.h"
#include "WandererCharacter.h"
#include "Algo/BinarySearch.h"
#include "Components/BoxComponent.h"
#include "Components/CapsuleComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Components/TextRenderComponent.h"
#include "Materials/MaterialInterface.h"
#include "Dom/JsonObject.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/GameStateBase.h"
#include "GameFramework/PlayerController.h"
#include "HAL/IConsoleManager.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Net/UnrealNetwork.h"

static TAutoConsoleVariable<float> CVarFerryTimeScale(TEXT("ferry.TimeScale"), 1.f,
    TEXT("Ferry service clock speed (1 = the timetable; dev only, the host's runs the clients' ships too)."));

static FAutoConsoleCommandWithWorldAndArgs FerryGoCommand(TEXT("ferry.Go"),
    TEXT("ferry.Go [hidamari|brinecove]: jump the ferry clock to the next ship coming alongside there and walk up to the terminal."),
    FConsoleCommandWithWorldAndArgsDelegate::CreateLambda([](const TArray<FString>& Args, UWorld* World)
    {
        if (auto* Service = AFerryService::Find(World)) Service->GoTo(Args.Num() ? Args[0] : FString(TEXT("hidamari")));
        else UE_LOG(LogTemp, Warning, TEXT("FERRY GO no ferry service in this world"));
    }));

// ------------------------------------------------------------------------------------------------------------ Line

static EFerryAudioPhase PhaseNamed(const FString& Name)
{
    if (Name == TEXT("departing")) return EFerryAudioPhase::Departing;
    if (Name == TEXT("cruise")) return EFerryAudioPhase::Cruise;
    if (Name == TEXT("approach")) return EFerryAudioPhase::Approach;
    return EFerryAudioPhase::Berthed;
}

bool FFerryLine::Parse(const TSharedPtr<FJsonObject>& Root, FString& Error)
{
    *this = FFerryLine();
    const TSharedPtr<FJsonObject>* Data = nullptr;
    if (!Root || !Root->TryGetObjectField(TEXT("line"), Data)) { Error = TEXT("no line"); return false; }
    const TSharedPtr<FJsonObject>& L = *Data;
    Cycle = L->GetNumberField(TEXT("cycle_s"));
    ClockStart = L->GetNumberField(TEXT("clock_start_s"));
    Step = L->GetNumberField(TEXT("step_s"));
    const TArray<TSharedPtr<FJsonValue>>* Rows = nullptr;
    if (!FMath::IsFinite(Cycle) || !FMath::IsFinite(Step) || !FMath::IsFinite(ClockStart) || Cycle <= 1. || Step <= 0. || !L->TryGetArrayField(TEXT("samples"), Rows)) { Error = TEXT("no cycle, step or samples"); return false; }
    for (const auto& Row : *Rows)
    {
        if (!Row || Row->Type != EJson::Array) { Error = TEXT("invalid sample"); return false; }
        const auto& A = Row->AsArray();
        for (const auto& Value : A)
            if (!Value || Value->Type != EJson::Number || !FMath::IsFinite(Value->AsNumber()))
            { Error = TEXT("non-finite or non-numeric sample"); return false; }
        if (A.Num() != 8) { Error = TEXT("short sample"); return false; }
        FFerrySample& S = Samples.AddDefaulted_GetRef();
        S.At = FVector2D(A[0]->AsNumber(), A[1]->AsNumber()); S.Yaw = A[2]->AsNumber();
        S.Velocity = FVector2D(A[3]->AsNumber(), A[4]->AsNumber()); S.YawRate = A[5]->AsNumber();
        S.Throttle = float(A[6]->AsNumber()); S.Thruster = float(A[7]->AsNumber());
    }
    if (Samples.Num() < 2 || !FMath::IsNearlyEqual(Samples.Num() * Step, Cycle, 1e-3)) { Error = TEXT("the samples do not fill the cycle"); return false; }
    if (!L->TryGetArrayField(TEXT("ships"), Rows) || Rows->Num() != 1) { Error = TEXT("the line requires exactly one ferry"); return false; }
    for (const auto& Value : *Rows)
    {
        const auto Ship = Value->AsObject();
        if (!Ship) { Error = TEXT("invalid ship"); return false; }
        ShipNames.Add(Ship->GetStringField(TEXT("name")));
        ShipOffsets.Add(Ship->GetNumberField(TEXT("offset_s")));
    }
    if (!L->TryGetArrayField(TEXT("phases"), Rows) || Rows->IsEmpty()) { Error = TEXT("no phases"); return false; }
    for (const auto& Row : *Rows)
    {
        const auto& A = Row->AsArray();
        if (A.Num() < 4) { Error = TEXT("short phase"); return false; }
        FFerryPhase& P = Phases.AddDefaulted_GetRef();
        P.Start = A[0]->AsNumber(); P.End = A[1]->AsNumber(); P.Phase = PhaseNamed(A[2]->AsString());
        if (A[2]->AsString() != TEXT("berthed") && A[2]->AsString() != TEXT("departing") &&
            A[2]->AsString() != TEXT("cruise") && A[2]->AsString() != TEXT("approach"))
        { Error = TEXT("unknown voyage phase"); return false; }
        double Berth = -1.;
        P.Berth = A[3]->TryGetNumber(Berth) && Berth >= 0. ? int32(Berth) : INDEX_NONE;
        if (P.End < P.Start || (Phases.Num() > 1 && !FMath::IsNearlyEqual(P.Start, Phases[Phases.Num() - 2].End, 1e-3)))
        { Error = TEXT("phases out of order"); return false; }
    }
    if (!FMath::IsNearlyZero(Phases[0].Start, 1e-3) || !FMath::IsNearlyEqual(Phases.Last().End, Cycle, 1e-3))
    { Error = TEXT("phases do not cover the complete cycle"); return false; }
    if (!L->TryGetArrayField(TEXT("brows"), Rows) || Rows->Num() != 2) { Error = TEXT("no brows"); return false; }
    for (const auto& Berth : *Rows)
    {
        TArray<FVector4>& Windows = BrowWindows.AddDefaulted_GetRef();
        for (const auto& W : Berth->AsArray())
        {
            const auto& A = W->AsArray();
            if (A.Num() < 4) { Error = TEXT("short brow window"); return false; }
            const FVector4 Window(A[0]->AsNumber(), A[1]->AsNumber(), A[2]->AsNumber(), A[3]->AsNumber());
            const int32 BerthIndex = BrowWindows.Num() - 1;
            if (!(Window.X >= 0. && Window.X < Window.Y && Window.Y <= Window.Z && Window.Z < Window.W && Window.W <= Cycle) ||
                !Phases.ContainsByPredicate([&](const FFerryPhase& P) { return P.Berth == BerthIndex &&
                    P.Phase == EFerryAudioPhase::Berthed && P.Start <= Window.X && P.End >= Window.W; }))
            { Error = TEXT("brow window is not inside its docked dwell"); return false; }
            Windows.Add(Window);
        }
    }
    return true;
}

double FFerryLine::ShipTime(int32 Ship, double Time) const
{
    const double Offset = ShipOffsets.IsValidIndex(Ship) ? ShipOffsets[Ship] : 0.;
    return FMath::Fmod(FMath::Fmod(Time + Offset, Cycle) + Cycle, Cycle);
}

FFerryState FFerryLine::State(int32 Ship, double Time) const
{
    FFerryState Out;
    if (Samples.Num() < 2) return Out;
    const double T = ShipTime(Ship, Time);
    Out.CycleTime = T;
    const int32 N = Samples.Num();
    const double F = T / Step;
    const int32 I = FMath::Clamp(int32(F), 0, N - 1), J = (I + 1) % N;
    const double U = F - FMath::FloorToDouble(F), U2 = U * U, U3 = U2 * U;
    const FFerrySample& A = Samples[I]; const FFerrySample& B = Samples[J];
    // Cubic Hermite through the samples' positions and velocities (the timetable's own derivatives).
    const double H00 = 2 * U3 - 3 * U2 + 1, H10 = U3 - 2 * U2 + U, H01 = -2 * U3 + 3 * U2, H11 = U3 - U2;
    const double D00 = 6 * U2 - 6 * U, D10 = 3 * U2 - 4 * U + 1, D01 = -6 * U2 + 6 * U, D11 = 3 * U2 - 2 * U;
    const FVector2D P = A.At * H00 + A.Velocity * (Step * H10) + B.At * H01 + B.Velocity * (Step * H11);
    const FVector2D V = (A.At * D00 + A.Velocity * (Step * D10) + B.At * D01 + B.Velocity * (Step * D11)) / Step;
    const double Turn = FRotator::NormalizeAxis(B.Yaw - A.Yaw);
    Out.Location = FVector(P.X, P.Y, 0.);
    Out.Velocity = FVector(V.X, V.Y, 0.);
    Out.Yaw = FRotator::NormalizeAxis(A.Yaw + A.YawRate * Step * H10 + Turn * H01 + B.YawRate * Step * H11);
    Out.YawRate = (A.YawRate * Step * D10 + Turn * D01 + B.YawRate * Step * D11) / Step;
    Out.Throttle = FMath::Lerp(A.Throttle, B.Throttle, float(U));
    Out.Thruster = FMath::Lerp(A.Thruster, B.Thruster, float(U));
    const int32 K = FMath::Clamp(int32(Algo::UpperBoundBy(Phases, T, &FFerryPhase::Start)) - 1, 0, Phases.Num() - 1);
    if (Phases.IsValidIndex(K)) { Out.Phase = Phases[K].Phase; Out.Berth = Phases[K].Berth; }
    return Out;
}

float FFerryLine::BrowDown(int32 Berth, double Time) const
{
    if (!BrowWindows.IsValidIndex(Berth)) return 0.f;
    double Down = 0.;
    for (int32 Ship = 0; Ship < ShipOffsets.Num(); ++Ship)
    {
        const double T = ShipTime(Ship, Time);
        for (const FVector4& W : BrowWindows[Berth])
        {
            double D = 0.;
            if (T >= W.X && T < W.Y) D = (T - W.X) / FMath::Max(W.Y - W.X, 1e-3);
            else if (T >= W.Y && T < W.Z) D = 1.;
            else if (T >= W.Z && T < W.W) D = 1. - (T - W.Z) / FMath::Max(W.W - W.Z, 1e-3);
            Down = FMath::Max(Down, D);
        }
    }
    return float(Down * Down * (3. - 2. * Down));
}

double FFerryLine::NextAlongside(int32 Berth, double From, int32* Which) const
{
    double Best = -1.;
    for (int32 Ship = 0; Ship < ShipOffsets.Num(); ++Ship)
    {
        const double T = ShipTime(Ship, From);
        for (const FFerryPhase& P : Phases)
        {
            if (P.Phase != EFerryAudioPhase::Berthed || P.Berth != Berth) continue;
            const double Wait = FMath::Fmod(P.Start - T + Cycle, Cycle);
            if (Best < 0. || From + Wait < Best) { Best = From + Wait; if (Which) *Which = Ship; }
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

AFerryService::AFerryService()
{
    PrimaryActorTick.bCanEverTick = true;
    // Before the characters: riders standing on a deck are carried by it (based movement) in the same frame.
    PrimaryActorTick.TickGroup = TG_PrePhysics;
    bReplicates = true;
    bAlwaysRelevant = true;
    SetNetUpdateFrequency(5.f);
    SetMinNetUpdateFrequency(1.f);
    Tags.Add(TEXT("NoClimb"));   // nobody climbs the ships' or terminals' walls (AdventureMoveSet::Climbable)
    RootComponent = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
    RootComponent->SetMobility(EComponentMobility::Static);
}

void AFerryService::GetLifetimeReplicatedProps(TArray<FLifetimeProperty>& OutLifetimeProps) const
{
    Super::GetLifetimeReplicatedProps(OutLifetimeProps);
    DOREPLIFETIME(AFerryService, NetworkState);
}

AFerryService* AFerryService::Spawn(UWorld* World, const FString& Path)
{
    if (!World || !FPaths::FileExists(Path)) return nullptr;
    if (AFerryService* Existing = Find(World)) return Existing;
    auto* Service = World->SpawnActor<AFerryService>();
    if (Service && !Service->Initialize(Path)) { Service->Destroy(); return nullptr; }
    return Service;
}

AFerryService* AFerryService::Find(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    TActorIterator<AFerryService> It(World);
    return It ? *It : nullptr;
}

void AFerryService::BeginPlay()
{
    Super::BeginPlay();
    // A client builds the ships and terminals when the host's replicated service arrives.
    if (!bInitialized) Initialize(AtelierDataPath(TEXT("ferry/service/service.json")));
}

double AFerryService::ServiceTime() const
{
    const UWorld* World = GetWorld();
    const AGameStateBase* State = World ? World->GetGameState() : nullptr;
    const double Now = State ? State->GetServerWorldTimeSeconds() : (World ? World->GetTimeSeconds() : 0.);
    return Now + Line.ClockStart + DevOffset;
}

UStaticMeshComponent* AFerryService::MeshPart(const FString& Name, const FString& Asset, USceneComponent* Parent, bool bCollision, bool bMovable)
{
    UStaticMesh* Mesh = UYorimichiFoliageSubsystem::LoadMesh(GetWorld(), Asset);
    if (!Mesh) { UE_LOG(LogTemp, Warning, TEXT("FERRY SERVICE missing mesh %s"), *Asset); return nullptr; }
    auto* C = NewObject<UStaticMeshComponent>(this, *Name);
    C->SetMobility(bMovable ? EComponentMobility::Movable : EComponentMobility::Static);
    C->SetupAttachment(Parent);
    C->SetStaticMesh(Mesh);
    C->SetCollisionEnabled(bCollision ? ECollisionEnabled::QueryAndPhysics : ECollisionEnabled::NoCollision);
    C->SetGenerateOverlapEvents(false);
    C->SetCanEverAffectNavigation(false);
    C->SetAffectDistanceFieldLighting(false);
    C->PrimaryComponentTick.bCanEverTick = false;
    // Stable names on every machine: a deck or a brow is a network movement base.
    C->SetNetAddressable();
    Components.Add(C);
    return C;
}

bool AFerryService::Initialize(const FString& Path)
{
    if (bInitialized) return true;
    if (bInitFailed) return false;
    const TSharedPtr<FJsonObject> Root = AtelierReadJson(Path);
    FString Error;
    if (!Line.Parse(Root, Error)) { bInitFailed = true; UE_LOG(LogTemp, Error, TEXT("FERRY SERVICE cannot read %s: %s"), *Path, *Error); return false; }
    int32 Missing = 0;
    // The terminals: static meshes at their anchors, their collision (hidden), and each brow on its hinge.
    for (const auto& Value : Root->GetArrayField(TEXT("terminals")))
    {
        const auto T = Value->AsObject();
        FTerminal& Terminal = Terminals.AddDefaulted_GetRef();
        Terminal.Key = T->GetStringField(TEXT("key")); Terminal.Name = T->GetStringField(TEXT("name"));
        Terminal.Anchor = JsonVector(T->GetArrayField(TEXT("anchor_cm")));
        Terminal.bStarboard = T->GetStringField(TEXT("side")) == TEXT("starboard");
        for (const auto& Part : T->GetArrayField(TEXT("parts")))
        {
            const auto P = Part->AsObject();
            UStaticMeshComponent* C = MeshPart(Terminal.Key + TEXT("_") + P->GetStringField(TEXT("name")), P->GetStringField(TEXT("mesh")), RootComponent, false, false);
            if (!C) { ++Missing; continue; }
            C->SetWorldLocation(Terminal.Anchor);
            C->RegisterComponent();
            Terminal.Parts.Add(C);
        }
        if (UStaticMeshComponent* C = MeshPart(Terminal.Key + TEXT("_Collision"), T->GetStringField(TEXT("collision")), RootComponent, true, false))
        {
            C->SetWorldLocation(Terminal.Anchor);
            C->SetCollisionProfileName(TEXT("BlockAll"));
            C->SetVisibility(false);
            C->RegisterComponent();
        }
        else ++Missing;
        const auto Brow = T->GetObjectField(TEXT("brow"));
        Terminal.HingeAt = JsonVector(Brow->GetArrayField(TEXT("hinge_cm")));
        const FVector To = JsonVector(Brow->GetArrayField(TEXT("to_cm")));
        // Raising swings the brow's far end up about its hinge: the axis across the brow, so that a positive angle lifts it.
        Terminal.Axis = FVector::CrossProduct((To - Terminal.HingeAt).GetSafeNormal2D(), FVector::UpVector).GetSafeNormal();
        if (FQuat(Terminal.Axis, FMath::DegreesToRadians(1.f)).RotateVector(To - Terminal.HingeAt).Z < (To - Terminal.HingeAt).Z)
            Terminal.Axis *= -1.;
        Terminal.Raised = float(Brow->GetNumberField(TEXT("raised_deg")));
        auto* Hinge = NewObject<USceneComponent>(this, *(Terminal.Key + TEXT("_BrowHinge")));
        Hinge->SetMobility(EComponentMobility::Movable);
        Hinge->SetupAttachment(RootComponent);
        Hinge->SetWorldLocation(Terminal.HingeAt);
        Hinge->RegisterComponent();
        Terminal.Hinge = Hinge;
        if (UStaticMeshComponent* C = MeshPart(Terminal.Key + TEXT("_Brow"), Brow->GetStringField(TEXT("mesh")), Hinge, true, true))
        {
            C->SetRelativeLocation(Terminal.Anchor - Terminal.HingeAt);
            C->SetCollisionProfileName(TEXT("BlockAllDynamic"));
            C->RegisterComponent();
            Terminal.Brow = C;
        }
        else ++Missing;
        for (const auto& P : T->GetArrayField(TEXT("walk_cm"))) Terminal.Walk.Add(JsonVector(P->AsArray()));
        Terminal.WalkYaw = float(T->GetNumberField(TEXT("walk_yaw")));
        if (GetNetMode() != NM_DedicatedServer)
        {
            const auto Board = T->GetObjectField(TEXT("board"));
            auto* Text = NewObject<UTextRenderComponent>(this, *(Terminal.Key + TEXT("_TimetableText")));
            Text->SetupAttachment(RootComponent); Text->SetMobility(EComponentMobility::Static);
            Text->SetWorldLocationAndRotation(JsonVector(Board->GetArrayField(TEXT("location_cm"))), FRotator(0, Board->GetNumberField(TEXT("yaw")), 0));
            Text->SetWorldSize(Board->GetNumberField(TEXT("text_size_cm")));
            Text->SetHorizontalAlignment(EHTA_Center); Text->SetVerticalAlignment(EVRTA_TextTop);
            Text->SetTextRenderColor(FColor(35, 30, 25)); Text->SetCastShadow(false);
            Text->SetCollisionEnabled(ECollisionEnabled::NoCollision); Text->SetCachedMaxDrawDistance(10000.f);
            Text->RegisterComponent(); Terminal.Board = Text;
        }
    }
    // The ships: the collision (hidden) is each ship's body, the render meshes ride on it, and so do the gate stops and
    // the sounds.
    const auto ShipData = Root->GetObjectField(TEXT("ship"));
    Deck = FBox(JsonVector(ShipData->GetArrayField(TEXT("deck_box_cm")), 0), JsonVector(ShipData->GetArrayField(TEXT("deck_box_cm")), 3));
    for (const auto& Value : ShipData->GetArrayField(TEXT("gates")))
    {
        const auto G = Value->AsObject();
        GateSpecs.Add({JsonVector(G->GetArrayField(TEXT("centre_cm"))), JsonVector(G->GetArrayField(TEXT("extent_cm"))),
            JsonVector(G->GetArrayField(TEXT("hinge_cm"))), float(G->GetNumberField(TEXT("open_yaw"))),
            G->GetStringField(TEXT("side")) == TEXT("starboard")});
    }
    for (int32 I = 0; I < Line.ShipNames.Num(); ++I)
    {
        FShip& Ship = Ships.AddDefaulted_GetRef();
        const FString Name = TEXT("Ferry_") + Line.ShipNames[I];
        Ship.Body = MeshPart(Name, ShipData->GetStringField(TEXT("body")), RootComponent, true, true);
        if (!Ship.Body) { ++Missing; Ships.Pop(); continue; }
        Ship.Body->SetAbsolute(true, true, true);
        Ship.Body->SetCollisionProfileName(TEXT("BlockAllDynamic"));
        Ship.Body->SetCollisionObjectType(ECC_Vehicle);
        Ship.Body->SetVisibility(false);
        Ship.Body->RegisterComponent();
        for (const auto& Part : ShipData->GetArrayField(TEXT("parts")))
        {
            const auto P = Part->AsObject();
            UStaticMeshComponent* C = MeshPart(Name + TEXT("_") + P->GetStringField(TEXT("name")), P->GetStringField(TEXT("mesh")), Ship.Body, false, true);
            if (!C) { ++Missing; continue; }
            const float Cull = float(P->GetNumberField(TEXT("cull_cm")));
            if (Cull > 0.f) { C->SetCachedMaxDrawDistance(Cull); C->LDMaxDrawDistance = Cull; }
            C->RegisterComponent();
            Ship.Parts.Add(C);
        }
        for (int32 G = 0; G < GateSpecs.Num(); ++G)
        {
            auto* Box = NewObject<UBoxComponent>(this, *FString::Printf(TEXT("%s_Gate_%d"), *Name, G));
            Box->SetMobility(EComponentMobility::Movable);
            Box->SetupAttachment(Ship.Body);
            Box->SetRelativeLocation(GateSpecs[G].Centre);
            Box->SetBoxExtent(GateSpecs[G].Extent, false);
            Box->SetCollisionProfileName(TEXT("BlockAllDynamic"));
            Box->SetCollisionObjectType(ECC_Vehicle);
            Box->SetCollisionResponseToChannel(ECC_Camera, ECR_Ignore);
            Box->SetGenerateOverlapEvents(false);
            Box->SetCanEverAffectNavigation(false);
            Box->SetNetAddressable();
            Box->RegisterComponent();
            Ship.Gates.Add(Box);
            Components.Add(Box);
            UStaticMeshComponent* Visual = MeshPart(FString::Printf(TEXT("%s_GateRail_%d"), *Name, G),
                ShipData->GetStringField(TEXT("gate_mesh")), Ship.Body, false, true);
            if (!Visual) ++Missing;
            else { Visual->SetRelativeLocation(GateSpecs[G].Hinge); Visual->RegisterComponent(); }
            Ship.GateVisuals.Add(Visual); Ship.GateYaw.Add(0.f);
        }
        if (GetNetMode() != NM_DedicatedServer)
        {
            Ship.Audio = NewObject<UFerryAudioComponent>(this, *(Name + TEXT("_Audio")));
            Ship.Audio->SetupAttachment(Ship.Body);
            Ship.Audio->RegisterComponent();
        }
    }
    float Scale = 1.f;
    if (FParse::Value(FCommandLine::Get(), TEXT("ferrytimescale="), Scale)) CVarFerryTimeScale->Set(Scale);
    FString Where;
    if (FParse::Value(FCommandLine::Get(), TEXT("ferrygo="), Where) || FParse::Param(FCommandLine::Get(), TEXT("ferrygo")))
    { PendingGo = Where.IsEmpty() ? FString(TEXT("hidamari")) : Where; PendingGoDelay = 4.f; }
    if (GetNetMode() == NM_Client) OnRep_NetworkState();
    PlaceShips(ServiceTime(), true);
    UpdateBrows(ServiceTime());
    UpdateGates();
    bInitialized = Missing == 0 && Ships.Num() == 1 && Terminals.Num() == 2;
    bInitFailed = !bInitialized;
    if (bInitialized && HasAuthority()) PublishNetworkState();
    UE_LOG(LogTemp, Display, TEXT("FERRY SERVICE ready ships=%d terminals=%d cycle=%.1f samples=%d phases=%d missing=%d"),
        Ships.Num(), Terminals.Num(), Line.Cycle, Line.Samples.Num(), Line.Phases.Num(), Missing);
    return bInitialized;
}

void AFerryService::EndPlay(const EEndPlayReason::Type Reason)
{
    for (FRider& Rider : Riders) if (Rider.Character.IsValid()) FTransportRiders::SetAboard(Rider, false, false, ETransportVehicle::Ferry);
    Super::EndPlay(Reason);
}

void AFerryService::PlaceShips(double Time, bool bForce)
{
    for (int32 I = 0; I < Ships.Num(); ++I)
    {
        FShip& Ship = Ships[I];
        Ship.State = Line.State(I, Time);
        Ship.Previous = Ship.Body->GetComponentTransform();
        const FVector At = Ship.State.Location;
        const FRotator Rotation(0., Ship.State.Yaw, 0.);
        // A ship alongside is not moved again: no transform or physics update while it stands.
        Ship.bMoved = Ship.bPlaced && (!At.Equals(Ship.Previous.GetLocation(), .01) || !Rotation.Quaternion().Equals(Ship.Previous.GetRotation(), 1e-6));
        if (bForce || !Ship.bPlaced || Ship.bMoved)
            Ship.Body->SetWorldLocationAndRotation(At, Rotation, false, nullptr, bForce ? ETeleportType::TeleportPhysics : ETeleportType::None);
        if (bForce || !Ship.bPlaced) { Ship.Previous = Ship.Body->GetComponentTransform(); Ship.bMoved = false; }
        Ship.bPlaced = true;
    }
}

void AFerryService::UpdateBrows(double Time)
{
    for (int32 I = 0; I < Terminals.Num(); ++I)
    {
        FTerminal& T = Terminals[I];
        const float Down = Line.BrowDown(I, Time);
        if (T.Hinge && Down != T.Down)
            T.Hinge->SetWorldRotation(FQuat(T.Axis, FMath::DegreesToRadians(T.Raised * (1.f - Down))));
        // The ship alongside hears its brow land on the landing plate and lift off it.
        for (FShip& Ship : Ships)
            if (Ship.State.Phase == EFerryAudioPhase::Berthed && Ship.State.Berth == I && Ship.Audio)
            {
                const bool bDown = Down >= .98f;
                if (T.Down >= 0.f && bDown != Ship.bBrowHeardDown) { if (bDown) Ship.Audio->OnBoardingOpen(); else Ship.Audio->OnBoardingClose(); }
                Ship.bBrowHeardDown = bDown;
            }
        T.Down = Down;
    }
}

void AFerryService::UpdateGates()
{
    for (FShip& Ship : Ships)
    {
        // A boarding gate is open only where a brow rests on it: alongside, on the berth's side, brow down.
        const bool bAlongside = Ship.State.Phase == EFerryAudioPhase::Berthed && Terminals.IsValidIndex(Ship.State.Berth) &&
            Terminals[Ship.State.Berth].Down >= .999f;
        for (int32 G = 0; G < Ship.Gates.Num(); ++G)
        {
            const bool bOpen = bAlongside && GateSpecs[G].bStarboard == Terminals[Ship.State.Berth].bStarboard;
            const ECollisionEnabled::Type Wanted = bOpen ? ECollisionEnabled::NoCollision : ECollisionEnabled::QueryAndPhysics;
            if (Ship.Gates[G]->GetCollisionEnabled() != Wanted) Ship.Gates[G]->SetCollisionEnabled(Wanted);
            const float Target = bOpen ? GateSpecs[G].OpenYaw : 0.f;
            Ship.GateYaw[G] = Ship.bGatesPlaced ? FMath::FInterpConstantTo(Ship.GateYaw[G], Target, GetWorld()->GetDeltaSeconds(), 180.f) : Target;
            if (Ship.GateVisuals[G]) Ship.GateVisuals[G]->SetRelativeRotation(FRotator(0, Ship.GateYaw[G], 0));
        }
        Ship.bGatesPlaced = true;
    }
}

void AFerryService::UpdateBoards(double Time)
{
    if (GetWorld()->GetRealTimeSeconds() < NextBoardUpdate) return;
    NextBoardUpdate = GetWorld()->GetRealTimeSeconds() + 1.;
    const float Scale = GetNetMode() == NM_Client ? NetworkState.TimeScale : CVarFerryTimeScale.GetValueOnGameThread();
    for (int32 I = 0; I < Terminals.Num(); ++I)
    {
        FTerminal& Terminal = Terminals[I];
        if (!Terminal.Board) continue;
        FString Status;
        const FFerryState State = Line.State(0, Time);
        if (State.Berth == I)
        {
            Status = Terminal.Down >= .999f ? TEXT("Boarding open") : TEXT("Gangway closed");
            for (const FFerryPhase& Phase : Line.Phases)
                if (Phase.Berth == I && State.CycleTime >= Phase.Start && State.CycleTime < Phase.End)
                    Status += FString::Printf(TEXT("\nDeparting in %d s"), FMath::CeilToInt((Phase.End - State.CycleTime) / FMath::Max(Scale, .001f)));
        }
        else
        {
            const double Wait = FMath::Max(0., Line.NextAlongside(I, Time) - Time) / FMath::Max(Scale, .001f);
            Status = Wait < 60 ? TEXT("Arriving soon") : FString::Printf(TEXT("Arrives in %d min"), FMath::CeilToInt(Wait / 60.));
        }
        const FString Destination = Terminals.IsValidIndex(1 - I) ? Terminals[1 - I].Name : FString();
        Terminal.Board->SetText(FText::FromString(TEXT("Ferry to ") + Destination + TEXT("\n") + Status));
    }
}

AFerryService::FRider& AFerryService::RiderFor(AWandererCharacter* Character)
{
    return FTransportRiders::Find(Riders, Character);
}

const AFerryService::FRider* AFerryService::FindRider(const AWandererCharacter* Character) const
{
    for (const FRider& R : Riders) if (R.Character.Get() == Character) return &R;
    return nullptr;
}

int32 AFerryService::ShipOfComponent(const UPrimitiveComponent* Component) const
{
    if (!Component || Component->GetOwner() != this) return INDEX_NONE;
    for (int32 I = 0; I < Ships.Num(); ++I)
        if (Component == Ships[I].Body.Get() || Component->IsAttachedTo(Ships[I].Body.Get())) return I;
    return INDEX_NONE;
}

int32 AFerryService::DeckAt(const FVector& Feet) const
{
    for (int32 I = 0; I < Ships.Num(); ++I)
    {
        if (FVector::DistSquared2D(Ships[I].Previous.GetLocation(), Feet) > FMath::Square(6000.)) continue;
        const FTransform Now = Ships[I].Body->GetComponentTransform();
        const FVector Local = Ships[I].Previous.InverseTransformPosition(Feet);
        if (!Deck.IsInside(Local)) continue;
        FHitResult Hit;
        const FVector At = Now.TransformPosition(Local);
        FCollisionObjectQueryParams Objects(ECC_Vehicle);
        if (GetWorld()->LineTraceSingleByObjectType(Hit, At + FVector(0, 0, 15), At - FVector(0, 0, 80), Objects) &&
            Hit.GetComponent() == Ships[I].Body && Hit.ImpactNormal.Z >= .7f) return I;
    }
    return INDEX_NONE;
}

int32 AFerryService::ShipOf(const AWandererCharacter* Character) const
{
    const FRider* R = FindRider(Character);
    return R && R->bAboard ? R->Vehicle : INDEX_NONE;
}

void AFerryService::UpdateRiders(float Dt)
{
    bool bChanged = Riders.RemoveAll([](const FRider& R) { return !R.Character.IsValid(); }) > 0;
    for (TActorIterator<AWandererCharacter> It(GetWorld()); It; ++It)
    {
        AWandererCharacter* C = *It;
        if (C->IsNpc()) continue;
        FRider& Rider = RiderFor(C);
        FTransportRiders::OrderTick(*this, Rider);
        if (!C->IsPlayerControlled() || !(C->IsLocallyControlled() || C->HasAuthority())) continue;
        // On a deck: standing on a ship (its collision is the movement base) or with the feet in its deck volume, in the
        // frame the ship stood in last frame (where the rider still stands relative to it).
        const float Half = C->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        const FVector Feet = C->GetActorLocation() - FVector(0, 0, Half - 5.);
        int32 Ship = ShipOfComponent(C->GetMovementBase());
        if (Ship == INDEX_NONE) Ship = DeckAt(Feet);
        if (Ship != INDEX_NONE) FTransportRiders::Carry(Rider, *this, Ships[Ship].Body, Ships[Ship].Previous, Ships[Ship].bMoved);
        const bool bWas = Rider.bAboard;
        bChanged |= bWas != (Ship != INDEX_NONE) || (bWas && Rider.Vehicle != Ship);
        Rider.Vehicle = Ship;
        if (FTransportRiders::SetAboard(Rider, Ship != INDEX_NONE, false, ETransportVehicle::Ferry))
            UE_LOG(LogTemp, Display, TEXT("FERRY RIDER %s %s ship=%s"), *C->GetName(), bWas ? TEXT("left") : TEXT("boarded"),
                Line.ShipNames.IsValidIndex(Ship) ? *Line.ShipNames[Ship] : TEXT("-"));
    }
    if (bChanged && HasAuthority()) PublishNetworkState();
}

void AFerryService::UpdateAudio()
{
    for (FShip& Ship : Ships)
    {
        if (!Ship.Audio) continue;
        Ship.Audio->SetPhase(Ship.State.Phase);
        Ship.Audio->SetThrottle(Ship.State.Throttle);
        Ship.Audio->SetSpeed(float(Ship.State.Velocity.Size2D()));
        Ship.Audio->SetThruster(Ship.State.Thruster);
    }
}

bool AFerryService::AnyRiderAboard() const
{
    for (const FRider& R : Riders) if (R.Character.IsValid() && R.bAboard) return true;
    return false;
}

void AFerryService::PublishNetworkState()
{
    if (!HasAuthority() || !JapanNetwork::IsOnline(GetWorld())) return;
    ++NetworkState.Serial;
    NetworkState.DevOffset = DevOffset;
    NetworkState.TimeScale = FMath::Clamp(CVarFerryTimeScale.GetValueOnGameThread(), 0.f, 100.f);
    NetworkState.Passengers.Reset();
    for (const FRider& R : Riders)
        if (AWandererCharacter* C = R.Character.Get(); C && R.bAboard && Ships.IsValidIndex(R.Vehicle))
        {
            FFerryPassenger& P = NetworkState.Passengers.AddDefaulted_GetRef();
            P.Rider = C; P.Ship = int16(R.Vehicle);
        }
    ForceNetUpdate();
}

void AFerryService::OnRep_NetworkState()
{
    if (!NetworkState.Serial) return;
    DevOffset = NetworkState.DevOffset;
    ApplyRemotePassengers();
}

void AFerryService::ApplyRemotePassengers()
{
    if (!NetworkState.Serial || Ships.IsEmpty()) return;
    TArray<FTransportMembership> Membership;
    for (const FFerryPassenger& P : NetworkState.Passengers) Membership.Add({P.Rider.Get(), P.Ship});
    FTransportRiders::ApplyRemote(*this, Riders, Membership, Ships.Num(), ETransportVehicle::Ferry);
}

static const TCHAR* PhaseName(EFerryAudioPhase Phase)
{
    switch (Phase)
    {
    case EFerryAudioPhase::Departing: return TEXT("departing");
    case EFerryAudioPhase::Cruise: return TEXT("cruise");
    case EFerryAudioPhase::Approach: return TEXT("approach");
    default: return TEXT("berthed");
    }
}

void AFerryService::Report(double Time) const
{
    FString Text;
    for (int32 I = 0; I < Ships.Num(); ++I)
    {
        const FFerryState& S = Ships[I].State;
        Text += FString::Printf(TEXT(" %s: %s berth=%d t=%.1f v=%.1fm/s at=(%.0f,%.0f) yaw=%.1f"), *Line.ShipNames[I], PhaseName(S.Phase), S.Berth,
            S.CycleTime, S.Velocity.Size2D() / 100., S.Location.X, S.Location.Y, S.Yaw);
    }
    for (int32 I = 0; I < Terminals.Num(); ++I) Text += FString::Printf(TEXT(" brow_%s=%.2f"), *Terminals[I].Key, Terminals[I].Down);
    for (const FRider& R : Riders)
        if (const AWandererCharacter* C = R.Character.Get(); C && R.bAboard)
        {
            if (!Line.ShipNames.IsValidIndex(R.Vehicle)) continue;
            const FVector L = C->GetActorLocation();
            Text += FString::Printf(TEXT(" rider %s ship=%s at=(%.0f,%.0f,%.0f)"), *C->GetName(), *Line.ShipNames[R.Vehicle], L.X, L.Y, L.Z);
        }
    UE_LOG(LogTemp, Display, TEXT("FERRY SERVICE time=%.1f%s"), Time, *Text);
}

void AFerryService::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);
    if (!bInitialized) return;
    if (GetNetMode() == NM_Client) ApplyRemotePassengers();
    const float Scale = FMath::Clamp(CVarFerryTimeScale.GetValueOnGameThread(), 0.f, 100.f);
    if (HasAuthority())
    {
        if (Scale != 1.f) DevOffset += double(DeltaSeconds) * (Scale - 1.);
        if (Scale != 1.f || NetworkState.TimeScale != Scale) PublishNetworkState();
    }
    if (PendingGoDelay >= 0.f && (PendingGoDelay -= DeltaSeconds) < 0.f && !GoTo(PendingGo)) PendingGoDelay = 1.f;
    const double Time = ServiceTime();
    PlaceShips(Time, false);
    UpdateBrows(Time);
    UpdateGates();
    UpdateBoards(Time);
    UpdateRiders(DeltaSeconds);
    UpdateAudio();
    const double Now = GetWorld()->GetRealTimeSeconds();
    if (Now >= NextReport) { NextReport = Now + 5.; Report(Time); }
}

bool AFerryService::GoTo(const FString& Harbour)
{
    const int32 Berth = Terminals.IndexOfByPredicate([&](const FTerminal& T) { return T.Key.Contains(Harbour) || T.Name.Contains(Harbour); });
    if (Berth == INDEX_NONE) { UE_LOG(LogTemp, Warning, TEXT("FERRY GO no terminal %s"), *Harbour); return true; }
    UWorld* World = GetWorld();
    APlayerController* PC = World ? World->GetFirstPlayerController() : nullptr;
    auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    const FTerminal& T = Terminals[Berth];
    if (!Player || T.Walk.IsEmpty()) return false;
    double Skipped = 0.;
    if (GetNetMode() == NM_Standalone && !AnyRiderAboard())
    {
        // To just after the next ship comes alongside, once its brow is down (or now, if one stands there with time left).
        const double Now = ServiceTime();
        int32 Ship = INDEX_NONE;
        const double Next = Line.NextAlongside(Berth, Now - 60., &Ship);
        if (Next >= 0. && (Next + 13. < Now || Next > Now)) { Skipped = Next + 13. - Now; DevOffset += Skipped; PublishNetworkState(); }
    }
    const bool bMoved = Player->TravelTo(T.Walk[0], T.WalkYaw, TEXT("ferry terminal"), 300.f);
    UE_LOG(LogTemp, Display, TEXT("FERRY GO %s moved=%d skipped=%.0fs at=(%.0f,%.0f,%.0f)"), *T.Name, bMoved, Skipped, T.Walk[0].X, T.Walk[0].Y, T.Walk[0].Z);
    PlaceShips(ServiceTime(), true);
    UpdateBrows(ServiceTime());
    return bMoved;
}

FVector AFerryService::Point(const FString& What) const
{
    TArray<FString> P; What.ParseIntoArray(P, TEXT(":"));
    if (P.Num() >= 5 && P[0] == TEXT("ship") && Ships.IsValidIndex(FCString::Atoi(*P[1])))
        return Ships[FCString::Atoi(*P[1])].Body->GetComponentTransform().TransformPosition(
            FVector(FCString::Atod(*P[2]) * 100., -FCString::Atod(*P[3]) * 100., FCString::Atod(*P[4]) * 100.));
    if (P.Num() >= 3 && P[0] == TEXT("walk") && Terminals.IsValidIndex(FCString::Atoi(*P[1])))
    {
        const TArray<FVector>& W = Terminals[FCString::Atoi(*P[1])].Walk;
        const int32 I = FCString::Atoi(*P[2]);
        return W.Num() ? W[I < 0 ? FMath::Max(0, W.Num() + I) : FMath::Min(I, W.Num() - 1)] : FVector::ZeroVector;
    }
    return FVector::ZeroVector;
}

FString AFerryService::StateJson() const
{
    const double Time = ServiceTime();
    FString ShipText;
    for (int32 I = 0; I < Ships.Num(); ++I)
    {
        const FFerryState& S = Ships[I].State;
        const FVector L = Ships[I].Body->GetComponentLocation();
        ShipText += FString::Printf(TEXT("%s{\"name\":\"%s\",\"at\":[%.1f,%.1f,%.1f],\"yaw\":%.2f,\"speed\":%.1f,\"phase\":\"%s\",\"berth\":%d,\"cycle_time\":%.2f,\"throttle\":%.2f,\"thruster\":%.2f}"),
            I ? TEXT(",") : TEXT(""), *Line.ShipNames[I], L.X, L.Y, L.Z, Ships[I].Body->GetComponentRotation().Yaw, S.Velocity.Size2D(), PhaseName(S.Phase), S.Berth,
            S.CycleTime, S.Throttle, S.Thruster);
    }
    FString Brows;
    for (int32 I = 0; I < Terminals.Num(); ++I) Brows += FString::Printf(TEXT("%s\"%s\":%.3f"), I ? TEXT(",") : TEXT(""), *Terminals[I].Key, Terminals[I].Down);
    const APlayerController* PC = GetWorld()->GetFirstPlayerController();
    const auto* Player = PC ? Cast<AWandererCharacter>(PC->GetPawn()) : nullptr;
    const FRider* Rider = FindRider(Player);
    const FVector At = Player ? Player->GetActorLocation() : FVector::ZeroVector;
    const int32 Ship = Rider && Rider->bAboard ? Rider->Vehicle : INDEX_NONE;
    const FVector Local = Ships.IsValidIndex(Ship) ? Ships[Ship].Body->GetComponentTransform().InverseTransformPosition(At) : FVector::ZeroVector;
    const FString Base = Player && Player->GetMovementBase() ? Player->GetMovementBase()->GetName() : FString();
    return FString::Printf(TEXT("{\"time\":%.2f,\"cycle\":%.2f,\"ships\":[%s],\"brows\":{%s},\"player\":[%.1f,%.1f,%.1f],\"aboard\":%s,\"ship\":%d,\"local\":[%.1f,%.1f,%.1f],\"base\":\"%s\",\"mode\":%d,\"train_aboard\":%s}"),
        Time, Line.Cycle, *ShipText, *Brows, At.X, At.Y, At.Z, Ship != INDEX_NONE ? TEXT("true") : TEXT("false"), Ship, Local.X, Local.Y, Local.Z, *Base,
        Player ? int32(Player->GetCharacterMovement()->MovementMode.GetValue()) : -1, Player && Player->bTrainAboard ? TEXT("true") : TEXT("false"));
}

// ------------------------------------------------------------------------------------------------------------ Live

FString UFerryLive::FerryState()
{
    const AFerryService* Service = AFerryService::Find(ULiveLibrary::GameWorld());
    return Service ? Service->StateJson() : FString(TEXT("{}"));
}

FVector UFerryLive::FerryPoint(const FString& What)
{
    const AFerryService* Service = AFerryService::Find(ULiveLibrary::GameWorld());
    return Service ? Service->Point(What) : FVector::ZeroVector;
}

bool UFerryLive::FerryGo(const FString& Harbour)
{
    AFerryService* Service = AFerryService::Find(ULiveLibrary::GameWorld());
    return Service && Service->GoTo(Harbour);
}

FString UFerryLive::FerryLoops()
{
    const AFerryService* Service = AFerryService::Find(ULiveLibrary::GameWorld());
    if (!Service) return FString();
    FString Out;
    TArray<UFerryAudioComponent*> Audio;
    Service->GetComponents<UFerryAudioComponent>(Audio);
    for (const UFerryAudioComponent* A : Audio) Out += A->GetName() + TEXT(": ") + A->GetLoopState() + TEXT("\n");
    return Out;
}
