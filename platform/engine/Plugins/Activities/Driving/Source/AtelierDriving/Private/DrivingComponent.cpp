#include "DrivingComponent.h"

#include "Components/CapsuleComponent.h"
#include "Components/AudioComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundAttenuation.h"
#include "Sound/SoundWave.h"
#include "UObject/ConstructorHelpers.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Simulation/SimulationKart.h"
#include "Simulation/SimulationVehicle.h"

using namespace atelier::driving;

namespace
{
FVector ToUE(const Vec3& V)
{
    return FVector(V.z, V.x, V.y) * 100.f;
}

FVector ToUEDir(const Vec3& V)
{
    return FVector(V.z, V.x, V.y);
}

Vec3 ToSim(const FVector& V)
{
    return Vec3{float(V.Y) * .01f, float(V.Z) * .01f, float(V.X) * .01f};
}

Vec3 ToSimDir(const FVector& V)
{
    return Vec3{float(V.Y), float(V.Z), float(V.X)};
}

FQuat ToUE(const Quat& Q)
{
    return FQuat(Q.z, Q.x, Q.y, Q.w);
}

Quat ToSim(const FQuat& Q)
{
    return Quat{float(Q.Y), float(Q.Z), float(Q.X), float(Q.W)};
}

/** The simulation's only world interface: a ray per wheel, plus the body rays the step makes for the chassis. */
struct FCarGround final : Ground
{
    UWorld* World = nullptr;
    const AActor* Ignore = nullptr;
    ECollisionChannel Channel = ECC_Visibility;

    FCarGround() = default;
    FCarGround(UWorld* InWorld, const AActor* InIgnore, ECollisionChannel InChannel)
        : World(InWorld), Ignore(InIgnore), Channel(InChannel)
    {}

    bool hit(Vec3 Origin, Vec3 Dir, float MaxDistance, GroundHit& Out) const override
    {
        if (!World || MaxDistance <= 0.f)
        {
            return false;
        }
        const FVector From = ToUE(Origin);
        const FHitResult Result = [&]
        {
            FHitResult Hit;
            FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingGround), false, Ignore);
            World->LineTraceSingleByChannel(Hit, From, From + ToUEDir(Dir) * (MaxDistance * 100.f), Channel, Params);
            return Hit;
        }();
        if (!Result.bBlockingHit && !Result.bStartPenetrating)
        {
            return false;
        }
        Out.distance = FVector::Dist(From, Result.ImpactPoint) * .01f;
        Out.normal = ToSimDir(Result.ImpactNormal);
        if (Out.normal.y <= 0.f)
        {
            return false;
        }
        Out.surface = SurfaceGrip{};
        return true;
    }
};
} // namespace

struct FDrivingCar
{
    explicit FDrivingCar(const VehicleSpec& InSpec) : Chassis(InSpec) {}
    Vehicle Chassis;
    float Accumulator = 0.f;
};

UDrivingComponent::UDrivingComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.bStartWithTickEnabled = true;
    static ConstructorHelpers::FObjectFinder<UStaticMesh> Column(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
    ColumnMesh = Column.Object;
}

UDrivingComponent::~UDrivingComponent() = default;

void UDrivingComponent::Initialize(ACharacter* InRider)
{
    Rider = InRider;
    if (!Rider || CarRoot)
    {
        return;
    }
    CarRoot = NewObject<USceneComponent>(this, TEXT("CarRoot"));
    Rider->AddInstanceComponent(CarRoot);
    CarRoot->RegisterComponent();
    CarRoot->AttachToComponent(Rider->GetRootComponent(), FAttachmentTransformRules::KeepRelativeTransform);
    Body = NewObject<UStaticMeshComponent>(this, TEXT("CarBody"));
    Rider->AddInstanceComponent(Body);
    Body->SetupAttachment(CarRoot);
    Body->RegisterComponent();
    Body->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Body->SetVisibility(false, true);
    Body->SetCastShadow(true);
    Seat = NewObject<UStaticMeshComponent>(this, TEXT("CarSeat"));
    Rider->AddInstanceComponent(Seat);
    Seat->SetupAttachment(Body);
    Seat->RegisterComponent();
    Seat->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Seat->SetVisibility(false, true);
    for (int i = 0; i < 4; ++i)
    {
        Wheel[i] = NewObject<UStaticMeshComponent>(this, *FString::Printf(TEXT("CarWheel%d"), i));
        Rider->AddInstanceComponent(Wheel[i]);
        Wheel[i]->SetupAttachment(Body);
        Wheel[i]->RegisterComponent();
        Wheel[i]->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Wheel[i]->SetVisibility(false, true);
    }
    Steering = NewObject<UStaticMeshComponent>(this, TEXT("CarSteeringWheel"));
    Rider->AddInstanceComponent(Steering);
    Steering->SetupAttachment(Body);
    Steering->RegisterComponent();
    Steering->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    Steering->SetVisibility(false, true);
    SteeringColumn = NewObject<UStaticMeshComponent>(this, TEXT("SteeringColumn"));
    Rider->AddInstanceComponent(SteeringColumn);
    SteeringColumn->SetupAttachment(Body);
    SteeringColumn->SetStaticMesh(ColumnMesh);
    SteeringColumn->RegisterComponent();
    SteeringColumn->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    SteeringColumn->SetVisibility(false, true);
    LoadSounds();
}

