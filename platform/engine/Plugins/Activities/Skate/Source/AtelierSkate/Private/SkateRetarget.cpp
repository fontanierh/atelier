// USkateComponent's pose retargeter (SkateRuntime.cpp): fits the native rider's pose onto the character, keeping
// the hands and feet out of the body and the ground.
#include "SkateComponent.h"
#include "SkateRuntimeDetail.h"
#include "Native/GameplaySession.h"
#include "Native/GroundSurfaceRuntime.h"
#include "Native/HostScalar.h"
#include "SkatePad.h"
#include <deque>
#include <limits>
#include <cfenv>
#include "Engine/Engine.h"
#include "SkateRider.h"
#include "SkateSettings.h"
#include "SkateFeel.h"
#include "SkateRails.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/HitResult.h"
#include "Materials/MaterialInterface.h"
#include "Engine/SkeletalMesh.h"
#include "PhysicsEngine/BodySetup.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformProcess.h"
#include "HAL/PlatformTime.h"
#include "Misc/App.h"
#include "HAL/Runnable.h"
#include "HAL/Event.h"
#include "HAL/RunnableThread.h"
#include "Containers/Queue.h"
#include <atomic>
#include "Misc/Paths.h"
#include "StaticMeshResources.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkinWeightVertexBuffer.h"
#include "TwoBoneIK.h"
#include "HAL/IConsoleManager.h"
#include "UObject/UObjectIterator.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/ObjectKey.h"
#include "Async/Async.h"
#include "Async/ParallelFor.h"
#include "Ride/RideClipPlayer.h"
#include "Ride/RidePoseMeasure.h"
#include "Ride/RideTuning.h"
#include "Ride/RidePhysicalRider.h"
#include "PhysicsEngine/PhysicsAsset.h"
#include "PhysicsEngine/SkeletalBodySetup.h"

// The skin of the limbs RetargetRetailPose keeps out of the body and the ground: the vertices skinned (most) to each
// hand or the hand's half of its forearm, and to each foot or toe, 48 farthest-point picks per limb (its extremes first:
// finger and toe tips, heels, then filling between).
static void SampleLimbSkin(FSkateRuntime& Runtime,USkeletalMesh* Asset,const FReferenceSkeleton& Ref,const TArray<FTransform>& Bind,
    const int32 Roots[4],const int32 Hands[2])
{
    Runtime.LimbMesh=Asset;
    for (TArray<FSkateRuntime::FSkinPoint>& Samples : Runtime.LimbSkin) Samples.Reset();
    Runtime.bArmsValid=false;
    const FSkeletalMeshRenderData* Data=Asset->GetResourceForRendering();
    if (!Data || Data->LODRenderData.IsEmpty()) return;
    const FSkeletalMeshLODRenderData& LOD=Data->LODRenderData[0];
    const auto& Positions=LOD.StaticVertexBuffers.PositionVertexBuffer;
    const FSkinWeightVertexBuffer* Weights=LOD.GetSkinWeightVertexBuffer();
    if (!Positions.GetVertexData() || !Weights || !Weights->GetDataVertexBuffer()->GetWeightData()) return;
    TArray<TPair<int32,FVector>> All[4];
    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
    {
        const TConstArrayView<FBoneIndexType> Bones=Section.HasUnifiedBoneMap()?LOD.GetUnifiedBoneMap():MakeArrayView(Section.BoneMap);
        for (uint32 V=Section.BaseVertexIndex;V<Section.BaseVertexIndex+Section.NumVertices;++V)
        {
            int32 Bone=INDEX_NONE; uint32 Most=0;
            for (uint32 K=0;K<Weights->GetMaxBoneInfluences();++K)
            {
                const uint32 Weight=Weights->GetBoneWeight(V,K),Local=Weights->GetBoneIndex(V,K);
                if (Weight>Most && Bones.IsValidIndex(Local) && Bind.IsValidIndex(Bones[Local])) { Most=Weight; Bone=Bones[Local]; }
            }
            if (Bone<0) continue;
            const FVector Position(Positions.VertexPosition(V));
            for (int32 L=0;L<4;++L)
            {
                if (Roots[L]<0) continue;
                bool bHand=false; int32 Up=Bone;
                while (Up>Roots[L]) { bHand|=L<2 && Up==Hands[L]; Up=Ref.GetParentIndex(Up); }
                if (Up!=Roots[L]) continue;
                // The forearm's elbow half stays out: an elbow by the waist is not a hand in the thigh.
                if (L<2 && !bHand && Hands[L]>=0)
                {
                    const FVector Axis=Bind[Hands[L]].GetLocation()-Bind[Roots[L]].GetLocation();
                    if (((Position-Bind[Roots[L]].GetLocation())|Axis)<.4*Axis.SizeSquared()) break;
                }
                All[L].Add({Bone,Position});
                break;
            }
        }
    }
    for (int32 L=0;L<4;++L)
    {
        const TArray<TPair<int32,FVector>>& Points=All[L];
        if (Points.IsEmpty()) continue;
        TArray<double> Near; Near.Init(TNumericLimits<double>::Max(),Points.Num());
        const FVector Root=Bind[Roots[L]].GetLocation();
        int32 Next=0;
        for (int32 I=1;I<Points.Num();++I) if (FVector::DistSquared(Points[I].Value,Root)>FVector::DistSquared(Points[Next].Value,Root)) Next=I;
        while (Runtime.LimbSkin[L].Num()<FMath::Min(L<2?96:48,Points.Num()))
        {
            const TPair<int32,FVector> Pick=Points[Next];
            Runtime.LimbSkin[L].Add({Pick.Key,Bind[Pick.Key].InverseTransformPosition(Pick.Value)});
            double Far=-1;
            for (int32 I=0;I<Points.Num();++I)
            {
                Near[I]=FMath::Min(Near[I],FVector::DistSquared(Points[I].Value,Pick.Value));
                if (Near[I]>Far) { Far=Near[I]; Next=I; }
            }
        }
    }
}

