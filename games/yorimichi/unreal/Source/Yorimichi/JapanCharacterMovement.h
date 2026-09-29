#pragma once
#include "CoreMinimal.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "JapanCharacterMovement.generated.h"
class AMegaRamp;
/** Ordinary skating retains CharacterMovement; the mini-mega uses swept surface/air physics. */
UCLASS()
class YORIMICHI_API UJapanCharacterMovement : public UCharacterMovementComponent
{
    GENERATED_BODY()
public:
    virtual void CalcVelocity(float Dt,float Friction,bool bFluid,float BrakingDeceleration) override;
    virtual void PhysicsRotation(float Dt) override;
    virtual float GetMaxSpeed() const override;
    virtual void PhysCustom(float Dt,int32 Iterations) override;
    virtual void UpdateCharacterStateBeforeMovement(float DeltaSeconds) override;
    bool TryMegaInteract();
    FString MegaEntryHint() const;
    void MegaJump();
    bool IsMega() const { return MovementMode==MOVE_Custom && CustomMovementMode==1; }
    bool IsMegaClimbing() const { return IsMega()&&MegaPhase==0; }
    FName MegaClip() const;
    float MegaPoseTime() const;
    FString MegaStatus() const;
    float MegaSpeed() const { return SurfaceSpeed; }
    int32 MegaStage() const { return MegaPhase; }
    int32 MegaSection() const { return Section; }
    float MegaProgress() const { return SurfaceS; }
    int32 GapLandings=0,VertLandings=0,RolloutExits=0;
private:
    UPROPERTY() TObjectPtr<AMegaRamp> Ramp;
    int32 MegaPhase=0,Section=0;
    float PhaseTime=0,SurfaceS=0,SurfaceSpeed=0,Lateral=0,LateralSpeed=0,LandingTime=1,AirTime=0;
    FVector BoardPoint=FVector::ZeroVector,AirVelocity=FVector::ZeroVector;
    float VertFlightTime=1.f,RolloutOffset=0;
    bool bVertAir=false,bReturnedVert=false;
    bool EnterMegaDeck(AMegaRamp* Candidate, bool Drop);
    void ExitMega();
    void StartMegaAir(const FVector& V,bool Vert);
};
