#include "JapanCombatFX.h"
#include "WandererCharacter.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Kismet/GameplayStatics.h"
#include "Camera/PlayerCameraManager.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Sound/SoundWave.h"
#include "Sound/SoundAttenuation.h"
#include "Misc/App.h"
#if WITH_EDITORONLY_DATA
#include "EditorFramework/AssetImportData.h"
#endif

bool FJapanAudioLog::bRecording = false;
int32 FJapanAudioLog::Frame = 0;
TArray<FJapanAudioEvent> FJapanAudioLog::Events;

void FJapanAudioLog::Record(USoundBase* Sound, const FVector& At, float Volume, float Pitch, bool b2D, bool bLoop)
{
    if (!bRecording || !Sound) return;
    FJapanAudioEvent E; E.Frame = Frame; E.Sound = Sound->GetPathName(); E.At = At; E.Volume = Volume; E.Pitch = Pitch; E.b2D = b2D; E.bLoop = bLoop;
#if WITH_EDITORONLY_DATA
    if (const USoundWave* Wave = Cast<USoundWave>(Sound); Wave && Wave->AssetImportData) E.Source = Wave->AssetImportData->GetFirstFilename();
#endif
    Events.Add(E);
}

// ------------------------------------------------------------------ slash trail
UJapanSwordTrail::UJapanSwordTrail(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
    SetUsingAbsoluteLocation(true); SetUsingAbsoluteRotation(true); SetUsingAbsoluteScale(true);
    SetCollisionEnabled(ECollisionEnabled::NoCollision);
    SetCastShadow(false);
    bUseAsyncCooking = false;
    SetGenerateOverlapEvents(false);
}

static float TrailLife(int32 Style) { return Style >= 3 ? .24f : Style == 2 ? .19f : .13f; }

void UJapanSwordTrail::Sample(const FVector& Base, const FVector& Tip, bool bEmit, int32 Strength, float Dt)
{
    if (!GetMaterial(0))
        if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, TEXT("/Game/FX/M_FX_Trail.M_FX_Trail"), nullptr, LOAD_NoWarn | LOAD_Quiet))
            SetMaterial(0, UMaterialInstanceDynamic::Create(M, this));
    for (FPoint& P : Points) P.Age += Dt;
    if (bEmit)
    {
        if (!bWasEmitting) Points.Reset();
        Style = FMath::Max(1, Strength);
        Points.Add({ Base, Tip, 0.f, 1.f });
    }
    bWasEmitting = bEmit;
    const float Life = TrailLife(Style);
    Points.RemoveAll([&](const FPoint& P) { return P.Age >= Life; });
    Rebuild();
}