void UDrivingComponent::LoadSounds()
{
    if (bAudioReady || !Rider || !CarRoot)
    {
        return;
    }
    auto Load = [this](const FString& Name)
    {
        return LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *AudioRoot, *Name, *Name), nullptr,
                                      LOAD_NoWarn | LOAD_Quiet);
    };
    Attenuation = NewObject<USoundAttenuation>(this);
    FSoundAttenuationSettings& A = Attenuation->Attenuation;
    A.bAttenuate = true;
    A.bSpatialize = true;
    A.AttenuationShape = EAttenuationShape::Sphere;
    A.AttenuationShapeExtents = FVector(300.f, 0.f, 0.f);
    A.FalloffDistance = 3000.f;
    A.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound;
    A.dBAttenuationAtMax = -48.f;
    for (const TCHAR* Cue : {TEXT("impact"), TEXT("bump")})
    {
        const int32 First = Waves.Num();
        for (int32 I = 1; I <= 8; ++I)
        {
            if (USoundWave* W = Load(FString::Printf(TEXT("%s_%02d"), Cue, I)))
            {
                Waves.Add(W);
            }
        }
        if (Waves.Num() > First)
        {
            CueRange.Add(FName(Cue), FIntPoint(First, Waves.Num() - First));
        }
    }
    auto LoadBank = [&](const TCHAR* Cue, int32 Count)
    {
        const int32 First = Loops.Num();
        for (int32 I = 1; I <= Count; ++I)
        {
            UAudioComponent* L = NewObject<UAudioComponent>(Rider, *FString::Printf(TEXT("DriveLoop%d"), Loops.Num()));
            L->SetupAttachment(CarRoot);
            L->bAutoActivate = false;
            L->bAllowSpatialization = true;
            L->AttenuationSettings = Attenuation;
            L->SetSound(Load(FString::Printf(TEXT("%s_%02d"), Cue, I)));
            L->RegisterComponent();
            Loops.Add(L);
        }
        return First;
    };
    EngineFirst = LoadBank(TEXT("engine"), 5);
    EngineCount = Loops.Num() - EngineFirst;
    TyreFirst = LoadBank(TEXT("tyre"), 3);
    TyreCount = Loops.Num() - TyreFirst;
    SkidFirst = LoadBank(TEXT("skid"), 3);
    SkidCount = Loops.Num() - SkidFirst;
    WindFirst = LoadBank(TEXT("wind"), 3);
    WindCount = Loops.Num() - WindFirst;
    // The engine is the one required bank: a game that stages no driving cues stays silent rather than half-voiced.
    bAudioReady = EngineCount > 0 && Loops[EngineFirst] && Loops[EngineFirst]->Sound != nullptr;
    if (bAudioReady)
    {
        LoopVolume.Init(0.f, Loops.Num());
        LoopPitch.Init(1.f, Loops.Num());
    }
    else
    {
        for (UAudioComponent* L : Loops)
        {
            if (L) L->DestroyComponent();
        }
        Loops.Reset();
    }
    UE_LOG(LogTemp, Display, TEXT("DRIVING sounds: %d one-shots, %d loops (%d engine, %d tyre, %d skid, %d wind)%s"),
           Waves.Num(), Loops.Num(), EngineCount, TyreCount, SkidCount, WindCount,
           bAudioReady ? TEXT("") : TEXT(" (none staged)"));
}

bool UDrivingComponent::PlayCue(FName Cue, float Volume, float Pitch)
{
    const FIntPoint* Range = CueRange.Find(Cue);
    if (!Range || Range->Y <= 0 || !Rider || !CarRoot || !Waves.IsValidIndex(Range->X))
    {
        return false;
    }
    int32 Pick = Range->X + FMath::RandHelper(Range->Y);
    if (Range->Y > 1 && Pick == LastVariant)
    {
        Pick = Range->X + (Pick - Range->X + 1) % Range->Y;
    }
    LastVariant = Pick;
    UGameplayStatics::PlaySoundAtLocation(this, Waves[Pick], CarRoot->GetComponentLocation() + FVector(0, 0, 40.f),
                                         Volume, FMath::Clamp(Pitch, .25f, 4.f), 0.f, Attenuation);
    return true;
}

void UDrivingComponent::StopAudio()
{
    for (UAudioComponent* L : Loops)
    {
        if (L) L->Stop();
    }
    for (float& V : LoopVolume) V = 0.f;
    AudioRevs = AudioSlip = ImpactSpeed = PendingImpact = 0.f;
    BumpWait = ImpactWait = 0.f;
}

