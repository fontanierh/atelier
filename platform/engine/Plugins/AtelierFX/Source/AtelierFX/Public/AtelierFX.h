#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/DeveloperSettings.h"
#include "UObject/Interface.h"
#include "ProceduralMeshComponent.h"
#include "AtelierFX.generated.h"

class UInstancedStaticMeshComponent;
class UPointLightComponent;
class USoundBase;
class USoundWave;
class USoundAttenuation;
class UMaterialInterface;
class AAtelierFX;

/** What the effects need from the game, set in its DefaultGame.ini under [/Script/AtelierFX.AtelierFXSettings]. */
UCLASS(Config = Game, DefaultConfig, meta = (DisplayName = "Atelier FX"))
class ATELIERFX_API UAtelierFXSettings : public UDeveloperSettings
{
    GENERATED_BODY()
public:
    /** The effects actor to spawn, usually the game's subclass with its own reactions. */
    UPROPERTY(Config, EditAnywhere, Category = "FX") TSoftClassPtr<AAtelierFX> FXClass;
    /** Sprite materials (instanced quads; per-instance data: alpha, R, G, B). */
    UPROPERTY(Config, EditAnywhere, Category = "FX") FSoftObjectPath GlowMaterial;
    UPROPERTY(Config, EditAnywhere, Category = "FX") FSoftObjectPath SparkMaterial;
    UPROPERTY(Config, EditAnywhere, Category = "FX") FSoftObjectPath RingMaterial;
    UPROPERTY(Config, EditAnywhere, Category = "FX") FSoftObjectPath DustMaterial;
    /** Ribbon trail material (vertex colour, scalar parameter "Intensity"). */
    UPROPERTY(Config, EditAnywhere, Category = "FX") FSoftObjectPath TrailMaterial;
    /** Content folder of the sound cues: a cue <name> plays a random one of <SoundFolder>/<name>_01.._16. */
    UPROPERTY(Config, EditAnywhere, Category = "FX") FString SoundFolder;
};

/** A pawn that reacts to camera shake from the effects (the game's player implements it). */
UINTERFACE(MinimalAPI)
class UAtelierFXTarget : public UInterface { GENERATED_BODY() };
class ATELIERFX_API IAtelierFXTarget
{
    GENERATED_BODY()
public:
    virtual void AddCameraShake(float Trauma) = 0;
};

/** The loaded variants of one cue. */
USTRUCT()
struct FAtelierSoundBank
{
    GENERATED_BODY()
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
};

/** One sound the game started, for offline mixing of filmed takes (frame index, not wall time). */
struct FAtelierAudioEvent { int32 Frame = 0; FString Sound, Source; FVector At = FVector::ZeroVector; float Volume = 1.f, Pitch = 1.f; bool b2D = false; bool bLoop = false; };

/** Film capture sets these; every sound the game plays is then recorded with the current frame. */
struct ATELIERFX_API FAtelierAudioLog
{
    static bool bRecording;
    static int32 Frame;
    static TArray<FAtelierAudioEvent> Events;
    static void Record(USoundBase* Sound, const FVector& At, float Volume, float Pitch, bool b2D, bool bLoop = false);
};

/**
 * A ribbon between two moving points (a blade's base and tip), sampled every frame while it emits and smoothed with
 * Catmull-Rom between samples so a fast cut stays a clean arc. Vertices are in world space; colour and alpha fade with
 * age. It keeps fading after emission stops. Strength 1, 2 or 3 sets its length, colour and intensity.
 */
UCLASS()
class ATELIERFX_API UAtelierTrail : public UProceduralMeshComponent
{
    GENERATED_BODY()
public:
    UAtelierTrail(const FObjectInitializer& ObjectInitializer);
    /** Call every frame: Base/Tip in world space; Emit false lets the remaining trail fade out. */
    void Sample(const FVector& Base, const FVector& Tip, bool bEmit, int32 Strength, float Dt);
private:
    struct FPoint { FVector Base, Tip; float Age = 0.f; float Weight = 1.f; };
    TArray<FPoint> Points;
    int32 Style = 1;
    bool bWasEmitting = false;
    void Rebuild();
};

