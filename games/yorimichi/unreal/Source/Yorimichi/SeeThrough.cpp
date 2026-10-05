#include "SeeThrough.h"
#include "JapanWorld.h"
#include "JapanCameraArm.h"
#include "WandererCharacter.h"
#include "EngineUtils.h"
#include "Engine/World.h"
#include "Engine/StaticMesh.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/CapsuleComponent.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"
#include "Misc/PackageName.h"

static TAutoConsoleVariable<int32> CVarSeeThrough(TEXT("japan.SeeThrough"), 1,
    TEXT("Camera see-through (docs/CAMERA.md). 1: the thin things between the camera and Cairo fade out whole and come ")
    TEXT("back, everything fades right at the lens, and he fades when the camera comes very close. 0: all off."));
static TAutoConsoleVariable<int32> CVarSeeThroughHole(TEXT("japan.SeeThroughHole"), 0,
    TEXT("The first camera see-through, kept as a fallback (docs/CAMERA.md). 1: a round hole round Cairo instead of the ")
    TEXT("whole fades, his tree house room opens on the camera's side, and the camera probe passes the tree house. 0: off."));
static TAutoConsoleVariable<float> CVarSeeThroughRadius(TEXT("japan.SeeThroughRadius"), 55.f,
    TEXT("Radius of the hole round Cairo's body in hole mode (japan.SeeThroughHole 1), in cm (10 to 300)."));

namespace JapanSeeThrough
{
    const FName Tag(TEXT("JapanSeeThrough"));
    bool IsEnabled() { return CVarSeeThrough.GetValueOnGameThread() != 0; }
    bool IsHole() { return CVarSeeThroughHole.GetValueOnGameThread() != 0; }
    float Radius() { return FMath::Clamp(CVarSeeThroughRadius.GetValueOnGameThread(), 10.f, 300.f); }

    int32 FadeMode(const FString& Key, const UStaticMesh* Mesh)
    {
        // The tree house's thin pieces (rails, posts, ropes) and its dressing (lanterns, floats, noren) are merged
        // meshes. Once the build bakes each piece into UV channels 1 to 4 they fade piece by piece; until then only at
        // the lens.
        if (Key == TEXT("TH_Frame") || Key == TEXT("TH_Dressing"))
            return Mesh && Mesh->GetNumTexCoords(0) >= 5 ? FadePieces : FadeNearOnly;
        // Thin things, one instance each: the tree house's and the city's props, trees and bushes, poles, stone
        // lanterns, the torii.
        if (Key.StartsWith(TEXT("TH_P_")) || Key.StartsWith(TEXT("HD_P_")) || Key.StartsWith(TEXT("Tree")) || Key.StartsWith(TEXT("HD_NorthTree"))
            || Key == TEXT("HD_ArcadeTree") || Key.StartsWith(TEXT("HD_PlazaTree")) || Key.StartsWith(TEXT("Bush"))
            || Key == TEXT("Pole") || Key == TEXT("Pole_Lamp") || Key == TEXT("Lantern") || Key == TEXT("Torii"))
            return FadeInstances;
        // Too many and too low to fade one by one: grass, litter, the lake's plants.
        if (Key.StartsWith(TEXT("Grass")) || Key == TEXT("Litter") || Key == TEXT("Lake_Plants")) return FadeNearOnly;
        // Everything else stops the camera: the terrain (with the road's guardrail), houses, rocks, and the tree house's
        // floors, walls, roofs and trunks.
        return FadeSolid;
    }
}

namespace
{
    const TCHAR* CollectionPackage = TEXT("/Game/SeeThrough/MPC_SeeThrough");
    const TCHAR* CollectionPath = TEXT("/Game/SeeThrough/MPC_SeeThrough.MPC_SeeThrough");
    const TCHAR* HousePackage = TEXT("/Game/Japan/Treehouse/Materials/M_TreeHouse");
    const TCHAR* HousePath = TEXT("/Game/Japan/Treehouse/Materials/M_TreeHouse.M_TreeHouse");
    // The whole fades (Fade), all in cm:
    // - BodyClearance: the sight lines to Cairo widen toward him by his body's width;
    // - LensRange: a thin thing whose surface comes within this of the camera fades whole (fully at half of it);
    // - BigReach: a big thing (a tree, the torii) fades only this near the camera (none from 1 m further).
    constexpr float BodyClearance = 30.f, LensRange = 60.f, BigReach = 250.f;
    // The eye the sight lines start from is the camera, followed at EyeSpeed per second. A thing swept across the view
    // then fades over about a quarter of a second rather than in the frames it takes to cross. A jump of more than 3 m
    // (a camera cut, a travel) is taken at once.
    constexpr float EyeSpeed = 10.f, EyeJump = 300.f;
    // Hole mode: how far in front of Cairo the cut starts (cm), so nothing right at him is cut and he never looks sliced.
    constexpr float FrontMargin = 35.f;
    // Hole mode's room cutaway: the wall band round the room's outline (cm inside) and the eaves (cm outside).
    constexpr float WallBand = 60.f, Eaves = 90.f;
    // Hysteresis on the room boxes (cm): he must be 10 cm inside to enter a room and 25 cm outside to leave it.
    constexpr float EnterMargin = -10.f, LeaveMargin = 25.f;
    // The curtains' trail: where Cairo was, every TrailStep seconds, for the last TrailCount steps.
    constexpr float TrailStep = .3f;
    constexpr int32 TrailCount = 4;
    const FName TrailNames[TrailCount] = {TEXT("Trail0"), TEXT("Trail1"), TEXT("Trail2"), TEXT("Trail3")};

