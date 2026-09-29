#include "SkateboardComponent.h"
#include "JapanCharacterMovement.h"
#include "WandererCharacter.h"
#include "WandererDefinition.h"
#include "Components/CapsuleComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "Animation/AnimSequence.h"
#include "Engine/World.h"
#include "SkateOllieMotion.inl"

USkateboardComponent::USkateboardComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    PrimaryComponentTick.TickGroup = TG_PrePhysics;
}

void USkateboardComponent::Initialize(AWandererCharacter* Character)
{
    Rider = Character;
    if (!Rider->GetDefinition() || !Rider->GetDefinition()->SupportsSkateboarding)
    { SetComponentTickEnabled(false); return; }
    OriginalStepHeight = Rider->GetCharacterMovement()->MaxStepHeight;
    OriginalMeshLocation = Rider->GetMesh()->GetRelativeLocation();
    OriginalMeshRotation = Rider->GetMesh()->GetRelativeRotation().Quaternion();
    AddTickPrerequisiteComponent(Rider->GetCharacterMovement());
    AddTickPrerequisiteActor(Rider);
    Rider->GetMesh()->AddTickPrerequisiteComponent(this);
    BoardRoot = NewObject<USceneComponent>(Rider,TEXT("SkateboardRoot"));
    BoardRoot->SetupAttachment(Rider->GetRootComponent()); BoardRoot->RegisterComponent();
    auto Part = [&](const TCHAR* Name, const TCHAR* Asset, FVector Position)
    {
        auto* Mesh = NewObject<UStaticMeshComponent>(Rider,Name);
        Mesh->SetupAttachment(BoardRoot); Mesh->SetRelativeLocation(Position);
        Mesh->SetCollisionEnabled(ECollisionEnabled::NoCollision);
        Mesh->SetGenerateOverlapEvents(false); Mesh->SetCanEverAffectNavigation(false);
        Mesh->SetStaticMesh(LoadObject<UStaticMesh>(nullptr,Asset));
        Mesh->SetRenderCustomDepth(true); Mesh->SetCustomDepthStencilValue(2);
        Mesh->RegisterComponent(); return Mesh;
    };
    Deck = Part(TEXT("SkateDeck"),TEXT("/Game/Skateboard/SM_Deck.SM_Deck"),FVector::ZeroVector);
    for (int32 End = 0; End < 2; ++End)
    {
        const float X = End == 0 ? 26.f : -26.f;
        Trucks.Add(Part(*FString::Printf(TEXT("SkateTruck%d"),End),TEXT("/Game/Skateboard/SM_Truck.SM_Truck"),FVector(X,0,3.25f)));
        for (int32 Side = 0; Side < 2; ++Side)
        {
            auto* Wheel = Part(*FString::Printf(TEXT("SkateWheel%d%d"),End,Side),TEXT("/Game/Skateboard/SM_Wheel.SM_Wheel"),FVector::ZeroVector);
            Wheel->AttachToComponent(Trucks[End],FAttachmentTransformRules::KeepRelativeTransform);
            Wheel->SetRelativeLocation(FVector(0,Side == 0 ? -13.2f : 13.2f,0));
            Wheels.Add(Wheel);
        }
    }
    BoardRoot->SetVisibility(false,true);
    bAssetsReady = Deck->GetStaticMesh() && Trucks[0]->GetStaticMesh() && Wheels[0]->GetStaticMesh() && Rider->GetDefinition();
    if (bAssetsReady)
        for (const TCHAR* Name : {TEXT("SkateMount"),TEXT("SkateRide"),TEXT("SkatePush"),TEXT("SkatePushCycle"),TEXT("SkateBrake"),TEXT("SkateDismount"),TEXT("SkateOllieStart"),TEXT("SkateOllieAir"),TEXT("SkateOllieLand")})
            for (const FString Suffix : {FString(),FString(TEXT("Goofy"))})
            {
                const FName Key(FString(Name)+Suffix);
                bAssetsReady &= Rider->GetDefinition()->SkateActions.Contains(Key) && Rider->GetDefinition()->SkateActions[Key] != nullptr;
            }
    if (!bAssetsReady) UE_LOG(LogTemp,Warning,TEXT("Skateboard unavailable: build and import skateboard content for this character."));
}

