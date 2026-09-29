#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"
/** Seated helm pose: hips/feet supported by boat, articulated overhand tiller grip. */
struct FSailboatStanceNode final : public FAnimNode_SkeletalControlBase
{
 enum{Pelvis,Spine,Chest,Neck,Head,UpperL,ForeL,HandL,UpperR,ForeR,HandR,ThighL,ShinL,FootL,ThighR,ShinR,FootR,Finger0,Tip0,Finger1,Tip1,Finger2,Tip2,Finger3,Tip3,Thumb,Count};
 FBoneReference Bones[Count];
 FVector PelvisTarget,HandTarget[2],ElbowPole[2],FootTarget[2],KneePole[2];
 FVector GripAxis=FVector::ForwardVector,GripUp=FVector::UpVector,GripForward=FVector::RightVector;
 FSailboatStanceNode()
 {
  const TCHAR* Names[]={TEXT("pelvis"),TEXT("spine"),TEXT("chest"),TEXT("neck"),TEXT("head"),TEXT("upperarm_L"),TEXT("forearm_L"),TEXT("hand_L"),TEXT("upperarm_R"),TEXT("forearm_R"),TEXT("hand_R"),TEXT("thigh_L"),TEXT("shin_L"),TEXT("foot_L"),TEXT("thigh_R"),TEXT("shin_R"),TEXT("foot_R"),TEXT("finger_0_R"),TEXT("finger_tip_0_R"),TEXT("finger_1_R"),TEXT("finger_tip_1_R"),TEXT("finger_2_R"),TEXT("finger_tip_2_R"),TEXT("finger_3_R"),TEXT("finger_tip_3_R"),TEXT("thumb_R")};
  for(int I=0;I<Count;++I)Bones[I].BoneName=Names[I];
 }
 virtual void InitializeBoneReferences(const FBoneContainer& C) override{for(auto& B:Bones)B.Initialize(C);}
 virtual bool IsValidToEvaluate(const USkeleton*,const FBoneContainer& C) override{for(const auto& B:Bones)if(!B.IsValidToEvaluate(C))return false;return true;}
 virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output,TArray<FBoneTransform>& Result) override
 {
  const auto& C=Output.Pose.GetPose().GetBoneContainer();FCompactPoseBoneIndex Indices[Count];FTransform P[Count];
  for(int I=0;I<Count;++I){Indices[I]=Bones[I].GetCompactPoseIndex(C);P[I]=Output.Pose.GetComponentSpaceTransform(Indices[I]);}
  const FVector Shift=PelvisTarget-P[Pelvis].GetLocation();for(auto& T:P)T.AddToTranslation(Shift);
  const FTransform OldHand=P[HandR];
  // Derive the imported hand's anatomical axes from its knuckles, not assumed FBX bone axes.
  FVector Knuckles=FVector::ZeroVector;for(int I=0;I<4;++I)Knuckles+=P[Finger0+2*I].GetLocation();Knuckles*=.25;
  const FVector OldForward=(Knuckles-OldHand.GetLocation()).GetSafeNormal();
  const FVector OldSpan=(P[Finger3].GetLocation()-P[Finger0].GetLocation()).GetSafeNormal();
  const FQuat First=FQuat::FindBetweenNormals(OldForward,GripForward);
  const FVector Span=FVector::VectorPlaneProject(First.RotateVector(OldSpan),GripForward).GetSafeNormal();
  const FVector WantSpan=FVector::VectorPlaneProject(GripAxis,GripForward).GetSafeNormal();
  const FQuat Align=FQuat::FindBetweenNormals(Span,WantSpan)*First;
  const FQuat HandRotation=Align*OldHand.GetRotation();
  // The handle is 3.2cm thick: palm above its top, fingertips wrap around its outer face.
  const FVector DesiredKnuckles=HandTarget[1]+GripForward*1.2f+GripUp*2.8f;
  const FVector Wrist=DesiredKnuckles-Align.RotateVector(Knuckles-OldHand.GetLocation());
  for(int Side=0;Side<2;++Side)
  {
   int U=Side?ThighR:ThighL;const FQuat FootRotation=P[U+2].GetRotation();
   AnimationCore::SolveTwoBoneIK(P[U],P[U+1],P[U+2],KneePole[Side],FootTarget[Side],false,1.,1.);P[U+2].SetRotation(FootRotation);
   U=Side?UpperR:UpperL;AnimationCore::SolveTwoBoneIK(P[U],P[U+1],P[U+2],ElbowPole[Side],Side?Wrist:HandTarget[Side],false,1.,1.);
  }
  P[HandR].SetRotation(HandRotation);
  const FTransform NewHand=P[HandR];
  for(int I=0;I<4;++I)
  {
   const int F=Finger0+I*2,T=F+1;
   const FTransform OriginalFinger=P[F],OriginalTip=P[T];
   const FVector BoneDirection=(OriginalTip.GetLocation()-OriginalFinger.GetLocation()).GetSafeNormal();
   const FVector BoneLocalAxis=OriginalFinger.GetRotation().UnrotateVector(BoneDirection);
   const float Length=FVector::Distance(OriginalTip.GetLocation(),OriginalFinger.GetLocation());
   P[F]=OriginalFinger.GetRelativeTransform(OldHand)*NewHand;
   const FVector Across=(GripForward*.43f-GripUp*.90f).GetSafeNormal();
   const FVector Under=(-GripForward*.70f-GripUp*.71f).GetSafeNormal();
   const FVector Tip=P[F].GetLocation()+Across*Length;
   P[F].SetRotation(FQuat::FindBetweenNormals(P[F].GetRotation().RotateVector(BoneLocalAxis),Across)*P[F].GetRotation());
   P[T]=OriginalTip.GetRelativeTransform(OldHand)*NewHand;
   P[T].SetLocation(Tip);
   P[T].SetRotation(FQuat::FindBetweenNormals(P[T].GetRotation().RotateVector(BoneLocalAxis),Under)*P[T].GetRotation());
  }
  // Opposing thumb approaches the inner side of the grip, rather than hanging with the fingers.
  const FVector ThumbAxis=P[Finger0].GetRotation().UnrotateVector((GripForward*.43f-GripUp*.90f).GetSafeNormal());
  P[Thumb]=P[Thumb].GetRelativeTransform(OldHand)*NewHand;
  const FVector ThumbToward=(HandTarget[1]-GripForward*1.8f-GripUp*.8f-P[Thumb].GetLocation()).GetSafeNormal();
  P[Thumb].SetRotation(FQuat::FindBetweenNormals(P[Thumb].GetRotation().RotateVector(ThumbAxis),ThumbToward)*P[Thumb].GetRotation());
  for(int I=0;I<Count;++I)Result.Emplace(Indices[I],P[I]);Result.Sort(FCompareBoneTransformIndex());
 }
};
