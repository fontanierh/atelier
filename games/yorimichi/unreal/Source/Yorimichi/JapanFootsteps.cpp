#include "JapanFootsteps.h"
#include "JapanCharacterMovement.h"
#include "YorimichiCombatFX.h"
#include "JapanWorld.h"
#include "HorseRideComponent.h"
#include "SailboatComponent.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Kismet/GameplayStatics.h"
#include "Materials/MaterialInterface.h"
#include "Sound/SoundWave.h"

static TAutoConsoleVariable<float> CVarFootstepVolume(TEXT("japan.FootstepVolume"),1.f,
    TEXT("Footstep loudness multiplier. 0 silences them."));
static TAutoConsoleVariable<int32> CVarFootstepDebug(TEXT("japan.FootstepDebug"),0,
    TEXT("Log every footfall with its surface and the material it was read from."));

static const TCHAR* FootBone(int32 Side){ return Side ? TEXT("foot_R") : TEXT("foot_L"); }

const FJapanFootstepBank* UJapanFootstepSet::Find(FName Surface) const
{
    const FJapanFootstepBank* Bank=Surfaces.Find(Surface);
    if(Bank && Bank->Steps.Num()) return Bank;
    Bank=Surfaces.Find(DefaultSurface);
    return Bank && Bank->Steps.Num() ? Bank : nullptr;
}

UJapanFootstepComponent::UJapanFootstepComponent()
{
    PrimaryComponentTick.bCanEverTick=true;
    // After the mesh has been posed for this frame, or the feet lag a frame behind the sound.
    PrimaryComponentTick.TickGroup=TG_PostPhysics;
}

void UJapanFootstepComponent::BeginPlay()
{
    Super::BeginPlay();
    Set=LoadObject<UJapanFootstepSet>(nullptr,TEXT("/Game/Japan/Audio/DA_Footsteps.DA_Footsteps"));
    if(!Set)
    {
        UE_LOG(LogTemp,Warning,TEXT("No footstep library at /Game/Japan/Audio/DA_Footsteps. Run japan/run.sh footsteps."));
        return;
    }
    int32 Total=0; for(const auto& Pair:Set->Surfaces) Total+=Pair.Value.Steps.Num();
    UE_LOG(LogTemp,Display,TEXT("Footsteps ready: %d surfaces, %d one-shots"),Set->Surfaces.Num(),Total);
    TActorIterator<AJapanWorld> It(GetWorld()); if(It) Landscape=*It;
}

FName UJapanFootstepComponent::SurfaceAt(const FHitResult& Hit) const
{
    if(!Set) return NAME_None;
    FName Surface=NAME_None;
    // The painterly pass assigns one material instance per Blender slot, so the material the
    // foot actually landed on names the surface: MI_Road, MI_Wood, MI_Stone.
    if(const UStaticMeshComponent* Mesh=Cast<UStaticMeshComponent>(Hit.Component.Get()))
    {
        int32 Section=0;
        const UMaterialInterface* Material=Hit.FaceIndex!=INDEX_NONE
            ? Mesh->GetMaterialFromCollisionFaceIndex(Hit.FaceIndex,Section)
            : Mesh->GetMaterial(0);
        if(Material)
        {
            FString Name=Material->GetName();
            Name.RemoveFromStart(TEXT("MI_")); Name.RemoveFromStart(TEXT("M_"));
            if(const FName* Found=Set->MaterialSurfaces.Find(FName(*Name))) Surface=*Found;
            if(CVarFootstepDebug.GetValueOnGameThread())
                UE_LOG(LogTemp,Display,TEXT("  footstep material %s -> %s"),*Name,
                    Surface.IsNone()?TEXT("(unmapped)"):*Surface.ToString());
        }
    }
    if(Surface.IsNone()) Surface=Set->DefaultSurface;
    // Inside the forest lake bowl the terrain material is unchanged but the floor is leaf litter.
    if(Surface==Set->DefaultSurface && !Set->CanopySurface.IsNone() && Landscape && Landscape->bForestLakeLoaded)
    {
        const FVector Relative=Hit.ImpactPoint-Landscape->ForestLakeCenter;
        const double X=Relative.X/FMath::Max(1.,Landscape->ForestLakeRadii.X);
        const double Y=Relative.Y/FMath::Max(1.,Landscape->ForestLakeRadii.Y);
        // forest_lake/layout.py clears every tree inside r=1.24, so that is where the canopy
        // starts; beyond r=2 the placement window ends and it is open hillside again.
        const double R=FMath::Sqrt(X*X+Y*Y);
        if(R>1.24 && R<2.) Surface=Set->CanopySurface;
    }
    return Surface;
}

