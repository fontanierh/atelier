// SPDX-License-Identifier: Apache-2.0
#include "AnimationPhaseInput.h"
#include "StockSettingsReader.h"
#include <cstring>
namespace atelier::skate
{
namespace
{
std::uint32_t Word(float f) {std::uint32_t w;std::memcpy(&w,&f,4);return w;}
RawMatrix ResetWords() {RawMatrix m;for (std::size_t c=0;c<4;++c) for (std::size_t r=0;r<4;++r) m[c][r]=Word(AnimationResetPose[c][r]);return m;}
}
bool AnimationProfile::Load(const SettingsDatabase& data,std::string_view mode,std::string& error)
{
    constexpr std::array<std::string_view,5> modes{"easy","normal","hardcore","motorized","test"};std::optional<std::size_t> index;
    for (std::size_t i=0;i<5;++i) if (modes[i]==mode) {index=i;break;}
    if (!index) {error="Undefined player physics profile "+std::string(mode);return false;}
    AnimationProfile next;next.physics_mode=std::uint32_t(*index);StockSettingsReader reader(data);
    if (!reader.Float("anim_skitching","default","LongSkitchIntoReachTime",next.skitch_transition_time,error)||!reader.Float("anim_motion","pushing","disable_push_brake_at_slope",next.maximum_ground_angle_degrees,error)) return false;
    const std::uint32_t bits=0x3f333333;std::memcpy(&next.truck_tightness,&bits,4);next.wheel_hardness=next.truck_tightness;*this=next;error.clear();return true;
}
AnimationPhaseOutput::AnimationPhaseOutput()
{
    reset.requested_physics_mode=1;publication_.matrix_10704=ResetWords();
}
void AnimationPhaseOutput::Publish(const PhysicsPosePacket& pose,const AnimationProfile& profile,std::uint32_t actor_flags)
{
    auto& r=reset;r.actor_flag_1904_bit23=false;r.actor_flag_1908_bit2=profile.suppress_transition||(actor_flags&(1u<<2))!=0;r.truck_tightness=profile.truck_tightness;r.wheel_hardness=profile.wheel_hardness;r.requested_physics_mode=profile.physics_mode;r.prevent_manual_respawn=profile.prevent_manual_respawn;r.ignore_respawn_reset_button=profile.ignore_respawn_reset_button;r.force_braking=profile.force_braking;
    flags_=pose.flags&~((1u<<24)|(1u<<22));mirrored_=std::uint8_t(pose.mirrored);weight_forwards_=std::uint8_t(pose.weight_forwards);
    publication_=AnimationPacketFields{std::uint8_t(pose.board_flipped),pose.timestep,r.compression,{std::uint8_t(r.actor_flag_1904_bit23),0,0},{},ResetWords(),0,r.truck_tightness,r.wheel_hardness,std::uint8_t(pose.riding_switch)};
}
void AnimationPhaseOutput::PublishExternalReset(AnimationExternalReset reply)
{publication_.matrix_10704=reply.transform;publication_.byte_10768=reply.byte64;publication_.flags_10375_10496_10784[2]=1;}
AnimationInputPacket AnimationPhaseOutput::Packet() const
{
    const auto& r=reset;AnimationInputPacket p{publication_,external_};p.flag_10369=std::uint8_t(r.next_step_position_valid);p.flag_10370=mirrored_;p.flag_10373=weight_forwards_;p.suppress_transition_10376=std::uint8_t(r.actor_flag_1908_bit2);p.use_external_physics_10688=0;p.external_physics_flag_10689=0;p.flag_10786=std::uint8_t(r.prevent_manual_respawn);p.flag_10787=r.ignore_respawn_reset_button;p.force_braking_10796=std::uint8_t(r.force_braking);
    const std::array<RawVector*,6> vectors{&p.vector_10816,&p.vector_10832,&p.vector_10848,&p.vector_10864,&p.vector_10880,&p.vector_10896};for (std::size_t v=0;v<6;++v) for (std::size_t i=0;i<4;++i) (*vectors[v])[i]=Word(r.auxiliary_vectors[v][i]);
    p.scalar_10912=r.foot_ik_influence[0];p.scalar_10916=r.foot_ik_influence[1];p.state_variant_10928=r.requested_physics_mode;p.flags_10932=flags_;return p;
}
}