void UDrivingComponent::UpdateAudio(float DeltaSeconds)
{
    if (!bAudioReady || !Car || !Rider || LoopVolume.Num() != Loops.Num())
    {
        return;
    }
    const float Speed = GetSpeed();
    const float Throttle = FMath::Max(MoveInput.Y, 0.f);
    float Slip = 0.f;
    int32 Contacts = 0;
    for (int32 I = 0; I < 4; ++I)
    {
        const WheelState W = Car->Chassis.wheel(I);
        if (!W.on_ground)
        {
            bWheelWasGrounded[I] = false;
            continue;
        }
        ++Contacts;
        Slip = FMath::Max(Slip, W.skid);
        // A wheel meeting the ground again after airtime knocks the suspension once.
        if (!bWheelWasGrounded[I] && Speed > 400.f && BumpWait <= 0.f)
        {
            PlayCue(TEXT("bump"), .35f + .35f * FMath::Clamp(Speed / 1800.f, 0.f, 1.f),
                    FMath::FRandRange(.94f, 1.06f));
            BumpWait = .35f;
        }
        bWheelWasGrounded[I] = true;
    }
    AudioSlip = Slip;
    BumpWait = FMath::Max(0.f, BumpWait - DeltaSeconds);
    ImpactWait = FMath::Max(0.f, ImpactWait - DeltaSeconds);
    if (ImpactSpeed > 0.f && ImpactWait <= 0.f)
    {
        PlayCue(TEXT("impact"), FMath::Clamp(ImpactSpeed / 900.f, .3f, 1.f), FMath::FRandRange(.92f, 1.04f));
        ImpactWait = .25f;
    }
    ImpactSpeed = 0.f;

    AudioRevs = FMath::Clamp(Car->Chassis.rpm(), 0.f, 6000.f);
    float Want[32] = {};
    float Pitch[32] = {};
    const bool bRolling = Contacts > 0 && Speed > 4.f;
    // Volumes crossfade between adjacent recordings in a bank; the engine's five loops each pitch around their own
    // engine speed, so the ladder from idle to the limiter stays in tune as it hands over.
    static const float EngineSpeeds[] = {1200.f, 2200.f, 3200.f, 4200.f, 5200.f};
    auto FadeBank = [&](int32 First, int32 Count, float Position, float Base, float PitchAt, const float* Speeds)
    {
        if (Count <= 0 || First < 0 || First + Count > 32)
        {
            return;
        }
        for (int32 I = 0; I < Count; ++I)
        {
            Want[First + I] = 0.f;
            Pitch[First + I] = PitchAt;
        }
        const float X = FMath::Clamp(Position, 0.f, float(Count - 1));
        const int32 I0 = FMath::FloorToInt(X);
        const int32 I1 = FMath::Min(I0 + 1, Count - 1);
        const float F = X - I0;
        Want[First + I0] += Base * (1.f - F);
        Want[First + I1] += Base * F;
        if (Speeds)
        {
            for (int32 I = 0; I < Count; ++I)
            {
                Pitch[First + I] = FMath::Clamp(AudioRevs / Speeds[I], .72f, 1.42f);
            }
        }
    };
    const float RevPosition = FMath::Clamp((AudioRevs - 1150.f) / (5350.f - 1150.f), 0.f, 1.f) * (EngineCount - 1);
    FadeBank(EngineFirst, EngineCount, RevPosition, .42f + .30f * Throttle + .06f * RevPosition, 1.f, EngineSpeeds);
    if (bRolling)
    {
        FadeBank(TyreFirst, TyreCount, FMath::Clamp(Speed / 1900.f, 0.f, 1.f) * (TyreCount - 1),
                 .34f * FMath::Clamp(Speed / 1200.f, 0.f, 1.f), FMath::Clamp(.85f + Speed / 4200.f, .7f, 1.45f), nullptr);
        FadeBank(WindFirst, WindCount, FMath::Clamp((Speed - 250.f) / 2900.f, 0.f, 1.f) * (WindCount - 1),
                 .60f * FMath::Clamp((Speed - 300.f) / 2600.f, 0.f, 1.f), FMath::Clamp(.82f + Speed / 3600.f, .7f, 1.4f), nullptr);
    }
    if (bRolling && Slip > .05f)
    {
        FadeBank(SkidFirst, SkidCount, FMath::Clamp(Slip / .9f, 0.f, 1.f) * (SkidCount - 1),
                 .88f * Slip, FMath::Clamp(.90f + Speed / 5200.f, .8f, 1.25f), nullptr);
    }
    for (int32 I = 0; I < Loops.Num(); ++I)
    {
        UAudioComponent* L = Loops[I];
        if (!L || !L->Sound)
        {
            continue;
        }
        // A quick attack (a skid starts at once), a softer release.
        LoopVolume[I] = FMath::FInterpTo(LoopVolume[I], Want[I], DeltaSeconds, Want[I] > LoopVolume[I] ? 18.f : 6.f);
        LoopPitch[I] = FMath::FInterpTo(LoopPitch[I], FMath::Max(Pitch[I], .01f), DeltaSeconds, 10.f);
        if (LoopVolume[I] > .01f)
        {
            if (!L->IsPlaying())
            {
                L->Play(FMath::FRand() * 1.5f);
            }
            L->SetVolumeMultiplier(LoopVolume[I]);
            L->SetPitchMultiplier(LoopPitch[I]);
        }
        else if (L->IsPlaying())
        {
            L->Stop();
        }
    }
}

FString UDrivingComponent::GetAudioState() const
{
    if (!bAudioReady || LoopVolume.Num() != Loops.Num())
    {
        return TEXT("driving audio: none staged");
    }
    auto Bank = [this](int32 First, int32 Count)
    {
        float Volume = 0.f, Pitch = 1.f;
        for (int32 I = 0; I < Count; ++I)
        {
            if (LoopVolume[First + I] >= Volume)
            {
                Volume = LoopVolume[First + I];
                Pitch = LoopPitch[First + I];
            }
        }
        return FString::Printf(TEXT("%.2f@%.2f"), Volume, Pitch);
    };
    return FString::Printf(TEXT("engine %s tyre %s skid %s wind %s revs %.0f slip %.2f"),
                           *Bank(EngineFirst, EngineCount), *Bank(TyreFirst, TyreCount),
                           *Bank(SkidFirst, SkidCount), *Bank(WindFirst, WindCount), AudioRevs, AudioSlip);
}

FString UDrivingComponent::GetRideState() const
{
    if (!Car)
    {
        return TEXT("no car");
    }
    const Vec3 P = Car->Chassis.position();
    const Vec3 V = Car->Chassis.linear_velocity();
    const FRotator R = ToUE(Car->Chassis.orientation()).Rotator();
    FString Wheels;
    for (int32 I = 0; I < 4; ++I)
    {
        const WheelState Wheel = Car->Chassis.wheel(I);
        Wheels += FString::Printf(TEXT("%s%.2f@%.1f/%d"), I ? TEXT(",") : TEXT(""), Wheel.compression,
                                  Wheel.position.y * 100.f, Wheel.on_ground ? 1 : 0);
    }
    return FString::Printf(TEXT("y=%.2f vy=%.2f pitch=%.2f roll=%.2f wheels=%s"), P.y, V.y, R.Pitch, R.Roll, *Wheels);
}

float UDrivingComponent::GetWheelSlip(int32 Index) const
{
    if (!Car || Index < 0 || Index > 3)
    {
        return 0.f;
    }
    const WheelState W = Car->Chassis.wheel(Index);
    return W.on_ground ? FMath::Clamp(W.skid, 0.f, 1.f) : 0.f;
}

bool UDrivingComponent::IsWheelGrounded(int32 Index) const
{
    return Car && Index >= 0 && Index <= 3 && Car->Chassis.wheel(Index).on_ground;
}

FVector UDrivingComponent::GetWheelContact(int32 Index) const
{
    if (!Car || Index < 0 || Index > 3)
    {
        return FVector::ZeroVector;
    }
    return ToUE(Car->Chassis.wheel(Index).position);
}

bool UDrivingComponent::ConsumeImpact(float& OutSpeed, FVector& OutAt)
{
    if (PendingImpact <= 0.f)
    {
        return false;
    }
    OutSpeed = PendingImpact;
    OutAt = PendingImpactAt;
    PendingImpact = 0.f;
    return true;
}

