#pragma once
class AWandererCharacter;
class UDrivingComponent;
/** Read the character's authored wheel-local frames and adapt bind axes to the imported skeleton. */
void ReadKartGrip(AWandererCharacter* Pawn, UDrivingComponent* Car);