void UJapanSwordTrail::Rebuild()
{
    if (Points.Num() < 2) { if (GetNumSections()) ClearAllMeshSections(); return; }
    if (UMaterialInstanceDynamic* M = Cast<UMaterialInstanceDynamic>(GetMaterial(0)))
        M->SetScalarParameterValue(TEXT("Intensity"), Style >= 3 ? 3.4f : Style == 2 ? 2.6f : 1.8f);
    const float Life = TrailLife(Style);
    const FLinearColor Tint = Style >= 3 ? FLinearColor(1.f, .7f, .35f) : Style == 2 ? FLinearColor(1.f, .84f, .6f) : FLinearColor(.92f, .93f, .95f);
    auto CR = [](const FVector& P0, const FVector& P1, const FVector& P2, const FVector& P3, float T)
    {
        const float T2 = T * T, T3 = T2 * T;
        return .5f * ((2.f * P1) + (-P0 + P2) * T + (2.f * P0 - 5.f * P1 + 4.f * P2 - P3) * T2 + (-P0 + 3.f * P1 - 3.f * P2 + P3) * T3);
    };
    TArray<FVector> Verts; TArray<int32> Tris; TArray<FVector2D> UV; TArray<FLinearColor> Colors;
    constexpr int32 Sub = 5;
    const int32 N = Points.Num();
    for (int32 I = 0; I < N - 1; ++I)
    {
        const FPoint& A = Points[FMath::Max(0, I - 1)]; const FPoint& B = Points[I]; const FPoint& C = Points[I + 1]; const FPoint& D = Points[FMath::Min(N - 1, I + 2)];
        for (int32 S = 0; S < Sub || (I == N - 2 && S == Sub); ++S)
        {
            const float T = float(S) / Sub;
            const FVector Base = CR(A.Base, B.Base, C.Base, D.Base, T), Tip = CR(A.Tip, B.Tip, C.Tip, D.Tip, T);
            const float Age = FMath::Lerp(B.Age, C.Age, T);
            const float U = FMath::Clamp(Age / Life, 0.f, 1.f);
            // Brightest just behind the blade, fading with age; a short fade-in at the blade so the ribbon does not end in a hard edge.
            const float Alpha = FMath::Pow(1.f - U, 2.4f) * FMath::Clamp(Age / .012f + .35f, 0.f, 1.f);
            const FLinearColor Col(Tint.R, Tint.G, Tint.B, Alpha);
            Verts.Add(Base); Verts.Add(Tip); UV.Add(FVector2D(U, 0.f)); UV.Add(FVector2D(U, 1.f)); Colors.Add(Col); Colors.Add(Col);
        }
    }
    for (int32 I = 0; I + 3 < Verts.Num(); I += 2) { Tris.Append({ I, I + 1, I + 2, I + 1, I + 3, I + 2 }); }
    CreateMeshSection_LinearColor(0, Verts, Tris, TArray<FVector>(), UV, Colors, TArray<FProcMeshTangent>(), false);
}

// ------------------------------------------------------------------ the effects actor
static const TCHAR* LayerMaterials[] = { TEXT("/Game/FX/MI_FX_Glow.MI_FX_Glow"), TEXT("/Game/FX/MI_FX_Spark.MI_FX_Spark"), TEXT("/Game/FX/MI_FX_Ring.MI_FX_Ring"), TEXT("/Game/FX/MI_FX_Dust.MI_FX_Dust") };

AJapanCombatFX::AJapanCombatFX()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PostUpdateWork;   // after the camera has moved: sprites face this frame's view
    SetRootComponent(CreateDefaultSubobject<USceneComponent>(TEXT("Root")));
    for (int32 I = 0; I < 4; ++I)
    {
        UInstancedStaticMeshComponent* L = CreateDefaultSubobject<UInstancedStaticMeshComponent>(*FString::Printf(TEXT("Layer%d"), I));
        L->SetupAttachment(GetRootComponent());
        L->SetCollisionEnabled(ECollisionEnabled::NoCollision); L->SetCastShadow(false); L->SetNumCustomDataFloats(4);
        L->bAffectDynamicIndirectLighting = false; L->bAffectDistanceFieldLighting = false; L->SetTranslucentSortPriority(10 + I);
        L->SetMobility(EComponentMobility::Movable);
        SpriteLayers.Add(L);
    }
    for (int32 I = 0; I < 3; ++I)
    {
        UPointLightComponent* Light = CreateDefaultSubobject<UPointLightComponent>(*FString::Printf(TEXT("Flash%d"), I));
        Light->SetupAttachment(GetRootComponent());
        Light->SetCastShadows(false); Light->SetIntensityUnits(ELightUnits::Lumens); Light->SetIntensity(0.f); Light->SetVisibility(false);
        Light->SetMobility(EComponentMobility::Movable);
        Lights.Add(Light); LightState.AddDefaulted();
    }
    Rand.Initialize(1234);
}

