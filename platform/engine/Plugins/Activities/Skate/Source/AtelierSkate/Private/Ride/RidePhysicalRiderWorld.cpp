// URidePhysicalRider: the loose board and the world around the body (RidePhysicalRider.cpp).
#include "RidePhysicalRider.h"
#include "RidePhysicalRiderDetail.h"
#include "SkateRider.h"
#include "RideClipPlayer.h"
#include "PhysicsControlComponent.h"
#include "PhysicsControlAsset.h"
#include "PhysicsControlRecord.h"
#include "Components/BoxComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/Engine.h"
#include "Engine/OverlapResult.h"
#include "Engine/SkeletalMesh.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "HAL/IConsoleManager.h"
#include "Algo/Find.h"
#include "Chaos/ChaosEngineInterface.h"
#include "Physics/Experimental/PhysInterface_Chaos.h"
#include "PBDRigidsSolver.h"
#include "Chaos/Collision/CollisionConstraintFlags.h"
#include "PhysicsProxy/SingleParticlePhysicsProxy.h"
#include "PhysicalMaterials/PhysicalMaterial.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/PhysicsConstraintTemplate.h"
#include "PhysicsEngine/SkeletalBodySetup.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "Rendering/SkeletalMeshRenderData.h"

using namespace RidePhysicalRiderDetail;

// ---------------------------------------------------------------------------------------------------------------
// The loose board.

FTransform URidePhysicalRider::GetLooseBoardDeck() const
{
    if (!LooseBoard) return FTransform::Identity;
    const FTransform Body = LooseBoard->GetComponentTransform();
    return FTransform(Body.GetRotation(), Body.GetLocation() + Body.GetRotation().GetUpVector() * LooseBoardDrop * BoardScale, FVector(BoardScale));
}

UBoxComponent* URidePhysicalRider::TakeLooseBoard()
{
    UBoxComponent* Board = LooseBoard;
    LooseBoard = nullptr;
    TakenBoard = Board;
    TakenLast = LooseLast;
    return Board;
}

void URidePhysicalRider::GuardBoards()
{
    GuardBoard(LooseBoard, LooseLast);
    GuardBoard(TakenBoard.Get(), TakenLast);
}

void URidePhysicalRider::GuardBoard(UPrimitiveComponent* Board, FTransform& Last)
{
    // The board's own world and owner: a handed-over board outlives the body (End clears Rider).
    UWorld* World = Board ? Board->GetWorld() : nullptr;
    if (!World) return;
    const FTransform Now(Board->GetComponentQuat(), Board->GetComponentLocation());
    // Not simulating (held, lying still), barely moved or turned, or placed (a first frame, a teleport): nothing to sweep.
    const double Moved = FVector::DistSquared(Last.GetLocation(), Now.GetLocation());
    const bool bTurned = Last.GetRotation().AngularDistance(Now.GetRotation()) > 1e-3;
    if (!Board->IsSimulatingPhysics() || (Moved < .01 && !bTurned) || Moved > FMath::Square(BoardGuardReach)) { Last = Now; return; }
    // A little inside the box, so the ground physics already holds it on is not a hit.
    const UBoxComponent* Box = Cast<UBoxComponent>(Board);
    const FVector Extent = ((Box ? Box->GetScaledBoxExtent() : FVector(Board->Bounds.SphereRadius)) - FVector(BoardGuardInset)).ComponentMax(FVector(.5f));
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardGuard), false, Board->GetOwner());
    Params.AddIgnoredComponent(Board);
    const FTransform From(Last.GetRotation(), Last.GetLocation());
    for (int32 Try = 0; Try < 3; ++Try)
    {
        FHitResult Hit; FTransform Reached;
        if (!FRideClipPlayer::SweepBox(*World, From, Now, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, Hit, &Reached)) break;
        // What moves is physics' own to push.
        UPrimitiveComponent* Other = Hit.GetComponent();
        if (Other && Other->IsSimulatingPhysics()) { Params.AddIgnoredComponent(Other); continue; }
        FTransform Back;
        if (!Hit.bStartPenetrating) Back = FTransform(Reached.GetRotation(), Reached.GetLocation() + Hit.Normal * .2f);
        else if (Hit.Time > 0.f)
            Back = FTransform(FQuat::Slerp(From.GetRotation(), Now.GetRotation(), Hit.Time).GetNormalized(), FMath::Lerp(From.GetLocation(), Now.GetLocation(), double(Hit.Time)));
        else
        {
            // It was already inside something where it was last (it started there): physics taking it out to a free
            // pose, by a way its centre can go, is left alone; otherwise it stays.
            FHitResult There, Between;
            if (!FRideClipPlayer::SweepBox(*World, Now, Now, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, There) &&
                !World->LineTraceSingleByChannel(Between, From.GetLocation(), Now.GetLocation(), ECC_Pawn, Params))
                break;
            Back = From;
        }
        // Physics passed or turned into this face (it does not see it, or stepped over it): back to the last pose found
        // free, the velocity into the face turned back as a bounce; a turn into it stops.
        Board->SetWorldLocationAndRotation(Back.GetLocation(), Back.GetRotation(), false, nullptr, ETeleportType::TeleportPhysics);
        const FVector Normal = Hit.Normal;
        const FVector Velocity = Board->GetPhysicsLinearVelocity();
        const float Into = float(FVector::DotProduct(Velocity, Normal));
        if (Normal.IsNearlyZero()) Board->SetPhysicsLinearVelocity(FVector::ZeroVector);
        else if (Into < 0.f) Board->SetPhysicsLinearVelocity(Velocity - Normal * Into * (1.f + BoardGuardBounce));
        if (Hit.bStartPenetrating) Board->SetPhysicsAngularVelocityInRadians(FVector::ZeroVector);
        Last = Back;
        return;
    }
    Last = Now;
}

