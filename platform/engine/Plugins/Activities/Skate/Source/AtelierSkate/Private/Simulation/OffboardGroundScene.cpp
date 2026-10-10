#include "OffboardGroundScene.h"
#include "OffboardGroundQueryMath.h"
#include <algorithm>
#include <cstdlib>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
OffboardGroundFrame QueryFrame(AffineTransform f)
{const auto v=[](const std::array<float,3>& a){return Vec3{a[0],a[1],a[2]};};return {v(f.basis.columns[0]),v(f.basis.columns[1]),v(f.basis.columns[2]),f.translation};}
Vec3 Face(const std::array<Vec3,3>& vertices)
{
    using namespace offboard_ground_query;const auto normal=Cross(Sub(vertices[1],vertices[0]),Sub(vertices[2],vertices[0]));
    const auto q=std::fma(normal.z,normal.z,std::fma(normal.y,normal.y,normal.x*normal.x));auto r=1.0f/std::sqrt(q);
    for(unsigned n=0;n<2;++n)r=std::fma(r*.5f,std::fma(-q,r*r,1.0f),r);return Mul(normal,r);
}
void Append(std::vector<OffboardGroundEdge>& output,const std::vector<OffboardGroundEdgeSegment>& segments,OffboardGroundFrame frame,Bounds query)
{
    using namespace offboard_ground_query;
    for(const auto& segment:segments)
    {
        if(output.size()==40)break;
        if(Overlaps(TransformBounds(frame,segment.local_bounds),query))output.push_back({Point(frame,segment.edge.start),Point(frame,segment.edge.end)});
    }
}
void Body(std::vector<OffboardGroundEdge>& output,const OffboardGroundEdgeBody& body,Bounds query)
{if(offboard_ground_query::Overlaps(offboard_ground_query::TransformBounds(body.local_to_world,body.local_bounds),query))Append(output,body.segments,body.local_to_world,query);}
}
std::optional<OffboardGroundScene> OffboardGroundScene::Create(const WorldGeometry& world,OffboardGroundEdgeSources sources,std::string& error)
{
    const char* diagnostic=nullptr;const auto metadata=world.Metadata(diagnostic);if(!metadata){error=diagnostic;return std::nullopt;}
    error.clear();return OffboardGroundScene(world,*metadata,sources);
}
std::vector<OffboardGroundEdge> OffboardGroundScene::EdgeCandidates(OffboardGroundEdgeSearch search) const
{
    using namespace offboard_ground_query;const Bounds query{search.min,search.max};std::vector<OffboardGroundEdge> output;output.reserve(40);
    std::vector<OffboardGroundEdgeSegment> static_edges;static_edges.reserve(metadata_->static_edges.size());
    for(const auto& edge:metadata_->static_edges)static_edges.push_back({{edge.start,edge.end},edge.local_bounds});Append(output,static_edges,{},query);
    if(sources_.use_alternate)
    {
        for(const auto& record:sources_.alternates)
        {
            if(!record.enabled)continue;const auto& choice=record.choices[(search.context.selection_flags_2948&2)!=0?1:0];
            if(choice&&Matches(search.context.matching_id_2952,choice->second))
            {if(!choice->first)std::abort();Body(output,*choice->first,query);}
        }
    }
    else
    {
        const auto center=Mul(Add(query.min,query.max),.5f);
        for(const auto* provider:std::array<const std::vector<OffboardGroundEdgeBody>*,2>{&sources_.dynamic,&sources_.vehicles})
        {
            for(const auto& entry:*provider)
            {
                const auto d=Sub(entry.local_to_world.position,center);const auto squared=std::fma(d.z,d.z,std::fma(d.y,d.y,d.x*d.x));if(squared>=225)continue;
                Append(output,entry.segments,entry.local_to_world,query);if(output.size()==40)break;
            }
        }
    }
    std::vector<const OffboardGroundIndexedBody*> ordered;for(const auto& entry:sources_.indexed)ordered.push_back(&entry);
    std::stable_sort(ordered.begin(),ordered.end(),[](const auto* a,const auto* b){return a->id<b->id;});
    for(const auto* entry:ordered)if(!entry->disabled){if(!entry->body)std::abort();Body(output,*entry->body,query);}return output;
}
bool OffboardGroundScene::QueryLines(const OffboardGroundPacket& packet,std::array<std::optional<OffboardGroundLineHit>,7>& output,std::string& error) const
{
    using namespace offboard_ground_query;std::vector<std::size_t> candidates;
    for(const auto& line:packet.lines)
    {
        if(!std::isfinite(line.radius)||line.radius<0){error="Invalid Biped line radius";return false;}
        const auto indices=world_->CandidateMeshIndices(world_->LineCandidateBounds(line.start,line.end,line.radius));if(indices.error){error=indices.error;return false;}
        candidates.insert(candidates.end(),indices.indices.begin(),indices.indices.end());
    }
    std::sort(candidates.begin(),candidates.end());candidates.erase(std::unique(candidates.begin(),candidates.end()),candidates.end());
    std::array<std::vector<std::size_t>,3> pools;
    for(const auto index:candidates)pools[std::size_t(metadata_->meshes[index].pool)].push_back(index);
    if(metadata_->island_flags!=3)pools[2].clear();std::array<std::optional<OffboardGroundLineHit>,7> result;
    for(std::size_t index=0;index<7;++index)
    {
        const auto& line=packet.lines[index];const auto delta=Sub(line.end,line.start);const auto threshold=Bits(0x37800000);
        if(!(std::abs(delta.x)>threshold||std::abs(delta.y)>threshold||std::abs(delta.z)>threshold))continue;
        const auto low=[&](float a,float b){return VectorMin(a,b)-line.radius;};const auto high=[&](float a,float b){return VectorMax(a,b)+line.radius;};
        const Bounds bounds{{low(line.start.x,line.end.x),low(line.start.y,line.end.y),low(line.start.z,line.end.z)},{high(line.start.x,line.end.x),high(line.start.y,line.end.y),high(line.start.z,line.end.z)}};
        auto nearest=std::numeric_limits<float>::max();
        for(const auto& pool:pools)for(const auto mesh_index:pool)
        {
            const auto& mesh=metadata_->meshes[mesh_index];
            if(!Matches(packet.context.matching_id_2952,mesh.matching_group)||!Overlaps(TransformBounds(QueryFrame(mesh.world_to_local),bounds),mesh.local_bounds))continue;
            for(auto triangle_index=mesh.triangle_range.start;triangle_index<mesh.triangle_range.end;++triangle_index)
            {
                const auto& source=world_->Triangles()[triangle_index].triangle.vertices;const auto frame=QueryFrame(mesh.local_to_world);
                const std::array<Vec3,3> vertices{Point(frame,source[0]),Point(frame,source[1]),Point(frame,source[2])};TriangleLineHit hit;
                if(TriangleSegment(hit,line.start,delta,vertices,line.radius,0))
                {
                    const auto lower=-hit.fraction>=0?0:hit.fraction;const auto fraction=1.0f-lower>=0?lower:1.0f;
                    if(fraction<nearest){nearest=fraction;result[index]=OffboardGroundLineHit{hit.position,Face(vertices),fraction,metadata_->packed_surfaces[triangle_index]};}
                }
            }
        }
    }
    output=result;error.clear();return true;
}
}
