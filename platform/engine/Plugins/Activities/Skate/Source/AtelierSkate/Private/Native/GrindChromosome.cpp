#include "GrindChromosome.h"
#include "GrindForces.h"
#include "GrindNames.h"
#include "AnimationName.h"
#include <cmath>
#include <cstring>
#ifdef __clang__
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 Add(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]+=b[i];return a;}
Vec4 Sub(Vec4 a,Vec4 b){for(std::size_t i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Scale(Vec4 a,float b){for(float& v:a)v*=b;return a;}
Vec4 Signed(Vec4 a,bool positive){if(!positive)for(float& v:a)v=-v;return a;}
std::int32_t Increment(std::int32_t a){std::uint32_t bits;std::memcpy(&bits,&a,4);++bits;std::memcpy(&a,&bits,4);return a;}
bool Low(GrindChromosomeInput in)
{
    const auto axis=Signed(in.basic_forward_32,Dot3(Sub(in.basic_position_48,in.point),in.basic_forward_32)>0.0f);
    return Dot3(in.normal,axis)<=-0.1f;
}
bool Straight(GrindChromosomeInput in)
{
    const auto projected=Sub(in.basic_twist_axis_128,Scale(in.normal,Dot3(in.basic_twist_axis_128,in.normal)));
    const float length=GrindForceLength(projected);if(length<=0.01f)return true;
    float inverse=1.0f/length;
    for(unsigned i=0;i<2;++i){const float correction=std::fma(-inverse,length,1.0f);inverse=std::fma(inverse,correction,inverse);}
    return std::fabs(Dot3(Scale(projected,inverse),in.direction))>0.9397f;
}
}
void GrindChromosome::InitializeHostFakie(bool observed)
{
    if(!saved_fakie_initialized){saved.fakie=observed;saved_fakie_initialized=true;}
}
GrindApproachPose GrindChromosome::Reference() const {return history.size()==30?history.front():saved;}
bool GrindChromosome::Travel(GrindChromosomeInput in,PlayerGrindFamily family,std::uint32_t& out,std::string& error)
{
    const auto feet=Add(in.feet_256_272[0],in.feet_256_272[1]);
    const auto right=Signed(in.basic_right_0,Dot3(feet,in.basic_right_0)>0.0f);
    const bool forward=Dot3(right,in.direction)>0.0f;std::uint32_t result;
    if(family==PlayerGrindFamily::FiftyFifty||family==PlayerGrindFamily::FiveO){
        if(!orientation){if(history.size()!=30&&!saved_fakie_initialized){error="saved fakie144 consumed before an actual history write";return false;}const auto reference=Reference();reversed=Dot3(feet,Add(reference.feet[0],reference.feet[1]))<0.0f;if(reference.fakie)reversed=!reversed;}
        result=forward?(reversed?2:0):(reversed?3:1);
    }else result=!forward;
    orientation=result;out=result;return true;
}
bool GrindChromosome::Update(GrindChromosomeInput in,std::optional<GrindChromosomePublication>& out,std::string& error)
{
    const GrindApproachPose snapshot{in.basic_right_0,in.basic_position_48,in.feet_256_272,in.fakie_155};
    if(in.air_event_439){saved=snapshot;saved_fakie_initialized=true;history.clear();}
    if(in.category==100){if(history.size()==30)history.pop_front();history.push_back(snapshot);}
    const bool new_approach=in.category==400&&previous_category!=400&&away_frames>30;
    if(new_approach||(in.category==400&&previous_kind!=in.family)){saved=Reference();saved_fakie_initialized|=history.size()==30;}
    if(new_approach){
        const auto across=Signed(in.across,Dot3(in.across,Sub(saved.position,in.point))>0.0f);
        const auto right=Signed(saved.right,Dot3(Add(saved.feet[0],saved.feet[1]),saved.right)>0.0f);
        approach=Dot3(right,across)>0.0f;
    }
    previous_kind=in.family;away_frames=in.category==400?0:Increment(away_frames);
    std::optional<GrindChromosomePublication> result;
    if(in.family&&in.grinding_316){
        const auto family=*in.family;std::uint32_t travel;if(!Travel(in,family,travel,error))return false;const bool low=Low(in),straight=Straight(in);
        const bool location=(family==PlayerGrindFamily::Tipslide||family==PlayerGrindFamily::FiveO||family==PlayerGrindFamily::Backslash)
            &&Dot3(Sub(in.point,in.basic_location_position_144),in.basic_location_axis_96)<=0.0f;
        const GrindComponents c{{approach,std::uint32_t(location),std::uint32_t(straight),std::uint32_t(low),travel,std::uint32_t(family)}};
        if(previous_category!=400){pending=c;pending_frames=13;}
        else if(pending&&*pending==c)pending_frames=Increment(pending_frames);
        else{pending=c;pending_frames=0;}
        if(pending_frames>0)animation=pending;if(pending_frames>12)scoring=pending;
        result=GrindChromosomePublication{c,animation,scoring};
    }else{orientation.reset();reversed=false;}
    previous_category=in.category;out=result;return true;
}
bool GrindChromosome::Publish(const GrindChromosomePublication& p,GrindOutputFields& out,std::string& error) const
{
    out.volatile_chromosome_244=p.volatile_components;
    if(p.animation){
        const auto name=LookupGrindName(*p.animation);if(!name){error="validated grind chromosome dimensions";return false;}
        out.animation_chromosome_268=*p.animation;out.animation_id_144=std::uint32_t(name->skating_id);out.animation_name_156=EncodeAnimationName(name->attribute);
    }
    if(p.scoring){
        const auto name=LookupGrindName(*p.scoring);if(!name){error="validated grind chromosome dimensions";return false;}
        out.scoring_chromosome_292=*p.scoring;out.scoring_id_148=std::uint32_t(name->skating_id);out.scorable_id_152=std::uint32_t(name->scorable_id);out.scoring_name_176=EncodeAnimationName(name->attribute);
    }
    return true;
}
}