void URidePhysicalRider::DropLooseBoard()
{
    if (!LooseBoard) return;
    LooseBoard->SetSimulatePhysics(false);
    LooseBoard->DestroyComponent();
    LooseBoard = nullptr;
}

void URidePhysicalRider::PlaceLooseBoard(const FTransform& Deck)
{
    if (!LooseBoard) return;
    if (LooseBoard->IsSimulatingPhysics()) LooseBoard->SetSimulatePhysics(false);
    const FQuat Rotation = Deck.GetRotation();
    LooseBoard->SetWorldLocationAndRotation(Deck.GetLocation() - Rotation.GetUpVector() * LooseBoardDrop * BoardScale, Rotation,
        false, nullptr, ETeleportType::TeleportPhysics);
    LooseLast = LooseBoard->GetComponentTransform();
}

void URidePhysicalRider::ReleaseLooseBoard(const FVector& Velocity, const FVector& Spin)
{
    if (!LooseBoard || LooseBoard->IsSimulatingPhysics()) return;
    // The box's centre is below the deck it was placed by: it moves with the deck's velocity and the turn about it.
    const FVector Arm = LooseBoard->GetComponentLocation() - GetLooseBoardDeck().GetLocation();
    // The simulation's board (a deck, trucks and wheels) fits where the box may not: lifted out of what it would start inside,
    // which the guard (GuardBoard) would otherwise hold it in.
    if (UWorld* World = LooseBoard->GetWorld())
    {
        const FVector Extent = (LooseBoard->GetScaledBoxExtent() - FVector(BoardGuardInset)).ComponentMax(FVector(.5f));
        FCollisionQueryParams Params(SCENE_QUERY_STAT(RideBoardRelease), false, LooseBoard->GetOwner());
        Params.AddIgnoredComponent(LooseBoard.Get());
        const FTransform At(LooseBoard->GetComponentQuat(), LooseBoard->GetComponentLocation());
        for (int32 Step = 0, Tries = 0; Step <= 10 && Tries < 20; ++Tries)
        {
            const FTransform Try(At.GetRotation(), At.GetLocation() + FVector(0, 0, 3.f * Step));
            FHitResult Hit;
            if (!FRideClipPlayer::SweepBox(*World, Try, Try, Extent, ECC_Pawn, Params, FCollisionResponseParams::DefaultResponseParam, Hit))
            {
                if (Step > 0) LooseBoard->SetWorldLocationAndRotation(Try.GetLocation(), Try.GetRotation(), false, nullptr, ETeleportType::TeleportPhysics);
                break;
            }
            // What moves is physics' own to push.
            UPrimitiveComponent* Other = Hit.GetComponent();
            if (Other && Other->IsSimulatingPhysics()) Params.AddIgnoredComponent(Other); else ++Step;
        }
    }
    LooseBoard->SetSimulatePhysics(true);
    LooseBoard->SetPhysicsLinearVelocity(Velocity + FVector::CrossProduct(Spin, Arm));
    LooseBoard->SetPhysicsAngularVelocityInRadians(Spin);
    LooseLast = LooseBoard->GetComponentTransform();
}

