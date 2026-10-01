// SPDX-License-Identifier: Apache-2.0
#include "PlayerSceneProbe.h"
#include <algorithm>
#include <cstring>
#include <numeric>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec3 XYZ(Vec4 v){return {v[0],v[1],v[2]};}
bool Identity(AffineTransform f)
{return f.basis.columns==AffineTransform{}.basis.columns&&f.translation.x==0&&f.translation.y==0&&f.translation.z==0;}
Vec3 Transform(AffineTransform f,Vec3 v)
{
    const auto& b=f.basis.columns;const auto t=f.translation;
    return {std::fma(b[2][0],v.z,std::fma(b[1][0],v.y,std::fma(b[0][0],v.x,t.x))),
        std::fma(b[2][1],v.z,std::fma(b[1][1],v.y,std::fma(b[0][1],v.x,t.y))),
        std::fma(b[2][2],v.z,std::fma(b[1][2],v.y,std::fma(b[0][2],v.x,t.z)))};
}
}
bool QueryPlayerSceneProbe(const WorldGeometry& world,PlayerSceneProbe probe,std::uint32_t matching_id,
    std::optional<PlayerSceneProbeHit>& output,std::string& error)
{
    const char* failure=nullptr;const auto* metadata=world.Metadata(failure);if(!metadata){error=failure;return false;}
    const auto start=XYZ(probe.start),end=XYZ(probe.end);const Vec3 delta{end.x-start.x,end.y-start.y,end.z-start.z};
    std::vector<std::size_t> candidates;
    if(std::all_of(metadata->meshes.begin(),metadata->meshes.end(),[](const QueryMesh& m){return Identity(m.local_to_world);}))candidates=world.LineCandidates(start,end,probe.radius);
    else {candidates.resize(world.Triangles().size());std::iota(candidates.begin(),candidates.end(),0);}
    std::optional<PlayerSceneProbeHit> nearest;std::int32_t group;std::memcpy(&group,&matching_id,4);
    for(const auto pool:{QueryPool::Ground,QueryPool::Island,QueryPool::Conditional})
    {
        if(pool==QueryPool::Conditional&&metadata->island_flags!=3)continue;
        for(std::size_t mesh_index=0;mesh_index<metadata->meshes.size();++mesh_index)
        {
            const auto& mesh=metadata->meshes[mesh_index];if(mesh.pool!=pool||(mesh.matching_group!=-1&&mesh.matching_group!=group))continue;
            const auto first=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.start);
            const auto last=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.end);
            for(auto it=first;it!=last;++it)
            {
                const auto index=*it;const auto& triangle=world.Triangles()[index].triangle;std::array<Vec3,3> vertices;
                for(unsigned j=0;j<3;++j)vertices[j]=Transform(mesh.local_to_world,triangle.vertices[j]);
                TriangleLineHit geometry{};
                if(TriangleSegment(geometry,start,delta,vertices,probe.radius,triangle.fatness)&&(!nearest||geometry.fraction<nearest->geometry.fraction))
                    nearest=PlayerSceneProbeHit{geometry,metadata->packed_surfaces[index],mesh_index,mesh.local_to_world};
            }
        }
    }
    output=nearest;error.clear();return true;
}
}