AJapanCombatFX* AJapanCombatFX::Get(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    if (TActorIterator<AJapanCombatFX> It(World); It) return *It;
    FActorSpawnParameters Params; Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    AJapanCombatFX* FX = World->SpawnActor<AJapanCombatFX>(FVector::ZeroVector, FRotator::ZeroRotator, Params);
    if (!FX) return nullptr;
    UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
    for (int32 I = 0; I < FX->SpriteLayers.Num(); ++I)
    {
        FX->SpriteLayers[I]->SetStaticMesh(Plane);
        if (UMaterialInterface* M = LoadObject<UMaterialInterface>(nullptr, LayerMaterials[I], nullptr, LOAD_NoWarn | LOAD_Quiet)) FX->SpriteLayers[I]->SetMaterial(0, M);
        else UE_LOG(LogTemp, Warning, TEXT("Combat FX material missing: %s (run Scripts/import_combat_fx.py)"), LayerMaterials[I]);
    }
    FX->Attenuation = NewObject<USoundAttenuation>(FX);
    FSoundAttenuationSettings& A = FX->Attenuation->Attenuation;
    A.bAttenuate = true; A.bSpatialize = true; A.AttenuationShape = EAttenuationShape::Sphere;
    A.AttenuationShapeExtents = FVector(450.f, 0.f, 0.f); A.FalloffDistance = 5000.f; A.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound; A.dBAttenuationAtMax = -48.f;
    A.NonSpatializedRadiusStart = 250.f; A.NonSpatializedRadiusEnd = 60.f; A.NonSpatializedRadiusMode = ENonSpatializedRadiusSpeakerMapMode::OmniDirectional;
    return FX;
}

AJapanCombatFX::FParticle& AJapanCombatFX::Spawn(ESprite Kind, const FVector& At)
{
    FParticle& P = Particles.AddDefaulted_GetRef(); P.Kind = Kind; P.P = At; P.Seed = Rand.FRand();
    return P;
}

static FVector RandomUnit(FRandomStream& R) { return R.GetUnitVector(); }

// ---- sounds
const TArray<TObjectPtr<USoundWave>>& AJapanCombatFX::Bank(FName Cue)
{
    if (FJapanSoundBank* Found = Banks.Find(Cue)) return Found->Waves;
    FJapanSoundBank& New = Banks.Add(Cue);
    for (int32 I = 1; I <= 16; ++I)
    {
        const FString Name = FString::Printf(TEXT("%s_%02d"), *Cue.ToString(), I);
        USoundWave* Wave = LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("/Game/Audio/Combat/%s.%s"), *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (!Wave) break;
        New.Waves.Add(Wave);
    }
    if (!New.Waves.Num()) UE_LOG(LogTemp, Warning, TEXT("Combat sound bank empty: %s"), *Cue.ToString());
    return New.Waves;
}

bool AJapanCombatFX::Play(FName Cue, const FVector& At, float Volume, float PitchSpread, bool b2D)
{
    const TArray<TObjectPtr<USoundWave>>& Waves = Bank(Cue);
    if (!Waves.Num()) return false;
    TArray<int32>& Bag = Bags.FindOrAdd(Cue);
    if (!Bag.Num()) { for (int32 I = 0; I < Waves.Num(); ++I) Bag.Add(I); for (int32 I = Bag.Num() - 1; I > 0; --I) Bag.Swap(I, Rand.RandHelper(I + 1)); }
    USoundWave* Wave = Waves[Bag.Pop(EAllowShrinking::No)];
    const float Pitch = 1.f + Rand.FRandRange(-PitchSpread, PitchSpread);
    if (b2D) UGameplayStatics::PlaySound2D(this, Wave, Volume, Pitch);
    else UGameplayStatics::PlaySoundAtLocation(this, Wave, At, FRotator::ZeroRotator, Volume, Pitch, 0.f, Attenuation);
    FJapanAudioLog::Record(Wave, At, Volume, Pitch, b2D);
    return true;
}

