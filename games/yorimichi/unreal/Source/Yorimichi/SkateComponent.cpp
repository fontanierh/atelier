#include "SkateComponent.h"
#include "AtelierData.h"
#include "SkatePark.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "WandererSword.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Animation/AnimSequence.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "Misc/FileHelper.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Dom/JsonObject.h"
#include "YorimichiCombatFX.h"
#include "Components/AudioComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundAttenuation.h"
#include "Materials/MaterialInterface.h"

namespace SkateTune
{
    constexpr float Gravity = 1100.f;             // a little heavier than walking, for snappy pops
    constexpr float DeckHeight = 9.05f;           // deck top above the ground (docs/SKATE.md board contract)
    constexpr float WheelX = 18.f, WheelY = 9.3f, WheelRadius = 2.65f, HangerDrop = 7.3f, DeckThickness = 1.2f;
    constexpr float PushMax = 1250.f, PushAccel = 680.f, TopSpeed = 2200.f;   // pushing tops out at 45 km/h
    constexpr float Radius = 22.f, Half = 55.f, Clearance = 22.f;
    constexpr float ProbeUp = 25.f, Reach = 14.f, MaxStep = 3.5f;
    constexpr float PlantTime = .30f, ReleaseTime = .62f, StrokeLength = 44.f, PushLength = 1.f;
    // Pushing on: from the clip's lift (the foot up behind) straight to its swing (the foot forward, about to plant).
    constexpr float PushSwingFrom = .72f, PushSwingTo = .21f;
    constexpr float PushRecover = .28f;           // the swing back plays at this rate: about one push a second, not a scramble
    // Mouse deltas as PlayerInput reports them (about 20-40 per centimetre of travel): a full stick is ~1.5 cm of mouse,
    // scaled with the player's mouse sensitivity (0.4 is the default).
    constexpr float MouseScale = 1.f / 40.f;
    constexpr float PopMin = 250.f, PopMax = 520.f;   // 28 cm to 1.2 m: a hard flick clears a handrail with room, as in skate.
    constexpr float SpinMax = 420.f, SpinAccel = 1300.f, SpinWindUp = 300.f;
    constexpr float FlipDelay = .06f;             // the feet leave the board before it turns
}
using namespace SkateTune;

// -skatedebug: log every change of mode with the reason and the wheel probes (costly: strings every physics step).
static bool SkateDebug() { static const bool bOn = FParse::Param(FCommandLine::Get(), TEXT("skatedebug")); return bOn; }

namespace
{
    float Ease(float U) { U = FMath::Clamp(U, 0.f, 1.f); return 1.f - (1.f - U) * (1.f - U); }
    /** Ollie pop: the board pitches nose-up about the rear wheels, then levels (docs/SKATE.md, SkateOllie). */
    float PopPitch(float T)
    {
        if (T < 0.f) return 0.f;
        if (T < .05f) return 30.f * FMath::SmoothStep(0.f, .05f, T);
        if (T < .10f) return FMath::Lerp(30.f, 24.f, (T - .05f) / .05f);
        return 24.f * (1.f - FMath::SmoothStep(.10f, .24f, T));
    }
    FString Rounded(float Degrees)
    {
        // A turn is named from 150 degrees (180), 330 (360) ...: the quarter turn into a slide is not a 180.
        const int32 Half = FMath::FloorToInt((FMath::Abs(Degrees) + 30.f) / 180.f);
        return Half > 0 ? FString::FromInt(Half * 180) : FString();
    }
}

USkateComponent::USkateComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

UCharacterMovementComponent* USkateComponent::Movement() const { return Rider ? Rider->GetCharacterMovement() : nullptr; }

void USkateComponent::Initialize(AWandererCharacter* Character)
{
    Rider = Character;
    RailSystem = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    AddTickPrerequisiteComponent(Rider->GetCharacterMovement());
    AddTickPrerequisiteActor(Rider);
    Rider->GetMesh()->AddTickPrerequisiteComponent(this);
    BoardRoot = NewObject<USceneComponent>(Rider, TEXT("SkateBoardRoot"));
    BoardRoot->SetupAttachment(Rider->GetRootComponent()); BoardRoot->RegisterComponent();
    auto Load = [](const TCHAR* Name, const TCHAR* Fallback) -> UStaticMesh*
    {
        UStaticMesh* M = LoadObject<UStaticMesh>(nullptr, *FString::Printf(TEXT("/Game/SkatePark/Board/%s.%s"), Name, Name));
        return M ? M : LoadObject<UStaticMesh>(nullptr, Fallback);
    };
    auto Part = [&](const TCHAR* Name, UStaticMesh* Mesh, USceneComponent* Parent)
    {
        auto* C = NewObject<UStaticMeshComponent>(Rider, Name);
        C->SetupAttachment(Parent); C->SetStaticMesh(Mesh);
        C->SetCollisionEnabled(ECollisionEnabled::NoCollision); C->SetGenerateOverlapEvents(false); C->SetCanEverAffectNavigation(false);
        C->SetRenderCustomDepth(true); C->SetCustomDepthStencilValue(2);
        C->RegisterComponent(); return C;
    };
    UStaticMesh* DeckMesh = Load(TEXT("SM_SkateDeck"), TEXT("/Game/Skateboard/SM_Deck.SM_Deck"));
    UStaticMesh* TruckMesh = Load(TEXT("SM_SkateTruck"), TEXT("/Game/Skateboard/SM_Truck.SM_Truck"));
    UStaticMesh* WheelMesh = Load(TEXT("SM_SkateWheel"), TEXT("/Game/Skateboard/SM_Wheel.SM_Wheel"));
    Deck = Part(TEXT("SkateDeck"), DeckMesh, BoardRoot);
    for (int32 End = 0; End < 2; ++End)
    {
        auto* Truck = Part(*FString::Printf(TEXT("SkateTruck%d"), End), TruckMesh, Deck);
        Truck->SetRelativeLocationAndRotation(FVector(End == 0 ? WheelX : -WheelX, 0, -DeckThickness), FRotator(0, End == 0 ? 0.f : 180.f, 0));
        Trucks.Add(Truck);
        for (int32 Side = 0; Side < 2; ++Side)
        {
            auto* Wheel = Part(*FString::Printf(TEXT("SkateWheel%d%d"), End, Side), WheelMesh, Truck);
            Wheel->SetRelativeLocation(FVector(0, Side == 0 ? -WheelY : WheelY, -(DeckHeight - DeckThickness - WheelRadius) + 0.f));
            Wheels.Add(Wheel);
        }
    }
    BoardRoot->SetVisibility(false, true);
    const UWandererDefinition* D = Rider->GetDefinition();
    // Riding needs the board and at least the stance; missing clips fall back so the ride can be tested early.
    bAvailable = D && DeckMesh && TruckMesh && WheelMesh && (D->SkateActions.Contains(TEXT("SkateStance")) || D->FindAction(TEXT("Idle")));
    LoadContacts();
    LoadSounds();
    UE_LOG(LogTemp, Display, TEXT("SKATE available=%d clips=%d board=%s"), bAvailable, D ? D->SkateActions.Num() : 0, DeckMesh ? *DeckMesh->GetName() : TEXT("none"));
}

void USkateComponent::LoadSounds()
{
    auto Load = [](const FString& Name) { return LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("/Game/Audio/Skate/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet); };
    Attenuation = NewObject<USoundAttenuation>(this);
    FSoundAttenuationSettings& A = Attenuation->Attenuation;
    A.bAttenuate = true; A.bSpatialize = true; A.AttenuationShape = EAttenuationShape::Sphere;
    A.AttenuationShapeExtents = FVector(500.f, 0.f, 0.f); A.FalloffDistance = 4500.f; A.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound; A.dBAttenuationAtMax = -48.f;
    for (const TCHAR* Cue : {TEXT("pop"), TEXT("land"), TEXT("catch"), TEXT("push"), TEXT("flick"), TEXT("clatter")})
    {
        const int32 First = Waves.Num();
        for (int32 I = 1; I <= 8; ++I) if (USoundWave* W = Load(FString::Printf(TEXT("%s_%02d"), Cue, I))) Waves.Add(W);
        if (Waves.Num() > First) CueRange.Add(Cue, FIntPoint(First, Waves.Num() - First));
    }
    for (const TCHAR* Name : {TEXT("body_fall_01"), TEXT("body_fall_02")})
        if (USoundWave* W = LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("/Game/Audio/Combat/%s.%s"), Name, Name), nullptr, LOAD_NoWarn | LOAD_Quiet))
        { const int32 First = CueRange.Contains(TEXT("fall")) ? CueRange[TEXT("fall")].X : Waves.Num(); Waves.Add(W); CueRange.FindOrAdd(TEXT("fall"), FIntPoint(First, 0)).Y++; }
    int32 Index = 0;
    for (const TCHAR* Name : {TEXT("roll_01"), TEXT("grind_01"), TEXT("slide_01"), TEXT("skid_01"), TEXT("scrape_01")})
    {
        auto* C = NewObject<UAudioComponent>(Rider, *FString::Printf(TEXT("SkateLoop%d"), Index++));
        C->SetupAttachment(BoardRoot); C->bAutoActivate = false; C->bAllowSpatialization = true;
        C->AttenuationSettings = Attenuation; C->SetSound(Load(Name)); C->RegisterComponent();
        Loops.Add(C);
    }
    UE_LOG(LogTemp, Display, TEXT("SKATE sounds: %d one-shots, loops %d"), Waves.Num(), Loops.Num());
}

void USkateComponent::PlayCue(FName Cue, float Volume, float Pitch)
{
    const FIntPoint* Range = CueRange.Find(Cue);
    if (!Range || Range->Y <= 0 || !Rider) return;
    int32 Pick = Range->X + FMath::RandHelper(Range->Y);
    if (Range->Y > 1 && Pick == LastVariant) Pick = Range->X + (Pick - Range->X + 1) % Range->Y;   // no back-to-back repeat
    LastVariant = Pick;
    const FVector At = GetDeckWorld().GetLocation();
    UGameplayStatics::PlaySoundAtLocation(this, Waves[Pick], At, FRotator::ZeroRotator, Volume, Pitch, 0.f, Attenuation);
    FAtelierAudioLog::Record(Waves[Pick], At, Volume, Pitch, false);
}

void USkateComponent::UpdateAudio(float Dt)
{
    if (Loops.Num() < 5) return;
    const float Speed = Vel.Size();
    const bool bRolling = Mode == ESkateMode::Ground && !bPowerslide;
    const float Want[5] = {
        bRolling ? FMath::Clamp(Speed / 450.f, 0.f, 1.f) * .85f : 0.f,                                           // roll
        Mode == ESkateMode::Grind && !bSlide ? .8f * FMath::Clamp(RailSpeed / 300.f, .45f, 1.f) : 0.f,              // grind
        Mode == ESkateMode::Grind && bSlide ? .85f * FMath::Clamp(RailSpeed / 300.f, .45f, 1.f) : 0.f,              // slide
        Mode == ESkateMode::Ground && bPowerslide ? .9f * FMath::Clamp(Speed / 400.f, 0.f, 1.f) * SlideAngle / 82.f : 0.f, // skid
        Mode == ESkateMode::Ground && bBraking ? .7f * FMath::Clamp(Speed / 300.f, .3f, 1.f) : 0.f };              // foot brake
    const float Pitch[5] = { .75f + .45f * FMath::Clamp(Speed / 1000.f, 0.f, 1.f), .85f + .3f * FMath::Clamp(RailSpeed / 800.f, 0.f, 1.f),
        .9f + .2f * FMath::Clamp(RailSpeed / 800.f, 0.f, 1.f), .9f + .3f * FMath::Clamp(Speed / 800.f, 0.f, 1.f), 1.f };
    for (int32 I = 0; I < 5; ++I)
    {
        UAudioComponent* C = Loops[I];
        if (!C || !C->Sound) continue;
        // Quick attack (a grind starts at contact), a softer release.
        LoopVolume[I] = FMath::FInterpTo(LoopVolume[I], Want[I], Dt, Want[I] > LoopVolume[I] ? 30.f : 10.f);
        if (LoopVolume[I] > .01f)
        {
            if (!C->IsPlaying()) C->Play(FMath::FRand() * 1.5f);
            C->SetVolumeMultiplier(LoopVolume[I]); C->SetPitchMultiplier(Pitch[I]);
        }
        else if (C->IsPlaying()) C->Stop();
    }
}