bool UDrivingComponent::Configure(const FDrivingCockpit& InCockpit)
{
    if (bEquipped) return false;
    bConfigured = false;
    Hint = TEXT("Kart cockpit data is invalid");
    if (!Rider || InCockpit.ReferenceLegLength <= 0.f || InCockpit.SteeringRadius <= 0.f ||
        InCockpit.MinScale <= 0.f || InCockpit.MaxScale < InCockpit.MinScale ||
        InCockpit.WheelRadius <= 0.f || InCockpit.WheelWidth <= 0.f)
    {
        UE_LOG(LogTemp, Warning, TEXT("Kart cockpit values: rider=%d leg=%.3f steer=%.3f scale=%.2f..%.2f wheel=%.3f/%.3f"),
               Rider ? 1 : 0, InCockpit.ReferenceLegLength, InCockpit.SteeringRadius, InCockpit.MinScale,
               InCockpit.MaxScale, InCockpit.WheelRadius, InCockpit.WheelWidth);
        return false;
    }
    const USkeletalMesh* Mesh = Rider->GetMesh()->GetSkeletalMeshAsset();
    if (!Mesh)
    {
        UE_LOG(LogTemp, Warning, TEXT("Kart cockpit: %s has no skeletal mesh yet"), *GetNameSafe(Rider));
        return false;
    }
    const FReferenceSkeleton& Ref = Mesh->GetRefSkeleton();
    auto Point = [&Ref](const TCHAR* Name)
    {
        FTransform T = FTransform::Identity;
        for (int32 I = Ref.FindBoneIndex(Name); I != INDEX_NONE; I = Ref.GetParentIndex(I)) T = T * Ref.GetRefBonePose()[I];
        return T.GetLocation();
    };
    if (Ref.FindBoneIndex(TEXT("thigh_L")) == INDEX_NONE || Ref.FindBoneIndex(TEXT("shin_L")) == INDEX_NONE ||
        Ref.FindBoneIndex(TEXT("foot_L")) == INDEX_NONE)
    {
        UE_LOG(LogTemp, Warning, TEXT("Kart cockpit: %s lacks thigh_L/shin_L/foot_L"), *Mesh->GetName());
        return false;
    }
    const float Leg = FVector::Dist(Point(TEXT("thigh_L")), Point(TEXT("shin_L"))) + FVector::Dist(Point(TEXT("shin_L")), Point(TEXT("foot_L")));
    const float Scale = Leg / InCockpit.ReferenceLegLength;
    if (!FMath::IsFinite(Scale) || Scale < InCockpit.MinScale || Scale > InCockpit.MaxScale)
    {
        Hint = FString::Printf(TEXT("Kart does not fit this character (scale %.3f; allowed %.2f to %.2f)"), Scale, InCockpit.MinScale, InCockpit.MaxScale);
        return false;
    }
    Cockpit = InCockpit;
    SetKartScale(Scale);
    SteeringBase = FQuat(FVector::RightVector, FMath::DegreesToRadians(Cockpit.SteeringTilt));
    Steering->SetRelativeLocation(Cockpit.Steering);
    Steering->SetRelativeRotation(SteeringBase);
    Seat->SetRelativeLocation(Cockpit.Seat);
    SetAuthoredFit(0.f, 0.f, 0.f);
    bConfigured = true;
    return true;
}

void UDrivingComponent::SetMeshes(const FSoftObjectPath& BodyPath, const FSoftObjectPath& SeatPath,
                                  const FSoftObjectPath& WheelPath, const FSoftObjectPath& SteeringPath)
{
    BodyMeshPath = BodyPath;
    SeatMeshPath = SeatPath;
    WheelMeshPath = WheelPath;
    SteeringMeshPath = SteeringPath;
    BodyMesh = Cast<UStaticMesh>(BodyPath.TryLoad());
    SeatMesh = Cast<UStaticMesh>(SeatPath.TryLoad());
    WheelMesh = Cast<UStaticMesh>(WheelPath.TryLoad());
    SteeringMesh = Cast<UStaticMesh>(SteeringPath.TryLoad());
    if (SteeringColumn && SteeringMesh)
        if (UMaterialInstanceDynamic* Paint = SteeringColumn->CreateDynamicMaterialInstance(0, SteeringMesh->GetMaterial(0)))
            Paint->SetVectorParameterValue(TEXT("Tint"), FLinearColor(.285f, .27f, .22f));
}

void UDrivingComponent::SetKartScale(float Scale)
{
    if (bEquipped) return;
    KartScale = FMath::Clamp(Scale, .5f, 2.f);
    if (Body)
    {
        Body->SetRelativeScale3D(FVector(KartScale));
    }
}

bool UDrivingComponent::Toggle()
{
    if (bEquipped)
    {
        if (bAutoRight && IsInverted())
        {
            StartRighting(true);
            return true;
        }
        if (GetSpeed() > 60.f)
        {
            Hint = TEXT("Stop first");
            return false;
        }
        return Dismount();
    }
    return Summon();
}

void UDrivingComponent::StowImmediately()
{
    if (!bEquipped)
    {
        return;
    }
    if (!Dismount())
    {
        // Forced cleanup (world change, character switch): keep the capsule centre as it is; no floor shift.
        FinishDrive();
    }
}

bool UDrivingComponent::GroundBelow(const FVector& At, float Reach, FVector& Out) const
{
    if (!Rider || !Rider->GetWorld())
    {
        return false;
    }
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingPlace), false, Rider);
    const FVector From = At + FVector(0, 0, Reach * .5f);
    if (Rider->GetWorld()->LineTraceSingleByChannel(Hit, From, From - FVector(0, 0, Reach * 1.5f), TraceChannel, Params) &&
        Hit.ImpactNormal.Z > .55f)
    {
        Out = Hit.ImpactPoint;
        return true;
    }
    return false;
}

