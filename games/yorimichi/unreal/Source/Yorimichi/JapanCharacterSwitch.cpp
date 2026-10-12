#include "JapanSession.h"
#include "JapanNetwork.h"
#include "JapanCharacterMovement.h"
#include "JapanCombatResolver.h"
#include "PlayableCharacter.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "WandererSword.h"
#include "AdventureNetworkState.h"
#include "BikeComponent.h"
#include "SailboatComponent.h"
#include "SkateComponent.h"
#include "ZeppelinService.h"
#include "JapanWorld.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Serialization/MemoryWriter.h"
#include "Engine/World.h"

bool AJapanPlayerController::RequestCharacter(const FString& Name)
{
    if (!IsLocalController()) return false;
    auto* From = Cast<AWandererCharacter>(GetPawn());
    if (!From || !JapanNetwork::IsPlayableRider(Name))
    { ClientCharacterResult_Implementation(TEXT("This character is unavailable in this build.")); return false; }
    ServerRequestCharacter(Name, From);
    return true;
}

void AJapanPlayerController::ServerRequestCharacter_Implementation(const FString& Name, AWandererCharacter* ExpectedPawn)
{
    if (!ExpectedPawn || GetPawn() != ExpectedPawn || Name.Len() > 64 || !JapanNetwork::IsPlayableRider(Name))
    { ClientCharacterResult(TEXT("The character request is no longer valid.")); return; }
    if (FPlayableCharacter::NameOf(ExpectedPawn) == Name) { ClientCharacterResult(FString()); return; }
    PendingCharacter = Name; CharacterSource = ExpectedPawn; CharacterRequestedAt = GetWorld()->GetTimeSeconds();
}

void AJapanPlayerController::ClientCharacterResult_Implementation(const FString& Error)
{
    if (auto* Session = GetGameInstance<UJapanGameInstance>())
        Session->SetSessionStatus(Error.IsEmpty() ? TEXT("Character changed.") : Error);
}

