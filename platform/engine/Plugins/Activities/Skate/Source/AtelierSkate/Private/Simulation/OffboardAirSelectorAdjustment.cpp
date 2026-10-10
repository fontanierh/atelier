#include "OffboardAirMath.h"
#include "GravityScale.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void OffboardAirSelectorCore::AdjustAnimation(std::int32_t frame,Vec4 animation,const Mat4& axes,float radius)
{
    using namespace offboard_air_math;sampling.adjustment_8336=Mul(axes[2],animation[2]);
    correction_8304=Mul(Madd(axes[1],animation[1]-radius,sampling.adjustment_8336),-1);correction_8304[1]-=.08f;
    auto& s=sampling.selection;const auto delta=Sub(Sub(s.position_6176,correction_8304),AirTrajectoryPositionAt(s.trajectory_8144,float(s.landing_frame_8480)*Step()));
    Shift(s.trajectory_8144,float(frame)*Step());Adjust(s.trajectory_8144,WrappingSub(s.landing_frame_8480,frame),delta,.5f);Shift(s.trajectory_8144,float(WrappingNeg(frame))*Step());
    const auto t=s.trajectory_8144;const auto end=AirTrajectoryPositionAt(t,float(s.landing_frame_8480)*Step());
    if(launch.up_48[1]<.8f&&Dot(launch.up_48,Flat(t.velocity))<=0&&s.normal_6144[1]>.9f&&end[1]-t.position[1]>-.2f)
    {
        const auto g=(Bits(0x411ccccd)*GravityScale()),distance=Length(Sub(t.position,end)),square=(2*distance)*Reciprocal(g);
        const auto root=square==0?0:square*Inverse(square),duration=root*.66f+float(s.landing_frame_8480)*.0056666667f;
        if(duration>.2f)
        {
            const Vec4 acceleration{0,-g,0,0};s.trajectory_8144.velocity=Sub(Mul(Sub(end,t.position),Reciprocal(duration)),Mul(Mul(acceleration,.5f),duration));
            s.trajectory_8144.acceleration=acceleration;s.trajectory_8144.scalar_48=-1;s.landing_frame_8480=Integer(duration*59.999996f);s.scalar_8392=float(s.landing_frame_8480)*Step();
        }
    }
}
}
