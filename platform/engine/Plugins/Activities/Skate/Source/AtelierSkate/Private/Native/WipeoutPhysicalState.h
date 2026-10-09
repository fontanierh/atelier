#pragma once
#include "NativeMath.h"
#include <cstdint>
#include <limits>
#include <optional>
namespace atelier::skate
{
struct WipeoutRecoverySettings
{float minimum_time,minimum_settled,maximum_time,fade_time,over_speed,over_minimum_time;};
struct WipeoutPhysicalOutput
{
    bool over_599;
    float scalar_544;
    float no_support_time_548;
    bool can_leave_72;
    bool special_surface_81;
    bool below_surface_82;
    float surface_height_32;
    bool surface_height_valid_83;
    float collision_time_144;
    std::uint32_t profile_148;
    float response_strength_580;
    float extra_weight_584;
    float time_until_teleport_576;
    bool teleport_pending_604;
    bool material_ten_3479;
    bool material_eleven_3480;
    bool imminent_surface_twelve_3483;
    Vec4 predicted_position_64;
    std::optional<Vec4> retained_air_velocity_160;
    std::optional<float> response_change_588;
    bool teleport_countdown_68;
    bool request_teleport_69;
    float hips_right_angle_496;
    float hips_up_angle_500;
};
struct WipeoutPhysicalState
{
    float time=0.0; //304
    float settled_time=0.0; //308
    float time_until_teleport=0.0; //312
    float impaled_time=0.0; //316
    float no_support_time=0.0; //320
    float response_time=0.0; //324
    float extra_weight_zero_time=0.0; //328
    float slow_time=0.0; //332
    float surface_height=0.0; //336
    Vec4 board_offset{}; //352
    Vec4 forward{}; //368
    Vec4 right{}; //384
    Vec4 angular_velocity{}; //400
    Vec4 retained_tilt{}; //416
    Vec4 velocity{}; //432
    Vec4 retained_velocity{}; //448
    Vec4 predicted_position{}; //464
    bool over=false; //480
    bool slow=false; //481
    bool material_eleven_response=false; //482
    bool air_collision_mode=false; //483
    bool request_teleport=false; //484
    bool move_board=false; //485
    bool special_surface=false; //486
    bool below_surface=false; //487
    bool retained_velocity_active=false; //488
    float sideways_input=0.0; //492
    float forward_input=0.0; //496
    float orientation=0.0; //500
    float collision_weight=0.0; //504
    float controlled_weight=0.0; //508
    float control_time=0.0; //512
    float retained_sideways_input=0.0; //516
    float retained_forward_input=0.0; //520
    float response_scalar=0.0; //524
    float extra_weight=1.0; //528
    float maximum_speed=10.0; //532
    float response_start_speed=0.0; //536
    float response_change=0.0; //540
    std::uint32_t board_move_frames=0; //544, initialized by Enter
    std::uint32_t response_count=0; //548
    std::int32_t response_frames=-1; //552
    std::int32_t airborne_frames=-1; //556
    std::int32_t teleport_countdown=-1; //560
    bool prevent_manual=false; //564
    bool ignore_reset=false; //565
    bool reset_ever=false; //566
    bool ever_settled=false; //567
    bool recovery_eligible=false; //568
    bool teleport_pending=false; //569
    bool ever_impaled=false; //570
    bool direction_initialized=false; //571
    bool material_ten_response=false; //572
    bool imminent_surface_twelve=false; //573
    bool allow_retained_velocity=true; //574
    bool response_finished=false; //575
    bool surface_query=false; //576
    std::size_t profile=0; //580
    float predicted_time=std::numeric_limits<float>::max(); //832
    float ResponseStrength() const;
    void ManageRecovery(std::uint32_t flags2468,std::uint32_t flags2472,std::uint32_t flags2484,float timestep,const WipeoutRecoverySettings&);
    void PostPhysics(Vec4 hips_velocity,Vec4 neck_velocity,bool support,const WipeoutRecoverySettings&);
    WipeoutPhysicalOutput Output(const Mat4& hips,Vec4 normal) const;
private:
    bool ShouldTeleport(std::uint32_t flags2472,std::uint32_t flags2484,float timestep,const WipeoutRecoverySettings&);
};
}
