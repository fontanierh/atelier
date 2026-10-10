#include "OffboardSettings.h"
#include "OffboardControllerMath.h"
#include "StockSettingsReader.h"
#include <algorithm>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
const SettingValue* OffboardField(const SettingsDatabase& data,std::string_view category,std::string_view name,std::string& error)
{
    const auto* field=data.Field(category,"default",name);
    if(!field){std::vector<std::uint32_t> ignored;StockSettingsReader(data).Words(category,"default",name,0,ignored,error);}
    return field;
}
template<std::size_t N>bool OffboardCurve(const SettingsDatabase& data,std::string_view category,std::string_view name,PointGraph<N>& graph,std::array<float,4>& bounds,std::string& error)
{
    const auto* field=OffboardField(data,category,name,error);if(!field)return false;
    const auto path=std::string(category)+"/default/"+std::string(name),type="Sk8::PointNegGraphData"+std::to_string(N);
    if(field->type!=type){error="Expected PointNegGraphData"+std::to_string(N)+" at "+path;return false;}
    const std::uint32_t* words=nullptr;if(!field->Words(4+2*N,words)){error=path+": Invalid native graph payload length";return false;}
    std::array<float,4+2*N> values{};for(std::size_t n=0;n<values.size();++n)values[n]=biped_math::Bits(words[n]);
    if(std::any_of(values.begin(),values.end(),[](float v){return !std::isfinite(v);})){error=path+": Non-finite native graph value";return false;}
    PointGraph<N> next;for(std::size_t n=0;n<N;++n){next.x[n]=values[4+n];next.y[n]=values[4+N+n];}
    for(std::size_t n=1;n<N;++n)if(next.x[n-1]>next.x[n]){error=path+": Native graph X values are not ordered";return false;}
    std::copy_n(values.begin(),4,bounds.begin());graph=next;return true;
}
template<std::size_t N>bool OffboardCurve(const SettingsDatabase& d,std::string_view c,std::string_view n,PointGraph<N>& g,std::string& e)
{std::array<float,4> ignored{};return OffboardCurve(d,c,n,g,ignored,e);}
bool OffboardMetric(const AnimationMetadata& metadata,std::string_view name,std::optional<BipedClipMetric>& result,std::string& error)
{
    const auto* clip=metadata.Clip(name,error);if(!clip)return false;
    const auto* source=metadata.SourceFor(name);if(!source){error="Missing bank identity for "+std::string(name);return false;}
    auto bank=source->source_bank;for(auto& c:bank)if(c>='A'&&c<='Z')c=char(c-'A'+'a');
    if(bank!="offboard.abin"){error=std::string(name)+": expected actual OffBoard.abin source";return false;}
    const auto attribute=std::find_if(clip->attributes.begin(),clip->attributes.end(),[](const auto& a){return a.name=="ANIMTRANSZ";});
    if(attribute==clip->attributes.end()){result.reset();return true;}
    if(attribute->type_id!=0){error=clip->name+": AnimTransZ expected scalar stock record";return false;}
    if(attribute->payload_words.empty()){error=clip->name+": truncated AnimTransZ";return false;}
    const auto translation=biped_math::Bits(attribute->payload_words.front());
    const auto length=biped_math::Bits(clip->frames_bits)/biped_math::Bits(clip->fps_bits),end=biped_math::Bits(attribute->end_bits)*length;
    if(!std::isfinite(translation)||!std::isfinite(end)||end==0){error=clip->name+": invalid AnimTransZ metric";return false;}
    result=BipedClipMetric{translation,end};return true;
}
bool OffboardBoardVector(const SettingsDatabase& data,std::string_view name,Vec4& output,std::string& error)
{
    const auto* field=OffboardField(data,"physics_state_offboard",name,error);if(!field)return false;
    if(field->type!="Math::Vector3"){error=std::string(name)+": expected stock Vector3";return false;}
    std::vector<std::uint32_t> words;if(!StockSettingsReader(data).Words("physics_state_offboard","default",name,4,words,error))return false;
    Vec4 value{};for(std::size_t n=0;n<4;++n)value[n]=biped_math::Bits(words[n]);
    if(std::any_of(value.begin(),value.end(),[](float v){return !std::isfinite(v);})){error=std::string(name)+": non-finite vector";return false;}
    output=value;return true;
}
}
bool OffboardSettings::Load(const SettingsDatabase& data,const AnimationMetadata& metadata,std::string& error)
{
    OffboardSettings next;std::array<float,4> bounds{};auto& intent=next.controller.movement_intent;auto& velocity=next.controller.movement_velocity;
    if(!OffboardCurve(data,"physics_biped","Hash_6B93C51256A30FB4",intent.sprint_blend,bounds,error))return false;
    intent.sprint_time_cap=bounds[2];
    if(!OffboardCurve(data,"physics_biped","Hash_7209DCFDF3015EBF",intent.sprint_speed,error)||
       !OffboardCurve(data,"physics_biped","SpeedVsInput",intent.normal_speed,error)||
       !OffboardCurve(data,"physics_biped","AutoTurnVsAngle",intent.slide_steering,error)||
       !OffboardCurve(data,"physics_biped","Hash_31309236050A8F09",velocity.slope_speed_scalar,error)||
       !OffboardCurve(data,"physics_biped","Hash_CE45C724B30F9134",velocity.slope_mode_speed,error)||
       !OffboardCurve(data,"physics_biped","TurnVsSpeed",velocity.turn_vs_speed,error)||
       !OffboardCurve(data,"physics_biped","TurnDeltaVsSpeed",velocity.turn_delta_vs_speed,error)||
       !OffboardCurve(data,"physics_biped","SlideVsSlope",next.controller.slide_vs_slope,error)||
       !OffboardCurve(data,"physics_biped","SlideVsSpeed",next.controller.slide_vs_speed,error))return false;
    const std::array<std::string_view,3> clips{"NB_WALK_FWD_CYC","NB_RUN_FWD_CYC","NB_SPRINT_FWD_CYC"};
    for(std::size_t n=0;n<3;++n)if(!OffboardMetric(metadata,clips[n],next.metrics[n],error))return false;
    auto& board=next.board;const StockSettingsReader reader(data);
    if(!OffboardBoardVector(data,"GrabBoxSizeGrabbing",board.extent_0,error)||!OffboardBoardVector(data,"GrabBoxSize",board.extent_16,error)||!OffboardBoardVector(data,"GrabBoxOffset",board.offset_32,error)||
       !reader.Float("physics_state_offboard","default","GrabSplineMaxAngleToHorizontalGrabbing",board.angle_436,error)||
       !reader.Float("physics_state_offboard","default","GrabSplineMaxAngleToHorizontal",board.angle_440,error)||
       !reader.Float("physics_state_offboard","default","GrabSplineEndExclusion",board.margin_444,error)||
       !reader.Float("physics_state_offboard","default","GrabSplineAngleLimitGrabbing",board.angle_452,error)||
       !reader.Float("physics_state_offboard","default","GrabSplineAngleLimit",board.angle_456,error)||
       !OffboardCurve(data,"physics_state_offboard","Hash_DF759B46440F16E9",next.movement_vs_stick_angle,error)||
       !OffboardCurve(data,"physics_state_offboard","TurnVsStickAngle",next.turn_vs_stick_angle,error)||
       !reader.Float("physics_biped","default","JumpSpeedScalar",next.air_launch.jump_speed_scalar,error)||
       !reader.Float("physics_biped","default","JumpHeight",next.air_launch.jump_height,error))return false;
    *this=std::move(next);error.clear();return true;
}
}
