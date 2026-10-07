#include "JapanCharacterMovement.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "WandererSword.h"
#include "BotwMoveSet.h"
#include "SkateComponent.h"
#include "GameFramework/Controller.h"
#include "Engine/World.h"
#include "Interfaces/MovementBaseInterface.h"
#include "Components/PrimitiveComponent.h"
#include "TimerManager.h"

UJapanCharacterMovement::UJapanCharacterMovement(const FObjectInitializer& Initializer) : Super(Initializer)
{
    SetNetworkMoveDataContainer(NetworkMoves);
    SetMoveResponseDataContainer(NetworkResponse);
}

void UJapanCharacterMovement::SetBase(FMovementBaseInterfaceData* Base, const FName Bone, bool bNotifyActor)
{
    // Locally constructed terrain has no shared object identity. Walk on its collision in world space; never send
    // a process-local component as a relative movement base. Replicated vehicles retain ordinary based movement.
    if (JapanNetwork::IsOnline(GetWorld()) && Base)
        if (const auto* Component = Cast<UPrimitiveComponent>(Base->PhysicsObjectOwner.Get()))
            if (const AActor* Owner = Component->GetOwner(); Owner && !Owner->GetIsReplicated() && !Owner->IsNameStableForNetworking())
            {
                Super::SetBase(static_cast<FMovementBaseInterfaceData*>(nullptr), NAME_None, bNotifyActor);
                return;
            }
    Super::SetBase(Base, Bone, bNotifyActor);
}

bool UJapanCharacterMovement::PredictsMoves() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    return Rider && JapanNetwork::IsOnline(GetWorld()) && !Rider->IsNpc() && Rider->GetMoves() &&
        Rider->GetNetworkActivity() == EJapanActivity::OnFoot;
}

uint32 UJapanCharacterMovement::GetActivityEpoch() const
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    return Rider ? Rider->GetActivityEpoch() : 1;
}

void UJapanCharacterMovement::ResetActivityPrediction()
{
    ResetPredictionData_Client(); ResetPredictionData_Server();
    PendingEdges.Reset(); JournalFirstEdge = 1; ProcessedEdge = PendingAcknowledgedEdge = 0;
    HeldButtons = LastServerHolds = 0; bRecoveryQueued = false; bInputPrepared = false; ActiveInput = FJapanMoveInput();
    PendingCheckpoint = FJapanMoveCheckpoint(); PendingCheckpointTime = -1.f;
    LastCustomCorrection = -1.;
    ClearAccumulatedForces(); CurrentRootMotion.Clear();
}

void UJapanCharacterMovement::ReplicateMoveToServer(float Dt, const FVector& NewAcceleration)
{
    const auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    if (Rider && JapanNetwork::IsOnline(GetWorld()) && Rider->GetNetworkActivity() != EJapanActivity::OnFoot)
    {
        // Trusted skating has a separate position/pose stream. Simulate normally without saving or sending CMC moves.
        Acceleration = NewAcceleration.GetClampedToMaxSize(GetMaxAcceleration());
        AnalogInputModifier = ComputeAnalogInputModifier();
        CharacterOwner->ClientRootMotionParams.Clear(); CharacterOwner->SavedRootMotion.Clear();
        PerformMovement(Dt);
        return;
    }
    if (PredictsMoves() && (!Rider->Definition || !Rider->Landscape || !Rider->bReady)) return;
    Super::ReplicateMoveToServer(Dt, NewAcceleration);
}

void UJapanCharacterMovement::ServerMove_PerformMovement(const FCharacterNetworkMoveData& MoveData)
{
    const auto& Custom = static_cast<const FJapanNetworkMoveData&>(MoveData);
    if (JapanNetwork::IsOnline(GetWorld()) && (!PredictsMoves() || Custom.Input.ActivityEpoch != GetActivityEpoch())) return;
    if (PredictsMoves())
    {
        const auto* Rider = CastChecked<AWandererCharacter>(CharacterOwner);
        if (!Rider->Definition || !Rider->Landscape || !Rider->bReady) return;
    }
    Super::ServerMove_PerformMovement(MoveData);
}

