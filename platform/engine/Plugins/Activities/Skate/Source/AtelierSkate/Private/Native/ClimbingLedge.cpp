// SPDX-License-Identifier: Apache-2.0
#include "ClimbingLedge.h"
#include <cmath>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
using namespace climbing_math;
std::optional<std::array<Vec3,2>> Hit(const WorldGeometry& world,Vec3 a,Vec3 b,float radius){
  const auto result=world.QuerySweptLine(a,b,radius);
  // The original .ok()?? intentionally treats query errors as no contact.
  if(result.error||!result.hit)return std::nullopt;
  return std::array<Vec3,2>{result.hit->geometry.position,result.hit->geometry.normal};
}
std::optional<ClimbingLedge> FindRange(const WorldGeometry& world,Vec3 feet,Vec3 facing,float minimum,float distance){
  const auto normalized=TryNormalize({facing.x,0,facing.z});if(!normalized)return std::nullopt;facing=*normalized;
  const auto chest=Add(feet,ScaleVector(Up,1.15f));const auto wall_hit=Hit(world,chest,Add(chest,ScaleVector(facing,distance)),0);if(!wall_hit)return std::nullopt;
  const auto wall=(*wall_hit)[0],normal=(*wall_hit)[1];if(std::fabs(normal.y)>.2f||Dot(normal,facing)>-.65f)return std::nullopt;
  const auto forward=ScaleVector(Normalize({normal.x,0,normal.z}),-1);const auto right=Cross(Up,forward);const auto probe=Add(wall,ScaleVector(forward,.12f));
  const auto top_hit=Hit(world,{probe.x,feet.y+2.75f,probe.z},{probe.x,feet.y+minimum,probe.z},0);if(!top_hit)return std::nullopt;
  const auto top=(*top_hit)[0],up=(*top_hit)[1];if(up.y<.95f)return std::nullopt;
  const auto anchor=Add(Vec3{wall.x,top.y+.025f,wall.z},ScaleVector(forward,.055f));
  std::array<Vec3,2> palms{{Vec3{},Vec3{}}},normals{{Up,Up}};
  constexpr float sides[]={.30f,-.30f};
  for(unsigned i=0;i<2;++i){const auto p=Add(Add(wall,ScaleVector(forward,.08f)),ScaleVector(right,sides[i]));const auto h=Hit(world,{p.x,top.y+.15f,p.z},{p.x,top.y-.15f,p.z},0);if(!h)return std::nullopt;
    const auto point=(*h)[0],n=(*h)[1];palms[i]=Add(point,ScaleVector(n,.005f));normals[i]=n;if(std::fabs(point.y-top.y)>.06f||n.y<.95f)return std::nullopt;
  }
  const ClimbingLedge ledge{anchor,Add(Vec3{wall.x,top.y+.015f,wall.z},ScaleVector(forward,.62f)),forward,palms,normals};
  if(!ClearClimbingLedge(world,ledge))return std::nullopt;
  const auto outside=Sub(anchor,ScaleVector(forward,.32f));
  if(Hit(world,Sub(outside,ScaleVector(Up,1.25f)),Add(outside,ScaleVector(Up,.55f)),.20f))return std::nullopt;
  return ledge;
}
}
std::optional<ClimbingLedge> FindClimbingLedge(const WorldGeometry& world,Vec3 feet,Vec3 facing){return FindRange(world,feet,facing,1.90f,.95f);}
std::optional<ClimbingLedge> FindAirClimbingLedge(const WorldGeometry& world,Vec3 feet,Vec3 facing){return FindRange(world,feet,facing,1.25f,2.6f);}
bool ClearClimbingLedge(const WorldGeometry& world,ClimbingLedge ledge){
  using namespace climbing_math;
  const auto right=Cross(Up,ledge.forward);
  const std::array<Vec3,5> offsets{Vec3{},ScaleVector(right,.25f),ScaleVector(right,-.25f),ScaleVector(ledge.forward,.25f),ScaleVector(ledge.forward,-.25f)};
  for(auto offset:offsets){const auto p=Add(ledge.landing,offset);const auto h=Hit(world,Add(p,ScaleVector(Up,.15f)),Sub(p,ScaleVector(Up,.15f)),0);
    if(!h)return false;const auto ground=(*h)[0],normal=(*h)[1];if(std::fabs(ground.y-ledge.landing.y)>.06f||normal.y<.95f)return false;
    if(Hit(world,Add(p,ScaleVector(Up,.35f)),Add(p,ScaleVector(Up,1.55f)),.28f))return false;
  }
  return !Hit(world,Sub(Add(ledge.anchor,ScaleVector(Up,.65f)),ScaleVector(ledge.forward,.32f)),Add(ledge.landing,ScaleVector(Up,.65f)),.22f);
}
} // namespace atelier::skate
