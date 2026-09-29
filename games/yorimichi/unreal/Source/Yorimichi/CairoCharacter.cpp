#include "CairoCharacter.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"

ACairoCharacter::ACairoCharacter()
{
    DefinitionAssetPath = TEXT("/Game/Cairo/DA_Cairo.DA_Cairo");
    SprintSpeedMultiplier = 1.25f;
    GetCapsuleComponent()->InitCapsuleSize(22.f,74.f);
    GetCharacterMovement()->SetCrouchedHalfHeight(65.f);
    GetMesh()->SetRelativeLocation(FVector(0,0,-74.65f));
    // The imported Tripo skeleton faces +X (measured toe-to-ankle vector).
    GetMesh()->SetRelativeRotation(FRotator::ZeroRotator);
}

void ACairoCharacter::Tick(float Dt)
{
    Super::Tick(Dt);
    if(Dt<=SMALL_NUMBER || !GetMesh()->GetSkeletalMeshAsset())return;
    const FTransform Head=GetMesh()->GetSocketTransform(TEXT("head"));
    const FVector Position=Head.GetLocation();
    // Teleports and long suspended frames must not kick the spring.
    if(!bHairInitialized || Dt>.1f || FVector::DistSquared(Position,PreviousHairHead)>2500.f)
    {
        bHairInitialized=true;PreviousHairHead=Position;PreviousHairVelocity=FVector::ZeroVector;
        HairFlex=HairFlexVelocity=FVector2D::ZeroVector;
    }
    const FVector Velocity=(Position-PreviousHairHead)/Dt;
    const FVector Acceleration=GetActorTransform().InverseTransformVectorNoScale((Velocity-PreviousHairVelocity)/Dt);
    PreviousHairHead=Position;PreviousHairVelocity=Velocity;
    const FName Action=GetAnimationAction();
    const bool ContactAction=Action==TEXT("Roll") || Action==TEXT("DoubleJump");
    HairContactFade=FMath::FInterpConstantTo(HairContactFade,ContactAction?0.f:1.f,Dt,8.f);
    // Use the character's +X forward/+Y lateral frame, independent of FBX's
    // bone-axis conversion. The tip fields follow the skinned head themselves.
    FVector2D Target=ContactAction?FVector2D::ZeroVector:FVector2D(-(Acceleration.X+.45*Acceleration.Z)/1800.,-Acceleration.Y/1800.);
    if(Target.SizeSquared()>1.)Target.Normalize();
    const int32 Steps=FMath::Max(1,FMath::CeilToInt(Dt*120.f));
    const float H=Dt/Steps,Omega=18.f,Damping=.8f;
    for(int32 I=0;I<Steps;++I)
    {
        HairFlexVelocity+=(Omega*Omega*(Target-HairFlex)-2.f*Damping*Omega*HairFlexVelocity)*H;
        HairFlex+=HairFlexVelocity*H;
        if(HairFlex.SizeSquared()>1.){HairFlex.Normalize();HairFlexVelocity=FVector2D::ZeroVector;}
    }
    const float Enabled=FParse::Param(FCommandLine::Get(),TEXT("cairostatichair"))?0.f:HairContactFade;
    GetMesh()->SetMorphTarget(TEXT("head_Hair_fore"),HairFlex.X*Enabled);
    GetMesh()->SetMorphTarget(TEXT("head_Hair_side"),HairFlex.Y*Enabled);
}
