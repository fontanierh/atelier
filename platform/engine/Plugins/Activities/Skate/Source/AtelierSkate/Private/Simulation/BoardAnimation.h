#pragma once
#include "SkeletonRoot.h"
namespace atelier::skate
{
struct BoardAnimationSettings {PointGraph<8> slow,fast;};
// This history is shared between ground error capture and air animation.
struct BoardAnimation
{
    Quat rotation_error{0,0,0,1};
    bool blending=false;
    void Reset(){rotation_error={0,0,0,1};}
    void CapturePhysicsError(const Mat4& target,const Mat4& deck_part);
    Mat4 Apply(const Mat4& target,bool fast,const BoardAnimationSettings&);
};
Vec4 BoardAnimationTargetVelocity(Vec4 target,Vec4 deck_body_position,float dt);
}
