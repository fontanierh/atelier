// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "BoardPossessionDrives.h"
#include "BoardPhysicsSettings.h"
#include "BoardGround.h"
#include "SkeletonCollisionFeedback.h"
namespace atelier::skate
{
struct BoardPossessionVolumeFlags
{
    bool deck=true,trucks=false,wheels=true;
    std::vector<bool> deck_children;
    void SetEnabled(bool value);
};
struct BoardPossessionLiveState
{
    BoardPossessionVolumeFlags volumes;
    BoardPossessionAlignment alignment{};
    bool alignment_active=false;
    std::array<ContactMaterial,3> standard_materials{};
    ContactMaterial released_material{};
    float standard_drag=0;
    std::optional<BoardPossessionFill> output;
    void PublishVolumes(BoardCollisionSettings&) const;
    bool VolumeEnabled(CollisionBody) const;
};
class LiveBoardPossessionEffects final : public BoardPossessionEffects
{
    BoardRuntime& board;
    std::uint8_t& animated;
    bool& wiping_out;
    BoardPossessionLiveState& live;
    BoardCollisionSettings& collision;
    float dt;
public:
    LiveBoardPossessionEffects(BoardRuntime& b,std::uint8_t& a,bool& w,BoardPossessionLiveState& l,
        BoardCollisionSettings& c,float step):board(b),animated(a),wiping_out(w),live(l),collision(c),dt(step){}
    void EnableAnimationSoft() override;
    void EnableAnimationAngularOnly() override;
    void DisableAnimation() override;
    void DisableLinearDrive() override;
    void StandardBoard() override;
    void ReleasedBoard() override;
    void CollisionVolumes(bool) override;
    void ClearAlignment() override;
    void Alignment(BoardPossessionAlignment) override;
    void Velocity(Vec4) override;
    void Position(Vec4) override;
    void HookFrame(Mat4) override;
    void TargetPositionVelocity(Vec4) override;
    void Torque(Vec4) override;
};
class BoardPossessionOwner
{
    BoardPossessionSettings settings;
public:
    BoardPossessionState state;
    explicit BoardPossessionOwner(BoardPossessionSettings s):settings(s){}
    const BoardPossessionSettings& Settings() const{return settings;}
    void Update(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e){state.Update(f,o,settings,e);}
    void Hold(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e){state.Hold(f,o,e);}
    void LetGo(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e){state.LetGo(f,o,settings,e);}
    void Stop(SkateboardControllerFields& f,const BoardPossessionObservation& o,BoardPossessionEffects& e){state.Stop(f,o,settings,e);}
    void ResetForTeleport(SkateboardControllerFields&,const BoardPossessionObservation&,BoardPossessionEffects&);
    void AppendDrives(BodySnapshot deck,const std::array<BodySnapshot,2>& hands,std::size_t deck_reaction,
        std::array<std::size_t,2> hand_reactions,float dt,std::vector<DriveRows>& rows) const
    {AppendBoardPossessionDrives(state,deck,hands,deck_reaction,hand_reactions,dt,rows);}
    BoardPossessionFill Fill(const SkateboardControllerFields& f,const BoardPossessionProcessed& p,Mat4 bone11) const
    {return FillBoardPossession(f,state,p,bone11);}
};
class BoardPossessionTransition
{
    BoardPossessionOwner& owner;
    const BoardPossessionObservation& observation;
    BoardPossessionEffects& effects;
    SkateboardControllerFields previous;
    bool changed=false;
public:
    BoardPossessionTransition(BoardPossessionOwner& o,const BoardPossessionObservation& p,BoardPossessionEffects& e,
        SkateboardControllerFields f):owner(o),observation(p),effects(e),previous(f){}
    void Hold();
    void LetGo();
    void Finish(SkateboardControllerFields&) const;
};
struct BoardPossessionObserveInput
{
    BoardPossessionProcessed processed;
    std::optional<Mat4> toolkit_deck;
    const BoardGroundState& ground;
    const WheelLineState& wheel_lines;
    const SkeletonPhysicalRecord& physical;
    const SkeletonCollisionFeedback& feedback;
    const std::array<Mat4,24>& drive_frames;
    Mat4 animation_to_world;
};
std::uint32_t BoardPossessionSurface(const BoardGroundState&,const WheelLineState&);
BoardPossessionObservation ObserveBoardPossession(const BoardRuntime&,const BoardPossessionObserveInput&);
void UpdateBoardPossession(BoardPossessionOwner&,BoardPossessionLiveState&,BoardRuntime&,BoardCollisionSettings&,
    bool& wiping_out,std::uint8_t& animated,SkateboardControllerFields&,const BoardPossessionObserveInput&,float processed_dt);
void ResetBoardPossessionForTeleport(BoardPossessionOwner&,BoardPossessionLiveState&,BoardRuntime&,BoardCollisionSettings&,
    bool& wiping_out,std::uint8_t& animated,SkateboardControllerFields&,const BoardPossessionObserveInput&,float processed_dt);
void FinishBoardPossessionTeleport(BoardPossessionLiveState&,BoardRuntime&,BoardCollisionSettings&,bool& wiping_out,
    std::uint8_t& animated,float processed_dt);
BoardPossessionFill PublishBoardPossession(const BoardPossessionOwner&,BoardPossessionLiveState&,const BoardRuntime&,
    BoardGroundState&,const SkateboardControllerFields&,const BoardPossessionObserveInput&);
}
