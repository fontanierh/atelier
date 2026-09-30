#include "SeeThrough.h"
#include "JapanWorld.h"
#include "JapanCameraArm.h"
#include "WandererCharacter.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "Components/CapsuleComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "Misc/PackageName.h"

static TAutoConsoleVariable<int32> CVarSeeThrough(TEXT("japan.SeeThrough"), 1,
    TEXT("Camera see-through (docs/CAMERA.md). 1: what stands between the camera and Cairo dithers away, his tree house ")
    TEXT("room opens on the camera's side, he fades when the camera comes very close, and the camera probe passes the ")
    TEXT("tree house. 0: all off, and the tree house stops the camera probe again."));
static TAutoConsoleVariable<float> CVarSeeThroughRadius(TEXT("japan.SeeThroughRadius"), 55.f,
    TEXT("Radius of the see-through round Cairo's body, in cm (10 to 300)."));

namespace JapanSeeThrough
{
    const FName Tag(TEXT("JapanSeeThrough"));
    bool IsEnabled() { return CVarSeeThrough.GetValueOnGameThread() != 0; }
    float Radius() { return FMath::Clamp(CVarSeeThroughRadius.GetValueOnGameThread(), 10.f, 300.f); }
}

namespace
{
    const TCHAR* CollectionPackage = TEXT("/Game/SeeThrough/MPC_SeeThrough");
    const TCHAR* CollectionPath = TEXT("/Game/SeeThrough/MPC_SeeThrough.MPC_SeeThrough");
    const TCHAR* HousePackage = TEXT("/Game/Japan/Treehouse/Materials/M_TreeHouse");
    const TCHAR* HousePath = TEXT("/Game/Japan/Treehouse/Materials/M_TreeHouse.M_TreeHouse");
    // How far in front of Cairo the cut starts (cm): nothing right at him is cut, so he never looks sliced.
    constexpr float FrontMargin = 35.f;
    // Room cutaway: the wall band round the room's outline (cm inside) and the eaves (cm outside).
    constexpr float WallBand = 60.f, Eaves = 90.f;
    // Hysteresis on the room boxes (cm): he must be 10 cm inside to enter a room and 25 cm outside to leave it.
    constexpr float EnterMargin = -10.f, LeaveMargin = 25.f;
    // The curtains' trail: where Cairo was, every TrailStep seconds, for the last TrailCount steps.
    constexpr float TrailStep = .3f;
    constexpr int32 TrailCount = 4;
    const FName TrailNames[TrailCount] = {TEXT("Trail0"), TEXT("Trail1"), TEXT("Trail2"), TEXT("Trail3")};
}

USeeThroughComponent::USeeThroughComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    // After the character has moved this frame, so the cut is centred where he is drawn.
    PrimaryComponentTick.TickGroup = TG_PostPhysics;
}

