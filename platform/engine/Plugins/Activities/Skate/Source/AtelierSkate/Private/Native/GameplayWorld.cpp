// SPDX-License-Identifier: Apache-2.0
#include "GameplayWorld.h"
#include <algorithm>
#include <charconv>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <numeric>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
// This host adapter used glam ordinary Vec3 arithmetic, independently of the
// recovered solver's explicit FMA and reciprocal-refinement operations.
Vec3 HostCross(Vec3 a,Vec3 b)
{return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
std::string DebugFloat(float value)
{
    if(std::isnan(value))return "NaN";
    if(std::isinf(value))return std::signbit(value) ? "-inf" : "inf";
    char buffer[64];const auto converted=std::to_chars(buffer,buffer+sizeof(buffer),value);
    if(converted.ec!=std::errc{})std::abort();
    std::string text(buffer,converted.ptr);const auto exponent=text.find('e');
    if(exponent!=std::string::npos)
    {
        auto first=exponent+1;
        if(text[first]=='+')text.erase(first,1);
        if(text[first]=='-')++first;
        while(first+1<text.size()&&text[first]=='0')text.erase(first,1);
    }
    else if(text.find('.')==std::string::npos)text+=".0";
    return text;
}
std::string DebugPoints(const std::array<Vec3,3>& points)
{
    std::string text="[";
    for(std::size_t i=0;i<3;++i)
    {
        if(i)text+=", ";
        text+="["+DebugFloat(points[i].x)+", "+DebugFloat(points[i].y)+", "+DebugFloat(points[i].z)+"]";
    }
    return text+"]";
}
std::uint32_t Word(float value)
{std::uint32_t word;std::memcpy(&word,&value,4);return word;}
std::int64_t WeldCoordinate(float value)
{
    const double scaled=std::round(double(value)*(1.0/double(0.001f)));
    // Rust's float-to-integer conversion saturates rather than invoking UB.
    if(std::isnan(scaled))return 0;
    if(scaled>=double(std::numeric_limits<std::int64_t>::max()))return std::numeric_limits<std::int64_t>::max();
    if(scaled<=double(std::numeric_limits<std::int64_t>::min()))return std::numeric_limits<std::int64_t>::min();
    return std::int64_t(scaled);
}
std::int32_t TotalOrder(float value)
{
    std::int32_t bits;std::memcpy(&bits,&value,4);
    bits^=std::int32_t(std::uint32_t(bits>>31)>>1);return bits;
}
bool BuildRails(const GameplayWorldSnapshot& source,
    std::shared_ptr<const PlayerGrindStaticProvider>& output,std::string& error)
{
    if(source.rails.size()>UINT16_MAX)
    {error="Pegasus spline table exceeds its uint16 rail count";return false;}
    PlayerGrindConvertedData data;
    for(std::size_t rail=0;rail<source.rails.size();++rail)
    {
        const auto& points=source.rails[rail];
        const auto name="iw4_edge_"+std::to_string(rail);
        if(points.size()<2){error="Rail "+name+" needs two points";return false;}
        std::uint64_t id=1469598103934665603ull;
        const auto hash=[&](std::uint8_t byte){id=(id^byte)*1099511628211ull;};
        for(unsigned char byte:name)hash(byte);
        for(const auto& point:points)for(float value:point)
        {
            const auto word=Word(value);
            for(int shift=24;shift>=0;shift-=8)hash(std::uint8_t(word>>shift));
        }
        const std::array<std::uint64_t,2> guids{id,0x2c7017070007004aull};
        data.rail_guids.push_back(guids);
        for(std::size_t segment=0;segment+1<points.size();++segment)
        {
            const auto& start=points[segment];const auto& end=points[segment+1];
            // Preserve the original authored cubic and decoded chord rounding.
            // The chord is (A+B)+(C+D); it need not equal the source endpoint.
            Vec4 chord{},begin{start[0],start[1],start[2],1};
            for(std::size_t i=0;i<3;++i)
            {
                const float delta=end[i]-start[i],a=-2.0f*delta,b=3.0f*delta;
                if(!std::isfinite(a)||!std::isfinite(b)||!std::isfinite(start[i])
                    ||!std::isfinite(VectorMin(start[i],end[i]))||!std::isfinite(VectorMax(start[i],end[i])))
                {error="Non-finite spline data in "+name;return false;}
                chord[i]=(a+b)+(0.0f+start[i]);
            }
            chord[3]=1.0f;
            const auto delta=Subtract(Vec3{chord[0],chord[1],chord[2]},Vec3{begin[0],begin[1],begin[2]});
            const float tolerance=1.0f/65536.0f;
            const bool vertical=std::abs(delta.x)<=tolerance && std::abs(delta.z)<=tolerance;
            data.primitives.push_back({begin,chord,std::uint64_t(rail)+1});
            data.metadata.push_back({guids,std::uint32_t(segment),vertical ? 0x80000000u : 0u});
            PlayerGrindBounds bounds;
            for(std::size_t i=0;i<3;++i)
            {bounds.min[i]=VectorMin(begin[i],chord[i]);bounds.max[i]=VectorMax(begin[i],chord[i]);}
            data.authored_bounds.push_back(bounds);data.source_rail_indices.push_back(rail);
        }
    }
    // The authored spline table is validated in full before its contact chords
    // are decoded. Preserve that failure order across different rails.
    for(std::size_t segment=0;segment<data.primitives.size();++segment)
    {
        const auto& primitive=data.primitives[segment];
        const auto delta=Subtract(Vec3{primitive.end[0],primitive.end[1],primitive.end[2]},
            Vec3{primitive.start[0],primitive.start[1],primitive.start[2]});
        if(!std::isfinite(Dot3(delta,delta)))
        {error="Spline segment "+std::to_string(segment)+" has a non-finite contact chord";return false;}
    }
    if(!data.primitives.empty())
    {
        std::vector<std::size_t> indices(data.primitives.size());std::iota(indices.begin(),indices.end(),0);
        data.assets.push_back({{"","host-authored",0,0},std::move(indices),false});
    }
    auto provider=PlayerGrindStaticProvider::FromConverted(std::move(data),error);
    if(!provider)return false;
    output=std::make_shared<PlayerGrindStaticProvider>(std::move(*provider));return true;
}
}
bool BuildGameplayWorld(const GameplayWorldSnapshot& source,ContactMaterial material,
    std::optional<PreparedGameplayWorld>& output,std::string& error)
{
    // Welding defines adjacency only; contact vertices retain source precision.
    std::map<std::array<std::int64_t,3>,std::size_t> welded;
    std::vector<Vec3> positions,normals;
    std::vector<std::array<std::size_t,3>> vertices;
    for(const auto& triangle:source.triangles)
    {
        std::array<std::size_t,3> ids;
        for(std::size_t corner=0;corner<3;++corner)
        {
            const auto p=triangle[corner];
            const std::array<std::int64_t,3> key{WeldCoordinate(p.x),WeldCoordinate(p.y),WeldCoordinate(p.z)};
            const auto found=welded.find(key);
            if(found==welded.end()){ids[corner]=positions.size();welded.emplace(key,positions.size());positions.push_back(p);}
            else ids[corner]=found->second;
        }
        const auto cross=HostCross(Subtract(triangle[1],triangle[0]),Subtract(triangle[2],triangle[0]));
        const float inverse=1.0f/std::sqrt(Dot3(cross,cross));
        if(!std::isfinite(inverse)||!(inverse>0))
        {error="Invalid SKATE collision triangle normal";return false;}
        vertices.push_back(ids);normals.push_back(Scale(cross,inverse));
    }
    if(!source.surfaces.empty()&&source.surfaces.size()!=source.triangles.size())
    {error="SKATE collision surfaces do not match its triangles";return false;}
    std::vector<std::array<float,3>> cosines(vertices.size(),{1,1,1});
    constexpr std::uint32_t one_sided=0x10,use_edge_cosines=0x100;
    std::vector<std::uint32_t> flags(vertices.size(),one_sided|use_edge_cosines|0xe0);
    struct Incident {std::size_t triangle,edge,a,b;};
    std::map<std::pair<std::size_t,std::size_t>,std::vector<Incident>> edges;
    for(std::size_t i=0;i<vertices.size();++i)for(std::size_t edge=0;edge<3;++edge)
    {
        const auto a=vertices[i][edge],b=vertices[i][(edge+1)%3];
        edges[{std::min(a,b),std::max(a,b)}].push_back({i,edge,a,b});
    }
    for(const auto& entry:edges)for(const auto& face:entry.second)
    {
        std::optional<std::size_t> other;float best=0;
        for(const auto& candidate:entry.second)
        {
            if(candidate.triangle==face.triangle || candidate.a!=face.b || candidate.b!=face.a)continue;
            const float dot=Dot3(normals[face.triangle],normals[candidate.triangle]);
            // Iterator::max_by chooses the last equal maximum.
            if(!other || TotalOrder(dot)>=TotalOrder(best)){other=candidate.triangle;best=dot;}
        }
        if(!other)continue;
        const float cosine=std::clamp(best,-1.0f,1.0f);
        const float orientation=Dot3(Subtract(positions[face.b],positions[face.a]),
            HostCross(normals[face.triangle],normals[*other]));
        cosines[face.triangle][face.edge]=cosine;
        if(orientation<=-1.0e-6f || cosine>=1.0f-1.0e-5f)flags[face.triangle]&=~(0x20u<<face.edge);
    }
    std::vector<std::vector<std::size_t>> adjacent(positions.size());
    for(std::size_t i=0;i<vertices.size();++i)for(auto vertex:vertices[i])adjacent[vertex].push_back(i);
    for(std::size_t vertex=0;vertex<adjacent.size();++vertex)
    {
        const auto& faces=adjacent[vertex];const auto reference=normals[faces[0]];
        if(std::all_of(faces.begin(),faces.end(),[&](auto i){return std::abs(Dot3(reference,normals[i])-1.0f)<=0.01f;}))
            for(auto i:faces)for(std::size_t corner=0;corner<3;++corner)
                if(vertices[i][corner]==vertex)flags[i]|=0x200u<<corner;
    }
    std::vector<WorldTriangle> triangles;triangles.reserve(source.triangles.size());
    QueryMetadata metadata;metadata.packed_surfaces.resize(source.triangles.size(),0);
    for(std::size_t i=0;i<source.triangles.size();++i)
    {
        const std::uint32_t surface=source.surfaces.empty()?0u:source.surfaces[i];metadata.packed_surfaces[i]=std::uint16_t(surface);
        auto triangle=WorldTriangle::FromVertices(source.triangles[i],material,surface,flags[i],cosines[i],0);
        if(!triangle){error="Invalid SKATE collision volume at triangle "+std::to_string(i)+": "+DebugPoints(source.triangles[i]);return false;}
        triangles.push_back(std::move(*triangle));
    }
    for(std::size_t start=0;start<triangles.size();start+=64)
    {
        const auto end=std::min(start+64,triangles.size());std::vector<Vec3> points;
        for(auto i=start;i<end;++i)for(auto p:triangles[i].triangle.vertices)points.push_back(p);
        const auto bounds=Bounds::FromPoints(points);
        if(!bounds){error="SKATE collision bounds empty";return false;}
        QueryMesh mesh;mesh.triangle_range={start,end};mesh.local_bounds=*bounds;
        mesh.matching_group=-1;mesh.pool=QueryPool::Ground;metadata.meshes.push_back(mesh);
    }
    const char* diagnostic=nullptr;
    auto world=WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),diagnostic);
    if(!world){error=diagnostic;return false;}
    std::shared_ptr<const PlayerGrindStaticProvider> grind;
    if(!BuildRails(source,grind,error))return false;
    output=PreparedGameplayWorld{std::move(*world),std::move(grind),true};error.clear();return true;
}
}
