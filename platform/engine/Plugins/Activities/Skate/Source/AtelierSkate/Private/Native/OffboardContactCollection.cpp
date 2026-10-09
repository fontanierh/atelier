#include "OffboardContactPrivate.h"
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate::offboard_contact
{
float Tangent(float x)
{
    if(x==0)return 0;const auto turns=std::nearbyint(x*Bits(0x3f22f983));
    const auto r=std::fma(-turns,Bits(0x2e85a309),std::fma(-turns,Bits(0x3fc90fdb),x)),q=r*r;
    auto denominator=std::fma(q,std::fma(q,std::fma(q,std::fma(q,Bits(0x3505bba8),Bits(0xb9a37b25)),Bits(0x3cd23cf5)),Bits(0xbeeef582)),1.0f);
    const auto polynomial=std::fma(q,std::fma(q,Bits(0xb795d5b9),Bits(0x3b607415)),Bits(0xbe0895af));auto numerator=std::fma(r,q*polynomial,r);
    if(std::abs(r)<=Bits(0x39800000)){numerator=r;denominator=1;}
    const auto magnitude=std::abs(turns);const auto integer=std::isnan(magnitude)?0:magnitude>=2147483648.0f?2147483647:static_cast<std::int32_t>(magnitude);
    return (integer&1)==0?numerator*Reciprocal(denominator):denominator*Reciprocal(-numerator);
}
void Sort(std::vector<OffboardContactSample>& values)
{std::stable_sort(values.begin(),values.end(),[](const auto& a,const auto& b){return a.sort_distance<b.sort_distance;});}
namespace
{
float FoldedAngle(Vec4 a,Vec4 b)
{
    const auto aa=Dot(a,a),bb=Dot(b,b);float angle=0;
    if(aa>Bits(0x38d1b717)&&bb>Bits(0x38d1b717))
    {const auto value=Dot(Scale(a,Inverse(aa,1)),Scale(b,Inverse(bb,1)));angle=Acos(value< -1?-1:value>1?1:value);}
    const auto turns=angle*Bits(0x3e22f983),fraction=turns-std::floor(turns),signed_angle=(fraction-(fraction>.5f?1.0f:0.0f))*Bits(0x40c90fdb);
    const auto sign=signed_angle<=0?-1.0f:1.0f,magnitude=signed_angle*sign;return sign*(magnitude>1.5707964f?magnitude-3.1415927f:magnitude);
}
const std::optional<OffboardLineHit>& ContactHit(const OffboardQueryResults& results,std::size_t index)
{if(index>=results.lines.size())std::abort();return results.lines[index];}
}
OffboardContactSamples Collect(const OffboardQueryBatch& batch,const OffboardProbeLayout& layout,const OffboardQueryResults& results)
{
    const auto input=batch.input;OffboardContactSamples samples;const auto main=results.trajectories[0];
    if(Valid(main))samples.Insert(input,main.contact_position,main.landing_normal,1,-1,0);
    std::vector<std::optional<Vec4>> edge_points(batch.secondary.size());
    for(const auto& edge:results.edges)
    {
        const auto start=edge[0],end=edge[1],delta=Sub(end,start);
        if(std::abs(FoldedAngle(delta,input.forward))>30.0f*.017453292f)
        {const auto point=PlaneSegment(input.position,input.right,start,end);if(point)samples.Insert(input,*point,input.up,2,-1,0);continue;}
        const auto a=Dot(Sub(start,input.position),input.forward),b=Dot(Sub(end,input.position),input.forward);const auto at_origin=Madd(delta,a/(a-b),start);
        if(std::abs(Dot(input.right,Sub(at_origin,input.position)))>.5f)continue;
        const auto count=std::min({layout.secondary.size(),batch.secondary.size(),edge_points.size()});
        for(std::size_t n=0;n<count;++n)
        {
            const auto z=layout.secondary[n].line.start[2];if(z<VectorMin(a,b)||z>VectorMax(a,b))continue;
            const auto on_edge=Madd(delta,(z-a)/(b-a),start),world_start=batch.secondary[n].line.start;
            const auto projected=Madd(input.up,Dot(input.up,Sub(on_edge,world_start)),world_start);
            if(std::abs(Dot(input.right,Sub(projected,on_edge)))>=.05f)continue;
            if(!edge_points[n]||projected[1]>(*edge_points[n])[1])edge_points[n]=projected;
        }
    }
    for(std::size_t n=0;n<std::min(batch.secondary.size(),edge_points.size());++n)
    {
        const auto& hit=ContactHit(results,batch.secondary[n].forward_index);const auto& edge=edge_points[n];
        if(hit&&edge&&(*edge)[1]>hit->position[1])samples.Insert(input,*edge,input.up,1,-1,0);
        else if(hit)samples.Insert(input,hit->position,hit->normal,1,-1,0);
        else if(edge)samples.Insert(input,*edge,input.up,1,-1,0);
    }
    for(const auto& descriptor:batch.primary)
    {
        const std::array<std::optional<std::size_t>,2> indices{descriptor.forward_index,descriptor.reverse_index};
        for(const auto index:indices)if(index){const auto& hit=ContactHit(results,*index);if(hit)samples.Insert(input,hit->position,hit->normal,0,-1,0);}
    }
    Sort(samples.ground);Sort(samples.other);return samples;
}
void InsertObstacles(OffboardToolkitInput input,OffboardContactSamples& s)
{
    const auto initial=s.ground;
    for(std::size_t pair=1;pair<initial.size();++pair)
    {
        const auto a=initial[pair-1],b=initial[pair];auto low=VectorMin(a.height,b.height),high=VectorMax(a.height,b.height);std::size_t i=0;
        while(i<s.other.size())
        {
            const auto p=s.other[i];
            if(a.forward_distance>p.forward_distance||p.forward_distance>b.forward_distance){++i;continue;}
            if(low>p.height){s.other[i].flags|=2;++i;continue;}
            if(high>p.height||p.sort_distance<a.sort_distance||p.sort_distance>b.sort_distance){++i;continue;}
            auto minimum=i,maximum=i;s.other[i].flags|=2;++i;
            while(i<s.other.size()&&std::abs(p.forward_distance-s.other[i].forward_distance)<=.001f)
            {const auto q=s.other[i];s.other[i].flags|=2;if(q.height>=high&&s.other[minimum].height>q.height)minimum=i;if(q.height>s.other[maximum].height)maximum=i;++i;}
            for(const auto index:std::array<std::size_t,2>{minimum,maximum})s.other[index].flags=(s.other[index].flags&~std::uint32_t{2})|1;
            const auto first=s.other[minimum];s.Insert(input,first.position,first.normal,1,first.sort_distance,1);
            if(first.height>high){low=high;high=first.height;}else if(first.height>low)low=first.height;
            if(minimum!=maximum){const auto q=s.other[maximum];s.Insert(input,q.position,q.normal,1,q.sort_distance,1);}++i;
        }
    }
    Sort(s.ground);
}
namespace
{
void Infill(OffboardToolkitInput input,OffboardContactSamples& s,OffboardContactSample a,OffboardContactSample b,std::size_t index)
{
    const auto p=s.other[index];
    if(Dot(a.normal,b.normal)>.99f&&Dot(a.normal,p.normal)>.99f&&std::abs(Dot(Sub(b.position,a.position),b.normal))<.01f)
    {auto delta=Sub(p.position,a.position);if(Length(delta)<.01f)delta=Sub(p.position,b.position);if(std::abs(Dot(delta,b.normal))<.01f)return;}
    const auto n=ClampNormal(b.height>a.height?Scale(input.forward,-1):input.forward,input.up,p.normal),delta=Sub(b.position,a.position);
    const auto first_end=Madd(Sub(delta,Scale(a.normal,Dot(a.normal,delta))),1.1f,a.position);
    const auto last_start=Sub(b.position,Scale(Sub(delta,Scale(b.normal,Dot(b.normal,delta))),1.1f));
    const std::array<std::optional<Vec4>,2> candidates{PlaneSegment(p.position,n,a.position,first_end),PlaneSegment(p.position,n,last_start,b.position)};
    for(const auto& candidate:candidates)if(candidate)
    {
        const auto d=Sub(*candidate,input.position);const auto x=Dot(input.forward,d),y=Dot(input.up,d);
        if(x>=a.forward_distance&&x<=b.forward_distance&&y>=VectorMin(a.height,b.height)&&y<=VectorMax(a.height,b.height))
        {const auto t=Length(Sub(*candidate,a.position))/Length(delta),order=t*(b.sort_distance-a.sort_distance)+a.sort_distance;s.Insert(input,*candidate,n,1,order,2);s.other[index].flags|=4;}
    }
}
}
void CorrectNormals(OffboardToolkitInput input,OffboardContactSamples& s)
{
    auto previous=input.position;
    for(auto& p:s.ground)
    {const auto height=Dot(Sub(p.position,previous),input.up);p.normal=std::abs(height)<.001f?input.up:ClampNormal(height<=0?input.forward:Scale(input.forward,-1),input.up,p.normal);previous=p.position;}
    const auto initial=s.ground;
    for(std::size_t pair=1;pair<initial.size();++pair)for(std::size_t i=0;i<s.other.size();++i)
    {const auto p=s.other[i];if((p.flags&3)==0&&initial[pair-1].forward_distance<=p.forward_distance&&p.forward_distance<=initial[pair].forward_distance)Infill(input,s,initial[pair-1],initial[pair],i);}
    Sort(s.ground);
}
std::pair<float,std::size_t> Simplify(OffboardToolkitInput input,std::vector<OffboardContactSample>& points)
{
    float obstruction=1.0e10f;if(points.size()<2)return {obstruction,points.size()};auto count=points.size();const auto removed=points.back().sort_distance+1.0f;
    for(std::size_t i=1;i+1<points.size();++i)
    {
        if((points[i].flags&8)!=0){count-=points.size()-1-i;obstruction=Dot(Sub(points[i].position,input.position),input.forward);break;}
        const Vec4 incoming{points[i].forward_distance-points[i-1].forward_distance,points[i].height-points[i-1].height,0,0};
        const Vec4 outgoing{points[i+1].forward_distance-points[i].forward_distance,points[i+1].height-points[i].height,0,0};
        const auto a=Length(incoming),b=Length(outgoing);
        const auto discard=a<.02f||b<.02f||(!(Dot(incoming,outgoing)<0&&Dot(incoming,input.up)>=0)&&Length(Cross(Scale(incoming,Reciprocal(a)),Scale(outgoing,Reciprocal(b))))<.05f);
        if(discard){points[i].sort_distance=removed;--count;}
    }
    Sort(points);return {obstruction,count};
}
Profile BuildProfile(OffboardToolkitInput input,const std::vector<OffboardContactSample>& points,std::size_t count)
{
    if(count>points.size())std::abort();Profile out;
    for(std::size_t i=1;i<count;++i)
    {
        const auto start=points[i-1].position,end=points[i].position,delta=Sub(end,start);const auto distance=Length(delta);if(distance<.0001f)continue;
        const auto direction=Scale(delta,Reciprocal(distance));const auto kind=std::abs(Dot(input.forward,direction))>.5f?std::uint32_t{0}:Dot(input.up,direction)>=0?std::uint32_t{1}:std::uint32_t{2};
        if(kind!=0&&!out.segments.empty()&&out.segments.back().kind==kind)
        {auto& last=out.segments.back();last.end=end;const auto difference=Sub(end,last.start);last.length=Length(difference);last.direction=Scale(difference,Reciprocal(last.length));last.normal=Normalize(Cross(difference,input.right),input.up);}
        else {out.segments.push_back({kind,start,end,direction,Normalize(Cross(delta,input.right),input.up),distance});if(kind==0)out.last_ground=out.segments.size();}
    }
    return out;
}
}
