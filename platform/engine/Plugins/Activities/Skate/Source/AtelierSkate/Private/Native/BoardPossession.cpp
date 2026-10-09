#include "BoardPossession.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Bits(float v){std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
Vec4 Sub(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Scale4(Vec4 a,float s){for(auto& x:a)x*=s;return a;}
Vec4 Madd4(Vec4 a,float s,Vec4 b){for(unsigned i=0;i<4;++i)a[i]=std::fma(a[i],s,b[i]);return a;}
Vec4 Unit(Vec4 a,Vec4 fallback)
{
    const float squared=Dot3(a,a),inverse=InverseLengthSquared(squared,2),length=squared==0.0f?0.0f:squared*inverse;
    return length>Scalar(0x358637bd)?Scale4(a,inverse):fallback;
}
Vec4 Direction(const Mat4& frame,Vec4 v){return Madd4(frame[2],v[2],Madd4(frame[1],v[1],Scale4(frame[0],v[0])));}
float ProjectedAngle(Vec4 a,Vec4 b,Vec4 axis)
{
    if(!(Dot3(a,a)*Dot3(b,b)>Scalar(0x37800000)))return 0.0f;
    a=Sub(a,Scale4(axis,Dot3(axis,a)));b=Sub(b,Scale4(axis,Dot3(axis,b)));
    const float aa=Dot3(a,a),bb=Dot3(b,b),gate=Scalar(0x38d1b717);if(!(aa>gate && bb>gate))return 0.0f;
    a=Scale4(a,InverseLengthSquared(aa,1));b=Scale4(b,InverseLengthSquared(bb,1));
    const float angle=Acos(std::fmin(std::fmax(Dot3(a,b),-1.0f),1.0f));
    return Dot3(Cross3(a,b),axis)<0.0f?Scalar(0x40c90fdb)-angle:angle;
}
float Wrap(float angle)
{
    const float turns=angle*Scalar(0x3e22f983),fraction=turns-std::floor(turns);
    return (fraction-(fraction>0.5f?1.0f:0.0f))*Scalar(0x40c90fdb);
}
}
void BoardPossessionState::Stop(SkateboardControllerFields& f,const BoardPossessionObservation& o,const BoardPossessionSettings& s,BoardPossessionEffects& e)
{
    if(f.system_on_452){f.word_444=0;if(f.state_448!=0){LetGo(f,o,s,e);f.state_448=0;}f.system_on_452=false;}
}
void BoardPossessionState::Hold(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e)
{
    e.EnableAnimationSoft();e.StandardBoard();e.CollisionVolumes(true);f.state_448=1;
    selected_hand_424=((~o.processed.flags_2476)>>2)&1u;hands[selected_hand_424].dynamics={{{0x4395ffff,0,0x468c9fff,2},{0x4395ffff,0,0x468c9fff,2}}};
    UpdateDriveFrames(o);
}
void BoardPossessionState::DisableHand()
{
    if(selected_hand_424!=2){if(selected_hand_424>=2)std::abort();hands[selected_hand_424].dynamics={{{0,0,0,2},{0,0,0,2}}};selected_hand_424=2;}
}
void BoardPossessionState::LetGo(SkateboardControllerFields& f,const BoardPossessionObservation& o,const BoardPossessionSettings& s,BoardPossessionEffects& e)
{
    e.DisableAnimation();e.ReleasedBoard();e.CollisionVolumes(true);e.ClearAlignment();DisableHand();
    if(f.state_448==4)e.Velocity(Vec4{});f.word_444=0;
    if(o.processed.flags_2476&0x1000){f.word_444=8;e.Velocity(BoardThrowVelocity(o.processed,s));}
}
void BoardPossessionState::Hide(const BoardPossessionObservation& o,BoardPossessionEffects& e)
{
    e.CollisionVolumes(false);e.DisableLinearDrive();e.ClearAlignment();DisableHand();
    retrieval={};retrieval.initial_0=o.processed.board_frame_64;retrieval.elapsed_192=0.0f;e.EnableAnimationAngularOnly();
}
void BoardPossessionState::Retrieve(const SkateboardControllerFields& f,const BoardPossessionObservation& o,const BoardPossessionSettings& s,BoardPossessionEffects& e)
{
    e.CollisionVolumes(false);e.ClearAlignment();e.EnableAnimationAngularOnly();
    const auto old=retrieval.initial_0[3];retrieval={};retrieval.initial_0=o.processed.board_frame_64;
    if(f.state_448==3)retrieval.initial_0[3]=old;retrieval.target_64=o.attachment_frame_0;
    auto delta=Sub(retrieval.initial_0[3],retrieval.target_64[3]);float distance=Length3(delta);const float tiny=Scalar(0x3a83126f);
    if(!(distance>=tiny)){distance=tiny;delta=Scale4(o.processed.player_frame_192[2],tiny);}
    const bool mounting=(o.processed.flags_2480&0x80000)!=0;const float maximum=mounting?s.mounted_return_distance:s.return_distance;
    if(distance>maximum || f.state_448==3)
    {
        retrieval.initial_0[3]=Madd4(Scale4(delta,maximum),RefinedReciprocal(distance,2),retrieval.target_64[3]);e.Position(retrieval.initial_0[3]);distance=maximum;
    }
    retrieval.duration_196=s.retrieval_time.Evaluate(distance);retrieval.elapsed_192=0.0f;
    if(mounting){const float duration=retrieval.duration_196;retrieval.duration_196=s.mounting_time-duration>=0.0f?duration:s.mounting_time;}
}
void BoardPossessionState::UpdateState(SkateboardControllerFields& f,const BoardPossessionObservation& o,const BoardPossessionSettings& s,BoardPossessionEffects& e)
{
    const auto& p=o.processed;switch(f.state_448)
    {
    case 1:
    {
        const bool free_allowed=(p.flags_2480&0x80000)==0 && (p.flags_2488&0x8000000)==0;
        if((p.flags_2476&0x2000) || (free_allowed && (o.board_collision_flags_872&0x4000000))){f.word_444=0;LetGo(f,o,s,e);f.state_448=2;}
        else {const auto hand=selected_hand_424==0?0:1;e.Alignment({Unit(Sub(o.physical_hand_positions[hand],p.board_frame_64[3]),Vec4{}),Unit(Sub(p.position_592,p.board_frame_64[3]),Vec4{}),Scalar(0x3f4ccccd),true});}break;
    }
    case 2:
    {
        const auto delta=Sub(p.board_frame_64[3],p.position_592);const bool distant=Dot3(delta,delta)>s.hide_distance*s.hide_distance;
        if((p.flags_2480&0x80000) || (p.flags_2476&0x800)){f.word_444=0;Retrieve(f,o,s,e);f.state_448=4;}
        else if(distant || o.board_state_840==6){f.word_444=0;Hide(o,e);f.state_448=3;}break;
    }
    case 3:if((p.flags_2480&0x80000) || (p.flags_2476&0x800)){f.word_444=0;Retrieve(f,o,s,e);f.state_448=4;}break;
    case 4:
    {
        const auto hand=((~p.flags_2476)>>2)&1u;
        if((p.flags_2480&0x80000)==0 && o.hand_contacts[hand]){f.word_444=0;LetGo(f,o,s,e);f.state_448=2;}
        else if(!(retrieval.progress_200<1.0f)){e.Velocity(Vec4{});f.word_444=0;Hold(f,o,e);f.state_448=1;}break;
    }
    case 5:if(o.board_collision_flags_872&0x4000000){f.word_444=0;LetGo(f,o,s,e);f.state_448=2;}
        else e.Alignment({p.board_frame_64[2],p.board_frame_64[2],Scalar(0x3f733333),false});break;
    default:break;
    }
}
void BoardPossessionState::UpdateDriveFrames(const BoardPossessionObservation& o)
{
    if(selected_hand_424>=2)std::abort();const auto hand=selected_hand_424==0?0:1;
    const auto& a=o.animation_board_frame_12624;const auto& b=o.animation_hand_frames[hand];Mat4 inverse{};
    for(unsigned i=0;i<3;++i)inverse[i]={a[0][i],a[1][i],a[2][i],0.0f};
    const auto negative=Sub(Vec4{},a[3]);const auto translation=Madd4(inverse[0],negative[0],Madd4(inverse[1],negative[1],Scale4(inverse[2],negative[2])));
    auto parent=SkeletonIdentity;for(unsigned i=0;i<3;++i)parent[i]=Direction(inverse,b[i]);
    parent[3]=Madd4(inverse[2],b[3][2],Madd4(inverse[1],b[3][1],Madd4(inverse[0],b[3][0],translation)));
    hands[selected_hand_424].child=SkeletonIdentity;hands[selected_hand_424].parent=parent;
}
void BoardPossessionState::Update(SkateboardControllerFields& f,const BoardPossessionObservation& o,const BoardPossessionSettings& s,BoardPossessionEffects& e)
{
    if(!f.system_on_452)return;UpdateState(f,o,s,e);
    switch(f.state_448)
    {
    case 1:UpdateDriveFrames(o);break;
    case 2:if(f.word_444!=0 && f.word_444<0x80000000u){--f.word_444;for(const auto& torque:BoardThrowTorques(o.processed,s))e.Torque(torque);}break;
    case 3:
        retrieval.elapsed_192+=Scalar(0x3c888889);retrieval.progress_200=0.5f;retrieval.weight_204=0.5f;retrieval.target_64=retrieval.initial_0;
        retrieval.target_64[3]=Madd4(o.processed.hide_direction_464,s.hide_offset,o.processed.player_frame_192[3]);retrieval.current_128=retrieval.target_64;
        e.HookFrame(retrieval.current_128);e.Position(retrieval.current_128[3]);e.Velocity(Vec4{});break;
    case 4:
    {
        retrieval.elapsed_192+=Scalar(0x3c888889);const float fraction=retrieval.elapsed_192/retrieval.duration_196;
        retrieval.progress_200=1.0f-fraction>=0.0f?fraction:1.0f;retrieval.weight_204=s.retrieval_weight.Evaluate(retrieval.progress_200);
        retrieval.target_64=o.attachment_frame_0;retrieval.current_128=InterpolateAffine(retrieval.initial_0,retrieval.target_64,retrieval.weight_204);
        e.HookFrame(retrieval.current_128);e.TargetPositionVelocity(retrieval.current_128[3]);break;
    }
    default:break;
    }
}
BoardPossessionFill FillBoardPossession(const SkateboardControllerFields& f,const BoardPossessionState& state,const BoardPossessionProcessed& p,Mat4 bone11)
{
    const auto& frame=p.player_frame_192;const auto on_axis=Madd4(frame[1],Dot3(Sub(bone11[3],frame[3]),frame[1]),frame[3]);
    const auto position=f.state_448==3?state.retrieval.initial_0[3]:p.board_frame_64[3];const auto delta=Sub(position,on_axis);
    const float y=Dot3(delta,frame[0]),x=Dot3(delta,frame[2]);const float basic=Atan(std::fma(y,RefinedReciprocal(x,1),0.0f));
    const auto sign=Bits(y)&0x80000000u;const float result=0.0f>x?Scalar(0x40490fdbu|sign)+basic:basic;
    const float angle=x==0.0f?Scalar(0x3fc90fdbu|sign):result;const auto s=f.state_448,bits=p.flags_2476;
    return {angle,0.0f,s==1,s==2 || s==3 || s==4,s==4,s==3,(bits&0x200)!=0,(bits&0x400)!=0 || s==4,(bits&0x400)!=0 || ((bits&0x800)!=0 && s==4)};
}
Vec4 BoardThrowVelocity(const BoardPossessionProcessed& p,const BoardPossessionSettings& s)
{
    const float radians=Scalar(0x3c8efa35);const auto [yaw_sin,yaw_cos]=SinCos(0.0f*radians);
    const Mat4 yaw{{{yaw_cos,0.0f,-yaw_sin,yaw_cos},{0.0f,1.0f,0.0f,0.0f},{yaw_sin,0.0f,yaw_cos,yaw_sin},{0.0f,0.0f,0.0f,0.0f}}};
    const auto [sin,cos]=SinCos(-s.throw_pitch*radians);const auto local=Direction(yaw,{0.0f,-sin,cos,0.0f});
    const auto direction=Direction(p.player_frame_192,local);const float speed=Length3(p.velocity_912);return Scale4(direction,speed+s.throw_velocity.Evaluate(speed));
}
std::array<Vec4,3> BoardThrowTorques(const BoardPossessionProcessed& p,const BoardPossessionSettings& s)
{
    auto flat_board=p.board_frame_64[2];flat_board[1]=0.0f;auto flat_direction=p.direction_400;flat_direction[1]=0.0f;
    const auto heading=Unit(flat_direction,Unit(flat_board,{0.0f,0.0f,1.0f,0.0f}));const Vec4 up{0.0f,1.0f,0.0f,0.0f};
    const auto right=Cross3(up,heading);const Mat4 basis{right,up,heading,Vec4{}};
    const auto [sin,cos]=SinCos(-s.throw_target_pitch*Scalar(0x3c8efa35));
    const auto target_right=Direction(basis,{1.0f,0.0f,0.0f,1.0f}),target_up=Direction(basis,{0.0f,cos,sin,0.0f}),target_forward=Direction(basis,{0.0f,-sin,cos,0.0f});
    auto forward=p.board_frame_64[2],board_right=p.board_frame_64[0];if(0.0f>Dot3(forward,target_forward)){for(auto& v:forward)v=-v;for(auto& v:board_right)v=-v;}
    return {Scale4(Scale4(target_up,Wrap(ProjectedAngle(forward,target_forward,target_up))),s.throw_yaw_scalar),
        Scale4(Scale4(target_right,Wrap(ProjectedAngle(forward,target_forward,target_right))),s.throw_pitch_scalar),
        Scale4(Scale4(target_forward,Wrap(ProjectedAngle(board_right,target_right,target_forward))),s.throw_roll_scalar)};
}
Vec4 BoardPossessionAngularAcceleration(Vec4 request,Vec4 omega,const std::array<Vec4,3>& inverse_inertia)
{
    const auto& a=inverse_inertia[0];const auto& b=inverse_inertia[1];const auto& c=inverse_inertia[2];
    const std::array<Vec4,3> cofactor{Cross3(b,c),Cross3(c,a),Cross3(a,b)};const float inverse_det=RefinedReciprocal(Dot3(a,cofactor[0]),2);
    Mat4 inverse=SkeletonIdentity;for(unsigned i=0;i<3;++i)inverse[i]={cofactor[0][i]*inverse_det,cofactor[1][i]*inverse_det,cofactor[2][i]*inverse_det,0.0f};inverse[3]={};
    const float dt=Scalar(0x3c888889);const auto axis=Unit(request,Vec4{});const auto residual=Sub(request,Scale4(axis,Dot3(axis,Scale4(omega,dt))));
    const auto local=Direction(inverse,Scale4(residual,RefinedReciprocal(dt,2)));
    return Direction(Mat4{a,b,c,Vec4{}},Scale4(local,RefinedReciprocal(dt,2)));
}
}