    const TCHAR* ModeName(bool bHole)
    {
        return bHole ? TEXT("the first version's hole and room cutaway (japan.SeeThroughHole 1)")
                     : TEXT("whole fades like Breath of the Wild (japan.SeeThroughHole 0)");
    }
}

USeeThroughComponent::USeeThroughComponent()
{
    PrimaryComponentTick.bCanEverTick = true;
    // After the character has moved this frame, so the fades follow where he is drawn.
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
        // Only a tree house built with the see-through (unreal.treehouse makes M_TreeHouse masked) may be cut in hole
        // mode and let the camera probe through.
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
    const bool bEnabled = JapanSeeThrough::IsEnabled();
    const bool bHole = JapanSeeThrough::IsHole();
    if (!bLogged && (Place || Now > 3.0))
    {
        bLogged = true; LoggedHole = bHole ? 1 : 0;
        UE_LOG(LogTemp, Display, TEXT("SEE-THROUGH active: %s, %d tree house rooms, %d tree house groups, tree house material %s, switch japan.SeeThrough %d"),
            ModeName(bHole), Place ? Place->SeeThroughRooms.Num() : 0, Place ? Place->SeeThroughGroups.Num() : 0,
            bHouseCut ? TEXT("ready") : TEXT("not patched (run unreal.treehouse)"), bEnabled ? 1 : 0);
    }
    else if (bLogged && LoggedHole != (bHole ? 1 : 0))
    {
        LoggedHole = bHole ? 1 : 0;
        UE_LOG(LogTemp, Display, TEXT("SEE-THROUGH now %s"), ModeName(bHole));
    }
    // The tree house stops the camera like any solid thing; only hole mode lets the probe pass it.
    if (Place) Place->SetSeeThroughProbe(bEnabled && bHole && bHouseCut);

    // Fixed review and trailer views frame the world, not Cairo: nothing fades there.
    const AWandererCharacter* Wanderer = Cast<AWandererCharacter>(Pawn);
    const bool bOn = bEnabled && !(Wanderer && Wanderer->IsFixedView());
    Strength = FMath::FInterpConstantTo(Strength, bOn ? 1.f : 0.f, DeltaTime, 3.f);
    HoleBlend = FMath::FInterpConstantTo(HoleBlend, bHole ? 1.f : 0.f, DeltaTime, 4.f);

    const FVector At = Pawn->GetActorLocation();
    const float Half = Pawn->GetCapsuleComponent() ? Pawn->GetCapsuleComponent()->GetScaledCapsuleHalfHeight() : 90.f;
    Values->SetVectorParameterValue(TEXT("Focus"), FLinearColor(At.X, At.Y, At.Z, Half));

    // The camera the view was drawn from last (the camera manager updates after this tick), smoothed.
    bool bCamera = false;
    FVector Camera = At;
    if (const APlayerController* Player = Cast<APlayerController>(Pawn->GetController()))
        if (Player->PlayerCameraManager)
        {
            Camera = Player->PlayerCameraManager->GetCameraLocation();
            bCamera = true;
        }
    if (!bEyeSet || FVector::DistSquared(Camera, Eye) > FMath::Square(EyeJump)) Eye = Camera;
    else Eye = FMath::VInterpTo(Eye, Camera, DeltaTime, EyeSpeed);
    bEyeSet = bCamera;
    Values->SetVectorParameterValue(TEXT("Eye"), FLinearColor(Eye.X, Eye.Y, Eye.Z, 0.f));
    // Cut: the hole's radius and front margin, the lens fade's strength, the hole's strength (0 unless in hole mode).
    Values->SetVectorParameterValue(TEXT("Cut"), FLinearColor(JapanSeeThrough::Radius(), FrontMargin, Strength, Strength * HoleBlend));
    // Fade: the whole fades' strength (they give way to the hole in hole mode), the body clearance, the lens range and
    // the big things' reach.
    const float Whole = bCamera ? Strength * (1.f - HoleBlend) : 0.f;
    Values->SetVectorParameterValue(TEXT("Fade"), FLinearColor(Whole, BodyClearance, LensRange, BigReach));

    // Hole mode: the tree house room he is in, if any, whose near walls and roof open while the camera is outside it.
    // A change of room first closes the old one, then opens the new one, so the walls never jump from one room to the
    // next. Out of hole mode the room closes and stays closed.
    int32 Inside = INDEX_NONE;
    if (Place && bHouseCut && bHole)
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