// ---- timing
void AJapanCombatFX::HitStop(float Seconds, AActor* A, AActor* B)
{
    for (AActor* Actor : { A, B })
    {
        if (!Actor) continue;
        FFrozen* Existing = Frozen.FindByPredicate([&](const FFrozen& F) { return F.Actor.Get() == Actor; });
        if (Existing) Existing->Remaining = FMath::Max(Existing->Remaining, Seconds);
        else Frozen.Add({ Actor, Seconds });
        Actor->CustomTimeDilation = .02f;
    }
}

void AJapanCombatFX::SlowMotion(float Seconds, float Dilation)
{
    SlowRemaining = FMath::Max(SlowRemaining, Seconds); SlowTotal = FMath::Max(SlowTotal, Seconds); SlowDepth = Dilation;
    UGameplayStatics::SetGlobalTimeDilation(this, Dilation);
}

void AJapanCombatFX::Shake(float Trauma)
{
    if (AWandererCharacter* P = Cast<AWandererCharacter>(UGameplayStatics::GetPlayerPawn(this, 0))) P->AddCameraShake(Trauma);
}

void AJapanCombatFX::PlayLater(float Delay, FName Cue, const FVector& At, float Volume) { Scheduled.Add({ Delay, Cue, At, Volume }); }

// ---- visuals
void AJapanCombatFX::Flash(const FVector& At, float Size, const FLinearColor& Color, float Life)
{
    FParticle& P = Spawn(ESprite::Glow, At); P.Size0 = Size * .55f; P.Size1 = Size; P.Life = Life; P.Color = Color;
}

void AJapanCombatFX::LightFlash(const FVector& At, const FLinearColor& Color, float Intensity, float Radius, float Life)
{
    int32 Best = 0; for (int32 I = 1; I < LightState.Num(); ++I) if (LightState[I].Age / LightState[I].Life > LightState[Best].Age / LightState[Best].Life) Best = I;
    UPointLightComponent* L = Lights[Best];
    Intensity *= .045f;   // a warm kick on the fighters (hundreds of lumens: the shop practicals are 350), not a floodlight
    L->SetWorldLocation(At); L->SetLightColor(Color); L->SetAttenuationRadius(Radius); L->SetIntensity(Intensity); L->SetVisibility(true);
    LightState[Best] = { 0.f, Life, Intensity };
}

void AJapanCombatFX::Dust(const FVector& Ground, float Strength, const FVector& Direction)
{
    const int32 Count = FMath::RoundToInt(5 + 7 * Strength);
    for (int32 I = 0; I < Count; ++I)
    {
        const float A = Rand.FRandRange(0.f, 2 * PI);
        const FVector Out(FMath::Cos(A), FMath::Sin(A), 0.f);
        FParticle& P = Spawn(ESprite::Dust, Ground + Out * Rand.FRandRange(5.f, 25.f) + FVector(0, 0, 6));
        P.V = Out * Rand.FRandRange(60.f, 200.f) * (.6f + .5f * Strength) + Direction * 140.f + FVector(0, 0, Rand.FRandRange(15.f, 60.f));
        P.Drag = 3.2f; P.Gravity = -25.f; P.Life = Rand.FRandRange(.55f, 1.f); P.Size0 = Rand.FRandRange(18.f, 30.f); P.Size1 = P.Size0 * Rand.FRandRange(2.6f, 3.6f);
        P.Color = FLinearColor(.62f, .55f, .44f); P.Alpha = Rand.FRandRange(.28f, .45f) * FMath::Min(1.f, .55f + .3f * Strength); P.FadeIn = .08f;
    }
}

void AJapanCombatFX::SwordSwing(const FVector& At, int32 Strength)
{
    Play(Strength >= 2 ? TEXT("sword_swing_heavy") : TEXT("sword_swing"), At, Strength >= 2 ? 1.f : .8f, .06f);
}