FNetworkPredictionData_Client* UJapanCharacterMovement::GetPredictionData_Client() const
{
    if (!ClientPredictionData)
        const_cast<UJapanCharacterMovement*>(this)->ClientPredictionData = new FNetworkPredictionData_Client_Japan(*this);
    return ClientPredictionData;
}

bool UJapanCharacterMovement::QueueMoveButton(FName Button)
{
    if (!PredictsMoves() || bExecutingMove || !CharacterOwner->IsLocallyControlled()) return false;
    const int32 Index = FJapanMoveInput::ButtonIndex(Button);
    if (Index == INDEX_NONE) return false;
    if (Button == TEXT("attack")) HeldButtons |= FJapanMoveInput::AttackHeld;
    if (Button == TEXT("attack_release")) HeldButtons &= ~FJapanMoveInput::AttackHeld;
    if (Button == TEXT("guard")) HeldButtons |= FJapanMoveInput::GuardHeld;
    if (Button == TEXT("guard_release")) HeldButtons &= ~FJapanMoveInput::GuardHeld;
    if (Button == TEXT("jump")) HeldButtons |= FJapanMoveInput::JumpHeld;
    if (Button == TEXT("jump_release")) HeldButtons &= ~FJapanMoveInput::JumpHeld;
    if (Button == TEXT("drop_holds")) HeldButtons = 0;
    if (CastChecked<AWandererCharacter>(CharacterOwner)->IsNetworkActivityPending()) return true;
    if (PendingEdges.Num() < 64) PendingEdges.Add(uint8(Index));
    else
    {
        // Bounded input journal. Hold levels still release safely if a disconnected peer fills it.
        UE_LOG(LogTemp, Warning, TEXT("Network input journal full; awaiting host acknowledgement"));
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->SetSessionStatus(TEXT("Waiting for the host. This action could not be sent yet."));
    }
    return true;
}

FJapanMoveInput UJapanCharacterMovement::ReadMoveInput() const
{
    FJapanMoveInput Input;
    Input.ActivityEpoch = GetActivityEpoch();
    if (const auto* Rider = Cast<AWandererCharacter>(CharacterOwner))
    {
        const bool Menu = Rider->bMenuOpen || Rider->bControlsSuspended;
        const FVector2D Stick = Menu ? FVector2D::ZeroVector : Rider->MoveIntent.GetClampedToMaxSize(1.);
        Input.X = int8(FMath::Clamp(FMath::RoundToInt(Stick.X * 127.), -127, 127));
        Input.Y = int8(FMath::Clamp(FMath::RoundToInt(Stick.Y * 127.), -127, 127));
        Input.Flags = (Rider->bWalk ? FJapanMoveInput::Walk : 0) | (Rider->bJog ? FJapanMoveInput::Jog : 0) |
            (Rider->bSprintHeld ? FJapanMoveInput::Sprint : 0) | (Menu ? FJapanMoveInput::Menu : HeldButtons);
    }
    return Input;
}

FJapanMoveInput UJapanCharacterMovement::ConsumeMoveInput()
{
    FJapanMoveInput Input = ReadMoveInput();
    Input.FirstEdge = JournalFirstEdge;
    const int32 Count = FMath::Min(PendingEdges.Num(), int32(FJapanMoveInput::MaximumEdges));
    for (int32 I = 0; I < Count; ++I) Input.Edges.Add(PendingEdges[I]);
    return Input;
}

void UJapanCharacterMovement::ApplyMoveInput(const FJapanMoveInput& Input)
{
    if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner))
    {
        Rider->MoveIntent = Input.Stick();
        Rider->bWalk = (Input.Flags & FJapanMoveInput::Walk) != 0;
        Rider->bJog = (Input.Flags & FJapanMoveInput::Jog) != 0;
        Rider->bSprintHeld = (Input.Flags & FJapanMoveInput::Sprint) != 0;

    }
}

