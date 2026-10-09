#pragma once
#include "SimulationMath.h"
#include "ForceQueue.h"
namespace atelier::skate
{
struct SlideState
{
    float start_speed=0,steering_push=1,damped_turn=0;
    bool flag48=false,wall_riding=false;
    void Enter(float speed) {start_speed=speed;Exit();}
    void Exit() {flag48=false;wall_riding=false;steering_push=1;damped_turn=0;}
};
struct SlideSettings
{
    PointGraph<8> input_remap,remap_vs_speed,force_vs_angle,force_vs_speed;
    float softest_wheel_force,softest_wheel_spin,angular_force,force_y_offset;
};
struct SlideSurface {PointGraph<8> speed_to_force;float yaw_strength,yaw_damping;};
struct SlideInput
{
    Vec4 velocity,normal,side,effective_forward,reference_forward,angular_velocity;
    float absolute_speed,surface_speed,slide,elapsed,wheel_hardness;
};
// The angular path preserves the original zero-velocity normalization behavior.
Vec4 CalculateSlideAngularCorrection(const SlideSettings&,const SlideSurface&,SlideInput);
QueuedPointForce CalculateSlidingForce(const SlideSettings&,const SlideSurface&,SlideInput);
}
