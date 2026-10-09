#include "OffboardContactPrivate.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
OffboardProbeLayout OffboardProbeLayout::Stock()
{
    const auto probe=[](float x0,float y0,float z0,float x1,float y1,float z1,float radius){return OffboardLineProbe{{x0,y0,z0,0},{x1,y1,z1,0},radius};};
    OffboardProbeLayout out;out.trajectories={probe(0,1.2f,0,0,-.8f,0,.01f),probe(-.12f,.8f,0,-.17f,-.2f,0,.03f),probe(.12f,.8f,0,.17f,-.2f,0,.03f)};
    std::size_t index=0;auto z=.037500001f;
    for(;;){out.secondary.push_back({probe(0,.8f,z,0,-.8f,z,0),index,std::nullopt});++index;z+=.075000003f;if(!(z<1.7624999f))break;}
    for(unsigned n=0;n<12;++n)
    {
        const auto fraction=float(n)*.090909094f,height=fraction*.8f-(1.0f-fraction)*.8f;
        const auto reverse=height<0?std::optional<std::size_t>(index+1):std::nullopt;
        out.primary.push_back({probe(0,height,0,0,height,1.8f,0),index,reverse});index+=reverse?2:1;
    }
    for(unsigned n=0;n<3;++n){const auto height=(float(n)*2.0f+1.0f)*.099999994f+.8f;out.primary.push_back({probe(0,height,.099999994f,0,height,1.6999999f,.099999994f),index,std::nullopt});++index;}
    return out;
}
OffboardQueryBatch OffboardProbeLayout::Prepare(OffboardToolkitInput input,std::int32_t group) const
{
    const Mat4 surface{{input.right,input.up,input.forward,input.position}},animated{{input.animation_right,input.animation_up,offboard_contact::Cross(input.animation_right,input.animation_up),input.position}};
    const auto transform=[](OffboardLineProbe p,const Mat4& f)
    {
        const auto point=[&](Vec4 v){return offboard_contact::Madd(f[2],v[2],offboard_contact::Madd(f[1],v[1],offboard_contact::Madd(f[0],v[0],f[3])));};
        return OffboardLineProbe{point(p.start),point(p.end),p.radius};
    };
    OffboardQueryBatch out;out.input=input;out.matching_group=group;out.mesh_reject_mask=0x6000;
    for(std::size_t n=0;n<3;++n){const auto line=transform(trajectories[n],n==0?surface:animated);out.trajectories[n]={{line.start,offboard_contact::Sub(line.end,line.start),{},1},line.radius,0,0};}
    const auto prepare=[&](const std::vector<OffboardProbeDescriptor>& source,std::vector<OffboardProbeDescriptor>& destination)
    {
        for(const auto& descriptor:source){const auto line=transform(descriptor.line,surface);out.lines.push_back(line);if(descriptor.reverse_index)out.lines.push_back({line.end,line.start,line.radius});destination.push_back({line,descriptor.forward_index,descriptor.reverse_index});}
    };
    prepare(secondary,out.secondary);prepare(primary,out.primary);return out;
}
void OffboardContactPrefix::ConsumeSupport(OffboardToolkitInput input,const std::array<AirTrajectoryQueryResult,3>& hits,std::uint32_t candidate_flags)
{
    using namespace offboard_contact;const auto main=hits[0];
    if(Valid(main))
    {
        position=main.contact_position;normal=main.landing_normal;support_frame=main.contact_transform;flags_176|=1;
        if(Dot(input.up,Sub(main.contact_position,input.position))<-.1f){flags_176|=8;if((candidate_flags&0x40)!=0)flags_176|=0x40;}
        else flags_176&=~std::uint32_t{8};support_180=main.geometry;
    }
    for(const auto& pair:std::array<std::pair<AirTrajectoryQueryResult,std::uint32_t>,2>{{{hits[1],0x10},{hits[2],0x20}}})
    {const auto& hit=pair.first;const auto height=Dot(Sub(hit.contact_position,input.position),input.up);if(Valid(hit)&&height<.2f&&height>-.2f){flags_176|=pair.second;if(Valid(main)&&hit.landing_normal[1]>normal[1])normal=hit.landing_normal;}}
}
Vec4 OffboardTriangleNormal(const std::array<Vec4,3>& vertices)
{
    using namespace offboard_contact;const auto normal=Cross(Sub(vertices[1],vertices[0]),Sub(vertices[2],vertices[0]));return Scale(normal,Inverse(Dot(normal,normal)));
}
bool OffboardContactSamples::Insert(OffboardToolkitInput input,Vec4 position,Vec4 normal,std::uint32_t category,float sort_override,std::uint32_t provenance)
{
    using namespace offboard_contact;const auto delta=Sub(position,input.position);const auto forward=Dot(input.forward,delta),height=Dot(input.up,delta);const auto high=height>=.79000002f&&forward>=0;
    normal=Sub(normal,Scale(input.right,Dot(normal,input.right)));const auto magnitude=Length(normal);
    normal=magnitude>=.001f?Scale(normal,Reciprocal(magnitude)):height<0?input.forward:Scale(input.forward,-1);
    const auto to_ground=category==1||high;if((to_ground&&ground.size()==64)||(!to_ground&&forward<0))return false;
    auto flags=provenance==1?std::uint32_t{1}:provenance==2?std::uint32_t{4}:std::uint32_t{0};if(high)flags|=8;if(category==2)flags|=0x10;
    const OffboardContactSample sample{position,normal,forward,height,flags,sort_override>=0?sort_override:forward};
    if(to_ground){ground.push_back(sample);original_ground_count=ground.size();}else other.push_back(sample);return true;
}
}
