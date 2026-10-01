// SPDX-License-Identifier: Apache-2.0
#include "BoardPossessionRuntime.h"
#include <algorithm>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec3 Xyz(Vec4 v){return {v[0],v[1],v[2]};}
Vec4 Vector(Vec3 v){return {v.x,v.y,v.z,0.0f};}
AffineTransform Affine(Mat4 v)
{
    Basis3 b;for(unsigned i=0;i<3;++i)b.columns[i]={v[i][0],v[i][1],v[i][2]};return {b,Xyz(v[3])};
}
Mat4 Matrix(AffineTransform v)
{
    Mat4 result;for(unsigned i=0;i<3;++i)result[i]={v.basis.columns[i][0],v.basis.columns[i][1],v.basis.columns[i][2],0.0f};
    result[3]=Vector(v.translation);return result;
}
}
void BoardPossessionVolumeFlags::SetEnabled(bool value)
{deck=value;trucks=value;wheels=value;std::fill(deck_children.begin(),deck_children.end(),value);}
void BoardPossessionLiveState::PublishVolumes(BoardCollisionSettings& collision) const
{
    collision.truck_collisions=volumes.trucks;
    for(std::size_t i=0;i<std::min(collision.deck_geometry.children.size(),volumes.deck_children.size());++i)
        collision.deck_geometry.children[i].collision_enabled=volumes.deck_children[i];
}
bool BoardPossessionLiveState::VolumeEnabled(CollisionBody body) const
{
    if(body.kind!=CollisionBody::Kind::Board)return true;
    if(body.index==6)return volumes.deck;if(body.index==4 || body.index==5)return volumes.trucks;return volumes.wheels;
}
void LiveBoardPossessionEffects::EnableAnimationSoft(){board.HookMut().drive.EnableAnimationSoft(animated);}
void LiveBoardPossessionEffects::EnableAnimationAngularOnly(){board.HookMut().drive.EnableAngularOnly(animated);}
void LiveBoardPossessionEffects::DisableAnimation(){board.HookMut().drive.DisableAnimation(animated);}
void LiveBoardPossessionEffects::DisableLinearDrive(){board.HookMut().drive.DisableLinear();}
void LiveBoardPossessionEffects::StandardBoard()
{
    wiping_out=false;board.BodiesMut()[6].inertia.angular_drag=live.standard_drag;board.SetCollisionGroup(4);
    collision.wheel_material=live.standard_materials[0];collision.truck_material=live.standard_materials[1];collision.deck_material=live.standard_materials[2];CollisionVolumes(true);
}
void LiveBoardPossessionEffects::ReleasedBoard()
{
    wiping_out=true;const std::uint32_t bits=0x416fffff;float drag;std::memcpy(&drag,&bits,4);board.BodiesMut()[6].inertia.angular_drag=drag;board.SetCollisionGroup(7);
    collision.wheel_material=live.released_material;collision.truck_material=live.released_material;collision.deck_material=live.released_material;CollisionVolumes(true);
}
void LiveBoardPossessionEffects::CollisionVolumes(bool value){live.volumes.SetEnabled(value);}
void LiveBoardPossessionEffects::ClearAlignment(){live.alignment_active=false;}
void LiveBoardPossessionEffects::Alignment(BoardPossessionAlignment value){live.alignment=value;live.alignment_active=true;}
void LiveBoardPossessionEffects::Velocity(Vec4 value){for(auto& body:board.BodiesMut())body.rates.linear_velocity=Xyz(value);}
void LiveBoardPossessionEffects::Position(Vec4 value)
{auto target=board.PartTransforms()[6];target.translation=Xyz(value);board.SetTransform(target);}
void LiveBoardPossessionEffects::HookFrame(Mat4 value){board.SetHookTransform(Affine(value));}
void LiveBoardPossessionEffects::TargetPositionVelocity(Vec4 value)
{
    const auto center=board.Bodies()[6].rates.position;const float inverse=1.0f/dt;
    Velocity({(value[0]-center.x)*inverse,(value[1]-center.y)*inverse,(value[2]-center.z)*inverse,0.0f*inverse});
}
void LiveBoardPossessionEffects::Torque(Vec4 value)
{
    auto& deck=board.BodiesMut()[6];std::array<Vec4,3> inertia;
    for(unsigned i=0;i<3;++i){const auto& v=deck.rates.world_inverse_inertia.columns[i];inertia[i]={v[0],v[1],v[2],0.0f};}
    const auto delta=BoardPossessionAngularAcceleration(value,Vector(deck.rates.angular_velocity),inertia);const auto a=deck.rates.torque_acceleration;
    deck.rates.torque_acceleration={a.x+delta[0],a.y+delta[1],a.z+delta[2]};deck.rates.cool_down=0;
}
void BoardPossessionOwner::ResetForTeleport(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e)
{f.word_444=0;Stop(f,o,e);state.retrieval={};}
void BoardPossessionTransition::Hold(){previous.word_444=0;owner.Hold(previous,observation,effects);changed=true;}
void BoardPossessionTransition::LetGo(){previous.word_444=0;owner.LetGo(previous,observation,effects);changed=true;}
void BoardPossessionTransition::Finish(SkateboardControllerFields& f) const{if(changed)f.word_444=previous.word_444;}
std::uint32_t BoardPossessionSurface(const BoardGroundState& ground,const WheelLineState& lines)
{
    if(ground.collision_flags&0x02000000)return 12;std::array<unsigned,32> counts{};
    for(unsigned i=0;i<4;++i){const auto surface=lines.physics_surfaces[i];if(surface){if(surface>=32)std::abort();counts[surface]+=ground.parts[i].in_contact?4:1;}}
    std::uint32_t best=1;unsigned count=0;for(unsigned i=1;i<=13;++i)if(counts[i]>count){best=i;count=counts[i];}return best;
}
BoardPossessionObservation ObserveBoardPossession(const BoardRuntime& board,const BoardPossessionObserveInput& input)
{
    auto processed=input.processed;processed.board_frame_64=input.toolkit_deck.value_or(Matrix(board.PartTransforms()[6]));
    const auto& frames=input.drive_frames;return {processed,input.ground.collision_flags,BoardPossessionSurface(input.ground,input.wheel_lines),
        {input.feedback.bones[3].groups[3],input.feedback.bones[7].groups[3]},
        {input.physical.pose[3][3],input.physical.pose[7][3]},frames[0],{frames[3],frames[7]},ComposeSkeletonAffine(input.animation_to_world,frames[0])};
}
void UpdateBoardPossession(BoardPossessionOwner& owner,BoardPossessionLiveState& live,BoardRuntime& board,BoardCollisionSettings& collision,
    bool& wiping_out,std::uint8_t& animated,SkateboardControllerFields& fields,const BoardPossessionObserveInput& input,float dt)
{
    if(!fields.system_on_452)return;const auto observation=ObserveBoardPossession(board,input);
    LiveBoardPossessionEffects effects(board,animated,wiping_out,live,collision,dt);owner.Update(fields,observation,effects);live.PublishVolumes(collision);
}
void ResetBoardPossessionForTeleport(BoardPossessionOwner& owner,BoardPossessionLiveState& live,BoardRuntime& board,BoardCollisionSettings& collision,
    bool& wiping_out,std::uint8_t& animated,SkateboardControllerFields& fields,const BoardPossessionObserveInput& input,float dt)
{
    const auto observation=ObserveBoardPossession(board,input);LiveBoardPossessionEffects effects(board,animated,wiping_out,live,collision,dt);
    owner.ResetForTeleport(fields,observation,effects);live.output.reset();live.PublishVolumes(collision);
}
void FinishBoardPossessionTeleport(BoardPossessionLiveState& live,BoardRuntime& board,BoardCollisionSettings& collision,bool& wiping_out,std::uint8_t& animated,float dt)
{LiveBoardPossessionEffects effects(board,animated,wiping_out,live,collision,dt);effects.StandardBoard();live.PublishVolumes(collision);}
BoardPossessionFill PublishBoardPossession(const BoardPossessionOwner& owner,BoardPossessionLiveState& live,const BoardRuntime& board,
    BoardGroundState& ground,const SkateboardControllerFields& fields,const BoardPossessionObserveInput& input)
{
    if(live.alignment_active)
    {
        auto a=live.alignment.first_1008,b=live.alignment.second_1024;for(auto& x:a)x=-x;for(auto& x:b)x=-x;
        for(const auto& part:ground.parts)if(part.in_contact && (Dot3(Vector(part.normal),a)>live.alignment.factor_1040 || Dot3(Vector(part.normal),b)>live.alignment.factor_1040))ground.collision_flags|=0x04000000;
    }
    const auto observation=ObserveBoardPossession(board,input);const auto bone=ComposeSkeletonAffine(input.animation_to_world,input.drive_frames[11]);
    const auto output=owner.Fill(fields,observation.processed,bone);live.output=output;return output;
}
}