bool UDrivingComponent::FreeAt(const FVector& At, const FQuat& Rotation) const
{
    if (!Rider || !Rider->GetWorld())
    {
        return false;
    }
    FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingPlace), false, Rider);
    const FCollisionShape Shape = FCollisionShape::MakeBox(Cockpit.BodyHalfExtents * (KartScale * .88f));
    return !Rider->GetWorld()->OverlapBlockingTestByChannel(At, Rotation, TraceChannel, Shape, Params);
}

void UDrivingComponent::FindGroundOffset()
{
    if (!Car)
    {
        GroundOffset = 0.f;
        return;
    }
    const VehicleSpec& Spec = Car->Chassis.spec_ref();
    GroundOffset = (Spec.dimension.y + inch_to_m(Spec.chassis.ride_height[0])) * 100.f;
}

bool UDrivingComponent::Summon()
{
    if (bRequireAuthoredGrips && !HasAuthoredGrips())
    {
        Hint = TEXT("This character's kart grip is not ready: save and import its grip pose"); return false;
    }
    if (!Rider || !Rider->GetWorld() || !Body || !bConfigured || !BodyMesh || !SeatMesh || !WheelMesh || !SteeringMesh)
    {
        UE_LOG(LogTemp, Warning, TEXT("Kart summon blocked: rider=%d world=%d body=%d configured=%d meshes=%d%d%d%d"),
               Rider ? 1 : 0, Rider && Rider->GetWorld() ? 1 : 0, Body ? 1 : 0, bConfigured ? 1 : 0,
               BodyMesh ? 1 : 0, SeatMesh ? 1 : 0, WheelMesh ? 1 : 0, SteeringMesh ? 1 : 0);
        if (Hint.IsEmpty()) Hint = TEXT("The car is not ready");
        return false;
    }
    if (Rider->GetCharacterMovement()->IsFalling())
    {
        Hint = TEXT("Land first");
        return false;
    }
    const FRotator Yaw(0.f, Rider->GetActorRotation().Yaw, 0.f);
    const FRotationMatrix Basis(Yaw);
    const FVector Right = Basis.GetUnitAxis(EAxis::Y);
    const FVector Forward = Basis.GetUnitAxis(EAxis::X);
    const FVector Base = Rider->GetActorLocation();
    TArray<FVector> Candidates;
    for (const FVector& Direction : {Forward, Right, -Right, -Forward})
        for (const float Distance : {200.f, 350.f, 500.f})
            Candidates.Add(Base + Direction * Distance);
    FVector Spot = FVector::ZeroVector;
    bool bFound = false;
    for (const FVector& Candidate : Candidates)
    {
        FVector Ground;
        if (!GroundBelow(Candidate, 320.f, Ground))
        {
            continue;
        }
        if (FreeAt(Ground + FVector(0, 0, 30.f), Yaw.Quaternion()))
        {
            Spot = Ground;
            bFound = true;
            break;
        }
    }
    if (!bFound)
    {
        UE_LOG(LogTemp, Warning, TEXT("Kart summon: no free ground beside %s at %s"), *GetNameSafe(Rider),
               *Rider->GetActorLocation().ToString());
        Hint = TEXT("No room for the car");
        return false;
    }

    VehicleSpec Spec = kart_spec();
    Spec.dimension = ToSim(Cockpit.BodyHalfExtents) * KartScale;
    Spec.chassis.wheel_base = (Cockpit.WheelPositions[0].X - Cockpit.WheelPositions[2].X) * .01f * KartScale;
    Spec.chassis.front_axle = Cockpit.WheelPositions[0].X * .01f * KartScale;
    for (int I = 0; I < 2; ++I)
    {
        Spec.chassis.track_width[I] = FMath::Abs(Cockpit.WheelPositions[I*2].Y - Cockpit.WheelPositions[I*2+1].Y) * .01f * KartScale;
        Spec.chassis.ride_height[I] *= KartScale; Spec.chassis.travel[I] *= KartScale;
        const float Size = I == 0 ? 1.f : 1.08f;
        Spec.tires.rim_size[I] *= KartScale * Size;
        Spec.tires.section_width[I] = Cockpit.WheelWidth * 10.f * KartScale * Size;
        Spec.tires.aspect_ratio[I] = (Cockpit.WheelRadius * .01f * KartScale * Size - inch_to_m(Spec.tires.rim_size[I]) * .5f) /
                                    (Spec.tires.section_width[I] * .001f) * 100.f;
    }
    Car = MakeShared<FDrivingCar>(Spec);
    // The kart is the only host that feeds a wheel-contact plane and uses the airborne alignment assist.
    if (Spec.kart_alignment_assist)
    {
        Car->Chassis.jump_config.alignment.minimum_ground_up = .55f;
        Car->Chassis.jump_config.alignment.minimum_body_up = .3f;
        Car->Chassis.jump_config.alignment.minimum_alignment = .5f;
        Car->Chassis.jump_config.alignment.minimum_altitude = .02f;
        Car->Chassis.jump_config.alignment.maximum_altitude = 1.f;
        Car->Chassis.jump_config.alignment.maximum_speed = 30.f;
        Car->Chassis.jump_config.alignment.correction_threshold = .1f;
        Car->Chassis.jump_config.alignment.pitch = 1.f;
        Car->Chassis.jump_config.alignment.roll = 1.f;
    }
    FindGroundOffset();
    FCarGround Ground{Rider->GetWorld(), Rider, TraceChannel};
    if (!Car->Chassis.place_on_ground(Ground, float(Spot.Y) * .01f, float(Spot.X) * .01f, float(Spot.Z) * .01f + 1.f,
                                     FMath::DegreesToRadians(Yaw.Yaw)))
    {
        Car.Reset();
        Hint = TEXT("No ground for the car");
        return false;
    }

    if (!BodyMesh && !BodyMeshPath.IsNull())
    {
        BodyMesh = Cast<UStaticMesh>(BodyMeshPath.TryLoad());
    }
    if (!WheelMesh && !WheelMeshPath.IsNull())
    {
        WheelMesh = Cast<UStaticMesh>(WheelMeshPath.TryLoad());
    }
    if (!SeatMesh && !SeatMeshPath.IsNull())
    {
        SeatMesh = Cast<UStaticMesh>(SeatMeshPath.TryLoad());
    }
    if (!SteeringMesh && !SteeringMeshPath.IsNull())
    {
        SteeringMesh = Cast<UStaticMesh>(SteeringMeshPath.TryLoad());
    }
    Body->SetStaticMesh(BodyMesh);
    Body->SetRelativeScale3D(FVector(KartScale));
    Body->SetRelativeLocation(FVector(0, 0, -GroundOffset));
    Body->SetVisibility(true, true);
    Seat->SetStaticMesh(SeatMesh);
    Seat->SetRelativeLocation(Cockpit.Seat);
    Seat->SetVisibility(true, true);
    for (int i = 0; i < 4; ++i)
    {
        Wheel[i]->SetStaticMesh(WheelMesh);
        Wheel[i]->SetRelativeLocation(Cockpit.WheelPositions[i]);
        Wheel[i]->SetRelativeRotation(FQuat::Identity);
        Wheel[i]->SetRelativeScale3D(FVector(i < 2 ? 1.f : 1.08f));
        Wheel[i]->SetVisibility(true, true);
        Spin[i] = 0.f;
    }
    Steering->SetStaticMesh(SteeringMesh);
    Steering->SetRelativeRotation(SteeringBase);
    Steering->SetVisibility(true, true);

    // The rider alone: propagating to attached meshes would force carried equipment (the paraglider) visible
    // behind the move set's back, which then believes it is still hidden.
    Rider->GetMesh()->SetVisibility(true, false);
    Rider->GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::NoCollision);
    bSavedUseControllerYaw = Rider->bUseControllerRotationYaw;
    Rider->bUseControllerRotationYaw = false;
    Rider->GetCharacterMovement()->StopMovementImmediately();
    Rider->GetCharacterMovement()->SetMovementMode(MOVE_None);

    bEquipped = true;
    bHasGround = false;
    bRighting = false;
    InvertedTime = 0.f;
    RightingTime = 0.f;
    LastGround = Spot;
    MoveInput = FVector2D::ZeroVector;
    bHandbrake = false;
    Hint = TEXT("Driving");
    UpdatePose(0.f);
    return true;
}