// ---------------------------------------------------------------------------------------------------------------
// The world around the body. Surfaces that only answer queries (the character walks on those) become physical near
// the body so its bodies and the loose board can touch them, and go back when the body has left.

// An instance's own body: none for an index out of range (GetBodyInstance falls back to the component's template).
static FBodyInstance* InstanceBody(UInstancedStaticMeshComponent* Mesh, int32 Index)
{
    if (!Mesh || Index < 0 || Index >= Mesh->GetInstanceCount()) return nullptr;
    FBodyInstance* Body = Mesh->GetBodyInstance(NAME_None, false, Index);
    return Body && Body != &Mesh->BodyInstance && Body->InstanceBodyIndex == Index ? Body : nullptr;
}

// How far an instance's bounds are from At (0 within them).
static double InstanceAway(const UInstancedStaticMeshComponent& Mesh, int32 Index, const FVector& At)
{
    FTransform Where;
    if (!Mesh.GetStaticMesh() || !Mesh.GetInstanceTransform(Index, Where, true)) return 0.;
    const FBoxSphereBounds Bounds = Mesh.GetStaticMesh()->GetBounds().TransformBy(Where);
    return FMath::Max(0., FVector::Dist(Bounds.Origin, At) - Bounds.SphereRadius);
}

// An instance's collision (its body is made again, by itself, when physics comes or goes).
// An instance body's switch rebuilds the body (FInstancedMeshComponentBodies::Recreate), which copies its responses and
// profile but not its object type: the new body is put back to the old one's type, or a WorldDynamic instance would come
// back WorldStatic.
static void SetInstanceCollision(UInstancedStaticMeshComponent* Mesh, int32 Index, ECollisionEnabled::Type Type)
{
    FBodyInstance* Body = InstanceBody(Mesh, Index);
    if (!Body) return;
    const ECollisionChannel Type0 = Body->GetObjectType();
    Body->SetCollisionEnabled(Type);
    if (FBodyInstance* Made = InstanceBody(Mesh, Index); Made && Made->GetObjectType() != Type0) Made->SetObjectType(Type0);
}

