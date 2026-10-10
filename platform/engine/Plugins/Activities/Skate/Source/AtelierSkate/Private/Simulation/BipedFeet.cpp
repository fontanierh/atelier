#include "BipedFeet.h"
#include "OffboardVectorMath.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float FootHeight(const BoardPossessionManager& s,const BipedFeetInput& input,float ground,float desired)
{
    const float base=ground+.02f,proposed=(desired-s.scalars_288_to_296[0])+ground;
    const float limited=VectorMax(VectorMin(proposed,base+.08f),base),output=VectorMax(desired,limited);
    const float ceiling=std::fma(input.velocity[1],offboard_air_math::Step(),input.position[1])-.46f;
    return output-desired>.4f||output>ceiling?desired:output;
}
Vec4 ClampFootNormal(Vec4 normal)
{
    using namespace offboard_air_math;
    if(normal[1]>=.9f)return normal;normal[1]=0;
    // The original deliberately uses an unguarded refined reciprocal here.
    normal=Mul(normal,Reciprocal(Length(normal))*std::sqrt(Bits(0x3e428f5f)));normal[1]=.9f;return normal;
}
float FootHeightCorrection(BoardPossessionManager& s,const BipedFeetInput& input)
{
    using namespace offboard_air_math;
    if(!s.hands[0].flag_84&&!s.hands[1].flag_84)return 0;
    float highest=Bits(0x501502f9);
    for(auto& foot:s.hands)
    {
        foot.scalars_96_100[0]=0;if(!foot.flag_84)continue;
        if(foot.flags_104_to_107[0])
        {
            const auto side=input.effective_root[0],normal=UnitOr(Sub(foot.vectors_0_to_64[4],Mul(side,Dot(side,foot.vectors_0_to_64[4]))),{});
            foot.scalars_96_100[0]=Dot(normal,input.effective_root[2])*.2f;
        }
        highest=VectorMin(highest,foot.vectors_0_to_64[3][1]+foot.scalars_96_100[0]);
    }
    return s.scalars_288_to_296[0]-highest;
}
}
std::array<BipedFootTarget,2> UpdateBipedFeetTargets(BoardPossessionManager& s,const BipedFeetInput& input)
{
    using namespace offboard_air_math;
    for(std::size_t index=0;index<2;++index)
    {
        auto& foot=s.hands[index];const auto& line=input.lines[index];foot.vectors_0_to_64[1]=input.world_foot_pairs[index][0];
        foot.vectors_0_to_64[3]=line.position;foot.vectors_0_to_64[4]=line.normal;foot.word_80=line.surface;foot.flag_84=line.valid;
        const auto side=index^std::size_t((input.flags_2476&4)!=0);
        foot.flags_104_to_107[2]=(input.flags_2484&(1u<<(6+side)))!=0;foot.flags_104_to_107[3]=(input.flags_2484&(1u<<(2+side)))!=0;
    }
    if(s.words_308_to_316[0]==0){s.vectors_224_to_272[2]=input.effective_root[3];s.flags_304_to_307[3]=true;}
    for(std::size_t index=0;index<2;++index)
    {
        auto& foot=s.hands[index];const bool low=s.word_300!=3&&input.local_foot_pairs[index][0][1]<.09f&&input.local_foot_pairs[index][1][1]<.09f;
        foot.flags_104_to_107[0]=low;bool supported=low;
        if(foot.flag_84)
        {
            const auto normal=ClampFootNormal(foot.vectors_0_to_64[4]);foot.vectors_0_to_64[2]=normal;
            const auto a=Dot(normal,Sub(input.world_foot_pairs[index][0],foot.vectors_0_to_64[3])),b=Dot(normal,Sub(input.world_foot_pairs[index][1],foot.vectors_0_to_64[3]));
            const float distance=VectorMax(a,b);supported=distance<.09f||(low&&distance<.2f);
        }
        else foot.vectors_0_to_64[2]=Up;
        foot.flags_104_to_107[1]=supported;
    }
    const bool mirrored=(input.flags_2476&4)!=0,forced_left=(input.flags_2480&(mirrored?1u<<5:1u<<6))!=0,forced_right=(input.flags_2480&(mirrored?1u<<6:1u<<5))!=0;
    if(forced_left){s.hands[0].flags_104_to_107[1]=true;s.hands[1].flags_104_to_107[1]=false;}
    else if(forced_right){s.hands[0].flags_104_to_107[1]=false;s.hands[1].flags_104_to_107[1]=true;}
    s.scalars_288_to_296[1]+=Step();std::uint32_t support=2;
    if(input.state==501)support=3;
    else if(s.flags_304_to_307[0])
    {
        const bool left=s.hands[0].flags_104_to_107[1],right=s.hands[1].flags_104_to_107[1];if(left&&!right)support=0;else if(!left&&right)support=1;
    }
    if(support!=s.word_300)
    {
        s.word_300=support;s.scalars_288_to_296[1]=0;s.vectors_224_to_272[3]=support<2?input.world_foot_pairs[support][0]:Vec4{};
    }
    for(std::size_t index=0;index<2;++index)
    {
        const auto foot=s.hands[index];auto desired=foot.vectors_0_to_64[1];
        if(s.word_300==index)
        {
            auto flat=Sub(s.vectors_224_to_272[3],desired);flat[1]=0;
            if(Dot(flat,flat)<Bits(0x3bd1b717))desired=s.vectors_224_to_272[3];
            else
            {
                const auto old=s.vectors_224_to_272[3];desired=Madd(flat,.08f/Length(flat),desired);desired[1]=old[1];s.vectors_224_to_272[3]=desired;
            }
            s.hands[index].vectors_0_to_64[0]=desired;
        }
        else
        {
            if(foot.flag_84)desired[1]=FootHeight(s,input,foot.vectors_0_to_64[3][1],desired[1]-VectorMax(foot.scalars_96_100[0],0));
            const auto time=VectorMax(foot.scalars_96_100[1]-Step(),0);s.hands[index].scalars_96_100[1]=time;const float weight=1-time*10;
            s.hands[index].vectors_0_to_64[0]=Madd(desired,weight,Mul(foot.vectors_0_to_64[0],1-weight));
        }
    }
    std::array<BipedFootTarget,2> targets;
    for(std::size_t index=0;index<2;++index)
    {
        auto& foot=s.hands[index];const bool world=s.word_300==index;if(world&&(input.flags_2484&0x80000000)==0)foot.scalars_96_100[1]=.1f;
        targets[index]={world?foot.vectors_0_to_64[0]:TransformSkeletonPoint(input.inverse_root,foot.vectors_0_to_64[0]),world,world?1.0f:.3f,
            foot.flags_104_to_107[1]&&foot.flag_84?std::optional<Vec4>(foot.vectors_0_to_64[2]):std::nullopt};
    }
    s.scalars_288_to_296[0]=input.root[3][1];s.scalars_288_to_296[2]=FootHeightCorrection(s,input);return targets;
}
void SetBipedFootNormal(foot_ik::ExternalTarget& target,Vec4 normal)
{
    if(target.normal_blend>0)target.normal=offboard_air_math::LimitAngle(normal,target.normal,.1f);
    target.normal_set=true;target.normal_blend=VectorMin(target.normal_blend+.2f,1);
}
void ApplyBipedFootTargets(const std::array<BipedFootTarget,2>& targets,foot_ik::State& ik)
{
    for(std::size_t index=0;index<2;++index)
    {
        const auto& target=targets[index];auto& limb=ik.limbs[index];auto& external=ik.external_targets[index];
        if(target.world){external.world_position=target.position;limb.external_target_set=true;}
        else{external.animation_position=target.position;limb.local_target_set=true;}
        limb.target_blend=target.blend;if(target.normal)SetBipedFootNormal(external,*target.normal);
    }
}
}