static void Burst(AJapanCombatFX& FX, FRandomStream& R, const FVector& At, const FVector& Bias, int32 Count, float Speed, const FLinearColor& Color, float Life, float Size)
{
    for (int32 I = 0; I < Count; ++I)
    {
        FVector Dir = (Bias * .75f + R.GetUnitVector()).GetSafeNormal();
        AJapanCombatFX::FParticle& P = FX.Spawn(AJapanCombatFX::ESprite::Spark, At);
        P.V = Dir * Speed * R.FRandRange(.45f, 1.1f); P.Drag = 3.5f; P.Gravity = 1300.f; P.Life = Life * R.FRandRange(.5f, 1.2f);
        P.Size0 = Size * R.FRandRange(.6f, 1.2f); P.Size1 = P.Size0 * .4f; P.Stretch = .028f; P.Color = Color * R.FRandRange(.7f, 1.2f);
    }
}

static void Streaks(AJapanCombatFX& FX, FRandomStream& R, const FVector& At, int32 Count, float Size, const FLinearColor& Color)
{
    for (int32 I = 0; I < Count; ++I)
    {
        AJapanCombatFX::FParticle& P = FX.Spawn(AJapanCombatFX::ESprite::Spark, At);
        P.V = R.GetUnitVector() * R.FRandRange(1500.f, 2400.f); P.Drag = 11.f; P.Life = R.FRandRange(.08f, .13f);
        P.Size0 = Size; P.Size1 = Size * .5f; P.Stretch = .05f; P.Color = Color;
    }
}

void AJapanCombatFX::SwordHit(const FVector& At, const FVector& SwingDir, int32 Strength, AActor* Wielder, AActor* Victim)
{
    const float K = Strength >= 3 ? 1.45f : Strength == 2 ? 1.2f : 1.f;
    HitStop(Strength >= 3 ? .13f : Strength == 2 ? .08f : .055f, Wielder, Victim);
    Flash(At, 70.f * K, FLinearColor(1.f, .84f, .6f) * 4.5f, .09f + .02f * Strength);
    Flash(At, 28.f * K, FLinearColor(1.f, 1.f, .95f) * 9.f, .05f);
    Burst(*this, Rand, At, SwingDir.GetSafeNormal(), FMath::RoundToInt(14 * K), 1150.f * K, FLinearColor(1.f, .6f, .22f) * 9.f, .3f, 3.2f);
    Streaks(*this, Rand, At, Strength >= 2 ? 7 : 4, 7.f * K, FLinearColor(1.f, .92f, .8f) * 6.f);
    if (Strength >= 2)
    {
        FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 25.f; Ring.Size1 = 140.f * K; Ring.Life = .2f; Ring.Color = FLinearColor(1.f, .75f, .45f) * 2.6f;
    }
    LightFlash(At, FLinearColor(1.f, .72f, .42f), 11000.f * K, 450.f, .11f);
    Shake(Strength >= 3 ? .75f : Strength == 2 ? .45f : .28f);
    Play(Strength >= 2 ? TEXT("hit_heavy") : TEXT("hit_body"), At, Strength >= 2 ? 1.f : .9f, .06f);
    if (Strength >= 3) SlowMotion(.32f, .3f);
    if (Victim) Dust(Victim->GetActorLocation() - FVector(0, 0, 85.f), .4f + .3f * Strength, SwingDir.GetSafeNormal2D());
}

void AJapanCombatFX::Parry(const FVector& At, AActor* Defender, AActor* Attacker)
{
    HitStop(.09f, Defender, Attacker);
    Flash(At, 80.f, FLinearColor(1.f, .93f, .78f) * 3.f, .12f);
    Flash(At, 30.f, FLinearColor(1.f, 1.f, 1.f) * 6.f, .05f);
    Burst(*this, Rand, At, FVector::UpVector * .4f, 30, 1500.f, FLinearColor(1.f, .85f, .5f) * 7.f, .36f, 3.f);
    Streaks(*this, Rand, At, 7, 6.f, FLinearColor(.9f, .95f, 1.f) * 4.f);
    FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 20.f; Ring.Size1 = 170.f; Ring.Life = .2f; Ring.Color = FLinearColor(.75f, .88f, 1.f) * 2.2f;
    FParticle& Ring2 = Spawn(ESprite::Ring, At); Ring2.Size0 = 10.f; Ring2.Size1 = 120.f; Ring2.Life = .15f; Ring2.Color = FLinearColor(1.f, .9f, .7f) * 3.f;
    LightFlash(At, FLinearColor(.95f, .95f, 1.f), 16000.f, 520.f, .15f);
    Shake(.5f);
    Play(TEXT("parry"), At, 1.f, .04f);
    SlowMotion(.34f, .28f);
}

