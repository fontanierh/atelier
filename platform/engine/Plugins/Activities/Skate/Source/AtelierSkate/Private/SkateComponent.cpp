#include "SkateComponent.h"
#include "SkateRails.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "GameFramework/Character.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "AtelierFX.h"
#include "Components/AudioComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundAttenuation.h"

namespace
{
    constexpr float DeckHeight=9.05f, WheelX=18.f, WheelY=9.3f, WheelRadius=2.65f, DeckThickness=1.2f;
    constexpr float Radius=22.f, Half=55.f, Clearance=22.f, MouseScale=1.f/40.f;
}

USkateComponent::USkateComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

UCharacterMovementComponent* USkateComponent::Movement() const { return Rider ? Rider->GetCharacterMovement() : nullptr; }

void USkateComponent::Initialize(ACharacter* Character)
{
    Rider = Character;
    RiderApi = Cast<ISkateRider>(Character);
    checkf(RiderApi, TEXT("USkateComponent: the rider must implement ISkateRider"));
    RailSystem = GetWorld()->GetSubsystem<USkateRailSubsystem>();
    AddTickPrerequisiteComponent(Rider->GetCharacterMovement());
    AddTickPrerequisiteActor(Rider);
    Rider->GetMesh()->AddTickPrerequisiteComponent(this);
    BoardRoot = NewObject<USceneComponent>(Rider, TEXT("SkateBoardRoot"));
    BoardRoot->SetupAttachment(Rider->GetRootComponent()); BoardRoot->RegisterComponent();
    const USkateSettings* Settings = GetDefault<USkateSettings>();
    auto Load = [](const FSoftObjectPath& Path) { return Path.IsNull() ? nullptr : Cast<UStaticMesh>(Path.TryLoad()); };
    auto Part = [&](const TCHAR* Name, UStaticMesh* Mesh, USceneComponent* Parent)
    {
        auto* C = NewObject<UStaticMeshComponent>(Rider, Name);
        C->SetupAttachment(Parent); C->SetStaticMesh(Mesh);
        C->SetCollisionEnabled(ECollisionEnabled::NoCollision); C->SetGenerateOverlapEvents(false); C->SetCanEverAffectNavigation(false);
        C->SetRenderCustomDepth(true); C->SetCustomDepthStencilValue(2);
        C->RegisterComponent(); return C;
    };
    UStaticMesh* DeckMesh = Load(Settings->DeckMesh);
    UStaticMesh* TruckMesh = Load(Settings->TruckMesh);
    UStaticMesh* WheelMesh = Load(Settings->WheelMesh);
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
    bAvailable = DeckMesh && TruckMesh && WheelMesh;
    LoadSounds();
    UE_LOG(LogTemp, Display, TEXT("SKATE available=%d board=%s"), bAvailable, DeckMesh ? *DeckMesh->GetName() : TEXT("none"));
}

