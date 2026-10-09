#pragma once
#include "PlayerGrindContact.h"
namespace atelier::skate
{
Vec4 PlayerGrindDirectedTangent(Vec4 start,Vec4 end,Vec4 velocity,Vec4 previous);
struct PlayerGrindGeometryInput
{
    bool valid;std::uint32_t family,current_state,category,air_frames,geometry_kind,geometry_flags;
    std::array<Vec4,2> far_points;Vec4 upmost,high_side,point,direction,board_position,board_forward,velocity;
    float deck_to_truck,previous_exit_angle;Vec4 previous_exit_direction;std::uint32_t flags;
};
struct PlayerGrindGeometryOutput {bool valid;std::uint32_t family,flags;};
PlayerGrindGeometryOutput TweakPlayerGrindGeometry(PlayerGrindGeometryInput,std::uint32_t& avoid_five_o_frames);
float PlayerGrindGravityRelief(float& timer,bool valid,std::uint32_t category,Vec4 tangent,Vec4 velocity,
    float dt,const PointGraph<4>& vertical,const PointGraph<4>& linear);
struct PlayerGrindJumpGeometry {std::uint32_t geometry_kind;Vec4 high_side,normal,direction,upmost,point;};
struct PlayerGrindJumper
{
    bool launched=false;std::uint32_t cooldown=0,family=3;float energy=1;
    PlayerGrindJumpGeometry geometry{0,{1,0,0,0},{0,1,0,0},{1,0,0,0},{0,1,0,0},{0,0,0,0}};
    std::uint32_t Update(std::optional<PlayerGrindJumpGeometry>,std::uint32_t published_family);
};
}
