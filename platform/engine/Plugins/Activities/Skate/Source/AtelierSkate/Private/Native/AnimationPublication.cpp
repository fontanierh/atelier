// SPDX-License-Identifier: Apache-2.0
#include "AnimationPublication.h"
#include <algorithm>
#include <cstring>
namespace atelier::skate
{
namespace
{
void ReplaceFlag(std::uint32_t& flags,unsigned bit,bool value) {flags=(flags&~(std::uint32_t(1)<<bit))|(std::uint32_t(value)<<bit);}
}
bool ResetAnimationPacket(PhysicsPosePacket& packet,AnimationAdditionalResetFields& fields,std::string& error)
{
    const auto count=packet.bone_count<0x80000000?std::size_t(packet.bone_count):0;
    if (packet.hierarchy.size()<count||packet.local.size()<count) {error="RangeOutsideAllocation";return false;}
    const std::uint32_t step=0x3c888889;std::memcpy(&packet.timestep,&step,4);
    fields.external_impulse_active=false;fields.compression=0.5f;fields.foot_ik_influence[0]=0;fields.external_physics_input_active=false;fields.foot_ik_influence[1]=0;fields.externally_controlled=false;fields.truck_tightness=0;
    packet.mirrored=false;packet.riding_switch=false;packet.riding_fakie=false;packet.weight_forwards=false;packet.regular_stance=false;fields.prevent_manual_respawn=false;fields.ignore_respawn_reset_button=0;fields.force_braking=false;packet.air_dismount_revert_frames=0;packet.board_flipped=false;
    fields.next_step_position_valid=false;fields.actor_flag_1904_bit23=false;packet.flags&=0x013fffff;fields.actor_flag_1908_bit2=false;packet.foot_surface_ids[0]=0;fields.wheel_hardness=0;packet.foot_surface_ids[1]=0;fields.auxiliary_vectors[0]={0,0,0,0};fields.requested_physics_mode=1;
    for (std::size_t i=1;i<fields.auxiliary_vectors.size();++i) fields.auxiliary_vectors[i]={0,0,0,0};
    for (std::size_t i=0;i<count;++i) {packet.local[i]=AnimationResetPose;packet.hierarchy[i]=AnimationResetPose;}error.clear();return true;
}
std::uint32_t AnimationSignalHash(std::string_view name)
{
    std::uint32_t hash=0;for (const auto character:name) {const auto byte=static_cast<unsigned char>(character);if (byte==0) break;const auto signed_byte=byte>=128?std::int32_t(byte)-256:std::int32_t(byte);hash=(hash<<4)+std::uint32_t(signed_byte);const auto high=hash&0xf0000000;if (high!=0) hash^=(high>>23)^high;}return hash;
}
bool PublishAnimationEvaluated(SkaterPublicationState& state,const std::vector<Mat4>& hierarchy,const std::vector<Mat4>& local,PhysicsPosePacket& packet,double timestep,std::string_view name,std::int32_t& result,std::string& error)
{
    const auto count=std::size_t(packet.bone_count);
    if (hierarchy.size()<count||local.size()<count||packet.hierarchy.size()<count||packet.local.size()<count) {error="RangeOutsideAllocation";return false;}
    packet.timestep=float(timestep);packet.foot_surface_ids={0,0};ReplaceFlag(packet.flags,27,state.request_bit16);state.request_bit16=false;ReplaceFlag(packet.flags,23,state.request_bit15);state.request_bit15=false;packet.flags&=~((std::uint32_t(1)<<25)|(std::uint32_t(1)<<26));
    if (state.signal) {state.signal->name_hash=AnimationSignalHash(name);state.signal->active=0;}
    std::copy_n(hierarchy.begin(),count,packet.hierarchy.begin());std::copy_n(local.begin(),count,packet.local.begin());packet.board_flipped=state.orientation_bit31!=state.mirrored;packet.mirrored=state.mirrored;packet.riding_switch=state.relative_stance==1;packet.riding_fakie=state.riding_fakie;packet.weight_forwards=state.riding_fakie?!state.weight_on_nose:state.weight_on_nose;packet.regular_stance=state.natural_stance==0;
    ReplaceFlag(packet.flags,28,state.air_dismount_revert_requested);state.air_dismount_revert_requested=false;packet.air_dismount_revert_frames=state.air_dismount_revert_frames;result=state.air_dismount_revert_frames;error.clear();return true;
}
AnimationPublication::AnimationPublication(bool local_player):flags((std::uint32_t(local_player)<<27)|0x00020000) {}
void AnimationPublication::ApplyStanceEvents(const std::vector<AnimationAttribute>& attributes)
{
    const auto present=[&](std::string_view name) {const auto key=EncodeAnimationName(name);return std::any_of(attributes.begin(),attributes.end(),[&](const auto& a){return a.name==key;});};
    if (present("animboardbackward")) flags^=0x80000000;if (present("mirrored")) flags^=0x40000000;if (present("switch")) publication.relative_stance=std::int32_t(publication.relative_stance==0);
}
void AnimationPublication::PreparePublication()
{
    publication.orientation_bit31=(flags&0x80000000)!=0;publication.mirrored=(flags&0x40000000)!=0;publication.riding_fakie=(flags&0x20000000)!=0;publication.weight_on_nose=(flags&0x10000000)!=0;publication.request_bit16=(flags&0x00010000)!=0;publication.request_bit15=(flags&0x00008000)!=0;publication.air_dismount_revert_requested=(flags&0x00100000)!=0;
}
void AnimationPublication::FinishPublication() {flags&=~std::uint32_t(0x00010000|0x00008000|0x00100000);}
float AnimationPublication::CullThreshold() const {const std::uint32_t b=(flags&0x08000000)!=0?0x3c23d70a:0x3dcccccd;float value;std::memcpy(&value,&b,4);return value;}
std::uint32_t AnimationPublication::CheckpointStance() const {return std::uint32_t(((publication.natural_stance==0&&publication.relative_stance==0)||(publication.natural_stance==1&&publication.relative_stance==1))!=Fakie());}
std::uint32_t AnimationPublication::RequestedStanceForFoot(std::uint32_t foot) const {return std::uint32_t(foot==0?publication.natural_stance!=1:publication.natural_stance==1);}
}