bool UDrivingComponent::Dismount()
{
    if (!Rider || !Car)
    {
        return false;
    }
    const FVector Forward = Rider->GetActorForwardVector();
    const FVector Right = Rider->GetActorRightVector();
    const FVector Base = Rider->GetActorLocation();
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    for (const FVector& Candidate : {Base - Right * 150.f, Base + Right * 150.f, Base - Forward * 420.f})
    {
        FVector Ground;
        if (!GroundBelow(Candidate, 300.f, Ground))
        {
            continue;
        }
        FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingDismount), false, Rider);
        if (Rider->GetWorld()->OverlapBlockingTestByChannel(Ground + FVector(0, 0, Half + 2.f), FQuat::Identity,
                                                           TraceChannel, FCollisionShape::MakeCapsule(34.f, Half), Params))
        {
            continue;
        }
        EndDrive(Ground);
        return true;
    }
    Hint = TEXT("No room to step out");
    return false;
}

void UDrivingComponent::EndDrive(const FVector& GroundSpot)
{
    if (!Rider || !Car)
    {
        return;
    }
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    Rider->SetActorLocation(GroundSpot + FVector(0, 0, Half + 2.f), false, nullptr, ETeleportType::TeleportPhysics);
    FinishDrive();
}

void UDrivingComponent::FinishDrive()
{
    if (!Rider || !Car)
    {
        return;
    }
    Rider->SetActorRotation(FRotator(0, Rider->GetActorRotation().Yaw, 0));
    Rider->GetMesh()->SetVisibility(true, false);
    Rider->GetCapsuleComponent()->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
    Rider->bUseControllerRotationYaw = bSavedUseControllerYaw;
    Rider->GetCharacterMovement()->SetMovementMode(MOVE_Walking);
    Body->SetVisibility(false, true);
    if (Seat) Seat->SetVisibility(false, true);
    for (int i = 0; i < 4; ++i) Wheel[i]->SetVisibility(false, true);
    if (Steering) Steering->SetVisibility(false, true);
    StopAudio();
    Car.Reset();
    bEquipped = false;
    bRighting = false;
    InvertedTime = 0.f;
    RightingTime = 0.f;
    Hint = TEXT("Parked");
}

bool UDrivingComponent::StandingRoom(const FVector& Ground) const
{
    if (!Rider || !Rider->GetWorld())
    {
        return false;
    }
    const float Half = Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingDismount), false, Rider);
    return !Rider->GetWorld()->OverlapBlockingTestByChannel(Ground + FVector(0, 0, Half + 2.f), FQuat::Identity,
                                                           TraceChannel, FCollisionShape::MakeCapsule(34.f, Half), Params);
}

void UDrivingComponent::Recover()
{
    FVector Spot;
    if (bHasGround && GroundBelow(LastGround, 200.f, Spot) && StandingRoom(Spot))
    {
        EndDrive(Spot);
        Hint = TEXT("Recovered");
        return;
    }
    // No verified floor plus standing room: keep the capsule centre and let the game's fall/respawn handle it.
    FinishDrive();
    Hint = TEXT("Recovered without ground");
}

bool UDrivingComponent::IsInverted() const
{
    if (!Car)
    {
        return false;
    }
    return FVector::DotProduct(ToUE(Car->Chassis.orientation()).GetUpVector(), FVector::UpVector) < .3f;
}

bool UDrivingComponent::ForceInvertedForQA()
{
    if (!Car || !bEquipped)
    {
        return false;
    }
    const FQuat Flipped = ToUE(Car->Chassis.orientation()) * FQuat(FVector::ForwardVector, PI);
    Car->Chassis.body.orientation = ToSim(Flipped);
    Car->Chassis.body.position += VEC3_Y * .3f;
    Car->Chassis.body.linear_velocity = VEC3_ZERO;
    Car->Chassis.body.angular_velocity = VEC3_ZERO;
    InvertedTime = 0.f;
    bRighting = false;
    return true;
}

