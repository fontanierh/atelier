// SPDX-License-Identifier: Apache-2.0
#include "SkeletonColliders.h"
#include "CollisionBody.h"
#include <algorithm>
#include <charconv>
#include <cstdlib>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
std::string DebugFloat(float value)
{
    if(std::isnan(value))return "NaN";
    if(std::isinf(value))return value<0 ? "-inf":"inf";
    char buffer[64];const auto result=std::to_chars(buffer,buffer+sizeof(buffer),value,std::chars_format::general);
    if(result.ec!=std::errc{})std::abort();std::string text(buffer,result.ptr);
    const auto e=text.find('e');
    if(e!=std::string::npos)
    {
        std::size_t at=e+1;bool minus=false;if(text[at]=='+' || text[at]=='-'){minus=text[at]=='-';++at;}
        while(at+1<text.size() && text[at]=='0')++at;
        text=text.substr(0,e)+"e"+(minus ? "-":"")+text.substr(at);
    }
    else if(text.find('.')==std::string::npos)text+=".0";
    return text;
}
std::string DebugShape(const MassShape& s)
{
    if(s.kind==MassShapeKind::Cylinder)return "Cylinder { radius: "+DebugFloat(s.radius)+", half_length: "+DebugFloat(s.half_length)+", padding: "+DebugFloat(s.padding)+" }";
    return "Unsupported";
}
}
std::optional<std::vector<BoardWorldVolume>> SkeletonEnabledVolumes(const SkeletonBody& skeleton,const SkeletonCollisionMode& collision,std::string& error)
{
    const auto transforms=skeleton.PartTransforms();std::vector<BoardWorldVolume> volumes;
    for(std::size_t index=0;index<SkeletonPartCount;++index)
    {
        const auto& part=skeleton.definition.parts[index];const auto& state=collision.parts[index];if(!state.enabled)continue;
        if(state.volume_group!=0 && state.volume_group!=4){error="Skater part"+std::to_string(index)+" requires volume group"+std::to_string(state.volume_group)+" world filtering";return std::nullopt;}
        if(part.hat){error="The equipped hat requires its original cylinder collision query";return std::nullopt;}
        const auto& frame=transforms[index];const auto center=Xyz(frame[3]);ContactPrimitive primitive;
        switch(part.shape.kind)
        {
        case MassShapeKind::Sphere:primitive=Sphere{center,part.shape.radius};break;
        case MassShapeKind::Capsule:primitive=Capsule{center,Xyz(frame[2]),part.shape.half_length,part.shape.radius};break;
        case MassShapeKind::RoundedBox:
        {
            Basis3 basis;for(unsigned i=0;i<3;++i)for(unsigned j=0;j<3;++j)basis.columns[i][j]=frame[i][j];
            primitive=RoundedBox{center,basis,part.shape.half_extents,part.shape.radius};break;
        }
        default:error="Skater part"+std::to_string(index)+" has no recovered collision query for "+DebugShape(part.shape);return std::nullopt;
        }
        volumes.push_back({CollisionBody::Attached(index).ContactId(),primitive,skeleton.Bodies()[index].rates.linear_velocity,state.material});
    }
    error.clear();return volumes;
}
void RetainSkeletonWorldVolumes(std::vector<BoardWorldVolume>& volumes,const SkeletonCollisionMode& collision)
{
    volumes.erase(std::remove_if(volumes.begin(),volumes.end(),[&](const BoardWorldVolume& volume)
    {
        const auto body=CollisionBody::FromContactId(volume.body_contact_id);
        if(body.kind!=CollisionBody::Kind::Attached || body.index>=collision.parts.size())std::abort();
        return collision.parts[body.index].volume_group==4;
    }),volumes.end());
}
std::optional<std::vector<BoardWorldVolume>> SkeletonWorldVolumes(const SkeletonBody& skeleton,const SkeletonCollisionMode& collision,std::string& error)
{auto volumes=SkeletonEnabledVolumes(skeleton,collision,error);if(volumes)RetainSkeletonWorldVolumes(*volumes,collision);return volumes;}
}
