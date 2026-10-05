#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"
/** Hands kept on handlebars that the game steers past the authored clip. The clip already holds the grips where it was
 *  solved; this moves each gripping hand by the grip's live offset from that authored spot (component space), turns it
 *  with the bars, and re-solves the arm in its own bend plane. Weight per hand follows the clip's contact windows. */
struct FBikeGripNode final : public FAnimNode_SkeletalControlBase
{
 enum{UpperL,ForeL,HandL,UpperR,ForeR,HandR,Count};
 FBoneReference Bones[Count];
 FVector Offset[2]={FVector::ZeroVector,FVector::ZeroVector};
 FQuat Turn[2]={FQuat::Identity,FQuat::Identity};
 float Weight[2]={0.f,0.f};
 FBikeGripNode()
 {
  const TCHAR* Names[]={TEXT("upperarm_L"),TEXT("forearm_L"),TEXT("hand_L"),TEXT("upperarm_R"),TEXT("forearm_R"),TEXT("hand_R")};
  for(int I=0;I<Count;++I)Bones[I].BoneName=Names[I];
 }
 virtual void InitializeBoneReferences(const FBoneContainer& C) override{for(auto& B:Bones)B.Initialize(C);}
 virtual bool IsValidToEvaluate(const USkeleton*,const FBoneContainer& C) override
 {
  if(Weight[0]<=0.f&&Weight[1]<=0.f)return false;
  for(const auto& B:Bones)if(!B.IsValidToEvaluate(C))return false;return true;
 }
 virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output,TArray<FBoneTransform>& Result) override
 {
  const auto& C=Output.Pose.GetPose().GetBoneContainer();FCompactPoseBoneIndex Indices[Count];FTransform P[Count];
  for(int I=0;I<Count;++I){Indices[I]=Bones[I].GetCompactPoseIndex(C);P[I]=Output.Pose.GetComponentSpaceTransform(Indices[I]);}
  for(int Side=0;Side<2;++Side)
  {
   const float W=FMath::Clamp(Weight[Side],0.f,1.f);if(W<=0.f)continue;
   const int U=Side?UpperR:UpperL;
   const FQuat HandRotation=FQuat::Slerp(FQuat::Identity,Turn[Side],W)*P[U+2].GetRotation();
   const FVector Target=P[U+2].GetLocation()+Offset[Side]*W;
   // The authored elbow, pushed out from the shoulder-wrist line, keeps the arm bending the way the clip bends it.
   const FVector Shoulder=P[U].GetLocation(),Elbow=P[U+1].GetLocation();
   const FVector Line=(P[U+2].GetLocation()-Shoulder).GetSafeNormal();
   const FVector Out=FVector::VectorPlaneProject(Elbow-Shoulder,Line).GetSafeNormal();
   AnimationCore::SolveTwoBoneIK(P[U],P[U+1],P[U+2],Elbow+Out*20.f,Target,false,1.,1.);
   P[U+2].SetRotation(HandRotation.GetNormalized());
  }
  for(int I=0;I<Count;++I)Result.Emplace(Indices[I],P[I]);Result.Sort(FCompareBoneTransformIndex());
 }
};
