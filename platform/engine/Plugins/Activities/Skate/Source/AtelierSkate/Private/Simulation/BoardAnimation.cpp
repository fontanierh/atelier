#include "BoardAnimation.h"
#include "ConstraintFrames.h"
#include "DriveFrames.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t word){float result;std::memcpy(&result,&word,4);return result;}
}
void BoardAnimation::CapturePhysicsError(const Mat4& target,const Mat4& deck_part)
{
    const auto relative=OrthonormalizeSkeletonFrame(ComposeSkeletonAffine(InverseSkeletonRigid(target),deck_part));
    Basis3 basis;
    for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)basis.columns[axis][lane]=relative[axis][lane];
    rotation_error=QuaternionFromBasis(basis);blending=true;
}
Mat4 BoardAnimation::Apply(const Mat4& target,bool fast,const BoardAnimationSettings& settings)
{
    if(!blending)return target;
    const float angle=Acos(rotation_error[3])*2.0f,turns=angle*Float(0x3e22f983),fractional=turns-std::floor(turns);
    const float folded=fractional-(fractional>0.5f?1.0f:0.0f),distance=std::fabs(folded*Float(0x40c90fdb));
    const float fraction=(fast?settings.fast:settings.slow).Evaluate(distance);
    if(!(fraction<Float(0x3f733333))){blending=false;return target;}
    const Quat identity{0,0,0,1};const float dot=Dot4(rotation_error,identity);const bool reverse=0.0f>dot;
    const float magnitude=reverse?-dot:dot;auto q=rotation_error;if(reverse)for(auto& v:q)v=-v;
    if(magnitude>Float(0x3f7f069e))
    {
        const bool same_sign=Dot4(q,identity)>0.0f;Quat mixed;
        for(unsigned lane=0;lane<4;++lane)mixed[lane]=same_sign?std::fma(fraction,identity[lane]-q[lane],q[lane]):std::fma(-(identity[lane]+q[lane]),fraction,q[lane]);
        const float inverse=InverseLengthSquared(Dot4(mixed,mixed),2);
        for(unsigned lane=0;lane<4;++lane)q[lane]=mixed[lane]*inverse;
    }
    else
    {
        const float theta=Acos(magnitude),a=Sin((1.0f-fraction)*theta),b=Sin(fraction*theta);
        const float inverse=RefinedReciprocal(Sin(theta),2),weight_a=a*inverse,weight_b=b*inverse;
        for(unsigned lane=0;lane<4;++lane)q[lane]=std::fma(identity[lane],weight_b,q[lane]*weight_a);
    }
    rotation_error=q;const auto rotation=constraint_frame::Basis(q);auto correction=SkeletonIdentity;
    for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<3;++lane)correction[axis][lane]=rotation.columns[axis][lane];
    return ComposeSkeletonAffine(target,correction);
}
Vec4 BoardAnimationTargetVelocity(Vec4 target,Vec4 deck_body_position,float dt)
{
    const float inverse=1.0f/dt;Vec4 velocity;
    for(unsigned lane=0;lane<4;++lane)velocity[lane]=(target[lane]-deck_body_position[lane])*inverse;
    return velocity;
}
}
