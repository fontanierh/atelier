#include "CairoCharacter.h"
#include "JapanNetwork.h"
#include "AtelierData.h"
#include "AdventureMoveSet.h"
#include "AtelierStream.h"
#include "PlayableCharacter.h"
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
    const TCHAR* AdventureDefinition = TEXT("/Game/CairoAdventure/DA_CairoAdventure.DA_CairoAdventure");

    /** Cairo's move record, read once; null when it has not been built. */
    TSharedPtr<FJsonObject> AdventureRecord()
    {
        static TSharedPtr<FJsonObject> Record;
        static bool bLoaded = false;
        if (!bLoaded)
        {
            bLoaded = true;
            Record = AtelierReadJson(AtelierDataPath(TEXT("cairo/adventure.json")));
        }
        return Record;
    }
}

// Cairo is the default character, with his legacy moves or the merged set as he chooses at BeginPlay; CairoAdventure is him
// with the merged set (FPlayableCharacter). The switch tells a switched-in Cairo which.
static void PrepareCairo(AWandererCharacter* Pawn, const FString& Name) { CastChecked<ACairoCharacter>(Pawn)->SetAdventure(Name == ACairoCharacter::AdventureName()); }
static const FPlayableCharacter::FRegister RegisterCairo({TEXT("Cairo"), &ACairoCharacter::StaticClass, nullptr, TEXT("unreal.cairo"), &PrepareCairo, true,
                                                          ACairoCharacter::AdventureName()});
static const FPlayableCharacter::FRegister RegisterCairoAdventure({ACairoCharacter::AdventureName(), &ACairoCharacter::StaticClass, &ACairoCharacter::HasAdventure,
                                                              TEXT("unreal.cairo_adventure"), &PrepareCairo});

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

bool ACairoCharacter::HasAdventure()
{
    // Checked on disk, not loaded: the character switch asks every time the menu opens.
    return AdventureRecord().IsValid() && FPackageName::DoesPackageExist(FPackageName::ObjectPathToPackageName(FString(AdventureDefinition)));
}


void ACairoCharacter::BeginPlay()
{
    // Where a person plays, the "Move set" setting picks the merged set (the default), when built, or his original moves.
    // QA, reviews and benchmarks keep his original moves
    // unless the command line asks (-rider=CairoAdventure). A switched-in Cairo was told by the switch.
    if (JapanNetwork::IsOnline(GetWorld()) && !IsNpc()) bAdventure = true;
    else if (!bSwitchedIn)
    {
        const FString Requested = FPlayableCharacter::Requested();
        const bool bPlayed = !AJapanGameMode::IsScriptedSession() || FAtelierStream::IsRequested();
        bAdventure = Requested == AdventureName() || (Requested.IsEmpty() && bPlayed && HasAdventure() && UAdventureMoveSet::Chosen() != UAdventureMoveSet::LegacyCairo);
    }
    if (bAdventure)
    {
        DefinitionAssetPath = AdventureDefinition;
        SprintSpeedMultiplier = 1.f;   // the reference rig's sprint: the dash clip's own stride speed
    }
    Super::BeginPlay();
    if (bAdventure)
    {
        UAdventureMoveSet* Set = NewObject<UAdventureMoveSet>(this, TEXT("AdventureMoves"));
        if (Set->Initialize(this, AdventureRecord())) Moves = Set;
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