void AJapanCombatFX::PlayerHurt(const FVector& At, const FVector& From, float Damage, AActor* Victim, AActor* Attacker, bool bKnockDown)
{
    const FVector Dir = (At - From).GetSafeNormal();
    HitStop(bKnockDown ? .12f : .07f, Victim, Attacker);
    Flash(At, 55.f, FLinearColor(1.f, .45f, .3f) * 3.f, .09f);
    Burst(*this, Rand, At, Dir, 12, 900.f, FLinearColor(1.f, .4f, .22f) * 7.f, .26f, 2.8f);
    Streaks(*this, Rand, At, 4, 7.f, FLinearColor(1.f, .75f, .65f) * 5.f);
    LightFlash(At, FLinearColor(1.f, .5f, .35f), 9000.f, 380.f, .09f);
    Shake(bKnockDown ? .9f : .6f);
    Play(TEXT("player_hurt"), At, 1.f, .05f);
    if (AWandererCharacter* P = Cast<AWandererCharacter>(Victim)) P->FlashDamage(bKnockDown ? 1.f : .7f);
    if (bKnockDown && Victim)
    {
        const FVector Ground = Victim->GetActorLocation() - FVector(0, 0, 70.f);
        PlayLater(.55f, TEXT("body_fall"), Ground, 1.f);
        ScheduledDust.Add({ .55f, Ground, 1.2f });
    }
}

void AJapanCombatFX::ChargeTick(const FVector& Base, const FVector& Tip, float Fraction, float Dt)
{
    // Embers lift off the blade; the rate and brightness grow with the charge. A soft glow gathers at the tip.
    ChargeAccumulator += Dt * (26.f + 70.f * Fraction);
    while (ChargeAccumulator >= 1.f)
    {
        ChargeAccumulator -= 1.f;
        FParticle& P = Spawn(ESprite::Glow, FMath::Lerp(Base, Tip, Rand.FRandRange(.15f, 1.f)) + RandomUnit(Rand) * 3.f);
        P.V = FVector(0, 0, Rand.FRandRange(40.f, 110.f)) + RandomUnit(Rand) * 35.f; P.Drag = 1.4f; P.Gravity = -60.f;
        P.Life = Rand.FRandRange(.35f, .7f); P.Size0 = Rand.FRandRange(3.f, 6.f) * (1.f + Fraction); P.Size1 = P.Size0 * .3f;
        P.Color = FLinearColor(1.f, .62f + .2f * Rand.FRand(), .25f) * (5.f + 7.f * Fraction); P.FadeIn = .05f;
    }
    FParticle& G = Spawn(ESprite::Glow, Tip); G.Life = .05f; G.Size0 = G.Size1 = 14.f + 34.f * Fraction; G.Color = FLinearColor(1.f, .7f, .35f) * (1.5f + 4.f * Fraction);
    FParticle& H = Spawn(ESprite::Glow, FMath::Lerp(Base, Tip, .55f)); H.Life = .05f; H.Size0 = H.Size1 = 30.f + 30.f * Fraction; H.Color = FLinearColor(1.f, .6f, .3f) * (.5f + 1.5f * Fraction);
}