bool USkateboardComponent::Toggle()
{
    bRemountForStance = false; // An explicit equip/stow press cancels automatic remounting.
    if (!bAssetsReady || !Rider) return false;
    if (IsEquipped())
    {
        if (State != ESkateState::Mounting && State != ESkateState::Dismounting) bStowRequested = true;
        return true;
    }
    if (!Rider->GetCharacterMovement()->IsMovingOnGround() || Rider->bIsCrouched) return false;
    Rider->GetCharacterMovement()->StopMovementImmediately();
    LastPosition = Rider->GetActorLocation(); GroundRotation = FQuat::Identity;
    Input = FVector2D::ZeroVector; Steering = 0.f; Bank = 0.f; bStowRequested = false;
    Rider->GetCharacterMovement()->MaxStepHeight = 8.f;
    SetState(ESkateState::Mounting); return true;
}

void USkateboardComponent::SetPreferredGoofy(bool bNewGoofy)
{
    if (bPreferredGoofy == bNewGoofy) return;
    bPreferredGoofy = bNewGoofy;
    if (!IsEquipped()) bGoofy = bPreferredGoofy;
    else
    {
        // Finish landing, brake, and step off before exchanging foot roles.
        bStowRequested = true;
        bRemountForStance = true;
    }
}

void USkateboardComponent::SetInput(FVector2D Intent, bool bMenuOpen)
{
    Input = Intent.GetClampedToMaxSize(1.f); bMenu = bMenuOpen;
    if (bMenu) Input = FVector2D::ZeroVector;
}

bool USkateboardComponent::BeginMega()
{
    if(!bAssetsReady||!Rider||!Rider->GetDefinition())return false;
    for(const TCHAR* Name:{TEXT("MegaClimb"),TEXT("MegaRide"),TEXT("MegaAir"),TEXT("MegaLand")})
    {
        const FName Key(FString(Name)+(bGoofy?TEXT("Goofy"):TEXT("")));
        if(!Rider->GetDefinition()->SkateActions.Contains(Key)||!Rider->GetDefinition()->SkateActions[Key])return false;
    }
    bStowRequested=false; LastMegaClip=NAME_None; SetState(ESkateState::Riding);
    Rider->GetCharacterMovement()->MaxStepHeight=8.f;
    return true;
}

void USkateboardComponent::RequestOllie()
{
    if (!Rider) return;
    if(auto* M=Cast<UJapanCharacterMovement>(Rider->GetCharacterMovement()); M&&M->IsMega()){M->MegaJump();return;}
    if (!Rider || !IsEquipped() || !CanRoll() || IsOllie() || IsStopping() ||
        !Rider->GetCharacterMovement()->IsMovingOnGround()) return;
    // One press, one pop. The first 120 ms recover a pushing foot before crouch.
    SetState(ESkateState::OllieStart);
}

void USkateboardComponent::Landed()
{
    if (IsEquipped()) SetState(ESkateState::OllieLand);
}

FTransform USkateboardComponent::GetBoardTransform() const
{
    return BoardRoot ? BoardRoot->GetComponentTransform() : FTransform::Identity;
}

int32 USkateboardComponent::GetBoardStencil() const
{
    return Deck ? Deck->CustomDepthStencilValue : 0;
}

void USkateboardComponent::StowImmediately()
{
    Input = FVector2D::ZeroVector;
    Steering = Bank = 0.f;
    bRemountForStance = false;
    LastMegaClip = NAME_None;
    if (IsEquipped()) SetState(ESkateState::Stowed);
}

void USkateboardComponent::SetState(ESkateState Next)
{
    State = Next; bPushCycle = false; PoseTime = 0.f; StrokeTravel = 0.f; ContactSeconds = 0.f; bContact = false; ++Serial;
    UE_LOG(LogTemp,Verbose,TEXT("Skateboard: %s"),*GetClipName().ToString());
    if (Next == ESkateState::Stowed)
    {
        BoardRoot->SetVisibility(false,true);
        Rider->GetMesh()->SetRelativeLocationAndRotation(OriginalMeshLocation,OriginalMeshRotation);
        Rider->GetCharacterMovement()->MaxStepHeight = OriginalStepHeight;
        bStowRequested = false;
        bGoofy = bPreferredGoofy;
    }
}