void URidePhysicalRider::MakeWorldPhysical(const FVector& Centre)
{
    if (!Rider) return;
    const float Radius = GetDefault<URidePhysicalSettings>()->WorldRadius;
    PhysicalCentre = Centre;
    // Let go of the surfaces far behind, unless a taken board still lies near them.
    const UPrimitiveComponent* Board = TakenBoard.Get();
    for (int32 I = MadePhysical.Num() - 1; I >= 0; --I)
    {
        UPrimitiveComponent* C = MadePhysical[I].Get();
        if (!C) { MadePhysical.RemoveAtSwap(I); continue; }
        const FBoxSphereBounds Bounds = C->Bounds;
        const double Away = FMath::Max(0., FVector::Dist(Bounds.Origin, Centre) - Bounds.SphereRadius);
        const double FromBoard = Board ? FMath::Max(0., FVector::Dist(Bounds.Origin, Board->GetComponentLocation()) - Bounds.SphereRadius) : 1e30;
        if (Away > Radius * 2. && FromBoard > Radius) { C->SetCollisionEnabled(ECollisionEnabled::QueryOnly); MadePhysical.RemoveAtSwap(I); }
    }
    for (int32 I = MadeInstances.Num() - 1; I >= 0; --I)
    {
        UInstancedStaticMeshComponent* M = MadeInstances[I].Mesh.Get();
        const int32 Index = MadeInstances[I].Index;
        if (!M) { MadeInstances.RemoveAtSwap(I); continue; }
        const double FromBoard = Board ? InstanceAway(*M, Index, Board->GetComponentLocation()) : 1e30;
        if (InstanceAway(*M, Index, Centre) > Radius * 2. && FromBoard > Radius) { SetInstanceCollision(M, Index, ECollisionEnabled::QueryOnly); MadeInstances.RemoveAtSwap(I); }
    }
    TArray<FOverlapResult> Hits;
    FCollisionObjectQueryParams Objects;
    Objects.AddObjectTypesToQuery(ECC_WorldStatic); Objects.AddObjectTypesToQuery(ECC_WorldDynamic);
    FCollisionQueryParams Params(SCENE_QUERY_STAT(RideWorld), false, Rider);
    Rider->GetWorld()->OverlapMultiByObjectType(Hits, Centre, FQuat::Identity, Objects, FCollisionShape::MakeSphere(Radius), Params);
    for (const FOverlapResult& Hit : Hits)
    {
        UPrimitiveComponent* C = Hit.GetComponent();
        if (!C || C == LooseBoard || C->GetCollisionEnabled() != ECollisionEnabled::QueryOnly) continue;
        if (C->GetCollisionResponseToChannel(ECC_PhysicsBody) != ECR_Block || C->GetCollisionResponseToChannel(ECC_Pawn) != ECR_Block) continue;
        // An instanced mesh (a village's houses and lots, a forest): each instance near, by itself; switching a whole
        // one would hitch, and the component's own switch never reaches its instances' bodies anyway.
        if (UInstancedStaticMeshComponent* Instanced = Cast<UInstancedStaticMeshComponent>(C))
        {
            const int32 Index = Hit.ItemIndex;
            const FBodyInstance* Body = InstanceBody(Instanced, Index);
            if (Body && Body->GetCollisionEnabled() == ECollisionEnabled::QueryOnly)
            {
                SetInstanceCollision(Instanced, Index, ECollisionEnabled::QueryAndPhysics);
                MadeInstances.Add({Instanced, Index});
            }
            continue;
        }
        C->SetCollisionEnabled(ECollisionEnabled::QueryAndPhysics);
        MadePhysical.Add(C);
    }
}

void URidePhysicalRider::RestoreWorld()
{
    // A taken board keeps the ground it lies on.
    const UPrimitiveComponent* Board = TakenBoard.Get();
    const float Radius = GetDefault<URidePhysicalSettings>()->WorldRadius;
    for (int32 I = MadePhysical.Num() - 1; I >= 0; --I)
    {
        UPrimitiveComponent* C = MadePhysical[I].Get();
        if (!C) { MadePhysical.RemoveAtSwap(I); continue; }
        if (Board && Board->IsSimulatingPhysics() && FVector::Dist(C->Bounds.Origin, Board->GetComponentLocation()) - C->Bounds.SphereRadius < Radius) continue;
        C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);
        MadePhysical.RemoveAtSwap(I);
    }
    for (int32 I = MadeInstances.Num() - 1; I >= 0; --I)
    {
        UInstancedStaticMeshComponent* M = MadeInstances[I].Mesh.Get();
        if (!M) { MadeInstances.RemoveAtSwap(I); continue; }
        if (Board && Board->IsSimulatingPhysics() && InstanceAway(*M, MadeInstances[I].Index, Board->GetComponentLocation()) < Radius) continue;
        SetInstanceCollision(M, MadeInstances[I].Index, ECollisionEnabled::QueryOnly);
        MadeInstances.RemoveAtSwap(I);
    }
    PhysicalCentre = FVector(1e30);
}
