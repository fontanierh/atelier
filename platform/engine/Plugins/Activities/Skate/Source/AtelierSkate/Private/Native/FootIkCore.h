// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "FootIkTypes.h"
#include "SkeletonBody.h"
namespace atelier::skate::foot_ik
{
void UpdateModes(std::array<LimbStatus,4>&,bool,std::uint32_t);
void UpdateBlends(std::array<LimbStatus,4>&,float,float,std::uint32_t,const BlendSettings&);
void PrepareAnimationTarget(LimbStatus&,LimbFrames&,LimbBinding,const std::array<Mat4,24>&,const Mat4&,const Mat4&,Vec4);
void UpdateExternal(ExternalTarget&,LimbStatus&,LimbFrames&,LimbBinding,const std::array<Mat4,24>&,const Mat4&,const Mat4&);
void BlendFrames(const std::array<LimbStatus,4>&,std::array<LimbFrames,4>&,const std::array<LimbBinding,4>&,const Mat4&,const Mat4&,const Mat4&);
void UpdateContacts(ContactState&,const std::array<LimbStatus,4>&,std::array<LimbFrames,4>&,const UpdateInput&);
SolveResult SolveTwoBone(Vec4,Vec4,Vec4,Vec4&,Vec4&,AngleLimits,bool,std::uint32_t);
std::optional<Mat4> LineMapping(Vec4,Vec4,Vec4,Vec4,Vec4,Vec4);
Vec4 NormalizeSafe(Vec4);
std::array<bool,4> UpdateDrives(const std::array<LimbStatus,4>&,std::array<LimbFrames,4>&,const std::array<LimbBinding,4>&,const Geometry&,const std::array<Mat4,24>&,std::array<Mat4,24>&,const Mat4&,AngleLimits);
std::array<bool,4> Update(State&,const UpdateInput&,const Geometry&,const Settings&,std::array<Mat4,24>&);
std::optional<Vec4> PostContactTarget(const Mat4&,Vec4,Vec4,Vec4,bool,const Settings&,const PostSettings&);
bool SolvePhysical(SkeletonBody&,const Geometry&,std::size_t,Vec4);
std::array<bool,4> PostPhysics(State&,SkeletonBody&,const Geometry&,const Settings&,const PostSettings&,const PostInput&);
}
