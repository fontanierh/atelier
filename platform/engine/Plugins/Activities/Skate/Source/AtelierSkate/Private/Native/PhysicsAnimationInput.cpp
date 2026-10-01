// SPDX-License-Identifier: Apache-2.0
#include "PhysicsAnimationInput.h"
#include "StockSettingsReader.h"
namespace atelier::skate
{
namespace
{
bool EqualAscii(std::string_view a,std::string_view b)
{
    if (a.size()!=b.size()) return false;
    const auto lower=[](unsigned char c) {return c>='A'&&c<='Z'?static_cast<unsigned char>(c+32):c;};
    for (std::size_t i=0;i<a.size();++i) if (lower(static_cast<unsigned char>(a[i]))!=lower(static_cast<unsigned char>(b[i]))) return false;
    return true;
}
}
bool PhysicsAnimationInput::Load(const SettingsDatabase& data,const AnimationRig& rig,std::string_view mode,std::string& error)
{
    std::optional<std::size_t> toe;
    for (std::size_t i=0;i<rig.bones.size();++i) if (EqualAscii(rig.bones[i].name,"RightToeBase")) {toe=i;break;}
    if (!toe) {error="Stock skeleton is missing RightToeBase";return false;}
    PhysicsAnimationInput next;StockSettingsReader reader(data);
    constexpr std::array<std::string_view,5> modes{"easy","normal","hardcore","motorized","test"};
    for (std::size_t i=0;i<5;++i) if (!reader.Boolean("physics_mode",modes[i],"JumpHeightOverrideEnabled",next.height_overrides_[i],error)) return false;
    for (const auto& bone:rig.bones) next.bone_names_.push_back(EncodeAnimationName(bone.name));
    next.right_toe_=*toe;
    if (!reader.Boolean("anim_motion","jumping","clamp_jump",next.settings_.select_jump_extremes,error)
        ||!reader.Float("anim_motion","jumping","clamp_low_inclusive",next.settings_.low_jump_threshold,error)
        ||!reader.Float("anim_motion","jumping","clamp_high_inclusive",next.settings_.high_jump_threshold,error)
        ||!reader.Boolean("physics_mode",mode,"JumpHeightOverrideEnabled",next.settings_.allow_height_override,error)
        ||!reader.Boolean("physics_jump","default","AdjustOnPrepare",next.settings_.use_prepared_controls,error)) return false;
    *this=std::move(next);error.clear();return true;
}
bool PhysicsAnimationInput::SelectPhysicsMode(std::uint32_t mode,std::string& error)
{
    if (mode>=height_overrides_.size()) {error="Invalid animation physics mode "+std::to_string(mode);return false;}
    settings_.allow_height_override=height_overrides_[mode];error.clear();return true;
}
void PhysicsAnimationInput::ResetProcessed()
{
    fields=ScalarAttributeInputs::Reset(fields.flags2468,fields.flags2488);
    extra=ExtendedAttributes::Reset(extra.footstep_strength);
    contacts={0,0};
}
void PhysicsAnimationInput::FinishOutputPublication()
{
    output.grind_name=EncodeAnimationName("");output.flags&=0x003fffff;extra.footstep_strength=0;
}
bool PhysicsAnimationInput::Process(const std::vector<AnimationAttribute>& attributes,const std::vector<Mat4>& hierarchy,
    float timestep,std::uint32_t flags,bool impulse,ActionMap& map,std::string& error)
{
    const ContactEventPose pose{bone_names_,hierarchy,0,std::int32_t(right_toe_),timestep};
    auto finalization=settings_;finalization.animation_flags=flags;finalization.external_impulse_active=impulse;
    return ProcessSkeletonAttributes(attributes,pose,fields,extra,contacts,cached_jump_,output,finalization,&map,error);
}
}
