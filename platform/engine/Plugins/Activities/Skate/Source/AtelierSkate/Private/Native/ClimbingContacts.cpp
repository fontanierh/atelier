// SPDX-License-Identifier: Apache-2.0
#include "ClimbingContacts.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace climbing_math;
bool RotateBone(const ClimbingClip& c,std::vector<Transform>& locals,const std::vector<Mat4>& globals,std::size_t bone,Vec3 from,Vec3 to,std::string& error){
  const auto delta=RotationArc(Normalize(from),Normalize(to));const auto parent=c.parents[bone];
  if(parent<0||std::size_t(parent)>=globals.size()){
    error="Climbing arm parent is outside the hierarchy (source index assertion)";return false;
  }
  locals[bone].rotation=NormalizeQuat(MultiplyQuat(MultiplyQuat(InverseQuat(Transform::FromMatrix(globals[std::size_t(parent)]).rotation),delta),Transform::FromMatrix(globals[bone]).rotation));
  return true;
}
bool Solve(const ClimbingClip& c,std::vector<Transform>& locals,std::size_t upper,std::size_t lower,std::size_t hand,Vec3 target,Quat wrist,std::string& error){
  auto g=c.Globals(locals);const auto a=Translation(g[upper]),b=Translation(g[lower]),position=Translation(g[hand]);const auto l1=Distance(a,b),l2=Distance(b,position);
  const auto dir=TryNormalize(Sub(target,a));if(!dir)return true;
  const auto minimum=std::fabs(l1-l2)+.0001f,maximum=l1+l2-.0001f;
  if(!(minimum<=maximum)){
    error="Climbing limb clamp range is invalid (source clamp assertion)";return false;
  }
  auto distance=Distance(a,target);if(distance<minimum)distance=minimum;if(distance>maximum)distance=maximum;
  const auto along=(l1*l1-l2*l2+distance*distance)/(2.0f*distance);
  const auto bend=Sub(Sub(b,a),ScaleVector(*dir,Dot(Sub(b,a),*dir)));
  const auto normalized=TryNormalize(bend);const auto pole=normalized?*normalized:Orthonormal(*dir);
  const auto elbow=Add(Add(a,ScaleVector(*dir,along)),ScaleVector(pole,std::sqrt(std::fmax(l1*l1-along*along,0.0f))));
  if(!RotateBone(c,locals,g,upper,Sub(b,a),Sub(elbow,a),error))return false;
  g=c.Globals(locals);const auto lower_position=Translation(g[lower]);
  if(!RotateBone(c,locals,g,lower,Sub(Translation(g[hand]),lower_position),Sub(Add(a,ScaleVector(*dir,distance)),lower_position),error))return false;
  g=c.Globals(locals);const auto relative=MultiplyQuat(InverseQuat(Transform::FromMatrix(g[lower]).rotation),wrist);
  const auto axis=Normalize(locals[hand].translation);const auto projected=ScaleVector(axis,Dot({relative[0],relative[1],relative[2]},axis));
  const Quat raw{projected.x,projected.y,projected.z,relative[3]};
  // Source raw_twist.length_squared() uses the neon horizontal dot.
  const auto square=(raw[0]*raw[0]+raw[1]*raw[1])+(raw[2]*raw[2]+raw[3]*raw[3]);
  const auto actual_twist=square>1e-8f?NormalizeQuat(raw):Quat{0,0,0,1};
  locals[lower].rotation=NormalizeQuat(MultiplyQuat(locals[lower].rotation,actual_twist));
  locals[hand].rotation=NormalizeQuat(MultiplyQuat(InverseQuat(actual_twist),relative));
  return true;
}
}
Vec3 ClimbingContactClearance(const ClimbingClip& c,const std::vector<Mat4>& globals){
  using namespace climbing_math;const auto hands=c.Hands(globals),hips=Translation(globals[c.Index("HIPS")]);const auto back=std::fmax(hips.z-hands.z+.24f,0.0f);return {0,back*.53f,-back};
}
std::pair<Vec3,Quat> ClimbingWrist(ClimbingLedge ledge,std::size_t i){
  using namespace climbing_math;const auto normal=ledge.normals[i];const auto forward=Normalize(Sub(ledge.forward,ScaleVector(normal,Dot(ledge.forward,normal))));const auto down=ScaleVector(normal,-1);const auto rotation=RotationAxes(forward,down,Cross(forward,down));return {Sub(ledge.palms[i],Rotate(rotation,{.075f,.052f,0})),rotation};
}
bool ApplyClimbingHands(const ClimbingClip& c,std::vector<climbing_math::Transform>& locals,const Mat4& root,ClimbingLedge ledge,float weight,std::string& error){
  using namespace climbing_math;const auto globals=c.Globals(locals);const auto inverse=Inverse(root);const auto root_rotation=Transform::FromMatrix(root).rotation;
  const char* sides[]={"LEFT","RIGHT"};
  for(unsigned i=0;i<2;++i){const std::string side=sides[i];const auto upper=c.Index(side+"ARM"),lower=c.Index(side+"FOREARM"),hand=c.Index(side+"HAND");const auto wrist=ClimbingWrist(ledge,i);const auto target=Lerp(Translation(globals[hand]),Point(inverse,wrist.first),weight);const auto rotation=Slerp(Transform::FromMatrix(globals[hand]).rotation,MultiplyQuat(InverseQuat(root_rotation),wrist.second),weight);if(!Solve(c,locals,upper,lower,hand,target,rotation,error))return false;}
  error.clear();return true;
}
} // namespace atelier::skate