void USkateComponent::LoadContacts()
{
    // Limb contacts from the rider build (game-r17 skate-build.json): intervals when a foot is on the deck or a hand
    // holds the board. Without the file every foot counts as planted and no hand holds.
    const FString Path = AtelierDataPath(TEXT("characters/warm-original/skate-build.json"));
    FString Text; TSharedPtr<FJsonObject> Root;
    if (!FFileHelper::LoadFileToString(Text, *Path) || !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Root) || !Root.IsValid()) return;
    const TSharedPtr<FJsonObject>* Clips = nullptr;
    if (!Root->TryGetObjectField(TEXT("clips"), Clips)) return;
    const TCHAR* Limbs[] = {TEXT("foot_L"), TEXT("foot_R"), TEXT("hand_L"), TEXT("hand_R")};
    for (const auto& Pair : (*Clips)->Values)
    {
        const TSharedPtr<FJsonObject> Clip = Pair.Value->AsObject();
        const TSharedPtr<FJsonObject>* Contacts = nullptr;
        if (!Clip || !Clip->TryGetObjectField(TEXT("contacts"), Contacts)) continue;
        TArray<FVector4f>& Out = ClipContacts.FindOrAdd(FName(*Pair.Key));
        for (int32 L = 0; L < 4; ++L)
        {
            const TArray<TSharedPtr<FJsonValue>>* Spans = nullptr;
            if (!(*Contacts)->TryGetArrayField(Limbs[L], Spans)) continue;
            for (const auto& Span : *Spans)
            {
                const auto& A = Span->AsArray();
                if (A.Num() >= 2) Out.Add(FVector4f(L, A[0]->AsNumber(), A[1]->AsNumber(), 0));
            }
        }
    }
    UE_LOG(LogTemp, Display, TEXT("SKATE contacts for %d clips"), ClipContacts.Num());
}

UAnimSequence* USkateComponent::FindClip(FName Name, bool bSwitch) const
{
    const UWandererDefinition* D = Rider ? Rider->GetDefinition() : nullptr;
    if (!D || Name.IsNone()) return nullptr;
    const bool bSkateClip = Name.ToString().StartsWith(TEXT("Skate"));
    if (bSkateClip)
    {
        const FName Key = bGoofy != bSwitch ? FName(Name.ToString() + TEXT("Goofy")) : Name;
        if (const auto* Clip = D->SkateActions.Find(Key)) if (*Clip) return *Clip;
        if (const auto* Clip = D->SkateActions.Find(Name)) if (*Clip) return *Clip;
        // Development fallbacks until every clip is authored.
        if (Name != TEXT("SkateStance") && Name.ToString().StartsWith(TEXT("SkateGrab"))) return FindClip(TEXT("SkateAir"));
        if (Name == TEXT("SkateStanceFakie") || Name == TEXT("SkateCarveToe") || Name == TEXT("SkateCarveHeel") || Name == TEXT("SkateBrake") || Name == TEXT("SkatePowerslide") ||
            Name == TEXT("SkateManual") || Name == TEXT("SkateNoseManual") || Name.ToString().StartsWith(TEXT("SkateGrind")) || Name == TEXT("SkateSlide"))
            return Name == TEXT("SkateStance") ? nullptr : FindClip(TEXT("SkateStance"));
        if (Name == TEXT("SkateNollie") || Name == TEXT("SkateFlip")) return FindClip(TEXT("SkateOllie"));
        if (Name == TEXT("SkateOllie") || Name == TEXT("SkateAir") || Name == TEXT("SkateLand") || Name == TEXT("SkateCrouch") || Name == TEXT("SkateNollieCrouch") || Name == TEXT("SkatePush"))
            return Name == TEXT("SkateStance") ? nullptr : FindClip(TEXT("SkateStance"));
        return D->FindAction(TEXT("Idle"));
    }
    return D->FindAction(Name);
}

void USkateComponent::SetGoofy(bool bNewGoofy)
{
    if (bGoofy == bNewGoofy) return;
    bGoofy = bNewGoofy;
    if (IsRiding() && Mode != ESkateMode::Bail) { SetMeshForRiding(true); ++Serial; }
}

void USkateComponent::SetMeshForRiding(bool bRiding)
{
    USkeletalMeshComponent* Mesh = Rider->GetMesh();
    if (bRiding)
    {
        // The rider stands across the board: regular faces the toe side (+Y), goofy -Y. The clips put the nose on the
        // rider's left (regular) or right (goofy), so this turn puts it on the actor's +X.
        // The clips stand the Root bone on the board's ground point; the Root is not the mesh's origin, so place by it.
        FVector RootRef = FVector::ZeroVector;
        if (const USkeletalMesh* Asset = Mesh->GetSkeletalMeshAsset())
        {
            const FReferenceSkeleton& Ref = Asset->GetRefSkeleton();
            const int32 Root = Ref.FindBoneIndex(TEXT("root"));
            if (Root != INDEX_NONE) RootRef = Ref.GetRefBonePose()[Root].GetLocation();
        }
        const FQuat Turn = FQuat(FVector::UpVector, FMath::DegreesToRadians(bGoofy ? -90.f : 90.f)) * SavedMeshRotation;
        Mesh->SetRelativeLocationAndRotation(FVector(0, 0, -BodyLift) - Turn.RotateVector(RootRef), Turn);
    }
    else Mesh->SetRelativeLocationAndRotation(SavedMeshLocation, SavedMeshRotation);
}

bool USkateComponent::Toggle()
{
    if (!Rider || !bAvailable) return false;
    UCharacterMovementComponent* M = Movement();
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    if (Mode == ESkateMode::Off)
    {
        if (!M->IsMovingOnGround() || Rider->bIsCrouched) return false;
        if (Rider->GetSword() && Rider->GetSword()->IsArmed()) Rider->GetSword()->SetArmed(false);
        SavedRadius = Capsule->GetUnscaledCapsuleRadius(); SavedHalf = Capsule->GetUnscaledCapsuleHalfHeight();
        SavedMeshLocation = Rider->GetMesh()->GetRelativeLocation(); SavedMeshRotation = Rider->GetMesh()->GetRelativeRotation().Quaternion();
        SavedStep = M->MaxStepHeight;
        Pos = Rider->GetActorLocation() - FVector(0, 0, Capsule->GetScaledCapsuleHalfHeight() + M->CurrentFloor.FloorDist);
        const FVector Normal = M->CurrentFloor.HitResult.bBlockingHit ? FVector(M->CurrentFloor.HitResult.ImpactNormal) : FVector::UpVector;
        Rot = AlignUp(FRotator(0, Rider->GetActorRotation().Yaw, 0).Quaternion(), Normal, 1.f);
        // A running start carries onto the board.
        Vel = Forward() * FMath::Max(0.f, float(FVector::DotProduct(M->Velocity, Forward())));
        Capsule->SetCapsuleSize(Radius, Half);
        BodyLift = Clearance + Half;
        SetMeshForRiding(true);
        M->SetMovementMode(MOVE_Custom, 2);
        Rider->SetAction(NAME_None);
        Flick.Reset(); Combo.Reset(); ComboPoints = 0;
        Enter(ESkateMode::Ground); LandTime = 0.f;
        FHitResult Hit; MoveBody(Hit);
        BoardRoot->SetVisibility(true, true);
        return true;
    }
    if (Mode != ESkateMode::Ground) return false;    // step off from the ground only
    StowImmediately();
    // Step off moving on: face the way the board was going, keep a jog's worth of the speed.
    const FVector Flat = FVector(Vel.X, Vel.Y, 0.f);
    if (Flat.Size() > 30.f) Rider->SetActorRotation(Flat.Rotation());
    M->Velocity = Flat.GetClampedToMaxSize(420.f);
    return true;
}

void USkateComponent::StowImmediately()
{
    if (Mode == ESkateMode::Off || !Rider) return;
    UCharacterMovementComponent* M = Movement();
    const bool bWasBail = Mode == ESkateMode::Bail;
    EndCombo(true);
    Mode = ESkateMode::Off;
    bManual = bPowerslide = bPushing = bBraking = false;
    BoardRoot->SetVisibility(false, true);
    for (int32 I = 0; I < Loops.Num(); ++I) { if (Loops[I]) Loops[I]->Stop(); LoopVolume[I] = 0.f; }
    if (!bWasBail)
    {
        UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
        Capsule->SetCapsuleSize(SavedRadius, SavedHalf);
        SetMeshForRiding(false);
        const FVector Stand = Pos + FVector(0, 0, SavedHalf + 2.f);
        Rider->SetActorLocationAndRotation(Stand, FRotator(0, Forward().Rotation().Yaw, 0), false, nullptr, ETeleportType::TeleportPhysics);
        M->SetMovementMode(MOVE_Falling);
        M->Velocity = FVector::ZeroVector;
    }
    M->MaxStepHeight = SavedStep;
    ++Serial;
}

void USkateComponent::Launch(const FVector& Velocity)
{
    if (Mode == ESkateMode::Ground || Mode == ESkateMode::Air) Vel = Velocity;
}

bool USkateComponent::PlaceAt(const FVector& GroundPoint, float Yaw)
{
    if (!Rider || !bAvailable) return false;
    if (Mode == ESkateMode::Off)
    {
        Rider->SetActorLocationAndRotation(GroundPoint + FVector(0, 0, Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() + 2.f), FRotator(0, Yaw, 0), false, nullptr, ETeleportType::TeleportPhysics);
        Movement()->SetMovementMode(MOVE_Walking);
        Movement()->Velocity = FVector::ZeroVector;
        Movement()->FindFloor(Movement()->UpdatedComponent->GetComponentLocation(), Movement()->CurrentFloor, false);
        if (!Toggle()) return false;
    }
    if (Mode == ESkateMode::Bail) EndBail();
    Pos = GroundPoint; Rot = FRotator(0, Yaw, 0).Quaternion(); Vel = FVector::ZeroVector; bFakie = false; RevertLeft = 0.f;
    Enter(ESkateMode::Ground);
    Rider->SetActorLocationAndRotation(Pos + Up() * BodyLift, Rot, false, nullptr, ETeleportType::TeleportPhysics);
    return true;
}

FQuat USkateComponent::AlignUp(const FQuat& Q, const FVector& NewUp, float Alpha) const
{
    const FVector Current = Q.GetUpVector();
    const FVector Target = FVector(NewUp).GetSafeNormal();
    if (Target.IsNearlyZero()) return Q;
    const FQuat Full = FQuat::FindBetweenNormals(Current, Target);
    return (FQuat::Slerp(FQuat::Identity, Full, FMath::Clamp(Alpha, 0.f, 1.f)) * Q).GetNormalized();
}

void USkateComponent::Enter(ESkateMode Next)
{
    const ESkateMode Was = Mode;
    if (SkateDebug()) UE_LOG(LogTemp, Display, TEXT("SKATE %d -> %d v=%.0f up=%s %s"), int32(Was), int32(Next), Vel.Size(), *Up().ToString(), Next == ESkateMode::Air ? *AirWhy : TEXT(""));
    AirWhy = TEXT("pop");
    Mode = Next;
    if (Next == ESkateMode::Air)
    {
        AirTime = 0.f; PredictClock = 0; LandingNormal = Up();
        // Leaving a wall (quarter pipe above ~70 degrees): a vert air.
        bVertAir = FMath::Abs(Up().Z) < .35f; VertNormal = Up(); VertPoint = Pos;
        Grab = NAME_None; GrabTime = GrabTotal = 0.f; bGrabHeldAtStart = In.bGrabLeft || In.bGrabRight;
        bManual = bPowerslide = bPushing = bBraking = false;
        if (Was != ESkateMode::Air && !bPopped) { SpinRate = 0.f; SpinTotal = 0.f; }
    }
    if (Next == ESkateMode::Ground)
    {
        bPopped = false; Trick = FSkateTrick(); TrickTime = TrickDuration = 0.f; SpinRate = 0.f;
        Grab = NAME_None; Rail = INDEX_NONE; GroundTime = 0.f;
    }
    if (Next == ESkateMode::Grind) { bManual = bPowerslide = bPushing = bBraking = false; GrindTime = 0.f; Balance = 0.f; }
}

