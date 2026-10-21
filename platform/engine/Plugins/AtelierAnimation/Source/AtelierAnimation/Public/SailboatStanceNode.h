#pragma once
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "TwoBoneIK.h"
/** Seated helm pose: hips/feet supported by the boat, articulated overhand tiller grip. With bGripLeft the left hand
 *  wraps its own target too (a steering wheel held at both sides); otherwise it rests as a plain wrist target. */
struct FSailboatStanceNode final : public FAnimNode_SkeletalControlBase
{
 enum{Pelvis,Spine,Chest,Neck,Head,UpperL,ForeL,HandL,UpperR,ForeR,HandR,ThighL,ShinL,FootL,ToeL,ThighR,ShinR,FootR,ToeR,Finger0,Tip0,Finger1,Tip1,Finger2,Tip2,Finger3,Tip3,Thumb,
      FingerL0,TipL0,FingerL1,TipL1,FingerL2,TipL2,FingerL3,TipL3,ThumbL,Count};
 FBoneReference Bones[Count];
 FVector PelvisTarget,HandTarget[2],ElbowPole[2],FootTarget[2],KneePole[2];
 FVector GripAxis=FVector::UpVector,GripUp=FVector::UpVector,GripForward=FVector::ForwardVector;
 /** The left hand grips too, with these axes (a wheel's rim rather than the tiller). */
 bool bGripLeft=false;
 /** Authored prop grips run later; keep this node responsible only for the seated body. */
 bool bPoseHands=true;
 FVector GripAxisL=FVector::UpVector,GripUpL=FVector::LeftVector,GripForwardL=FVector::ForwardVector;
 /** Degrees the upper body leans back from the pelvis, over a reclined seat (0 keeps the source pose). */
 float TorsoRecline=0.f;
 /** Plant the toes down the pedals instead of keeping each source rig's resting ankle roll. */
 bool bPlantFeet=false;
 FVector FootForward=FVector::ForwardVector;
 FSailboatStanceNode()
 {
  const TCHAR* Names[]={TEXT("pelvis"),TEXT("spine"),TEXT("chest"),TEXT("neck"),TEXT("head"),TEXT("upperarm_L"),TEXT("forearm_L"),TEXT("hand_L"),TEXT("upperarm_R"),TEXT("forearm_R"),TEXT("hand_R"),TEXT("thigh_L"),TEXT("shin_L"),TEXT("foot_L"),TEXT("toe_L"),TEXT("thigh_R"),TEXT("shin_R"),TEXT("foot_R"),TEXT("toe_R"),TEXT("finger_0_R"),TEXT("finger_tip_0_R"),TEXT("finger_1_R"),TEXT("finger_tip_1_R"),TEXT("finger_2_R"),TEXT("finger_tip_2_R"),TEXT("finger_3_R"),TEXT("finger_tip_3_R"),TEXT("thumb_R"),
                        TEXT("finger_0_L"),TEXT("finger_tip_0_L"),TEXT("finger_1_L"),TEXT("finger_tip_1_L"),TEXT("finger_2_L"),TEXT("finger_tip_2_L"),TEXT("finger_3_L"),TEXT("finger_tip_3_L"),TEXT("thumb_L")};
  for(int I=0;I<Count;++I)Bones[I].BoneName=Names[I];
 }
 virtual void InitializeBoneReferences(const FBoneContainer& C) override{for(auto& B:Bones)B.Initialize(C);}
 virtual bool IsValidToEvaluate(const USkeleton*,const FBoneContainer& C) override{for(const auto& B:Bones)if(!B.IsValidToEvaluate(C))return false;return true;}
 virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output,TArray<FBoneTransform>& Result) override
 {
  const auto& C=Output.Pose.GetPose().GetBoneContainer();FCompactPoseBoneIndex Indices[Count];FTransform P[Count];
  for(int I=0;I<Count;++I){Indices[I]=Bones[I].GetCompactPoseIndex(C);P[I]=Output.Pose.GetComponentSpaceTransform(Indices[I]);}
  const FVector Shift=PelvisTarget-P[Pelvis].GetLocation();for(auto& T:P)T.AddToTranslation(Shift);
  if(TorsoRecline!=0.f)
  {
   const FQuat Recline(FVector::RightVector,FMath::DegreesToRadians(-TorsoRecline));
   const FVector Pivot=P[Pelvis].GetLocation();
   for(int I=0;I<Count;++I)
   {
    if(I==Pelvis||(I>=ThighL&&I<=ToeR))continue;
    P[I].SetLocation(Pivot+Recline.RotateVector(P[I].GetLocation()-Pivot));
    P[I].SetRotation(Recline*P[I].GetRotation());
   }
   const FQuat Look(FVector::RightVector,FMath::DegreesToRadians(TorsoRecline*.6f));
   const FVector HeadPivot=P[Neck].GetLocation();
   for(int I: {Neck,Head})
   {
    P[I].SetLocation(HeadPivot+Look.RotateVector(P[I].GetLocation()-HeadPivot));
    P[I].SetRotation(Look*P[I].GetRotation());
   }
  }
  // The rim is about 3.2cm thick: the knuckles sit above its top and the fingertips wrap around its outer face.
  auto grip=[&](int Hand,int Finger,int Upper,int Fore,int Side,const FVector& Target,const FVector& Forward,const FVector& Up,const FVector& Axis)
  {
   const FTransform OldHand=P[Hand];
   const FTransform OldFore=P[Fore];
   // Derive the imported hand's anatomical axes from its knuckles, not assumed FBX bone axes.
   FVector Knuckles=FVector::ZeroVector;for(int I=0;I<4;++I)Knuckles+=P[Finger+2*I].GetLocation();Knuckles*=.25;
   const FVector OldForward=(Knuckles-OldHand.GetLocation()).GetSafeNormal();
   const FVector OldSpan=(P[Finger+6].GetLocation()-P[Finger].GetLocation()).GetSafeNormal();
   const FVector OldPalm=OldSpan.Cross(OldForward).GetSafeNormal();
   const float PalmSign=FVector::DotProduct(P[Finger+8].GetLocation()-OldHand.GetLocation(),OldPalm)>0.f?1.f:-1.f;
   const FVector Palm=OldPalm*PalmSign;
   const FQuat First=FQuat::FindBetweenNormals(OldForward,Forward);
   const FVector Span=FVector::VectorPlaneProject(First.RotateVector(OldSpan),Forward).GetSafeNormal();
   FVector WantSpan=FVector::VectorPlaneProject(Axis,Forward).GetSafeNormal();
   FQuat Align=FQuat::FindBetweenNormals(Span,WantSpan)*First;
   // Keep the palm toward the wheel centre. Rig hand rolls differ; aligning only the knuckle
   // span can leave a mirrored hand showing its back instead of closing round the rim.
   if(bGripLeft && FVector::DotProduct(Align.RotateVector(Palm),-Up)<0.f)
   {
    WantSpan=-WantSpan;
    Align=FQuat::FindBetweenNormals(Span,WantSpan)*First;
   }
   const FQuat HandRotation=Align*OldHand.GetRotation();
   const FVector DesiredKnuckles=Target+Forward*1.2f+Up*2.8f;
   const FVector Wrist=DesiredKnuckles-Align.RotateVector(Knuckles-OldHand.GetLocation());
   AnimationCore::SolveTwoBoneIK(P[Upper],P[Fore],P[Hand],ElbowPole[Side],Wrist,false,1.,1.);
   P[Hand].SetRotation(HandRotation);
   const FQuat RestLocal=OldFore.GetRotation().Inverse()*OldHand.GetRotation();
   const FQuat PoseLocal=P[Fore].GetRotation().Inverse()*P[Hand].GetRotation();
   const FQuat Delta=PoseLocal*RestLocal.Inverse();
   const float Twist=2.f*FMath::Atan2(Delta.X,Delta.W);
   if(bGripLeft && FMath::Abs(Twist)>FMath::DegreesToRadians(5.f))
   {
    const FVector ForeAxis=(P[Hand].GetLocation()-P[Fore].GetLocation()).GetSafeNormal();
    P[Fore].SetRotation(FQuat(ForeAxis,-Twist*.6f)*P[Fore].GetRotation());
    P[Hand].SetRotation(HandRotation);
   }
   const FTransform NewHand=P[Hand];
   for(int I=0;I<4;++I)
   {
    const int F=Finger+I*2,T=F+1;
    const FTransform OriginalFinger=P[F],OriginalTip=P[T];
    const FVector BoneDirection=(OriginalTip.GetLocation()-OriginalFinger.GetLocation()).GetSafeNormal();
    const FVector BoneLocalAxis=OriginalFinger.GetRotation().UnrotateVector(BoneDirection);
    const float Length=FVector::Distance(OriginalTip.GetLocation(),OriginalFinger.GetLocation());
    P[F]=OriginalFinger.GetRelativeTransform(OldHand)*NewHand;
    const FVector Across=(Forward*.43f-Up*.90f).GetSafeNormal();
    const FVector Under=(-Forward*.70f-Up*.71f).GetSafeNormal();
    const FVector Tip=P[F].GetLocation()+Across*Length;
    P[F].SetRotation(FQuat::FindBetweenNormals(P[F].GetRotation().RotateVector(BoneLocalAxis),Across)*P[F].GetRotation());
    P[T]=OriginalTip.GetRelativeTransform(OldHand)*NewHand;
    P[T].SetLocation(Tip);
    P[T].SetRotation(FQuat::FindBetweenNormals(P[T].GetRotation().RotateVector(BoneLocalAxis),Under)*P[T].GetRotation());
   }
   // Opposing thumb approaches the inner side of the grip, rather than hanging with the fingers.
   const int ThumbBone=Finger+8;
   const FVector ThumbAxis=P[Finger].GetRotation().UnrotateVector((Forward*.43f-Up*.90f).GetSafeNormal());
   P[ThumbBone]=P[ThumbBone].GetRelativeTransform(OldHand)*NewHand;
   const FVector ThumbToward=(Target-Forward*1.8f-Up*.8f-P[ThumbBone].GetLocation()).GetSafeNormal();
   P[ThumbBone].SetRotation(FQuat::FindBetweenNormals(P[ThumbBone].GetRotation().RotateVector(ThumbAxis),ThumbToward)*P[ThumbBone].GetRotation());
  };
  if(bPoseHands)grip(HandR,Finger0,UpperR,ForeR,1,HandTarget[1],GripForward,GripUp,GripAxis);
  if(bPoseHands&&bGripLeft)grip(HandL,FingerL0,UpperL,ForeL,0,HandTarget[0],GripForwardL,GripUpL,GripAxisL);
  for(int Side=0;Side<2;++Side)
  {
   const int U=Side?ThighR:ThighL;const FQuat FootRotation=P[U+2].GetRotation();
   const FVector ToeOffset=P[U+3].GetLocation()-P[U+2].GetLocation();
   AnimationCore::SolveTwoBoneIK(P[U],P[U+1],P[U+2],KneePole[Side],FootTarget[Side],false,1.,1.);P[U+2].SetRotation(FootRotation);
   if(bPlantFeet)
   {
    const FVector ToeDir=ToeOffset.GetSafeNormal();
    const FQuat Plant=FQuat::FindBetweenNormals(ToeDir,FootForward.GetSafeNormal());
    P[U+2].SetRotation(Plant*FootRotation);
    P[U+3].SetLocation(P[U+2].GetLocation()+Plant.RotateVector(ToeOffset));
    P[U+3].SetRotation(Plant*P[U+3].GetRotation());
   }
   else
   {
    P[U+3].SetLocation(P[U+2].GetLocation()+ToeOffset);
   }
  }
  if(bPoseHands&&!bGripLeft)AnimationCore::SolveTwoBoneIK(P[UpperL],P[ForeL],P[HandL],ElbowPole[0],HandTarget[0],false,1.,1.);
  // The left fingers only move when the left hand grips its own target. Otherwise leave them out, so the
  // pose keeps the free wrist's own child propagation (the sailing tiller hand).
  for(int I=0;I<Count;++I){if((!bPoseHands&&I>=Finger0)||(!bGripLeft&&I>=FingerL0))continue;Result.Emplace(Indices[I],P[I]);}
  Result.Sort(FCompareBoneTransformIndex());
 }
};