void UDrivingComponent::StartRighting(bool bImmediate)
{
    if (!Car)
    {
        return;
    }
    RightFrom = ToUE(Car->Chassis.position());
    RightFromQ = ToUE(Car->Chassis.orientation());
    const FVector Ground = bHasGround ? LastGround : RightFrom - FVector(0, 0, GroundOffset);
    const float Yaw = RightFromQ.Rotator().Yaw;
    RightToQ = FRotator(0.f, Yaw, 0.f).Quaternion();
    RightTo = FVector(RightFrom.X, RightFrom.Y, Ground.Z + GroundOffset);
    Car->Chassis.body.linear_velocity = VEC3_ZERO;
    Car->Chassis.body.angular_velocity = VEC3_ZERO;
    InvertedTime = 0.f;
    if (bImmediate)
    {
        Car->Chassis.place(ToSim(RightTo), ToSim(RightToQ));
        bRighting = false;
        UpdatePose(0.f);
        Hint = TEXT("Recovered");
        return;
    }
    RightingTime = 0.f;
    bRighting = true;
}

void UDrivingComponent::UpdatePose(float DeltaSeconds)
{
    if (!Rider || !Car)
    {
        return;
    }
    const FVector NewLocation = ToUE(Car->Chassis.position());
    const FQuat NewRotation = ToUE(Car->Chassis.orientation());
    const FVector OldLocation = Rider->GetActorLocation();

    FCollisionQueryParams Params(SCENE_QUERY_STAT(DrivingBody), false, Rider);
    const FCollisionShape Shape = FCollisionShape::MakeBox(Cockpit.BodyHalfExtents * (KartScale * .9f));
    FHitResult Hit;
    if (Rider->GetWorld()->SweepSingleByChannel(Hit, OldLocation, NewLocation, NewRotation, TraceChannel, Shape, Params))
    {
        if (FMath::Abs(Hit.ImpactNormal.Z) < .55f)
        {
            const Vec3 N = ToSimDir(Hit.ImpactNormal);
            Vec3 V = Car->Chassis.body.linear_velocity;
            const float Closing = dot(V, N);
            if (Closing < 0.f)
            {
                Car->Chassis.notify_wall_contact(ToSim(Hit.ImpactPoint), N, N * Closing, V);
                ImpactSpeed = FMath::Max(ImpactSpeed, -Closing * 100.f);
                PendingImpact = FMath::Max(PendingImpact, -Closing * 100.f);
                PendingImpactAt = Hit.ImpactPoint;
                Car->Chassis.body.linear_velocity = V - N * Closing;
            }
            Car->Chassis.body.position = ToSim(OldLocation);
        }
    }
    Rider->SetActorLocationAndRotation(ToUE(Car->Chassis.position()), ToUE(Car->Chassis.orientation()).Rotator(), false,
                                       nullptr, ETeleportType::TeleportPhysics);
    float ContactY = 0.f;
    int Contacts = 0;
    for (int i = 0; i < 4; ++i)
    {
        const WheelState Wheel = Car->Chassis.wheel(i);
        if (Wheel.on_ground)
        {
            ContactY += Wheel.position.y;
            ++Contacts;
        }
    }
    if (Contacts > 0 && Body)
    {
        // The mesh's origin is the ground under the middle of the car: keep it on the contact patches as the
        // suspension settles, rather than at the free ride height it was placed at.
        const float Drop = (Car->Chassis.position().y - ContactY / float(Contacts)) * 100.f;
        Body->SetRelativeLocation(FVector(0, 0, -Drop));
        LastGround = ToUE(Car->Chassis.position()) - FVector(0, 0, Drop);
        bHasGround = true;
    }
    const float Steer = float(Car->Chassis.wheel(0).steer_angle);
    for (int i = 0; i < 4; ++i)
    {
        const WheelState State = Car->Chassis.wheel(i);
        const FVector Centre = ToUE(State.position) + NewRotation.RotateVector(FVector::UpVector) * (State.radius * 100.f);
        Wheel[i]->SetRelativeLocation(Body->GetComponentTransform().InverseTransformPosition(Centre));
        Spin[i] += float(State.angular_velocity) * DeltaSeconds;
        Wheel[i]->SetRelativeRotation(FQuat(FVector::UpVector, float(State.steer_angle)) *
                                      FQuat(FVector::RightVector, Spin[i]));
    }
    if (SteeringMesh)
    {
        Steering->SetRelativeRotation(SteeringBase * FQuat(FVector::ForwardVector, -Steer * 2.5f));
    }
}

void UDrivingComponent::SetInput(FVector2D Move)
{
    MoveInput = FVector2D(FMath::Clamp(Move.X, -1.f, 1.f), FMath::Clamp(Move.Y, -1.f, 1.f));
}

void UDrivingComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    if (!bEquipped || !Car || !Rider || !Rider->GetWorld())
    {
        return;
    }
    if (bRighting)
    {
        RightingTime += FMath::Min(DeltaTime, .1f);
        const float T = FMath::Clamp(RightingTime / .5f, 0.f, 1.f);
        const float Smooth = T * T * (3.f - 2.f * T);
        FVector Position = FMath::Lerp(RightFrom, RightTo, Smooth);
        Position.Z += 50.f * FMath::Sin(PI * T);
        const FQuat Rotation = FQuat::Slerp(RightFromQ, RightToQ, Smooth);
        Car->Chassis.body.position = ToSim(Position);
        Car->Chassis.body.orientation = ToSim(Rotation);
        Car->Chassis.body.linear_velocity = VEC3_ZERO;
        Car->Chassis.body.angular_velocity = VEC3_ZERO;
        UpdatePose(0.f);
        if (T >= 1.f)
        {
            Car->Chassis.place(ToSim(RightTo), ToSim(RightToQ));
            bRighting = false;
            Hint = TEXT("Recovered");
        }
        return;
    }
    if (bAutoRight)
    {
        if (IsInverted() && GetSpeed() < 200.f)
        {
            InvertedTime += DeltaTime;
        }
        else
        {
            InvertedTime = 0.f;
        }
        if (InvertedTime >= 1.f)
        {
            StartRighting();
            return;
        }
    }
    InputState Input;
    Input.steer = MoveInput.X;
    Input.throttle = FMath::Max(MoveInput.Y, 0.f);
    Input.brake = FMath::Max(-MoveInput.Y, 0.f);
    Input.handbrake = bHandbrake ? 1.f : 0.f;
    FCarGround Ground{Rider->GetWorld(), Rider, TraceChannel};
    Car->Accumulator = FMath::Min(Car->Accumulator + FMath::Min(DeltaTime, .25f), FIXED_STEP * 6.f);
    int Steps = 0;
    while (Car->Accumulator >= FIXED_STEP && Steps < 6)
    {
        Car->Chassis.step(FIXED_STEP, Input, Ground);
        Car->Accumulator -= FIXED_STEP;
        ++Steps;
    }
    if (Steps > 0)
    {
        UpdatePose(DeltaTime);
    }
    UpdateAudio(DeltaTime);
    if (Car->Chassis.position().y < -20.0f)
    {
        Recover();
    }
}