bool USkateComponent::MoveBody(FHitResult& Hit)
{
    UCharacterMovementComponent* M = Movement();
    const FVector Target = Pos + Up() * BodyLift;
    M->SafeMoveUpdatedComponent(Target - M->UpdatedComponent->GetComponentLocation(), Rot, true, Hit);
    if (Hit.IsValidBlockingHit())
    {
        Pos = M->UpdatedComponent->GetComponentLocation() - Up() * BodyLift;
        return true;
    }
    return false;
}

bool USkateComponent::ProbeGround(const FVector& At, const FQuat& Q, FVector& OutPoint, FVector& OutNormal, bool& bBlocked, float& LeadRise) const
{
    const FVector N = Q.GetUpVector(), F = Q.GetForwardVector(), R = Q.GetRightVector();
    const FVector Travel = Vel.SizeSquared() > 1.f ? Vel.GetSafeNormal() : F;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateWheels), false, Rider);
    // Wheels in order around the board: front-left, front-right, back-right, back-left.
    const FVector2D Wheel[4] = {{WheelX, -WheelY}, {WheelX, WheelY}, {-WheelX, WheelY}, {-WheelX, -WheelY}};
    FVector Hits[4]; FVector Normals[4]; bool Got[4] = {false, false, false, false}; int32 Count = 0;
    bBlocked = false; LeadRise = 0.f; ProbeDebug.Reset();
    float LeadSum = 0.f; int32 Leads = 0;
    FVector LeadN = FVector::ZeroVector, TrailN = FVector::ZeroVector;
    for (int32 I = 0; I < 4; ++I)
    {
        const FVector Spot = At + F * Wheel[I].X + R * Wheel[I].Y;
        const FVector Start = Spot + N * ProbeUp, End = Spot - N * Reach;
        FHitResult Hit;
        if (!GetWorld()->LineTraceSingleByChannel(Hit, Start, End, ECC_Visibility, Params) || Hit.bStartPenetrating)
        { if (SkateDebug()) ProbeDebug += FString::Printf(TEXT("[%d miss%s]"), I, Hit.bStartPenetrating ? TEXT(" start") : TEXT("")); continue; }
        const float Rise = FVector::DotProduct(Hit.ImpactPoint - Spot, N);
        const float Facing = FVector::DotProduct(FVector(Hit.ImpactNormal), N);
        if (SkateDebug()) ProbeDebug += FString::Printf(TEXT("[%d rise %.1f n(%.2f %.2f %.2f) %s]"), I, Rise, Hit.ImpactNormal.X, Hit.ImpactNormal.Y, Hit.ImpactNormal.Z, Hit.GetComponent() ? *Hit.GetComponent()->GetName() : TEXT("?"));
        if (Rise > MaxStep)
        {
            // A step or a face in front of the wheels, unless it is a ramp rising ahead (a concave transition).
            const float Ahead = FVector::DotProduct(F * Wheel[I].X, Travel) + 6.f;
            const float Slope = FMath::Tan(FMath::Acos(FMath::Clamp(Facing, -1.f, 1.f)));
            if (Facing < .55f || Rise > MaxStep + FMath::Max(Ahead, 0.f) * Slope * 1.3f)
            {
                if (Ahead > 6.f) bBlocked = true;
                continue;
            }
        }
        if (FVector::DotProduct(F * Wheel[I].X, Travel) > 0.f) { LeadSum += Rise; ++Leads; LeadN += Hit.ImpactNormal; } else TrailN += Hit.ImpactNormal;
        Hits[I] = Hit.ImpactPoint; Normals[I] = Hit.ImpactNormal; Got[I] = true; ++Count;
    }
    // A wheel catching an edge or the coping reports a surface far off the board's own: leave it out while three agree.
    if (Count > 3)
    {
        int32 Worst = INDEX_NONE; float WorstFacing = .82f;
        for (int32 I = 0; I < 4; ++I) if (Got[I]) { const float F2 = FVector::DotProduct(Normals[I], N); if (F2 < WorstFacing) { WorstFacing = F2; Worst = I; } }
        if (Worst != INDEX_NONE) { Got[Worst] = false; --Count; }
    }
    if (Count < 3) return false;
    // The surfaces' own normals under the wheels (a plane through the hit points would tip on every seam and pebble),
    // and the board's height from the hit points along that normal.
    FVector Normal = FVector::ZeroVector, Centre = FVector::ZeroVector;
    for (int32 I = 0; I < 4; ++I) if (Got[I]) { Normal += Normals[I]; Centre += Hits[I]; }
    Centre /= Count;
    Normal = Normal.GetSafeNormal();
    if (FVector::DotProduct(Normal, N) < 0.f) Normal = -Normal;
    if (Normal.IsNearlyZero()) Normal = N;
    OutNormal = Normal;
    // Height of the leading wheels' ground against the board's own plane at the centre's new height: negative where
    // the surface falls away ahead (a convex edge).
    if (Leads > 0) LeadRise = LeadSum / Leads - FVector::DotProduct(Centre - At, N);
    // Concave (a ramp coming up ahead): the leading wheels' surface tips back against the travel. Only a convex edge
    // (the surface tipping forward ahead) can throw the board.
    const bool bConvex = !LeadN.IsNearlyZero() && !TrailN.IsNearlyZero() && FVector::DotProduct(LeadN.GetSafeNormal() - TrailN.GetSafeNormal(), Travel) > .002f;
    if (!bConvex) LeadRise = FMath::Max(LeadRise, 0.f);
    OutPoint = At - Normal * FVector::DotProduct(At - Centre, Normal);
    return true;
}

// ---------------------------------------------------------------------------------------------------- the ride

void USkateComponent::PhysSkate(float Dt)
{
    if (!Rider || Mode == ESkateMode::Off || Mode == ESkateMode::Bail) return;
    float Remaining = FMath::Min(Dt, .1f);
    while (Remaining > KINDA_SMALL_NUMBER && (Mode == ESkateMode::Ground || Mode == ESkateMode::Air || Mode == ESkateMode::Grind))
    {
        const float H = FMath::Min(Remaining, 1.f / 120.f); Remaining -= H;
        LeaveRailCooldown = FMath::Max(0.f, LeaveRailCooldown - H);
        BumpCooldown = FMath::Max(0.f, BumpCooldown - H);
        if (Mode == ESkateMode::Ground) StepGround(H);
        else if (Mode == ESkateMode::Air) StepAir(H);
        else StepGrind(H);
    }
    if (Movement()) Movement()->Velocity = Vel;
}

float USkateComponent::ReadSurface() const
{
    // What the wheels roll on, by the material under the board: smooth (concrete, asphalt, wood, the park) to grass.
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateSurface), true, Rider);
    Params.bReturnFaceIndex = true;
    FHitResult Hit;
    SurfaceName = TEXT("none");
    if (!GetWorld()->LineTraceSingleByChannel(Hit, Pos + Up() * 20.f, Pos - Up() * 20.f, ECC_Visibility, Params) || !Hit.GetComponent()) return 1.f;
    if (Hit.GetActor() && Hit.GetActor()->IsA<ASkatePark>()) { SurfaceName = TEXT("park"); return 1.f; }
    int32 Section = 0;
    const UMaterialInterface* Material = Hit.FaceIndex != INDEX_NONE ? Hit.GetComponent()->GetMaterialFromCollisionFaceIndex(Hit.FaceIndex, Section) : Hit.GetComponent()->GetMaterial(0);
    if (!Material) return 1.f;
    FString Name = Material->GetName();
    SurfaceName = FString::Printf(TEXT("%s#%d"), *Name, Hit.FaceIndex);
    Name.RemoveFromStart(TEXT("MI_")); Name.RemoveFromStart(TEXT("M_"));
    auto Has = [&](std::initializer_list<const TCHAR*> Keys) { for (const TCHAR* K : Keys) if (Name.Contains(K)) return true; return false; };
    if (Has({TEXT("Grass"), TEXT("Ground"), TEXT("Hills"), TEXT("Moss"), TEXT("Flower"), TEXT("FarForest"), TEXT("Litter"), TEXT("Leaf")})) return 20.f;
    if (Has({TEXT("Water"), TEXT("Mud")})) return 25.f;
    if (Has({TEXT("Sand"), TEXT("Dirt")})) return 12.f;
    if (Has({TEXT("Lane"), TEXT("Rock")})) return 4.f;
    return 1.f;
}

void USkateComponent::StepGround(float H)
{
    GroundTime += H;
    SurfaceClock -= H;
    if (SurfaceClock <= 0.f) { SurfaceClock = .05f; SurfaceDrag = FMath::Lerp(SurfaceDrag, ReadSurface(), .5f); }
    const FVector N = Up();
    float Speed = Vel.Size();
    const FVector Travel = Speed > 1.f ? Vel / Speed : Forward() * (bFakie ? -1.f : 1.f);
    const bool bPushContact = bPushing && PushTime >= PlantTime && PushTime < ReleaseTime;
    if (bPowerslide)
    {
        // The board turns across the line of travel and scrubs the speed; the line itself barely steers.
        SlideAngle = FMath::FInterpConstantTo(SlideAngle, (In.bPowerslide || In.bBrake) && Speed > 120.f ? 82.f : 0.f, H, 480.f);
        SlideTravel = FQuat(N, FMath::DegreesToRadians(In.Left.X * 25.f * H)).RotateVector(FVector::VectorPlaneProject(SlideTravel, N).GetSafeNormal());
        Speed = FMath::Max(0.f, Speed - (650.f + Speed * .7f) * H);
        Vel = SlideTravel * Speed;
        const FVector Heading = FQuat(N, FMath::DegreesToRadians(SlideSign * SlideAngle)).RotateVector(SlideTravel * (bFakie ? -1.f : 1.f));
        Rot = FRotationMatrix::MakeFromXZ(Heading, N).ToQuat();
        if (SlideAngle <= .5f) { bPowerslide = false; Rot = FRotationMatrix::MakeFromXZ(SlideTravel * (bFakie ? -1.f : 1.f), N).ToQuat(); }
    }
    else
    {
        // Crouched for a pop, the left stick still steers (a little less) while it winds up the spin.
        if (RevertLeft > 0.f)
        {
            const float Step = FMath::Min(RevertLeft, 900.f * H);
            Rot = (FQuat(N, FMath::DegreesToRadians(RevertSign * Step)) * Rot).GetNormalized();
            RevertLeft -= Step;
        }
        const float SteerIn = bManual ? In.Left.X * .6f : Flick.Load > .3f ? In.Left.X * .75f : In.Left.X;
        Steering = FMath::FInterpTo(Steering, SteerIn, H, 9.f);
        if (Speed < 30.f)
        {
            // Kickturn on the back wheels when stopped.
            Rot = FQuat(N, FMath::DegreesToRadians(In.Left.X * 160.f * H)) * Rot;
            Vel = Forward() * FVector::DotProduct(Vel, Forward());
        }
        else
        {
            const float Rate = FMath::Lerp(150.f, 60.f, FMath::Clamp(Speed / 1200.f, 0.f, 1.f)) * (bPushContact ? .35f : 1.f);
            const FQuat Turn(N, FMath::DegreesToRadians(Steering * Rate * H));
            Rot = (Turn * Rot).GetNormalized(); Vel = Turn.RotateVector(Vel);
        }
        const FVector G(0, 0, -Gravity);
        const FVector Along = G - FVector::DotProduct(G, N) * N;
        const FVector Fwd = Forward(), Right = Rot.GetRightVector();
        const float VF = FVector::DotProduct(Vel, Fwd);
        float VL = FVector::DotProduct(Vel, Right);
        float A = FVector::DotProduct(Along, Fwd);
        const float Dir = FMath::Abs(VF) > 1.f ? FMath::Sign(VF) : (bFakie ? -1.f : 1.f);
        // At speed the planted foot is on the ground for less time (the stroke follows the distance rolled), so it pushes
        // harder for it: every stroke adds about the same, fading toward the push limit.
        if (bPushContact) A += Dir * PushAccel * FMath::Max(0.f, 1.f - FMath::Abs(VF) / PushMax) * FMath::Max(1.f, FMath::Abs(VF) / 150.f);
        // Grass and sand stop a board quickly; concrete barely slows it.
        float Resist = (10.f + FMath::Abs(VF) * .01f) * SurfaceDrag + VF * VF * 3.5e-5f;
        if (bBraking) Resist += 480.f + FMath::Abs(VF) * .5f;
        if (bManual) Resist += 8.f;
        float NewVF = VF + A * H;
        const float Drop = Resist * H;
        NewVF = FMath::Abs(NewVF) <= Drop ? 0.f : NewVF - FMath::Sign(NewVF) * Drop;
        if (RevertLeft <= 0.f) VL *= FMath::Exp(-20.f * H);   // the wheels grip sideways, except while skidding round in a revert
        Vel = (Fwd * NewVF + Right * VL).GetClampedToMaxSize(TopSpeed);
    }
    if (!bPowerslide && RevertLeft <= 0.f && Vel.SizeSquared() > 400.f) bFakie = FVector::DotProduct(Vel, Forward()) < 0.f;
    else if (Vel.SizeSquared() < 25.f && RevertLeft <= 0.f) bFakie = false;   // stopped, he stands regular again
    Speed = Vel.Size();
    // Follow the surface.
    const FVector Next = Pos + Vel * H;
    FVector Point, Normal; bool bBlocked = false; float LeadRise = 0.f;
    const bool bGround = ProbeGround(Next, Rot, Point, Normal, bBlocked, LeadRise);
    if (bBlocked && BumpCooldown <= 0.f)
    {
        const float Into = FMath::Abs(FVector::DotProduct(Vel, Forward()));
        BumpCooldown = .2f;
        if (Into > 380.f) { StartBail(TEXT("tripped on a step")); return; }
        Vel = -Vel * .15f;
        return;
    }
    if (!bGround)
    {
        if (SkateDebug()) AirWhy = FString::Printf(TEXT("no ground (blocked %d) %s"), bBlocked, *ProbeDebug);
        Pos = Next;
        Enter(ESkateMode::Air);
        return;
    }
    if (LeadRise < -1.f && Speed > 60.f)
    {
        // The ground falls away under the leading wheels: over that curvature (2 * drop / lever^2) the board keeps contact
        // only while gravity can supply v^2 * curvature. Seams and pebbles (under a centimetre) do not count.
        const float Curvature = 2.f * -LeadRise / (WheelX * WheelX);
        const float Need = Speed * Speed * Curvature;
        const float Hold = Gravity * FMath::Max(0.f, float(Normal.Z)) + 350.f;
        if (Need > Hold) { if (SkateDebug()) AirWhy = FString::Printf(TEXT("convex edge drop %.1f need %.0f hold %.0f"), LeadRise, Need, Hold); Pos = Next; Enter(ESkateMode::Air); return; }
    }
    Pos = Point;
    // Follow the surface, but never swing more than 6 degrees in a step (a transition turns 1-4): a stray normal cannot
    // throw the board past the vertical.
    const float Swing = FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Up(), Normal)), -1.f, 1.f));
    Rot = AlignUp(Rot, Normal, Swing > FMath::DegreesToRadians(6.f) ? FMath::DegreesToRadians(6.f) / Swing : 1.f);
    Vel = FVector::VectorPlaneProject(Vel, Up()).GetSafeNormal() * Speed;
    if (Normal.Z < .15f && Speed < 70.f) { AirWhy = TEXT("stalled on a wall"); Enter(ESkateMode::Air); return; }   // stalled on a wall: fall away from it
    FHitResult Hit;
    if (MoveBody(Hit) && FVector::DotProduct(FVector(Hit.ImpactNormal), Up()) < .5f)
    {
        const FVector Wall = Hit.ImpactNormal;
        const float Into = -FVector::DotProduct(Vel, Wall);
        if (Into > 520.f) { StartBail(TEXT("hit a wall")); return; }
        if (Into > 0.f) Vel = FVector::VectorPlaneProject(Vel + Wall * Into, Up()) * .85f;
    }
}

