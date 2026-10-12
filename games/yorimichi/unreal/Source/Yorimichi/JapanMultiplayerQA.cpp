#include "JapanMultiplayerQA.h"
#if !UE_BUILD_SHIPPING
#include "JapanSession.h"
#include "JapanWorld.h"
#include "JapanNetwork.h"
#include "JapanCharacterMovement.h"
#include "JapanSkateNetwork.h"
#include "PlayableCharacter.h"
#include "WandererCharacter.h"
#include "WandererSword.h"
#include "AdventureMoveSet.h"
#include "SkateComponent.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "ZeppelinService.h"
#include "Components/StaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/CapsuleComponent.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "Engine/GameViewportClient.h"
#include "Dom/JsonObject.h"
#include "Misc/CommandLine.h"
#include "Misc/FileHelper.h"
#include "HAL/FileManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Algo/AllOf.h"
#include "UnrealClient.h"

struct FJapanMultiplayerQAAccess
{
    static bool Attached(const UAdventureMoveSet* Moves, bool Hand)
    {
        int32 Weapons = 0;
        for (const auto& Pair : Moves->Slots)
        {
            if (Pair.Value.Hand.IsNone()) continue;
            const auto* Prop = Moves->Props.Find(Pair.Key);
            if (!Prop || !*Prop || (*Prop)->GetAttachSocketName() != (Hand ? Pair.Value.Hand : Pair.Value.Back)) return false;
            ++Weapons;
        }
        return Weapons > 0;
    }
};
namespace
{
bool Save(const FString& File, const TSharedPtr<FJsonObject>& Data)
{
    FString Text; FJsonSerializer::Serialize(Data.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text, *(File+TEXT(".tmp"))) && IFileManager::Get().Move(*File, *(File+TEXT(".tmp")), true, true);
}
TSharedPtr<FJsonObject> Read(const FString& File)
{
    FString Text; TSharedPtr<FJsonObject> Data;
    if (FFileHelper::LoadFileToString(Text, *File)) FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Data);
    return Data;
}
struct FProbe
{
    TWeakObjectPtr<UWorld> World;
    FString Case;
    int32 Phase = 0, LocalPhase = -1, CapturedPhase = -1;
    double Began = -1., PhaseAt = 0., LastWrite = -1.;
    double LastLongFrameAt = -1.;
    uint32 EquipmentEpoch = 0;
    int32 EquipmentRecoveryRetries = 0;
    bool Finished = false, DefaultVehicles = false;
    bool CaptureApproved = false;
    bool SawAir = false, SawBail = false, CharacterSent = false;
    bool BikeExitSent = false, BikeExitGrounded = false;
    float BikeExitSpeed = -1.f;
    FVector SailLaunch = FVector::ZeroVector;
    int32 SailExitRequests = 0;
    double NextSailExit = 0.;
    TArray<TSharedPtr<FJsonValue>> Stages;
    TMap<FString, uint32> OriginalEpochs;
    EJapanActivity Activity() const
    {
        if (Case == TEXT("switch-bike")) return EJapanActivity::Bike;
        if (Case == TEXT("switch-sail")) return EJapanActivity::Sailboat;
        if (Case.StartsWith(TEXT("switch-skate"))) return EJapanActivity::Skate;
        if (Case == TEXT("zeppelin")) return EJapanActivity::Zeppelin;
        return EJapanActivity::OnFoot;
    }
    TSharedPtr<FJsonObject> Snapshot(AWandererCharacter* Local) const
    {
        auto Data = MakeShared<FJsonObject>();
        Data->SetStringField(TEXT("case"), Case); Data->SetNumberField(TEXT("phase"), Phase);
        Data->SetBoolField(TEXT("complete"), Finished); Data->SetBoolField(TEXT("default_vehicles"), DefaultVehicles);
        Data->SetBoolField(TEXT("requested_in_air"), SawAir); Data->SetBoolField(TEXT("requested_in_bail"), SawBail);
        Data->SetNumberField(TEXT("equipment_recovery_retries"), EquipmentRecoveryRetries);
        Data->SetBoolField(TEXT("bike_exit_sent"), BikeExitSent);
        Data->SetBoolField(TEXT("bike_exit_grounded"), BikeExitGrounded);
        Data->SetNumberField(TEXT("bike_exit_speed"), BikeExitSpeed);
        Data->SetNumberField(TEXT("sail_exit_requests"), SailExitRequests);
        Data->SetNumberField(TEXT("sail_shore_distance"), FVector::Dist2D(Local->GetActorLocation(), SailLaunch));
        Data->SetBoolField(TEXT("sail_landing_grounded"), Local->GetCharacterMovement()->IsMovingOnGround());
        Data->SetBoolField(TEXT("rendering"), FParse::Param(FCommandLine::Get(), TEXT("networkrender")));
        TArray<TSharedPtr<FJsonValue>> Views;
        for (TActorIterator<AWandererCharacter> It(World.Get()); It; ++It)
        {
            auto* P = *It; auto* State = P->GetPlayerState<AJapanPlayerState>(); auto* Moves = P->GetMoves();
            if (P->IsNpc() || !State || !Moves) continue;
            auto Row = MakeShared<FJsonObject>();
            Row->SetStringField(TEXT("player"), State->SessionPlayerId); Row->SetStringField(TEXT("rider"), FPlayableCharacter::NameOf(P));
            Row->SetStringField(TEXT("pawn"), P->GetClass()->GetPathName()); Row->SetBoolField(TEXT("local"), P == Local);
            Row->SetNumberField(TEXT("local_role"), int32(P->GetLocalRole()));
            Row->SetBoolField(TEXT("predicts_moves"), CastChecked<UJapanCharacterMovement>(P->GetCharacterMovement())->PredictsMoves());
            Row->SetBoolField(TEXT("ready"), P->IsReady()); Row->SetNumberField(TEXT("epoch"), P->GetActivityEpoch());
            Row->SetNumberField(TEXT("activity"), uint8(P->GetNetworkActivity())); Row->SetNumberField(TEXT("health"), P->GetSword()->GetHealth());
            Row->SetNumberField(TEXT("hits"), P->GetSword()->HitsTaken()); Row->SetBoolField(TEXT("armed"), Moves->IsArmed());
            Row->SetBoolField(TEXT("attachment"), FJapanMultiplayerQAAccess::Attached(Moves, Moves->IsArmed()));
            Row->SetBoolField(TEXT("guard"), Moves->IsGuarding()); Row->SetNumberField(TEXT("guard_weight"), Moves->SwordGuardWeight());
            Row->SetStringField(TEXT("action"), P->GetAnimationAction().ToString());
            Row->SetNumberField(TEXT("action_time"), P->GetActionTime());
            Row->SetStringField(TEXT("move_mode"), Moves->ModeName());
            Row->SetNumberField(TEXT("streamed_pose_bones"), P->GetSkate()->GetRiderPose().Num());
            const auto* Stream = P->FindComponentByClass<UJapanSkateNetwork>();
            Row->SetNumberField(TEXT("observed_pose_frames"), Stream ? Stream->GetObservedPoseCount() : 0);
            Row->SetNumberField(TEXT("matching_pose_frames"), Stream ? Stream->GetMatchingPoseCount() : 0);
            Row->SetNumberField(TEXT("matching_mesh_frames"), Stream ? Stream->GetMatchingMeshCount() : 0);
            Row->SetNumberField(TEXT("mesh_world_error"), Stream ? Stream->GetMeshWorldError() : -1.);
            const auto* Mesh = P->GetMesh();
            Row->SetBoolField(TEXT("body_visible"), Mesh->IsVisible() && !Mesh->bHiddenInGame && !P->IsHidden());
            Row->SetNumberField(TEXT("mesh_x"), Mesh->GetComponentLocation().X);
            Row->SetNumberField(TEXT("mesh_y"), Mesh->GetComponentLocation().Y);
            Row->SetNumberField(TEXT("mesh_z"), Mesh->GetComponentLocation().Z);
            Row->SetNumberField(TEXT("bounds_x"), Mesh->Bounds.Origin.X);
            Row->SetNumberField(TEXT("bounds_y"), Mesh->Bounds.Origin.Y);
            Row->SetNumberField(TEXT("bounds_z"), Mesh->Bounds.Origin.Z);
            Row->SetNumberField(TEXT("bounds_radius"), Mesh->Bounds.SphereRadius);
            const FVector Deck = P->GetSkate()->GetDeckWorld().GetLocation();
            Row->SetNumberField(TEXT("deck_x"), Deck.X);
            Row->SetNumberField(TEXT("deck_y"), Deck.Y);
            Row->SetNumberField(TEXT("deck_z"), Deck.Z);
            Row->SetNumberField(TEXT("checkpoints"), CastChecked<UJapanCharacterMovement>(P->GetCharacterMovement())->GetNetworkStats().Checkpoints);
            Row->SetNumberField(TEXT("simulation_tick"), double(P->GetSkate()->GetSimulationTick()));
            Row->SetNumberField(TEXT("continued_at_tick"), double(P->GetSkate()->GetContinuedAtTick()));
            Row->SetNumberField(TEXT("continued_mode"), uint8(P->GetSkate()->GetContinuedMode()));
            Row->SetNumberField(TEXT("ride_root_z"), P->GetSkate()->GetRideRoot().GetLocation().Z);
            Row->SetNumberField(TEXT("body_lift"), P->GetSkate()->GetBodyLift());
            Row->SetNumberField(TEXT("standing_half"), P->GetClass()->GetDefaultObject<AWandererCharacter>()->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
            Row->SetNumberField(TEXT("x"), P->GetActorLocation().X); Row->SetNumberField(TEXT("y"), P->GetActorLocation().Y); Row->SetNumberField(TEXT("z"), P->GetActorLocation().Z);
            Views.Add(MakeShared<FJsonValueObject>(Row));
        }
        Data->SetArrayField(TEXT("views"), Views);
        if (auto* Ship = Local->GetLandscape()->Zeppelin.Get())
        {
            Data->SetNumberField(TEXT("ship_stage"), Ship->GetStage()); Data->SetNumberField(TEXT("dock"), Ship->GetDock());
            Data->SetNumberField(TEXT("destination"), Ship->GetDestination()); Data->SetNumberField(TEXT("flight_speed"), Ship->GetFlightSpeed());
            Data->SetNumberField(TEXT("ship_z"), Ship->ShipPosition().Z);
        }
        return Data;
    }
    void Drive(AWandererCharacter* P)
    {
        bool Enter = Phase != LocalPhase;
        if (Case == TEXT("equipment") && EquipmentEpoch != P->GetActivityEpoch())
        {
            if (EquipmentEpoch) ++EquipmentRecoveryRetries;
            EquipmentEpoch = P->GetActivityEpoch();
            Enter = true; // A clock recovery invalidates the previous epoch's input edges.
        }
        if (Enter) { LocalPhase = Phase; CharacterSent = false; }
        P->SetMenuOpen(false); P->Live_Drive(FVector2D::ZeroVector, 1);
        auto* PC = CastChecked<AJapanPlayerController>(P->GetController());
        if (Case == TEXT("equipment"))
        {
            if (Enter && ((Phase == 1 && !P->GetMoves()->IsArmed()) || (Phase == 4 && P->GetMoves()->IsArmed()))) P->Live_Press(TEXT("weapon"));
            if (Enter && Phase == 2) P->Live_Press(TEXT("guard"));
            if (Phase == 2) P->Live_Drive(FVector2D(0,.2), 1);
            if (Enter && Phase == 3) { P->Live_Press(TEXT("guard_release")); P->Live_Press(TEXT("attack")); P->Live_Press(TEXT("attack_release")); }
            return;
        }
        if (Case == TEXT("zeppelin"))
        {
            auto* Ship = P->GetLandscape()->Zeppelin.Get();
            if (Enter && Phase == 0)
            {
                FVector Entry = Ship->GetStations()[Ship->GetDock()].Entry;
                Entry.X += P->HasAuthority() ? -50.f : 50.f;
                P->TravelTo(Entry, 0.f, TEXT("multiplayer zeppelin platform"));
            }
            if (Enter && Phase == 1) P->Live_Press(TEXT("interact"));
            if (Enter && Phase == 2) PC->RequestCharacter(TEXT("Modori"));
            if (Enter && Phase == 3) { P->Live_Press(TEXT("stop_next")); P->Live_Press(TEXT("interact")); }
            return;
        }
        if (Enter && Phase == 0 && Activity() == EJapanActivity::Sailboat)
            P->TravelTo(AJapanWorld::ToUE(P->HasAuthority()?-226.f:-216.f,-169.f,1.6f), 80.f, TEXT("multiplayer boat shore"));
        if (Enter && Phase == 1)
        {
            if (Activity() == EJapanActivity::Bike) P->Live_Press(TEXT("bike"));
            else if (Activity() == EJapanActivity::Sailboat)
            { SailLaunch = P->GetActorLocation(); P->Live_Press(TEXT("sailboat")); }
            else if (Activity() == EJapanActivity::Skate) P->Live_Press(TEXT("skateboard"));
            else P->Live_Press(TEXT("weapon"));
        }
        if (Phase == 2 && Case == TEXT("switch-skate-air") && !CharacterSent)
        {
            FSkateInput Input;
            const double Elapsed = FPlatformTime::Seconds() - PhaseAt;
            Input.Right = Elapsed < .35 ? FVector2D(0,-1) : Elapsed < .5 ? FVector2D(0,1) : FVector2D::ZeroVector;
            P->GetSkate()->SetScriptedInput(&Input);
            if (P->GetSkate()->GetMode() == ESkateMode::Air)
            {
                SawAir = true; CharacterSent = PC->RequestCharacter(TEXT("Modori"));
                P->GetSkate()->SetScriptedInput(nullptr);
            }
        }
        else if (Phase == 2 && Case == TEXT("switch-skate-bail") && !CharacterSent)
        {
            FSkateInput Input; Input.bBail = Enter;
            P->GetSkate()->SetScriptedInput(&Input);
            if (P->GetSkate()->GetMode() == ESkateMode::Bail)
            {
                SawBail = true; CharacterSent = PC->RequestCharacter(TEXT("Modori"));
                P->GetSkate()->SetScriptedInput(nullptr);
            }
        }
        else if (Enter && Phase == 2) CharacterSent = PC->RequestCharacter(TEXT("Modori"));
        if (Enter && Phase == 3) PC->RequestCharacter(TEXT("Cairo"));
        if (Phase >= 1 && Phase <= 3 && Activity() != EJapanActivity::OnFoot) P->Live_Drive(FVector2D(0,.4), 1);
        if (Phase == 4)
        {
            if (Activity() == EJapanActivity::Bike && !BikeExitSent)
            {
                // Ordinary V rejects a moving dismount. Brake through normal input
                // and send one request after stopping, preserving the final exit gate.
                P->Live_Drive(FVector2D(0,-1), 1);
                if (P->GetBike()->IsRiding() && FMath::Abs(P->GetBike()->GetSpeed()) <= 1.f &&
                    P->GetCharacterMovement()->IsMovingOnGround() && !P->IsNetworkActivityPending())
                {
                    BikeExitSpeed = P->GetBike()->GetSpeed(); BikeExitGrounded = true;
                    BikeExitSent = P->Live_Press(TEXT("bike"));
                }
            }
            else if (Activity() == EJapanActivity::Sailboat && P->GetNetworkActivity() == EJapanActivity::Sailboat)
            {
                // A sailing replacement must return to a real shore before K can
                // land. Steer and lower/raise the sail through ordinary move input.
                const FVector Return = SailLaunch - P->GetActorLocation();
                const float Turn = FMath::FindDeltaAngleDegrees(P->GetActorRotation().Yaw, Return.Rotation().Yaw);
                P->Live_Drive(FVector2D(FMath::Clamp(Turn / 30.f, -1.f, 1.f), FMath::Abs(Turn) > 60.f ? -.2f : .2f), 1);
                const double Now = FPlatformTime::Seconds();
                // The launch point can be inland of the hull-clearance boundary.
                // K still performs the actual supported-landing search on the host.
                if (Return.Size2D() <= 1500. && Now >= NextSailExit && !P->IsNetworkActivityPending())
                {
                    P->Live_Press(TEXT("sailboat")); ++SailExitRequests; NextSailExit = Now + .75;
                }
            }
            else if (Enter && Activity() == EJapanActivity::Skate) P->Live_Press(TEXT("skateboard"));
        }
    }
};
FProbe Probe;
bool ViewsMeet(const TSharedPtr<FJsonObject>& Data, TFunctionRef<bool(const FJsonObject&)> Gate)
{
    if (!Data) return false;
    const auto& Views = Data->GetArrayField(TEXT("views"));
    return Views.Num() == 2 && Algo::AllOf(Views, [&](const auto& Row){ return Gate(*Row->AsObject()); });
}
}
bool JapanMultiplayerQA::Tick(UWorld* World, bool Server, const FString& Folder, FString& Error)
{
    if (Probe.World.Get() != World)
    {
        Probe = FProbe(); Probe.World = World;
        FParse::Value(FCommandLine::Get(), TEXT("networkfeaturecase="), Probe.Case);
        auto* Rules = World->GetGameState<AJapanGameState>(); Probe.DefaultVehicles = Rules && Rules->bPredictedVehicles;
    }
    if (Probe.Finished) return true;
    const double Now = FPlatformTime::Seconds();
    if (Probe.Began >= 0. && Now - Probe.PhaseAt > 25.) { Error = FString::Printf(TEXT("Multiplayer feature %s phase %d timed out"), *Probe.Case, Probe.Phase); return false; }
    AWandererCharacter* Local = nullptr; int32 Players = 0;
    for (auto It = World->GetPlayerControllerIterator(); It; ++It)
        if (It->Get()->IsLocalController()) Local = Cast<AWandererCharacter>(It->Get()->GetPawn());
    for (TActorIterator<AWandererCharacter> It(World); It; ++It)
        if (!It->IsNpc() && It->GetPlayerState<AJapanPlayerState>() && It->IsReady()) ++Players;
    if (!Local || !Local->IsReady() || Players != 2 || !Local->GetLandscape() || !Local->GetLandscape()->bGameplayReady) return false;
    if (Probe.Case == TEXT("zeppelin") && (!Local->GetLandscape()->Zeppelin || !Local->GetLandscape()->Zeppelin->IsReady())) return false;
    // A rendered first launch can still be finishing shader/skin setup when the
    // world-ready flag appears. Require a settled frame window before stimulus.
    if (Probe.Began < 0.)
    {
        if (Probe.LastLongFrameAt < 0. || World->GetDeltaSeconds() > .125f) Probe.LastLongFrameAt = Now;
        if (Now - Probe.LastLongFrameAt < 2.) return false;
    }
    const FString ControlFile = Folder / TEXT("features-control.json");
    if (Server && Probe.Began < 0.)
    {
        Probe.Began = Probe.PhaseAt = Now;
        for (TActorIterator<AWandererCharacter> It(World); It; ++It) if (!It->IsNpc() && It->GetPlayerState<AJapanPlayerState>())
        {
            It->GetSword()->ApplyNetworkHealth(73.f, 2);
            Probe.OriginalEpochs.Add(It->GetPlayerState<AJapanPlayerState>()->SessionPlayerId, It->GetActivityEpoch());
        }
        auto Control = MakeShared<FJsonObject>(); Control->SetNumberField(TEXT("phase"), 0); Control->SetBoolField(TEXT("complete"), false); Save(ControlFile, Control);
    }
    if (!Server)
    {
        auto Control = Read(ControlFile); if (!Control) return false;
        const int32 Phase = int32(Control->GetNumberField(TEXT("phase")));
        if (Phase != Probe.Phase) { Probe.Phase = Phase; Probe.PhaseAt = Now; }
        double CapturePhase = -1.;
        Probe.CaptureApproved = Control->TryGetNumberField(TEXT("capture_phase"), CapturePhase) && int32(CapturePhase) == Phase;
        if (Control->GetBoolField(TEXT("complete"))) Probe.Finished = true;
        if (Probe.Began < 0.) Probe.Began = Probe.PhaseAt = Now;
    }
    Probe.Drive(Local);
    auto Host = Probe.Snapshot(Local);
    if (Now - Probe.LastWrite >= .1)
    {
        Probe.LastWrite = Now;
        if (!Save(Folder / (Server ? TEXT("features-host.json") : TEXT("features-guest.json")), Host)) { Error = TEXT("Could not save feature observation"); return false; }
    }
    if (!Server)
    {
        if (FParse::Param(FCommandLine::Get(), TEXT("networkrender")) && Probe.CaptureApproved &&
            Now - Probe.PhaseAt >= 2. && Probe.CapturedPhase != Probe.Phase)
        {
            FScreenshotRequest::RequestScreenshot(Folder / FString::Printf(TEXT("feature-%d.png"), Probe.Phase), false, false);
            Probe.CapturedPhase = Probe.Phase;
        }
        return Probe.Finished;
    }
    auto Peer = Read(Folder / TEXT("features-guest.json"));
    if (!Peer || Peer->GetNumberField(TEXT("phase")) != Probe.Phase || Now - Probe.PhaseAt < 2.) return false;
    const FString CaptureFile = Folder / FString::Printf(TEXT("feature-%d.png"), Probe.Phase);
    auto Gate = [&](const FJsonObject& R)
    {
        if (!R.GetBoolField(TEXT("ready")) || !R.GetBoolField(TEXT("attachment")) || R.GetNumberField(TEXT("health")) != 73. || R.GetNumberField(TEXT("hits")) != 2.) return false;
        const int32 Phase = Probe.Phase;
        if (Probe.Activity() == EJapanActivity::Skate && Phase >= 1 && Phase <= 3 && !R.GetBoolField(TEXT("local")))
        {
            const double Observed = R.GetNumberField(TEXT("observed_pose_frames"));
            if (Observed < 30. || R.GetNumberField(TEXT("matching_pose_frames")) < Observed * .95) return false;
            if (R.GetNumberField(TEXT("matching_mesh_frames")) < Observed * .95 ||
                R.GetNumberField(TEXT("mesh_world_error")) < 0. || R.GetNumberField(TEXT("mesh_world_error")) > 1. ||
                !R.GetBoolField(TEXT("body_visible"))) return false;
        }
        if (Probe.Case == TEXT("equipment"))
        {
            if (R.GetBoolField(TEXT("predicts_moves")) != (R.GetNumberField(TEXT("local_role")) >= ROLE_AutonomousProxy)) return false;
            return (Phase == 0 || Phase == 4) ? !R.GetBoolField(TEXT("armed")) :
                R.GetBoolField(TEXT("armed")) && (Phase != 2 || (R.GetBoolField(TEXT("guard")) && R.GetNumberField(TEXT("guard_weight")) > .8));
        }
        const auto Kind = EJapanActivity(int32(R.GetNumberField(TEXT("activity"))));
        if (Probe.Case == TEXT("zeppelin")) return Kind == ((Phase == 0 || Phase == 3) ? EJapanActivity::OnFoot : EJapanActivity::Zeppelin) &&
            (Phase < 2 || R.GetStringField(TEXT("rider")) == TEXT("Modori"));
        const FString Rider = Phase == 2 ? TEXT("Modori") : TEXT("Cairo");
        return R.GetStringField(TEXT("rider")) == Rider && Kind == ((Phase == 0 || Phase == 4) ? EJapanActivity::OnFoot : Probe.Activity()) &&
            (Phase < 2 || (Probe.OriginalEpochs.Contains(R.GetStringField(TEXT("player"))) && R.GetNumberField(TEXT("epoch")) > Probe.OriginalEpochs[R.GetStringField(TEXT("player"))]));
    };
    if (!ViewsMeet(Host, Gate) || !ViewsMeet(Peer, Gate)) return false;
    if (Probe.Case == TEXT("switch-bike") && Probe.Phase == 4 &&
        (!Probe.BikeExitSent || !Peer->GetBoolField(TEXT("bike_exit_sent")) ||
         !Peer->GetBoolField(TEXT("bike_exit_grounded")) ||
         FMath::Abs(Peer->GetNumberField(TEXT("bike_exit_speed"))) > 40.)) return false;
    if (Probe.Case == TEXT("switch-sail") && Probe.Phase == 4 &&
        (!Probe.SailExitRequests || Peer->GetNumberField(TEXT("sail_exit_requests")) < 1. ||
         !Host->GetBoolField(TEXT("sail_landing_grounded")) || !Peer->GetBoolField(TEXT("sail_landing_grounded")) ||
         Host->GetNumberField(TEXT("sail_shore_distance")) > 1500. || Peer->GetNumberField(TEXT("sail_shore_distance")) > 1500.)) return false;
    if (Probe.Case == TEXT("zeppelin") && (Probe.Phase == 1 || Probe.Phase == 2) && !Local->GetLandscape()->Zeppelin->IsFlying()) return false;
    // Readback and PNG saving can stall a cold renderer. Capture a state that
    // passed both observer gates, then finish saving before the next input phase.
    if (FParse::Param(FCommandLine::Get(), TEXT("networkrender")) && Probe.CapturedPhase != Probe.Phase)
    {
        FScreenshotRequest::RequestScreenshot(CaptureFile, false, false);
        Probe.CapturedPhase = Probe.Phase;
    }
    if ((FParse::Param(FCommandLine::Get(), TEXT("networkrender")) || Peer->GetBoolField(TEXT("rendering"))) &&
        !IFileManager::Get().FileExists(*CaptureFile))
    {
        auto Control = MakeShared<FJsonObject>(); Control->SetNumberField(TEXT("phase"), Probe.Phase);
        Control->SetBoolField(TEXT("complete"), false); Control->SetNumberField(TEXT("capture_phase"), Probe.Phase);
        Save(ControlFile, Control);
        return false;
    }
    auto Stage = MakeShared<FJsonObject>(); Stage->SetNumberField(TEXT("phase"), Probe.Phase);
    Stage->SetObjectField(TEXT("host"), Host); Stage->SetObjectField(TEXT("guest"), Peer); Probe.Stages.Add(MakeShared<FJsonValueObject>(Stage));
    const int32 Last = Probe.Case == TEXT("zeppelin") ? 3 : 4;
    if (Probe.Phase == Last)
    {
        Probe.Finished = true;
        auto Result = MakeShared<FJsonObject>(); Result->SetStringField(TEXT("case"), Probe.Case);
        Result->SetBoolField(TEXT("passed"), true); Result->SetBoolField(TEXT("default_vehicles"), Probe.DefaultVehicles);
        Result->SetArrayField(TEXT("stages"), Probe.Stages);
        if (!Save(Folder / TEXT("features-result.json"), Result)) Error = TEXT("Could not save feature result");
    }
    else { ++Probe.Phase; Probe.PhaseAt = Now; }
    auto Control = MakeShared<FJsonObject>(); Control->SetNumberField(TEXT("phase"), Probe.Phase); Control->SetBoolField(TEXT("complete"), Probe.Finished); Save(ControlFile, Control);
    UE_LOG(LogTemp, Display, TEXT("NETWORK feature=%s phase=%d complete=%d"), *Probe.Case, Probe.Phase, Probe.Finished);
    return Probe.Finished;
}
#else
bool JapanMultiplayerQA::Tick(UWorld*, bool, const FString&, FString&) { return false; }
#endif