void UJapanCharacterMovement::AcknowledgeEdges(uint16 Through)
{
    const uint16 Count = uint16(Through - JournalFirstEdge + 1);
    if (Count == 0 || Count > PendingEdges.Num()) return;
    PendingEdges.RemoveAt(0, Count, EAllowShrinking::No);
    JournalFirstEdge = Through + 1;
}

void UJapanCharacterMovement::PerformMovement(float Dt)
{
    if (!PredictsMoves() || Dt <= 0.f) { Super::PerformMovement(Dt); return; }
    auto* Rider = CastChecked<AWandererCharacter>(CharacterOwner);
    if (!Rider->Definition || !Rider->Landscape) { Super::PerformMovement(Dt); return; }
    const FJapanMoveInput LiveInput = ReadMoveInput();
    if (!bInputPrepared)
    {
        FJapanMoveInput Stall;
        Stall.ActivityEpoch = GetActivityEpoch(); Stall.Flags = LastServerHolds;
        SetMoveInput(Rider->IsLocallyControlled() ? ConsumeMoveInput() : Stall);
    }
    TGuardValue<bool> SimulationMenu(Rider->bMenuOpen, (ActiveInput.Flags & FJapanMoveInput::Menu) != 0);
    ApplyMoveInput(ActiveInput);
    TGuardValue<bool> Executing(bExecutingMove, true);
    UBotwMoveSet* Moves = Rider->GetMoves();
    ActiveInput.ApplyNewEdges(ProcessedEdge, [&](uint8 Edge)
    {
        if (!Rider->bReady || Rider->bMenuOpen || Rider->OnVehicle() || Rider->IsZeppelinPassenger()) return;
        const FName Button = FJapanMoveInput::ButtonName(Edge);
        if (Button == TEXT("drop_holds")) Moves->DropHolds();
        else if (!Moves->Press(Button) && Button == TEXT("crouch"))
        {
            if (Rider->bIsCrouched) Rider->UnCrouch(); else Rider->Crouch();
        }
    });
    Moves->ApplyInputHolds(Rider->bMenuOpen ? 0 : ActiveInput.Flags);
    if (Rider->HasAuthority() && Rider->IsLocallyControlled()) AcknowledgeEdges(ProcessedEdge);
    // The clock and action transitions advance once per simulated move, including each replayed move.
    Moves->Advance(Dt);
    const bool CanSprint = !Rider->bWalk && !Rider->bJog && !Rider->bIsCrouched && !Rider->MovementLocked() &&
        !Rider->MoveIntent.IsNearlyZero() && Velocity.Size2D() > 40.f && Moves->CanSprint();
    Rider->Stamina.Tick(Dt, Rider->bSprintHeld, CanSprint, Rider->bMenuOpen || Moves->HoldsStamina());
    const auto* Definition = Rider->Definition.Get();
    MaxWalkSpeed = Definition->UseAuthoredMovement
        ? ((Rider->bWalk || Rider->bJog) ? Definition->WalkSpeed : Rider->Stamina.Sprinting ? Rider->GetSprintSpeed() : Definition->RunSpeed)
        : Rider->bWalk ? Definition->WalkSpeed : Definition->RunSpeed * (Rider->bJog ? 1.f : Rider->Stamina.Sprinting ? 2.5f : 2.f);
    MaxWalkSpeed = Moves->GetMaxWalkSpeed(MaxWalkSpeed);
    const FRotationMatrix Basis(FRotator(0, Rider->GetControlRotation().Yaw, 0));
    const FVector Wish = Basis.GetUnitAxis(EAxis::X) * Rider->MoveIntent.Y + Basis.GetUnitAxis(EAxis::Y) * Rider->MoveIntent.X;
    Acceleration = Rider->bMenuOpen || Rider->MovementLocked() ? FVector::ZeroVector
        : ConstrainInputAcceleration(Wish) * GetMaxAcceleration();
    AnalogInputModifier = ComputeAnalogInputModifier();
    Super::PerformMovement(Dt);
    bInputPrepared = false;
    // Quantized simulation inputs must not rewrite the user's actual stick state or menu after the prediction step.
    if (Rider->IsLocallyControlled() && !bReplaying) ApplyMoveInput(LiveInput);
}

