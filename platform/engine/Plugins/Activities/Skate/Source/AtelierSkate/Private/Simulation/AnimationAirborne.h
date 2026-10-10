#pragma once
#include "Graph.h"
#include "GraphMotionSpecialConditions.h"
#include "MotionAnimation.h"
#include <variant>
namespace atelier::skate
{
enum class AnimationAirLegBone {Board,LeftToe,RightToe};
struct AnimationAirLegSettings
{
    float going_up_speed,going_down_speed,minimum_height,preland_velocity,preland_final_height,offboard_multiplier;
    PointGraph<4> arm_extension;
};
struct AnimationAirLegPhysical
{
    Vec4 com_velocity,com_position,system_up,right_toe,left_toe;
    float animation_height;
    bool offboard_316;
    float remaining_air_time;
};
struct AnimationAirLegState
{
    std::uint32_t mode=0;
    float height=0,descending_time=0;
    bool NeedsInitialAttribute() const {return mode==0;}
    bool NeedsPrelandingQuery(const AnimationAirLegPhysical& p) const {return mode==2||(mode==1&&p.com_velocity[1]<0);}
    std::array<float,2> Update(AnimationAirLegBone,const AnimationAirLegPhysical&,const AnimationAirLegSettings&,
        float dt,const std::optional<AnimationAttribute>& initial,bool prepare_to_land);
};
bool AnimationAirLegPrepareToLand(bool physical_query,const std::optional<AnimationAttribute>& full_extension,
    const AnimationAirLegPhysical&,const AnimationAirLegSettings&);
struct AnimationBodySpinSettings
{
    PointGraph<8> map;
    float blend_out,blend_in,maximum_acceleration,maximum_delta;
    float final_height,height_velocity,on_deck_height;
    MotionGraphPrelandingConditionSettings prelanding;
    PointGraph<8> landing_distance;
};
bool AnimationNearLanding(const MotionGraphPrelandingInputs&,const AnimationBodySpinSettings&);
struct AnimationBodySpinState
{
    std::uint32_t mode=0;
    float previous_spin=0,back=0,back_delta=0,front=0,front_delta=0;
    bool Update(MotionAnimation&,std::uint32_t category,std::uint32_t physical_state,bool doing_trick,
        std::array<std::uint32_t,2> busy_hands,bool mirrored,
        const std::optional<MotionGraphPrelandingInputs>&,const AnimationBodySpinSettings&,std::string& error);
};
struct AnimationAirborneSettings {AnimationAirLegSettings air_leg;AnimationBodySpinSettings spin;};
bool LoadAnimationAirborneSettings(const SettingsDatabase&,AnimationAirborneSettings&,std::string& error);
struct GraphMotionAirborneOperation
{
    enum class Kind {Unsupported,AirLeg,BodySpin};
    Kind kind=Kind::Unsupported;
    AttributeName height{};
    AnimationAirLegBone bone=AnimationAirLegBone::Board;
};
using GraphMotionAirborneInstance=std::variant<std::monostate,AnimationAirLegState,AnimationBodySpinState>;
struct GraphMotionAirborneContext
{
    MotionAnimation& animation;
    const AnimationAirborneSettings& settings;
    const std::optional<AnimationAirLegPhysical>& air_leg;
    const std::optional<MotionGraphPrelandingInputs>& prelanding;
    std::optional<std::uint32_t> category,physical_state;
    bool doing_trick;
    std::array<std::uint32_t,2> busy_hands;
    std::optional<bool> mirrored;
};
bool ParseGraphMotionAirborneOperation(const GraphAttributes&,GraphMotionAirborneOperation&,bool& recognized,std::string& error);
GraphMotionAirborneInstance CreateGraphMotionAirborneInstance(const GraphMotionAirborneOperation&);
bool ExecuteGraphMotionAirborneOperation(const GraphMotionAirborneOperation&,GraphMotionAirborneInstance&,
    std::uint8_t phase,float dt,GraphMotionAirborneContext,std::string& error);
}
