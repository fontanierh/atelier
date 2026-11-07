#pragma once
#include "CoreMinimal.h"
class AActor;
class AFoxHunter;
class AWandererCharacter;
class UWorld;

/** Nonshipping shared-enemy proof. Hooks observe the ordinary combat paths. */
namespace JapanEnemyQA
{
    void QueuedAttack(AWandererCharacter* Player, uint32 Epoch, uint16 Edge);
    void AcceptedAttack(AWandererCharacter* Player, uint32 Epoch, uint16 Edge);
    void StartedCut(AWandererCharacter* Player, bool BufferedPress);
    void BeginHunter(AFoxHunter* Fox);
    void AuthorityTick(AFoxHunter* Fox);
    void Sweep(AFoxHunter* Fox);
    void Noticed(AFoxHunter* Fox);
    void SwordDamage(AFoxHunter* Fox, AActor* Attacker, int32 Power, int32 Before, int32 After);
    void BladeCandidate(AWandererCharacter* Player, AActor* Victim);
    uint32 Contact(AFoxHunter* Fox, AWandererCharacter* Victim, float Damage);
    void Resolved(uint32 Contact, int32 Outcome);
    bool Tick(UWorld* World, bool Server, const FString& Folder, FString& Error);
    bool Finalize(const FString& Folder, FString& Error);
}
