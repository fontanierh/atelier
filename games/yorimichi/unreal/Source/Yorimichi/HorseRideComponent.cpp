#include "HorseRideComponent.h"
#include "AtelierFX.h"
#include "BotwRider.h"
#include "CairoCharacter.h"
#include "Hippodrome.h"
#include "WandererCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Engine/World.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Sound/SoundBase.h"

namespace
{
    // cm/s: the roster horse's own gaits (speeds_cm at rate 1), so each plays near its natural rate.
    constexpr float WalkSpeed = 190.f, TrotSpeed = 440.f, GallopSpeed = 830.f, SpurSpeed = 1040.f;
    constexpr float SpurSeconds = 1.8f, SpurRefillSeconds = 4.f, OffSpeed = 250.f, Reach = 1500.f;
    // The horse is 2.7 m long round the rider's capsule: its nose and tail are this far ahead of and behind the feet.
    constexpr float HalfLength = 120.f;
}

UHorseRideComponent::UHorseRideComponent() { PrimaryComponentTick.bCanEverTick = true; }

void UHorseRideComponent::Initialize(AWandererCharacter* Character)
{
    Rider = Character;
    // Speed and heading go in before the movement component moves the capsule; the horse follows after it.
    Character->GetCharacterMovement()->AddTickPrerequisiteComponent(this);
    for (int32 I = 1; I <= 12; ++I)
    {
        const FString Name = FString::Printf(TEXT("HR_Hoof_%02d"), I);
        USoundBase* Sound = LoadObject<USoundBase>(nullptr, *FString::Printf(TEXT("/Game/Audio/Hippodrome/%s.%s"), *Name, *Name));
        if (!Sound) break;
        Hooves.Add(Sound);
    }
    SpurSound = LoadObject<USoundBase>(nullptr, TEXT("/Game/Audio/Hippodrome/HR_Spur_01.HR_Spur_01"));
}

bool UHorseRideComponent::IsAvailable() const
{
    const FString Name = RiderFor(Rider);
    return !Name.IsEmpty() && FHorseSpec::Find(ChosenHorse()) != nullptr;
}

AHippodromeFigure* UHorseRideComponent::GetFigure() const { return Figure.Get(); }

FString UHorseRideComponent::RiderFor(const AWandererCharacter* Character)
{
    if (!Character) return FString();
    if (Character->IsA<ACairoCharacter>()) return FHorseSpec::PlayerRider();
    const FString Name = TEXT("Rider") + ABotwRider::Requested();
    return FHorseSpec::Find(Name) ? Name : FString();
}

FString UHorseRideComponent::ChosenHorse()
{
    // The horse last raced at the hippodrome (AHorseRace::SaveResults), else Momo.
    FString Text, Horse; TSharedPtr<FJsonObject> Root;
    if (FFileHelper::LoadFileToString(Text, *(FPaths::ProjectSavedDir() / TEXT("hippodrome.json"))) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) && Root.IsValid() &&
        Root->TryGetStringField(TEXT("horse"), Horse) && FHorseSpec::Find(Horse)) return Horse;
    return TEXT("HorseRoan");
}

FVector UHorseRideComponent::Feet() const
{
    return Rider->GetActorLocation() - FVector(0, 0, Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight());
}

bool UHorseRideComponent::ClearFor(const FVector& Ground, float Yaw) const
{
    // Room for the horse's body, and ground under its forelegs and hind legs.
    const FQuat R = FRotator(0, Yaw, 0).Quaternion();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseClear), false, Rider);
    if (GetWorld()->OverlapBlockingTestByChannel(Ground + FVector(0, 0, 115), R, ECC_WorldStatic, FCollisionShape::MakeBox(FVector(HalfLength, 32, 50)), Q)) return false;
    for (const float Along : { HalfLength * .8f, -HalfLength * .8f })
    {
        const FVector P = Ground + R.RotateVector(FVector(Along, 0, 0)); FHitResult H;
        if (!GetWorld()->LineTraceSingleByChannel(H, P + FVector(0, 0, 80), P - FVector(0, 0, 70), ECC_Visibility, Q)) return false;
    }
    return true;
}

