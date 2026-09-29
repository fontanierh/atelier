#pragma once

#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"

// Component-space terrain adaptation. Preserve the authored swing clearance;
// only support height and sole orientation change. Never used on the skateboard.
struct FGroundContactNode final : public FAnimNode_SkeletalControlBase
{
    FBoneReference Bones[7];
    FVector Point[2], Normal[2];
    bool Valid[2] = {false,false};
    FVector Forward = FVector::ForwardVector;
    float DeltaSeconds = 0.f, Drop = 0.f;
    FVector Correction[2] = {FVector::ZeroVector,FVector::ZeroVector};
    FQuat Tilt[2] = {FQuat::Identity,FQuat::Identity};
    FVector2D RestAnkle = FVector2D(11.2,11.2);
    double Sole = .65;
    FGroundContactNode()
    {
        const TCHAR* Names[]={TEXT("pelvis"),TEXT("thigh_L"),TEXT("shin_L"),TEXT("foot_L"),
                              TEXT("thigh_R"),TEXT("shin_R"),TEXT("foot_R")};
        for(int32 I=0;I<7;++I)Bones[I].BoneName=Names[I];
    }
    void Reset()
    {
        Drop=0.f;
        for(int32 I=0;I<2;++I){Correction[I]=FVector::ZeroVector;Tilt[I]=FQuat::Identity;Valid[I]=false;}
    }
    virtual void InitializeBoneReferences(const FBoneContainer& RequiredBones) override
    {for(auto& Bone:Bones)Bone.Initialize(RequiredBones);Reset();}
    virtual bool IsValidToEvaluate(const USkeleton*,const FBoneContainer& RequiredBones) override
    {for(const auto& Bone:Bones)if(!Bone.IsValidToEvaluate(RequiredBones))return false;return true;}
    virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output,TArray<FBoneTransform>& Result) override
    {
        const auto& Required=Output.Pose.GetPose().GetBoneContainer();
        FCompactPoseBoneIndex Indices[7];FTransform Pose[7];FVector Targets[2];
        for(int32 I=0;I<7;++I){Indices[I]=Bones[I].GetCompactPoseIndex(Required);Pose[I]=Output.Pose.GetComponentSpaceTransform(Indices[I]);}
        double RequiredDrop=0.;
        for(int32 Side=0;Side<2;++Side)
        {
            const int32 H=1+Side*3;
            const FVector Ankle=Pose[H+2].GetLocation();
            FVector Offset=FVector::ZeroVector;FQuat Rotation=FQuat::Identity;
            if(Valid[Side] && Normal[Side].Z>.65)
            {
                const FVector N=Normal[Side];
                // Evaluate the sampled ground plane at the current authored foot,
                // avoiding feedback from last frame's already-corrected height.
                FVector Surface(Ankle.X,Ankle.Y,Point[Side].Z-
                    (N.X*(Ankle.X-Point[Side].X)+N.Y*(Ankle.Y-Point[Side].Y))/N.Z);
                const double Lift=FMath::Max(0.,Ankle.Z-RestAnkle[Side]);
                FVector Target=Surface+N*(RestAnkle[Side]-Sole)+FVector(0,0,Lift);
                Offset=Target-Ankle;
                Offset.Z=FMath::Clamp(Offset.Z,-20.,20.);
                const double Plant=1.-FMath::Clamp(Lift/8.,0.,1.);
                Rotation=FQuat::Slerp(FQuat::Identity,FQuat::FindBetweenNormals(FVector::UpVector,N),Plant);
            }
            Correction[Side]=FMath::VInterpTo(Correction[Side],Offset,DeltaSeconds,18.f);
            Tilt[Side]=FQuat::Slerp(Tilt[Side],Rotation,FMath::Clamp(DeltaSeconds*18.f,0.f,1.f)).GetNormalized();
            Targets[Side]=Ankle+Correction[Side];
            // Keep the torso upright and lower the pelvis to the lower support.
            RequiredDrop=FMath::Max(RequiredDrop,-Correction[Side].Z);
        }
        Drop=FMath::FInterpTo(Drop,float(FMath::Clamp(RequiredDrop,0.,18.)),DeltaSeconds,18.f);
        const FVector PelvisOffset(0,0,-Drop);
        Pose[0].AddToTranslation(PelvisOffset);Result.Emplace(Indices[0],Pose[0]);
        for(int32 Side=0;Side<2;++Side)
        {
            const int32 H=1+Side*3;
            FTransform& Hip=Pose[H];FTransform& Knee=Pose[H+1];FTransform& Foot=Pose[H+2];
            const FQuat FootRotation=Foot.GetRotation();
            const FVector Pole=Knee.GetLocation()+Forward*35.;
            Hip.AddToTranslation(PelvisOffset);Knee.AddToTranslation(PelvisOffset);Foot.AddToTranslation(PelvisOffset);
            AnimationCore::SolveTwoBoneIK(Hip,Knee,Foot,Pole,Targets[Side],false,1.,1.);
            Foot.SetRotation((Tilt[Side]*FootRotation).GetNormalized());
            for(int32 I=H;I<H+3;++I)Result.Emplace(Indices[I],Pose[I]);
        }
        Result.Sort(FCompareBoneTransformIndex());
    }
};