void USkateComponent::StepAir(float H)
{
    AirTime += H; PopTime += H;
    Vel.Z -= Gravity * H;
    // Spin: the left stick winds the body and board around the board's up axis.
    const float SpinTarget = In.Left.X * SpinMax;
    SpinRate = FMath::FInterpConstantTo(SpinRate, SpinTarget, H, FMath::Abs(SpinTarget) > 1.f ? SpinAccel : SpinAccel * .45f);
    const float Yaw = SpinRate * H;
    Rot = (FQuat(Up(), FMath::DegreesToRadians(Yaw)) * Rot).GetNormalized();
    SpinTotal += Yaw;
    // Turn toward the surface we are going to land on (found by sweeping the flight path), so vert airs come back in.
    if ((PredictClock++ % 4) == 0)
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateLanding), false, Rider);
        FVector P = Pos + Up() * 12.f, V = Vel; LandingNormal = FVector::UpVector;
        for (int32 I = 0; I < 40; ++I)
        {
            const float Step = .04f;
            const FVector NextP = P + V * Step + FVector(0, 0, -.5f * Gravity * Step * Step);
            V.Z -= Gravity * Step;
            FHitResult Hit;
            if (GetWorld()->SweepSingleByChannel(Hit, P, NextP, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(12.f), Params))
            { LandingNormal = Hit.ImpactNormal; break; }
            P = NextP;
        }
    }
    // Vert: off a wall the board stays square to it and comes back in on it; a real transfer (far from the wall) lands flat.
    const float FromWall = bVertAir ? float(FVector::DotProduct(Pos - VertPoint, VertNormal)) : 0.f;
    if (bVertAir && FromWall > 90.f) bVertAir = false;
    if (bVertAir) Rot = AlignUp(Rot, VertNormal, 1.f - FMath::Exp(-8.f * H));
    else if (AirTime > .1f) Rot = AlignUp(Rot, LandingNormal, 1.f - FMath::Exp(-4.f * H));
    if (TryGrind()) return;
    if (bVertAir && Vel.Z < 0.f)
    {
        FCollisionQueryParams WallParams(SCENE_QUERY_STAT(SkateReentry), false, Rider);
        FHitResult Wall;
        if (GetWorld()->LineTraceSingleByChannel(Wall, Pos + Up() * 20.f, Pos - Up() * 12.f, ECC_Visibility, WallParams) && !Wall.bStartPenetrating &&
            FVector::DotProduct(FVector(Wall.ImpactNormal), Up()) > .7f)
        { Pos = Wall.ImpactPoint; TryLand(Wall.ImpactPoint, Wall.ImpactNormal); return; }
    }
    const FVector From = Pos + Up() * 9.f, To = From + Vel * H;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateTouchdown), false, Rider);
    // A surface counts as a landing when it faces up or faces the board (vert); anything else is a wall.
    auto Landable = [&](const FVector& N) { return N.Z > .5f || (N.Z > -.25f && FVector::DotProduct(N, Up()) > .6f); };   // never an overhang
    auto GroundBelow = [&](FHitResult& Down)
    {
        return GetWorld()->LineTraceSingleByChannel(Down, Pos + Up() * 40.f, Pos - Up() * 25.f, ECC_Visibility, Params) && !Down.bStartPenetrating && Landable(Down.ImpactNormal);
    };
    FHitResult Hit;
    if (GetWorld()->SweepSingleByChannel(Hit, From, To, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(9.f), Params))
    {
        const FVector N = Hit.ImpactNormal;
        FHitResult Down;
        if (Hit.bStartPenetrating)
        {
            // Already touching (an edge, a shoulder): land on what is under the board.
            if (GroundBelow(Down)) { Pos = Down.ImpactPoint; TryLand(Down.ImpactPoint, Down.ImpactNormal); return; }
        }
        else if (FVector::DotProduct(Vel, N) < 0.f && Landable(N))
        {
            Pos = Hit.Location - Up() * 9.f;
            TryLand(Hit.ImpactPoint, N);
            return;
        }
        else if (FVector::DotProduct(Vel, N) < 0.f)
        {
            // A wall in the board's way: glance off it.
            const float Into = -FVector::DotProduct(Vel, N);
            Vel += N * Into;
            if (Into > 1100.f) { StartBail(TEXT("flew into a wall")); return; }
        }
    }
    const FVector Before = Pos;
    Pos += Vel * H;
    FHitResult Wall;
    if (MoveBody(Wall))
    {
        const FVector N = Wall.ImpactNormal;
        FHitResult Down;
        // The body came down on something the board missed: put the board on it.
        if (N.Z > .5f && GroundBelow(Down)) { Pos = Down.ImpactPoint; TryLand(Down.ImpactPoint, Down.ImpactNormal); return; }
        const float Into = -FVector::DotProduct(Vel, N);
        if (Into > 0.f) Vel += N * Into * (N.Z < -.3f ? 1.f : 1.1f);
        if (Into > 1100.f && N.Z < .5f) { StartBail(TEXT("flew into a wall")); return; }
    }
    // Pinned (nothing to land on, nowhere to go): come off the board rather than hang there.
    AirStuck = FVector::DistSquared(Before, Pos) < .04f ? AirStuck + H : 0.f;
    if (AirStuck > .25f) { StartBail(TEXT("got stuck")); return; }
    if (Pos.Z < -6000.f) StartBail(TEXT("fell"));
}

void USkateComponent::TryLand(const FVector& Point, const FVector& InNormal)
{
    // A swept sphere reports an edge's normal on a lip or seam; the face under the board is what it lands on.
    FVector Normal = InNormal;
    {
        FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateLandFace), false, Rider);
        FHitResult Face;
        const FVector Along = FVector::DotProduct(InNormal, Up()) > .3f ? Up() : FVector(InNormal);
        if (GetWorld()->LineTraceSingleByChannel(Face, Point + Along * 15.f, Point - Along * 15.f, ECC_Visibility, Params) && !Face.bStartPenetrating)
            Normal = Face.ImpactNormal;
    }
    const FVector N = Normal.GetSafeNormal();
    const float UpErr = FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Up(), N)), -1.f, 1.f)));
    const FVector Tangent = FVector::VectorPlaneProject(Vel, N);
    const float Speed = Tangent.Size();
    const FVector Heading = FVector::VectorPlaneProject(Forward(), N).GetSafeNormal();
    const float YawErr = Speed > 1.f ? FMath::RadiansToDegrees(FMath::Acos(FMath::Clamp(float(FVector::DotProduct(Heading, Tangent / Speed)), -1.f, 1.f))) : 0.f;
    const float Impact = -FVector::DotProduct(Vel, N);
    const TCHAR* Why = nullptr;
    if (UpErr > 55.f) Why = TEXT("landed on the edge");
    else if (Speed > 150.f && YawErr > 60.f && YawErr < 120.f) Why = TEXT("landed sideways");
    else if (Trick.MovesBoard() && TrickProgress() < .78f) Why = TEXT("missed the catch");
    // Landing on a grab still held (after a moment of holding it) bails; one let go this frame just lets go.
    else if (!Grab.IsNone() && GrabTime > .2f && (In.bGrabLeft || In.bGrabRight)) Why = TEXT("still grabbing");
    else if (Impact > 1700.f) Why = TEXT("too big a drop");
    if (Why) { Pos = Point; StartBail(Why); return; }
    if (Speed > 20.f) bFakie = YawErr >= 90.f;
    // Rolling over a crest leaves the ground for a moment: no landing to show for it.
    const bool bSilent = !bPopped && AirTime < .15f && AirName.IsEmpty() && Grab.IsNone();
    // Land: keep the speed along the new surface, lose a little to the impact, and square the board to the line.
    Pos = Point;
    Rot = AlignUp(Rot, N, 1.f);
    if (Speed > 20.f)
    {
        const FVector Line = Tangent / Speed * (bFakie ? -1.f : 1.f);
        Rot = FRotationMatrix::MakeFromXZ(Line, N).ToQuat();
    }
    Vel = Tangent * FMath::Clamp(1.f - Impact * 1e-4f, .8f, .98f);
    // Landed a little sideways: the wheels scrub round to the line and it costs speed.
    const float Off = FMath::Min(YawErr, 180.f - YawErr);
    if (Off > 25.f) Vel *= 1.f - .3f * FMath::SmoothStep(25.f, 60.f, Off);
    // Name what was done in the air.
    FString Name;
    int32 Points = 0;
    if (Trick.IsValid() && bPopped)
    {
        Name = Trick.Name.ToString();
        if (FMath::Abs(Trick.Flips) >= 1.5f) Name = (FMath::Abs(Trick.Flips) >= 2.5f ? TEXT("Triple ") : TEXT("Double ")) + Name;
        Points += Trick.Points + 150 * FMath::Max(0, FMath::RoundToInt(FMath::Abs(Trick.Flips)) - 1);
    }
    const FString Spin = SpinName();
    if (!Spin.IsEmpty()) { Name = Name.IsEmpty() || Name == TEXT("Ollie") ? Spin : Spin + TEXT(" ") + Name; Points += 100 * FMath::FloorToInt((FMath::Abs(SpinTotal) + 30.f) / 180.f); }
    if (!Grab.IsNone() && GrabTotal > .12f && AirName.IsEmpty())
        AirName = Grab == TEXT("Double") ? TEXT("Double Grab") : Grab == TEXT("Nose") || Grab == TEXT("Tail") ? Grab.ToString() + TEXT(" Grab") : Grab.ToString();
    Grab = NAME_None;
    if (!AirName.IsEmpty()) { Name = Name.IsEmpty() ? AirName : Name + TEXT(" + ") + AirName; Points += 100 + int32(200.f * GrabTotal); }
    if (!Name.IsEmpty())
    {
        AddCombo(Name, Points);
        LastTrickName = FName(*Name);
        ++Landed;
    }
    AirName.Reset();
    Enter(ESkateMode::Ground);
    if (!bSilent) { LandTime = 0.f; PlayCue(TEXT("land"), FMath::Clamp(.35f + Impact / 800.f, .3f, 1.3f), FMath::FRandRange(.94f, 1.04f)); }
    // Coming down with the manual held (the right stick part-way back, or forward for a nose manual): it lands straight
    // into the manual on the wheels it came down on, instead of landing flat and tipping up after.
    const int32 Band = FSkateFlick::ManualBand(In.Right);
    if (Band != 0 && Speed > 80.f && !bManualLock)
    {
        bManual = true; bNoseManual = Band < 0; ManualHold = 0.f; bPushing = false;
        Balance = FMath::Clamp(Impact / 5000.f, 0.f, .12f);   // a heavy landing rocks it back a little
        DriftClock = .4f;
    }
}