FName USkateboardComponent::GetClipName() const
{
    if(Rider) if(auto* M=Cast<UJapanCharacterMovement>(Rider->GetCharacterMovement());M&&M->IsMega()) return M->MegaClip();
    switch (State)
    {
        case ESkateState::Mounting: return TEXT("SkateMount");
        case ESkateState::Riding: return TEXT("SkateRide");
        case ESkateState::Pushing: return bPushCycle ? TEXT("SkatePushCycle") : TEXT("SkatePush");
        case ESkateState::Braking: return TEXT("SkateBrake");
        case ESkateState::Dismounting: return TEXT("SkateDismount");
        case ESkateState::OllieStart: return TEXT("SkateOllieStart");
        case ESkateState::OllieAir: return TEXT("SkateOllieAir");
        case ESkateState::OllieLand: return TEXT("SkateOllieLand");
        default: return NAME_None;
    }
}
UAnimSequence* USkateboardComponent::GetSequence() const
{
    const FName Key = bGoofy ? FName(GetClipName().ToString()+TEXT("Goofy")) : GetClipName();
    if (Rider && Rider->GetDefinition())
        if (const auto* Clip = Rider->GetDefinition()->SkateActions.Find(Key)) return *Clip;
    return nullptr;
}
FString USkateboardComponent::GetStatus() const
{
    if(Rider) if(auto* M=Cast<UJapanCharacterMovement>(Rider->GetCharacterMovement());M&&M->IsMega()) return M->MegaStatus();
    if (bRemountForStance) return TEXT("Changing skate stance");
    if (bStowRequested) return TEXT("Stopping to step off");
    switch (State)
    {
        case ESkateState::Mounting: return TEXT("Stepping on");
        case ESkateState::Pushing: return TEXT("Pushing");
        case ESkateState::Braking: return TEXT("Foot brake");
        case ESkateState::Dismounting: return TEXT("Stepping off");
        case ESkateState::OllieStart: return TEXT("Ollie");
        case ESkateState::OllieAir: return TEXT("Airborne");
        case ESkateState::OllieLand: return TEXT("Landing");
        default: return TEXT("Coasting");
    }
}

void USkateboardComponent::PlantFoot()
{
    // The previous pose is within one sample of plant. Lock its horizontal
    // position in the world, then solve the leg against the actual ground.
    ContactLocation = Rider->GetMesh()->GetSocketLocation(GetPushFootBone());
    FHitResult Hit;
    FCollisionQueryParams Params(SCENE_QUERY_STAT(SkateFoot),false,Rider);
    const auto* Movement = Rider->GetCharacterMovement();
    const float GroundZ = Rider->GetActorLocation().Z-Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()-Movement->CurrentFloor.FloorDist;
    const FVector Start(ContactLocation.X,ContactLocation.Y,GroundZ+20.f);
    const FVector End(ContactLocation.X,ContactLocation.Y,GroundZ-30.f);
    if (GetWorld()->LineTraceSingleByChannel(Hit,Start,End,ECC_Visibility,Params) && Hit.ImpactNormal.Z > .75f && FMath::Abs(Hit.ImpactPoint.Z-GroundZ) < 15.f)
    {
        // Character definitions record sole-to-ankle height in centimetres.
        ContactLocation.Z = Hit.ImpactPoint.Z+Rider->GetDefinition()->SkateAnkleHeight;
        bContact = true;
    }
}

