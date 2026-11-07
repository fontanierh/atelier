#include "PlayableCharacter.h"
#include "JapanNetwork.h"
#include "JapanSession.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

TArray<FPlayableCharacter>& FPlayableCharacter::Registry()
{
    static TArray<FPlayableCharacter> Characters;
    static bool bScanned = false;
    if (!bScanned)
    {
        bScanned = true;   // first: Scan itself reads the registry
        Scan();
    }
    return Characters;
}

const TArray<FPlayableCharacter>& FPlayableCharacter::All() { return Registry(); }

const FPlayableCharacter* FPlayableCharacter::Find(const FString& Name)
{
    return Name.IsEmpty() ? nullptr : Registry().FindByPredicate([&](const FPlayableCharacter& C)
        { return C.Name == Name || C.Aliases.Contains(Name); });
}

const FPlayableCharacter& FPlayableCharacter::Default()
{
    if (const FPlayableCharacter* Character = Registry().FindByPredicate([](const FPlayableCharacter& C) { return C.bDefault; }))
        return *Character;
    // None built yet (a fresh checkout): no pawn class, and the game says which step makes one.
    static const FPlayableCharacter None = []
    {
        UE_LOG(LogTemp, Error, TEXT("No default playable character: build the pawn step (unreal.<key>_pawn) of the one whose [game] is the default"));
        FPlayableCharacter Character;
        Character.Class = [] { return static_cast<UClass*>(nullptr); };
        Character.IsBuilt = [] { return false; };
        return Character;
    }();
    return None;
}

FString FPlayableCharacter::Requested()
{
    FString Name;
    if (!FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) || Name.IsEmpty()) return FString();
    const FPlayableCharacter* Character = Find(Name);
    if (Character && Character->Built()) return Character->Name;
    UE_LOG(LogTemp, Warning, TEXT("Playable character %s is unavailable"), *Name);
    return FString();
}

UClass* FPlayableCharacter::PawnOverride()
{
    const FPlayableCharacter* Character = Find(Requested());
    return Character ? Character->Class() : nullptr;
}

TArray<FString> FPlayableCharacter::Available()
{
    TArray<FString> Names;
    for (const FPlayableCharacter& Character : All())
        if (!Character.bDefault && Character.Built()) Names.Add(Character.Name);
    return Names;
}

FString FPlayableCharacter::NameOf(const AWandererCharacter* Character)
{
    const FString Name = Character ? Character->GetPlayableName() : FString();
    return Name.IsEmpty() ? Default().Name : Name;
}

AWandererCharacter* FPlayableCharacter::SwitchPlayer(AWandererCharacter* From, const FString& Name)
{
    if (From && JapanNetwork::IsOnline(From->GetWorld()))
    {
        if (auto* Controller = Cast<AJapanPlayerController>(From->GetController())) Controller->RequestCharacter(Name);
        return From; // The persistent controller commits the host-approved replacement asynchronously.
    }
    APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
    UWorld* World = From ? From->GetWorld() : nullptr;
    const FPlayableCharacter* Character = Find(Name);
    if (!PC || !World || !From->IsReady() || From->IsZeppelinPassenger() || !Character || Character->Name == NameOf(From) || !Character->Built())
    {
        UE_LOG(LogTemp, Warning, TEXT("Character switch to %s refused"), *Name);
        return nullptr;
    }
    const FRotator Look = PC->GetControlRotation();
    const FVector Feet = From->GetActorLocation() - FVector(0, 0, From->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
    const FRotator Facing(0, From->GetActorRotation().Yaw, 0);
    From->Leave();
    From->SetActorEnableCollision(false);
    AWandererCharacter* To = World->SpawnActorDeferred<AWandererCharacter>(Character->Class(), FTransform(Facing, Feet), nullptr, nullptr, ESpawnActorCollisionHandlingMethod::AdjustIfPossibleButAlwaysSpawn);
    if (!To) { From->SetActorEnableCollision(true); return nullptr; }
    To->bSwitchedIn = true;
    To->EnterWorld(From->GetLandscape());
    To->FinishSpawning(FTransform(Facing, Feet + FVector(0, 0, To->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f)));
    PC->UnPossess();
    PC->Possess(To);
    PC->SetControlRotation(Look);
    From->Destroy();
    UE_LOG(LogTemp, Display, TEXT("Character switch: now playing %s"), *Name);
    return To;
}