// The rider's own pelvis, spine, chest and thigh bodies, in their bones' spaces (fitted to its skin when the physical
// rider fits them), with a bounding sphere each. A hull whose planes are not cooked yet (a body asset fitted this frame)
// counts as its box and leaves the set incomplete: it is gathered again on the next frames (up to 120 times).
static void GatherBodies(FSkateRuntime& Runtime,USkeletalMesh* Asset,UPhysicsAsset* Physics,const FReferenceSkeleton& Ref,TFunctionRef<int32(const FString&)> Index)
{
    if (Runtime.BodiesFor.Get()!=Physics || Runtime.BodiesMesh.Get()!=Asset) { Runtime.BodiesTries=0; Runtime.bArmsValid=false; }
    ++Runtime.BodiesTries;
    Runtime.BodiesFor=Physics; Runtime.BodiesMesh=Asset; Runtime.Bodies.Reset(); Runtime.bBodiesComplete=true;
    for (const TCHAR* Contract : {TEXT("pelvis"),TEXT("spine"),TEXT("spine_mid"),TEXT("chest"),TEXT("thigh_L"),TEXT("thigh_R")})
    {
        const int32 Bone=Index(Contract);
        const int32 Body=Bone>=0?Physics->FindBodyIndex(Ref.GetBoneName(Bone)):INDEX_NONE;
        if (!Physics->SkeletalBodySetups.IsValidIndex(Body) || !Physics->SkeletalBodySetups[Body]) continue;
        const FKAggregateGeom& Geom=Physics->SkeletalBodySetups[Body]->AggGeom;
        FSkateRuntime::FBody B; B.Bone=Bone;
        TArray<FSphere> Bounds;
        for (const FKConvexElem& E : Geom.ConvexElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=0; S.Local=E.GetTransform(); E.GetPlanes(S.Planes);
            Bounds.Add(FSphere(S.Local.TransformPosition(E.ElemBox.GetCenter()),E.ElemBox.GetExtent().Size()));
            if (S.Planes.IsEmpty())
            {
                // Not cooked yet: its box until it is.
                Runtime.bBodiesComplete=false;
                if (!E.ElemBox.IsValid) continue;
                S.Kind=3; S.Local=FTransform(E.ElemBox.GetCenter())*E.GetTransform(); S.Half=E.ElemBox.GetExtent();
            }
            B.Shapes.Add(MoveTemp(S));
        }
        for (const FKSphylElem& E : Geom.SphylElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=1; S.Local=E.GetTransform(); S.Half=FVector(0,0,E.Length*.5); S.Radius=E.Radius;
            Bounds.Add(FSphere(E.Center,E.Length*.5+E.Radius)); B.Shapes.Add(MoveTemp(S));
        }
        for (const FKSphereElem& E : Geom.SphereElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=2; S.Local=FTransform(E.Center); S.Radius=E.Radius;
            Bounds.Add(FSphere(E.Center,E.Radius)); B.Shapes.Add(MoveTemp(S));
        }
        for (const FKBoxElem& E : Geom.BoxElems)
        {
            FSkateRuntime::FBodyShape S; S.Kind=3; S.Local=E.GetTransform(); S.Half=FVector(E.X,E.Y,E.Z)*.5;
            Bounds.Add(FSphere(E.Center,S.Half.Size())); B.Shapes.Add(MoveTemp(S));
        }
        if (B.Shapes.IsEmpty()) continue;
        for (const FSphere& S : Bounds) B.Centre+=S.Center/Bounds.Num();
        for (const FSphere& S : Bounds) B.Reach=FMath::Max(B.Reach,FVector::Dist(B.Centre,S.Center)+S.W);
        Runtime.Bodies.Add(MoveTemp(B));
    }
    if (Runtime.bBodiesComplete || Runtime.BodiesTries==120)
    {
        FString Names;
        for (const FSkateRuntime::FBody& B : Runtime.Bodies) Names+=FString::Printf(TEXT(" %s:%d"),*Ref.GetBoneName(B.Bone).ToString(),B.Shapes.Num());
        UE_LOG(LogTemp,Display,TEXT("SKATE arms keep clear of %d bodies of %s (%s), %s after %d gathers:%s"),Runtime.Bodies.Num(),*Physics->GetName(),
            *Asset->GetName(),Runtime.bBodiesComplete?TEXT("complete"):TEXT("hulls without planes"),Runtime.BodiesTries,*Names);
    }
}

// Signed distance (bone units, below 0 inside) from a point in a body's bone space to its shapes, and the way out.
static double BodyDistance(const FSkateRuntime::FBody& Body,const FVector& Q,FVector& Out)
{
    double D=TNumericLimits<double>::Max();
    for (const FSkateRuntime::FBodyShape& S : Body.Shapes)
    {
        const FVector P=S.Local.InverseTransformPosition(Q);
        double Shape=-TNumericLimits<double>::Max(); FVector N=FVector::UpVector;
        switch (S.Kind)
        {
        case 0:
            for (const FPlane& Plane : S.Planes) if (const double Dot=Plane.PlaneDot(P); Dot>Shape) { Shape=Dot; N=FVector(Plane.X,Plane.Y,Plane.Z); }
            break;
        case 1:
        {
            const FVector Axis(0,0,FMath::Clamp(P.Z,-S.Half.Z,S.Half.Z));
            N=(P-Axis).GetSafeNormal(); Shape=(P-Axis).Size()-S.Radius;
            break;
        }
        case 2: N=P.GetSafeNormal(); Shape=P.Size()-S.Radius; break;
        default:
        {
            const FVector Excess=P.GetAbs()-S.Half,Outside=Excess.ComponentMax(FVector::ZeroVector);
            if (Outside.IsNearlyZero())
            {
                const int32 Axis=Excess.X>Excess.Y?(Excess.X>Excess.Z?0:2):(Excess.Y>Excess.Z?1:2);
                N=FVector::ZeroVector; N[Axis]=P[Axis]<0?-1.:1.; Shape=Excess[Axis];
            }
            else { N=(Outside*P.GetSignVector()).GetSafeNormal(); Shape=Outside.Size(); }
        }
        }
        if (Shape<D) { D=Shape; Out=S.Local.TransformVectorNoScale(N); }
    }
    return D;
}

