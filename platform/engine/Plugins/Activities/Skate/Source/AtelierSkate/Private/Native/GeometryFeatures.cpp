// SPDX-License-Identifier: Apache-2.0
#include "GeometryFeatures.h"
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <cstring>
#include <optional>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t word) { float value;std::memcpy(&value,&word,4);return value; }
std::uint32_t Word(float value) { std::uint32_t word;std::memcpy(&word,&value,4);return word; }
Vec4 Load(const std::uint32_t* words) { return {Scalar(words[0]),Scalar(words[1]),Scalar(words[2]),Scalar(words[3])}; }
Vec4 Load(const DirectionWords& words) { return Load(words.data()); }
void Store(std::uint32_t* words,const Vec4& value) { for (unsigned i=0;i<4;++i) words[i]=Word(value[i]); }
DirectionWords Words(const Vec4& value) { return {Word(value[0]),Word(value[1]),Word(value[2]),Word(value[3])}; }
Vec4 Scale(const Vec4& a,float b) { return {a[0]*b,a[1]*b,a[2]*b,a[3]*b}; }
Vec4 Sub(const Vec4& a,const Vec4& b) { return {a[0]-b[0],a[1]-b[1],a[2]-b[2],a[3]-b[3]}; }
Vec4 Add(const Vec4& a,const Vec4& b) { return {a[0]+b[0],a[1]+b[1],a[2]+b[2],a[3]+b[3]}; }
Vec4 Neg(const Vec4& a) { return {-a[0],-a[1],-a[2],-a[3]}; }
Vec4 Madd(const Vec4& a,float b,const Vec4& c)
{ return {std::fma(a[0],b,c[0]),std::fma(a[1],b,c[1]),std::fma(a[2],b,c[2]),std::fma(a[3],b,c[3])}; }
float Squared(const Vec4& value) { return Dot3(value,value); }
float Length(const Vec4& value)
{
    const float squared=Squared(value);
    return squared==0.0f ? 0.0f : squared*InverseLengthSquared(squared,2);
}
void Project(const GpRecord& gp,PrimitiveKind kind,DirectionWords direction,ProjectionInterval& output,bool batch)
{
    const Vec4 axis=Load(direction);
    const float center=Dot3(Load(gp.data()),axis);
    float low=center,high=center;
    switch (kind)
    {
    case PrimitiveKind::Sphere:break;
    case PrimitiveKind::Capsule:
    {
        const float radius=std::fabs(Dot3(Load(gp.data()+16),axis))*Scalar(gp[28]);
        low=center-radius; high=center+radius; break;
    }
    case PrimitiveKind::Triangle:
    {
        const float second=Dot3(Load(gp.data()+8),axis),third=Dot3(Load(gp.data()+12),axis);
        const float minimum=center<second ? center:second,maximum=center>second ? center:second;
        low=minimum<third ? minimum:third; high=maximum>third ? maximum:third; break;
    }
    case PrimitiveKind::Box:
    {
        std::array<float,3> extent{};
        for (unsigned i=0;i<3;++i)
        {
            const Vec4 column=Load(gp.data()+4+i*4); const float half=Scalar(gp[28+i]);
            extent[i]=std::fabs(batch ? Dot3(Scale(column,half),axis) : Dot3(column,axis)*half);
        }
        const float radius=(extent[0]+extent[1])+extent[2]; low=center-radius;high=center+radius;break;
    }
    }
    std::fill_n(output.begin(),4,Word(low)); std::fill_n(output.begin()+4,4,Word(high));
}
void Append(const Vec4& candidate,SeparatingAxes& output,std::size_t& count)
{
    output[count]=Words(candidate);
    if (Length(candidate)>Scalar(0x34000000))
    {
        output[count]=Words(Scale(candidate,InverseLengthSquared(Squared(candidate),2))); ++count;
    }
}
void TriangleSegment(MaximumFeature& feature,unsigned index,const Vec4& point,const Vec4& edge,std::uint32_t length)
{
    const unsigned offset=4+index*16;
    Store(feature.data()+offset,point); Store(feature.data()+offset+4,edge);
    std::fill_n(feature.begin()+offset+12,4,length);
}
constexpr std::array<std::array<unsigned,2>,3> Other={{{1,2},{0,2},{0,1}}};
constexpr std::array<std::array<float,2>,4> Signs={{{1,1},{1,-1},{-1,-1},{-1,1}}};
Vec4 BoxPlane(const Vec4& axis,const Vec4& direction,std::uint32_t mode)
{
    const Vec4 result=mode!=0 ? Cross3(axis,direction):Cross3(direction,axis);
    const float squared=Squared(result);
    return squared>Scalar(0x34000000) ? Scale(result,InverseLengthSquared(squared,2)):result;
}
void BoxFace(const Vec4& center,const std::array<Vec4,3>& axes,const std::array<float,3>& half,
             unsigned fixed,std::uint32_t mode,const Vec4& direction,MaximumFeature& output)
{
    const float sign=Dot3(axes[fixed],direction)>0.0f ? 1.0f:-1.0f;
    const Vec4 face_center=Madd(axes[fixed],half[fixed]*sign,center);
    const float winding_sign=fixed==1 ? -sign:sign;
    const auto u=Other[fixed][0],v=Other[fixed][1];
    const Vec4 positive_u=Scale(axes[u],half[u]),negative_u=Scale(axes[u],-half[u]);
    const Vec4 positive_v=Scale(axes[v],half[v]),negative_v=Scale(axes[v],-half[v]);
    const Vec4 p=BoxPlane(axes[v],direction,mode),q=BoxPlane(axes[u],direction,mode);
    const float len_u=half[u]*2.0f,len_v=half[v]*2.0f;
    const std::array<Vec4,4> points={Add(Add(face_center,positive_u),positive_v),Add(Add(face_center,positive_u),negative_v),
                                  Add(Add(face_center,negative_u),negative_v),Add(Add(face_center,negative_u),positive_v)};
    std::array<unsigned,4> indices;
    std::array<Vec4,4> directions,planes;
    std::array<float,4> lengths;
    if (static_cast<std::uint32_t>(winding_sign<0.0f)==mode)
    {
        indices={0,1,2,3}; directions={Neg(axes[v]),Neg(axes[u]),axes[v],axes[u]};
        planes={Neg(p),Neg(q),p,q}; lengths={len_v,len_u,len_v,len_u};
    }
    else
    {
        indices={0,3,2,1}; directions={Neg(axes[u]),Neg(axes[v]),axes[u],axes[v]};
        planes={Neg(q),Neg(p),q,p}; lengths={len_u,len_v,len_u,len_v};
    }
    for (unsigned i=0;i<4;++i)
    {
        const unsigned offset=4+i*16;
        Store(output.data()+offset,points[indices[i]]); Store(output.data()+offset+4,directions[i]);
        Store(output.data()+offset+8,planes[i]); std::fill_n(output.begin()+offset+12,4,Word(lengths[i]));
    }
    Store(output.data()+132,Scale(axes[fixed],-winding_sign)); output[140]=4;
}
}

