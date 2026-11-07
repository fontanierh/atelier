#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "JapanAudioPreferences.generated.h"

class UJapanFootstepComponent;
class USkateComponent;

/** This client's local footstep and skate sound preferences (soften, volume) for its own world, applied to the
 * emitters that are already live and to each one that becomes audio-ready later, including remote players'.
 * Presentation only: no simulation state, replicated preference or server authority belongs here. */
UCLASS()
class YORIMICHI_API UJapanAudioPreferences : public UWorldSubsystem
{
    GENERATED_BODY()
public:
    virtual void Initialize(FSubsystemCollectionBase& Collection) override;
    virtual void Deinitialize() override;
    void SetFootstepPreferences(bool bSoften, float Volume);
    void SetSkatePreferences(bool bSoften, float Volume);
protected:
    virtual bool DoesSupportWorldType(EWorldType::Type Type) const override
    { return Type == EWorldType::Game || Type == EWorldType::PIE; }
private:
    friend class FJapanFootstepPreferencesTest;
    friend class FJapanSkatePreferencesTest;
    void FootReady(UJapanFootstepComponent* Component);
    void SkateReady(USkateComponent* Component);
    bool bShuttingDown = false;
    bool bSoftenFootsteps = false;
    float FootstepVolume = 1.f;
    bool bSoftenSkate = false;
    float SkateVolume = 1.f;
    FDelegateHandle FootHandle, SkateHandle;
};
