// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "GameplayFrameRuntime.h"
namespace atelier::skate
{
// Immutable, project-native resources. Sessions share clip storage and graph
// definitions; every mutable controller, physical and graph history is local.
struct GameplayResources
{
    SettingsDatabase settings;
    PhysicsSkeleton physical_skeleton;
    AnimationStockGraphs graphs;
    std::shared_ptr<const AnimationSource> animation;
    Graph camera_graph;
    std::vector<std::uint8_t> camera_data;
    std::vector<GestureSet> gestures;
    std::optional<ClimbingClipFile> climbing;
};
bool LoadGameplayResources(const std::filesystem::path&,
    std::shared_ptr<const GameplayResources>& output,std::string& error);
// Sole owning tree for the original GamePhysics + SkaterRuntime. BorrowFrame
// constructs ephemeral views, so all phases consume these exact same records.
// Its address is stable: grab and teleport owners borrow its member histories.
class GameplayRuntime
{
public:
    static bool Create(std::shared_ptr<const GameplayResources>,WorldGeometry,
        std::shared_ptr<const PlayerGrindStaticProvider>,AffineTransform spawn,
        std::string_view mode,std::unique_ptr<GameplayRuntime>& output,std::string& error);
    GameplayRuntime(const GameplayRuntime&)=delete;
    GameplayRuntime& operator=(const GameplayRuntime&)=delete;
    GameplayRuntime(GameplayRuntime&&)=delete;
    GameplayRuntime& operator=(GameplayRuntime&&)=delete;
    GameplayFrameOwners BorrowFrame();
    bool Advance(const TickInput&,std::string& error);
    bool TravelTo(Mat4,std::string& error);
    bool InstallWorld(WorldGeometry,std::shared_ptr<const PlayerGrindStaticProvider>,std::string& error);
    bool Tune(float pop,float spin,float push_speed,float push_power,float vert_assist,std::string& error);
    bool Tune(float pop,float spin,float push_speed,float push_power,std::string& error)
    {return Tune(pop,spin,push_speed,push_power,0.0f,error);}
    void Launch(Vec3 velocity);

    std::shared_ptr<const GameplayResources> resources;
    std::shared_ptr<const PlayerGrindStaticProvider> grind_world;
    std::unique_ptr<PhysicalSimulationRuntime> physical;
    std::unique_ptr<SkaterAnimation> animation;
    std::unique_ptr<AnimatedSkeleton> animated;
    std::unique_ptr<FootIk> ik;
    std::unique_ptr<SkeletonInputRuntime> skeleton_input;
    std::unique_ptr<SkeletonAir> skeleton_air;
    std::unique_ptr<PlayerInputRuntime> input;
    std::unique_ptr<PlayerStateRuntime> player_state;
    std::unique_ptr<BipedGroundRuntime> biped_ground;
    std::unique_ptr<OffboardAirSelector> offboard_air_selector;
    std::unique_ptr<RespawnRuntime> respawn;
    std::unique_ptr<TeleportStateRuntime> teleport;
    std::unique_ptr<PlayerTeleportRuntime> input_teleport;
    std::unique_ptr<PlayerGrindMaterials> grind_materials;
    std::unique_ptr<PlayerControls> controls;
    std::unique_ptr<FootPhysicalOutputs> foot_physical;
    std::unique_ptr<SkeletonOutputRuntime> skeleton_output;
    GroundStateRuntime ground;
    GroundRuntime ground_runtime;
    GroundProfiles ground_profiles;
    GroundSettings ground_settings;
    GroundPhaseLifecycle ground_lifecycle;
    AirStateSettings air_settings;
    AirReckoning air_reckoning;
    AirPhaseRuntime air;
    KnownAirRuntime known_air;
    BipedAirRuntime biped_air;
    LandingOnDeckRuntime landing_on_deck;
    LandingDeck landing_deck;
    GroundAnimationRuntime ground_animation;
    GroundAnimationSettings ground_animation_settings;
    RevertRuntime revert;
    SlidePhaseRuntime slide;
    AirTrajectoryRuntime trajectory;
    GrindRuntime grind;
    FootplantRuntime footplant;
    BonelessRuntime boneless;
    Handplant handplant;
    WipeoutRuntime wipeout;
    WipeoutPhysicalRuntime ragdoll;
    OffboardContactToolkit offboard_contact;
    BoardPossessionManager offboard_feet;
    OffboardGrabCache grab_cache;
    OffboardGrabRuntime grab;
    OffboardGrabRegistry grab_registry;
    PhysicsAnimationInput animation_input;
    AnimationFeedbackRuntime feedback;
    AnimationPhysicalFeedback physical_feedback;
    SkeletonWobble wobble;
    std::vector<Mat4> render_pose;
    std::uint64_t pose_generation=0;
    CentreOfMassFilter centre_of_mass_filter;
    CentreOfMassOutput centre_of_mass_output{};
    ClimbingRuntime climbing;
    ScoringRuntime scoring;
    camera::CameraRuntime camera;
    AnimationProfile profile;
    TrainerTuning trainer;
    SimulationClock clock;
    SimulationExchange exchange{0};
    bool network_active=false;
private:
    GameplayRuntime():grab(grab_cache),physical_feedback(InitialAnimationPhysicalFeedback()){}
    float stock_spin_speed_=0;
};
}
