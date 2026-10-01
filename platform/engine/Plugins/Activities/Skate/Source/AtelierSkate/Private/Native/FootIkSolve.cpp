// SPDX-License-Identifier: Apache-2.0
#include "FootIkCore.h"
#include "SkeletonRoot.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::foot_ik
{
namespace
{
float Word(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Bits(float v){std::uint32_t bits;std::memcpy(&bits,&v,4);return bits;}
Vec4 Sub(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]-=b[i];return a;}
Vec4 Add(Vec4 a,Vec4 b){for(unsigned i=0;i<4;++i)a[i]+=b[i];return a;}
Vec4 ScaledAdd(Vec4 a,float scale,Vec4 b){for(unsigned i=0;i<4;++i)a[i]=std::fma(a[i],scale,b[i]);return a;}
void AddTranslation(Mat4& frame,Vec4 offset){for(unsigned i=0;i<4;++i)frame[3][i]+=offset[i];}
float SquareRoot(float squared){const float value=squared*InverseLengthSquared(squared,2);return squared==0.0f?0.0f:value;}
float ClampCosine(float value){return VectorMin(1.0f,VectorMax(0.0f,value));}
Vec4 Candidate(Vec4 delta,float angle,float upper_length,Vec4 root,const Mat4& basis)
{
    const auto sc=SinCos(angle);const float sine=sc.first,cosine=sc.second;
    const Mat4 rotation{{{cosine,sine,0.0f,cosine},{-sine,cosine,0.0f,-sine},{0,0,1,0},{0,0,0,0}}};
    const Vec4 rotated=Normalize3(TransformSkeletonPoint(rotation,delta));
    return TransformSkeletonPoint(basis,ScaledAdd(rotated,upper_length,root));
}
std::optional<Mat4> LineFrame(Vec4 start,Vec4 end,Vec4 normal)
{
    const Vec4 line=Sub(end,start),across=Cross3(line,normal),third=Cross3(across,line);
    const Vec4 x=NormalizeSafe(across),z=NormalizeSafe(third),y=NormalizeSafe(line);
    const float product=(Dot3(z,z)*Dot3(x,x))*Dot3(y,y);
    if(product>Word(0x37800000))return Mat4{{x,y,z,start}};
    return std::nullopt;
}
Vec4 ClampPoint(Vec4 point,Vec4 origin,float maximum)
{
    const Vec4 delta=Sub(point,origin);const float distance=Length3(delta);
    return maximum>=distance?point:ScaledAdd(delta,maximum/distance,origin);
}
std::optional<Vec4> SolveDrives(std::size_t end_part,Vec4 offset,float maximum_distance,const Geometry& geometry,const std::array<Mat4,24>& original,std::array<Mat4,24>& drives,AngleLimits limits)
{
    if(!geometry.parents[end_part])return std::nullopt;const std::size_t middle_part=*geometry.parents[end_part];
    if(!geometry.parents[middle_part])return std::nullopt;const std::size_t root_part=*geometry.parents[middle_part];
    const Vec4 root=original[root_part][3],middle=original[middle_part][3],end=original[end_part][3],requested=Add(end,offset);
    Vec4 target=ClampPoint(requested,root,maximum_distance),solved_middle{};
    if(SolveTwoBone(root,middle,end,solved_middle,target,limits,true,2)==SolveResult::Invalid)return std::nullopt;
    const Vec4 residual=Sub(target,requested),original_normal=Cross3(Sub(root,middle),Sub(end,middle)),solved_normal=Cross3(Sub(root,solved_middle),Sub(target,solved_middle));
    const Vec4 normal=NormalizeSafe(Add(original_normal,solved_normal));
    const auto mid_map=LineMapping(middle,end,normal,solved_middle,target,normal);if(!mid_map)return std::nullopt;
    const auto root_map=LineMapping(root,middle,normal,root,solved_middle,normal);if(!root_map)return std::nullopt;
    drives[root_part]=OrthonormalizeSkeletonFrame(ComposeSkeletonAffine(*root_map,drives[root_part]));
    drives[middle_part]=OrthonormalizeSkeletonFrame(ComposeSkeletonAffine(*mid_map,drives[middle_part]));return residual;
}
float Tangent(float angle)
{
    const float quadrant=std::nearbyint(angle*Word(0x3f22f983));
    float reduced=std::fma(-quadrant,Word(0x3fc90fdb),angle);reduced=std::fma(-quadrant,Word(0x2e85a309),reduced);
    const float squared=reduced*reduced;
    float denominator=std::fma(squared,Word(0x3505bba8),Word(0xb9a37b25));
    denominator=std::fma(squared,denominator,Word(0x3cd23cf5));denominator=std::fma(squared,denominator,Word(0xbeeef582));
    denominator=std::fma(squared,denominator,1.0f);
    float numerator=std::fma(squared,Word(0xb795d5b9),Word(0x3b607415));numerator=std::fma(squared,numerator,Word(0xbe0895af));
    numerator=std::fma(reduced,squared*numerator,reduced);
    const float bound=Word(0x39800000);const std::uint32_t mask=(reduced>bound?0x80000000u:0)|(reduced<-bound?0x40000000u:0);
    denominator=Word((Bits(denominator)&~mask)|(Bits(1.0f)&mask));numerator=Word((Bits(numerator)&~mask)|(Bits(reduced)&mask));
    return (static_cast<std::int32_t>(std::fabs(quadrant))&1)==0?numerator*RefinedReciprocal(denominator,2):denominator*RefinedReciprocal(-numerator,2);
}
void Feet(State& state,SkeletonBody& body,const Geometry& geometry,const Settings& settings,const PostSettings& post,const PostInput& input,std::array<bool,4>& updated)
{
    Mat4 effective_board=input.board;
    if((input.flags_2484&(1u<<21))!=0)for(unsigned i=0;i<4;++i){effective_board[0][i]*=-1.0f;effective_board[1][i]*=-1.0f;}
    const Vec4 up=effective_board[1];float up_y=up[0]*input.world_to_animation[0][1];up_y=std::fma(up[1],input.world_to_animation[1][1],up_y);up_y=std::fma(up[2],input.world_to_animation[2][1],up_y);
    const bool constrained=(input.flags_2468&(1u<<18))!=0;
    if((input.flags_2484&(1u<<20))!=0||post.minimum_board_up>up_y||(constrained&&input.value_2664>Word(0x3d23d70a))||(constrained&&input.state_2520==500))return;
    for(unsigned limb=0;limb<2;++limb)
    {
        const auto binding=Limbs[limb];const auto adjacent=*binding.parent_part;
        if(state.frames[limb].within_contact_bounds&&!input.wipeout)
        {
            state.frames[limb].world=ComposeSkeletonAffine(input.board,state.frames[limb].board);
            state.frames[limb].parent_world=ComposeSkeletonAffine(input.board,state.frames[limb].parent_board);
            const Vec4 offset=Sub(state.frames[limb].parent_world[3],body.record.pose[adjacent][3]);
            if(SolvePhysical(body,geometry,adjacent,offset)){body.SetPartTransform(binding.part,state.frames[limb].world);body.SetPartTransform(adjacent,state.frames[limb].parent_world);updated[limb]=true;}
        }
        else if(!state.limbs[limb].external_target_set)
        {
            Mat4 foot=body.record.pose[binding.part];if(Dot3(foot[1],up)<=0.0f)continue;
            const auto target=PostContactTarget(effective_board,foot[3],body.record.pose[adjacent][3],state.limbs[limb].part_position,input.wipeout,settings,post);if(!target)continue;
            const float distance=Dot3(up,Sub(*target,foot[3]));Vec4 offset;for(unsigned i=0;i<4;++i)offset[i]=up[i]*distance;
            if(SolvePhysical(body,geometry,adjacent,offset))
            {
                foot[3]=*target;body.SetPartTransform(binding.part,foot);Mat4 adjacent_frame=body.record.pose[adjacent];AddTranslation(adjacent_frame,offset);body.SetPartTransform(adjacent,adjacent_frame);updated[limb]=true;
            }
        }
    }
}
}
std::optional<Geometry> Geometry::Create(std::array<std::optional<std::size_t>,24> parents,const std::array<Mat4,24>& part_frames,std::string& error)
{
    for(unsigned part=0;part<24;++part)
    {
        auto parent=parents[part];std::array<bool,24> visited{};visited[part]=true;
        while(parent){const auto index=*parent;if(index>=24||visited[index]){error="Invalid physical ancestor chain for IK part "+std::to_string(part);return std::nullopt;}visited[index]=true;parent=parents[index];}
    }
    Geometry result;result.parents=parents;for(unsigned part=0;part<24;++part)result.inverse_part_frames[part]=InverseAffine(part_frames[part]);return result;
}
bool Geometry::ValidateLimbs(const std::array<LimbBinding,4>& bindings,std::string& error) const
{
    for(const auto& binding:bindings)
    {
        const auto end=binding.parent_part.value_or(binding.part);
        if(binding.part>=24||end>=24||!parents[end]||!parents[*parents[end]]){error="IK part "+std::to_string(end)+" has no two-bone physical ancestor chain";return false;}
    }
    return true;
}
Vec4 NormalizeSafe(Vec4 value)
{
    const float magnitude=Length3(value);const Vec4 normalized=Normalize3(value);
    return magnitude>Word(0x358637bd)?normalized:Vec4{};
}
std::optional<Mat4> LineMapping(Vec4 start,Vec4 end,Vec4 normal,Vec4 new_start,Vec4 new_end,Vec4 new_normal)
{
    const auto original=LineFrame(start,end,normal);if(!original)return std::nullopt;
    const auto target=LineFrame(new_start,new_end,new_normal);if(!target)return std::nullopt;
    return ComposeSkeletonAffine(*target,InverseSkeletonRigid(*original));
}
SolveResult SolveTwoBone(Vec4 root,Vec4 middle,Vec4 end,Vec4& solved_middle,Vec4& target,AngleLimits limits,bool override_maximum,std::uint32_t recursion_budget)
{
    if(recursion_budget==0){target=end;solved_middle=middle;return SolveResult::Invalid;}
    const Vec4 upper=Sub(middle,root),lower=Sub(end,middle);const float upper_length=Length3(upper),lower_length=Length3(lower),epsilon=Word(0x3a03126f);
    if(epsilon>upper_length||epsilon>lower_length){solved_middle=middle;return SolveResult::Invalid;}
    const Vec4 requested_delta=Sub(target,root),forward=Normalize3(Sub(end,root)),normal=Normalize3(Cross3(upper,lower));
    const Mat4 original_basis{{forward,Cross3(forward,normal),normal,root}};
    const Vec4 target_forward=Normalize3(requested_delta),target_lateral=Cross3(target_forward,normal),target_normal=Cross3(target_lateral,target_forward);
    const Mat4 target_basis{{target_forward,target_lateral,target_normal,root}},original_inverse=InverseAffine(original_basis),target_inverse=InverseAffine(target_basis);
    const Vec4 local_root=TransformSkeletonPoint(original_inverse,root),local_middle=TransformSkeletonPoint(original_inverse,middle),local_end=TransformSkeletonPoint(original_inverse,end),local_target=TransformSkeletonPoint(target_inverse,target),target_delta=Sub(local_target,local_root);
    const float planar_squared=std::fma(target_delta[0],target_delta[0],target_delta[1]*target_delta[1]);const float distance=SquareRoot(planar_squared);
    const float upper_squared=upper_length*upper_length,lower_squared=lower_length*lower_length,twice_upper=2.0f*upper_length,twice_product=twice_upper*lower_length,sum_squared=upper_squared+lower_squared;
    Vec4 negative_lower;for(unsigned i=0;i<4;++i)negative_lower[i]=-lower[i];const float negative_length=-lower_length;
    const float original_angle=Acos(RefinedReciprocal(upper_length*negative_length,2)*Dot3(upper,negative_lower))*Word(0x42652ee1);
    float maximum=limits.maximum_degrees;if(original_angle>maximum&&override_maximum)maximum=original_angle;
    const float minimum_distance=SquareRoot(sum_squared-twice_product*Cos(limits.minimum_degrees*Word(0x3c8efa35))),maximum_distance=SquareRoot(sum_squared-twice_product*Cos(maximum*Word(0x3c8efa35)));
    if(minimum_distance>distance||distance>maximum_distance)
    {
        if(distance>upper_length+lower_length&&maximum==180.0f)
        {
            const Vec4 direction=Normalize3(target_delta),middle_local=ScaledAdd(direction,upper_length,local_root),end_local=ScaledAdd(direction,lower_length,middle_local);
            solved_middle=TransformSkeletonPoint(target_basis,middle_local);target=TransformSkeletonPoint(target_basis,end_local);return SolveResult::Extended;
        }
        const float capped=distance>maximum_distance?maximum_distance-epsilon:minimum_distance+epsilon;
        target=ScaledAdd(Normalize3(requested_delta),capped,root);
        return SolveTwoBone(root,middle,end,solved_middle,target,limits,override_maximum,recursion_budget-1);
    }
    const float cosine=ClampCosine(RefinedReciprocal(twice_product,2)*(sum_squared-planar_squared)),interior_angle=Acos(cosine)*Word(0x42652ee1);
    if(limits.minimum_degrees>=interior_angle)
    {
        target=ScaledAdd(Normalize3(requested_delta),minimum_distance+epsilon,root);
        return SolveTwoBone(root,middle,end,solved_middle,target,limits,override_maximum,recursion_budget-1);
    }
    float target_angle=Acos(ClampCosine(RefinedReciprocal(distance,2)*target_delta[0]));
    if((local_middle[1]<0.0f&&local_target[1]>0.0f)||(local_middle[1]>0.0f&&local_target[1]<0.0f))target_angle*=-1.0f;
    const float ratio=std::fma(RefinedReciprocal(twice_upper*distance,2),(upper_squared+planar_squared)-lower_squared,target_angle),angle=Acos(ClampCosine(ratio));
    const Vec4 original_delta=Sub(local_end,local_root),positive=Candidate(original_delta,angle,upper_length,local_root,target_basis),negative=Candidate(original_delta,Word(0x40c90fdb)-angle,upper_length,local_root,target_basis);
    solved_middle=local_end[1]>local_middle[1]?negative:positive;return SolveResult::Solved;
}
std::array<bool,4> UpdateDrives(const std::array<LimbStatus,4>& statuses,std::array<LimbFrames,4>& frames,const std::array<LimbBinding,4>& bindings,const Geometry& geometry,const std::array<Mat4,24>& original,std::array<Mat4,24>& drives,const Mat4& world_to_animation,AngleLimits limits)
{
    std::array<bool,4> updated{};
    for(unsigned limb=0;limb<4;++limb)
    {
        if(statuses[limb].mode==Mode::Disabled)continue;const auto binding=bindings[limb];
        const Mat4 target=ComposeSkeletonAffine(world_to_animation,frames[limb].world);
        const std::optional<Mat4> parent_target=binding.parent_part?std::optional<Mat4>(ComposeSkeletonAffine(world_to_animation,frames[limb].parent_world)):std::nullopt;
        const std::size_t driven=binding.parent_part.value_or(binding.part);const Mat4& driven_target=parent_target?*parent_target:target;
        const Vec4 endpoint=TransformSkeletonPoint(driven_target,geometry.inverse_part_frames[driven][3]),offset=Sub(endpoint,original[driven][3]);
        const auto residual=SolveDrives(driven,offset,limb<2?Word(0x3f4ccccd):1.0f,geometry,original,drives,limits);if(!residual)continue;
        drives[binding.part]=target;AddTranslation(drives[binding.part],*residual);AddTranslation(frames[limb].world,*residual);
        if(binding.parent_part){drives[*binding.parent_part]=*parent_target;AddTranslation(drives[*binding.parent_part],*residual);AddTranslation(frames[limb].parent_world,*residual);}updated[limb]=true;
    }
    return updated;
}
std::optional<Vec4> PostContactTarget(const Mat4& board,Vec4 foot,Vec4 adjacent,Vec4 animated_board_position,bool wipeout,const Settings& settings,const PostSettings& post)
{
    const Mat4 inverse=InverseSkeletonRigid(board);const Vec4 local_foot=TransformSkeletonPoint(inverse,foot),local_adjacent=TransformSkeletonPoint(inverse,adjacent);
    Vec4 midpoint;for(unsigned i=0;i<4;++i)midpoint[i]=(local_foot[i]+local_adjacent[i])*0.5f;midpoint[1]=local_foot[1];
    const float x=VectorMin(std::fabs(local_foot[0]),std::fabs(midpoint[0])),z=VectorMin(std::fabs(local_foot[2]),std::fabs(midpoint[2]));
    if(x>=settings.deck_half_width+settings.post_ik_padding[0]||z>=settings.deck_total_half_length+settings.post_ik_padding[2])return std::nullopt;
    float height=wipeout?post.wipeout_height:post.riding_height;
    if(z>settings.deck_half_length)
    {
        float distance=z-settings.deck_half_length;const float end=settings.deck_total_half_length-settings.deck_half_length;distance=end-distance>=0.0f?distance:end;
        float angle=settings.deck_front_angle_degrees*Word(0x3c8efa35);angle=0.01f-angle>=0.0f?0.01f:angle;angle=Word(0x3fc7c82d)-angle>=0.0f?angle:Word(0x3fc7c82d);
        height=std::fma(distance,Tangent(angle),height);
    }
    if(midpoint[1]>=height||midpoint[1]<=height-Word(0x3e99999a))return std::nullopt;
    Vec4 result=animated_board_position;result[1]=height;return TransformSkeletonPoint(board,result);
}
bool SolvePhysical(SkeletonBody& body,const Geometry& geometry,std::size_t end_part,Vec4 offset)
{
    if(!geometry.parents[end_part])return false;const auto middle_part=*geometry.parents[end_part];if(!geometry.parents[middle_part])return false;const auto root_part=*geometry.parents[middle_part];
    const auto point=[&](std::size_t part){return TransformSkeletonPoint(body.record.pose[part],geometry.inverse_part_frames[part][3]);};
    const Vec4 root=point(root_part),middle=point(middle_part),end=point(end_part);Vec4 target=Add(end,offset),solved_middle{};
    if(SolveTwoBone(root,middle,end,solved_middle,target,{0,180},false,1)!=SolveResult::Solved)return false;
    const Vec4 normal=NormalizeSafe(Add(Cross3(Sub(root,middle),Sub(end,middle)),Cross3(Sub(root,solved_middle),Sub(target,solved_middle))));
    const auto mid_map=LineMapping(middle,end,normal,solved_middle,target,normal);if(!mid_map)return false;
    const auto root_map=LineMapping(root,middle,normal,root,solved_middle,normal);if(!root_map)return false;
    const Mat4 middle_frame=ComposeSkeletonAffine(*mid_map,body.record.pose[middle_part]),root_frame=ComposeSkeletonAffine(*root_map,body.record.pose[root_part]);
    body.SetPartTransform(middle_part,middle_frame);body.SetPartTransform(root_part,root_frame);return true;
}
std::array<bool,4> PostPhysics(State& state,SkeletonBody& body,const Geometry& geometry,const Settings& settings,const PostSettings& post,const PostInput& input)
{
    std::array<bool,4> updated{};
    if(input.state_id!=702)
    {
        const bool airborne=input.state_id==200||input.state_id==201;
        if((!airborne||input.board_body_flag_868)&&input.category_id!=500)Feet(state,body,geometry,settings,post,input,updated);
        if(airborne&&input.board_body_flag_868)for(unsigned limb=2;limb<4;++limb)if(state.frames[limb].within_contact_bounds)
        {
            state.frames[limb].world=ComposeSkeletonAffine(input.board,state.frames[limb].board);const auto part=Limbs[limb].part;
            const Vec4 offset=Sub(state.frames[limb].world[3],body.record.pose[part][3]);if(SolvePhysical(body,geometry,part,offset)){body.SetPartTransform(part,state.frames[limb].world);updated[limb]=true;}
        }
    }
    for(unsigned limb=0;limb<2;++limb)if(!(state.limbs[limb].external_blend<=0.0f))
    {
        const auto binding=Limbs[limb];const auto adjacent=*binding.parent_part;const Vec4 offset=Sub(state.frames[limb].parent_world[3],body.record.pose[adjacent][3]);
        if(SolvePhysical(body,geometry,adjacent,offset)){body.SetPartTransform(binding.part,state.frames[limb].world);body.SetPartTransform(adjacent,state.frames[limb].parent_world);updated[limb]=true;}
    }
    for(unsigned limb=0;limb<4;++limb){state.external_targets[limb].normal_set=false;state.limbs[limb].external_target_set=false;state.limbs[limb].local_target_set=false;}return updated;
}
}
