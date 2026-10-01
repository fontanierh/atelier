// SPDX-License-Identifier: Apache-2.0
#include "SkeletonLineQueries.h"
#include "CameraWorld.h"
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Word(std::uint32_t bits){float v;std::memcpy(&v,&bits,4);return v;}
std::uint32_t Bits(float v){std::uint32_t b;std::memcpy(&b,&v,4);return b;}
Vec3 Vector(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 Lanes(Vec3 v){return {v.x,v.y,v.z,0};}
bool QueryTrajectory(const WorldGeometry& world,Vec4 start,Vec4 velocity,SkeletonLineHit& result,std::string& error)
{
    const camera::TrajectoryQuery request{start,velocity,{},1.0f,Word(0x3cf5c28f),0,0};result=SkeletonLineHit{};
    const auto line=[&](Vec4 a,Vec4 b,float radius,std::optional<Vec4>& position,std::string&)
    {
        const Vec3 origin=Vector(a),direction{b[0]-a[0],b[1]-a[1],b[2]-a[2]};float nearest=std::numeric_limits<float>::max();position.reset();
        for(const auto index:world.LineCandidates(origin,Vector(b),radius))
        {
            const auto& triangle=world.Triangles()[index];TriangleLineHit geometry{};
            if(TriangleSegment(geometry,origin,direction,triangle.triangle.vertices,radius,0.0f))
            {
                const float lower=-geometry.fraction>=0.0f?0.0f:geometry.fraction,fraction=1.0f-lower>=0.0f?lower:1.0f;
                if(fraction<nearest){nearest=fraction;result.position=Lanes(geometry.position);result.normal=Lanes(triangle.triangle.feature.normal);result.surface=triangle.tag;position=result.position;}
            }
        }
        return true;
    };
    if(!request.CollisionTime(line,result.collision_time,error))return false;result.hit=result.collision_time>=0.0f;return true;
}
LineTestFields Fields(const SkeletonLineHit& hit)
{
    LineTestFields fields;for(unsigned i=0;i<4;++i){fields.position[i]=Bits(hit.position[i]);fields.normal[i]=Bits(hit.normal[i]);}fields.surface=hit.surface;fields.valid=hit.collision_time>=0.0f;return fields;
}
}
void SkeletonLineTests::Publish(PlayerInputState& player) const
{
    player.hips_line_test_1488=Fields(hips);player.left_line_test_1536=Fields(feet[0]);player.right_line_test_1584=Fields(feet[1]);
}
bool QuerySkeletonLines(const WorldGeometry& world,const SkeletonBody& body,SkeletonLineTests& result,std::string& error)
{
    const auto parts=body.PartTransforms();SkeletonLineTests next;
    if(!QueryTrajectory(world,parts[23][3],{0,-100,0,0},next.hips,error))return false;
    const Vec4 raised{{0,Word(0x3ea8f5c3),0,0}},lowered{{0,-1.5f,0,0}};Vec4 velocity;
    for(unsigned i=0;i<4;++i)velocity[i]=lowered[i]-raised[i];
    for(unsigned foot=0;foot<2;++foot){Vec4 start;for(unsigned i=0;i<4;++i)start[i]=parts[foot==0?15:19][3][i]+raised[i];if(!QueryTrajectory(world,start,velocity,next.feet[foot],error))return false;}
    result=next;return true;
}
}
