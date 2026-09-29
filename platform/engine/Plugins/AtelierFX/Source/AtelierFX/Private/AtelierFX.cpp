#include "AtelierFX.h"
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

bool FAtelierAudioLog::bRecording = false;
int32 FAtelierAudioLog::Frame = 0;
TArray<FAtelierAudioEvent> FAtelierAudioLog::Events;

void FAtelierAudioLog::Record(USoundBase* Sound, const FVector& At, float Volume, float Pitch, bool b2D, bool bLoop)
{
    if (!bRecording || !Sound) return;
    FAtelierAudioEvent E; E.Frame = Frame; E.Sound = Sound->GetPathName(); E.At = At; E.Volume = Volume; E.Pitch = Pitch; E.b2D = b2D; E.bLoop = bLoop;
#if WITH_EDITORONLY_DATA
    if (const USoundWave* Wave = Cast<USoundWave>(Sound); Wave && Wave->AssetImportData) E.Source = Wave->AssetImportData->GetFirstFilename();
#endif
    Events.Add(E);
}

// ------------------------------------------------------------------ slash trail
UAtelierTrail::UAtelierTrail(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
    SetUsingAbsoluteLocation(true); SetUsingAbsoluteRotation(true); SetUsingAbsoluteScale(true);
    SetCollisionEnabled(ECollisionEnabled::NoCollision);
    SetCastShadow(false);
    bUseAsyncCooking = false;
    SetGenerateOverlapEvents(false);
}

static float TrailLife(int32 Style) { return Style >= 3 ? .24f : Style == 2 ? .19f : .13f; }

