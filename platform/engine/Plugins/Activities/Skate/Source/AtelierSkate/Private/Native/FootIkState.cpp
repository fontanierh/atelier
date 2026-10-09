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
float Select(float condition,float nonnegative,float negative){return condition>=0.0f?nonnegative:negative;}
float Positive(float value){return Select(-value,0.0f,value);}
void Approach(float& value,float target,float step)
{
    float delta=target-value;delta=Select(-step-delta,-step,delta);
    value=Select(step-delta,delta,step)+value;
}
float LimitOffset(float value)
{
    const float lower=Select(Word(0xbdcccccd)-value,Word(0xbdcccccd),value);
    return Select(Word(0x3dcccccd)-lower,lower,Word(0x3dcccccd));
}
void ApproachContact(FootContact& contact)
{
    const float delta=contact.desired_offset-contact.offset;
    const float lower=Select(Word(0xbc75c28f)-delta,Word(0xbc75c28f),delta);
    contact.offset=Select(Word(0x3c75c28f)-lower,lower,Word(0x3c75c28f))+contact.offset;
}
Vec4 ContactOffset(const Mat4& board,float offset)
{
    Vec4 result;
    for(unsigned i=0;i<4;++i){const float x=board[0][i]*0.0f,y=std::fma(board[1][i],offset,x);result[i]=std::fma(board[2][i],0.0f,y);}
    return result;
}
void AddOffset(LimbFrames& frame,const Mat4& board,float offset)
{
    const Vec4 delta=ContactOffset(board,offset);
    for(unsigned i=0;i<4;++i){frame.world[3][i]+=delta[i];frame.parent_world[3][i]+=delta[i];}
}
float DistanceToContact(const FootContact& contact,const LimbFrames& frame,const Mat4& board,const Mat4& inverse)
{
    const Vec4 local_contact=TransformSkeletonPoint(inverse,contact.position),delta=ContactOffset(board,contact.offset);
    Vec4 foot;for(unsigned i=0;i<4;++i)foot[i]=frame.world[3][i]+delta[i];
    const Vec4 local_foot=TransformSkeletonPoint(inverse,foot);
    return (local_foot[1]-Word(0x3ccccccd))-local_contact[1];
}
Mat4 BoardBlend(const Mat4& original,const Mat4& target,float weight)
{
    Vec4 translation;for(unsigned i=0;i<4;++i)translation[i]=std::fma(target[3][i],weight,original[3][i]*(1.0f-weight));
    Mat4 a=OrthonormalizeSkeletonFrame(original),b=OrthonormalizeSkeletonFrame(target);a[3]={};b[3]={};
    auto output=InterpolateMatrix(a,b,weight).first;output[3]=translation;return output;
}
}
void UpdateModes(std::array<LimbStatus,4>& limbs,bool feet_enabled,std::uint32_t flags)
{
    const std::array<bool,4> enabled{{feet_enabled,feet_enabled,(flags&0x80)!=0,(flags&0x100)!=0}};
    for(unsigned i=0;i<4;++i)
    {
        auto& limb=limbs[i];const Mode fallback=enabled[i]?Mode::OnDeck:Mode::Disabled;
        switch(limb.mode)
        {
        case Mode::Disabled:
            limb.board_blend=0.0f;
            if(limb.external_target_set){limb.mode=Mode::External;limb.external_blend=limb.target_blend;}
            else if(limb.local_target_set){limb.mode=Mode::Local;limb.external_blend=limb.target_blend;limb.external_target_local_delta={};}
            else{limb.mode=fallback;limb.external_blend=0.0f;}break;
        case Mode::OnDeck:
            if(limb.external_target_set){limb.mode=Mode::External;limb.external_blend=limb.target_blend;}
            else if(limb.local_target_set){limb.mode=Mode::Local;limb.external_blend=limb.target_blend;limb.external_target_local_delta={};}
            else if(limb.board_blend==0.0f){limb.mode=fallback;limb.external_blend=0.0f;}break;
        case Mode::External:if(!limb.external_target_set)limb.mode=Mode::Local;break;
        case Mode::Local:
            if(limb.external_target_set){limb.mode=Mode::External;limb.external_blend=limb.target_blend;}
            if(!limb.local_target_set&&limb.external_blend==0.0f){limb.mode=fallback;limb.external_target_local_delta={};}break;
        }
    }
}
void UpdateBlends(std::array<LimbStatus,4>& limbs,float half_width,float total_half_length,std::uint32_t flags,const BlendSettings& settings)
{
    const Vec4 base{{half_width,0.0f,total_half_length,0.0f}};Vec4 inner,outer;
    for(unsigned i=0;i<4;++i){inner[i]=base[i]+settings.hand_inner_padding[i];outer[i]=inner[i]+settings.hand_outer_padding[i];}
    const float step=settings.board_blend_step;
    for(unsigned i=0;i<4;++i)
    {
        auto& limb=limbs[i];
        switch(limb.mode)
        {
        case Mode::Disabled:break;
        case Mode::External:limb.external_blend=limb.target_blend;limb.board_blend=Positive(limb.board_blend-step);break;
        case Mode::Local:
            limb.external_blend=limb.local_target_set?1.0f:Positive(limb.external_blend-settings.external_blend_step);
            limb.board_blend=Positive(limb.board_blend-step);break;
        case Mode::OnDeck:
            if(i<2)Approach(limb.board_blend,(flags&0x08000000)!=0?0.0f:1.0f,step);
            else
            {
                Vec4 p;for(unsigned j=0;j<4;++j)p[j]=std::fabs(limb.part_position[j]);
                if(limb.board_blend>0.0f||(p[0]<outer[0]&&p[1]<outer[1]&&p[2]<outer[2]))
                {
                    float target=1.0f;
                    for(unsigned axis:{0u,2u,1u})if(p[axis]>inner[axis])
                    {
                        const float candidate=1.0f-(p[axis]-inner[axis])/settings.hand_outer_padding[axis];
                        if(axis==0)target=candidate;else if(axis==2)target=Select(target-candidate,candidate,target);else target=Select(candidate-target,target,candidate);
                    }
                    target=Positive(target);target=Select(1.0f-target,target,1.0f);Approach(limb.board_blend,target,step);
                }
            }break;
        }
    }
}
void PrepareAnimationTarget(LimbStatus& status,LimbFrames& frames,LimbBinding binding,const std::array<Mat4,24>& animation,const Mat4& animation_to_world,const Mat4& inverse_animation_board,Vec4 contact_bounds)
{
    if(status.mode!=Mode::OnDeck&&!(status.board_blend>0.0f)&&status.external_blend>=1.0f)return;
    const Mat4& animated=animation[binding.part];frames.board=ComposeSkeletonAffine(inverse_animation_board,frames.target);
    status.part_position=frames.board[3];frames.world=ComposeSkeletonAffine(animation_to_world,animated);
    frames.within_contact_bounds=true;
    for(unsigned i=0;i<3;++i)if(status.part_position[i]>contact_bounds[i]||-contact_bounds[i]>status.part_position[i])frames.within_contact_bounds=false;
    if(binding.parent_part)
    {
        const Mat4 relative=ComposeSkeletonAffine(InverseSkeletonRigid(animated),animation[*binding.parent_part]);
        frames.parent_board=ComposeSkeletonAffine(frames.board,relative);frames.parent_world=ComposeSkeletonAffine(frames.world,relative);
    }
}
void UpdateExternal(ExternalTarget& target,LimbStatus& status,LimbFrames& frames,LimbBinding binding,const std::array<Mat4,24>& animation,const Mat4& animation_to_world,const Mat4& world_to_animation)
{
    const Mat4& animated=animation[binding.part];const Mat4 original=ComposeSkeletonAffine(animation_to_world,animated);Mat4 rotation=SkeletonIdentity;
    if(target.normal_blend>0.0f)
    {
        Vec4 axis=Cross3(Vec4{{0,1,0,0}},target.normal);const float magnitude=Length3(axis);
        if(magnitude>0.05f)
        {
            const float inverse=RefinedReciprocal(magnitude,2);for(float& v:axis)v=inverse*v;
            float angle=Asin(magnitude);angle=Select(-0.71f-angle,-0.71f,angle);angle=Select(0.71f-angle,angle,0.71f);
            rotation=AxisRotation(axis,angle*target.normal_blend);
        }
        if(!target.normal_set){const float next=target.normal_blend-0.2f;target.normal_blend=Select(-next,0.0f,next);}
    }
    if(status.mode==Mode::Local)
    {
        Vec4 desired,delta;
        for(unsigned i=0;i<4;++i){desired[i]=std::fma(target.animation_position[i]-animated[3][i],status.target_blend,status.external_target_local_delta[i]*(1.0f-status.target_blend));delta[i]=desired[i]-status.external_target_local_delta[i];}
        const Vec4 change=LimitLength3(delta,0.025f);
        for(unsigned i=0;i<4;++i){status.external_target_local_delta[i]+=change[i];target.animation_position[i]=animated[3][i]+desired[i];}
        target.world_position=TransformSkeletonPoint(animation_to_world,target.animation_position);
    }
    else target.animation_position=TransformSkeletonPoint(world_to_animation,target.world_position);
    Vec4 delta;for(unsigned i=0;i<4;++i)delta[i]=target.world_position[i]-original[3][i];const Vec4 offset=LimitLength3(delta,0.7f);
    Mat4 from_origin=SkeletonIdentity;for(unsigned i=0;i<4;++i)from_origin[3][i]=-original[3][i];
    const Mat4 rotated=ComposeSkeletonAffine(rotation,from_origin);Mat4 to_origin=SkeletonIdentity;
    for(unsigned i=0;i<4;++i)to_origin[3][i]=original[3][i]+offset[i];
    const Mat4 adjustment=ComposeSkeletonAffine(to_origin,rotated);frames.external_world=ComposeSkeletonAffine(adjustment,original);
    if(binding.parent_part){const Mat4 relative=ComposeSkeletonAffine(InverseSkeletonRigid(animated),animation[*binding.parent_part]);frames.external_parent_world=ComposeSkeletonAffine(frames.external_world,relative);}
}
void BlendFrames(const std::array<LimbStatus,4>& statuses,std::array<LimbFrames,4>& frames,const std::array<LimbBinding,4>& bindings,const Mat4& physical_board,const Mat4& animation_to_world,const Mat4& animated_board)
{
    Mat4 board=physical_board;board[3]=TransformSkeletonPoint(animation_to_world,animated_board[3]);
    for(unsigned i=0;i<4;++i)
    {
        const auto& status=statuses[i];auto& frame=frames[i];if(status.mode==Mode::Disabled)continue;
        if(status.board_blend>0.0f)
        {
            frame.world=BoardBlend(frame.world,ComposeSkeletonAffine(board,frame.board),status.board_blend);
            if(bindings[i].parent_part)frame.parent_world=BoardBlend(frame.parent_world,ComposeSkeletonAffine(board,frame.parent_board),status.board_blend);
        }
        if(status.mode==Mode::External||status.mode==Mode::Local)
        {
            if(status.external_blend>=1.0f){frame.world=frame.external_world;frame.parent_world=frame.external_parent_world;}
            else{frame.world=InterpolateAffine(frame.world,frame.external_world,status.external_blend);frame.parent_world=InterpolateAffine(frame.parent_world,frame.external_parent_world,status.external_blend);}
        }
    }
}
void UpdateContacts(ContactState& state,const std::array<LimbStatus,4>& statuses,std::array<LimbFrames,4>& frames,const UpdateInput& input)
{
    state.support_failed_this_update=false;const bool requires_support=(input.flags_2468&0x42000000)!=0;
    for(unsigned foot=0;foot<2;++foot)
    {
        auto& contact=state.feet[foot];auto& frame=frames[foot];bool failed=false;
        if(statuses[foot].mode==Mode::OnDeck&&input.contact_bone==input.foot_bones[foot])
        {
            switch(contact.query_state)
            {
            case 1:
            {
                const Vec4 local=TransformSkeletonPoint(input.inverse_contact_board,contact.position);const float height=local[1]+Word(0x3da8f5c3);
                if(height<=Word(0x3e99999a))
                {
                    contact.desired_offset=(input.flags_2468&0x01800000)==0?LimitOffset(height):0.0f;ApproachContact(contact);
                    const float distance=DistanceToContact(contact,frame,input.contact_board,input.inverse_contact_board);
                    if(distance<0.0f&&distance>Word(0xbe99999a))contact.offset-=distance;
                    AddOffset(frame,input.contact_board,contact.offset);
                    failed=requires_support&&distance>Word(0x3cf5c28f)&&contact.offset<Word(0xbc23d70a);
                }
                else{contact.desired_offset=LimitOffset(contact.desired_offset);ApproachContact(contact);AddOffset(frame,input.contact_board,contact.offset);failed=requires_support||input.hips_world_position[1]>Word(0x3f333333);}
                break;
            }
            case 0:case 2:contact.desired_offset=LimitOffset(contact.desired_offset);ApproachContact(contact);AddOffset(frame,input.contact_board,contact.offset);failed=contact.query_state==2&&requires_support;break;
            default:break;
            }
            if(input.current_contacts[foot]){contact.position=*input.current_contacts[foot];contact.query_state=1;}else contact.query_state=2;
        }
        else{contact.query_state=0;contact.desired_offset=0.0f;ApproachContact(contact);AddOffset(frame,input.contact_board,contact.offset);}
        if(failed){state.support_failed=true;state.support_failed_this_update=true;}
    }
}
std::array<bool,4> Update(State& state,const UpdateInput& input,const Geometry& geometry,const Settings& settings,std::array<Mat4,24>& drives)
{
    for(unsigned limb=0;limb<4;++limb)state.frames[limb].target=input.targets[limb];
    UpdateModes(state.limbs,state.feet_enabled,input.flags_2472);
    UpdateBlends(state.limbs,settings.deck_half_width,settings.deck_total_half_length,input.flags_2480,settings.blend);
    const Mat4 inverse_animation_board=InverseSkeletonRigid(input.animation[0]);
    for(unsigned limb=0;limb<4;++limb)
    {
        state.frames[limb].within_contact_bounds=false;
        if(state.limbs[limb].mode==Mode::External||state.limbs[limb].mode==Mode::Local)
            UpdateExternal(state.external_targets[limb],state.limbs[limb],state.frames[limb],Limbs[limb],input.animation,input.animation_to_world,input.world_to_animation);
        PrepareAnimationTarget(state.limbs[limb],state.frames[limb],Limbs[limb],input.animation,input.animation_to_world,inverse_animation_board,settings.contact_bounds);
    }
    BlendFrames(state.limbs,state.frames,Limbs,input.physical_board,input.animation_to_world,input.animation[0]);
    UpdateContacts(state.contacts,state.limbs,state.frames,input);
    return UpdateDrives(state.limbs,state.frames,Limbs,geometry,input.original_animation,drives,input.world_to_animation,settings.angle_limits);
}
}
