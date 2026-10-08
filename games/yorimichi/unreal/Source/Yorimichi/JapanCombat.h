#pragma once
#include "CoreMinimal.h"
#include "Engine/NetSerialization.h"
#include "JapanCombat.generated.h"

class AWandererCharacter;

UENUM()
enum class EJapanCombatCue : uint8 { Hit, Parry, Hurt, Dodge, Sound, Swing, Guard, GuardBreak, Draw, ChargeReady, Dash };

USTRUCT()
struct FJapanCombatEvent
{
    GENERATED_BODY()
    UPROPERTY() uint32 Serial = 0;
    UPROPERTY() uint32 ActivityEpoch = 0;
    UPROPERTY() EJapanCombatCue Kind = EJapanCombatCue::Hit;
    UPROPERTY() FVector_NetQuantize100 At = FVector::ZeroVector;
    UPROPERTY() FVector_NetQuantize100 Direction = FVector::ZeroVector;
    UPROPERTY() TObjectPtr<AActor> Actor = nullptr;
    UPROPERTY() TObjectPtr<AActor> Other = nullptr;
    UPROPERTY() float Amount = 0.f;
    UPROPERTY() bool bDown = false;
    UPROPERTY() FName Sound;
};

namespace JapanCombat
{
    /** Keeps a live nearby target until it is lost, then selects among all admitted players, including headless guests. */
    AWandererCharacter* FindPlayer(const AActor* Seeker, AWandererCharacter* Current, float Range);
    /** Server-authored cosmetic event. Returns true online, where local gameplay must not emit it a second time. */
    bool Publish(const UObject* Context, EJapanCombatCue Kind, const FVector& At, const FVector& Direction,
        float Amount, AActor* Actor = nullptr, AActor* Other = nullptr, bool bDown = false, FName Sound = NAME_None);
    void Present(const UObject* Context, const FJapanCombatEvent& Event, bool bOwnerConfirmed = false);
    bool DurableOwnerCue(EJapanCombatCue Kind);
    /** Immediate offline/NPC strikes, bounded and ordered adjudication for online players. */
    void Strike(AActor* Source, AWandererCharacter* Victim, float Damage, const FVector& From,
        TFunction<void(int32)> Result = TFunction<void(int32)>());
}