void USkateComponent::LoadSounds()
{
    const USkateSettings* Settings = GetDefault<USkateSettings>();
    const FString Folder = Settings->SoundFolder;
    auto Load = [&Folder](const FString& Name)
    {
        return Folder.IsEmpty() ? nullptr : LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *Folder, *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
    };
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
    for (const FSoftObjectPath& Path : Settings->FallSounds)
        if (USoundWave* W = Cast<USoundWave>(Path.TryLoad()))
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

void USkateComponent::SetGoofy(bool bNewGoofy)
{
    if (bGoofy == bNewGoofy) return;
    bGoofy = bNewGoofy;
    if (bRetailActive) ConfigureRetail();
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
        RiderApi->PrepareToSkate();
        SavedRadius = Capsule->GetUnscaledCapsuleRadius(); SavedHalf = Capsule->GetUnscaledCapsuleHalfHeight();
        SavedMeshLocation = Rider->GetMesh()->GetRelativeLocation(); SavedMeshRotation = Rider->GetMesh()->GetRelativeRotation().Quaternion();
        SavedStep = M->MaxStepHeight;
        Pos = Rider->GetActorLocation() - FVector(0, 0, Capsule->GetScaledCapsuleHalfHeight() + M->CurrentFloor.FloorDist);
        const FVector Normal = M->CurrentFloor.HitResult.bBlockingHit ? FVector(M->CurrentFloor.HitResult.ImpactNormal) : FVector::UpVector;
        Rot = AlignUp(FRotator(0, Rider->GetActorRotation().Yaw, 0).Quaternion(), Normal, 1.f);
        // Mount along the actual running direction, including while the character is still turning.
        Vel = FVector::VectorPlaneProject(M->Velocity, Normal);
        if (Vel.SizeSquared()>FMath::Square(30.f)) Rot=FRotationMatrix::MakeFromXZ(Vel.GetSafeNormal(),Normal).ToQuat();
        Capsule->SetCapsuleSize(Radius, Half);
        BodyLift = Clearance + Half;
        SetMeshForRiding(true);
        M->SetMovementMode(MOVE_Custom, MovementMode);
        ResetInput(); ShownCombo.Reset(); ComboFade=0;
        Mode=ESkateMode::Ground;
        Rider->SetActorLocationAndRotation(Pos + Up()*BodyLift,Rot,false,nullptr,ETeleportType::TeleportPhysics);
        BoardRoot->SetVisibility(true, true);
        if (!StartRetailRuntime()) { StowImmediately(); return false; }
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
    SuspendRetailRuntime();
    if (Mode == ESkateMode::Off || !Rider) return;
    UCharacterMovementComponent* M = Movement();
    ShownCombo.Reset(); ComboFade=0;
    Mode = ESkateMode::Off;
    bManual = bPowerslide = bPushing = bBraking = false;
    BoardRoot->SetVisibility(false, true);
    for (int32 I = 0; I < Loops.Num(); ++I) { if (Loops[I]) Loops[I]->Stop(); LoopVolume[I] = 0.f; }
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
    {
        Deck->SetRelativeTransform(FTransform::Identity);
        for (int32 I=0; I<Trucks.Num(); ++I)
            Trucks[I]->SetRelativeTransform(FTransform(FRotator(0,I==0?0.f:180.f,0),FVector(I==0?WheelX:-WheelX,0,-DeckThickness)));
        for (int32 I=0; I<Wheels.Num(); ++I)
            Wheels[I]->SetRelativeTransform(FTransform(FVector(0,I%2==0?-WheelY:WheelY,-(DeckHeight-DeckThickness-WheelRadius))));
    }
    ++Serial;
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
    ResetInput();
    Pos = GroundPoint; Rot = FRotator(0, Yaw, 0).Quaternion(); Vel = FVector::ZeroVector; bFakie = false;
    Mode=ESkateMode::Ground;
    Rider->SetActorLocationAndRotation(Pos + Up() * BodyLift, Rot, false, nullptr, ETeleportType::TeleportPhysics);
    if (!StartRetailRuntime()) { StowImmediately(); return false; }
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

void USkateComponent::ReadInput(float Dt)
{
    if (bScripted) { In = Scripted; return; }
    APlayerController* PC = Rider ? Cast<APlayerController>(Rider->GetController()) : nullptr;
    FSkateInput I;
    if (!PC || RiderApi->IsSkateInputBlocked()) { In = I; MouseStick = FVector2D::ZeroVector; return; }
    if (RiderApi->IsSkateMouseFree()) { In = I; return; }
    auto Down = [&](const FKey& K) { return PC->IsInputKeyDown(K); };
    I.Left.X = FMath::Clamp(PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftX) + ((Down(EKeys::D) || Down(EKeys::Right)) ? 1.f : 0.f) - ((Down(EKeys::A) || Down(EKeys::Left)) ? 1.f : 0.f), -1.f, 1.f);
    I.Left.Y = PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftY);
    // SceneViewport negates Gamepad_RightY (up reads negative); Flick-It wants up positive. The project's 0.25 dead
    // zone on each axis (DefaultInput.ini) squeezes the stick (half-way reads as a third, diagonals bend); Flick-It and
    // the manual's balance are laid out in real stick positions, so undo it and keep a small round dead zone instead.
    auto Unsqueeze = [](float A) { return FMath::Abs(A) > 1e-4f ? FMath::Sign(A) * (.25f + .75f * FMath::Abs(A)) : 0.f; };
    I.Left.X=Unsqueeze(I.Left.X); I.Left.Y=Unsqueeze(I.Left.Y);
    FVector2D Pad(Unsqueeze(PC->GetInputAnalogKeyState(EKeys::Gamepad_RightX)), -Unsqueeze(PC->GetInputAnalogKeyState(EKeys::Gamepad_RightY)));
    // Mouse: hold the left button and move it like the right stick (skate. on PC).
    if (Down(EKeys::LeftMouseButton))
    {
        float DX = 0.f, DY = 0.f; PC->GetInputMouseDelta(DX, DY);
        const FVector2D Move = FVector2D(DX, DY) * MouseScale * FMath::Clamp(RiderApi->GetSkateMouseSensitivity() / .4f, .25f, 4.f);
        // A quick flick of the mouse points the stick the way it moved (a hand swipes at 45 degrees, it does not trace
        // a chord across the stick's circle); slow movement moves the stick gradually (the load, a manual's tilt).
        if (Move.Size() > .22f) { MouseStick = Move.GetSafeNormal(); MouseQuiet = 0.f; bMouseSwiped=MouseStick.Y>0 || FMath::Abs(MouseStick.X)>.5; }
        else
        {
            // A moment after a flick the stick springs back to the centre, as a thumbstick does when let go: a manual
            // after a kickflip then starts from the middle, not from the corner the flick left it in.
            MouseQuiet += Dt;
            if (bMouseSwiped && MouseQuiet > .1f) { MouseStick = FVector2D::ZeroVector; bMouseSwiped = false; }
            MouseStick = (MouseStick + Move).GetClampedToMaxSize(1.f);
        }
    }
    else { MouseStick = FVector2D::ZeroVector; bMouseSwiped = false; }
    // Space: hold to load, release to pop (a straight ollie).
    FVector2D Keys = FVector2D::ZeroVector;
    if (Down(EKeys::SpaceBar)) { SpaceHeld = FMath::Max(0.f, SpaceHeld) + Dt; SpaceRelease = -1.f; Keys = FVector2D(0, -1); }
    else if (SpaceHeld >= 0.f) { SpaceHeld = -1.f; SpaceRelease = 0.f; }
    if (SpaceRelease >= 0.f) { SpaceRelease += Dt; Keys = SpaceRelease < .05f ? FVector2D(0, 1) : FVector2D::ZeroVector; if (SpaceRelease >= .05f) SpaceRelease = -1.f; }
    I.Right = Pad;
    if (MouseStick.Size() > I.Right.Size()) I.Right = MouseStick;
    if (Keys.Size() > I.Right.Size()) I.Right = Keys;
    I.bPush = Down(EKeys::W) || Down(EKeys::Up) || Down(EKeys::Gamepad_FaceButton_Bottom) || Down(EKeys::Gamepad_FaceButton_Left);
    I.bBrake = Down(EKeys::S) || Down(EKeys::Down) || Down(EKeys::Gamepad_FaceButton_Right);
    I.bPowerslide = Down(EKeys::C);
    I.bGrabLeft = Down(EKeys::Q) || PC->GetInputAnalogKeyState(EKeys::Gamepad_LeftTriggerAxis) > .35f;
    I.bGrabRight = Down(EKeys::E) || PC->GetInputAnalogKeyState(EKeys::Gamepad_RightTriggerAxis) > .35f;
    In = I;
}