// Each arm swings out about its shoulder (the whole arm, its bend kept) just far enough that its hand's and forearm's
// skin is Margin (component units) out of the rider's own body, at most 30 degrees. The swing is one abduction per arm,
// about the axis that carries a hanging arm straight out from the body's midline (across the torso, pelvis to chest), so
// it turns smoothly with the pose: no face or way out is chosen per frame. The angle needed is the smallest that clears
// every sample (a 2.5 degree scan, then the crossing found inside its step), and the arm follows it through a critically
// damped spring (half-life 0.05 s out, 0.15 s back) whose speed (170 degrees/s) and acceleration are capped, so a fast
// move may graze the body for a moment but the arm never snaps. Dt below 0 or over 0.25 s starts it afresh.
static void ClearArms(FSkateRuntime& Runtime,const FReferenceSkeleton& Ref,TArray<FTransform>& Output,const int32 Uppers[2],int32 Pelvis,int32 Chest,
    double Margin,double Dt)
{
    constexpr double Degree=UE_DOUBLE_PI/180.,Step=2.5*Degree,MaxSwing=30.*Degree;
    constexpr double RiseHalfLife=.05,FallHalfLife=.15,MaxRate=170.*Degree,MaxAccel=6000.*Degree;
    if (Pelvis<0 || Chest<0 || Uppers[0]<0 || Uppers[1]<0) return;
    const FVector Spine=(Output[Chest].GetLocation()-Output[Pelvis].GetLocation()).GetSafeNormal();
    const FVector Across=FVector::VectorPlaneProject(Output[Uppers[1]].GetLocation()-Output[Uppers[0]].GetLocation(),Spine).GetSafeNormal();
    if (Spine.IsNearlyZero() || Across.IsNearlyZero()) return;
    const bool bFresh=!Runtime.bArmsValid || Dt<0 || Dt>.25;
    for (int32 H=0;H<2;++H)
    {
        const int32 Upper=Uppers[H];
        const TArray<FSkateRuntime::FSkinPoint>& Skin=Runtime.LimbSkin[H];
        if (Skin.IsEmpty()) continue;
        const FVector Shoulder=Output[Upper].GetLocation();
        // Out from the midline on this arm's side (left shoulder to right is +Across); the axis turns -Spine toward it.
        const FVector Axis=FVector::CrossProduct(-Spine,H?Across:-Across);
        TArray<FVector,TInlineAllocator<128>> Points;
        double Arm=0;
        for (const FSkateRuntime::FSkinPoint& Point : Skin)
        {
            Points.Add(Output[Point.Bone].TransformPosition(Point.Local)-Shoulder);
            Arm=FMath::Max(Arm,Points.Last().Size());
        }
        // The bodies the arm can reach at any swing (a swing keeps each sample's distance from the shoulder).
        TArray<const FSkateRuntime::FBody*,TInlineAllocator<8>> Near;
        for (const FSkateRuntime::FBody& Body : Runtime.Bodies)
        {
            const FTransform& Frame=Output[Body.Bone];
            if (FVector::Dist(Frame.TransformPosition(Body.Centre),Shoulder)<=Arm+Body.Reach*Frame.GetMaximumAxisScale()+2.*Margin) Near.Add(&Body);
        }
        // The arm's clearance turned by Angle: the least over its samples and the bodies of the distance out of the body
        // less Margin, capped at Margin (a sample beyond a body's bounding sphere by that much counts as the cap, so the
        // cull keeps it continuous).
        const auto Clearance=[&](double Angle)
        {
            const FQuat Turn(Axis,Angle);
            double Least=Margin;
            for (const FSkateRuntime::FBody* Each : Near)
            {
                const FSkateRuntime::FBody& Body=*Each;
                const FTransform& Frame=Output[Body.Bone];
                const double Scale=Frame.GetMaximumAxisScale(),Reach=Body.Reach*Scale+2.*Margin;
                const FVector Centre=Frame.TransformPosition(Body.Centre);
                for (const FVector& Point : Points)
                {
                    const FVector P=Shoulder+Turn.RotateVector(Point);
                    if (FVector::DistSquared(P,Centre)>Reach*Reach) continue;
                    FVector Way;
                    Least=FMath::Min(Least,BodyDistance(Body,Frame.InverseTransformPosition(P),Way)*Scale-Margin);
                }
            }
            return Least;
        };
        double Need=0;
        if (double Low=Clearance(0.); Low<0)
        {
            Need=MaxSwing;
            for (double Angle=Step;Angle<=MaxSwing+1e-9;Angle+=Step)
            {
                double High=Clearance(Angle);
                if (High<0) { Low=High; continue; }
                // The crossing inside this step: halve it three times, then interpolate.
                double From=Angle-Step,To=Angle;
                for (int32 I=0;I<3;++I)
                {
                    const double Mid=(From+To)*.5,At=Clearance(Mid);
                    if (At<0) { From=Mid; Low=At; } else { To=Mid; High=At; }
                }
                Need=From+(To-From)*(-Low)/FMath::Max(High-Low,1e-9);
                break;
            }
        }
        Runtime.ArmNeed[H]=Need;
        double& Swing=Runtime.ArmSwing[H];
        double& Rate=Runtime.ArmRate[H];
        if (bFresh) { Swing=Need; Rate=0; }
        else
        {
            // A critically damped spring toward the need ((1 + wt) e^-wt halves the gap at wt = 1.678), in steps of at
            // most 1/120 s.
            for (double Left=Dt;Left>1e-6;)
            {
                const double Sub=FMath::Min(Left,1./120.),W=1.678/(Need>Swing?RiseHalfLife:FallHalfLife);
                const double Accel=FMath::Clamp(W*W*(Need-Swing)-2.*W*Rate,-MaxAccel,MaxAccel);
                Rate=FMath::Clamp(Rate+Accel*Sub,-MaxRate,MaxRate);
                Swing+=Rate*Sub;
                if (Swing<0) { Swing=0; Rate=FMath::Max(Rate,0.); }
                else if (Swing>MaxSwing) { Swing=MaxSwing; Rate=FMath::Min(Rate,0.); }
                Left-=Sub;
            }
        }
        if (Swing<=1e-6) continue;
        const FQuat Turn(Axis,Swing);
        for (int32 I=Upper;I<Ref.GetNum();++I)
        {
            int32 Above=I;
            while (Above>Upper) Above=Ref.GetParentIndex(Above);
            if (Above!=Upper) continue;
            Output[I].SetRotation(Turn*Output[I].GetRotation());
            Output[I].SetLocation(Shoulder+Turn.RotateVector(Output[I].GetLocation()-Shoulder));
        }
    }
    Runtime.bArmsValid=true;
}