bool UHorseRideComponent::Toggle()
{
    if (!Rider) return false;
    if (bRiding)
    {
        if (Speed > OffSpeed) { Hint = TEXT("Slow to a walk to get off"); return false; }
        Dismount(true);
        return true;
    }
    const FString RiderName = RiderFor(Rider);
    if (RiderName.IsEmpty()) { Hint = TEXT("Only Cairo and Link ride the horses"); return false; }
    if (!FHorseSpec::Find(ChosenHorse())) { Hint = TEXT("The horses are not installed"); return false; }
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    if (!M->IsMovingOnGround() || M->IsSwimming() || Rider->bIsCrouched) { Hint = TEXT("Stand on firm ground to call the horse"); return false; }
    // The horse left standing nearby takes him back; anywhere else the chosen horse is brought round beside him.
    AHippodromeFigure* Horse = Figure.Get();
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    if (Horse && FVector::Dist2D(Horse->GetActorLocation(), Feet()) < Reach && Horse->GetRider().Name == RiderName)
    {
        const FVector At = Horse->GetActorLocation() + FVector(0, 0, Half + 2.f);
        FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseMount), false, Rider);
        if (!GetWorld()->OverlapBlockingTestByChannel(At, FQuat::Identity, ECC_Pawn, Rider->GetCapsuleComponent()->GetCollisionShape(), Q))
        {
            Rider->SetActorLocationAndRotation(At, FRotator(0, Horse->GetActorRotation().Yaw, 0), false, nullptr, ETeleportType::TeleportPhysics);
            Mount(Horse);
            return true;
        }
    }
    if (Horse) Horse->Destroy();
    Figure.Reset();
    const FString Body = ChosenHorse();
    bool bFound = false; float Yaw = Rider->GetActorRotation().Yaw;
    for (const float Swing : { 0.f, -45.f, 45.f, -90.f, 90.f, 180.f })
        if (ClearFor(Feet(), Rider->GetActorRotation().Yaw + Swing)) { Yaw = Rider->GetActorRotation().Yaw + Swing; bFound = true; break; }
    if (!bFound) { Hint = TEXT("Find some open ground for the horse"); return false; }
    Horse = AHippodromeFigure::Spawn(GetWorld(), Body, RiderName, Feet(), Yaw);
    if (!Horse || !Horse->HasRider()) { if (Horse) Horse->Destroy(); Hint = TEXT("The horse would not come"); return false; }
    Figure = Horse;
    HorseName = Body;
    Rider->SetActorRotation(FRotator(0, Yaw, 0));
    Mount(Horse);
    return true;
}

void UHorseRideComponent::Mount(AHippodromeFigure* Horse)
{
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    M->StopMovementImmediately();
    SavedFriction = M->GroundFriction; SavedBraking = M->BrakingDecelerationWalking;
    M->GroundFriction = 0.f; M->BrakingDecelerationWalking = 0.f;
    Rider->SetActorHiddenInGame(true);
    Horse->GetRiderMesh()->SetVisibility(true);
    HorseName = Horse->GetBody().Name;
    bRiding = true; Speed = Steering = Pitch = SpurLeft = RearLeft = StrideClock = 0.f; Gait = NAME_None;
    Horse->Gait(TEXT("idle"), TEXT("idle"), 1.f);
    Horse->PlayRiderOnce(TEXT("notice"));   // a pat on the neck
    Hint = TEXT("Riding");
    Pose(0.f);
}

void UHorseRideComponent::Dismount(bool bPark)
{
    if (!bRiding) return;
    bRiding = false;
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    M->GroundFriction = SavedFriction; M->BrakingDecelerationWalking = SavedBraking;
    M->StopMovementImmediately();
    Rider->SetActorHiddenInGame(false);
    Speed = Steering = 0.f; Gait = NAME_None;
    AHippodromeFigure* Horse = Figure.Get();
    if (!bPark || !Horse) { if (Horse) Horse->Destroy(); Figure.Reset(); Hint = TEXT("H horse"); return; }
    // He steps down on the horse's left (the near side), or its right when the left is blocked; the horse stays.
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector Right = FRotator(0, Horse->GetActorRotation().Yaw, 0).RotateVector(FVector::RightVector);
    FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseStepOff), false, Rider);
    for (const float Side : { -1.f, 1.f })
    {
        // On a slope the ground beside the horse is higher or lower than under it: stand on what is there.
        FVector At = Horse->GetActorLocation() + Right * Side * 85.f; FHitResult Ground;
        if (GetWorld()->LineTraceSingleByChannel(Ground, At + FVector(0, 0, 80), At - FVector(0, 0, 120), ECC_Visibility, Q)) At.Z = Ground.ImpactPoint.Z;
        At.Z += Half + 2.f;
        if (!GetWorld()->OverlapBlockingTestByChannel(At, FQuat::Identity, ECC_Pawn, Rider->GetCapsuleComponent()->GetCollisionShape(), Q))
        { Rider->SetActorLocation(At, false, nullptr, ETeleportType::TeleportPhysics); break; }
    }
    M->bForceNextFloorCheck = true;
    Horse->SetActorRotation(FRotator(0, Horse->GetActorRotation().Yaw, 0));
    Horse->GetRiderMesh()->SetVisibility(false);
    Horse->Gait(TEXT("idle"), TEXT("idle"), 1.f);
    Hint = TEXT("H get back on");
}