void ProjectDirection(const GpRecord& gp,PrimitiveKind kind,DirectionWords direction,ProjectionInterval& output)
{ Project(gp,kind,direction,output,false); }
void ProjectDirections(const GpRecord& gp,PrimitiveKind kind,const std::vector<DirectionWords>& directions,
                       std::vector<ProjectionInterval>& output)
{
    if (output.size()<directions.size())
    {
        assert(false && "Projection output has insufficient intervals"); std::abort();
    }
    for (std::size_t i=0;i<directions.size();++i) Project(gp,kind,directions[i],output[i],true);
}
std::size_t SeparatingAxisCandidates(const GpRecord& a,const GpRecord& b,SeparatingAxes& output)
{
    std::size_t count=0;
    for (const GpRecord* gp:{&a,&b})
    {
        const std::uint32_t normals=(*gp)[35]>>24;
        if (normals>=1 && normals<=3)
            for (std::uint32_t index=normals;index>0;--index)
            {
                std::copy_n(gp->begin()+index*4,4,output[count].begin()); ++count;
            }
    }
    const std::size_t ae=(a[35]>>16)&255,be=(b[35]>>16)&255;
    if (ae>3 || be>3)
    {
        assert(false && "Native GP contains at most three edges"); std::abort();
    }
    for (std::size_t i=0;i<ae;++i)
        for (std::size_t j=0;j<be;++j)
        {
            const Vec4 candidate=Cross3(Load(a.data()+16+4*i),Load(b.data()+16+4*j));
            const float squared=Squared(candidate); output[count]=Words(candidate);
            if (squared>Scalar(0x3a83126f))
            {
                output[count]=Words(Scale(candidate,InverseLengthSquared(squared,2))); ++count;
            }
        }
    if (ae==1 && be==1)
    {
        const Vec4 edge_a=Load(a.data()+16),edge_b=Load(b.data()+16),perpendicular=Cross3(edge_a,edge_b);
        if (Length(perpendicular)>Scalar(0x34000000))
            for (const Vec4& edge:{edge_a,edge_b})
            {
                const Vec4 candidate=Cross3(edge,perpendicular);
                output[count]=Words(Scale(candidate,InverseLengthSquared(Squared(candidate),2))); ++count;
            }
    }
    if (count) return count;
    const Vec4 delta=Sub(Load(a.data()),Load(b.data()));
    if (ae==1 && be==1)
    {
        const Vec4 edge=Load(a.data()+16); Append(Cross3(Cross3(delta,edge),edge),output,count);
    }
    if (ae+be==1)
    {
        const Vec4 edge=Load((ae ? a:b).data()+16); Append(Cross3(Cross3(delta,edge),edge),output,count);
    }
    if (count) return count;
    Append(delta,output,count); return count;
}
std::pair<DirectionWords,DirectionWords> BestSeparatingDirection(const GpRecord& a,PrimitiveKind a_kind,
                                                               const GpRecord& b,PrimitiveKind b_kind)
{
    SeparatingAxes axes{}; std::size_t count=SeparatingAxisCandidates(a,b,axes);
    if (!count) { axes[0]={0,0,Word(1.0f),0};count=1; }
    const std::vector<DirectionWords> directions(axes.begin(),axes.begin()+count);
    std::vector<ProjectionInterval> ai(16),bi(16);
    ProjectDirections(a,a_kind,directions,ai); ProjectDirections(b,b_kind,directions,bi);
    std::size_t selected=0;float best=0.0f;bool flip=false;
    for (std::size_t i=0;i<count;++i)
    {
        const float forward=Scalar(ai[i][0])-Scalar(bi[i][4]),reverse=Scalar(bi[i][0])-Scalar(ai[i][4]);
        const bool reversed=forward>reverse; const float separation=reversed ? forward:reverse;
        if (!i || separation>best) {best=separation;selected=i;flip=reversed;}
    }
    DirectionWords normal=axes[selected];
    if (flip) for (auto& word:normal) word^=0x80000000u;
    return {{Word(best),Word(best),Word(best),Word(best)},normal};
}
void InitializeFeatureSegment(FeatureSegment& output,DirectionWords origin,DirectionWords end)
{
    std::copy(origin.begin(),origin.end(),output.begin());
    const Vec4 delta=Sub(Load(end),Load(origin)); const float squared=Squared(delta);
    const float reciprocal=InverseLengthSquared(squared,1);
    const float length=squared>Scalar(0x34000000) ? (squared==0.0f ? 0.0f:squared*reciprocal):0.0f;
    std::fill_n(output.begin()+12,4,Word(length));
    const float r=RefinedReciprocal(length,1);
    const Vec4 direction=squared>Scalar(0x34000000) ? Scale(delta,r):Vec4{};
    Store(output.data()+4,direction);
}
void CapsuleMaximumFeature(const GpRecord& gp,DirectionWords direction,MaximumFeature& output,FeatureSegment& scratch)
{
    const Vec4 axis=Load(gp.data()+16),normal=Load(direction),center=Load(gp.data());
    const float projection=Dot3(axis,normal),half=Scalar(gp[28]);
    if (std::fabs(projection)<Scalar(0x3d4ccccd))
    {
        const Vec4 scaled=Scale(axis,half);
        InitializeFeatureSegment(scratch,Words(Add(center,scaled)),Words(Sub(center,scaled)));
        std::copy(scratch.begin(),scratch.end(),output.begin()+4); output[140]=1;
    }
    else
    {
        const Vec4 point=projection>0.0f ? Madd(axis,half,center):Sub(center,Scale(axis,half));
        Store(output.data()+136,point); output[140]=0;
    }
    output[0]=0;
}
void BuildFeatureEdgePlanes(MaximumFeature& feature,std::uint32_t mode,DirectionWords direction)
{
    const auto count=static_cast<std::int32_t>(feature[140]);
    if (count<=0) return;
    if (count>8)
    {
        assert(false && "Native feature storage holds at most eight segments"); std::abort();
    }
    const Vec4 normal=mode==0 ? Neg(Load(direction)):Load(direction);
    for (std::int32_t i=0;i<count;++i)
    {
        const auto offset=4+static_cast<std::size_t>(i)*16;
        const Vec4 plane=Cross3(Load(feature.data()+offset+4),normal);
        const float squared=Squared(plane),r=InverseLengthSquared(squared,1);
        Store(feature.data()+offset+8,Scale(plane,squared>Scalar(0x34000000) ? r:0.0f));
    }
}
void TriangleMaximumFeature(const GpRecord& gp,std::uint32_t mode,DirectionWords direction,MaximumFeature& output)
{
    const Vec4 normal=Load(gp.data()+4),query=Load(direction); const float projected=Dot3(query,normal);
    const std::array<Vec4,3> points={Load(gp.data()),Load(gp.data()+8),Load(gp.data()+12)};
    const std::array<Vec4,3> edges={Load(gp.data()+16),Load(gp.data()+20),Load(gp.data()+24)};
    if (std::fabs(projected)>Scalar(0x3f733333))
    {
        if (static_cast<std::uint32_t>(projected<0.0f)==mode)
        {
            constexpr std::array<unsigned,3> order={0,2,1};
            for (unsigned i=0;i<3;++i) TriangleSegment(output,i,points[order[i]],edges[i],gp[28+i]);
            output[0]=8;
        }
        else
        {
            for (unsigned i=0;i<3;++i) TriangleSegment(output,i,points[i],Neg(edges[2-i]),gp[30-i]);
            output[0]=0;
        }
        Store(output.data()+132,normal); output[140]=3;
    }
    else
    {
        std::array<float,3> p{},e{};
        for (unsigned i=0;i<3;++i) {p[i]=Dot3(query,points[i]);e[i]=std::fabs(Dot3(query,edges[i]));}
        const float threshold=Scalar(0x3d4ccccd);
        unsigned point;std::optional<unsigned> edge;
        if (p[0]>p[1] && p[0]>p[2])
        {
            point=0;
            if (threshold>e[0] && e[2]>e[0]) edge=0;
            else if (threshold>e[2]) edge=2;
        }
        else if (p[1]>p[2])
        {
            point=1;
            if (threshold>e[1] && e[2]>e[1]) edge=1;
            else if (threshold>e[2]) edge=2;
        }
        else
        {
            point=2;
            if (threshold>e[0] && e[1]>e[0]) edge=0;
            else if (threshold>e[1]) edge=1;
        }
        if (edge)
        {
            constexpr std::array<unsigned,3> order={0,2,1};
            TriangleSegment(output,0,points[order[*edge]],edges[*edge],gp[28+*edge]); output[140]=1;
        }
        else {Store(output.data()+136,points[point]);output[140]=0;}
    }
    BuildFeatureEdgePlanes(output,mode,direction);
}
void BoxMaximumFeature(const GpRecord& gp,std::uint32_t mode,DirectionWords direction,MaximumFeature& output,
                       DirectionWords incoming_edge_plane)
{
    const Vec4 center=Load(gp.data()),query=Load(direction);
    const std::array<Vec4,3> axes={Load(gp.data()+4),Load(gp.data()+8),Load(gp.data()+12)};
    const std::array<float,3> half={Scalar(gp[28]),Scalar(gp[29]),Scalar(gp[30])};
    unsigned small=0,small_axis=0,large_axis=0;
    for (unsigned i=0;i<3;++i)
        if (std::fabs(Dot3(query,axes[i]))<Scalar(0x3e4ccccd)) {++small;small_axis=i;} else large_axis=i;
    if (small==2) BoxFace(center,axes,half,large_axis,mode,query,output);
    else if (small==1)
    {
        const unsigned u=Other[small_axis][0],v=Other[small_axis][1];
        Vec4 best{};float score=0.0f;
        for (unsigned i=0;i<4;++i)
        {
            const Vec4 point=Madd(axes[v],half[v]*Signs[i][1],Madd(axes[u],half[u]*Signs[i][0],center));
            const float projected=Dot3(point,query);
            if (!i || projected>score) {best=point;score=projected;}
        }
        const Vec4 negative=Sub(best,Scale(axes[small_axis],half[small_axis])),positive=Madd(axes[small_axis],half[small_axis],best);
        FeatureSegment segment{};std::copy(incoming_edge_plane.begin(),incoming_edge_plane.end(),segment.begin()+8);
        InitializeFeatureSegment(segment,Words(negative),Words(positive));
        std::copy(segment.begin(),segment.end(),output.begin()+4);output[140]=1;
    }
    else
    {
        Vec4 best{};float score=0.0f;
        for (unsigned i=0;i<8;++i)
        {
            const float sign=i>3 ? 1.0f:-1.0f;const auto pair=Signs[i%4];
            const Vec4 point=Madd(axes[2],half[2]*pair[1],Madd(axes[1],half[1]*pair[0],Madd(axes[0],half[0]*sign,center)));
            const float projected=Dot3(point,query);
            if (!i || projected>score) {best=point;score=projected;}
        }
        Store(output.data()+136,best);output[140]=0;
    }
    output[0]=0;
}
}