void AJapanPlayerController::FinishCharacterSwitch()
{
    auto* From = CharacterSource.Get();
    auto* State = GetPlayerState<AJapanPlayerState>();
    const auto* Choice = FPlayableCharacter::Find(PendingCharacter);
    if (!State || !From || GetPawn() != From || !Choice || !Choice->Built() || !From->Moves || !From->Landscape)
    { PendingCharacter.Reset(); ClientCharacterResult(TEXT("The character could not be changed.")); return; }
    auto* Movement = CastChecked<UJapanCharacterMovement>(From->GetCharacterMovement());
    auto* Combat = GetWorld()->GetSubsystem<UJapanCombatResolver>();
    if (!From->IsReady() || Movement->IsExecutingMove() || Movement->IsReplaying()) return;
    // Keep a requested swap queued while the existing contact/reaction resolves. Do not
    // discard damage or grant fresh immunity by replacing its victim's pawn early.
    if (Combat->HasPending(From))
    {
        if (GetWorld()->GetTimeSeconds() - CharacterRequestedAt < 1.) return;
        Combat->Flush(From);
        if (Movement->HasScheduledReaction()) Movement->RecoverScheduledReactions(From->GetActivityEpoch(), false);
    }
    FAdventureNetworkState Foot; Foot.Capture(*From->Moves);
    FName Action = From->AnimationAction;
    const auto Activity = From->NetworkActivity.Kind;
    FJapanBikeState Bike = From->Bike->CaptureNetworkState();
    FJapanSailState Sail = From->Sailboat->CaptureNetworkState();
    const FVector Feet = From->GetActorLocation() - FVector(0,0,From->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const FRotator Facing = From->GetActorRotation(), View = GetControlRotation();
    const FString Name = Choice->Name;
    const bool Falling = Movement->IsFalling();
    const FVector Velocity = Movement->Velocity;
    auto* To = GetWorld()->SpawnActorDeferred<AWandererCharacter>(Choice->Class(), FTransform(Facing,Feet),
        this, nullptr, ESpawnActorCollisionHandlingMethod::AlwaysSpawn);
    if (!To) { PendingCharacter.Reset(); ClientCharacterResult(TEXT("Could not create the selected character.")); return; }
    To->bSwitchedIn = true; To->ConfigureNetworkRider(Name, From->GetNetworkShield());
    To->FinishSpawning(FTransform(Facing, Feet + FVector(0,0,To->GetCapsuleComponent()->GetScaledCapsuleHalfHeight())));
    To->EnterWorld(From->Landscape);
    if (!To->Moves || !To->Definition)
    { To->Destroy(); PendingCharacter.Reset(); ClientCharacterResult(TEXT("The selected character's assets are incomplete.")); return; }
    // Fit authored offsets to the replacement body; world-space paths and gameplay
    // clocks survive, but another skeleton's mesh base must never be transplanted.
    Foot.MeshBase = To->Moves->MeshBase; Foot.MeshBaseRotation = To->Moves->MeshBaseRotation;
    if (!Action.IsNone() && !To->Definition->FindAction(Action))
    { Action = NAME_None; Foot.bDriving = false; Foot.DriveVelocity = FVector::ZeroVector; }
    TArray<uint8> Bytes; FMemoryWriter Writer(Bytes, true);
    if (!Foot.Serialize(Writer) || Bytes.Num() > FJapanMoveCheckpoint::MaximumBytes)
    { To->Destroy(); PendingCharacter.Reset(); ClientCharacterResult(TEXT("The current character state could not be transferred.")); return; }
    To->NetworkHealth = From->Sword->GetHealth(); To->NetworkHitsTaken = From->Sword->HitsTaken();
    To->Sword->ApplyNetworkHealth(To->NetworkHealth, To->NetworkHitsTaken);
    To->NetworkParkedBike = From->NetworkParkedBike;
    To->NetworkActivity = From->NetworkActivity;
    ++To->NetworkActivity.Epoch; if (!To->NetworkActivity.Epoch) ++To->NetworkActivity.Epoch;
    To->NetworkActivity.Location = To->GetActorLocation(); To->NetworkActivity.Rotation = Facing;
    To->NetworkActivity.Velocity = Velocity; To->NetworkActivity.bFalling = Falling;
    To->NetworkActivity.Bike = Bike; To->NetworkActivity.Sail = Sail;
    To->NetworkActivity.bFootReaction = false; To->NetworkActivity.bCharacterReplacement = true;
    To->NetworkActivity.ReplacementMovementMode = Movement->PackNetworkMovementMode();
    To->NetworkActivity.bReplacementCrouched = From->bIsCrouched;
    To->NetworkActivity.SkateDeck = From->SkateRide->GetDeckWorld();
    if (Activity == EJapanActivity::Skate) To->NetworkActivity.Velocity = From->SkateRide->IsOnBoard()
        ? From->SkateRide->GetBoardVelocity() : Velocity;
    To->NetworkActivity.FootBytes = MoveTemp(Bytes); To->NetworkActivity.FootAction = Action;
    To->bNetworkMovementReady = true; To->ReadyTime = 2.f;
    if (Activity == EJapanActivity::Zeppelin)
    {
        auto* Ship = From->GetZeppelin();
        if (!Ship || !Ship->ReplacePassenger(From,To))
        { To->Destroy(); PendingCharacter.Reset(); ClientCharacterResult(TEXT("Could not transfer the zeppelin seat.")); return; }
    }
    PendingCharacter.Reset(); CharacterSource.Reset();
    From->Leave();
    From->SetActorEnableCollision(false);
    UnPossess(); Possess(To); SetControlRotation(View);
    To->AppliedActivityEpoch = 0; To->bReady = true; To->OnRep_NetworkActivity();
    // The host's remote pawn also needs the simulation snapshot; ordinary foot
    // reaction handoffs only restore on the owner because proxies use presentation.
    To->NetworkAvatar = To->Moves->CapturePresentation();
    State->RiderName = Name; State->ForceNetUpdate(); To->ForceNetUpdate();
    From->Destroy();
    ClientCharacterResult(FString());
    UE_LOG(LogTemp,Display,TEXT("NETWORK character switch player=%s rider=%s activity=%u epoch=%u health=%.1f"),
        *State->SessionPlayerId,*Name,uint8(Activity),To->GetActivityEpoch(),To->NetworkHealth);
}
