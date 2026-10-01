// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "AnimationName.h"
#include "InputIntentions.h"
#include <array>
#include <cstdint>
#include <limits>
#include <optional>
namespace atelier::skate
{
// Exact value records of the original PlayerInput owner. Vector/matrix fields
// retain their source bits; no view below is a completed producer substitute.
using RawVector=std::array<std::uint32_t,4>;
using RawMatrix=std::array<RawVector,4>;
struct ExternalPhysicsInput
{
    std::array<RawVector,10> vectors{};
    std::uint32_t flags=0;
    void CopyFrom(const ExternalPhysicsInput& source)
    {vectors=source.vectors;flags=(flags&0x01ffffff)|(source.flags&0xfe000000);}
};
struct TeleportOutputFields {RawMatrix transform{};std::uint32_t next_state=0;std::uint8_t state_61=0,board_272=0;};
enum class NativeReferenceBase {Player,SurfaceSelector};
struct NativeRelativeReference {NativeReferenceBase base=NativeReferenceBase::Player;std::uint16_t offset=0;};
struct SkeletonPhysicalRecord;
struct AirOutputFields
{
    RawVector trajectory_apex_0{};
    RawVector collision_position_16{};
    RawVector landing_normal_32{};
    RawVector selector_vector_48{};
    RawVector trajectory_position_64{};
    RawVector landing_heading_80{};
    RawVector selector_com_position_96{};
    RawVector jump_velocity_delta_112{};
    RawVector launch_velocity_128{};
    float time_in_state_176{};
    float collision_time_180{};
    float collision_normal_speed_188{};
    float time_to_apex_196{};
    std::int32_t trajectory_index_220{};
    std::array<RawVector,4> selected_trajectory_240{};
    std::array<float,25> trajectory_plane_samples_336{};
    std::uint8_t known_air_valid_437{};
    std::uint8_t launched_442{};
    std::uint8_t flag_443{};
    std::uint8_t flag_444{};
    std::uint32_t handplant_flags_324{};
    RawVector handplant_position_304{};
    float handplant_time_320{};
    RawVector vector_160{};
    float scalar_184{};
    RawVector landing_normal_144{};
    float jump_height_200{};
    float footplant_contact_time_208{};
    float footplant_duration_212{};
    float footplant_surface_height_216{};
    std::uint32_t footplant_surface_224{};
    std::uint8_t footplant_left_449{};
    std::uint8_t footplant_right_450{};
    std::uint8_t reached_apex_436{};
    std::uint8_t flag_441{};
    std::uint8_t flag_446{};
    std::uint8_t flag_447{};
    std::uint8_t flag_448{};
    std::uint8_t use_air_reckoning_452{};
};
struct SkeletonOutputFields
{
    float hips_right_angle_496{};
    float hips_up_angle_500{};
    float twist_504{};
    float deck_yaw_536{};
    float deck_pitch_540{};
    float scalar_544{};
    float no_support_time_548{};
    float time_until_teleport_576{};
    float response_strength_580{};
    float extra_weight_584{};
    float response_change_588{};
    std::uint8_t flag_597{};
    std::uint8_t over_599{};
    std::uint8_t flag_600{};
    std::uint8_t flag_601{};
    std::uint8_t teleport_pending_604{};
    std::uint8_t response_changed_605{};
    RawMatrix anim_to_world_11920{};
    void PublishDeckAngles(Vec4 forward,bool board_flipped);
    void PublishTwist(const SkeletonPhysicalRecord&,Vec4 processed_forward_352,Vec4 reckoning_up_1152);
};
struct AnimationOutputFields
{
    float collision_time_144=std::numeric_limits<float>::max();
    std::uint32_t profile_148{};
    std::uint8_t tricks_blocked_on_stairs_166{};
    std::uint8_t manual_opposition_168{};
};
struct ScoringOutputFields
{
    std::uint32_t capabilities_204{};
};
struct GrindInvestigationFields
{
    RawVector tangent_1104{};
    RawVector point_1120{};
    RawVector direction_1136{};
    RawVector normal_1152{};
    RawVector target_up_1168{};
    RawVector entry_velocity_1184{};
    RawVector front_contact_1200{};
    RawVector rear_contact_1216{};
    RawVector vector_1232{};
    std::uint32_t family_1248{};
    std::uint32_t entry_kind_1252{};
    RawVector primitive_start_1264{};
    RawVector primitive_end_1280{};
    std::optional<std::uint64_t> owner_1296{};
    std::uint32_t primitive_flags_1300{};
    RawVector second_start_1312{};
    RawVector second_end_1328{};
    std::optional<std::uint64_t> second_owner_1344{};
    std::uint32_t second_flags_1348{};
    RawVector center_1360{};
    std::array<RawVector,2> far_points_1376_1392{};
    RawVector upmost_normal_1408{};
    RawVector surface_direction_1424{};
    RawVector high_side_1440{};
    std::array<float,2> normal_limits_1456_1460{};
    std::uint32_t geometry_kind_1464{};
    std::uint32_t audio_surface_1468{};
    std::uint32_t physics_surface_1472{};
    std::uint32_t geometry_flags_1476{};
    bool valid_1488{};
    float impact_speed_1492{};
    float friction_1496{};
    float exit_lean_1500{};
    float yaw_1504{};
    float pitch_1508{};
    float gravity_relief_1512{};
    std::uint32_t flags_1516{};
};
struct GrindOutputFields
{
    RawVector direction_0{0x3f800000,0,0,0};
    RawVector point_16{};
    RawVector normal_32{0,0x3f800000,0,0};
    RawVector across_48{0,0x3f800000,0,0};
    RawVector primitive_start_64{};
    RawVector primitive_end_80{};
    RawVector camera_target_96{};
    RawVector high_side_112{};
    float impact_speed_128{};
    float crouch_132{};
    std::array<std::uint32_t,2> words_136_140{0xffffffff,0};
    std::uint32_t animation_id_144{};
    std::uint32_t scoring_id_148{};
    std::uint32_t scorable_id_152=0xffffffff;
    std::optional<AttributeName> animation_name_156=EncodeAnimationName("");
    std::optional<AttributeName> scoring_name_176=EncodeAnimationName("");
    std::optional<AttributeName> surface_name_196{};
    std::uint32_t audio_surface_216{};
    std::array<std::uint64_t,2> spline_guids_224_232{0xffffffffffffffffULL,0xffffffffffffffffULL};
    std::uint32_t trick_out_240{};
    std::array<std::uint32_t,6> volatile_chromosome_244{0,0,0,0,0,0xffffffff};
    std::array<std::uint32_t,6> animation_chromosome_268{0,0,0,0,0,0xffffffff};
    std::array<std::uint32_t,6> scoring_chromosome_292{0,0,0,0,0,0xffffffff};
    std::uint8_t grinding_316{};
    std::uint8_t leaving_317{};
    std::uint8_t flag_318{};
    std::uint8_t flag_319{};
    std::uint8_t is_ledge_320{};
    std::uint8_t curb_321{};
    std::uint8_t flag_322{};
    std::uint8_t flag_323{};
    std::uint8_t dropping_in_324{};
    std::uint8_t tipslide_325{};
    std::uint8_t tipslide_326{};
    void ResetNames(std::optional<AttributeName> grind,std::optional<AttributeName> surface);
};
struct ProbeFields
{
    std::array<RawVector,3> vectors_16_32_48{};
    std::array<std::uint32_t,2> words_64_68{};
    std::array<std::uint8_t,2> bytes_72_73{};
    RawVector vector_80{};
    std::array<std::uint32_t,2> words_96_100{};
    std::uint8_t byte_104{};
};
struct LineTestFields
{
    RawVector position{};
    RawVector normal{};
    std::uint32_t surface{};
    std::uint8_t valid{};
};
struct StateVariantFields
{
    std::uint8_t surface_override_enabled_60{};
};
struct CurrentStateFields
{
    std::uint32_t identifier_8{};
    std::uint32_t category_12{};
    std::uint32_t state_16{};
    float surface_height_32{};
    std::uint32_t counter_36{};
    std::uint32_t skitch_value_40{};
    std::uint8_t flag_61{};
    std::uint8_t flag_66{};
    std::uint8_t flag_69{};
    std::uint8_t flag_74{};
    std::uint8_t signed_ground_step_84{};
};
struct SkateboardMotionFields
{
    RawVector vector_64{};
    RawVector vector_80{};
    RawVector vector_96{};
    RawVector vector_128{};
    RawVector vector_144{};
    float scalar_160{};
    float scalar_164{};
    float scalar_168{};
    float scalar_172{};
};
struct SystemReckoningFields
{
    RawVector vector_16{};
    RawVector vector_64{};
    RawVector vector_96{};
    RawVector vector_144{};
    std::uint8_t flag_164{};
};
struct GroundOutputFields
{
    std::int32_t landing_half_turns_312{};
    std::uint8_t hippy_jumping_322{};
    std::uint8_t hippy_takeoff_323{};
    RawVector vector_64{};
    RawVector vector_80{};
    std::uint8_t flag_273{};
    RawVector vector_96{};
    RawVector vector_128{};
    float scalar_276{};
    float scalar_292{};
    float scalar_296{};
    std::uint8_t flag_317{};
    std::uint8_t flag_318{};
};
struct CollisionOutputFields
{
    std::uint32_t wheel_count_0{};
    float scalar_28{};
    RawVector vector_48{};
    RawVector predicted_position_64{};
    std::uint8_t flag_215{};
    std::uint8_t flag_216{};
    std::array<std::uint8_t,4> wheel_contact_3296_3299{};
    std::uint8_t flag_3472{};
    std::uint8_t flag_3475{};
    std::uint8_t flag_3477{};
    std::uint8_t flag_3478{};
    std::uint8_t flag_3479{};
    std::uint8_t flag_3480{};
    std::uint8_t flag_3481{};
    std::uint8_t flag_3482{};
    std::uint8_t flag_3483{};
};
struct PhysicsOutputFields
{
    std::uint8_t flag_32{};
    RawVector vector_16{};
};
struct OffBoardOutputFields
{
    std::uint32_t kind_88{};
    float scalar_112{};
    float distance_116{};
    std::array<std::uint8_t,2> flags_306_307{};
    std::uint8_t flag_329{};
    std::uint8_t flag_330{};
    std::uint8_t flag_334{};
    float cadence_phase_80{};
    std::uint32_t locomotion_state_84{};
    float angle_36{};
    float angle_40{};
    float trajectory_time_120{};
    std::uint8_t trajectory_valid_331{};
    float scalar_32{};
    std::uint8_t flag_304{};
    std::uint8_t flag_308{};
    std::uint8_t flag_311{};
    std::uint8_t free_board_312{};
    std::uint8_t returning_board_313{};
    std::uint8_t flag_314{};
    std::uint8_t flag_315{};
    std::uint8_t flag_316{};
    std::uint8_t hippy_hurdling_317{};
    std::uint8_t flag_318{};
    std::uint8_t dropping_board_322{};
    std::uint8_t hiding_board_321{};
    std::uint8_t flag_319{};
    std::uint8_t retrieving_board_323{};
    std::uint8_t flag_324{};
    std::uint8_t flag_328{};
    RawVector vector_64{};
    float scalar_92{};
    RawVector vector_96{};
    std::uint32_t word_144{};
    float scalar_148{};
    float scalar_152{};
    float scalar_156{};
    RawVector vector_160{};
    RawVector vector_176{};
    RawVector vector_192{};
    RawVector vector_208{};
    RawVector vector_224{};
    RawVector vector_240{};
    std::uint8_t flag_320{};
};
struct PhysicalPlayerInput
{
    RawVector board_reckoning_side_176{};
    SkateboardMotionFields skateboard{};
    AirOutputFields air{};
    PhysicsOutputFields physics{};
    GrindOutputFields grinds{};
    SkeletonOutputFields skeleton{};
    AnimationOutputFields animation{};
    ScoringOutputFields scoring{};
    std::optional<TeleportOutputFields> teleport_output{};
    CollisionOutputFields collision{};
    CurrentStateFields state{};
    GroundOutputFields ground{};
    SystemReckoningFields reckoning{};
    std::uint32_t filtered_state_0{};
    OffBoardOutputFields off_board{};
    std::uint32_t surface_default_mode{};
    std::uint32_t component_1832_word_1876{};
};
struct AnimationInputPacket
{
    const AnimationPacketFields& publication;
    const ExternalPhysicsInput& external_physics_10512;
    std::uint8_t flag_10369{};
    std::uint8_t flag_10370{};
    std::uint8_t flag_10373{};
    std::uint8_t suppress_transition_10376{};
    std::uint8_t use_external_physics_10688{};
    std::uint8_t external_physics_flag_10689{};
    std::uint8_t flag_10786{};
    std::uint8_t flag_10787{};
    std::uint8_t force_braking_10796{};
    RawVector vector_10816{};
    RawVector vector_10832{};
    RawVector vector_10848{};
    RawVector vector_10864{};
    RawVector vector_10880{};
    RawVector vector_10896{};
    float scalar_10912{};
    float scalar_10916{};
    std::uint32_t state_variant_10928{};
    std::uint32_t flags_10932{};
};
struct PlayerInputState
{
    std::uint32_t manager_1856_counter_320{};
    std::uint8_t manager_1852_flag_256{};
    RawVector manager_1852_vector_176{};
    std::uint32_t flags_1296{};
    std::uint32_t grounded_frames_1300{};
    std::uint32_t state_count_1312{};
    std::uint32_t update_count_1316{};
    std::uint32_t spin_same_direction_frames_1324{};
    std::uint32_t frames_since_teleport_1328{};
    std::uint32_t dismount_request_frames_1332{};
    std::uint32_t state_value_1336{};
    float state_timer_1344{};
    float time_since_last_input_1348{};
    float time_on_ground_1352{};
    float signed_ground_time_1356{};
    float previous_spin_input_1360{};
    float previous_crouch_1364{};
    float time_off_board_1368{};
    std::uint32_t skitch_value_1372{};
    float skitch_timer_1376{};
    float ground_timer_1380{};
    float secondary_ground_timer_1384{};
    ProbeFields probe{};
    RawVector queued_vector_1280{};
    ExternalPhysicsInput external_physics_cache_1008{};
    RawVector prepared_jump_velocity_1184{};
    RawVector previous_ground_position_1200{};
    RawVector current_ground_position_1216{};
    RawVector ground_delta_1232{};
    RawVector damped_ground_delta_1248{};
    std::array<StateVariantFields,5> state_variants_1408{};
    LineTestFields hips_line_test_1488{};
    LineTestFields left_line_test_1536{};
    LineTestFields right_line_test_1584{};
    std::int32_t ground_history_frames_1304{};
};
struct ProcessedPhysicsInput
{
    RawMatrix effective_anim_transform_192{};
    std::array<RawVector,2> vectors_400_416{};
    std::array<RawVector,5> vectors_464_480_496_512_528{};
    std::array<RawVector,4> vectors_544_560_592_608{};
    std::array<RawVector,4> vectors_624_640_656_672{};
    RawVector prepared_jump_704{};
    RawVector collision_pose_error_736{};
    RawVector animation_com_to_deck_752{};
    RawVector animation_com_to_deck_delta_768{};
    std::array<RawVector,6> vectors_720_784_800_816_832_864{};
    std::array<RawVector,5> vectors_880_896_912_928_944{};
    std::array<LineTestFields,3> line_tests_960_1008_1056{};
    GrindInvestigationFields grind{};
    RawVector vector_1520{};
    RawMatrix matrix_1536{};
    std::uint8_t byte_1600{};
    ExternalPhysicsInput external_physics_1616{};
    ProbeFields probe_1792{};
    std::array<std::array<std::uint32_t,72>,2> grab_records_1888_2176{};
    std::uint32_t object_2464{};
    std::uint32_t flags_2468{};
    std::uint32_t flags_2472{};
    std::uint32_t flags_2476{};
    std::uint32_t flags_2480{};
    std::uint32_t flags_2484{};
    std::uint32_t flags_2488{};
    std::uint32_t state_identifier_2496{};
    std::uint32_t state_2504{};
    std::uint32_t state_2508{};
    std::uint32_t category_2512{};
    std::uint32_t category_2516{};
    std::uint32_t player_state_value_2520{};
    std::uint32_t filtered_state_2524{};
    std::uint32_t state_variant_index_2528{};
    std::array<std::uint32_t,2> grind_words_2532_2536{};
    std::uint32_t surface_mode_2540{};
    std::optional<NativeRelativeReference> surface_primary_ref_2544{};
    std::optional<NativeRelativeReference> state_variant_ref_2548{};
    std::optional<NativeRelativeReference> surface_secondary_ref_2552{};
    std::uint32_t wheel_count_2556{};
    std::uint32_t state_count_2564{};
    std::uint32_t update_count_2568{};
    std::uint32_t spin_same_direction_frames_2580{};
    std::uint32_t frames_since_teleport_2584{};
    std::uint32_t skitch_value_2592{};
    std::uint32_t left_surface_2596{};
    std::uint32_t right_surface_2600{};
    float timestep_2604{};
    float scalar_2612{};
    float scalar_2616{};
    float transition_2636{};
    float grind_adjusted_body_spin_2644{};
    float gravity_2648{};
    float scalar_2652{};
    float scalar_2656{};
    float state_timer_2664{};
    float scalar_2668{};
    float spin_input_2672{};
    float scalar_2696{};
    float scalar_2700{};
    float scalar_2736{};
    float time_since_last_input_2748{};
    float time_on_ground_2752{};
    float signed_ground_time_2756{};
    float truck_tightness_2760{};
    float scalar_2764{};
    float board_at_y_delta_2768{};
    float air_scalar_2772{};
    float crouch_2776{};
    float crouch_delta_2780{};
    float off_board_scalar_2832{};
    float time_off_board_2836{};
    float ground_timer_2848{};
    float secondary_ground_timer_2852{};
    float collision_scalar_2924{};
    std::uint32_t actor_query_2948{};
    std::uint32_t actor_query_2952{};
};
struct ProcessedPhysicsSnapshot
{
    std::uint64_t tick{};
    ProcessedPhysicsInput input{};
};
struct GroundHistoryRequest
{
    RawVector previous_position{};
    RawVector current_position{};
    RawVector previous_filtered_delta{};
    std::uint32_t timestep_bits{};
};
struct GroundHistoryResult
{
    RawVector delta{};
    RawVector filtered_delta{};
};
struct PrepareJumpRequest
{
    RawVector skateboard_vector{};
    RawVector previous_velocity{};
};
}
