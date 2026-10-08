#include "CairoCharacter.h"
#include "JapanNetwork.h"
#include "AtelierData.h"
#include "BotwMoveSet.h"
#include "AtelierStream.h"
#include "BotwRider.h"
#include "JapanGameMode.h"
#include "JapanPreferences.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Misc/FileHelper.h"
#include "Misc/PackageName.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

namespace
{
    const TCHAR* BotwDefinition = TEXT("/Game/CairoBotw/DA_CairoBotw.DA_CairoBotw");

    /** Cairo's move record, read once; null when it has not been built. */
    TSharedPtr<FJsonObject> BotwRecord()
    {
        static TSharedPtr<FJsonObject> Record;
        static bool bLoaded = false;
        if (!bLoaded)
        {
            bLoaded = true;
            Record = AtelierReadJson(AtelierDataPath(TEXT("cairo/botw.json")));
        }
        return Record;
    }
}

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

bool ACairoCharacter::HasBotw()
{
    // Checked on disk, not loaded: the character switch asks every time the menu opens.
    return BotwRecord().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(BotwDefinition)));
}

void ACairoCharacter::BeginPlay()
{
    // Where a person plays, the "Move set" setting picks: the merged set (the default) or the legacy BOTW set on Link's
    // retargeted clips, whenever they are built, or his legacy moves. QA, reviews and benchmarks keep his legacy moves
    // unless the command line asks (-rider=CairoBotw). A switched-in Cairo was told by the switch.
    if (JapanNetwork::IsOnline(GetWorld()) && !IsNpc()) bBotw = true;
    else if (!bSwitchedIn)
    {
        const FString Requested = ABotwRider::Requested();
        const bool bPlayed = !AJapanGameMode::IsScriptedSession() || FAtelierStream::IsRequested();
        bBotw = Requested == BotwName() || (Requested.IsEmpty() && bPlayed && HasBotw() && UBotwMoveSet::Chosen() != UBotwMoveSet::LegacyCairo);
    }
    if (bBotw)
    {
        DefinitionAssetPath = BotwDefinition;
        SprintSpeedMultiplier = 1.f;   // Link's sprint: the dash clip's own stride speed
    }
    Super::BeginPlay();
    if (bBotw)
    {
        UBotwMoveSet* Set = NewObject<UBotwMoveSet>(this, TEXT("BotwMoves"));
        if (Set->Initialize(this, BotwRecord())) Moves = Set;
    }
}

void ACairoCharacter::Tick(float Dt)
{
    Super::Tick(Dt);
    if(GetNetMode()==NM_DedicatedServer)return;
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
