#pragma once
#include "SkeletonAttributeDispatch.h"
#include "AnimationSamples.h"
#include "Settings.h"
namespace atelier::skate
{
// Actual host animation_input.rs owner. Contact speed is derived from the
// current trajectory hierarchy by the kind3 contact handler.
class PhysicsAnimationInput
{
public:
    ScalarAttributeInputs fields=ScalarAttributeInputs::Reset(0,0);
    ExtendedAttributes extra=ExtendedAttributes::Reset(0);
    ContactEventState contacts{};
    AnimationControlOutput output{EncodeAnimationName(""),0};
    bool Load(const SettingsDatabase&,const AnimationRig&,std::string_view mode,std::string& error);
    bool SelectPhysicsMode(std::uint32_t mode,std::string& error);
    void ResetProcessed();
    void FinishOutputPublication();
    bool Process(const std::vector<AnimationAttribute>& attributes,const std::vector<Mat4>& hierarchy,
        float timestep,std::uint32_t animation_flags,bool external_impulse_active,ActionMap&,std::string& error);
    const JumpAttributeState& JumpCache() const {return cached_jump_;}
    const FinalizationInput& Settings() const {return settings_;}
    const std::vector<AttributeName>& BoneNames() const {return bone_names_;}
    std::size_t RightToe() const {return right_toe_;}
    const std::array<bool,5>& HeightOverrides() const {return height_overrides_;}
private:
    JumpAttributeState cached_jump_{};
    std::vector<AttributeName> bone_names_;
    std::size_t right_toe_=0;
    FinalizationInput settings_{};
    std::array<bool,5> height_overrides_{};
};
}
