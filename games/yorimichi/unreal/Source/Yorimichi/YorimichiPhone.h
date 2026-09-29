#pragma once
#include "CoreMinimal.h"
class AWandererCharacter;
class FAtelierStream;

/**
 * Yorimichi on the phone stream (phone/, the touch page): the platform's stream channel (AtelierStream) with the
 * game's actions (settings, map, teleport, flight speed) and its touch controls mapped onto the character. Only exists
 * with -AtelierStream. The controls apply while the touch page sends them; the plain player (/play/) drives the game
 * with the far device's own keyboard, mouse or controller instead.
 */
class FYorimichiPhone
{
public:
    explicit FYorimichiPhone(AWandererCharacter* InRider);
    void Tick(float Dt);
    /** A touch page drives the game now (the HUD steps aside: the page draws its own). */
    bool IsTouchActive() const;
private:
    void SendSettings(const FString& Player);
    void SendMap(const FString& Player);
    TWeakObjectPtr<AWandererCharacter> Rider;
    TSharedPtr<FAtelierStream> Stream;
    double LastStatus = 0.;
    bool bBrakeAfterLease = false;   // the link dropped while sailing: hold the sail down until touch input returns
};