FString USkateComponent::SpinName() const
{
    const FString Amount = Rounded(SpinTotal);
    if (Amount.IsEmpty()) return FString();
    // Frontside turns the chest toward the direction of travel first.
    const float Front = -StanceSign() * (bFakie ? -1.f : 1.f);
    return FString(FMath::Sign(SpinTotal) == Front ? TEXT("FS ") : TEXT("BS ")) + Amount;
}

bool USkateComponent::TryGrind()
{
    if (!RailSystem || RailSystem->Rails.IsEmpty() || LeaveRailCooldown > 0.f || Vel.Z > 60.f || AirTime < .05f) return false;
    // A flip still turning cannot be caught on a rail.
    if (Trick.MovesBoard() && TrickProgress() < .78f) return false;
    const FVector F = Forward(), N = Up();
    const FVector Probes[3] = {Pos + N * (DeckHeight - HangerDrop) + F * WheelX, Pos + N * (DeckHeight - HangerDrop) - F * WheelX, Pos + N * (DeckHeight - DeckThickness)};
    int32 Best = INDEX_NONE; float BestFlat = 1e9f, S = 0.f; FVector Point, Tangent;
    for (const FVector& P : Probes)
    {
        float PS; FVector PP, PT;
        const int32 R = RailSystem->FindNear(P, 24.f, -8.f, 22.f, PS, PP, PT);
        if (R == INDEX_NONE) continue;
        const float Flat = FVector2D::Distance(FVector2D(P), FVector2D(PP));
        if (Flat < BestFlat) { BestFlat = Flat; Best = R; S = PS; Point = PP; Tangent = PT; }
    }
    if (Best == INDEX_NONE) return false;
    const float Along = FVector::DotProduct(Vel, Tangent);
    if (FMath::Abs(Along) < 100.f) return false;
    RailDir = Along >= 0.f ? 1.f : -1.f;
    const FVector T = Tangent * RailDir;
    const FVector Flat = FVector(F.X, F.Y, 0.f).GetSafeNormal();
    const float Rel = FMath::RadiansToDegrees(FMath::Atan2(FVector::DotProduct(FVector::CrossProduct(T, Flat), FVector::UpVector), FVector::DotProduct(T, Flat)));
    const float AbsRel = FMath::Abs(Rel);
    bSlide = AbsRel > 35.f && AbsRel < 145.f;
    const bool bBackwards = AbsRel >= 145.f;
    // The right stick at contact picks the grind; toe side toward the rail is frontside.
    const FVector2D Stick = In.Right;
    const bool bUp = Stick.Y > .45f, bDown = Stick.Y < -.45f, bSide = FMath::Abs(Stick.X) > .45f;
    const float Toward = FVector::DotProduct(Rot.GetRightVector() * StanceSign(), FVector(Point.X - Pos.X, Point.Y - Pos.Y, 0.f));
    const TCHAR* Side = Toward > 0.f ? TEXT("FS ") : TEXT("BS ");
    const FSkateRail& Line = RailSystem->Rails[Best];
    FString Name;
    GrindPitch = 0.f;
    if (bSlide)
    {
        GrindYaw = Rel > 0.f ? 90.f : -90.f;
        Name = bUp ? TEXT("Noseslide") : bDown ? TEXT("Tailslide") : (Line.Kind == ESkateRailKind::Rail && bFakie ? TEXT("Lipslide") : TEXT("Boardslide"));
    }
    else
    {
        GrindYaw = bBackwards ? 180.f : 0.f;
        if (bDown && bSide) { Name = Stick.X * StanceSign() > 0.f ? TEXT("Smith") : TEXT("Feeble"); GrindPitch = 7.f; GrindYaw += Stick.X * StanceSign() > 0.f ? 14.f : -14.f; }
        else if (bUp && bSide) { Name = Stick.X * StanceSign() > 0.f ? TEXT("Crooked") : TEXT("Overcrook"); GrindPitch = -7.f; GrindYaw += Stick.X * StanceSign() > 0.f ? -16.f : 16.f; }
        else if (bDown) { Name = TEXT("5-0"); GrindPitch = 9.f; }
        else if (bUp) { Name = TEXT("Nosegrind"); GrindPitch = -9.f; }
        else Name = TEXT("50-50");
    }
    GrindName = FName(*((bBackwards && !bSlide ? FString(TEXT("Fakie ")) : FString(Side)) + Name + (Line.Kind == ESkateRailKind::Coping ? TEXT(" (coping)") : TEXT(""))));
    Rail = Best; RailS = S; RailSpeed = FMath::Abs(Along);
    // The way in counts ("Kickflip + 50-50"); a plain ollie onto the rail is just the grind.
    FString Way = Trick.IsValid() && Trick.Name != TEXT("Ollie") ? Trick.Name.ToString() : FString();
    // The turn that sets the board across the rail (a slide) or backwards on it is part of the grind, not a spin.
    const float Turned = SpinTotal - FMath::Sign(SpinTotal) * (bSlide ? 90.f : bBackwards ? 180.f : 0.f);
    const float SavedSpin = SpinTotal; SpinTotal = FMath::Sign(SpinTotal) == FMath::Sign(Turned) ? Turned : 0.f;
    const FString Spin = SpinName();
    SpinTotal = SavedSpin;
    if (!Spin.IsEmpty()) Way = Spin + (Way.IsEmpty() ? FString() : TEXT(" ") + Way);
    if (!AirName.IsEmpty()) Way += (Way.IsEmpty() ? FString() : FString(TEXT(" + "))) + AirName;
    if (!Way.IsEmpty()) AddCombo(Way, (Trick.IsValid() ? Trick.Points : 0) + 100);
    GrindFakie = bFakie;
    Trick = FSkateTrick(); SpinRate = 0.f; SpinTotal = 0.f;
    AirName.Reset();
    Enter(ESkateMode::Grind);
    ++Grinds;
    PlayCue(TEXT("land"), .6f, bSlide ? .9f : 1.35f);
    StepGrind(0.f);
    return true;
}

void USkateComponent::StepGrind(float H)
{
    const FSkateRail& Line = RailSystem->Rails[Rail];
    FVector Tangent; const FVector P = RailSystem->Sample(Rail, RailS, Tangent);
    const FVector T = Tangent * RailDir;
    const float Friction = bSlide ? 130.f + RailSpeed * .10f : 45.f + RailSpeed * .04f;
    RailSpeed += (-Gravity * T.Z - Friction) * H;
    GrindTime += H;
    if (H > 0.f && RailSpeed < 40.f) { LeaveGrind(false, 0.f); return; }
    RailS += RailDir * RailSpeed * H;
    if (RailS < 0.f || RailS > Line.Length()) { LeaveGrind(false, 0.f); return; }
    // Balance needle: it drifts and tips further the further it leans; the left stick pulls it back.
    DriftClock -= H;
    if (DriftClock <= 0.f) { Drift = (FMath::RandBool() ? 1.f : -1.f) * FMath::FRandRange(.35f, .8f); DriftClock = FMath::FRandRange(.5f, 1.1f); }
    Balance += (Drift + Balance * 1.2f + In.Left.X * 2.6f) * H;
    if (FMath::Abs(Balance) > 1.f) { LeaveGrind(false, FMath::Sign(Balance)); return; }
    const FVector UpV = (FVector::UpVector - T * T.Z).GetSafeNormal();
    const FVector Heading = FQuat(UpV, FMath::DegreesToRadians(GrindYaw)).RotateVector(T);
    Rot = FRotationMatrix::MakeFromXZ(Heading, UpV).ToQuat();
    // Trucks sit on the rail (deck top 7.3 cm above it); a slide puts the deck's underside on it. On a ledge the
    // board rides a few centimetres in from the edge.
    const float Drop = bSlide ? DeckThickness : HangerDrop;
    const FVector Inward = Line.IsSlideSurface() ? -Line.Side * 5.f : FVector::ZeroVector;
    Pos = P + Inward + UpV * (Drop - DeckHeight);
    Vel = T * RailSpeed;
    FHitResult Hit;
    if (H > 0.f && MoveBody(Hit) && FVector::DotProduct(FVector(Hit.ImpactNormal), T) < -.5f) LeaveGrind(false, 0.f);
}

void USkateComponent::LeaveGrind(bool bPopOff, float SideKick)
{
    if (Mode != ESkateMode::Grind) return;
    AddCombo(GrindName.ToString(), 100 + int32(150.f * GrindTime));
    LastRail = Rail; LeaveRailCooldown = .3f;
    FVector Tangent; RailSystem->Sample(Rail, RailS, Tangent);
    const FVector T = Tangent * RailDir;
    Vel = T * RailSpeed;
    if (SideKick != 0.f) Vel += FVector::CrossProduct(FVector::UpVector, T).GetSafeNormal() * SideKick * 110.f + FVector(0, 0, 60.f);
    // Out of a slide the board turns back to the line; a grind keeps its way round (backwards is fakie).
    const FVector Flat = FVector(T.X, T.Y, 0.f).GetSafeNormal();
    const bool bBack = bSlide ? GrindFakie : FMath::Abs(GrindYaw) > 90.f;
    Rot = FRotationMatrix::MakeFromXZ(bBack ? -Flat : Flat, FVector::UpVector).ToQuat();
    bFakie = bBack;
    if (!bPopOff) { bPopped = false; Trick = FSkateTrick(); SpinTotal = 0.f; }
    Enter(ESkateMode::Air);
}

void USkateComponent::Pop(const FSkateTrick& Flicked, const FVector& Base, float Scale)
{
    const FVector N = Mode == ESkateMode::Grind ? FVector::UpVector : Up();
    const float Speed = FMath::Lerp(PopMin, PopMax, Flicked.Strength) * Scale;
    const bool bFromGrind = Mode == ESkateMode::Grind;
    if (bFromGrind) LeaveGrind(true, 0.f);
    if (bManual) AddCombo(bNoseManual ? TEXT("Nose Manual") : TEXT("Manual"), 40 + int32(60.f * ManualHold));
    bManual = false;
    Vel = Base + N * Speed;
    PlayCue(TEXT("pop"), .75f + .35f * Flicked.Strength, FMath::FRandRange(.95f, 1.05f));
    bPopped = true; bNolliePop = Flicked.bNollie; PopTime = 0.f; bCaught = false;
    SpinTotal = 0.f; SpinRate = In.Left.X * SpinWindUp;   // the wind-up
    StartTrick(Flicked);
    Enter(ESkateMode::Air);
    Pos += N * 1.f;
}