void UAtelierTrail::Sample(const FVector& Base, const FVector& Tip, bool bEmit, int32 Strength, float Dt)
{
    if (!GetMaterial(0))
        if (UMaterialInterface* M = Cast<UMaterialInterface>(GetDefault<UAtelierFXSettings>()->TrailMaterial.TryLoad()))
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

void UAtelierTrail::Rebuild()
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

AAtelierFX::AAtelierFX()
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

AAtelierFX* AAtelierFX::Get(const UObject* WorldContext)
{
    UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
    if (!World) return nullptr;
    if (TActorIterator<AAtelierFX> It(World); It) return *It;
    FActorSpawnParameters Params; Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
    const UAtelierFXSettings* Settings = GetDefault<UAtelierFXSettings>();
    UClass* Class = Settings->FXClass.LoadSynchronous();
    AAtelierFX* FX = World->SpawnActor<AAtelierFX>(Class ? Class : AAtelierFX::StaticClass(), FVector::ZeroVector, FRotator::ZeroRotator, Params);
    if (!FX) return nullptr;
    UStaticMesh* Plane = LoadObject<UStaticMesh>(nullptr, TEXT("/Engine/BasicShapes/Plane.Plane"));
    for (int32 I = 0; I < FX->SpriteLayers.Num(); ++I)
    {
        FX->SpriteLayers[I]->SetStaticMesh(Plane);
        const FSoftObjectPath& Path = I == 0 ? Settings->GlowMaterial : I == 1 ? Settings->SparkMaterial : I == 2 ? Settings->RingMaterial : Settings->DustMaterial;
        if (UMaterialInterface* M = Cast<UMaterialInterface>(Path.TryLoad())) FX->SpriteLayers[I]->SetMaterial(0, M);
        else UE_LOG(LogTemp, Warning, TEXT("FX sprite material missing: %s (AtelierFXSettings)"), *Path.ToString());
    }
    FX->Attenuation = NewObject<USoundAttenuation>(FX);
    FSoundAttenuationSettings& A = FX->Attenuation->Attenuation;
    A.bAttenuate = true; A.bSpatialize = true; A.AttenuationShape = EAttenuationShape::Sphere;
    A.AttenuationShapeExtents = FVector(450.f, 0.f, 0.f); A.FalloffDistance = 5000.f; A.DistanceAlgorithm = EAttenuationDistanceModel::NaturalSound; A.dBAttenuationAtMax = -48.f;
    A.NonSpatializedRadiusStart = 250.f; A.NonSpatializedRadiusEnd = 60.f; A.NonSpatializedRadiusMode = ENonSpatializedRadiusSpeakerMapMode::OmniDirectional;
    return FX;
}

AAtelierFX::FParticle& AAtelierFX::Spawn(ESprite Kind, const FVector& At)
{
    FParticle& P = Particles.AddDefaulted_GetRef(); P.Kind = Kind; P.P = At; P.Seed = Rand.FRand();
    return P;
}

static FVector RandomUnit(FRandomStream& R) { return R.GetUnitVector(); }

// ---- sounds
const TArray<TObjectPtr<USoundWave>>& AAtelierFX::Bank(FName Cue)
{
    if (FAtelierSoundBank* Found = Banks.Find(Cue)) return Found->Waves;
    FAtelierSoundBank& New = Banks.Add(Cue);
    for (int32 I = 1; I <= 16; ++I)
    {
        const FString Name = FString::Printf(TEXT("%s_%02d"), *Cue.ToString(), I);
        USoundWave* Wave = LoadObject<USoundWave>(nullptr, *FString::Printf(TEXT("%s/%s.%s"), *GetDefault<UAtelierFXSettings>()->SoundFolder, *Name, *Name), nullptr, LOAD_NoWarn | LOAD_Quiet);
        if (!Wave) break;
        New.Waves.Add(Wave);
    }
    if (!New.Waves.Num()) UE_LOG(LogTemp, Warning, TEXT("Sound bank empty: %s"), *Cue.ToString());
    return New.Waves;
}

bool AAtelierFX::Play(FName Cue, const FVector& At, float Volume, float PitchSpread, bool b2D)
{
    const TArray<TObjectPtr<USoundWave>>& Waves = Bank(Cue);
    if (!Waves.Num()) return false;
    TArray<int32>& Bag = Bags.FindOrAdd(Cue);
    if (!Bag.Num()) { for (int32 I = 0; I < Waves.Num(); ++I) Bag.Add(I); for (int32 I = Bag.Num() - 1; I > 0; --I) Bag.Swap(I, Rand.RandHelper(I + 1)); }
    USoundWave* Wave = Waves[Bag.Pop(EAllowShrinking::No)];
    const float Pitch = 1.f + Rand.FRandRange(-PitchSpread, PitchSpread);
    if (b2D) UGameplayStatics::PlaySound2D(this, Wave, Volume, Pitch);
    else UGameplayStatics::PlaySoundAtLocation(this, Wave, At, FRotator::ZeroRotator, Volume, Pitch, 0.f, Attenuation);
    FAtelierAudioLog::Record(Wave, At, Volume, Pitch, b2D);
    return true;
}

// ---- timing
void AAtelierFX::HitStop(float Seconds, AActor* A, AActor* B)
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

void AAtelierFX::SlowMotion(float Seconds, float Dilation)
{
    SlowRemaining = FMath::Max(SlowRemaining, Seconds); SlowTotal = FMath::Max(SlowTotal, Seconds); SlowDepth = Dilation;
    UGameplayStatics::SetGlobalTimeDilation(this, Dilation);
}

void AAtelierFX::Shake(float Trauma)
{
    if (IAtelierFXTarget* Target = Cast<IAtelierFXTarget>(UGameplayStatics::GetPlayerPawn(this, 0))) Target->AddCameraShake(Trauma);
}

void AAtelierFX::PlayLater(float Delay, FName Cue, const FVector& At, float Volume) { Scheduled.Add({ Delay, Cue, At, Volume }); }
void AAtelierFX::DustLater(float Delay, const FVector& Ground, float Strength) { ScheduledDust.Add({ Delay, Ground, Strength }); }

// ---- visuals
void AAtelierFX::Flash(const FVector& At, float Size, const FLinearColor& Color, float Life)
{
    FParticle& P = Spawn(ESprite::Glow, At); P.Size0 = Size * .55f; P.Size1 = Size; P.Life = Life; P.Color = Color;
}

void AAtelierFX::LightFlash(const FVector& At, const FLinearColor& Color, float Intensity, float Radius, float Life)
{
    int32 Best = 0; for (int32 I = 1; I < LightState.Num(); ++I) if (LightState[I].Age / LightState[I].Life > LightState[Best].Age / LightState[Best].Life) Best = I;
    UPointLightComponent* L = Lights[Best];
    Intensity *= .045f;   // a warm kick on the fighters (hundreds of lumens: the shop practicals are 350), not a floodlight
    L->SetWorldLocation(At); L->SetLightColor(Color); L->SetAttenuationRadius(Radius); L->SetIntensity(Intensity); L->SetVisibility(true);
    LightState[Best] = { 0.f, Life, Intensity };
}

void AAtelierFX::Dust(const FVector& Ground, float Strength, const FVector& Direction)
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

void AAtelierFX::Burst(const FVector& At, const FVector& Bias, int32 Count, float Speed, const FLinearColor& Color, float Life, float Size)
{
    for (int32 I = 0; I < Count; ++I)
    {
        FVector Dir = (Bias * .75f + Rand.GetUnitVector()).GetSafeNormal();
        FParticle& P = Spawn(ESprite::Spark, At);
        P.V = Dir * Speed * Rand.FRandRange(.45f, 1.1f); P.Drag = 3.5f; P.Gravity = 1300.f; P.Life = Life * Rand.FRandRange(.5f, 1.2f);
        P.Size0 = Size * Rand.FRandRange(.6f, 1.2f); P.Size1 = P.Size0 * .4f; P.Stretch = .028f; P.Color = Color * Rand.FRandRange(.7f, 1.2f);
    }
}

void AAtelierFX::Streaks(const FVector& At, int32 Count, float Size, const FLinearColor& Color)
{
    for (int32 I = 0; I < Count; ++I)
    {
        FParticle& P = Spawn(ESprite::Spark, At);
        P.V = Rand.GetUnitVector() * Rand.FRandRange(1500.f, 2400.f); P.Drag = 11.f; P.Life = Rand.FRandRange(.08f, .13f);
        P.Size0 = Size; P.Size1 = Size * .5f; P.Stretch = .05f; P.Color = Color;
    }
}

// ---- per frame
void AAtelierFX::Tick(float Dt)
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

void AAtelierFX::Draw()
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