void UJapanCharacterMovement::MoveAutonomous(float Timestamp, float Dt, uint8 Flags, const FVector& Accel)
{
    if (PredictsMoves())
        if (const auto* Data = static_cast<const FJapanNetworkMoveData*>(GetCurrentNetworkMoveData()))
        {
            SetMoveInput(Data->Input);
            LastServerHolds = Data->Input.Flags & (FJapanMoveInput::AttackHeld | FJapanMoveInput::GuardHeld | FJapanMoveInput::JumpHeld | FJapanMoveInput::Menu);
            if (CharacterOwner->Controller) CharacterOwner->Controller->SetControlRotation(Data->ControlRotation);
        }
    Super::MoveAutonomous(Timestamp, Dt, Flags, Accel);
}

bool UJapanCharacterMovement::ClientUpdatePositionAfterServerUpdate()
{
    const FJapanMoveInput LiveInput = ReadMoveInput();
    AController* Controller = CharacterOwner ? CharacterOwner->Controller.Get() : nullptr;
    const FRotator View = Controller ? Controller->GetControlRotation() : FRotator::ZeroRotator;
    TGuardValue<bool> Replay(bReplaying, true);
    const bool Result = Super::ClientUpdatePositionAfterServerUpdate();
    // UE restores pre-replay bWantsToCrouch. Keep the result of the final replayed move instead.
    if (Result && PredictsMoves())
        if (const auto* Data = GetPredictionData_Client_Character(); !Data->SavedMoves.IsEmpty())
            bWantsToCrouch = static_cast<const FSavedMove_Japan&>(*Data->SavedMoves.Last()).PostCrouch;
    ApplyMoveInput(LiveInput);
    if (Controller) Controller->SetControlRotation(View);
    bInputPrepared = false;
    return Result;
}

bool UJapanCharacterMovement::ServerCheckClientError(float Timestamp, float Dt, const FVector& Accel,
    const FVector& ClientLocation, const FVector& RelativeLocation, FMovementBaseInterfaceData* Base, FName Bone, uint8 Mode)
{
    // Non-foot epochs use their own transport. Never correct a skater from a disabled host CMC.
    if (JapanNetwork::IsOnline(GetWorld()) && !PredictsMoves()) return false;
    // Position agreement does not imply stamina, action or traversal agreement. Send an atomic checkpoint at 5 Hz.
    return (PredictsMoves() && GetWorld()->GetTimeSeconds() - LastCustomCorrection >= .2) ||
        Super::ServerCheckClientError(Timestamp, Dt, Accel, ClientLocation, RelativeLocation, Base, Bone, Mode);
}

void UJapanCharacterMovement::ServerMoveHandleClientError(float Timestamp, float Dt, const FVector& Accel,
    const FVector& RelativeLocation, FMovementBaseInterfaceData* Base, FName Bone, uint8 Mode)
{
    if (JapanNetwork::IsOnline(GetWorld()) && !PredictsMoves()) return;
    Super::ServerMoveHandleClientError(Timestamp, Dt, Accel, RelativeLocation, Base, Bone, Mode);
    const auto* Server = GetPredictionData_Server_Character();
    if (!Server || Server->PendingAdjustment.TimeStamp != Timestamp) return;
    PendingCheckpoint = FJapanMoveCheckpoint(); PendingCheckpointTime = Timestamp;
    PendingAcknowledgedEdge = ProcessedEdge;
    if (PredictsMoves() && !Server->PendingAdjustment.bAckGoodMove)
    {
        PendingCheckpoint = CastChecked<AWandererCharacter>(CharacterOwner)->GetMoves()->CaptureNetworkState();

    }
}