void USkateComponent::StartTrick(const FSkateTrick& Flicked)
{
    Trick = Flicked;
    if (bFakie && !Trick.bNollie && Trick.IsValid()) Trick.Name = FName(*(FString(TEXT("Fakie ")) + Trick.Name.ToString()));
    TrickTime = 0.f; TrickStart = FlipBase = ShoveBase = CatchTime = 0.f;
    TrickDuration = Trick.MovesBoard() ? .34f + .07f * FMath::Abs(Trick.Flips) + .05f * FMath::Abs(Trick.Shove) / 180.f : 0.f;
    if (Trick.MovesBoard()) PlayCue(TEXT("flick"), .55f, FMath::FRandRange(.9f, 1.15f));
}

void USkateComponent::StartBail(const TCHAR* Why)
{
    if (Mode == ESkateMode::Bail || Mode == ESkateMode::Off) return;
    UE_LOG(LogTemp, Display, TEXT("SKATE bail: %s"), Why);
    ++Bails;
    EndCombo(false);
    ShownCombo = FString::Printf(TEXT("Bail — %s"), Why);
    PlayCue(TEXT("clatter"), 1.f); PlayCue(TEXT("fall"), .9f);
    const FTransform DeckNow = GetDeckWorld();
    BoardFreePos = DeckNow.GetLocation(); BoardFreeRot = DeckNow.GetRotation();
    BoardFreeVel = Vel * .9f + FVector(0, 0, 180.f);
    BoardFreeSpin = FVector(FMath::FRandRange(-540.f, 540.f), FMath::FRandRange(-360.f, 360.f), FMath::FRandRange(-420.f, 420.f));
    const FVector Carry = FVector(Vel.X, Vel.Y, FMath::Max(0.f, float(Vel.Z))) * .45f;
    Mode = ESkateMode::Bail; BailTime = 0.f;
    bManual = bPowerslide = bPushing = bBraking = false; Grab = NAME_None; Trick = FSkateTrick(); ManualTilt = 0.f;
    // The rider comes off and falls with CharacterMovement; the knock-down clips play from the skate clock.
    UCapsuleComponent* Capsule = Rider->GetCapsuleComponent();
    Capsule->SetCapsuleSize(SavedRadius, SavedHalf);
    SetMeshForRiding(false);
    const FVector Flat = FVector(Vel.X, Vel.Y, 0.f);
    Rider->SetActorLocationAndRotation(Pos + FVector(0, 0, SavedHalf + 4.f), FRotator(0, Flat.Size() > 20.f ? Flat.Rotation().Yaw : Forward().Rotation().Yaw, 0), true, nullptr, ETeleportType::TeleportPhysics);
    Movement()->SetMovementMode(MOVE_Falling);
    Movement()->Velocity = Carry * (Flat.Size() > 300.f ? 1.35f : 1.f);
    // At speed he tumbles on through his dive-roll and the momentum carries him; slow, he sits down hard.
    BailRoll = Flat.Size() > 300.f && Rider->GetDefinition() && Rider->GetDefinition()->FindAction(TEXT("Roll")) ? Rider->GetDefinition()->FindAction(TEXT("Roll"))->GetPlayLength() : 0.f;
    SavedBraking = Movement()->BrakingDecelerationWalking; SavedFriction = Movement()->GroundFriction;
    if (BailRoll > 0.f) { Movement()->BrakingDecelerationWalking = 250.f; Movement()->GroundFriction = .6f; }
    BoardRoot->SetUsingAbsoluteLocation(true); BoardRoot->SetUsingAbsoluteRotation(true);
}

void USkateComponent::StepBail(float Dt)
{
    BailTime += Dt;
    // The board tumbles on by itself, bouncing on whatever is below.
    BoardFreeVel.Z -= Gravity * Dt;
    FVector Next = BoardFreePos + BoardFreeVel * Dt;
    FHitResult Hit; FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateLooseBoard), false, Rider);
    if (GetWorld()->SweepSingleByChannel(Hit, BoardFreePos, Next, FQuat::Identity, ECC_Visibility, FCollisionShape::MakeSphere(5.f), Params))
    {
        Next = Hit.Location + FVector(Hit.ImpactNormal) * .5f;
        const FVector N = Hit.ImpactNormal;
        const float Into = -FVector::DotProduct(BoardFreeVel, N);
        // Bounce a little, then roll on: only a real knock slows it hard and kills the tumble.
        if (Into > 0.f) BoardFreeVel += N * Into * 1.3f;
        if (Into > 80.f) { BoardFreeVel *= .75f; BoardFreeSpin *= .5f; }
        else { BoardFreeVel = FVector::VectorPlaneProject(BoardFreeVel, N) * FMath::Exp(-.6f * Dt); BoardFreeSpin *= FMath::Exp(-6.f * Dt); }
    }
    BoardFreePos = Next;
    BoardFreeRot = (FQuat(FVector::UpVector, FMath::DegreesToRadians(BoardFreeSpin.Z * Dt)) * BoardFreeRot * FQuat(FVector::ForwardVector, FMath::DegreesToRadians(BoardFreeSpin.X * Dt))).GetNormalized();
    if (BailTime > (BailRoll > 0.f ? BailRoll + .15f : 2.35f)) EndBail();
}

void USkateComponent::EndBail()
{
    UCharacterMovementComponent* M = Movement();
    BoardRoot->SetUsingAbsoluteLocation(false); BoardRoot->SetUsingAbsoluteRotation(false);
    M->BrakingDecelerationWalking = SavedBraking; M->GroundFriction = SavedFriction;
    // Back on the board where he stands, stopped, facing the way he fell.
    Mode = ESkateMode::Off;
    const float Yaw = Rider->GetActorRotation().Yaw;
    if (!M->IsMovingOnGround())
    {
        M->FindFloor(M->UpdatedComponent->GetComponentLocation(), M->CurrentFloor, false);
        if (!M->CurrentFloor.IsWalkableFloor()) { BoardRoot->SetVisibility(false, true); M->SetMovementMode(MOVE_Falling); ++Serial; return; }
        M->SetMovementMode(MOVE_Walking);
    }
    M->Velocity = FVector::ZeroVector;
    Rider->SetActorRotation(FRotator(0, Yaw, 0));
    if (!Toggle()) { BoardRoot->SetVisibility(false, true); ++Serial; }
}

// ---------------------------------------------------------------------------------------------------- per frame

void USkateComponent::ReadInput(float Dt)
{
    Previous = In;
    if (bScripted) { In = Scripted; Flick.Power = -1.f; return; }
    APlayerController* PC = Rider ? Cast<APlayerController>(Rider->GetController()) : nullptr;
    FSkateInput I;
    if (!PC || Rider->IsMenuOpenForSkate()) { In = I; MouseStick = FVector2D::ZeroVector; return; }
    if (Rider->IsMouseReleased()) { In = I; return; }
    auto Down = [&](const FKey& K) { return PC->IsInputKeyDown(K); };
    I.Left.X = FMath::Clamp(PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX) + ((Down(EKeys::D) || Down(EKeys::Right)) ? 1.f : 0.f) - ((Down(EKeys::A) || Down(EKeys::Left)) ? 1.f : 0.f), -1.f, 1.f);
    I.Left.Y = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftY);
    // SceneViewport negates Gamepad_RightY (up reads negative); Flick-It wants up positive. The project's 0.25 dead
    // zone on each axis (DefaultInput.ini) squeezes the stick (half-way reads as a third, diagonals bend); Flick-It and
    // the manual's balance are laid out in real stick positions, so undo it and keep a small round dead zone instead.
    auto Unsqueeze = [](float A) { return FMath::Abs(A) > 1e-4f ? FMath::Sign(A) * (.25f + .75f * FMath::Abs(A)) : 0.f; };
    FVector2D Pad(Unsqueeze(PC->GetInputAnalogKeyState(EKeys::Gamepad_RightX)), -Unsqueeze(PC->GetInputAnalogKeyState(EKeys::Gamepad_RightY)));
    if (Pad.Size() < .15f) Pad = FVector2D::ZeroVector;
    Pad = Pad.GetClampedToMaxSize(1.f);
    // Mouse: hold the left button and move it like the right stick (skate. on PC).
    if (Down(EKeys::LeftMouseButton))
    {
        float DX = 0.f, DY = 0.f; PC->GetInputMouseDelta(DX, DY);
        const FVector2D Move = FVector2D(DX, DY) * MouseScale * FMath::Clamp(Rider->GetMouseSensitivity() / .4f, .25f, 4.f);
        // A quick flick of the mouse points the stick the way it moved (a hand swipes at 45 degrees, it does not trace
        // a chord across the stick's circle); slow movement moves the stick gradually (the load, a manual's tilt).
        if (Move.Size() > .22f) { MouseStick = Move.GetSafeNormal(); MouseQuiet = 0.f; }
        else
        {
            // A moment after a flick the stick springs back to the centre, as a thumbstick does when let go: a manual
            // after a kickflip then starts from the middle, not from the corner the flick left it in.
            MouseQuiet += Dt;
            if (bMouseSwiped && MouseQuiet > .1f) { MouseStick = FVector2D::ZeroVector; bMouseSwiped = false; }
            MouseStick = (MouseStick + Move).GetClampedToMaxSize(1.f);
        }
        // The swipe's speed is how hard it flicks (a gentle swipe about .3, a hard one 1).
        MousePower = Move.Size() > .22f ? FMath::Clamp(.3f + (Move.Size() - .22f) / 1.f, 0.f, 1.f) : -1.f;
    }
    else { MouseStick = FVector2D::ZeroVector; bMouseSwiped = false; }
    // Space: hold to load, release to pop (a straight ollie).
    FVector2D Keys = FVector2D::ZeroVector;
    if (Down(EKeys::SpaceBar)) { SpaceHeld = FMath::Max(0.f, SpaceHeld) + Dt; SpaceRelease = -1.f; Keys = FVector2D(0, -1); }
    else if (SpaceHeld >= 0.f) { SpaceHeld = -1.f; SpaceRelease = 0.f; }
    if (SpaceRelease >= 0.f) { SpaceRelease += Dt; Keys = SpaceRelease < .05f ? FVector2D(0, 1) : FVector2D::ZeroVector; if (SpaceRelease >= .05f) SpaceRelease = -1.f; }
    I.Right = Pad; Flick.Power = -1.f;
    bMouseRight = MouseStick.Size() > I.Right.Size();
    if (bMouseRight) { I.Right = MouseStick; Flick.Power = MousePower; }
    if (Keys.Size() > I.Right.Size()) { I.Right = Keys; Flick.Power = -1.f; bMouseRight = false; }
    I.bPush = Down(EKeys::W) || Down(EKeys::Up) || Down(EKeys::Gamepad_FaceButton_Bottom) || Down(EKeys::Gamepad_FaceButton_Left);
    I.bBrake = Down(EKeys::S) || Down(EKeys::Down) || Down(EKeys::Gamepad_FaceButton_Right);
    I.bPowerslide = Down(EKeys::C) || I.Left.Y < -.6f;
    I.bGrabLeft = Down(EKeys::Q) || PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis) > .35f;
    I.bGrabRight = Down(EKeys::E) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > .35f;
    In = I;
    if (PC->WasInputKeyJustPressed(EKeys::Gamepad_FaceButton_Top) && Mode == ESkateMode::Ground) Toggle();
}