void USkateComponent::RetargetRetailPose()
{
    USkeletalMeshComponent* Mesh=Rider->GetMesh();
    if (!Mesh || !Mesh->GetSkeletalMeshAsset()) return;
    const FReferenceSkeleton& Ref=Mesh->GetSkeletalMeshAsset()->GetRefSkeleton();
    struct Mapping { const TCHAR* Target; const TCHAR* Source; const TCHAR* Child; };
    static const Mapping Map[]={
        {TEXT("pelvis"),TEXT("HIPS"),TEXT("SPINE")},{TEXT("spine"),TEXT("SPINE"),TEXT("SPINE1")},
        {TEXT("spine_mid"),TEXT("SPINE1"),TEXT("SPINE3")},{TEXT("chest"),TEXT("SPINE3"),TEXT("NECK")},
        {TEXT("neck"),TEXT("NECK"),TEXT("HEAD")},{TEXT("head"),TEXT("HEAD"),nullptr},
        {TEXT("clavicle_L"),TEXT("LEFTSHOULDER"),TEXT("LEFTARM")},{TEXT("upperarm_L"),TEXT("LEFTARM"),TEXT("LEFTFOREARM")},
        {TEXT("forearm_L"),TEXT("LEFTFOREARM"),TEXT("LEFTHAND")},{TEXT("hand_L"),TEXT("LEFTHAND"),nullptr},
        {TEXT("clavicle_R"),TEXT("RIGHTSHOULDER"),TEXT("RIGHTARM")},{TEXT("upperarm_R"),TEXT("RIGHTARM"),TEXT("RIGHTFOREARM")},
        {TEXT("forearm_R"),TEXT("RIGHTFOREARM"),TEXT("RIGHTHAND")},{TEXT("hand_R"),TEXT("RIGHTHAND"),nullptr},
        {TEXT("thigh_L"),TEXT("LEFTUPLEG"),TEXT("LEFTLEG")},{TEXT("shin_L"),TEXT("LEFTLEG"),TEXT("LEFTFOOT")},
        {TEXT("foot_L"),TEXT("LEFTFOOT"),TEXT("LEFTTOEBASE")},{TEXT("toe_L"),TEXT("LEFTTOEBASE"),nullptr},
        {TEXT("thigh_R"),TEXT("RIGHTUPLEG"),TEXT("RIGHTLEG")},{TEXT("shin_R"),TEXT("RIGHTLEG"),TEXT("RIGHTFOOT")},
        {TEXT("foot_R"),TEXT("RIGHTFOOT"),TEXT("RIGHTTOEBASE")},{TEXT("toe_R"),TEXT("RIGHTTOEBASE"),nullptr}
    };
    // The rider names its own bone for each contract role (ISkateRider::GetSkateBone).
    auto Index=[&](const FString& Contract){ const FName Bone=RiderApi?RiderApi->GetSkateBone(FName(*Contract)):FName(*Contract); return Bone.IsNone()?INDEX_NONE:Ref.FindBoneIndex(Bone); };
    TArray<const Mapping*> Matches; Matches.Init(nullptr,Ref.GetNum());
    for (const Mapping& M : Map) if (const int32 Bone=Index(M.Target); Bone>=0) Matches[Bone]=&M;
    TArray<FTransform> Bind,Output; Bind.SetNum(Ref.GetNum()); Output.SetNum(Ref.GetNum()); RetailPose.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I) { int32 P=Ref.GetParentIndex(I); Bind[I]=P>=0?Ref.GetRefBonePose()[I]*Bind[P]:Ref.GetRefBonePose()[I]; }
    auto Source=[&](const TCHAR* N){return RetailRuntime->Names.IndexOfByKey(FName(N));};
    const int32 Hip=Index(TEXT("pelvis")),Foot=Index(TEXT("foot_L")),SHip=Source(TEXT("HIPS")),SFoot=Source(TEXT("LEFTFOOT"));
    if (Hip<0 || Foot<0 || SHip<0 || SFoot<0) { RetailPose.Reset(); return; }
    const float Ratio=(Bind[Hip].GetLocation().Z-Bind[Foot].GetLocation().Z)*Mesh->GetComponentScale().Z /
        FMath::Max(1.,RetailRuntime->Reference[SHip].GetLocation().Z-RetailRuntime->Reference[SFoot].GetLocation().Z);
    // PhysCustom runs inside CharacterMovement's scoped move. The capsule already has the new pose, but its
    // children's cached world transforms are not propagated until the scope closes. Using that stale mesh world
    // transform adds the frame's travel to the bones a second time: at uneven frame rates the rider flickers
    // back and forth over the board. Compose from the current parent and the authored mesh-local transform.
    const FTransform MeshWorld=Mesh->GetRelativeTransform()*Rider->GetActorTransform();
    const FTransform RootToMesh=RetailRuntime->Root.GetRelativeTransform(MeshWorld);
    // Preserve sole height: the source ankle is much farther above its sole than this character's ankle. A bigger
    // board's deck is higher by its extra deck height (9.05 cm at the source's size).
    // Off the board the clips' root is on the ground: standing on the deck (OffBoardLift 1) the body rises onto the
    // visible deck, which is not scaled with the body.
    const float DeckLift=bOffBoardPose?OffBoardLift*((BoardScale()-1.f)*9.05f+(1.f-Ratio)*8.9f):(BoardScale()-1.f)*9.05f;
    const float SoleOffset=(Bind[Foot].GetLocation().Z-Bind[0].GetLocation().Z)*Mesh->GetComponentScale().Z -
        (RetailRuntime->Reference[SFoot].GetLocation().Z-RetailRuntime->Reference[0].GetLocation().Z)*Ratio+DeckLift;
    auto InMesh=[&](FTransform T){ T.ScaleTranslation(Ratio); T.AddToTranslation(FVector(0,0,SoleOffset)); return T*RootToMesh; };
    // The visible deck off the board: on the ground it is where the clip has it, grown about its contact like a
    // ridden board; held, it goes with the body's hands (scaled with the body). Between the two by its height.
    if (bOffBoardPose)
    {
        const int32 SD=Source(TEXT("SKATEBOARD_ROOT"));
        const float S=BoardScale();
        if (SD>=0)
        {
            const FTransform Clip=RetailRuntime->Bones[SD]*RetailRuntime->Root;
            const FVector Contact=Clip.GetLocation()-Clip.GetRotation().GetUpVector()*9.05;
            const FTransform Ground=Clip*FTransform(FQuat::Identity,Contact*(1.-S),FVector(S));
            FTransform Held=InMesh(RetailRuntime->Bones[SD])*MeshWorld; Held.SetScale3D(FVector(S));
            OffBoardDeck.Blend(Ground,Held,FMath::SmoothStep(15.f,45.f,float(RetailRuntime->Bones[SD].GetLocation().Z)));
        }
        else OffBoardDeck=FTransform(RetailRuntime->Root.GetRotation(),RetailRuntime->Root.GetLocation(),FVector(S));
        // A board just taken off a hand of the character's own pose eases from there (RideTransition.cpp).
        if (OffBoardDeckBlend<1.f) { const FTransform To=OffBoardDeck; OffBoardDeck.Blend(OffBoardDeckFrom,To,FMath::SmoothStep(0.f,1.f,OffBoardDeckBlend)); }
    }
    auto Frame=[](FVector Left,FVector Right,FVector Head,FVector HipP) { FVector Up=(Head-HipP).GetSafeNormal(); return FRotationMatrix::MakeFromXZ(FVector::CrossProduct(Right-Left,Up).GetSafeNormal(),Up).ToQuat(); };
    const int32 TL=Index(TEXT("thigh_L")),TR=Index(TEXT("thigh_R")),TH=Index(TEXT("head"));
    if (TL<0 || TR<0 || TH<0 || Source(TEXT("LEFTUPLEG"))<0 || Source(TEXT("RIGHTUPLEG"))<0 || Source(TEXT("HEAD"))<0)
    { RetailPose.Reset(); return; }
    // Imported meshes can carry a 180-degree facing correction. Joint names alone cannot recover it.
    const FQuat TargetFrame=FRotationMatrix::MakeFromXZ(SavedMeshRotation.UnrotateVector(FVector::ForwardVector),
        (Bind[TH].GetLocation()-Bind[Hip].GetLocation()).GetSafeNormal()).ToQuat();
    const FQuat Base=Frame(InMesh(RetailRuntime->Reference[Source(TEXT("LEFTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("RIGHTUPLEG"))]).GetLocation(),InMesh(RetailRuntime->Reference[Source(TEXT("HEAD"))]).GetLocation(),InMesh(RetailRuntime->Reference[SHip]).GetLocation()) * TargetFrame.Inverse();
    TArray<FQuat> Fits; Fits.Init(Base,Ref.GetNum());
    TArray<FVector> Targets; Targets.SetNum(Ref.GetNum());
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I); const Mapping* Match=Matches[I];
        if (Match && Source(Match->Source)>=0)
        {
            const int32 S=Source(Match->Source); const FTransform SB=InMesh(RetailRuntime->Reference[S]),SP=InMesh(RetailRuntime->Bones[S]);
            FQuat FitRotation=Base;
            // Hands and toes inherit the limb's reference alignment; a body-facing frame would twist them.
            if (!Match->Child && Parent>=0 && FCString::Strcmp(Match->Target,TEXT("head"))!=0) FitRotation=Fits[Parent];
            if (Match->Child && Source(Match->Child)>=0)
            {
                // A rider without the next contract bone (a spine one segment shorter) aims at the one after it.
                const TCHAR* ChildSource=Match->Child; int32 Child=INDEX_NONE;
                while (ChildSource && Child<0)
                {
                    const Mapping* Next=nullptr;
                    for (const Mapping& M : Map) if (FCString::Strcmp(M.Source,ChildSource)==0) { Next=&M; break; }
                    if (!Next) break;
                    Child=Index(Next->Target);
                    if (Child<0) ChildSource=Next->Child;
                }
                if (Child>=0 && Source(ChildSource)>=0)
                {
                    FVector A=Base.RotateVector(Bind[Child].GetLocation()-Bind[I].GetLocation());
                    FVector B=InMesh(RetailRuntime->Reference[Source(ChildSource)]).GetLocation()-SB.GetLocation();
                    // The source ankle/toe height difference is anatomical, not a toe-down foot rotation.
                    if (FCString::Strncmp(Match->Target,TEXT("foot_"),5)==0)
                    {
                        const FVector Up=RootToMesh.GetRotation().GetUpVector();
                        A=FVector::VectorPlaneProject(A,Up); B=FVector::VectorPlaneProject(B,Up);
                    }
                    FitRotation=FQuat::FindBetweenNormals(A.GetSafeNormal(),B.GetSafeNormal())*Base;
                }
            }
            const FTransform Fit(FitRotation,SB.GetLocation()-FitRotation.RotateVector(Bind[I].GetLocation()));
            Fits[I]=FitRotation;
            Output[I]=Bind[I]*Fit*SB.Inverse()*SP;
            Output[I].SetScale3D(Bind[I].GetScale3D());
        }
        else Output[I]=Parent>=0?Ref.GetRefBonePose()[I]*Output[Parent]:Ref.GetRefBonePose()[I];
        Targets[I]=Output[I].GetLocation();
        // Transfer motion, not adult bone lengths. In particular the source has an extra spine segment.
        if (Parent>=0 && I!=Hip)
            Output[I].SetLocation(Output[Parent].TransformPosition(Ref.GetRefBonePose()[I].GetLocation()));
    }
    // Preserve the source foot contacts while solving with this character's actual thigh/shin lengths.
    for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
    {
        const int32 A=Index(FString::Printf(TEXT("thigh_%s"),Side));
        const int32 B=Index(FString::Printf(TEXT("shin_%s"),Side));
        const int32 C=Index(FString::Printf(TEXT("foot_%s"),Side));
        if (A<0 || B<0 || C<0) continue;
        const FQuat FootTurn=Output[C].GetRotation();
        const FVector Pole=Targets[B]+(Targets[B]-(Targets[A]+Targets[C])*.5)*2;
        AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Targets[C],false,1.f,1.f);
        Output[C].SetRotation(FootTurn);
        // The toe remains its authored distance from the ankle; it must not stretch through the deck.
        for (int32 I=C+1;I<Ref.GetNum();++I)
            if (Ref.GetParentIndex(I)==C) Output[I]=Ref.GetRefBonePose()[I]*Output[C];
    }
    // The limbs against this rider's own body and the ground, outside bails (which keep the skin up themselves).
    if (Mode!=ESkateMode::Bail)
    {
        const int32 Roots[4]={Index(TEXT("forearm_L")),Index(TEXT("forearm_R")),Index(TEXT("foot_L")),Index(TEXT("foot_R"))};
        const int32 Hands[2]={Index(TEXT("hand_L")),Index(TEXT("hand_R"))},Uppers[2]={Index(TEXT("upperarm_L")),Index(TEXT("upperarm_R"))};
        USkeletalMesh* Asset=Mesh->GetSkeletalMeshAsset();
        if (RetailRuntime->LimbMesh.Get()!=Asset) SampleLimbSkin(*RetailRuntime,Asset,Ref,Bind,Roots,Hands);
        // A source foot steps on the source's ground plane (pushing, braking), which on this rider's proportions can be
        // under the real ground: each foot whose sole goes under the ground below it lifts out, the leg solved to it.
        if (const float Above=CVarSkateFootGround.GetValueOnGameThread(); Above>=0.f && !bOffBoardPose)
        {
            FCollisionQueryParams Query(SCENE_QUERY_STAT(SkateFootGround),false,Rider);
            for (int32 S=0;S<2;++S)
            {
                const TArray<FSkateRuntime::FSkinPoint>& Sole=RetailRuntime->LimbSkin[2+S];
                const int32 A=Index(S?TEXT("thigh_R"):TEXT("thigh_L")),B=Index(S?TEXT("shin_R"):TEXT("shin_L")),C=Roots[2+S];
                if (Sole.IsEmpty() || A<0 || B<0 || C<0) continue;
                const FVector Ankle=MeshWorld.TransformPosition(Output[C].GetLocation());
                FHitResult Hit;
                if (!GetWorld()->LineTraceSingleByChannel(Hit,Ankle+FVector(0,0,20),Ankle-FVector(0,0,80),ECC_Pawn,Query) || Hit.bStartPenetrating || Hit.ImpactNormal.Z<.5)
                    continue;
                double Under=0;
                for (const FSkateRuntime::FSkinPoint& Point : Sole)
                    Under=FMath::Max(Under,double((FVector(Hit.ImpactPoint)-MeshWorld.TransformPosition(Output[Point.Bone].TransformPosition(Point.Local)))|FVector(Hit.ImpactNormal))+Above);
                // Deeper than a sole goes is not a foot in the ground (a ledge or rail over the ankle).
                if (Under<=0 || Under>15.) continue;
                const FQuat FootTurn=Output[C].GetRotation();
                const FVector Knee=Output[B].GetLocation(),Pole=Knee+(Knee-(Output[A].GetLocation()+Output[C].GetLocation())*.5)*2;
                const FVector Target=Output[C].GetLocation()+MeshWorld.InverseTransformVector(FVector(Hit.ImpactNormal)*Under);
                AnimationCore::SolveTwoBoneIK(Output[A],Output[B],Output[C],Pole,Target,false,1.f,1.f);
                Output[C].SetRotation(FootTurn);
                for (int32 I=C+1;I<Ref.GetNum();++I)
                {
                    int32 Up=I;
                    while (Up>C) Up=Ref.GetParentIndex(Up);
                    if (Up==C) Output[I]=Ref.GetRefBonePose()[I]*Output[Ref.GetParentIndex(I)];
                }
            }
        }
        // The source's arms hang beside an adult's hips; beside wider hips and thighs the hands sink into them. Each arm
        // swings out until its hand and forearm clear the rider's own body by skate.ArmClear (ClearArms), smoothed over
        // the frames (the world's clock). A grab solves after this, so it still reaches its board.
        const double Now=GetWorld()?GetWorld()->GetTimeSeconds():0.,ArmDt=RetailRuntime->ArmTime>=0?Now-RetailRuntime->ArmTime:-1.;
        RetailRuntime->ArmTime=Now;
        if (const float Clear=CVarSkateArmClear.GetValueOnGameThread(); Clear>=0.f)
        {
            UPhysicsAsset* Physics=Mesh->GetPhysicsAsset();
            if (Physics && (RetailRuntime->BodiesFor.Get()!=Physics || RetailRuntime->BodiesMesh.Get()!=Asset || (!RetailRuntime->bBodiesComplete && RetailRuntime->BodiesTries<120))) GatherBodies(*RetailRuntime,Asset,Physics,Ref,Index);
            if (Physics && !RetailRuntime->Bodies.IsEmpty())
                ClearArms(*RetailRuntime,Ref,Output,Uppers,Index(TEXT("pelvis")),Index(TEXT("chest")),Clear/FMath::Max(Mesh->GetComponentScale().GetMax(),1e-4),ArmDt);
            else RetailRuntime->bArmsValid=false;
        }
        else RetailRuntime->bArmsValid=false;
    }
    else RetailRuntime->bArmsValid=false;
    // A grab closes the source hand on its own deck, but this arm only follows the source arm's directions at this
    // character's scale, so the hand stops short of the board with straight fingers. Where the source hand reaches
    // its deck, hold the nearest edge of the board instead (knuckles just outside it, fingers hooked under, thumb
    // over the grip tape) and solve the arm to that hand. The grip is sized by the rider's own hand.
    const int32 SDeck=Source(TEXT("SKATEBOARD_ROOT"));
    if (Mode!=ESkateMode::Bail && SDeck>=0 && Deck && Deck->GetStaticMesh())
    {
        TArray<float> Grip;
        {
            TArray<FString> Words; CVarSkateGrip.GetValueOnGameThread().ParseIntoArrayWS(Words);
            for (const FString& Word : Words) Grip.Add(FCString::Atof(*Word));
            Grip.SetNumZeroed(9);
        }
        // The deck mesh's frame is the source deck's (SM_SkateDeck: origin at the deck-top centre, nose +X).
        const FBox Box=Deck->GetStaticMesh()->GetBoundingBox();
        const double HalfWidth=Box.GetExtent().Y,HalfLength=Box.GetExtent().X,Flat=HalfLength-HalfWidth,KickStart=.675*HalfLength;
        constexpr double Concave=.9,Thickness=1.2,SourceKnuckle=9.;
        // Top of the deck's rail: the concave lifts the sides, and the kicks rise to the ends.
        auto RailTop=[&](double X){ const double T=FMath::Clamp((FMath::Abs(X)-KickStart)/(HalfLength-KickStart),0.,1.); return Concave+T*T*(Box.Max.Z-Concave); };
        // The visible deck: a bigger board's outline scales with it, the grip offsets stay at the hand's size.
        const FTransform DeckToMesh=(bOffBoardPose?OffBoardDeck:RetailRuntime->Bone(TEXT("SKATEBOARD_ROOT"))*BoardGrowth()).GetRelativeTransform(MeshWorld);
        for (const TCHAR* Side : {TEXT("L"),TEXT("R")})
        {
            auto Target=[&](const TCHAR* Name){ return Index(FString::Printf(TEXT("%s_%s"),Name,Side)); };
            const FString SourceSide=Side[0]=='L'?TEXT("LEFT"):TEXT("RIGHT");
            const int32 Upper=Target(TEXT("upperarm")),Fore=Target(TEXT("forearm")),Hand=Target(TEXT("hand")),ThumbEnd=Target(TEXT("thumb_end"));
            const int32 SHand=Source(*(SourceSide+TEXT("HAND"))),SFore=Source(*(SourceSide+TEXT("FOREARM")));
            if (Upper<0 || Fore<0 || Hand<0 || SHand<0 || SFore<0) continue;
            // The source hand and its length axis in its deck's frame; its knuckles are about 9 cm down that axis.
            const FTransform SourceHand=RetailRuntime->Bones[SHand].GetRelativeTransform(RetailRuntime->Bones[SDeck]);
            const FTransform& SourceRef=RetailRuntime->Reference[SHand];
            const FVector Axis=SourceHand.GetRotation().RotateVector(SourceRef.GetRotation().UnrotateVector(
                (SourceRef.GetLocation()-RetailRuntime->Reference[SFore].GetLocation()).GetSafeNormal()));
            const FVector Knuckle=SourceHand.GetLocation()+Axis*SourceKnuckle;
            // The nearest point of the deck's outline (straight rails, round ends) and its outward normal.
            const double Along=FMath::Clamp(Knuckle.X,-Flat,Flat);
            FVector Out=FVector(Knuckle.X-Along,Knuckle.Y,0).GetSafeNormal();
            if (Out.IsNearlyZero()) continue;
            const FVector Edge=FVector(Along,0,0)+Out*HalfWidth;
            const float Weight=1.f-FMath::SmoothStep(4.f,20.f,float(FVector::Dist(Knuckle,Edge+FVector(0,0,RailTop(Edge.X)-Thickness*.5))));
            if (Weight<=0.f) continue;
            // Hand frame on the board: fingers down the source hand's axis, kept in the plane across the edge; palm
            // towards the deck.
            const FVector Down=(Axis-(Axis|Out)*Out).GetSafeNormal(),Palm=(-Out-((-Out)|Down)*Down).GetSafeNormal();
            const FTransform& HandBind=Bind[Hand];
            auto Local=[&](int32 Bone){ return HandBind.GetRotation().UnrotateVector(Bind[Bone].GetLocation()-HandBind.GetLocation()); };
            // The rider's own hand frame and size come from its bind. Fingers are optional in the humanoid contract:
            // with them, the hand's axis runs to the middle knuckle (or the knuckles' mean), the knuckle line crosses
            // it, the palm is on the thumb's side and a finger's width is the knuckle spacing. Without them, the hand
            // continues the forearm, its palm faces the bind's floor and its size follows the upper arm.
            TArray<int32> Knuckles,Numbers;
            for (int32 N=0;N<4;++N)
                if (const int32 K=Target(*FString::Printf(TEXT("finger_%d"),N)); K>=0) { Knuckles.Add(K); Numbers.Add(N); }
            const double UpperLength=FVector::Dist(Bind[Upper].GetLocation(),Bind[Fore].GetLocation());
            FVector KnuckleLocal=HandBind.GetRotation().UnrotateVector(HandBind.GetLocation()-Bind[Fore].GetLocation()).GetSafeNormal()*UpperLength*.45;
            double FingerWidth=UpperLength*.1;
            if (const int32 Middle=Target(TEXT("finger_1")); Middle>=0) KnuckleLocal=Local(Middle);
            else if (!Knuckles.IsEmpty())
            {
                KnuckleLocal=FVector::ZeroVector;
                for (const int32 K : Knuckles) KnuckleLocal+=Local(K)/Knuckles.Num();
            }
            const FVector LAlong=KnuckleLocal.GetSafeNormal();
            FVector LAcross=FVector::ZeroVector;
            if (Knuckles.Num()>=2)
            {
                // The knuckle line is not square to the hand's axis: square it first, or the palm normal tilts with it.
                const FVector Line=Local(Knuckles.Last())-Local(Knuckles[0]);
                LAcross=FVector::VectorPlaneProject(Line,LAlong).GetSafeNormal();
                FingerWidth=Line.Size()/(Numbers.Last()-Numbers[0]);
            }
            FVector LPalm=ThumbEnd>=0?Local(ThumbEnd):HandBind.GetRotation().UnrotateVector(FVector::DownVector);
            LPalm-=(LPalm|LAlong)*LAlong; LPalm-=(LPalm|LAcross)*LAcross; LPalm.Normalize();
            if (Down.IsNearlyZero() || Palm.IsNearlyZero() || LAlong.IsNearlyZero() || LPalm.IsNearlyZero()) continue;
            const FQuat HandInDeck=FRotationMatrix::MakeFromXY(Down,Palm).ToQuat()*FRotationMatrix::MakeFromXY(LAlong,LPalm).ToQuat().Inverse();
            const FQuat HandRotation=DeckToMesh.GetRotation()*HandInDeck;
            const double Width=FingerWidth*Mesh->GetComponentScale().Z/BoardScale();
            const FVector KnuckleTarget=DeckToMesh.TransformPosition(Edge+Out*Grip[1]*Width+FVector(0,0,RailTop(Edge.X)+Grip[0]*Width));
            const FVector Wrist=KnuckleTarget-HandRotation.RotateVector(KnuckleLocal);
            const FQuat Retargeted=Output[Hand].GetRotation();
            const FVector Pole=Targets[Fore]+(Targets[Fore]-(Targets[Upper]+Targets[Hand])*.5)*2;
            AnimationCore::SolveTwoBoneIK(Output[Upper],Output[Fore],Output[Hand],Pole,FMath::Lerp(Output[Hand].GetLocation(),Wrist,double(Weight)),false,1.f,1.f);
            Output[Hand].SetRotation(FQuat::Slerp(Retargeted,HandRotation,Weight));
            // Curl each finger towards the palm about its own knuckle axis. Finger angles are absolute (cumulative from
            // the hand's axis, so the bind's own curl does not add up); the thumb swings towards the fingers first.
            const FQuat HandNow=Output[Hand].GetRotation();
            TMap<int32,FQuat> Turns;
            for (int32 Digit=0;Digit<5;++Digit)
            {
                const bool Thumb=Digit==4;
                const int32 Joints[3]={Thumb?Target(TEXT("thumb")):Target(*FString::Printf(TEXT("finger_%d"),Digit)),
                    Thumb?Target(TEXT("thumb_tip")):Target(*FString::Printf(TEXT("finger_tip_%d"),Digit)),
                    Thumb?ThumbEnd:Target(*FString::Printf(TEXT("finger_end_%d"),Digit))};
                if (Joints[0]<0 || Joints[1]<0 || Joints[2]<0) continue;
                const FVector Segments[3]={(Local(Joints[1])-Local(Joints[0])).GetSafeNormal(),(Local(Joints[2])-Local(Joints[1])).GetSafeNormal(),(Local(Joints[2])-Local(Joints[1])).GetSafeNormal()};
                const FVector SwingAxis=(Segments[0]^LAlong).GetSafeNormal();
                const double Swing=Thumb?FMath::DegreesToRadians(Grip[5]*Weight):0.;
                const FVector Bend=(FQuat(SwingAxis,Swing).RotateVector(Segments[0])^LPalm).GetSafeNormal();
                double Applied=0,Wanted=0;
                for (int32 J=0;J<3;++J)
                {
                    const double BindAngle=FMath::RadiansToDegrees(FMath::Atan2(Segments[J]|LPalm,Segments[J]|LAlong));
                    Wanted+=Grip[Thumb?6+J:2+J];
                    const double Delta=Thumb?Grip[6+J]:(Wanted-BindAngle)-Applied; Applied+=Delta;
                    FQuat Turn=FQuat(HandNow.RotateVector(Bend),FMath::DegreesToRadians(Delta*Weight));
                    if (J==0 && Thumb) Turn=Turn*FQuat(HandNow.RotateVector(SwingAxis),Swing);
                    Turns.Add(Joints[J],Turn);
                }
            }
            for (int32 I=Hand+1;I<Ref.GetNum();++I)
            {
                int32 Up=Ref.GetParentIndex(I);
                while (Up>Hand) Up=Ref.GetParentIndex(Up);
                if (Up!=Hand) continue;
                Output[I]=Ref.GetRefBonePose()[I]*Output[Ref.GetParentIndex(I)];
                if (const FQuat* Turn=Turns.Find(I)) Output[I].SetRotation(*Turn*Output[I].GetRotation());
            }
        }
    }
    // The source physical rider has adult proportions; the character's head and clothing can extend beyond it.
    // During a bail, keep the retargeted skin above the supporting surface without changing bone lengths
    // or feeding visual corrections back into the recovered rigid-body solver.
    RetailFloorClearance=0.f;
    if (Mode==ESkateMode::Bail)
    {
        USkeletalMesh* Asset=Mesh->GetSkeletalMeshAsset();
        if (RetailRuntime->ContactMesh.Get()!=Asset)
        {
            RetailRuntime->ContactMesh=Asset; RetailRuntime->ContactVertices.Reset();
            const FSkeletalMeshRenderData* Data=Asset->GetResourceForRendering();
            if (Data && !Data->LODRenderData.IsEmpty())
            {
                const FSkeletalMeshLODRenderData& LOD=Data->LODRenderData[0];
                const auto& Positions=LOD.StaticVertexBuffers.PositionVertexBuffer;
                const FSkinWeightVertexBuffer* Weights=LOD.GetSkinWeightVertexBuffer();
                if (Positions.GetVertexData() && Weights && Weights->GetDataVertexBuffer()->GetWeightData())
                    for (const FSkelMeshRenderSection& Section : LOD.RenderSections)
                    {
                        const TConstArrayView<FBoneIndexType> Bones=Section.HasUnifiedBoneMap()?LOD.GetUnifiedBoneMap():MakeArrayView(Section.BoneMap);
                        for (uint32 V=Section.BaseVertexIndex;V<Section.BaseVertexIndex+Section.NumVertices;++V)
                        {
                            FSkateRuntime::Vertex Vertex; float Sum=0;
                            for (uint32 K=0;K<Weights->GetMaxBoneInfluences();++K)
                            {
                                const float Weight=Weights->GetBoneWeight(V,K)/65535.f;
                                if (Weight<=0) continue;
                                const uint32 LocalBone=Weights->GetBoneIndex(V,K);
                                if (!Bones.IsValidIndex(LocalBone) || !Bind.IsValidIndex(Bones[LocalBone])) continue;
                                const int32 Bone=Bones[LocalBone];
                                Vertex.Influences.Add({Bone,Bind[Bone].InverseTransformPosition(FVector(Positions.VertexPosition(V))),Weight}); Sum+=Weight;
                            }
                            if (Sum>0)
                            {
                                for (auto& Influence : Vertex.Influences) Influence.Weight/=Sum;
                                RetailRuntime->ContactVertices.Add(MoveTemp(Vertex));
                            }
                        }
                    }
            }
        }
        // Keep the lowest skinned vertex in each 12cm footprint cell. This includes shoes, hands, hair
        // and the enlarged head, and bounds the scene-query count without a coarse whole-body hover box.
        TMap<FIntPoint,FVector> Support;
        for (const auto& Vertex : RetailRuntime->ContactVertices)
        {
            FVector Point=FVector::ZeroVector;
            for (const auto& I : Vertex.Influences) Point+=Output[I.Bone].TransformPosition(I.Position)*I.Weight;
            Point=MeshWorld.TransformPosition(Point);
            const FIntPoint Cell(FMath::FloorToInt(Point.X/12.),FMath::FloorToInt(Point.Y/12.));
            FVector* Existing=Support.Find(Cell);
            if (!Existing) Support.Add(Cell,Point);
            else if (Point.Z<Existing->Z) *Existing=Point;
        }
        double Clearance=MAX_dbl;
        FCollisionQueryParams Query(SCENE_QUERY_STAT(SkateBailSkin),true,Rider);
        for (const auto& Sample : Support)
        {
            const FVector Point=Sample.Value; FHitResult Hit;
            if (GetWorld()->LineTraceSingleByChannel(Hit,Point+FVector(0,0,200),Point-FVector(0,0,200),ECC_Pawn,Query) && Hit.ImpactNormal.Z>.25)
                Clearance=FMath::Min(Clearance,Point.Z-Hit.ImpactPoint.Z);
        }
        if (Clearance!=MAX_dbl)
        {
            const float Required=FMath::Max(0.,.5-Clearance);
            BailVisualLift=FMath::Max(Required,FMath::FInterpTo(BailVisualLift,Required,GetWorld()->GetDeltaSeconds(),14.f));
            RetailFloorClearance=Clearance+BailVisualLift;
        }
        const FVector Lift=MeshWorld.InverseTransformVector(FVector(0,0,BailVisualLift));
        for (FTransform& Bone : Output) Bone.AddToTranslation(Lift);
    }
    else BailVisualLift=0.f;
    for (int32 I=0;I<Ref.GetNum();++I)
    {
        const int32 Parent=Ref.GetParentIndex(I);
        RetailPose[I]=Parent>=0?Output[I].GetRelativeTransform(Output[Parent]):Output[I];
        RetailPose[I].NormalizeRotation();
    }
    // A blend asked for this pose (the ride's first after a mount) goes with it (RequestPoseBlendWithNextPose).
    if (PendingPoseBlend>0.f) RequestPoseBlend(PendingPoseBlend);
}
