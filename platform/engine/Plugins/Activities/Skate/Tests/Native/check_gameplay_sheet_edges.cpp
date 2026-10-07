// SPDX-License-Identifier: Apache-2.0
// Explicit C++ host-policy regressions; compile with the native session units.
#include "GameplayWorld.h"
#include "GeometryTriangleFixup.h"
#include <cstdlib>
#include <iostream>
using namespace atelier::skate;
namespace
{
unsigned checks=0;
void Require(bool ok,const char* message)
{
    if(!ok){std::cerr<<"FAIL: "<<message<<'\n';std::exit(1);}
    ++checks;
}
PreparedGameplayWorld Build(GameplayWorldSnapshot source,bool policy)
{
    source.exclude_coincident_backfaces=policy;
    std::optional<PreparedGameplayWorld> world;std::string error;
    const bool ok=BuildGameplayWorld(source,{.5f,.3f,0},world,error);
    Require(ok,error.c_str());
    return std::move(*world);
}
bool Accept(const TriangleFeature& feature,Vec3 normal)
{
    ContactPair pair{};
    return FixUpTriangle(feature,normal,&pair,1,{false,0.999f,0.01f,false});
}
void SameFeatures(const WorldGeometry& a,const WorldGeometry& b)
{
    Require(a.Triangles().size()==b.Triangles().size(),"triangle count preserved");
    for(std::size_t i=0;i<a.Triangles().size();++i)
    {
        const auto& x=a.Triangles()[i].triangle.feature;
        const auto& y=b.Triangles()[i].triangle.feature;
        Require(x.flags==y.flags&&x.edge_cosines==y.edge_cosines,"real solid/fold adjacency unchanged");
    }
}
}
int main()
{
    const Vec3 a{0,0,0},b{0,0,2},c{2,0,0};
    GameplayWorldSnapshot sheet;sheet.triangles={{a,b,c},{b,a,c}};
    const auto legacy=Build(sheet,false),filtered=Build(sheet,true);
    const auto& before=legacy.collision.Triangles()[0].triangle.feature;
    const auto& after=filtered.collision.Triangles()[0].triangle.feature;
    Require(before.edge_cosines[0]==-1,"fixture reproduces mirrored-edge cosine");
    Require(after.edge_cosines[0]==1,"coincident back does not widen the edge cone");
    Require(Accept(before,{-0.70710677f,0.70710677f,0}),"legacy edge admits tilted ghost normal");
    Require(!Accept(after,{-0.70710677f,0.70710677f,0}),"sheet edge rejects tilted ghost normal");
    Require(Accept(before,{-0.57735026f,0.57735026f,-0.57735026f}),"legacy corner admits ghost normal");
    Require(!Accept(after,{-0.57735026f,0.57735026f,-0.57735026f}),"sheet corner rejects ghost normal");
    Require(Accept(after,{0,1,0}),"top face still contacts");
    Require(Accept(filtered.collision.Triangles()[1].triangle.feature,{0,-1,0}),"ceiling face still contacts");
    for(bool from_above:{false,true})
    {
        const float height=from_above?1.0f:-1.0f;
        const auto hit=filtered.collision.QueryThinLine({.5f,height,.5f},{.5f,-height,.5f});
        Require(!hit.error&&hit.hit.has_value(),"both sides still query the sheet");
        Require(hit.hit->geometry.normal.y*height>0,"query keeps top/ceiling orientation");
    }
    Require(filtered.collision.Triangles().size()==2,"no collision face deleted");
    // Same welded edge and opposed normals alone do not prove coincidence.
    auto separated=sheet;
    for(auto& p:separated.triangles[1])p.y=.0002f;
    const auto separate_old=Build(separated,false),separate_new=Build(separated,true);
    SameFeatures(separate_old.collision,separate_new.collision);
    auto folded=sheet;folded.triangles[1][2].y=.02f;
    const auto fold_old=Build(folded,false),fold_new=Build(folded,true);
    SameFeatures(fold_old.collision,fold_new.collision);
    // A genuine neighbouring wall must still constrain the shared edge/corner.
    auto wall=sheet;wall.triangles={sheet.triangles[0],{b,a,{0,-1,0}}};
    const auto wall_old=Build(wall,false),wall_new=Build(wall,true);
    SameFeatures(wall_old.collision,wall_new.collision);
    // A top fan and a two-triangle back need not share all triangulation edges.
    const Vec3 d{2,0,2},centre{1,0,1};
    GameplayWorldSnapshot fan;
    fan.triangles={{a,b,centre},{b,d,centre},{d,c,centre},{c,a,centre},{a,c,b},{c,d,b}};
    const auto fan_world=Build(fan,true);
    for(const auto& triangle:fan_world.collision.Triangles())
        Require((triangle.triangle.feature.flags&0xe00u)==0xe00u,"different sheet tessellations keep flat corner suppression");
    std::cout<<"PASS: "<<checks<<" coincident-sheet contact/query checks\n";
}
