#pragma once
#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "JapanFootstepSet.h"
#include "AtelierFX.h"
#include "JapanFootsteps.generated.h"

class AJapanWorld;
class USoundAttenuation;
class USoundWave;
class UAudioComponent;
class UJapanFootstepComponent;
DECLARE_MULTICAST_DELEGATE_OneParam(FJapanFootstepAudioReady, UJapanFootstepComponent*);

/** Plays a footstep when a foot bone plants.
 *
 *  No anim notifies: the animation graph is native C++ with no Blueprint to hang them on, and
 *  the clips are regenerated from Blender on every character pass, which would drop them. Foot
 *  bone height above the capsule floor works for every clip, blend and play rate instead, and
 *  costs one trace per footfall rather than one per frame. */
UCLASS()
class YORIMICHI_API UJapanFootstepComponent : public UActorComponent
{
    GENERATED_BODY()
public:
    UJapanFootstepComponent();
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;
    virtual void TickComponent(float Dt,ELevelTick TickType,FActorComponentTickFunction* Function) override;
    /** A landing plants both feet at once; Weight scales with the drop. */
    void Land(const FHitResult& Hit,float Weight);
    /** A hoof of the horse he rides (UHorseComponent). There is no hoof bank (sound-cues.toml names footstep.<surface>
     *  only): it plays the surface's footstep, heavier and lower. Weight scales the volume with the gait. */
    void Hoof(const FHitResult& Hit,float Weight);
    FName SurfaceAt(const FHitResult& Hit) const;
    bool IsReady() const { return Set != nullptr; }
    bool IsAudioReady() const { return IsReady(); }
    static FJapanFootstepAudioReady AudioReady;
    /** Local human-footstep presentation only (hooves keep their plain playback). */
    void SetAudioPreferences(bool bSoften, float Volume);
private:
    friend class FJapanFootstepShuffleTest;
    friend class FJapanFootstepPreferencesTest;
    UPROPERTY() TObjectPtr<UJapanFootstepSet> Set;
    UPROPERTY() TObjectPtr<AJapanWorld> Landscape;
    // Per foot: planted means the sound has already fired and the foot must swing clear again.
    bool bPlanted[2] = {true,true};
    float Height[2] = {0.f,0.f};
    float SincePlant[2] = {0.f,0.f};
    // Per surface shuffled queue, so the same one-shot never comes round twice in a row.
    TMap<FName,FAtelierShuffleBag> Bags;
    bool bSoftenFootsteps = false;
    float FootstepVolume = 1.f;
    // Weak handles cannot retain finished auto-destroy voices.
    TMap<TWeakObjectPtr<UAudioComponent>,float> FootstepVoices;
    void ApplyVoicePreferences(UAudioComponent* Voice, float BaseVolume) const;
    void PlayFootstepVoice(USoundWave* Wave, const FVector& At, float Volume, float Pitch);
    void StopFootstepVoices();
    void Plant(int32 Side,const FVector& Foot,float Speed);
    USoundWave* DrawStep(FName Surface);
    /** bHoof: a hoof stand-in, played plainly without the human-footstep soften/volume preferences. */
    void Play(FName Surface,const FVector& At,float Volume,float Pitch,bool bHoof=false);
};