void USkateComponent::TickComponent(float Dt, ELevelTick Type, FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Dt, Type, Tick);
    if (!Rider || Mode == ESkateMode::Off) return;
    ReadInput(Dt);
    if (Mode == ESkateMode::Bail) { StepBail(Dt); UpdateClip(Dt); UpdateBoard(Dt); UpdateAudio(Dt); return; }
    const float Speed = Vel.Size();
    LandTime += Dt; ComboFade = FMath::Max(0.f, ComboFade - Dt * .4f);
    // Flick-It
    const FSkateTrick Flicked = Flick.Update(In.Right, Dt, bGoofy);
    if (Flicked.IsValid() && bMouseRight) bMouseSwiped = true;
    if (Flicked.IsValid())
    {
        if (Mode == ESkateMode::Ground && !bPowerslide) Pop(Flicked, Vel, 1.f);
        else if (Mode == ESkateMode::Grind)
        {
            FVector Tangent; RailSystem->Sample(Rail, RailS, Tangent);
            Pop(Flicked, Tangent * RailDir * RailSpeed, .85f);
        }
        else if (Mode == ESkateMode::Air && bPopped && Flicked.Flips != 0.f && AirTime > .12f && (!Trick.MovesBoard() || TrickProgress() >= .7f) && FMath::Abs(Trick.Flips) < 2.5f)
        {
            // Another flick in the air adds a flip, turned on from where the board is.
            if (!Trick.IsValid()) { Trick = Flicked; FlipBase = ShoveBase = 0.f; }
            else { FlipBase = Trick.Flips; ShoveBase = Trick.Shove; Trick.Flips += FMath::Sign(Flicked.Flips); }
            Trick.Points += 150;
            TrickStart = TrickTime; CatchTime = 0.f; bCaught = false;
            TrickDuration = TrickTime + FlipDelay + .28f;
        }
    }
    if (Mode == ESkateMode::Air)
    {
        if (Trick.MovesBoard()) { if (TrickTime >= TrickDuration) CatchTime += Dt; TrickTime = FMath::Min(TrickTime + Dt, TrickDuration); }
        // The feet catch the board as the flip finishes.
        if (Trick.MovesBoard() && !bCaught && TrickProgress() >= .88f) { bCaught = true; PlayCue(TEXT("catch"), .6f); }
        // Grabs: a trigger held in the air; the right stick at the start picks the spot.
        const bool bLeft = In.bGrabLeft, bRight = In.bGrabRight;
        if (bGrabHeldAtStart && !bLeft && !bRight) bGrabHeldAtStart = false;
        if (Grab.IsNone() && !bGrabHeldAtStart && (bLeft || bRight) && AirTime > .15f && (!Trick.MovesBoard() || TrickTime >= TrickDuration))
        {
            // Regular stance: the left hand is the front hand.
            const bool bFront = (bLeft && !bRight) ? !bGoofy : (bRight && !bLeft) ? bGoofy : false;
            const bool bBoth = bLeft && bRight;
            const float Y = In.Right.Y;
            if (bBoth) Grab = TEXT("Double");
            else if (bFront) Grab = Y > .5f ? TEXT("Nose") : Y < -.5f ? TEXT("Method") : TEXT("Melon");
            else Grab = Y > .5f ? TEXT("Stalefish") : Y < -.5f ? TEXT("Tail") : TEXT("Indy");
            GrabTime = 0.f;
        }
        if (!Grab.IsNone())
        {
            GrabTime += Dt; GrabTotal += Dt;
            if (!bLeft && !bRight)
            {
                if (GrabTotal > .12f) AirName = Grab == TEXT("Double") ? TEXT("Double Grab") : Grab == TEXT("Nose") || Grab == TEXT("Tail") ? Grab.ToString() + TEXT(" Grab") : Grab.ToString();
                Grab = NAME_None;
            }
        }
    }
    if (Mode == ESkateMode::Ground)
    {
        // Manual: the right stick held part-way back (or forward for a nose manual), still.
        const int32 Band = FSkateFlick::ManualBand(In.Right);
        const float StickSpeed = (In.Right - Previous.Right).Size() / FMath::Max(Dt, 1e-3f);
        if (!bManual)
        {
            if (In.Right.Size() < .2f) bManualLock = false;   // after a scrape, let go of the stick before the next manual
            if (Band != 0 && Speed > 80.f && !bPowerslide && LandTime > .15f && StickSpeed < 2.5f && !bManualLock) ManualHold += Dt; else ManualHold = 0.f;
            if (ManualHold > .1f) { bManual = true; bNoseManual = Band < 0; Balance = 0.f; ManualHold = 0.f; bPushing = false; }
        }
        else
        {
            ManualHold += Dt;
            const float Mag = In.Right.Size();
            const float Tilt = (bNoseManual ? In.Right.Y : -In.Right.Y);
            DriftClock -= Dt;
            // A slow wander to correct and a gentle tip-over away from the middle: held attentively it lasts, left alone
            // it goes in about three seconds.
            if (DriftClock <= 0.f) { Drift = (FMath::RandBool() ? 1.f : -1.f) * FMath::FRandRange(.1f, .25f); DriftClock = FMath::FRandRange(.9f, 1.6f); }
            const float Control = Mag > .8f ? 0.f : (Tilt - .53f) * 4.f;
            Balance += (Drift + Balance * .35f + Control) * Dt;
            if (Mag < .2f || FMath::Abs(Balance) > 1.f || Speed < 40.f)
            {
                AddCombo(bNoseManual ? TEXT("Nose Manual") : TEXT("Manual"), 40 + int32(60.f * ManualHold));
                bManual = false; ManualHold = 0.f;
                if (FMath::Abs(Balance) > 1.f) { Vel *= .96f; bManualLock = true; }
            }
        }
        // Revert: the powerslide input right after a landing swings the board 180 on its wheels (fakie to regular).
        if (RevertLeft <= 0.f && LandTime < .35f && Speed > 150.f && In.bPowerslide && !Previous.bPowerslide)
        {
            RevertLeft = 180.f; RevertSign = FMath::Abs(In.Left.X) > .2f ? FMath::Sign(In.Left.X) : -StanceSign();
            AddCombo(TEXT("Revert"), 60);
        }
        // Powerslide: at speed, the left stick pulled down (C on keys), or braking hard at speed.
        if (RevertLeft <= 0.f && !bPowerslide && !bManual && Speed > 330.f && (In.bPowerslide || (In.bBrake && Speed > 450.f)) && LandTime > .35f)
        {
            bPowerslide = true; SlideAngle = 0.f; SlideTravel = Vel.GetSafeNormal();
            SlideSign = FMath::Abs(In.Left.X) > .2f ? FMath::Sign(In.Left.X) : StanceSign() * (bFakie ? -1.f : 1.f);
            bPushing = false;
        }
        bBraking = !bPowerslide && In.bBrake && Speed > 5.f;
        // Pushing: each press starts a stroke; holding keeps pushing.
        if (In.bPush && !bPushing && !bManual && !bPowerslide && !bBraking && Flick.Load < .2f && LandTime > .3f && Speed < PushMax)
        { bPushing = true; PushTime = 0.f; PushStroke = 0.f; bPushAgain = false; }
        if (bPushing)
        {
            const float Before = PushTime;
            if (PushTime >= PlantTime && PushTime < ReleaseTime)
            {
                // The planted foot stays put on the ground: the stroke advances with the distance rolled.
                PushStroke += Speed * Dt;
                PushTime = FMath::Max(PushTime + Dt * .5f, PlantTime + (ReleaseTime - PlantTime) * FMath::Clamp(PushStroke / StrokeLength, 0.f, 1.f));
            }
            else
            {
                // Pushing on, the foot swings back unhurried (the stroke itself is as quick as the ground under it).
                const bool bRecover = In.bPush && (PushTime >= ReleaseTime || bPushAgain);
                PushTime += Dt * (bRecover ? PushRecover : 1.f);
            }
            if (Before < PlantTime && PushTime >= PlantTime) { PushTime = PlantTime; PushStroke = 0.f; PlayCue(TEXT("push"), .55f, FMath::FRandRange(.92f, 1.08f)); }
            if (Before < PushSwingFrom && PushTime >= PushSwingFrom && In.bPush && Speed < PushMax && Flick.Load < .2f)
            { PushTime = PushSwingTo + (PushTime - PushSwingFrom); bPushAgain = true; ++Serial; }   // blends across (ClipBlend)
            if (PushTime >= PushLength) { if (In.bPush && Speed < PushMax) PushTime -= PushLength; else bPushing = false; }
            if (Flick.Load > .3f || bManual || bPowerslide || bBraking) bPushing = false;
        }
        // The combo ends after a moment of plain rolling.
        if (!bManual && !bPowerslide) ComboIdle += Dt; else ComboIdle = 0.f;
        if (ComboIdle > .35f && !Combo.IsEmpty()) EndCombo(true);
    }
    else ComboIdle = 0.f;
    UpdateClip(Dt);
    UpdateBoard(Dt);
    UpdateAudio(Dt);
}

// ---------------------------------------------------------------------------------------------------- animation

void USkateComponent::UpdateClip(float Dt)
{
    FName Next; float Time = 0.f; bool bLoop = false; float Blend = .12f;
    StanceClock += Dt; const float Clock = StanceClock;
    if (Mode == ESkateMode::Bail && BailRoll > 0.f) { Next = TEXT("Roll"); Time = FMath::Min(BailTime, BailRoll - .01f); Blend = .06f; }
    else if (Mode == ESkateMode::Bail)
    {
        if (BailTime < 1.f) { Next = TEXT("SitDown"); Time = BailTime; Blend = .08f; }
        else if (BailTime < 1.6f) { Next = TEXT("SitIdle"); Time = BailTime - 1.f; bLoop = true; }
        else { Next = TEXT("StandUp"); Time = BailTime - 1.6f; }
    }
    else if (Mode == ESkateMode::Ground)
    {
        if (LandTime < .35f && !bManual) { Next = TEXT("SkateLand"); Time = LandTime; Blend = .06f; }
        else if (bPowerslide) { Next = TEXT("SkatePowerslide"); Time = FMath::Min(SlideAngle / 82.f * .59f, .59f); }
        else if (bManual) { Next = bNoseManual ? TEXT("SkateNoseManual") : TEXT("SkateManual"); Time = FMath::Fmod(ManualHold, 1.f); bLoop = true; Blend = .16f; }
        else if (bPushing) { Next = TEXT("SkatePush"); Time = PushTime; bLoop = true; Blend = .16f; }
        else if (bBraking) { Next = TEXT("SkateBrake"); Time = FMath::Min(ClipName == TEXT("SkateBrake") ? ClipTime + Dt : 0.f, .39f); }
        else { Next = bFakie ? TEXT("SkateStanceFakie") : TEXT("SkateStance"); Time = FMath::Fmod(Clock, 2.f); bLoop = true; }
    }
    else if (Mode == ESkateMode::Air)
    {
        if (!Grab.IsNone()) { Next = FName(*(TEXT("SkateGrab") + Grab.ToString())); Time = FMath::Min(GrabTime, .49f); Blend = .08f; }
        else if (Trick.MovesBoard() && TrickDuration > 0.f && CatchTime < .09f && (TrickStart > 0.f || TrickTime >= .04f))
        {
            // The flip clip follows the board: the feet leave it, stay up while it turns and catch it as it finishes
            // (its own board turns from .08 to .36 s). A flip's pop shows the ollie's snap first.
            const float Local = TrickTime - TrickStart;
            Next = TEXT("SkateFlip"); Blend = .05f;
            Time = TrickTime < TrickDuration ? (Local < FlipDelay ? FMath::Lerp(.03f, .08f, Local / FlipDelay) : .08f + .28f * FlipProgress()) : .36f + CatchTime;
        }
        else if (bPopped && PopTime < .45f) { Next = bNolliePop ? TEXT("SkateNollie") : TEXT("SkateOllie"); Time = PopTime; Blend = .04f; }
        else { Next = TEXT("SkateAir"); Time = FMath::Fmod(AirTime, 1.f); bLoop = true; Blend = .15f; }
    }
    else if (Mode == ESkateMode::Grind)
    {
        const FString G = GrindName.ToString();
        Next = bSlide ? TEXT("SkateSlide") : (G.Contains(TEXT("5-0")) || G.Contains(TEXT("Smith")) || G.Contains(TEXT("Feeble"))) ? TEXT("SkateGrindTail")
            : (G.Contains(TEXT("Nosegrind")) || G.Contains(TEXT("Crooked")) || G.Contains(TEXT("Overcrook"))) ? TEXT("SkateGrindNose") : TEXT("SkateGrind");
        Time = FMath::Fmod(GrindTime, 1.f); bLoop = true; Blend = .07f;
    }
    // Pushing while rolling fakie is a switch push: the other stance's clip, so the foot drives the way he is going.
    const bool bSwitch = Next == TEXT("SkatePush") && bFakie;
    if (Next != ClipName || bSwitch != bClipSwitch) { ClipName = Next; bClipSwitch = bSwitch; ++Serial; }
    ClipTime = Time; bClipLoops = bLoop; ClipBlend = Blend;
    // Crouch (the load) and the carve lean only while simply riding.
    const bool bStance = Mode == ESkateMode::Ground && !bManual && !bPowerslide && !bPushing && LandTime > .2f;
    CrouchAlpha = FMath::FInterpTo(CrouchAlpha, bStance ? Flick.Load : 0.f, Dt, 18.f);
    const float Lean = bStance ? Steering * StanceSign() * (bFakie ? -1.f : 1.f) * FMath::Clamp(Vel.Size() / 450.f, 0.f, 1.f) * .9f : 0.f;
    LeanAlpha = FMath::FInterpTo(LeanAlpha, Lean, Dt, 7.f);
    // Limb contacts (goofy clips are mirrored, so the left and right limbs swap).
    const FName Key = bGoofy != bClipSwitch && ClipName.ToString().StartsWith(TEXT("Skate")) ? FName(ClipName.ToString() + TEXT("Goofy")) : ClipName;
    float Want[4] = {0.f, 0.f, 0.f, 0.f};
    if (Mode != ESkateMode::Bail)
    {
        if (const TArray<FVector4f>* Spans = ClipContacts.Find(Key))
        {
            for (const FVector4f& S : *Spans)
            {
                const float Edge = .05f;
                const float W = FMath::Clamp((ClipTime - S.Y + Edge) / Edge, 0.f, 1.f) * FMath::Clamp((S.Z - ClipTime + Edge) / Edge, 0.f, 1.f);
                Want[int32(S.X)] = FMath::Max(Want[int32(S.X)], W);
            }
        }
        else
        {
            // Without the build file: feet on the deck except the pushing foot mid-stroke and both feet in a flip.
            Want[0] = Want[1] = 1.f;
            const int32 Back = bGoofy != bClipSwitch ? 0 : 1;
            if (ClipName == TEXT("SkatePush") && ClipTime > .1f && ClipTime < .9f) Want[Back] = 0.f;
            if (ClipName == TEXT("SkateBrake") && ClipTime > .08f) Want[Back] = 0.f;
            if (ClipName == TEXT("SkateFlip") && ClipTime > .05f && ClipTime < .38f) Want[0] = Want[1] = 0.f;
        }
    }
    for (int32 L = 0; L < 4; ++L) Contact[L] = FMath::FInterpConstantTo(Contact[L], Want[L], Dt, 14.f);
}

