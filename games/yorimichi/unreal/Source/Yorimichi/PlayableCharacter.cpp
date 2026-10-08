#include "PlayableCharacter.h"
#include "JapanNetwork.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"

TArray<FPlayableCharacter>& FPlayableCharacter::Registry()
{
    static TArray<FPlayableCharacter> Characters;
    return Characters;
}

FPlayableCharacter::FRegister::FRegister(FPlayableCharacter Character)
{
    TArray<FPlayableCharacter>& Characters = Registry();
    check(!Characters.ContainsByPredicate([&](const FPlayableCharacter& C) { return C.Name == Character.Name; }));
    Characters.Add(MoveTemp(Character));
    // Static registration runs in no set order across files: keep them by name.
    Characters.Sort([](const FPlayableCharacter& A, const FPlayableCharacter& B) { return A.Name < B.Name; });
}

const TArray<FPlayableCharacter>& FPlayableCharacter::All() { return Registry(); }

const FPlayableCharacter* FPlayableCharacter::Find(const FString& Name)
{
    return Name.IsEmpty() ? nullptr : Registry().FindByPredicate([&](const FPlayableCharacter& C) { return C.Name == Name; });
}

const FPlayableCharacter& FPlayableCharacter::Default()
{
    const FPlayableCharacter* Character = Registry().FindByPredicate([](const FPlayableCharacter& C) { return C.bDefault; });
    check(Character);
    return *Character;
}

FString FPlayableCharacter::Requested()
{
    FString Name;
    if (!FParse::Value(FCommandLine::Get(), TEXT("rider="), Name) || Name.IsEmpty()) return FString();
    const FPlayableCharacter* Character = Find(Name);
    if (Character && Character->IsRequestable() && Character->Built()) return Name;
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
    const FPlayableCharacter& Main = Default();
    for (const FPlayableCharacter& Character : All())
        if (!Character.bDefault && Character.Name != Main.MoveSet && Character.Built()) Names.Add(Character.Name);
    return Names;
}

FString FPlayableCharacter::NameOf(const AWandererCharacter* Character)
{
    const FString Name = Character ? Character->GetPlayableName() : FString();
    return Name.IsEmpty() ? Default().Name : Name;
}

AWandererCharacter* FPlayableCharacter::SwitchPlayer(AWandererCharacter* From, const FString& Name)
{
    if (From && JapanNetwork::IsOnline(From->GetWorld())) return nullptr;
    APlayerController* PC = From ? Cast<APlayerController>(From->GetController()) : nullptr;
    UWorld* World = From ? From->GetWorld() : nullptr;
    const FPlayableCharacter* Character = Find(Name);
    if (!PC || !World || !From->IsReady() || From->IsZeppelinPassenger() || Name == NameOf(From) || !Character || !Character->Built())
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
    if (Character->Prepare) Character->Prepare(To, Name);
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