void UHorseRideComponent::StowImmediately()
{
    Dismount(false);
    if (AHippodromeFigure* Horse = Figure.Get()) Horse->Destroy();
    Figure.Reset();
    Hint = TEXT("H horse");
}

void UHorseRideComponent::EndPlay(const EEndPlayReason::Type Reason)
{
    if (AHippodromeFigure* Horse = Figure.Get()) Horse->Destroy();
    Super::EndPlay(Reason);
}

void UHorseRideComponent::SetInput(FVector2D Intent, bool bGallopHeld, bool bWalkHeld, bool bMenuOpen)
{
    Input = bMenuOpen ? FVector2D::ZeroVector : Intent; bGallop = bGallopHeld; bWalk = bWalkHeld; bMenu = bMenuOpen;
}

bool UHorseRideComponent::Spur()
{
    AHippodromeFigure* Horse = Figure.Get();
    if (!bRiding || !Horse || bMenu || RearLeft > 0.f) return false;
    if (Spurs <= 0) { Hint = TEXT("No spurs left: let the horse breathe"); return false; }
    --Spurs; SpurLeft = SpurSeconds;
    Horse->PlayRiderOnce(TEXT("spur"));
    if (SpurSound)
    {
        UGameplayStatics::PlaySoundAtLocation(this, SpurSound, Feet(), .7f);
        FAtelierAudioLog::Record(SpurSound, Feet(), .7f, 1.f, false);
    }
    return true;
}

bool UHorseRideComponent::Rear()
{
    AHippodromeFigure* Horse = Figure.Get();
    if (!bRiding || !Horse || bMenu || Speed > 60.f || RearLeft > 0.f) return false;
    RearLeft = Horse->PlayBody(TEXT("rear"), false);
    Horse->PlayRiderOnce(TEXT("rear"));
    Gait = NAME_None;
    return RearLeft > 0.f;
}

void UHorseRideComponent::TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Dt, Type, Tick);
    if (!bRiding || !Rider) return;
    AHippodromeFigure* Horse = Figure.Get();
    if (!Horse) { Dismount(false); return; }
    UCharacterMovementComponent* M = Rider->GetCharacterMovement();
    if (M->IsSwimming()) { Dismount(true); Hint = TEXT("Too deep for the horse"); return; }
    if (Spurs < MaxSpurs && (SpurRefill += Dt) >= SpurRefillSeconds) { ++Spurs; SpurRefill = 0.f; }
    SpurLeft = FMath::Max(0.f, SpurLeft - Dt);
    RearLeft = FMath::Max(0.f, RearLeft - Dt);
    // Walls and fences: the horse stops short with its nose to them rather than pushing its head through.
    const FVector Forward = Rider->GetActorForwardVector();
    {
        FHitResult Hit; FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseAhead), false, Rider); Q.AddIgnoredActor(Horse);
        const FVector From = Feet() + FVector(0, 0, 90);
        if (Speed > 0.f && GetWorld()->LineTraceSingleByChannel(Hit, From, From + Forward * (HalfLength + 30.f + Speed * Dt), ECC_Visibility, Q) && Hit.ImpactNormal.Z < .6f)
            Speed = 0.f;
        const float Moved = FVector::DotProduct(M->Velocity, Forward);
        if (M->IsMovingOnGround() && Speed > 60.f && Moved < Speed * .4f) Speed = FMath::Max(0.f, Moved);
    }
    // W urges the horse on to a trot (Shift a gallop, Alt a walk); left alone it eases down; S reins it in.
    const float Want = bGallop ? GallopSpeed : bWalk ? WalkSpeed : TrotSpeed;
    if (RearLeft > 0.f || bMenu) Speed = FMath::FInterpConstantTo(Speed, 0.f, Dt, 900.f);
    else if (SpurLeft > 0.f) Speed = FMath::FInterpConstantTo(Speed, SpurSpeed, Dt, 900.f);
    // The urge is how far the stick is pushed, not its forward part: W with A or D steers at full pace.
    else if (Input.Y > .1f) Speed = FMath::FInterpConstantTo(Speed, Want * FMath::Clamp(Input.Size(), 0.f, 1.f), Dt, Speed > Want ? 260.f : 380.f);
    else if (Input.Y < -.1f) Speed = FMath::FInterpConstantTo(Speed, 0.f, Dt, 800.f * -Input.Y);
    else Speed = FMath::FInterpConstantTo(Speed, 0.f, Dt, 300.f);
    // Turns: on the spot at a standstill, tight at a walk, wide at a gallop.
    Steering = FMath::FInterpTo(Steering, RearLeft > 0.f ? 0.f : Input.X, Dt, 4.f);
    const float TurnRate = Speed < 30.f ? 75.f : FMath::Lerp(120.f, 48.f, FMath::Clamp(Speed / SpurSpeed, 0.f, 1.f));
    Rider->AddActorWorldRotation(FRotator(0, TurnRate * Steering * Dt, 0));
    FVector V = Rider->GetActorForwardVector() * Speed; V.Z = M->Velocity.Z; M->Velocity = V;
    Hint = Speed < 30.f ? TEXT("H get off") : SpurLeft > 0.f ? TEXT("Flat out") : Speed > TrotSpeed + 100.f ? TEXT("Galloping") : Speed > WalkSpeed + 80.f ? TEXT("Trotting") : TEXT("Walking");
    Pose(Dt);
}

