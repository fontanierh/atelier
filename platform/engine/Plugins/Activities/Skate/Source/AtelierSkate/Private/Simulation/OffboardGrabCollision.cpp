#include "OffboardGrabMath.h"
#include <algorithm>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool OffboardGrabScene::Line(OffboardGrabLine line,std::optional<OffboardGrabHit>& output,std::string& error) const
{
    using namespace offboard_grab_math;if(line.radius<0||!std::isfinite(line.radius)){error="Invalid grab validation swept line";return false;}for(unsigned n=0;n<4;++n)if(!std::isfinite(line.start[n])||!std::isfinite(line.end[n])){error="Invalid grab validation swept line";return false;}
    const auto delta=Sub(line.end,line.start);if(!(std::abs(delta[0])>Bits(0x37800000)||std::abs(delta[1])>Bits(0x37800000)||std::abs(delta[2])>Bits(0x37800000))){output.reset();error.clear();return true;}
    const char* diagnostic=nullptr;const auto metadata=world_->Metadata(diagnostic);if(!metadata){error=diagnostic;return false;}
    const Vec3 start{line.start[0],line.start[1],line.start[2]},end{line.end[0],line.end[1],line.end[2]},direction{delta[0],delta[1],delta[2]};const auto bounds=world_->LineCandidateBounds(start,end,line.radius);const auto meshes=world_->CandidateMeshIndices(bounds);if(meshes.error){error=meshes.error;return false;}const auto candidates=world_->LineCandidates(start,end,line.radius);
    auto nearest=std::numeric_limits<float>::max();std::optional<OffboardGrabHit> result;const std::array<QueryPool,3> pools{QueryPool::Ground,QueryPool::Island,QueryPool::Conditional};
    for(unsigned p=0;p<3;++p)
    {
        const auto pool=pools[p];if((line.source_pool_mask&(1u<<p))==0)continue;if(pool==QueryPool::Conditional&&metadata->island_flags!=3)continue;
        for(const auto index:meshes.indices)
        {
            const auto& mesh=metadata->meshes[index];if(mesh.pool!=pool||(mesh.rejection_flags&line.reject_flags)!=0||!(line.group==-1||mesh.matching_group==-1||line.group==mesh.matching_group))continue;
            const auto first=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.start),last=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.end);
            for(auto it=first;it!=last;++it)
            {
                TriangleLineHit hit;const auto& vertices=world_->Triangles()[*it].triangle.vertices;
                // This original owner forwards stored vertices directly. Do not
                // apply the separate scene adapter's mesh transform here.
                if(!TriangleSegment(hit,start,direction,vertices,line.radius,0))continue;const auto lower=-hit.fraction>=0?0:hit.fraction,fraction=1-lower>=0?lower:1;
                if(fraction<nearest){nearest=fraction;result=OffboardGrabHit{fraction,registry_->Assembly(mesh.geometry)};}
            }
        }
    }
    output=result;error.clear();return true;
}
}
