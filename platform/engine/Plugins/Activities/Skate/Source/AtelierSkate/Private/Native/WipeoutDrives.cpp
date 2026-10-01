// SPDX-License-Identifier: Apache-2.0
#include "WipeoutDrives.h"
#include "StockSettingsReader.h"
#include "WipeoutPhysicalMath.h"
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
using namespace wipeout_physical_math;
bool WipeoutDriveSettings::Load(const SettingsDatabase& data,const PhysicsSkeleton& skeleton,WipeoutDriveSettings& output,std::string& e)
{
    if(skeleton.bones.size()!=24){e="Wipeout requires the actual24 physical skeleton parts";return false;}
    StockSettingsReader r(data);WipeoutDriveSettings s{};std::vector<std::uint32_t> words;
    for(std::size_t part=1;part<24;++part){if(!r.Words("physics_skeleton_drives","default","PART_"+skeleton.bones[part].name,9,words,e))return false;for(unsigned i=0;i<5;++i)s.bone[part][i]=Word(words[i]);}
    const char* roots[]={"root_drive_start_scalar","root_drive_scalar","root_drive_controlled_scalar","root_drive_end_scalar"};
    for(unsigned i=0;i<4;++i)if(!r.Float("physics_skeleton_drives","default",roots[i],s.root[i],e))return false;
    if(!r.Float("animation","default","DriveStrengthLocal",s.strength[0],e)||!r.Float("animation","default","DriveStrengthRootLocal",s.strength[1],e)
        ||!r.Float("physics_animation","default","HookSoftDsp",s.hook_spring,e)||!r.Float("physics_animation","default","HookSoftStr",s.hook_strength,e)
        ||!r.Float("physics_animation","default","HookSoftDmp",s.hook_damping,e))return false;
    output=s;return true;
}
bool UpdateWipeoutDrives(SkeletonDrives& drives,const std::array<Mat4,24>& pose,const WipeoutDriveSettings& s,WipeoutDriveWeights w,float& output,std::string& error)
{
    std::array<Mat4,24> inverses;inverses.fill(SkeletonIdentity);
    for(std::size_t part=1;part<24;++part)inverses[part]=InverseAffine(pose[part]);
    const float residual=((1.0f-w.start)-w.end)-w.controlled;
    for(std::size_t part=1;part<23;++part){
        if(!drives.bones[part]){error="Original22 bone drives exist";return false;}
        auto& bone=*drives.bones[part];const auto c=s.bone[part];const bool upper=part>=3&&part<=10,lower=part>=15&&part<=22;
        std::array<float,2> strengths;
        if((upper&&w.upper_extra>0)||(lower&&w.lower_extra>0)){
            bone.dynamics.mode=5;const float extra=upper?w.upper_extra:w.lower_extra,value=extra*c[4];strengths={value*s.strength[0],value*s.strength[1]};
        }else{
            bone.dynamics.mode=4;
            const float local=std::fma(c[2],w.controlled,std::fma(c[0],w.start,std::fma(c[1],residual,c[3]*w.end)));
            const float root_start=s.root[0]*c[0],root_normal=s.root[1]*c[1],root_controlled=s.root[2]*c[2],root_end=s.root[3]*c[3];
            const float root=std::fma(root_controlled,w.controlled,std::fma(root_start,w.start,std::fma(root_end,w.end,root_normal*residual)));
            strengths={local*s.strength[0],root*s.strength[1]};
        }
        bone.dynamics.strengths=strengths;
        for(unsigned channel=0;channel<2;++channel)if(bone.active[channel]){
            if(bone.parent[channel]>=24){error="Wipeout bone drive parent is outside the original24 parts";return false;}
            bone.frames[channel]=BoneDriveFrames(pose[part],inverses[part],inverses[bone.parent[channel]]);
            bone.dynamics.Enable(channel,strengths[channel],drives.settings.bone);
        }
    }
    output=residual;return true;
}
namespace {float Weight(float v){const float lower=-v>=0?0:v;return 1.0f-lower>=0?lower:1.0f;}}
void SetWipeoutLinearRoot(SkeletonDrives& drives,const WipeoutDriveSettings& s,float weight)
{
    weight=Weight(weight);const float spring=s.hook_spring,root=spring==0?0:spring*InverseLengthSquared(spring,2);
    drives.targets.dynamics[0].linear={spring*weight,root*2.0f-spring*Word(0x3c83126f),(s.hook_strength*weight)*Word(0x4560fffe),DriveType::Soft};
}
void SetWipeoutAngularRoot(SkeletonDrives& drives,const WipeoutDriveSettings& s,float weight)
{
    weight=Weight(weight);drives.targets.dynamics[0].angular={s.hook_spring*weight,s.hook_damping,(s.hook_strength*weight)*Word(0x4560fffe),DriveType::Soft};
}
}
