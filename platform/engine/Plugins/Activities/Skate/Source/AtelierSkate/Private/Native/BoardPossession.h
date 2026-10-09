#pragma once
#include "SkeletonPoseFrames.h"
namespace atelier::skate
{
struct SkateboardControllerFields {std::uint32_t word_444=0,state_448=0;bool system_on_452=false;};
struct BoardRetrieval
{
    Mat4 initial_0=SkeletonIdentity,target_64=SkeletonIdentity,current_128=SkeletonIdentity;
    float elapsed_192=0,duration_196=0,progress_200=0,weight_204=0;
};
struct BoardHandDrive
{
    Mat4 child=SkeletonIdentity,parent=SkeletonIdentity;
    std::array<std::array<std::uint32_t,4>,2> dynamics{{{0,0,0,2},{0,0,0,2}}};
};
struct BoardPossessionProcessed
{
    Mat4 board_frame_64,player_frame_192;
    Vec4 position_592,velocity_912,direction_400,hide_direction_464;
    std::uint32_t flags_2476,flags_2480,flags_2488;
};
struct BoardPossessionFill
{
    float angle_36,angle_40;
    bool held_311,free_312,returning_313,hiding_321,flag_322,flag_323,flag_324;
};
struct BoardPossessionSettings
{
    float hide_distance,hide_offset,return_distance,mounted_return_distance,mounting_time;
    PointGraph<8> retrieval_time,retrieval_weight;
    float throw_pitch;
    PointGraph<8> throw_velocity;
    float throw_target_pitch,throw_pitch_scalar,throw_roll_scalar,throw_yaw_scalar;
};
struct BoardPossessionObservation
{
    BoardPossessionProcessed processed;
    std::uint32_t board_collision_flags_872,board_state_840;
    std::array<bool,2> hand_contacts;
    std::array<Vec4,2> physical_hand_positions;
    Mat4 animation_board_frame_12624;
    std::array<Mat4,2> animation_hand_frames;
    Mat4 attachment_frame_0;
};
struct BoardPossessionAlignment {Vec4 first_1008,second_1024;float factor_1040;bool flag_1044;};
class BoardPossessionEffects
{
public:
    virtual ~BoardPossessionEffects()=default;
    virtual void EnableAnimationSoft()=0;
    virtual void EnableAnimationAngularOnly()=0;
    virtual void DisableAnimation()=0;
    virtual void DisableLinearDrive()=0;
    virtual void StandardBoard()=0;
    virtual void ReleasedBoard()=0;
    virtual void CollisionVolumes(bool enabled)=0;
    virtual void ClearAlignment()=0;
    virtual void Alignment(BoardPossessionAlignment)=0;
    virtual void Velocity(Vec4)=0;
    virtual void Position(Vec4)=0;
    virtual void HookFrame(Mat4)=0;
    virtual void TargetPositionVelocity(Vec4)=0;
    virtual void Torque(Vec4)=0;
};
struct BoardPossessionState
{
    BoardRetrieval retrieval;
    std::array<BoardHandDrive,2> hands;
    std::uint32_t selected_hand_424=2;
    void Stop(SkateboardControllerFields&,const BoardPossessionObservation&,const BoardPossessionSettings&,BoardPossessionEffects&);
    void Hold(SkateboardControllerFields&,const BoardPossessionObservation&,BoardPossessionEffects&);
    void DisableHand();
    void LetGo(SkateboardControllerFields&,const BoardPossessionObservation&,const BoardPossessionSettings&,BoardPossessionEffects&);
    void Hide(const BoardPossessionObservation&,BoardPossessionEffects&);
    void Retrieve(const SkateboardControllerFields&,const BoardPossessionObservation&,const BoardPossessionSettings&,BoardPossessionEffects&);
    void UpdateState(SkateboardControllerFields&,const BoardPossessionObservation&,const BoardPossessionSettings&,BoardPossessionEffects&);
    void UpdateDriveFrames(const BoardPossessionObservation&);
    void Update(SkateboardControllerFields&,const BoardPossessionObservation&,const BoardPossessionSettings&,BoardPossessionEffects&);
};
BoardPossessionFill FillBoardPossession(const SkateboardControllerFields&,const BoardPossessionState&,
    const BoardPossessionProcessed&,Mat4 bone11);
Vec4 BoardThrowVelocity(const BoardPossessionProcessed&,const BoardPossessionSettings&);
std::array<Vec4,3> BoardThrowTorques(const BoardPossessionProcessed&,const BoardPossessionSettings&);
Vec4 BoardPossessionAngularAcceleration(Vec4 request,Vec4 omega,const std::array<Vec4,3>& inverse_inertia);
}