float UDrivingComponent::GetSpeed() const
{
    return Car ? length(Car->Chassis.linear_velocity()) * 100.f : 0.f;
}

float UDrivingComponent::GetSpeedKph() const
{
    return GetSpeed() * .036f;
}

FTransform UDrivingComponent::GetCarTransform() const
{
    if (!Car)
    {
        return FTransform::Identity;
    }
    return FTransform(ToUE(Car->Chassis.orientation()), ToUE(Car->Chassis.position()));
}

FVector UDrivingComponent::PosePoint(const FVector& Local) const
{
    return Body ? Body->GetComponentTransform().TransformPosition(Local) : Local;
}

FVector UDrivingComponent::PoseDirection(const FVector& Local) const
{
    return Body ? Body->GetComponentTransform().TransformVectorNoScale(Local) : Local;
}

FVector UDrivingComponent::HandPoint(int32 Side) const
{
    const float Bar = Car ? -float(Car->Chassis.wheel(0).steer_angle) * 2.5f : 0.f;
    const float Sign = AtelierDrivingSide::Sign(Side);   // 9:15 (left) and 2:45 (right), just above horizontal
    const float Elev = FMath::DegreesToRadians(Cockpit.GripElevation);
    const FVector Rim(0, Sign * Cockpit.SteeringRadius * FMath::Cos(Elev), Cockpit.SteeringRadius * FMath::Sin(Elev));
    return Steering ? Steering->GetRelativeTransform().TransformPosition(Rim) :
        Cockpit.Steering + SteeringBase.RotateVector(FQuat(FVector::ForwardVector, Bar).RotateVector(Rim));
}

FVector UDrivingComponent::GripForward(int32 Side) const
{
    (void)Side;
    return (Steering ? Steering->GetRelativeRotation().Quaternion() : SteeringBase).RotateVector(FVector(1, 0, 0));
}

FVector UDrivingComponent::GripUp(int32 Side) const
{
    const float Bar = Car ? -float(Car->Chassis.wheel(0).steer_angle) * 2.5f : 0.f;
    const float Sign = AtelierDrivingSide::Sign(Side);
    const float Elev = FMath::DegreesToRadians(Cockpit.GripElevation);
    const FVector Radial(0, Sign * FMath::Cos(Elev), FMath::Sin(Elev));
    return Steering ? Steering->GetRelativeRotation().Quaternion().RotateVector(Radial) :
        SteeringBase.RotateVector(FQuat(FVector::ForwardVector, Bar).RotateVector(Radial));
}

FVector UDrivingComponent::GripAxis(int32 Side) const
{
    const float Bar = Car ? -float(Car->Chassis.wheel(0).steer_angle) * 2.5f : 0.f;
    const float Sign = AtelierDrivingSide::Sign(Side);
    const float Elev = FMath::DegreesToRadians(Cockpit.GripElevation);
    const FVector Tangent(0, -Sign * FMath::Sin(Elev), FMath::Cos(Elev));
    return Steering ? Steering->GetRelativeRotation().Quaternion().RotateVector(Tangent) :
        SteeringBase.RotateVector(FQuat(FVector::ForwardVector, Bar).RotateVector(Tangent));
}


bool UDrivingComponent::AuthoredGripWorld(FName Bone, FTransform& Out) const
{
    const FTransform* Frame = AuthoredGrips.Find(Bone);
    if (!Frame || !Steering || !bEquipped) return false;
    Out = *Frame * Steering->GetComponentTransform();
    return true;
}


bool UDrivingComponent::SetAuthoredFit(float Lean, float Height, float Tilt)
{
    if (bEquipped || !Steering || !FMath::IsFinite(Lean) || !FMath::IsFinite(Height) || Lean < -15.f || Lean > 45.f) return false;
    const float Angle = Cockpit.SteeringTilt + Tilt;
    if (!FMath::IsFinite(Angle) || Angle < 15.f || Angle > 75.f || !ColumnMesh || !SteeringColumn) return false;
    AuthoredLean = Lean;
    FVector Hub = Cockpit.Steering + FVector(0., 0., Height);
    Hub.X = Cockpit.SteeringColumnBase.X - (Hub.Z - Cockpit.SteeringColumnBase.Z) / FMath::Tan(FMath::DegreesToRadians(Angle));
    SteeringBase = FQuat(FVector::RightVector, FMath::DegreesToRadians(Angle));
    Steering->SetRelativeRotation(SteeringBase);
    Steering->SetRelativeLocation(Hub);
    const FVector Shaft = Hub - Cockpit.SteeringColumnBase;
    const FVector Extent = ColumnMesh->GetBounds().BoxExtent;
    SteeringColumn->SetRelativeLocation((Hub + Cockpit.SteeringColumnBase) * .5f);
    SteeringColumn->SetRelativeRotation(FQuat::FindBetweenNormals(FVector::UpVector, Shaft.GetSafeNormal()));
    SteeringColumn->SetRelativeScale3D(FVector(1.9f / Extent.X, 1.9f / Extent.Y, Shaft.Size() / (Extent.Z * 2.f)));
    return true;
}