void UJapanFootstepComponent::Play(FName Surface,const FVector& At,float Volume,float Pitch)
{
    if (const auto* Rider = Cast<ACharacter>(GetOwner()))
        if (const auto* Movement = Cast<UJapanCharacterMovement>(Rider->GetCharacterMovement()); Movement && Movement->IsReplaying()) return;
    const float Scale=CVarFootstepVolume.GetValueOnGameThread();
    if(!Set || Scale<=0.f) return;
    const FJapanFootstepBank* Bank=Set->Find(Surface);
    if(!Bank) return;
    const int32 Index=Bags.FindOrAdd(Surface).Draw(Bank->Steps.Num());
    if(!Bank->Steps.IsValidIndex(Index) || !Bank->Steps[Index]) return;
    AtelierPlaySound(this,Bank->Steps[Index],At,Volume*Scale,Pitch,Set->Attenuation);
    if(CVarFootstepDebug.GetValueOnGameThread())
        UE_LOG(LogTemp,Display,TEXT("footstep %s %s vol %.2f pitch %.2f"),*Surface.ToString(),
            *Bank->Steps[Index]->GetName(),Volume*Scale,Pitch);
}

void UJapanFootstepComponent::Plant(int32 Side,const FVector& Foot,float Speed)
{
    const AWandererCharacter* Pawn=Cast<AWandererCharacter>(GetOwner());
    if(!Pawn) return;
    FCollisionQueryParams Query(SCENE_QUERY_STAT(JapanFootstep),true,Pawn);
    Query.bReturnFaceIndex=true;                       // needed to read the material under the foot
    const double Base=Pawn->GetActorLocation().Z-Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector From(Foot.X,Foot.Y,Base+45.);
    FHitResult Hit;
    if(!GetWorld()->LineTraceSingleByChannel(Hit,From,From-FVector(0,0,95),ECC_Visibility,Query)) return;
    // Louder and brighter the faster the foot arrives; a walk should whisper next to a sprint.
    const float Drive=FMath::GetMappedRangeValueClamped(FVector2f(60.f,320.f),FVector2f(0.f,1.f),Speed);
    const float Volume=FMath::Lerp(.32f,1.f,Drive)*FMath::FRandRange(.88f,1.f);
    const float Pitch=FMath::Lerp(.96f,1.06f,Drive)*FMath::FRandRange(.94f,1.06f);
    Play(SurfaceAt(Hit),Hit.ImpactPoint,Volume,Pitch);
}

void UJapanFootstepComponent::Land(const FHitResult& Hit,float Weight)
{
    if(!Set) return;
    const FName Surface=Hit.Component.IsValid()?SurfaceAt(Hit):Set->DefaultSurface;
    Play(Surface,Hit.ImpactPoint,FMath::Clamp(Weight,.4f,1.4f),FMath::FRandRange(.82f,.9f));
    // Both feet have just arrived: hold them until the next stride actually lifts one.
    bPlanted[0]=bPlanted[1]=true; SincePlant[0]=SincePlant[1]=0.f;
}

void UJapanFootstepComponent::TickComponent(float Dt,ELevelTick TickType,FActorComponentTickFunction* Function)
{
    Super::TickComponent(Dt,TickType,Function);
    AWandererCharacter* Pawn=Cast<AWandererCharacter>(GetOwner());
    if(!Set || !Pawn || !Pawn->GetDefinition() || !Pawn->GetMesh()) return;

    const UCharacterMovementComponent* Movement=Pawn->GetCharacterMovement();
    const float Speed=Pawn->GetVelocity().Size2D();
    const bool bRiding=(Pawn->GetSailboat() && Pawn->GetSailboat()->IsEquipped()) || (Pawn->GetHorse() && Pawn->GetHorse()->IsEquipped());
    // Below a slow walk the feet shuffle in place and every crossing would be a phantom step.
    if(!Movement->IsMovingOnGround() || bRiding || Speed<40.f)
    {
        bPlanted[0]=bPlanted[1]=true;
        return;
    }

    const double Base=Pawn->GetActorLocation().Z-Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
    const FVector2D Rest=Pawn->GetDefinition()->RestAnkleHeights;
    for(int32 Side=0;Side<2;++Side)
    {
        const FVector Foot=Pawn->GetMesh()->GetBoneLocation(FootBone(Side));
        const float Was=Height[Side];
        Height[Side]=float(Foot.Z-Base);
        SincePlant[Side]+=Dt;
        // Thresholds ride on the character's own rest ankle: the rigs differ by several cm.
        const float Ankle=Side?Rest.Y:Rest.X;
        if(bPlanted[Side])
        {
            if(Height[Side]>Ankle+5.8f) bPlanted[Side]=false;
        }
        else if(Height[Side]<Ankle+2.3f && Height[Side]<=Was && SincePlant[Side]>.1f)
        {
            bPlanted[Side]=true; SincePlant[Side]=0.f;
            Plant(Side,Foot,Speed);
        }
    }
}