void AJapanCombatFX::ChargeReady(const FVector& At)
{
    Flash(At, 90.f, FLinearColor(1.f, .8f, .45f) * 5.f, .18f);
    FParticle& Ring = Spawn(ESprite::Ring, At); Ring.Size0 = 20.f; Ring.Size1 = 150.f; Ring.Life = .26f; Ring.Color = FLinearColor(1.f, .78f, .4f) * 3.f;
    Burst(*this, Rand, At, FVector::UpVector, 14, 700.f, FLinearColor(1.f, .75f, .35f) * 8.f, .35f, 2.6f);
    LightFlash(At, FLinearColor(1.f, .78f, .45f), 8000.f, 400.f, .18f);
    Play(TEXT("charge_ready"), At, .9f, .0f);
}

void AJapanCombatFX::SpiritEmbers(const FVector& At, int32 Count, float Radius, float Rise)
{
    for (int32 I = 0; I < Count; ++I)
    {
        FVector Offset = RandomUnit(Rand) * Rand.FRandRange(0.f, Radius); Offset.Z *= 1.8f;
        FParticle& P = Spawn(ESprite::Glow, At + Offset);
        P.V = FVector(0, 0, Rise * Rand.FRandRange(.5f, 1.3f)) + FVector(Offset.Y, -Offset.X, 0).GetSafeNormal() * Rand.FRandRange(20.f, 70.f);
        P.Drag = .9f; P.Gravity = -Rise * .6f; P.Life = Rand.FRandRange(.8f, 1.8f); P.Size0 = Rand.FRandRange(3.5f, 9.f); P.Size1 = P.Size0 * .25f;
        P.Color = (Rand.FRand() < .7f ? FLinearColor(1.f, .38f, .12f) : FLinearColor(1.f, .82f, .6f)) * Rand.FRandRange(5.f, 10.f); P.FadeIn = .12f; P.Wobble = Rand.FRandRange(20.f, 60.f);
    }
}

// ---- per frame
void AJapanCombatFX::Tick(float Dt)
{
    Super::Tick(Dt);
    const float Real = FApp::GetDeltaTime();
    for (int32 I = Frozen.Num() - 1; I >= 0; --I)
    {
        FFrozen& F = Frozen[I]; F.Remaining -= Real;
        if (F.Remaining <= 0.f || !F.Actor.IsValid()) { if (F.Actor.IsValid()) F.Actor->CustomTimeDilation = 1.f; Frozen.RemoveAt(I); }
    }
    if (SlowRemaining > 0.f)
    {
        SlowRemaining -= Real;
        // Ease back to full speed over the last 40 % of the slow motion.
        const float U = SlowTotal > 0.f ? FMath::Clamp(SlowRemaining / (SlowTotal * .4f), 0.f, 1.f) : 0.f;
        UGameplayStatics::SetGlobalTimeDilation(this, SlowRemaining > 0.f ? FMath::Lerp(1.f, SlowDepth, U) : 1.f);
        if (SlowRemaining <= 0.f) SlowTotal = 0.f;
    }
    for (int32 I = Scheduled.Num() - 1; I >= 0; --I)
    {
        Scheduled[I].Delay -= Dt;
        if (Scheduled[I].Delay <= 0.f) { Play(Scheduled[I].Cue, Scheduled[I].At, Scheduled[I].Volume); Scheduled.RemoveAt(I); }
    }
    for (int32 I = ScheduledDust.Num() - 1; I >= 0; --I)
    {
        ScheduledDust[I].Delay -= Dt;
        if (ScheduledDust[I].Delay <= 0.f) { Dust(ScheduledDust[I].At, ScheduledDust[I].Strength); ScheduledDust.RemoveAt(I); }
    }
    for (FParticle& P : Particles)
    {
        P.Age += Dt;
        P.V.Z -= P.Gravity * Dt;
        P.V *= FMath::Exp(-P.Drag * Dt);
        if (P.Wobble > 0.f) P.V += FVector(FMath::Sin(P.Age * 5.f + P.Seed * 20.f), FMath::Cos(P.Age * 4.f + P.Seed * 13.f), 0.f) * P.Wobble * Dt;
        P.P += P.V * Dt;
    }
    Particles.RemoveAll([](const FParticle& P) { return P.Age >= P.Life; });
    for (int32 I = 0; I < Lights.Num(); ++I)
    {
        FLightFlash& L = LightState[I];
        if (L.Intensity <= 0.f) continue;
        L.Age += Dt;
        const float U = FMath::Clamp(1.f - L.Age / L.Life, 0.f, 1.f);
        Lights[I]->SetIntensity(L.Intensity * U * U);
        if (U <= 0.f) { L.Intensity = 0.f; Lights[I]->SetVisibility(false); }
    }
    Draw();
}

