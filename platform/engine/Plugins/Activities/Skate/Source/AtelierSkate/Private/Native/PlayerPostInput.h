#pragma once
#include <array>
#include <cstdint>
namespace atelier::skate
{
struct PostInputPlayerFields
{
    std::array<std::uint32_t,4> jump_reference_1264;
    std::uint32_t flags_1296,state_frames_1304,jump_fix_frames_1308,latch_frames_1320;
};
struct PostInputProcessedFields
{
    std::array<std::uint32_t,4> jump_reference_848;
    std::uint32_t word_2464,flags_2468,flags_2472,flags_2480,flags_2484,
        current_state_2508,state_frames_2572,jump_fix_frames_2576;
    float scalar_2740;
};
struct PostInputPhysOutFields
{
    bool reset_state_frames_316,capture_jump_reference_442;
    std::array<std::uint32_t,4> jump_reference_128;
    bool complete_76;
};
struct CandidatePublicationFields
{
    bool first_object_present_196,first_pending_288,second_object_present_500,second_pending_592;
    std::uint32_t staged_word_12768,staged_valid_12772,staged_latched_12776;
    bool staged_pending_12780;
};
enum class CandidateRegistration {First1888,Second2176};
// Actual independent owners are mandatory. Their host wrapper retains late
// errors until after this infallible source kernel has finished its local pass.
class PostInputServices
{
public:
    virtual ~PostInputServices()=default;
    virtual void UpdateGrindManager()=0;
    virtual std::uint8_t UpdateTrajectorySelector()=0;
    virtual float CalculateHeading()=0;
    virtual void RegisterCandidate(CandidateRegistration)=0;
};
struct PostInputContext
{
    PostInputPlayerFields& player;
    PostInputProcessedFields& processed;
    PostInputPhysOutFields& phys_out;
    CandidatePublicationFields& candidates;
};
void RunPostInput(PostInputContext,PostInputServices&);
void CopyGrabRecord(std::array<std::uint32_t,72>& destination,
    const std::array<std::uint32_t,72>& source);
}