void USeeThroughComponent::TickComponent(float DeltaTime, ELevelTick TickType, FActorComponentTickFunction* ThisTickFunction)
{
    Super::TickComponent(DeltaTime, TickType, ThisTickFunction);
    const ACharacter* Pawn = Cast<ACharacter>(GetOwner());
    if (!Pawn || !Pawn->IsPlayerControlled()) return;
    UWorld* World = GetWorld();
    if (!bLookedUp)
    {
        bLookedUp = true;
        if (FPackageName::DoesPackageExist(FString(CollectionPackage)))
            Collection = LoadObject<UMaterialParameterCollection>(nullptr, CollectionPath);
        if (!Collection)
            UE_LOG(LogTemp, Warning, TEXT("SEE-THROUGH off: %s is missing (atelier build yorimichi unreal.see_through)"), CollectionPath);
        const UMaterialInterface* Tree = FPackageName::DoesPackageExist(FString(HousePackage)) ? LoadObject<UMaterialInterface>(nullptr, HousePath) : nullptr;
        // Only a tree house built with the cut may let the camera through it (unreal.treehouse makes M_TreeHouse masked).
        bHouseCut = Collection && Tree && Tree->GetBlendMode() == BLEND_Masked;
    }
    if (!Collection) return;
    UMaterialParameterCollectionInstance* Values = World->GetParameterCollectionInstance(Collection);
    if (!Values) return;
    if (!House.IsValid())
        for (TActorIterator<AJapanWorld> It(World); It; ++It)
            if (It->bLoaded)
            {
                House = *It;
                if (UJapanCameraArm* Arm = Pawn->FindComponentByClass<UJapanCameraArm>()) Arm->SetSeeThroughHouse(*It);
                break;
            }
    AJapanWorld* Place = House.Get();
    const double Now = World->GetTimeSeconds();
    if (!bLogged && (Place || Now > 3.0))
    {
        bLogged = true;
        UE_LOG(LogTemp, Display, TEXT("SEE-THROUGH active: radius %.0f cm, %d tree house rooms, %d tree house groups, tree house cut %s, switch japan.SeeThrough %d"),
            JapanSeeThrough::Radius(), Place ? Place->SeeThroughRooms.Num() : 0, Place ? Place->SeeThroughGroups.Num() : 0,
            bHouseCut ? TEXT("yes") : TEXT("no (run unreal.treehouse)"), JapanSeeThrough::IsEnabled() ? 1 : 0);
    }
    const bool bEnabled = JapanSeeThrough::IsEnabled();
    if (Place) Place->SetSeeThroughProbe(bEnabled && bHouseCut);

    // Fixed review and trailer views frame the world, not Cairo: no cut there.
    const AWandererCharacter* Wanderer = Cast<AWandererCharacter>(Pawn);
    const bool bOn = bEnabled && !(Wanderer && Wanderer->IsFixedView());
    Strength = FMath::FInterpConstantTo(Strength, bOn ? 1.f : 0.f, DeltaTime, 3.f);

    const FVector At = Pawn->GetActorLocation();
    const float Half = Pawn->GetCapsuleComponent() ? Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
    Values->SetVectorParameterValue(TEXT("Focus"), FLinearColor(At.X, At.Y, At.Z, Half));
    Values->SetVectorParameterValue(TEXT("Cut"), FLinearColor(JapanSeeThrough::Radius(), FrontMargin, Strength, Strength));

    // The tree house room he is in, if any: its near walls and roof open while the camera is outside it. A change of
    // room first closes the old one, then opens the new one, so the walls never jump from one room to the next.
    int32 Inside = INDEX_NONE;
    if (Place && bHouseCut)
        Inside = Place->IsInSeeThroughRoom(Room, At, LeaveMargin) ? Room : Place->FindSeeThroughRoom(At, EnterMargin);
    if (Inside != Room)
    {
        RoomBlend = FMath::FInterpConstantTo(RoomBlend, 0.f, DeltaTime, 4.f);
        if (RoomBlend <= 0.f) Room = Inside;
    }
    else RoomBlend = FMath::FInterpConstantTo(RoomBlend, Room != INDEX_NONE ? 1.f : 0.f, DeltaTime, 4.f);
    if (Place && Place->SeeThroughRooms.IsValidIndex(Room))
    {
        const FSeeThroughRoom& R = Place->SeeThroughRooms[Room];
        Values->SetVectorParameterValue(TEXT("Room"), FLinearColor(R.Center.X, R.Center.Y, R.Center.Z, R.Yaw));
        Values->SetVectorParameterValue(TEXT("RoomSize"), FLinearColor(R.Extent.X, R.Extent.Y, R.Extent.Z, RoomBlend));
        Values->SetVectorParameterValue(TEXT("RoomShape"), FLinearColor(R.bRound ? 1.f : 0.f, WallBand, Eaves, 0.f));
    }
    else Values->SetVectorParameterValue(TEXT("RoomSize"), FLinearColor(100.f, 100.f, 100.f, 0.f));

    // The trail the curtains swing from: his position every TrailStep seconds. A jump of more than 2 m in a frame
    // (a map travel, a respawn) starts it afresh, so no curtain swings along the line of a teleport.
    if (TrailFilled > 0 && FVector::DistSquared(At, LastAt) > FMath::Square(200.f)) TrailFilled = 0;
    LastAt = At;
    if (TrailFilled == 0 || Now - TrailTime[0] >= TrailStep)
    {
        for (int32 K = TrailCount - 1; K > 0; --K) { Trail[K] = Trail[K - 1]; TrailTime[K] = TrailTime[K - 1]; }
        Trail[0] = At; TrailTime[0] = Now; TrailFilled = FMath::Min(TrailFilled + 1, TrailCount);
    }
    for (int32 K = 0; K < TrailCount; ++K)
    {
        // Missing samples repeat the oldest one, long ago: a segment of no length that moves nothing.
        const int32 S = FMath::Min(K, TrailFilled - 1);
        const float Age = K < TrailFilled ? float(Now - TrailTime[S]) : 10.f;
        Values->SetVectorParameterValue(TrailNames[K], FLinearColor(Trail[S].X, Trail[S].Y, Trail[S].Z, Age));
    }
}
