#pragma once
#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "JapanCombatResolver.generated.h"

class AWandererCharacter;

/** Server-only contact queue. Each victim keeps contact order while the host waits
 * briefly for defensive input; health and live movement are never rewound. */
UCLASS()
class YORIMICHI_API UJapanCombatResolver : public UTickableWorldSubsystem
{
    GENERATED_BODY()
public:
    using FResult = TFunction<void(int32)>;
    virtual bool DoesSupportWorldType(EWorldType::Type Type) const override;
    virtual void Tick(float Dt) override;
    virtual TStatId GetStatId() const override;
    virtual void Deinitialize() override;
    void Strike(AActor* Source, AWandererCharacter* Victim, float Damage,
        const FVector& From, FResult Result = FResult());
    bool HasPending(const AWandererCharacter* Victim) const;
    /** Mandatory server recovery drains contacts before moving/resetting the victim. */
    void Flush(AWandererCharacter* Victim);
    uint32 PendingSkateRefusals = 0, PendingTravelRefusals = 0;
    uint32 PendingBikeRefusals = 0, PendingSailRefusals = 0;
    uint32 Queued = 0, Resolved = 0, Cancelled = 0, Overflows = 0, Flushed = 0;
private:
    struct FContact
    {
        TWeakObjectPtr<AActor> Source;
        TWeakObjectPtr<AWandererCharacter> Victim;
        uint32 Epoch = 0;
        double Time = 0., Due = 0.;
        float Damage = 0.f;
        FVector From = FVector::ZeroVector;
        FResult Result;
    };
    TArray<FContact> Pending;
    void Resolve(FContact&& Contact);
    void RefreshRetention(AWandererCharacter* Victim);
};
