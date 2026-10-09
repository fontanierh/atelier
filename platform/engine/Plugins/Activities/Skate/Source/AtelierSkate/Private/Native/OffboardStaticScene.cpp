#include "OffboardStaticScene.h"
#include "OffboardContactPrivate.h"
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec3 Spatial(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 Lanes(Vec3 v){return {v.x,v.y,v.z,0};}
Vec4 Lanes(const std::array<float,3>& v){return {v[0],v[1],v[2],0};}
bool Matches(std::int32_t a,std::int32_t b){return a==-1||b==-1||a==b;}
float OrdinaryDot(Vec4 a,Vec4 b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
bool TriangleBox(const std::array<Vec4,3>& vertices,Vec4 center,float radius)
{
    using namespace offboard_contact;
    const std::array<Vec4,3> v{Sub(vertices[0],center),Sub(vertices[1],center),Sub(vertices[2],center)};
    const std::array<Vec4,3> edges{Sub(v[1],v[0]),Sub(v[2],v[1]),Sub(v[0],v[2])};
    const std::array<Vec4,3> axes{{{1,0,0,0},{0,1,0,0},{0,0,1,0}}};
    const auto separated=[&](Vec4 axis)
    {
        const std::array<float,3> p{OrdinaryDot(v[0],axis),OrdinaryDot(v[1],axis),OrdinaryDot(v[2],axis)};
        const auto extent=std::fma(std::abs(axis[2]),radius,std::fma(std::abs(axis[1]),radius,std::abs(axis[0])*radius));
        return VectorMin(VectorMin(p[0],p[1]),p[2])>extent||VectorMax(VectorMax(p[0],p[1]),p[2])< -extent;
    };
    for(const auto& edge:edges)for(const auto& axis:axes)if(separated(Cross(edge,axis)))return false;
    for(const auto& axis:axes)if(separated(axis))return false;
    return !separated(Cross(edges[0],edges[1]));
}
std::int32_t FloorFrame(float value)
{
    const auto floor=std::floor(value);
    // Rust float-to-integer casts saturate; a NaN becomes zero.
    if(std::isnan(floor))return 0;
    if(floor>=2147483648.0f)return std::numeric_limits<std::int32_t>::max();
    if(floor<= -2147483648.0f)return std::numeric_limits<std::int32_t>::min();
    return static_cast<std::int32_t>(floor);
}
Vec4 LandingNormal(const std::vector<std::array<Vec4,3>>& triangles,Vec4 velocity)
{
    using namespace offboard_contact;
    std::vector<Vec4> normals;normals.reserve(64);Vec4 best{};float best_y=-1;
    for(std::size_t n=0;n<std::min<std::size_t>(triangles.size(),64);++n)
    {
        const auto& triangle=triangles[n];auto normal=Cross(Sub(triangle[1],triangle[0]),Sub(triangle[2],triangle[0]));
        normal=Scale(normal,Inverse(Dot(normal,normal)));
        if(normal[1]>.7f||Dot(normal,velocity)<=0)
        {if(normal[1]>best_y){best=normal;best_y=normal[1];}normals.push_back(normal);}
    }
    if(normals.empty())return {0,1,0,0};Vec4 total{};
    for(const auto& normal:normals)if(Dot(best,normal)>.5f)for(std::size_t i=0;i<4;++i)total[i]+=normal[i];
    const auto square=Dot(total,total),inverse=Inverse(square);const auto magnitude=square==0?0:square*inverse;
    return magnitude>Bits(0x358637bd)?Scale(total,inverse):Vec4{};
}
bool Sweep(const OffboardStaticScene& scene,QueryPool pool,OffboardLineProbe probe,std::int32_t group,std::uint32_t reject,
           AirTrajectoryQueryResult& result,std::string& error)
{
    using namespace offboard_contact;const auto velocity=Sub(probe.end,probe.start);result=AirTrajectoryQueryResult::Miss();
    if(!(Dot(velocity,velocity)>0)||!(std::abs(velocity[0])>Bits(0x37800000)||std::abs(velocity[1])>Bits(0x37800000)||std::abs(velocity[2])>Bits(0x37800000)))return true;
    std::optional<OffboardLineHit> hit;if(!scene.Line(pool,probe,group,reject,hit,error))return false;if(!hit)return true;
    const auto distance=Length(Sub(hit->position,probe.start)),speed=Length(velocity),epsilon=Bits(0x38d1b717);
    const auto frames=std::abs(distance)>epsilon&&std::abs(speed)>epsilon?Reciprocal(speed)*distance:0;
    const auto contact_frame=FloorFrame(frames);std::vector<std::array<Vec4,3>> triangles;
    if(!scene.Nearby(pool,hit->position,probe.radius,group,triangles,error))return false;
    result={hit->position,hit->normal,LandingNormal(triangles,velocity),frames*Bits(0x3c888889),hit->mesh_frame,contact_frame,hit->surface,hit->geometry};return true;
}
class PoolQueries final:public AirTrajectoryWorldQueries
{
public:
    PoolQueries(const OffboardStaticScene& scene,QueryPool pool,std::int32_t group,std::uint32_t reject)
        :scene_(scene),pool_(pool),group_(group),reject_(reject){}
    bool Line(Vec4 start,Vec4 end,float radius,std::optional<AirTrajectorySurfaceHit>& result,std::string& error) override
    {
        std::optional<OffboardLineHit> hit;if(!scene_.Line(pool_,{start,end,radius},group_,reject_,hit,error))return false;
        result.reset();if(hit)result=AirTrajectorySurfaceHit{hit->position,hit->normal,hit->mesh_frame,hit->surface,hit->geometry};return true;
    }
    bool Nearby(Vec4 position,float radius,std::vector<std::array<Vec4,3>>& result,std::string& error) override
    {return scene_.Nearby(pool_,position,radius,group_,result,error);}
private:
    const OffboardStaticScene& scene_;QueryPool pool_;std::int32_t group_;std::uint32_t reject_;
};
}
std::optional<OffboardStaticScene> OffboardStaticScene::Create(const WorldGeometry& world,std::string& error)
{
    const char* diagnostic=nullptr;const auto metadata=world.Metadata(diagnostic);
    if(!metadata){error=diagnostic;return std::nullopt;}error.clear();return OffboardStaticScene(world,*metadata);
}
std::vector<QueryPool> OffboardStaticScene::Pools() const
{std::vector<QueryPool> pools{QueryPool::Ground,QueryPool::Island};if(metadata_->island_flags==3)pools.push_back(QueryPool::Conditional);return pools;}
bool OffboardStaticScene::Line(QueryPool pool,OffboardLineProbe probe,std::int32_t group,std::uint32_t reject,
                               std::optional<OffboardLineHit>& output,std::string& error) const
{
    using namespace offboard_contact;
    if(!std::isfinite(probe.radius)||probe.radius<0)
    {error="Invalid offboard swept-line request";return false;}
    for(std::size_t n=0;n<3;++n)if(!std::isfinite(probe.start[n])||!std::isfinite(probe.end[n]))
    {error="Invalid offboard swept-line request";return false;}
    output.reset();const auto delta=Sub(probe.end,probe.start);
    if(!(std::abs(delta[0])>Bits(0x37800000)||std::abs(delta[1])>Bits(0x37800000)||std::abs(delta[2])>Bits(0x37800000))){error.clear();return true;}
    const auto start=Spatial(probe.start),end=Spatial(probe.end),direction=Spatial(delta);
    const auto bounds=world_->LineCandidateBounds(start,end,probe.radius);const auto candidates=world_->LineCandidates(start,end,probe.radius);
    const auto meshes=world_->CandidateMeshIndices(bounds);if(meshes.error){error=meshes.error;return false;}
    auto nearest=std::numeric_limits<float>::max();
    for(const auto mesh_index:meshes.indices)
    {
        const auto& mesh=metadata_->meshes[mesh_index];if(mesh.pool!=pool||!Matches(group,mesh.matching_group)||(mesh.rejection_flags&reject)!=0)continue;
        const auto first=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.start);
        const auto last=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.end);
        for(auto it=first;it!=last;++it)
        {
            const auto index=*it;const auto& vertices=world_->Triangles()[index].triangle.vertices;TriangleLineHit hit;
            if(!TriangleSegment(hit,start,direction,vertices,probe.radius,0))continue;
            const auto lower=-hit.fraction>=0?0:hit.fraction;const auto fraction=1.0f-lower>=0?lower:1.0f;
            if(fraction<nearest)
            {
                nearest=fraction;const auto& transform=mesh.local_to_world;
                Mat4 frame{Lanes(transform.basis.columns[0]),Lanes(transform.basis.columns[1]),Lanes(transform.basis.columns[2]),Lanes(transform.translation)};
                const std::array<Vec4,3> face{Lanes(vertices[0]),Lanes(vertices[1]),Lanes(vertices[2])};
                output=OffboardLineHit{Lanes(hit.position),OffboardTriangleNormal(face),fraction,metadata_->packed_surfaces[index],frame,mesh.geometry};
            }
        }
    }
    error.clear();return true;
}
bool OffboardStaticScene::Nearby(QueryPool pool,Vec4 center,float radius,std::int32_t group,std::vector<std::array<Vec4,3>>& output,std::string& error) const
{
    output.clear();output.reserve(64);const auto position=Spatial(center);
    const auto bounds=world_->LineCandidateBounds(position,position,radius);const auto candidates=world_->LineCandidates(position,position,radius);
    const auto meshes=world_->CandidateMeshIndices(bounds);if(meshes.error){error=meshes.error;return false;}
    for(const auto mesh_index:meshes.indices)
    {
        const auto& mesh=metadata_->meshes[mesh_index];if(mesh.pool!=pool||!Matches(group,mesh.matching_group))continue;
        const auto first=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.start);
        const auto last=std::lower_bound(candidates.begin(),candidates.end(),mesh.triangle_range.end);
        for(auto it=first;it!=last;++it)
        {
            const auto& source=world_->Triangles()[*it].triangle.vertices;const std::array<Vec4,3> vertices{Lanes(source[0]),Lanes(source[1]),Lanes(source[2])};
            if(TriangleBox(vertices,center,radius)){output.push_back(vertices);if(output.size()==64){error.clear();return true;}}
        }
    }
    error.clear();return true;
}
std::vector<std::array<Vec4,2>> OffboardStaticScene::Edges(const OffboardQueryBatch& batch) const
{
    const auto input=batch.input;Vec4 center,extent;
    for(std::size_t i=0;i<4;++i)
    {
        center[i]=std::fma(input.up[i],.29999998f,std::fma(input.forward[i],.89999998f,input.position[i]));
        extent[i]=std::fma(std::abs(input.forward[i]),.89999998f,std::fma(std::abs(input.up[i]),1.1f,std::abs(input.right[i])*.037500001f));
    }
    std::vector<std::array<Vec4,2>> output;
    for(const auto& edge:metadata_->static_edges)
    {
        const auto min=Lanes(edge.local_bounds.min),max=Lanes(edge.local_bounds.max);bool overlap=true;
        for(std::size_t i=0;i<3;++i)overlap=overlap&&(center[i]-extent[i]<=max[i]&&min[i]<=center[i]+extent[i]);
        if(overlap){output.push_back({Lanes(edge.start),Lanes(edge.end)});if(output.size()==40)break;}
    }
    return output;
}
bool OffboardStaticScene::Execute(const OffboardQueryBatch& batch,OffboardQueryResults& output,std::string& error) const
{
    OffboardQueryResults result;for(auto& trajectory:result.trajectories)trajectory=AirTrajectoryQueryResult::Miss();result.lines.resize(batch.lines.size());
    for(const auto pool:Pools())
    {
        for(std::size_t i=0;i<3;++i)
        {
            const auto& request=batch.trajectories[i];const auto start=request.trajectory.position;Vec4 end;
            for(std::size_t n=0;n<4;++n)end[n]=start[n]+request.trajectory.velocity[n];
            AirTrajectoryQueryResult hit;if(!Sweep(*this,pool,{start,end,request.radius},batch.matching_group,batch.mesh_reject_mask,hit,error))return false;
            if(offboard_contact::Valid(hit)&&(!offboard_contact::Valid(result.trajectories[i])||hit.contact_time<result.trajectories[i].contact_time))result.trajectories[i]=hit;
        }
        for(std::size_t i=0;i<batch.lines.size();++i)
        {
            std::optional<OffboardLineHit> hit;if(!Line(pool,batch.lines[i],batch.matching_group,batch.mesh_reject_mask,hit,error))return false;
            if(hit&&(!result.lines[i]||hit->fraction<result.lines[i]->fraction))result.lines[i]=hit;
        }
    }
    result.edges=Edges(batch);output=std::move(result);error.clear();return true;
}
bool OffboardStaticScene::Lines(const std::vector<OffboardLineProbe>& requests,std::int32_t group,std::vector<std::optional<OffboardLineHit>>& output,std::string& error) const
{
    std::vector<std::optional<OffboardLineHit>> result(requests.size());
    for(const auto pool:Pools())for(std::size_t i=0;i<requests.size();++i)
    {
        std::optional<OffboardLineHit> hit;if(!Line(pool,requests[i],group,0,hit,error))return false;
        if(hit&&(!result[i]||hit->fraction<result[i]->fraction))result[i]=hit;
    }
    output=std::move(result);error.clear();return true;
}
bool OffboardStaticScene::Trajectory(AirTrajectoryQueryRequest request,std::int32_t group,std::uint32_t reject,AirTrajectoryQueryResult& output,std::string& error) const
{
    const auto& trajectory=request.trajectory;
    bool valid=std::isfinite(trajectory.scalar_48)&&trajectory.scalar_48>0&&std::isfinite(request.radius)&&request.radius>0
        &&std::isfinite(request.start_error)&&request.start_error>0&&std::isfinite(request.end_error)&&request.end_error>0;
    for(std::size_t i=0;i<4;++i)valid=valid&&std::isfinite(trajectory.position[i])&&std::isfinite(trajectory.velocity[i])&&std::isfinite(trajectory.acceleration[i]);
    if(!valid){error="Invalid offboard accelerated-trajectory request";return false;}
    auto nearest=AirTrajectoryQueryResult::Miss();
    for(const auto pool:Pools())
    {
        PoolQueries queries(*this,pool,group,reject);AirTrajectoryQueryResult result;
        if(!QueryAirTrajectory(request,queries,result,error))return false;
        if(offboard_contact::Valid(result)&&(!offboard_contact::Valid(nearest)||result.contact_time<nearest.contact_time))nearest=result;
    }
    output=nearest;error.clear();return true;
}
}
