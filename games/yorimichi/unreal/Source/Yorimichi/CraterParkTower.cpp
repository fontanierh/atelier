#include "CraterParkTower.h"
#include "AtelierData.h"
#include "LiveLibrary.h"
#include "SkateComponent.h"
#include "WandererCharacter.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Engine/World.h"
#include "GameFramework/PlayerController.h"

namespace
{
    // The build's own check (spawns.py GROUND_TOLERANCE, CLEARANCE), in cm.
    constexpr float GroundTolerance = 50.f;
    constexpr float Clearance = 200.f;
    int32 Last = 0;
    bool bLines = false;

    bool ReadStart(const TSharedPtr<FJsonObject>& Spawn, FCraterParkStart& Out)
    {
        const TArray<TSharedPtr<FJsonValue>>* At = nullptr;
        double Yaw = 0.;
        if (!Spawn.IsValid() || !Spawn->TryGetArrayField(TEXT("location_cm"), At) || At->Num() < 3 || !Spawn->TryGetNumberField(TEXT("yaw_deg"), Yaw))
            return false;
        Out.Ground = FVector((*At)[0]->AsNumber(), (*At)[1]->AsNumber(), (*At)[2]->AsNumber());
        Out.Yaw = float(Yaw);
        return true;
    }

    TArray<FCraterParkStart> Load()
    {
        TArray<FCraterParkStart> Result;
        const TSharedPtr<FJsonObject> Park = AtelierReadJson(AtelierDataPath(TEXT("craterpark/park.json")));
        if (!Park.IsValid()) return Result;
        const TArray<TSharedPtr<FJsonValue>>* Lines = nullptr;
        if (Park->TryGetArrayField(TEXT("lines"), Lines))
            for (const TSharedPtr<FJsonValue>& Value : *Lines)
            {
                const TSharedPtr<FJsonObject>* Line = nullptr;
                const TSharedPtr<FJsonObject>* Spawn = nullptr;
                FCraterParkStart Start;
                if (!Value->TryGetObject(Line) || !(*Line)->TryGetObjectField(TEXT("spawn"), Spawn) || !ReadStart(*Spawn, Start)) continue;
                (*Line)->TryGetStringField(TEXT("key"), Start.Key);
                if (!(*Line)->TryGetStringField(TEXT("name"), Start.Name) || Start.Name.IsEmpty()) Start.Name = Start.Key;
                Result.Add(Start);
            }
        bLines = !Result.IsEmpty();
        // An older park.json (r4, or a layout without lines): its one marked drop-in.
        const TSharedPtr<FJsonObject>* Spawn = nullptr;
        FCraterParkStart Start;
        if (!bLines && Park->TryGetObjectField(TEXT("spawn"), Spawn) && ReadStart(*Spawn, Start))
        {
            Start.Key = TEXT("drop-in"); Start.Name = TEXT("Drop-in");
            Result.Add(Start);
        }
        UE_LOG(LogTemp, Display, TEXT("Crater Park tower: %d starts%s"), Result.Num(), bLines ? TEXT("") : TEXT(" (the drop-in; park.json has no lines)"));
        return Result;
    }

    bool CanUseHoist(const AWandererCharacter* Pawn, FVector& OutFeet)
    {
        if (!Pawn || !Pawn->IsReady() || Pawn->IsCinematic() || Pawn->AreControlsSuspended() ||
            Pawn->OnVehicle() || Pawn->IsZeppelinPassenger() || (Pawn->GetSkate() && Pawn->GetSkate()->IsRiding()))
            return false;
        const float Half = Pawn->GetCapsuleComponent() ? Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
        OutFeet = Pawn->GetActorLocation() - FVector(0.f, 0.f, Half);
        return true;
    }

    void FadeCamera(AWandererCharacter* Pawn)
    {
        if (!Pawn) return;
        if (APlayerController* PC = Cast<APlayerController>(Pawn->GetController()))
            if (PC->PlayerCameraManager)
                PC->PlayerCameraManager->StartCameraFade(1.f, 0.f, 0.45f, FLinearColor::Black, false, false);
    }
}

const TArray<FCraterParkStart>& CraterParkTower::Starts()
{
    static const TArray<FCraterParkStart> All = Load();
    return All;
}

bool CraterParkTower::HasLines()
{
    Starts();
    return bLines;
}

int32 CraterParkTower::LastStart()
{
    return Starts().IsValidIndex(Last) ? Last : 0;
}

