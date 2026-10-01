// SPDX-License-Identifier: Apache-2.0
#include "GrindAir.h"
#include "SkeletonSettingReader.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
Vec4 Sub(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Add(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]+=b[i];return a;}
Vec4 Scaled(Vec4 v,float s){for(float& x:v)x*=s;return v;}
Vec4 Madd4(Vec4 v,float s,Vec4 a){for(unsigned i=0;i<4;++i)v[i]=std::fma(v[i],s,a[i]);return v;}
Vec4 Cross(Vec4 a,Vec4 b){auto v=Cross3(a,b);v[3]=0.0f;return v;}
Vec4 Unit(Vec4 v)
{
    const float squared=Dot3(v,v),inverse=InverseLengthSquared(squared,2),magnitude=squared==0.0f?0.0f:squared*inverse;
    return magnitude>Word(0x358637bd)?Scaled(v,inverse):Vec4{};
}
Vec4 Limited(Vec4 v,float maximum)
{const float magnitude=Length3(v);return magnitude>maximum?Scaled(v,maximum*RefinedReciprocal(magnitude,2)):v;}
float Wrap(float angle)
{const float turns=angle*Word(0x3e22f983),fraction=turns-std::floor(turns);return (fraction-(fraction>0.5f?1.0f:0.0f))*Word(0x40c90fdb);}
float SignedAngle(Vec4 a,Vec4 b,Vec4 axis)
{
    const float aa=Dot3(a,a),bb=Dot3(b,b);if(!(aa>Word(0x38d1b717)&&bb>Word(0x38d1b717)))return 0.0f;
    a=Scaled(a,InverseLengthSquared(aa,1));b=Scaled(b,InverseLengthSquared(bb,1));
    const float angle=Acos(VectorMin(VectorMax(Dot3(a,b),-1.0f),1.0f));return Wrap(Dot3(Cross(a,b),axis)<0.0f?Word(0x40c90fdb)-angle:angle);
}
Mat4 Rotation(Vec4 axis,float angle)
{
    const auto sc=SinCos(angle);const float s=sc.first,c=sc.second,k=1.0f-c,x=axis[0],y=axis[1],z=axis[2];
    return Mat4{{{std::fma(k*x,x,c),std::fma(k*x,y,s*z),std::fma(k*x,z,-s*y),0},
        {std::fma(k*y,x,-s*z),std::fma(k*y,y,c),std::fma(k*y,z,s*x),0},
        {std::fma(k*z,x,s*y),std::fma(k*z,y,-s*x),std::fma(k*z,z,c),0},{0,0,0,0}}};
}
Vec4 Direction(const Mat4& frame,Vec4 v){return Madd4(frame[2],v[2],Madd4(frame[1],v[1],Scaled(frame[0],v[0])));}
using Samples=std::array<std::array<Vec4,5>,12>;
constexpr std::array<std::size_t,7> Contacts{{0,1,4,0,2,2,3}};
constexpr std::array<float,7> Desired{{90,90,90,90,0,0,0}};
Samples Project(GrindAirInput input,const GrindAirSettings& settings,Vec4 rail,Vec4 normal,std::array<float,12>& headings)
{
    Samples samples{};Mat4 board=input.board;Vec4 velocity=input.velocity;const float speed=Length3(input.angular_velocity);
    const Mat4 rotation=speed<Word(0x37800000)?SkeletonIdentity:Rotation(Scaled(input.angular_velocity,1.0f/speed),speed*input.timestep);
    const Vec4 acceleration=Madd4(input.up,settings.stomp*input.timestep,{0,input.timestep*Word(0xc11ccccd),0,0});
    for(std::size_t frame=0;frame<settings.frames;++frame)
    {
        for(unsigned i=0;i<5;++i){const auto p=settings.points[i];samples[frame][i]=Madd4(board[2],p[2],Madd4(board[1],p[1],Madd4(board[0],p[0],board[3])));}
        const Vec4 forward=Sub(samples[frame][1],samples[frame][4]),projected=Unit(Sub(forward,Scaled(normal,Dot3(normal,forward)))),aligned=Dot3(projected,rail)<0.0f?Scaled(projected,-1.0f):projected;
        float angle=std::fabs(Acos(VectorMin(VectorMax(Dot3(aligned,rail),-1.0f),1.0f)));if(angle>90.0f)angle=180.0f-angle;
        const float sign=Dot3(normal,Cross(aligned,rail))<0.0f?-1.0f:1.0f;headings[frame]=-(sign*angle*Word(0x42652ee1));
        for(unsigned axis=0;axis<3;++axis)board[axis]=Direction(rotation,board[axis]);velocity=Add(velocity,acceleration);board[3]=Madd4(velocity,input.timestep,board[3]);
    }
    return samples;
}
struct ContactPredictions {std::array<float,5> times{{-1,-1,-1,-1,-1}},distances{};std::array<Vec4,5> corrections{};float earliest;};
ContactPredictions Predictions(const Samples& samples,std::size_t count,Vec4 origin,Vec4 rail,Vec4 normal)
{
    ContactPredictions out;out.earliest=static_cast<float>(count);
    for(unsigned p=0;p<5;++p)for(std::size_t i=1;i<count;++i)
    {
        const float a=Dot3(normal,Sub(samples[i-1][p],origin)),b=Dot3(normal,Sub(samples[i][p],origin));if(!(a*b<0.0f))continue;
        const float f=std::fabs(a/(a-b));const Vec4 at=Madd4(samples[i-1][p],1.0f-f,Scaled(samples[i][p],f)),on=Madd4(rail,Dot3(Sub(at,origin),rail),origin);
        out.times[p]=static_cast<float>(i-1)+f;out.corrections[p]=Sub(on,at);out.distances[p]=Length3(out.corrections[p]);out.earliest=VectorMin(out.earliest,out.times[p]);break;
    }
    return out;
}
std::size_t SampleIndex(float time)
{const auto index=static_cast<std::size_t>(time+0.5f);if(index>=12)std::abort();return index;}
std::optional<std::size_t> Choose(const ContactPredictions& c,const std::array<float,12>& headings,const GrindAirSettings& s,bool inverted,std::optional<std::size_t> previous)
{
    const auto valid=[&](std::size_t kind)
    {
        const auto p=Contacts[kind];const float t=c.times[p];
        if(kind==4){if(VectorMin(c.times[2],c.times[3])<4.0f&&std::fabs(c.times[2]-c.times[3])>2.0f)return false;}
        else if(c.earliest<5.0f&&std::fabs(c.earliest-t)>3.0f)return false;
        return t>0.0f&&c.distances[p]<s.distances[kind]&&std::fabs(Desired[kind]-std::fabs(headings[SampleIndex(t)]))<s.ranges[kind];
    };
    std::optional<std::size_t> selected;
    for(std::size_t kind=0;kind<7;++kind)
    {
        if(inverted!=(kind==0)||!valid(kind))continue;
        if(kind==3&&previous&&(*previous==1||*previous==2)&&valid(*previous))kind=*previous;
        if(!selected||c.distances[Contacts[kind]]<c.distances[Contacts[*selected]])selected=kind;
        if(selected&&*selected<5)break;
    }
    return selected;
}
void UpdateAngles(GrindAir& state,GrindAirInput input,const GrindAirSettings& s,const GrindAirTarget& target,const Samples& samples,Vec4 rail,Vec4 normal,std::size_t kind,float time)
{
    const float heading=state.headings[kind],desired=heading>0.0f?Desired[kind]:-Desired[kind],rad=Word(0x42652ee1),deg=Word(0x3c8efa35),pi=Word(0x40490fdb);
    const float speed=VectorMin(VectorMax((desired-heading)/time*s.yaw_assist[kind],-s.max_angle),s.max_angle);
    state.angle_delta[1]=VectorMin(VectorMax(state.angle_delta[1]*rad+speed,-s.max_angle),s.max_angle)*deg;
    const auto& points=samples[SampleIndex(time)];const Vec4 forward=Sub(points[1],points[4]),projected=Unit(Sub(forward,Scaled(rail,Dot3(rail,forward))));float error=0.0f;
    if(kind==0||kind==3){const float angle=SignedAngle(projected,target.orientation.boardslide_dir,rail);error=angle>pi*0.5f?angle-pi:angle<-pi*0.5f?angle+pi:angle;}
    else if(kind==1||kind==2){const Vec4 from=kind==1?Scaled(projected,-1.0f):projected;const float a=SignedAngle(from,target.orientation.tipslide_dir,rail),b=SignedAngle(from,target.orientation.backslash_dir,rail);error=std::fabs(a)<std::fabs(b)?a:b;}
    const float maximum=s.max_angle*deg;state.angle_delta[0]=VectorMin(VectorMax(state.angle_delta[0]+error/time,-maximum),maximum);
    Vec4 broadcast;const float dot=Dot3(input.board[0],normal);for(unsigned i=0;i<4;++i)broadcast[i]=input.board[0][i]-dot;const Vec4 right=Unit(broadcast);
    const float correction=Dot3(right,right)>0.9f?SignedAngle(input.board[0],right,input.board[2])*0.9f:0.0f;state.angle_delta[2]=kind<4?correction/time:0.0f;state.angles=Add(state.angles,state.angle_delta);
}
}
std::array<Vec4,5> GrindAirDeckDimensions::ContactPoints(float tip_fraction) const
{
    const float half=middle_length*0.5f,tip=front_end_size*tip_fraction,y=SinCos(front_end_angle_degrees*Word(0x3c8efa35)).first*tip,z=half+truck_z_front;
    return {{{0,0,0,0},{0,y,tip+half,0},{0,truck_y,z,0},{0,truck_y,-z,0},{0,y,-(tip+half),0}}};
}
bool GrindAirSettings::Validate(std::string& error) const
{if(frames<2||frames>12){error="Stock GrindAir NumFramesToTest exceeds native 2..12 storage";return false;}return true;}
std::optional<GrindAirSettings> GrindAirSettings::Load(const SettingsDatabase& data,std::string& error)
{
    detail::SkeletonSettingReader r(data,error);const auto air=[&](const char* name){return r.Scalar("physics_grinds_air",name);};const auto deck=[&](const char* name){return r.Scalar("physicsdeck",name);};
    const float half=deck("DeckMidLength")*0.5f,tip=deck("DeckFrontEndSize")*air("TipOffsetFraction"),angle=(deck("DeckFrontEndAngle")*Word(0x40490fdb))/180.0f;
    const float z=half+r.Scalar("physicstrucks","TruckZPosFront"),y=r.Scalar("physicstrucks","TruckYPos");const auto frames=r.Integer("physics_grinds_air","NumFramesToTest");if(!error.empty())return std::nullopt;
    if(frames<2||frames>12){error="GrindAir NumFramesToTest exceeds native12-frame storage";return std::nullopt;}
    GrindAirSettings s;s.frames=frames;s.stomp=air("StompAccelerationAdjust");s.points={{{0,0,0,0},{0,tip*SinCos(angle).first,half+tip,0},{0,y,z,0},{0,y,-z,0},{0,tip*SinCos(angle).first,-half-tip,0}}};
    s.ranges={90,air("AngleRangeTipSlide"),air("AngleRangeTipSlide"),air("AngleRangeBoardSlide"),air("AngleRange50_50"),air("AngleRange5_0"),air("AngleRange5_0")};
    s.distances={z,z*air("MaxDistTipSlide"),z*air("MaxDistTipSlide"),z*air("MaxDistBoardSlide"),z*air("MaxDist50_50"),z*air("MaxDist5_0"),z*air("MaxDist5_0")};
    s.yaw_assist={air("AngleYAssistBoardSlide"),air("AngleYAssistTipSlide"),air("AngleYAssistTipSlide"),air("AngleYAssistBoardSlide"),air("AngleYAssist50_50"),air("AngleYAssist5_0"),air("AngleYAssist5_0")};
    s.max_offset=air("MaxOffsetDist");s.max_delta=air("MaxOffsetDeltaPerFrame");s.max_angle=air("MaxAngleDeltaPerFrame");if(!error.empty())return std::nullopt;return s;
}
Mat4 GrindAirAdjustment::LocalTransform(const GrindAirPoseInput& input) const
{
    const Vec4 across_raw=Cross(Vec4{0,1,0,0},axis),across=Scaled(across_raw,InverseLengthSquared(Dot3(across_raw,across_raw),2)),up_raw=Cross(axis,across),up=Scaled(up_raw,InverseLengthSquared(Dot3(up_raw,up_raw),2));
    const Mat4 yaw=Rotation(up,angles[1]),lean=Rotation(axis,angles[0]),pitch=Rotation(input.physical_forward,angles[2]);Mat4 local=SkeletonIdentity;
    for(unsigned i=0;i<3;++i)local[i]=Direction(input.world_to_animation,Direction(yaw,Direction(lean,Direction(pitch,input.animation_to_world[i]))));
    const Vec4 pivot=input.animation_board_position;local[3]=Sub(Add(Direction(input.world_to_animation,offset),pivot),Direction(local,pivot));return local;
}
void GrindAir::Start(GrindAirTarget value){target=value;offset_delta={};offset={};angle_delta={};angles={};selected_kind.reset();}
bool GrindAir::Update(GrindAirInput input,const GrindAirSettings& s,std::optional<GrindAirAdjustment>& output,std::string& error)
{
    output.reset();if(!input.active)return true;
    if((input.flags_2480&0x04000000)!=0||(input.flags_2472&0x8000)!=0||(input.flags_2468&8)!=0){offset={};angles={};return true;}
    if(!target){error="Active GrindAirAdjust has no selected primitive";return false;}if(!s.Validate(error))return false;
    const Vec4 rail=Unit(Sub(target->end,target->start)),normal=Unit(Cross(rail,Cross(input.up,rail)));const auto samples=Project(input,s,rail,normal,headings);const auto c=Predictions(samples,s.frames,target->start,rail,normal);
    const auto kind=Choose(c,headings,s,(input.flags_2484&0x00200000)!=0,selected_kind);if(!kind)return true;selected_kind=kind;
    const auto probe=Contacts[*kind];const float time=c.times[probe];offset_delta=Limited(Add(offset_delta,Scaled(c.corrections[probe],RefinedReciprocal(time,2))),s.max_delta);offset=Limited(Add(offset,offset_delta),s.max_offset);
    UpdateAngles(*this,input,s,*target,samples,rail,normal,*kind,time);output=GrindAirAdjustment{rail,offset,angles};return true;
}
}