void USkateboardComponent::TickComponent(float Dt,ELevelTick Type,FActorComponentTickFunction* Tick)
{
    Super::TickComponent(Dt,Type,Tick);
    if (!Rider) return;
    if (!IsEquipped())
    {
        // Settings keep the rider stopped; remount only once play resumes.
        if (bRemountForStance && !bMenu && Rider->GetCharacterMovement()->IsMovingOnGround()) Toggle();
        return;
    }
    auto* Movement = Rider->GetCharacterMovement();
    if(auto* M=Cast<UJapanCharacterMovement>(Movement);M&&M->IsMega())
    {
        if(LastMegaClip!=M->MegaClip()){LastMegaClip=M->MegaClip();++Serial;}
        PoseTime=M->MegaPoseTime();bContact=false;
        const float Travel=FVector::Distance(Rider->GetActorLocation(),LastPosition);LastPosition=Rider->GetActorLocation();
        UpdateVisuals(Dt,Travel);return;
    }
    LastMegaClip=NAME_None;
    const FVector Position = Rider->GetActorLocation();
    const float Distance = FVector::Dist2D(Position,LastPosition); LastPosition = Position;
    const float Speed = Movement->Velocity.Size2D();
    const bool bGround = Movement->IsMovingOnGround();
    Steering = FMath::FInterpTo(Steering,CanRoll() && !bMenu && !IsOllie() ? Input.X : 0.f,Dt,7.f);
    if (!bGround)
    {
        if (State != ESkateState::OllieAir)
        {
            // Walking off an edge has no pop or extra upward impulse.
            SetState(ESkateState::OllieAir); PoseTime = .49f; AirFloorGap = 0.f;
        }
        PoseTime = FMath::Min(SkateOllieMotion::AirDuration,PoseTime+Dt);
    }
    else if (State == ESkateState::OllieStart)
    {
        if (bMenu || bStowRequested)
            SetState(ESkateState::Riding);
        else
        {
            PoseTime = FMath::Min(SkateOllieMotion::StartDuration,PoseTime+Dt);
            if (PoseTime >= SkateOllieMotion::StartDuration)
            {
                AirFloorGap = FMath::Clamp(Movement->CurrentFloor.FloorDist,0.f,8.f);
                // Use swept CharacterMovement gravity/collision, preserve XY.
                Rider->LaunchCharacter(FVector(0,0,420.f),false,true);
                SetState(ESkateState::OllieAir);
            }
        }
    }
    else if (State == ESkateState::OllieAir)
    {
        // LaunchCharacter's pending impulse is applied on the next movement tick.
    }
    else if (State == ESkateState::OllieLand)
    {
        PoseTime += Dt;
        if (PoseTime >= SkateOllieMotion::LandDuration) SetState(ESkateState::Riding);
    }
    else if (State == ESkateState::Pushing)
    {
        const bool bContinuePush = Input.Y > .15f && !IsStopping();
        if (bPushCycle && !bContinuePush && !IsPushingGround())
        {
            // Release during the airborne recovery: blend directly to the
            // raised-foot return, without planting for another unwanted stroke.
            bPushCycle = false; PoseTime = .88f; ++Serial;
        }
        if (IsPushingGround())
        {
            StrokeTravel += Distance; ContactSeconds += Dt;
            PoseTime = PlantTime+(ReleaseTime-PlantTime)*FMath::Clamp(StrokeTravel/StrokeLength,0.f,1.f);
            // A wall must not leave the foot indefinitely planted behind us.
            if (ContactSeconds > .55f) SetState(ESkateState::Riding);
            if (PoseTime >= ReleaseTime)
            {
                bContact = false;
                if (State == ESkateState::Pushing && bPushCycle != bContinuePush)
                {
                    // Both clips have the same body and foot targets at release.
                    bPushCycle = bContinuePush; ++Serial;
                }
            }
        }
        else
        {
            const float Previous = PoseTime; PoseTime += Dt;
            if (Previous < PlantTime && PoseTime >= PlantTime)
            { PoseTime = PlantTime; StrokeTravel = 0.f; ContactSeconds = 0.f; PlantFoot(); }
        }
        if (PoseTime >= 1.2f)
        {
            if (bPushCycle) PoseTime = FMath::Fmod(PoseTime,1.2f);
            else SetState(ESkateState::Riding);
        }
    }
    else if (State == ESkateState::Mounting || State == ESkateState::Dismounting)
    {
        PoseTime += Dt;
        if (PoseTime >= 1.2f) SetState(State == ESkateState::Mounting ? ESkateState::Riding : ESkateState::Stowed);
    }
    else
    {
        if (bStowRequested && Speed < 8.f) SetState(ESkateState::Dismounting);
        else if (IsStopping())
        {
            if (State != ESkateState::Braking) SetState(ESkateState::Braking);
            PoseTime = FMath::Min(.5f,PoseTime+Dt);
        }
        else
        {
            if (State == ESkateState::Braking) SetState(ESkateState::Riding);
            PoseTime = FMath::Fmod(PoseTime+Dt,2.f);
            if (Input.Y > .15f) SetState(ESkateState::Pushing);
        }
    }
    if (IsEquipped()) UpdateVisuals(Dt,Distance);
}