void USkateComponent::UpdateBoard(float Dt)
{
    if (Mode == ESkateMode::Bail)
    {
        BoardRoot->SetWorldLocationAndRotation(BoardFreePos - BoardFreeRot.RotateVector(FVector(0, 0, DeckHeight)), BoardFreeRot);
        Deck->SetRelativeLocationAndRotation(FVector(0, 0, DeckHeight), FQuat::Identity);
        return;
    }
    BoardRoot->SetRelativeLocationAndRotation(FVector(0, 0, -BodyLift), FQuat::Identity);
    // Pitch about a wheel line (pop, manual, 5-0 / nosegrind), flips and shoves about the deck centre.
    float Pitch = 0.f; FVector Pivot = FVector(-WheelX, 0, 0);
    if (Mode == ESkateMode::Air && bPopped) { Pitch = PopPitch(PopTime) * (bNolliePop ? -1.f : 1.f); if (bNolliePop) Pivot.X = WheelX; }
    // Manual tilt, eased: rocking up into a manual, setting the nose down after it, and tipping onto the back (or front)
    // wheels on the way down with the manual held, so the board lands into it.
    float TiltGoal = 0.f;
    if (Mode == ESkateMode::Ground && bManual) TiltGoal = (11.f + Balance * 4.f) * (bNoseManual ? -1.f : 1.f);
    else if (Mode == ESkateMode::Air && Vel.Z < 0.f && Grab.IsNone() && (!bPopped || PopTime > .24f) && (!Trick.MovesBoard() || TrickTime >= TrickDuration))
    {
        const int32 Band = FSkateFlick::ManualBand(In.Right);
        TiltGoal = Band > 0 ? 9.f : Band < 0 ? -9.f : 0.f;
    }
    ManualTilt = FMath::FInterpTo(ManualTilt, TiltGoal, Dt, 14.f);
    if (Mode != ESkateMode::Grind && Pitch == 0.f && FMath::Abs(ManualTilt) > .05f) { Pitch = ManualTilt; if (ManualTilt < 0.f) Pivot.X = WheelX; }
    if (Mode == ESkateMode::Grind && GrindPitch != 0.f) { Pitch = GrindPitch; Pivot = FVector(GrindPitch > 0.f ? -WheelX : WheelX, 0, DeckHeight - HangerDrop); }
    float Roll = 0.f, Yaw = 0.f;
    if (Mode == ESkateMode::Air && Trick.MovesBoard() && TrickDuration > 0.f)
    {
        const float U = Ease(FlipProgress());
        Roll = -StanceSign() * 360.f * (FlipBase + (Trick.Flips - FlipBase) * U);   // kickflip: the toe edge rises first
        Yaw = StanceSign() * (ShoveBase + (Trick.Shove - ShoveBase) * U);           // backside shove: the tail swings behind the heels
    }
    // Carving leans the deck over its trucks (toe or heel edge down), a few degrees at speed.
    DeckLean = FMath::FInterpTo(DeckLean, Mode == ESkateMode::Ground && !bPowerslide ? Steering * 7.f * FMath::Clamp(Vel.Size() / 500.f, 0.f, 1.f) * (bFakie ? -1.f : 1.f) : 0.f, Dt, 8.f);
    Roll += DeckLean;
    const FQuat PitchQ = FRotator(Pitch, 0, 0).Quaternion();
    const FQuat FlipQ = FQuat(FVector::UpVector, FMath::DegreesToRadians(Yaw)) * FQuat(FVector::ForwardVector, FMath::DegreesToRadians(Roll));
    const FVector Rest(0, 0, DeckHeight), Centre(0, 0, DeckHeight - 2.f);
    const FVector Flipped = Centre + FlipQ.RotateVector(Rest - Centre);
    const FVector Placed = Pivot + PitchQ.RotateVector(Flipped - Pivot);
    Deck->SetRelativeLocationAndRotation(Placed, PitchQ * FlipQ);
    const FQuat LeanQ(FVector::ForwardVector, FMath::DegreesToRadians(DeckLean));
    DeckCarry = FTransform(PitchQ * LeanQ, Pivot + PitchQ.RotateVector(Centre + LeanQ.RotateVector(Rest - Centre) - Pivot));
    // Trucks steer with the lean; wheels roll with the distance.
    const bool bRolling = Mode == ESkateMode::Ground;
    WheelAngle = FMath::Fmod(WheelAngle + (bRolling ? FMath::RadiansToDegrees(Vel.Size() * Dt / WheelRadius) * (bFakie ? -1.f : 1.f) : 0.f), 360.f);
    for (int32 I = 0; I < Trucks.Num(); ++I) Trucks[I]->SetRelativeRotation(FRotator(0, (I == 0 ? 0.f : 180.f) + Steering * 6.f, I == 0 ? -DeckLean : DeckLean));
    for (int32 I = 0; I < Wheels.Num(); ++I) Wheels[I]->SetRelativeRotation(FRotator(I < 2 ? -WheelAngle : WheelAngle, 0, 0));
}

FTransform USkateComponent::GetDeckWorld() const
{
    return Deck ? FTransform(Deck->GetComponentQuat(), Deck->GetComponentLocation()) : FTransform::Identity;
}

FTransform USkateComponent::GetDeckCarryWorld() const
{
    if (!BoardRoot) return FTransform::Identity;
    return DeckCarry * FTransform(BoardRoot->GetComponentQuat(), BoardRoot->GetComponentLocation());
}

float USkateComponent::FlipProgress() const
{
    const float Span = TrickDuration - TrickStart - FlipDelay;
    return Span > 0.f ? FMath::Clamp((TrickTime - TrickStart - FlipDelay) / Span, 0.f, 1.f) : 1.f;
}

FTransform USkateComponent::GetDeckRestWorld() const
{
    if (!BoardRoot) return FTransform::Identity;
    const FTransform Root(BoardRoot->GetComponentQuat(), BoardRoot->GetComponentLocation());
    return FTransform(FVector(0, 0, DeckHeight)) * Root;
}

// ---------------------------------------------------------------------------------------------------- score & HUD

void USkateComponent::AddCombo(const FString& Name, int32 Points)
{
    if (Name.IsEmpty()) return;
    Combo.Add(Name); ComboPoints += Points; ComboFade = 1.f; ComboIdle = 0.f;
    ShownCombo = FString::Join(Combo, TEXT(" + "));
}

void USkateComponent::EndCombo(bool bLanded)
{
    if (Combo.IsEmpty()) return;
    const int32 Total = ComboPoints * Combo.Num();
    ShownCombo = FString::Join(Combo, TEXT(" + ")) + (bLanded ? FString::Printf(TEXT("   %d"), Total) : TEXT("   bail"));
    if (bLanded) Score += Total;
    Combo.Reset(); ComboPoints = 0; ComboFade = 1.f;
}

FString USkateComponent::GetComboLine() const
{
    if (Mode == ESkateMode::Air)
    {
        FString Live = Trick.IsValid() ? Trick.Name.ToString() : FString();
        const FString Spin = SpinName();
        if (!Spin.IsEmpty()) Live = Spin + (Live.IsEmpty() ? FString() : TEXT(" ") + Live);
        if (!Grab.IsNone()) Live += (Live.IsEmpty() ? FString() : FString(TEXT(" + "))) + Grab.ToString();
        if (!Live.IsEmpty()) return (Combo.IsEmpty() ? FString() : FString::Join(Combo, TEXT(" + ")) + TEXT(" + ")) + Live;
    }
    if (Mode == ESkateMode::Grind) return (Combo.IsEmpty() ? FString() : FString::Join(Combo, TEXT(" + ")) + TEXT(" + ")) + GrindName.ToString();
    if (bManual) return (Combo.IsEmpty() ? FString() : FString::Join(Combo, TEXT(" + ")) + TEXT(" + ")) + (bNoseManual ? TEXT("Nose Manual") : TEXT("Manual"));
    return ShownCombo;
}

float USkateComponent::GetComboAlpha() const
{
    return Mode == ESkateMode::Grind || bManual || (Mode == ESkateMode::Air && (Trick.IsValid() || !Grab.IsNone())) ? 1.f : FMath::Clamp(ComboFade * 1.6f, 0.f, 1.f);
}

FString USkateComponent::GetStatus() const
{
    switch (Mode)
    {
    case ESkateMode::Air: return TEXT("Airborne");
    case ESkateMode::Grind: return bSlide ? TEXT("Sliding") : TEXT("Grinding");
    case ESkateMode::Bail: return TEXT("Bail");
    default: break;
    }
    if (bPowerslide) return TEXT("Powerslide");
    if (bManual) return bNoseManual ? TEXT("Nose manual") : TEXT("Manual");
    if (bPushing) return TEXT("Pushing");
    if (bBraking) return TEXT("Braking");
    return bFakie ? TEXT("Rolling fakie") : TEXT("Rolling");
}

bool USkateComponent::GetCameraYaw(float& Yaw) const
{
    if (Mode == ESkateMode::Off || Mode == ESkateMode::Bail) return false;
    const FVector Flat(Vel.X, Vel.Y, 0.f);
    if (Flat.Size() < 150.f) return false;
    Yaw = Flat.Rotation().Yaw;
    return true;
}

FString USkateComponent::GetLoopState() const
{
    FString Out;
    for (int32 I = 0; I < Loops.Num(); ++I)
        Out += FString::Printf(TEXT("%.3f %.3f "), Loops[I] && Loops[I]->IsPlaying() ? LoopVolume[I] : 0.f, Loops[I] ? Loops[I]->PitchMultiplier : 1.f);
    return Out;
}

FString USkateComponent::GetDebug() const
{
    const UCharacterMovementComponent* M = Movement();
    return FString::Printf(TEXT("mm=%d/%d mode=%d speed=%.0f fakie=%d manual=%d slide=%d push=%d clip=%s t=%.2f load=%.2f trick=%s flick=[%s] rail=%d spin=%.0f air=%.2f z=%.0f surf=%s/%.1f lt=%.2f ps=%d rv=%.0f up=(%.2f,%.2f,%.2f)"),
        M ? int32(M->MovementMode) : -1, M ? int32(M->CustomMovementMode) : -1, int32(Mode), Vel.Size(), bFakie, bManual, bPowerslide, bPushing, *ClipName.ToString(), ClipTime, Flick.Load, *Trick.Name.ToString(), *Flick.LastDebug, Rail, SpinTotal, AirTime, Pos.Z, *SurfaceName, SurfaceDrag, LandTime, In.bPowerslide, RevertLeft, Up().X, Up().Y, Up().Z);
}