FString USkateComponent::GetStatus() const
{
    if (bRetailActive && RetailPose.IsEmpty()) return TEXT("Loading skater");
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
    if (GetSpeed()<15.f) return TEXT("On board");
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

void USkateComponent::ResetInput()
{
    In={}; MouseStick=FVector2D::ZeroVector; MouseQuiet=0; bMouseSwiped=false;
    SpaceHeld=SpaceRelease=-1.f;
}
void USkateComponent::PhysSkate(float Dt) { StepRetailRuntime(Dt); }
void USkateComponent::Launch(const FVector& Velocity) { LaunchRetail(Velocity); }
void USkateComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Dt,Type,Tick);
    if (IsRiding()) UpdateAudio(Dt);
    // Start the skating worker a moment after play begins, so it is ready by the first mount (SkateRuntime.cpp).
    if (bAvailable && Rider && !RetailRuntime && !bRetailPreloaded && GetWorld()->GetTimeSeconds()>2.) PreloadRetailRuntime();
    PollIdleRetail();
}
FTransform USkateComponent::GetDeckWorld() const { return Deck ? Deck->GetComponentTransform() : FTransform::Identity; }
float USkateComponent::GetComboAlpha() const { return FMath::Clamp(ComboFade*1.6f,0.f,1.f); }
FString USkateComponent::GetDebug() const
{
    const UCharacterMovementComponent* M=Movement();
    return FString::Printf(TEXT("mm=%d/%d mode=%d speed=%.0f fakie=%d manual=%d slide=%d push=%d ps=%d yaw=%.1f z=%.1f skin_clearance=%.2f skin_lift=%.2f"),
        M?int32(M->MovementMode):-1,M?int32(M->CustomMovementMode):-1,int32(Mode),Vel.Size(),bFakie,bManual,bPowerslide,bPushing,
        In.bPowerslide,Rot.Rotator().Yaw,Pos.Z,RetailFloorClearance,BailVisualLift)+(bRetailActive?TEXT(" retail=")+GetRetailState():FString());
}