void UHorseRideComponent::Pose(float Dt)
{
    AHippodromeFigure* Horse = Figure.Get();
    if (!Horse) return;
    // The horse stands on the capsule's feet and tilts with the ground between its forelegs and hind legs.
    const FVector At = Feet();
    const float Yaw = Rider->GetActorRotation().Yaw;
    const FVector Forward = FRotator(0, Yaw, 0).Vector();
    FCollisionQueryParams Q(SCENE_QUERY_STAT(HorseSlope), false, Rider); Q.AddIgnoredActor(Horse);
    float Ground[2] = { (float)At.Z, (float)At.Z };
    for (int32 I = 0; I < 2; ++I)
    {
        const FVector P = At + Forward * (I ? -HalfLength * .8f : HalfLength * .8f); FHitResult H;
        if (GetWorld()->LineTraceSingleByChannel(H, P + FVector(0, 0, 90), P - FVector(0, 0, 120), ECC_Visibility, Q)) Ground[I] = H.ImpactPoint.Z;
    }
    const float Slope = FMath::Clamp(FMath::RadiansToDegrees(FMath::Atan2(Ground[0] - Ground[1], HalfLength * 1.6f)), -22.f, 22.f);
    Pitch = Dt > 0.f ? FMath::FInterpTo(Pitch, Slope, Dt, 6.f) : Slope;
    Horse->SetActorLocationAndRotation(At, FRotator(Pitch, Yaw, 0));
    if (RearLeft > 0.f) return;
    // The gait by speed, as the race picks it; turning hard at a canter or faster, the horse leans into the curve.
    const FHorseSpec& Spec = Horse->GetBody();
    FName Role = TEXT("idle"), RiderRole = TEXT("idle"); float Ref = 0.f;
    if (Speed > 30.f)
    {
        static const FName Gaits[5] = { TEXT("walk"), TEXT("trot"), TEXT("canter"), TEXT("run"), TEXT("sprint") };
        static const float Limits[5] = { 300.f, 540.f, 740.f, 960.f, 1e9f };
        int32 G = 0; while (Speed > Limits[G]) ++G;
        Role = Gaits[G]; RiderRole = G == 4 ? FName(TEXT("run")) : Gaits[G];
        Ref = Spec.SpeedsCm.FindRef(Role);
        if (G >= 3 && FMath::Abs(Steering) > .35f)
        {
            const bool bLeft = Steering < 0.f;
            Role = FName(FString::Printf(TEXT("Move_Gear_Top_Curve_%s%s"), bLeft ? TEXT("L") : TEXT("R"), G == 4 ? TEXT("_Fast") : TEXT("")));
            if (Horse->RiderHas(bLeft ? TEXT("left") : TEXT("right"))) RiderRole = bLeft ? TEXT("left") : TEXT("right");
        }
    }
    const float Rate = Ref > 1.f ? FMath::Clamp(Speed / Ref, .5f, 2.f) : 1.f;
    Horse->Gait(Role, RiderRole, Rate);
    Gait = Role;
    // Hooves: two falls a stride.
    if (Speed > 30.f && Ref > 1.f && Hooves.Num() && Dt > 0.f)
    {
        StrideClock += Dt * Rate / FMath::Max(Spec.Lengths.FindRef(Horse->BodyClip()), .1f) * 2.f;
        if (StrideClock >= 1.f)
        {
            StrideClock -= 1.f;
            USoundBase* Sound = Hooves[FMath::RandRange(0, Hooves.Num() - 1)];
            const float Pitch01 = FMath::FRandRange(.94f, 1.06f);
            UGameplayStatics::PlaySoundAtLocation(this, Sound, At, .5f, Pitch01);
            FAtelierAudioLog::Record(Sound, At, .5f, Pitch01, false);
        }
    }
}
