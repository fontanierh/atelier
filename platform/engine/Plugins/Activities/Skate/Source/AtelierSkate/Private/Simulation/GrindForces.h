#pragma once
#include "PlayerGrindManager.h"
#include "AirReckoning.h"
#include "WipeoutSettings.h"
#include "WipeoutRequests.h"
#include <vector>
namespace atelier::skate
{
float GrindForceLength(Vec4);
float GrindRefinedReciprocal(float);
float GrindMaterialMultiplier(std::uint32_t);
float GrindPinSlope(Vec4 normal,Vec4 upmost,float relief,const PointGraph<4>&);
std::optional<Vec4> GrindLateralPin(Mat4 board,Vec4 point,Vec4 across,Vec4 velocity,float strength,float forward,float up,bool forward_selected,float slope);
Vec4 GrindFriction(Vec4 velocity,Vec4 normal,Vec4 support,float time,bool flagged,float surface,std::uint32_t kind,std::array<float,3> strengths);
bool GrindFrictionApplies(Vec4 velocity,Vec4 normal);
struct GrindSlideInput
{
    Vec4 position,point,direction,across,velocity;float translation_2796,total_mass_2660,update_frequency;
    bool preparing_jump;std::uint32_t geometry_kind;
};
std::vector<Vec4> GrindSlideControl(bool darkslide,GrindSlideInput);
struct GrindReleaseInput
{
    Vec4 position,point,across,normal,velocity;std::uint32_t geometry_kind;Vec4 high_side;
    bool force_across,enable_lift;float strength,speed_limit,lift;
};
std::optional<Vec4> GrindReleaseForce(GrindReleaseInput);
std::optional<Vec4> GrindSupportPin(Vec4 normal,float relief);
std::optional<Vec4> GrindSupportCoping(Vec4 upmost,Vec4 velocity,float relief);
std::optional<Vec4> GrindSupportExitLean(Vec4 high_side,float angle,const PointGraph<4>&);
Vec4 GrindTruckCompensation(Vec4 normal,float pitch);
struct GrindOrientationInput {Mat4 board;Vec4 direction,normal,point;float yaw_1504,pitch_1508;bool switched;};
struct GrindOrientationTarget {Mat4 frame;float noise_amount;};
bool GrindTargetOrientation(std::uint32_t family,GrindOrientationInput,GrindOrientationTarget&,std::string& error);
Mat4 GrindBlendOrientation(Mat4 current,Mat4 target);
std::array<float,3> GrindNoiseAngles(float speed,float amount,std::array<std::uint32_t,3> draws);
Mat4 ApplyGrindOrientationNoise(Mat4,float speed,float amount,std::array<std::uint32_t,3> draws);
struct GrindLaunchInput {Vec4 velocity_400,position_112,current_point_1120;float balance_2800,geometry_side_jump,vertical_jump;};
struct GrindLaunchOutput {Vec4 velocity;PlayerGrindJumper jumper;std::uint32_t flags_2476_to_or;};
GrindLaunchOutput CalculateGrindLaunch(PlayerGrindJumper,GrindLaunchInput);
struct GrindReckoningSettings {Vec4 ground_normal_smoothing;PointGraph<8> tilt_vs_rotation,tilt_vs_slope;};
bool UpdateGrindReckoning(GroundOrientation&,ReckoningFrames&,PhysicalBodySpinState&,AirReckoningState&,const GrindReckoningSettings&,Vec4 normal,Vec4 heading,float smoothing,bool reverse,float body_spin,std::string& error);
struct GrindPostSettings {float max_arm_contact_164,max_body_contact_168,xz_acceleration_204,max_displacement_208,max_angular_deck_error_212;};
// Shared original regional-force kernel will be exported by the Wipeout owner
// after its frozen baseline passes. There is no duplicate grind implementation.
bool CheckWipeoutRegionalForce(const WipeoutFrame&,float body,float arms);
void CheckGrindPost(WipeoutRequests&,GrindPostSettings,const WipeoutFrame&);
}