void AJapanCombatFX::Draw()
{
    APlayerController* PC = UGameplayStatics::GetPlayerController(this, 0);
    if (!PC || !PC->PlayerCameraManager) return;
    const FVector Eye = PC->PlayerCameraManager->GetCameraLocation();
    const FRotator View = PC->PlayerCameraManager->GetCameraRotation();
    const FVector Right = FRotationMatrix(View).GetUnitAxis(EAxis::Y);
    TArray<FTransform> Transforms[4]; TArray<float> Data[4];
    for (const FParticle& P : Particles)
    {
        const float T = FMath::Clamp(P.Age / P.Life, 0.f, 1.f);
        const int32 K = int32(P.Kind);
        const FVector ToEye = (Eye - P.P).GetSafeNormal();
        float Fade;
        switch (P.Kind)
        {
            case ESprite::Spark: Fade = 1.f - T; break;
            case ESprite::Ring: Fade = FMath::Pow(1.f - T, 1.4f); break;
            case ESprite::Dust: Fade = FMath::SmoothStep(0.f, .15f, T) * (1.f - FMath::SmoothStep(.35f, 1.f, T)); break;
            default: Fade = FMath::Pow(1.f - T, 1.8f); break;
        }
        if (P.FadeIn > 0.f && P.Kind != ESprite::Dust) Fade *= FMath::Clamp(P.Age / P.FadeIn, 0.f, 1.f);
        // A flash right in front of the lens must not fill the screen: sprites never grow past ~16 degrees of view.
        const float Size = FMath::Min(FMath::Lerp(P.Size0, P.Size1, 1.f - FMath::Square(1.f - T)), .28f * FVector::Dist(Eye, P.P));
        FVector Axis = Right; float Length = Size;
        if (P.Kind == ESprite::Spark)
        {
            const FVector Along = P.V - ToEye * FVector::DotProduct(P.V, ToEye);
            if (Along.SizeSquared() > 1.f) { Axis = Along.GetSafeNormal(); Length = Size * (1.f + P.Stretch * Along.Size()); }
        }
        else if (P.Kind == ESprite::Dust) Axis = Right.RotateAngleAxis(P.Seed * 360.f + P.Age * 25.f, ToEye);
        const FMatrix M = FRotationMatrix::MakeFromZX(ToEye, Axis);
        Transforms[K].Add(FTransform(M.Rotator(), P.P, FVector(Length / 100.f, Size / 100.f, 1.f)));
        // Colours are authored hot; under the daylight exposure they bloom, so all sprites share one damping.
        const float Damp = P.Kind == ESprite::Dust ? 1.f : .45f;
        Data[K].Append({ P.Alpha * Fade * Damp, P.Color.R, P.Color.G, P.Color.B });
    }
    for (int32 K = 0; K < 4; ++K)
    {
        UInstancedStaticMeshComponent* L = SpriteLayers[K];
        L->ClearInstances();
        if (!Transforms[K].Num()) continue;
        L->AddInstances(Transforms[K], false, true);
        for (int32 I = 0; I < Transforms[K].Num(); ++I) L->SetCustomData(I, MakeArrayView(&Data[K][I * 4], 4), false);
        L->MarkRenderStateDirty();
    }
}