void USkateboardComponent::UpdateVisuals(float Dt,float Distance)
{
    auto* Movement = Rider->GetCharacterMovement();
    if(auto* M=Cast<UJapanCharacterMovement>(Movement);M&&M->IsMega())
    {
        const float Half=Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight();
        Rider->GetMesh()->SetRelativeLocationAndRotation(OriginalMeshLocation,OriginalMeshRotation);
        if(M->IsMegaClimbing())
            BoardRoot->SetRelativeLocationAndRotation(FVector(-24,0,-Half+70),FRotator(90,0,0));
        else BoardRoot->SetRelativeLocationAndRotation(FVector(0,0,-Half),FRotator::ZeroRotator);
        BoardRoot->SetVisibility(true,true);
        WheelAngle=FMath::Fmod(WheelAngle+FMath::RadiansToDegrees(Distance/3.25f),360.f);
        for(auto& W:Wheels)W->SetRelativeRotation(FRotator(-WheelAngle,0,0));
        return;
    }
    const bool bGround = Movement->IsMovingOnGround();
    const float FloorGap = bGround ? FMath::Clamp(Movement->CurrentFloor.FloorDist,0.f,8.f) : AirFloorGap;
    const FVector Normal = bGround ? Movement->CurrentFloor.HitResult.ImpactNormal : FVector::UpVector;
    FVector LocalNormal = Rider->GetActorQuat().UnrotateVector(Normal);
    const FQuat Target = FRotationMatrix::MakeFromXZ(FVector::VectorPlaneProject(FVector::ForwardVector,LocalNormal),LocalNormal).ToQuat();
    GroundRotation = FQuat::Slerp(GroundRotation,Target,1.f-FMath::Exp(-14.f*Dt)).GetNormalized();
    Bank = FMath::FInterpTo(Bank,IsOllie() ? 0.f : Steering*4.f*FMath::Clamp(Movement->Velocity.Size2D()/350.f,0.f,1.f),Dt,8.f);
    const FQuat Tilt = GroundRotation*FRotator(0,0,Bank).Quaternion();
    float Pitch = 0.f, Height = 0.f;
    using namespace SkateOllieMotion;
    if (State == ESkateState::OllieStart) { Pitch = Sample(StartPitch,PoseTime); Height = Sample(StartHeight,PoseTime); }
    if (State == ESkateState::OllieAir) { Pitch = Sample(AirPitch,PoseTime); Height = Sample(AirHeight,PoseTime); }
    BoardRoot->SetRelativeLocationAndRotation(FVector(0,0,-Rider->GetCapsuleComponent()->GetScaledCapsuleHalfHeight()-FloorGap)+Tilt.RotateVector(FVector(0,0,Height)),Tilt*FRotator(Pitch,0,0).Quaternion());
    Deck->SetRelativeRotation(FRotator::ZeroRotator);
    Rider->GetMesh()->SetRelativeLocationAndRotation(OriginalMeshLocation-FVector(0,0,FloorGap),Tilt*OriginalMeshRotation);
    WheelAngle = FMath::Fmod(WheelAngle+FMath::RadiansToDegrees(Distance/3.25f),360.f);
    for (int32 I = 0; I < Trucks.Num(); ++I) Trucks[I]->SetRelativeRotation(FRotator(0,Steering*(I == 0 ? 7.f : -7.f),0));
    for (int32 I = 0; I < Wheels.Num(); ++I) Wheels[I]->SetRelativeRotation(FRotator(-WheelAngle,0,0));
    const bool bVisible = (State != ESkateState::Mounting || PoseTime > .23f) && (State != ESkateState::Dismounting || PoseTime < .97f);
    BoardRoot->SetVisibility(bVisible,true);
}
