// SPDX-License-Identifier: Apache-2.0
#include "PlayerGrindInputWorld.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float F(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
Vec3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 Packed(Vec3 v){return {v.x,v.y,v.z,0};}
float ClampFraction(float fraction){const float lower=-fraction>=0 ? 0 : fraction;return 1.0f-lower>=0 ? lower : 1.0f;}
Vec3 Face(const std::array<Vec3,3>& vertices)
{
    const auto u=Subtract(vertices[1],vertices[0]),v=Subtract(vertices[2],vertices[0]);const auto normal=Cross3(u,v);
    const float square=std::fma(normal.z,normal.z,std::fma(normal.y,normal.y,normal.x*normal.x));
    float inverse=1.0f/std::sqrt(square);for(unsigned i=0;i<2;++i)inverse=std::fma(inverse*.5f,std::fma(-square,inverse*inverse,1.0f),inverse);
    return Scale(normal,inverse);
}
bool Line(const WorldGeometry& world,std::int32_t matching,PlayerGrindProbe probe,std::optional<PlayerGrindProbeHit>& result,std::string& error)
{
    const char* diagnostic=nullptr;const auto* metadata=world.Metadata(diagnostic);if(!metadata){error=diagnostic;return false;}
    if(!std::isfinite(probe.radius)||probe.radius<0){error="Invalid grind line radius";return false;}
    const auto start=XYZ(probe.start),end=XYZ(probe.end);const auto initial=Bounds::FromPoints(std::array<Vec3,2>{start,end});
    if(!initial){error="Non-finite grind line endpoints";return false;}const auto bounds=initial->Expanded(probe.radius);
    if(!std::isfinite(bounds.min.x)||!std::isfinite(bounds.min.y)||!std::isfinite(bounds.min.z)||!std::isfinite(bounds.max.x)||!std::isfinite(bounds.max.y)||!std::isfinite(bounds.max.z)){error="Grind line bounds overflow";return false;}
    const auto delta=Subtract(end,start);const float threshold=F(0x37800000);
    if(!(std::abs(delta.x)>threshold||std::abs(delta.y)>threshold||std::abs(delta.z)>threshold)){result.reset();error.clear();return true;}
    const auto candidates=world.CandidateMeshIndices(bounds);if(candidates.error){error=candidates.error;return false;}
    const auto triangles=world.LineCandidates(start,end,probe.radius);float nearest=std::numeric_limits<float>::max();std::optional<PlayerGrindProbeHit> output;
    for(auto pool:{QueryPool::Ground,QueryPool::Island,QueryPool::Conditional})
    {
        if(pool==QueryPool::Conditional&&metadata->island_flags!=3)continue;
        for(auto mesh_index:candidates.indices)
        {
            const auto& mesh=metadata->meshes[mesh_index];if(mesh.pool!=pool||!(matching==-1||mesh.matching_group==-1||matching==mesh.matching_group)||!bounds.Overlaps(mesh.local_bounds))continue;
            const auto first=std::lower_bound(triangles.begin(),triangles.end(),mesh.triangle_range.start),last=std::lower_bound(triangles.begin(),triangles.end(),mesh.triangle_range.end);
            for(auto it=first;it!=last;++it)
            {
                const auto triangle_index=*it;const auto vertices=world.Triangles()[triangle_index].triangle.vertices;
                const auto triangle_bounds=Bounds::FromPoints(vertices);if(!triangle_bounds){error="Non-finite authored grind triangle";return false;}if(!bounds.Overlaps(*triangle_bounds))continue;
                TriangleLineHit hit{};if(!TriangleSegment(hit,start,delta,vertices,probe.radius,0.0f))continue;
                const float fraction=ClampFraction(hit.fraction);if(fraction<nearest){nearest=fraction;output=PlayerGrindProbeHit{fraction,Packed(hit.position),Packed(Face(vertices)),metadata->packed_surfaces[triangle_index]};}
            }
        }
    }
    result=output;error.clear();return true;
}
}
PlayerGrindBounds PlayerGrindBounds::IdentityTransformed() const
{
    PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){const float center=(max[i]+min[i])*.5f,half=(max[i]-min[i])*.5f;out.min[i]=center-half;out.max[i]=center+half;}return out;
}
bool PlayerGrindBounds::Overlaps(PlayerGrindBounds b) const {for(std::size_t i=0;i<3;++i)if(!(min[i]<=b.max[i]&&b.min[i]<=max[i]))return false;return true;}
PlayerGrindBounds PlayerGrindBounds::Union(PlayerGrindBounds b) const {PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){out.min[i]=VectorMin(min[i],b.min[i]);out.max[i]=VectorMax(max[i],b.max[i]);}return out;}
PlayerGrindBounds PlayerGrindBounds::Padded() const {PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){out.min[i]=min[i]-1;out.max[i]=max[i]+1;}return out;}
PlayerGrindBounds PlayerGrindBounds::Cube() const
{
    std::array<float,3> half,center;for(std::size_t i=0;i<3;++i){half[i]=(max[i]-min[i])*.5f;center[i]=(max[i]+min[i])*.5f;}
    const float radius=VectorMax(VectorMax(half[0],half[1]),half[2]);PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){out.min[i]=center[i]-radius;out.max[i]=center[i]+radius;}return out;
}
PlayerGrindBounds PlayerGrindBounds::Inner() const {PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){const float padding=(max[i]-min[i])*F(0xbecccccd);out.min[i]=min[i]-padding;out.max[i]=max[i]+padding;}return out;}
PlayerGrindBounds PlayerGrindBounds::Child(std::size_t index) const {const auto inner=Inner();PlayerGrindBounds out;for(std::size_t i=0;i<3;++i){out.min[i]=(index&(1u<<i))!=0 ? inner.min[i] : min[i];out.max[i]=(index&(1u<<i))!=0 ? max[i] : inner.max[i];}return out;}
std::optional<std::pair<std::size_t,PlayerGrindBounds>> PlayerGrindBounds::ContainingChild(PlayerGrindBounds entry) const
{
    const auto inner=Inner();std::size_t index=0;for(std::size_t i=0;i<3;++i){const float low=entry.min[i]-inner.min[i],high=inner.max[i]-entry.max[i];if(low<=0&&high<=0)return std::nullopt;if(low>high)index|=1u<<i;}return std::pair<std::size_t,PlayerGrindBounds>{index,Child(index)};
}
bool PlayerGrindBounds::Movable(PlayerGrindBounds entry) const {const auto inner=Inner();for(std::size_t i=0;i<3;++i)if(!(inner.max[i]>entry.max[i]||entry.min[i]>inner.min[i]))return false;return true;}
std::optional<PlayerGrindOctree> PlayerGrindOctree::New(PlayerGrindBounds asset,std::vector<PlayerGrindBounds> bounds,std::string& error)
{
    if(bounds.size()>0xffff){error="Native grind octree exceeds uint16 entry capacity";return std::nullopt;}
    PlayerGrindOctree out;out.node_capacity_=bounds.size()/2+1;out.bounds_=std::move(bounds);out.nodes_.push_back({asset.Cube(),{},{}});for(std::size_t i=0;i<out.bounds_.size();++i)out.Insert(i);error.clear();return out;
}
void PlayerGrindOctree::Insert(std::size_t entry)
{
    std::size_t at=0;for(;;)
    {
        const auto node_bounds=nodes_[at].bounds;bool contained=true;for(std::size_t i=0;i<3;++i)contained=contained&&bounds_[entry].min[i]>=node_bounds.min[i]&&bounds_[entry].max[i]<=node_bounds.max[i];
        const auto target=contained ? node_bounds.ContainingChild(bounds_[entry]) : std::nullopt;if(!target){nodes_[at].resident.push_back(entry);return;}
        const auto slot=target->first;const auto child_bounds=target->second;const auto child=nodes_[at].buckets[slot].child;if(child){at=*child;continue;}
        auto& bucket=nodes_[at].buckets[slot];bucket.entries.emplace_back(entry,child_bounds.Movable(bounds_[entry]));
        if(std::count_if(bucket.entries.begin(),bucket.entries.end(),[](const auto& v){return v.second;})>3&&nodes_.size()<node_capacity_)Split(at,slot,child_bounds);return;
    }
}
void PlayerGrindOctree::Split(std::size_t parent,std::size_t slot,PlayerGrindBounds bounds)
{
    auto entries=std::move(nodes_[parent].buckets[slot].entries);nodes_[parent].buckets[slot].entries.clear();const auto child=nodes_.size();nodes_[parent].buckets[slot].child=child;Node node{bounds,{},{}};
    for(auto it=entries.rbegin();it!=entries.rend();++it)
    {
        if(it->second){const auto target=bounds.ContainingChild(bounds_[it->first]);if(!target)std::abort();node.buckets[target->first].entries.emplace_back(it->first,target->second.Movable(bounds_[it->first]));}
        else node.resident.push_back(it->first);
    }
    nodes_.push_back(std::move(node));
}
std::vector<std::size_t> PlayerGrindOctree::Query(PlayerGrindBounds query,std::size_t limit) const
{
    std::vector<std::size_t> result;if(limit==0)return result;std::vector<std::size_t> stack{0};
    while(!stack.empty())
    {
        const auto index=stack.back();stack.pop_back();const auto& node=nodes_[index];std::vector<std::size_t> leaves;
        for(std::size_t slot=0;slot<8;++slot)if(node.bounds.Child(slot).Overlaps(query)){if(node.buckets[slot].child)stack.push_back(*node.buckets[slot].child);else leaves.push_back(slot);}
        for(auto slot=leaves.rbegin();slot!=leaves.rend();++slot)for(auto entry=node.buckets[*slot].entries.rbegin();entry!=node.buckets[*slot].entries.rend();++entry)if(bounds_[entry->first].Overlaps(query)){result.push_back(entry->first);if(result.size()==limit)return result;}
        for(auto entry=node.resident.rbegin();entry!=node.resident.rend();++entry)if(bounds_[*entry].Overlaps(query)){result.push_back(*entry);if(result.size()==limit)return result;}
    }
    return result;
}
std::optional<PlayerGrindStaticProvider> PlayerGrindStaticProvider::FromConverted(PlayerGrindConvertedData data,std::string& error)
{
    const auto count=data.primitives.size();if(data.metadata.size()!=count||data.authored_bounds.size()!=count||data.source_rail_indices.size()!=count){error="Converted grind primitive metadata count mismatch";return std::nullopt;}
    PlayerGrindStaticProvider out;out.source_for_primitive_.resize(count,std::numeric_limits<std::size_t>::max());
    for(std::size_t asset_index=0;asset_index<data.assets.size();++asset_index)
    {
        const auto& asset=data.assets[asset_index];if(asset.indices.empty()){error="Empty stock grind source section";return std::nullopt;}
        std::vector<PlayerGrindBounds> bounds;for(auto i:asset.indices)
        {
            if(i>=count||out.source_for_primitive_[i]!=std::numeric_limits<std::size_t>::max()){error="Converted grind source index invalid or repeated";return std::nullopt;}
            out.source_for_primitive_[i]=asset_index;bounds.push_back(asset.identity_transform_bounds ? data.authored_bounds[i].IdentityTransformed() : data.authored_bounds[i]);
        }
        auto bound=bounds[0];for(std::size_t i=1;i<bounds.size();++i)bound=bound.Union(bounds[i]);bound=bound.Padded();auto tree=PlayerGrindOctree::New(bound,std::move(bounds),error);if(!tree)return std::nullopt;out.assets_.push_back({bound,std::move(*tree)});
    }
    if(std::find(out.source_for_primitive_.begin(),out.source_for_primitive_.end(),std::numeric_limits<std::size_t>::max())!=out.source_for_primitive_.end()){error="Converted grind primitive lacks source section";return std::nullopt;}
    out.data_=std::move(data);error.clear();return out;
}
const PlayerGrindPrimitiveMetadata* PlayerGrindStaticProvider::Metadata(std::size_t i) const {return i<data_.metadata.size() ? &data_.metadata[i] : nullptr;}
std::optional<std::array<std::uint64_t,2>> PlayerGrindStaticProvider::SplineGuids(std::uint64_t owner) const {return owner>0&&owner-1<data_.rail_guids.size() ? std::optional<std::array<std::uint64_t,2>>(data_.rail_guids[std::size_t(owner-1)]) : std::nullopt;}
const PlayerGrindSourceIdentity* PlayerGrindStaticProvider::Source(std::size_t i) const {return i<source_for_primitive_.size() ? &data_.assets[source_for_primitive_[i]].source : nullptr;}
std::optional<std::uint64_t> PlayerGrindStaticProvider::SourceRailIndex(std::size_t i) const {return i<data_.source_rail_indices.size() ? std::optional<std::uint64_t>(data_.source_rail_indices[i]) : std::nullopt;}
const PlayerGrindBounds* PlayerGrindStaticProvider::AuthoredBounds(std::size_t i) const {return i<data_.authored_bounds.size() ? &data_.authored_bounds[i] : nullptr;}
bool PlayerGrindStaticProvider::Query(std::array<float,3> min,std::array<float,3> max,std::vector<std::size_t>& result,std::string& error) const
{
    for(std::size_t i=0;i<3;++i)if(!std::isfinite(min[i])||!std::isfinite(max[i])||min[i]>max[i]){error="Invalid grind query bounds";return false;}
    const PlayerGrindBounds query{min,max};std::array<float,3> delta;for(std::size_t i=0;i<3;++i)delta[i]=min[i]-max[i];const float square=(delta[0]*delta[0]+delta[1]*delta[1])+delta[2]*delta[2];
    std::vector<std::size_t> output;if(square>F(0x37800000))for(std::size_t i=0;i<assets_.size();++i)
    {
        const auto& asset=assets_[i];if(!asset.bounds.Overlaps(query))continue;for(auto local:asset.tree.Query(query,40-output.size()))output.push_back(data_.assets[i].indices[local]);if(output.size()==40)break;
    }
    result=std::move(output);error.clear();return true;
}
bool PlayerGrindSurfaceProbe(const WorldGeometry& world,std::array<std::uint32_t,2> actor,std::size_t index,PlayerGrindProbe probe,std::optional<PlayerGrindProbeHit>& result,std::string& error)
{
    if(index>=7){error="Grind surface descriptor "+std::to_string(index)+" is outside native batch7";return false;}return Line(world,std::int32_t(actor[1]),probe,result,error);
}
bool PlayerGrindForceExitLine(const WorldGeometry& world,std::array<std::uint32_t,2> actor,PlayerGrindForceExitProbe probe,std::optional<PlayerGrindForceExitHit>& result,std::string& error)
{
    std::optional<PlayerGrindProbeHit> hit;if(!Line(world,std::int32_t(actor[1]),{probe.start,probe.end,0},hit,error))return false;result=hit ? std::optional<PlayerGrindForceExitHit>(PlayerGrindForceExitHit{hit->normal}) : std::nullopt;return true;
}
}