bool CraterParkTower::Return(AWandererCharacter* Pawn, int32 Index)
{
    if (!Pawn || !Pawn->GetWorld() || Pawn->IsCinematic() || Pawn->AreControlsSuspended()) return false;
    const TArray<FCraterParkStart>& All = Starts();
    if (!All.IsValidIndex(Index)) { ULiveLibrary::Say(TEXT("Crater Park's tower is not in this build.")); return false; }
    const FCraterParkStart& Start = All[Index];
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(CraterParkTower), false, Pawn);
    const bool bHit = Pawn->GetWorld()->LineTraceSingleByChannel(Hit, Start.Ground + FVector(0, 0, Clearance), Start.Ground - FVector(0, 0, Clearance), ECC_Visibility, Params);
    if (!bHit || FMath::Abs(Hit.ImpactPoint.Z - Start.Ground.Z) > GroundTolerance)
    {
        UE_LOG(LogTemp, Warning, TEXT("Crater Park tower: %s at %s has no ground within %.0f cm (%s)"), *Start.Name, *Start.Ground.ToString(), GroundTolerance,
            bHit ? *FString::Printf(TEXT("hit at z %.0f"), Hit.ImpactPoint.Z) : TEXT("no hit"));
        ULiveLibrary::Say(FString::Printf(TEXT("%s: the tower's ground is not there yet. Try again in a moment."), *Start.Name));
        return false;
    }
    if (!Pawn->TravelTo(Hit.ImpactPoint, Start.Yaw, *(TEXT("Crater Park tower, ") + Start.Name), 30.f)) return false;
    Last = Index;
    FadeCamera(Pawn);
    ULiveLibrary::Say(Start.Name + TEXT(": Triangle / Y or B for the board, then roll in."));
    return true;
}

bool CraterParkTower::ReturnDown(AWandererCharacter* Pawn)
{
    if (!Pawn || !Pawn->GetWorld() || Pawn->IsCinematic() || Pawn->AreControlsSuspended()) return false;
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(CraterParkTowerDown), false, Pawn);
    const bool bHit = Pawn->GetWorld()->LineTraceSingleByChannel(
        Hit, HoistLandingGround + FVector(0, 0, Clearance), HoistLandingGround - FVector(0, 0, Clearance), ECC_Visibility, Params);
    if (!bHit || FMath::Abs(Hit.ImpactPoint.Z - HoistLandingGround.Z) > GroundTolerance)
    {
        ULiveLibrary::Say(TEXT("Crater Park hoist: the rim landing ground is not there yet. Try again in a moment."));
        return false;
    }
    if (!Pawn->TravelTo(Hit.ImpactPoint, 0.f, TEXT("Crater Park tower, rim landing"), 30.f)) return false;
    FadeCamera(Pawn);
    ULiveLibrary::Say(TEXT("Rim landing: paths east to Southeast / Floor Rim, or north-west along the rim."));
    return true;
}

bool CraterParkTower::CanRideUp(const AWandererCharacter* Pawn)
{
    FVector Feet = FVector::ZeroVector;
    if (!CanUseHoist(Pawn, Feet)) return false;
    return FVector::Dist2D(Feet, HoistPortalGround) <= HoistInteractRadiusCm &&
           FMath::Abs(Feet.Z - HoistPortalGround.Z) <= HoistInteractRadiusCm;
}

bool CraterParkTower::CanRideDown(const AWandererCharacter* Pawn)
{
    FVector Feet = FVector::ZeroVector;
    if (!CanUseHoist(Pawn, Feet) || FMath::Abs(Feet.Z - HoistDeckZCm) > HoistInteractRadiusCm) return false;
    for (const FCraterParkStart& Start : Starts())
        if (FVector::Dist2D(Feet, Start.Ground) <= HoistInteractRadiusCm)
            return true;
    return FVector::Dist2D(Feet, FVector(128481.52f, -249700.96f, 85798.6f)) <= HoistInteractRadiusCm ||
           FVector::Dist2D(Feet, FVector(130080.f, -249120.f, 85833.f)) <= HoistInteractRadiusCm;
}

FString CraterParkTower::Hint(const AWandererCharacter* Pawn)
{
    if (CanRideUp(Pawn)) return TEXT("Ride up");
    if (CanRideDown(Pawn)) return TEXT("Ride down");
    return FString();
}

bool CraterParkTower::TryInteract(AWandererCharacter* Pawn)
{
    if (CanRideUp(Pawn)) return Return(Pawn, LastStart());
    if (CanRideDown(Pawn)) return ReturnDown(Pawn);
    return false;
}
