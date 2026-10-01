// SPDX-License-Identifier: Apache-2.0
#include "WipeoutRagdoll.h"
#include "StockSettingsReader.h"
#include "WipeoutPhysicalMath.h"
#include <algorithm>
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
namespace
{
std::array<std::uint32_t,4> Limits(float swing,float twist)
{
    swing=swing-0.01f>=0?swing:0.01f;twist=twist-0.01f>=0?twist:0.01f;
    const Vec4 values{swing,twist,Cos(swing),Cos(twist)};std::array<std::uint32_t,4> words;std::memcpy(words.data(),values.data(),16);return words;
}
}
bool WipeoutRagdollSettings::Load(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,WipeoutRagdollSettings& output,std::string& e)
{
    if(skeleton.bones.size()!=24){e="Ragdoll requires24 physical bones";return false;}
    const char* names[]={"JOINT_NECK_NECK1","JOINT_SPINE3_NECK","JOINT_LEFT_FOREARM_HAND","JOINT_LEFT_ARM_FOREARM","JOINT_LEFT_SHOULDER_ARM","JOINT_SPINE3_LEFT_SHOULDER",
        "JOINT_RIGHT_FOREARM_HAND","JOINT_RIGHT_ARM_FOREARM","JOINT_RIGHT_SHOULDER_ARM","JOINT_SPINE3_RIGHT_SHOULDER","JOINT_SPINE2_SPINE3","JOINT_SPINE1_SPINE2","JOINT_SPINE_SPINE1","JOINT_HIPS_SPINE",
        "JOINT_LEFT_FOOT_TOE_BASE","JOINT_LEFT_LEG_FOOT","JOINT_LEFT_UPLEG_LEG","JOINT_HIPS_LEFT_LEG","JOINT_RIGHT_FOOT_TOE_BASE","JOINT_RIGHT_LEG_FOOT","JOINT_RIGHT_UPLEG_LEG","JOINT_HIPS_RIGHT_LEG"};
    StockSettingsReader r(data);WipeoutRagdollSettings s;float swing,twist;
    if(!r.Float("physics_skeleton_joints","default","SwingRagdollScalar",swing,e)||!r.Float("physics_skeleton_joints","default","TwistRagdollScalar",twist,e))return false;
    std::vector<std::uint32_t> words;
    for(unsigned i=0;i<22;++i){
        if(!r.Words("physics_skeleton_joints","default",names[i],5,words,e))return false;
        const float bone_s=Word(skeleton.bones[i+1].words[21]),bone_t=Word(skeleton.bones[i+1].words[20]);
        s.normal_limits[i]=Limits(bone_s*Word(words[1]),bone_t*Word(words[2]));s.ragdoll_limits[i]=Limits((bone_s*Word(words[3]))*swing,(bone_t*Word(words[4]))*twist);
    }
    if(!r.Boolean("physics_wipeout","default","DoInverseMass",s.inverse_mass,e)||!r.Boolean("physics_wipeout","default","DoInverseInertia",s.inverse_inertia,e)
        ||!r.Float("physics_wipeout","default","LinearDrag",s.drag[0],e)||!r.Float("physics_wipeout","default","AngularDrag",s.drag[1],e))return false;
    s.drag[0]*=Word(0x426fffff);s.drag[1]*=Word(0x426fffff);
    const char* friction[]={"FrictionRagdoll","FrictionRagdollHead"};const char* restitution[]={"RestitutionRagdoll","RestitutionRagdollHead"};
    for(unsigned i=0;i<2;++i){auto& m=s.materials[i];if(!r.Float("physics_skeleton","default",friction[i],m.static_friction,e))return false;m.dynamic_friction=m.static_friction;if(!r.Float("physics_skeleton","default",restitution[i],m.restitution,e))return false;}
    output=s;return true;
}
bool WipeoutRagdollSetup::Load(const SettingsDatabase& d,const PhysicsSkeleton& s,std::string& e){return WipeoutRagdollSettings::Load(d,s,settings,e);}
bool WipeoutRagdollSetup::Request(SkeletonControllerState& controller,std::uint32_t requested,SkeletonBody& body,SkeletonJoints& joints,SkeletonCollisionMode& collision,std::string& error) const
{
    const auto mode=controller.SelectRequest(requested);if(!mode)return true;
    if(*mode<7||*mode>10)return collision.SelectDriven(*mode,error);
    const auto& limits=*mode==10?settings.normal_limits:settings.ragdoll_limits;
    for(std::size_t i=0;i<joints.records.size();++i)std::copy(limits[i].begin(),limits[i].end(),joints.records[i].parameters.begin()+10);
    collision.ApplyRagdollProperties(body,settings.inverse_mass,settings.inverse_inertia,settings.drag,settings.materials);collision.FinishRagdollRequest(*mode);return true;
}
void WipeoutRagdollSetup::RestoreNormal(SkeletonBody& body,SkeletonJoints& joints,SkeletonCollisionMode& collision,SkeletonCollisionFeedback& feedback) const
{
    for(std::size_t i=0;i<joints.records.size();++i)std::copy(settings.normal_limits[i].begin(),settings.normal_limits[i].end(),joints.records[i].parameters.begin()+10);
    feedback.SetUpNormal();collision.RestoreNormalProperties(body);
}
}