void UJapanCharacterMovement::ClientHandleMoveResponse(const FCharacterMoveResponseDataContainer& Response)
{
    const auto& Custom = static_cast<const FJapanMoveResponse&>(Response);
    if (Custom.ActivityEpoch != GetActivityEpoch()) return;
    if (JapanNetwork::IsOnline(GetWorld()) && !PredictsMoves())
    {
        if (Custom.IsCorrection()) UE_LOG(LogTemp, Warning, TEXT("Network movement: ignored CMC correction outside on-foot epoch %u"), GetActivityEpoch());
        return;
    }
    auto* Client = GetPredictionData_Client_Character();
    const FSavedMovePtr PreviousAck = Client->LastAckedMove;
    Super::ClientHandleMoveResponse(Response);
    // A duplicate or stale response must not rewind state. CMC must have accepted this exact correction first.
    if (Client->LastAckedMove == PreviousAck || !Client->LastAckedMove.IsValid() ||
        Client->LastAckedMove->TimeStamp != Response.ClientAdjustment.TimeStamp) return;
    AcknowledgeEdges(Custom.AcknowledgedEdge);
    if (!Custom.IsCorrection()) return;
    const auto& Saved = static_cast<const FSavedMove_Japan&>(*Client->LastAckedMove);
    const FJapanMoveCheckpoint& State = Custom.bHasCheckpoint ? Custom.Checkpoint : Saved.PostState;
    if (!Custom.bHasCheckpoint && State.Bytes.IsEmpty())
    {
        UE_LOG(LogTemp, Warning, TEXT("Network correction has no traversal snapshot; retaining current traversal state"));
        return;
    }
    ProcessedEdge = Custom.bHasCheckpoint ? Custom.AcknowledgedEdge : Saved.PostEdge;
    auto* Rider = Cast<AWandererCharacter>(CharacterOwner);
    TGuardValue<bool> Replay(bReplaying, true);
    if (PredictsMoves() && (!Rider || !Rider->GetMoves() || !Rider->GetMoves()->ApplyNetworkState(State)))
    {
        UE_LOG(LogTemp, Error, TEXT("Network movement correction rejected: invalid traversal checkpoint"));
        if (auto* Session = GetWorld()->GetGameInstance<UJapanGameInstance>())
            Session->ReturnWithError(TEXT("The host sent incompatible movement state. Rejoin using the same build."));
    }
}

void UJapanCharacterMovement::SendClientAdjustment()
{
    const float Before = ServerLastClientAdjustmentTime;
    Super::SendClientAdjustment();
    // Capture is not delivery: UE may throttle or replace pending responses within a frame.
    if (ServerLastClientAdjustmentTime != Before) LastCustomCorrection = ServerLastClientAdjustmentTime;
}

bool UJapanCharacterMovement::QueueAuthoritativeRecovery(FVector Shore, float Yaw, float Damage)
{
    if (!CharacterOwner || !CharacterOwner->HasAuthority() || bRecoveryQueued) return false;
    bRecoveryQueued = true;
    const uint32 Epoch = GetActivityEpoch();
    // Travel resets prediction data. Defer until no CMC server move or replay holds pointers into it.
    GetWorld()->GetTimerManager().SetTimerForNextTick(FTimerDelegate::CreateWeakLambda(this, [this, Shore, Yaw, Damage, Epoch]()
    {
        bRecoveryQueued = false;
        if (Epoch == GetActivityEpoch())
            if (auto* Rider = Cast<AWandererCharacter>(CharacterOwner); Rider && Rider->TravelTo(Shore, Yaw, TEXT("swim recovery"), 100.f))
                if (auto* Sword = Rider->GetSword()) Sword->Health = FMath::Max(1.f, Sword->Health - Damage);
    }));
    return true;
}
