#pragma once
#include "AnimationPlayback.h"
namespace atelier::skate
{
struct AnimationSignal {std::uint32_t name_hash=0;std::uint8_t active=0;};
struct SkaterPublicationState
{
    bool orientation_bit31=false,mirrored=false,riding_fakie=false,weight_on_nose=false;
    std::int32_t relative_stance=0,natural_stance=1;
    bool request_bit16=false,request_bit15=false,air_dismount_revert_requested=false;
    std::int32_t air_dismount_revert_frames=0;
    std::optional<AnimationSignal> signal;
};
struct PhysicsPosePacket
{
    std::uint32_t bone_count=0;
    std::vector<Mat4> hierarchy,local;
    float timestep=0;
    std::array<std::uint32_t,2> foot_surface_ids{};
    std::uint32_t flags=0;
    bool board_flipped=false,mirrored=false,riding_switch=false,riding_fakie=false,weight_forwards=false,regular_stance=false;
    std::int32_t air_dismount_revert_frames=0;
};
struct AnimationAdditionalResetFields
{
    float compression=0;
    std::array<float,2> foot_ik_influence{};
    bool next_step_position_valid=false,actor_flag_1904_bit23=false,actor_flag_1908_bit2=false;
    bool external_impulse_active=false,external_physics_input_active=false,externally_controlled=false;
    bool prevent_manual_respawn=false;
    std::uint8_t ignore_respawn_reset_button=0;
    bool force_braking=false;
    float truck_tightness=0,wheel_hardness=0;
    std::array<Vec4,6> auxiliary_vectors{};
    std::uint32_t requested_physics_mode=0;
};
inline constexpr Mat4 AnimationResetPose{{{1,0,0,0},{0,1,0,0},{0,0,1,0},{0,0,0,0}}};
// Packet extents are validated before any mutation. Reset treats bone_count as
// signed; publication treats it as unsigned, preserving the original boundary.
bool ResetAnimationPacket(PhysicsPosePacket& packet,AnimationAdditionalResetFields& fields,std::string& error);
std::uint32_t AnimationSignalHash(std::string_view bytes);
bool PublishAnimationEvaluated(SkaterPublicationState& state,const std::vector<Mat4>& hierarchy,const std::vector<Mat4>& local,PhysicsPosePacket& packet,double timestep,std::string_view signal_name,std::int32_t& result,std::string& error);
struct AnimationPublication
{
    explicit AnimationPublication(bool local_player);
    std::uint32_t flags=0;
    SkaterPublicationState publication;
    float phase=0;
    bool Mirrored() const {return (flags&0x40000000)!=0;}
    bool Fakie() const {return (flags&0x20000000)!=0;}
    bool Switch() const {return publication.relative_stance==1;}
    void ApplyStanceEvents(const std::vector<AnimationAttribute>& attributes);
    void PreparePublication();
    void FinishPublication();
    float CullThreshold() const;
    std::uint32_t CheckpointStance() const;
    std::uint32_t RequestedStanceForFoot(std::uint32_t foot) const;
};
}
