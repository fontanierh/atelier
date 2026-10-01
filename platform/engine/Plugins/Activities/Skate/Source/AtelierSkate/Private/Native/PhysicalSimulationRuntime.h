// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "PhysicalSimulationSettings.h"
#include "BoardColliders.h"
#include "BoardMotionOutput.h"
#include "BoardProbes.h"
#include "BoardToolkit.h"
#include "NetworkProxies.h"
#include "ReckoningFrames.h"
#include "SkeletonBoardFrames.h"
#include "SkeletonContactReports.h"
#include "SkeletonPoseErrors.h"

namespace atelier::skate
{
struct GroundNormalFilter
{
    std::array<std::uint32_t,24> words{};
    static GroundNormalFilter Initialized(Vec4 control,Vec4 initial);
    void PublishCurrent(Vec4 value);
    Vec4 FilterRaw(Vec4 control,Vec4 input);
    Vec4 Update(Vec4 control,Vec4 input);
private:
    Vec4 Filter(Vec4 input);
};
struct GroundOrientationInput
{
    Vec3 com_to_deck,ground_normal,dynamic_up;
    float speed;
    std::int32_t wheel_contact_count;
    float animation_balance,deck_angle_curve_input;
    Vec3 board_up,board_forward,effective_board_forward,previous_reckoning_right;
    bool prevent_up_behind_board;
};
struct GroundOrientation
{
    Vec3 dynamic_up{0,1,0},up{0,1,0},target{0,1,0},up_velocity{},ground_normal{0,1,0};
    float ground_blend=0;
    GroundNormalFilter ground_filter,slow_filter,fast_filter;
    explicit GroundOrientation(const GroundOrientationSettings&);
    void Reset();
    void Update(const GroundOrientationSettings&,GroundOrientationInput);
};
struct PhysicalGroundPacket
{
    Vec3 wheel_normal,dynamic_up;
    float speed,absolute_speed;
    std::int32_t wheel_count;
};
struct PhysicalRidingPose {Vec3 com_to_deck;float body_spin;};
struct PhysicalBoardProbes
{
    BoardProbeState deck,wall;
    std::optional<WheelLine> wall_line;
    struct Pending {std::optional<BoardProbeHit> deck;std::optional<std::optional<BoardProbeHit>> wall;};
    std::optional<Pending> pending;
    void ResetResults();
    void PrepareWall(WallLineInput input);
    bool Start(const BoardRuntime&,const WorldGeometry&,std::string& error);
    bool Publish(std::string& error);
};
struct PhysicalRidingOutputs
{
    PhysicalRidingSettings settings;
    BoardGroundState ground;
    WheelLineState wheel_lines;
    PhysicalBoardProbes probes;
    GroundOrientation reckoning;
    ReckoningFrames reckoning_frames;
    std::array<std::uint32_t,44> body_spin{};
    BoardMotionOutput motion;
    float heading_adjust_factor;
    std::optional<std::array<std::optional<WheelLineHit>,4>> pending_wheel_queries;
    PhysicalRidingOutputs(PhysicalRidingSettings,const BoardRuntime&,std::uint32_t processed_flags);
    void ResetForTeleport();
    float UpdateInputHeading(float normal_y,float speed);
    void UpdateGroundReckoning(const BoardRuntime&,PhysicalRidingPose,std::uint32_t flags,
        float animation_balance,bool coffin,PhysicalGroundPacket,std::optional<Vec4> heading=std::nullopt);
    void UpdateSlideReckoning(const BoardToolkit&,PhysicalRidingPose,std::uint32_t flags,
        float animation_balance,bool coffin,PhysicalGroundPacket);
    bool StartWheelQueries(const BoardRuntime&,const WorldGeometry&,std::string& error);
    bool FinishWheelQueries(std::string& error);
    void FinishPostPhysics(BoardRuntime&,bool board_wiping_out,std::uint32_t flags,float time_step);
};
struct PhysicalSkeletonCorrection
{
    Vec4 board_prediction_error{};
    bool pending=false;
    void ObserveBoard(Vec4 actual,Vec4 predicted);
    void Apply(SkeletonBody&,Vec4 ground_normal,bool wipeout,std::uint32_t flags_2468,std::uint32_t flags_2476);
};
// These are the current upstream ProcessedPhysIn fields, not contact/body
// results. Contacts, physical frames, errors and target positions are computed
// from the live owners below.
struct PhysicalFeedbackInput
{
    std::uint32_t state_2508,category_2512,flags_2472,flags_2480;
    std::array<Vec4,5> vectors_464_480_496_512_528;
    std::array<Vec4,5> vectors_880_896_912_928_944;
};
struct PhysicalSimulationDiagnostic
{
    enum class Stage {BeforeSharedSolve,AfterSharedSolve,EndFrame};
    enum class Field {Position,LinearVelocity,AngularVelocity,ForceAcceleration,TorqueAcceleration,OrientationInertia};
    Stage stage;
    Field field;
    std::size_t reaction_body;
    BodySnapshot body;
};
class PhysicalSimulationRuntime
{
public:
    PhysicalSimulationSettings settings;
    BoardRuntime board;
    WorldGeometry world;
    PhysicalRidingOutputs riding;
    SkeletonBody skeleton;
    SkeletonJoints skeleton_joints;
    SkeletonDrives skeleton_drives;
    SkeletonCollisionMode skeleton_collision;
    SkeletonCollisionFeedback collision_feedback;
    SkeletonPoseErrors pose_errors;
    SkeletonAnimationRecord animation_record;
    SkeletonRootFrames roots;
    SkeletonBoardFrames board_frames;
    PhysicalSkeletonCorrection correction;
    BoardPossessionOwner possession;
    BoardPossessionLiveState possession_live;
    SkateboardControllerFields controller_fields;
    NetworkProxies network_proxies;
    std::array<Mat4,24> drive_frames;
    Vec4 deck_velocity{},root_velocity{},previous_root_position{};
    Vec4 reset_local_hips{};
    bool invalid_target_reset=false;
    Mat4 animation_board_to_physics=SkeletonIdentity;
    std::array<Vec4,3> extra_target_positions{};
    Vec4 collision_pose_error{};
    std::array<Vec4,2> collision_extra_errors{};
    std::optional<float> collision_maximum_error;
    std::optional<SkeletonDriveBatch> solved_drives;
    std::vector<BoardCollision> generated_contacts;
    std::vector<JointConstraint> solved_joints;
    std::vector<SkeletonContactReport> contact_reports;
    std::size_t contact_count=0,network_contacts=0;
    std::uint64_t ticks=0;
    std::uint32_t processed_flags_2468=0x2000;
    bool board_wiping_out=false,failed=false;
    std::optional<PhysicalSimulationDiagnostic> diagnostic;
    static std::optional<PhysicalSimulationRuntime> Initialize(PhysicalSimulationSettings,const SettingsDatabase&,
        const std::vector<Mat4>& initial_hierarchy,WorldGeometry,AffineTransform spawn,std::string& error);
    static std::optional<PhysicalSimulationRuntime> Initialize(PhysicalSimulationSettings,const SettingsDatabase&,
        const AnimationPoseEvaluator&,WorldGeometry,AffineTransform spawn,std::string& error);
    Mat4 DeckFrame() const;
    bool BeginBoardQueries(std::string& error);
    bool FinishBoardQueries(std::string& error);
    // Climbing's dropped board advances independently of the attached rider.
    // It uses this owner's world contact history and the caller's current dt.
    bool AdvanceClimbingBoardOnly(float dt,std::string& error);
    Mat4 PrepareGroundSkeleton(const Mat4& animation_board,const Mat4& reckoning,float processed_dt);
    void UpdateRootDerivative(float processed_dt);
    void ResetPhysicalPose();
    void ApplySkeletonGravity(float processed_gravity);
    SkeletonTargetUpdate UpdateTargetPositions(const Mat4& animation_hips,const Mat4& animation_board,bool teleporting);
    void UpdateBoneDrives(const std::array<Mat4,24>& actual_frames);
    void UpdatePossession(const BoardPossessionProcessed&,std::optional<Mat4> toolkit_deck,
        std::uint8_t& animated,float processed_dt);
    BoardPossessionFill PublishPossession(const BoardPossessionProcessed&,std::optional<Mat4> toolkit_deck);
    bool Solve(std::array<float,2> truck_targets,std::string& error);
    void FinishBoardOutputs(WallLineInput current_input);
    void PublishFeedback(const PhysicalFeedbackInput&);
    bool FinishFrame(std::string& error);
    void EnableImportedFloorSeams();
    void ReplaceWorld(WorldGeometry);
private:
    BoardWorldContacts world_contacts_;
    PhysicalSimulationRuntime(PhysicalSimulationSettings,BoardRuntime,WorldGeometry,SkeletonBody,
        SkeletonJoints,SkeletonDrives,const std::array<Mat4,24>&);
    bool Validate(PhysicalSimulationDiagnostic::Stage,std::string& error);
};
}