/**
 * Cosmetic feedback, one actor per world: camera-facing sprites (sparks, glow flashes, shock rings, dust, embers) drawn
 * as instanced quads whose materials read colour and intensity from per-instance data; short point-light flashes;
 * hit-stop and slow motion; camera shake (through IAtelierFXTarget); and sound cues (variant banks without
 * back-to-back repeats, spatialized, logged for filmed takes). Games subclass it to compose their own reactions from
 * these primitives. Gameplay never reads it.
 */
UCLASS()
class ATELIERFX_API AAtelierFX : public AActor
{
    GENERATED_BODY()
public:
    AAtelierFX();
    /** The world's effects actor, spawned on first use as the configured FXClass. */
    static AAtelierFX* Get(const UObject* WorldContext);
    virtual void Tick(float Dt) override;

    enum class ESprite : uint8 { Glow, Spark, Ring, Dust };
    struct FParticle
    {
        FVector P = FVector::ZeroVector, V = FVector::ZeroVector; float Age = 0.f, Life = .3f, Size0 = 10.f, Size1 = 10.f, Stretch = 0.f, Drag = 0.f, Gravity = 0.f, Alpha = 1.f;
        FLinearColor Color = FLinearColor::White; ESprite Kind = ESprite::Glow; float FadeIn = 0.f; float Wobble = 0.f; float Seed = 0.f;
    };
    FParticle& Spawn(ESprite Kind, const FVector& At);

    void Flash(const FVector& At, float Size, const FLinearColor& Color, float Life);
    void LightFlash(const FVector& At, const FLinearColor& Color, float Intensity, float Radius, float Life);
    void Dust(const FVector& Ground, float Strength, const FVector& Direction = FVector::ZeroVector);
    /** Sparks thrown from At, biased along Bias. */
    void Burst(const FVector& At, const FVector& Bias, int32 Count, float Speed, const FLinearColor& Color, float Life, float Size);
    /** Fast, short streaks in every direction. */
    void Streaks(const FVector& At, int32 Count, float Size, const FLinearColor& Color);
    /** Freezes these actors for Seconds of real time (CustomTimeDilation), then restores them. */
    void HitStop(float Seconds, AActor* A, AActor* B = nullptr);
    /** Global time dilation for Seconds of real time, easing back over the last 40 %. */
    void SlowMotion(float Seconds, float Dilation);
    /** Adds trauma to the player's camera shake (its pawn implements IAtelierFXTarget). */
    void Shake(float Trauma);
    /** A cue that should land a little later (a body reaching the ground). */
    void PlayLater(float Delay, FName Cue, const FVector& At, float Volume = 1.f);
    /** Dust that should rise a little later. */
    void DustLater(float Delay, const FVector& Ground, float Strength);
    /** Plays a random variant of <SoundFolder>/<Cue>_NN; returns false if the bank is empty. */
    bool Play(FName Cue, const FVector& At, float Volume = 1.f, float PitchSpread = .05f, bool b2D = false);

protected:
    FRandomStream Rand;
    TArray<FParticle> Particles;

private:
    UPROPERTY() TArray<TObjectPtr<UInstancedStaticMeshComponent>> SpriteLayers;
    UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Lights;
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    UPROPERTY() TMap<FName, FAtelierSoundBank> Banks;
    TMap<FName, TArray<int32>> Bags;
    struct FLightFlash { float Age = 0.f, Life = .1f, Intensity = 0.f; };
    TArray<FLightFlash> LightState;
    struct FFrozen { TWeakObjectPtr<AActor> Actor; float Remaining = 0.f; };
    TArray<FFrozen> Frozen;
    float SlowRemaining = 0.f, SlowTotal = 0.f, SlowDepth = 1.f;
    struct FScheduledSound { float Delay = 0.f; FName Cue; FVector At = FVector::ZeroVector; float Volume = 1.f; };
    TArray<FScheduledSound> Scheduled;
    struct FScheduledDust { float Delay = 0.f; FVector At = FVector::ZeroVector; float Strength = 1.f; };
    TArray<FScheduledDust> ScheduledDust;
    const TArray<TObjectPtr<USoundWave>>& Bank(FName Cue);
    void Draw();
};
