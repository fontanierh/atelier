#pragma once
#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "ProceduralMeshComponent.h"
#include "JapanCombatFX.generated.h"

class UInstancedStaticMeshComponent;
class UPointLightComponent;
class USoundBase;
class USoundWave;
class USoundAttenuation;
class UMaterialInterface;

/** The loaded variants of one combat cue. */
USTRUCT()
struct FJapanSoundBank
{
    GENERATED_BODY()
    UPROPERTY() TArray<TObjectPtr<USoundWave>> Waves;
};

/** One sound the game started, for offline mixing of filmed takes (frame index, not wall time). */
struct FJapanAudioEvent { int32 Frame = 0; FString Sound, Source; FVector At = FVector::ZeroVector; float Volume = 1.f, Pitch = 1.f; bool b2D = false; bool bLoop = false; };

/** Film capture sets these; every sound the game plays is then recorded with the current frame. */
struct YORIMICHI_API FJapanAudioLog
{
    static bool bRecording;
    static int32 Frame;
    static TArray<FJapanAudioEvent> Events;
    static void Record(USoundBase* Sound, const FVector& At, float Volume, float Pitch, bool b2D, bool bLoop = false);
};

/**
 * The blade's slash trail: a ribbon between two points of the blade, sampled every frame while the sword cuts
 * and smoothed with Catmull-Rom between samples so a fast cut stays a clean arc. Vertices are in world space
 * (the component sits at the origin with an absolute transform); colour and alpha fade with age, and a painted
 * streak texture gives the brush-stroke look. It keeps fading after emission stops.
 */
UCLASS()
class YORIMICHI_API UJapanSwordTrail : public UProceduralMeshComponent
{
    GENERATED_BODY()
public:
    UJapanSwordTrail(const FObjectInitializer& ObjectInitializer);
    /** Call every frame: Base/Tip in world space; Emit false lets the remaining trail fade out. Strength 1 light, 2 charged, 3 full. */
    void Sample(const FVector& Base, const FVector& Tip, bool bEmit, int32 Strength, float Dt);
private:
    struct FPoint { FVector Base, Tip; float Age = 0.f; float Weight = 1.f; };
    TArray<FPoint> Points;
    int32 Style = 1;
    bool bWasEmitting = false;
    void Rebuild();
};

/**
 * Combat feedback for the sword fight, owned by one actor per world: camera-facing sprites (sparks, glow flashes,
 * shock rings, dust, spirit embers) drawn as instanced quads with additive or translucent materials that read
 * their colour and intensity from per-instance data; short point-light flashes; hit-stop and slow motion; and the
 * combat sounds (variant banks without back-to-back repeats, spatialized, logged for filmed takes).
 * Everything is cosmetic: gameplay never reads it.
 */
UCLASS()
class YORIMICHI_API AJapanCombatFX : public AActor
{
    GENERATED_BODY()
public:
    AJapanCombatFX();
    static AJapanCombatFX* Get(const UObject* WorldContext);
    virtual void Tick(float Dt) override;

    // ---- events
    void SwordSwing(const FVector& At, int32 Strength);
    void SwordHit(const FVector& At, const FVector& SwingDir, int32 Strength, AActor* Wielder, AActor* Victim);
    void Parry(const FVector& At, AActor* Defender, AActor* Attacker);
    void PlayerHurt(const FVector& At, const FVector& From, float Damage, AActor* Victim, AActor* Attacker, bool bKnockDown);
    void Dust(const FVector& Ground, float Strength, const FVector& Direction = FVector::ZeroVector);
    void ChargeTick(const FVector& Base, const FVector& Tip, float Fraction, float Dt);
    void ChargeReady(const FVector& At);
    void SpiritEmbers(const FVector& At, int32 Count, float Radius, float Rise);
    void Flash(const FVector& At, float Size, const FLinearColor& Color, float Life);
    void LightFlash(const FVector& At, const FLinearColor& Color, float Intensity, float Radius, float Life);
    /** Freezes these actors for Seconds of real time (CustomTimeDilation), then restores them. */
    void HitStop(float Seconds, AActor* A, AActor* B = nullptr);
    /** Global time dilation for Seconds of real time. */
    void SlowMotion(float Seconds, float Dilation);
    void Shake(float Trauma);
    /** A sound that should land a little later (a body reaching the ground after a knock-down). */
    void PlayLater(float Delay, FName Cue, const FVector& At, float Volume = 1.f);
    /** Plays a random variant of /Game/Audio/Combat/<Cue>_NN; returns false if the bank is empty. */
    bool Play(FName Cue, const FVector& At, float Volume = 1.f, float PitchSpread = .05f, bool b2D = false);

    enum class ESprite : uint8 { Glow, Spark, Ring, Dust };
    struct FParticle
    {
        FVector P = FVector::ZeroVector, V = FVector::ZeroVector; float Age = 0.f, Life = .3f, Size0 = 10.f, Size1 = 10.f, Stretch = 0.f, Drag = 0.f, Gravity = 0.f, Alpha = 1.f;
        FLinearColor Color = FLinearColor::White; ESprite Kind = ESprite::Glow; float FadeIn = 0.f; float Wobble = 0.f; float Seed = 0.f;
    };
    FParticle& Spawn(ESprite Kind, const FVector& At);

private:
    UPROPERTY() TArray<TObjectPtr<UInstancedStaticMeshComponent>> SpriteLayers;
    UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Lights;
    UPROPERTY() TObjectPtr<USoundAttenuation> Attenuation;
    UPROPERTY() TMap<FName, FJapanSoundBank> Banks;
    TMap<FName, TArray<int32>> Bags;
    TArray<FParticle> Particles;
    struct FLightFlash { float Age = 0.f, Life = .1f, Intensity = 0.f; };
    TArray<FLightFlash> LightState;
    struct FFrozen { TWeakObjectPtr<AActor> Actor; float Remaining = 0.f; };
    TArray<FFrozen> Frozen;
    float SlowRemaining = 0.f, SlowTotal = 0.f, SlowDepth = 1.f, ChargeAccumulator = 0.f;
    struct FScheduledSound { float Delay = 0.f; FName Cue; FVector At = FVector::ZeroVector; float Volume = 1.f; };
    TArray<FScheduledSound> Scheduled;
    struct FScheduledDust { float Delay = 0.f; FVector At = FVector::ZeroVector; float Strength = 1.f; };
    TArray<FScheduledDust> ScheduledDust;
    FRandomStream Rand;
    const TArray<TObjectPtr<USoundWave>>& Bank(FName Cue);
    void Draw();
};
