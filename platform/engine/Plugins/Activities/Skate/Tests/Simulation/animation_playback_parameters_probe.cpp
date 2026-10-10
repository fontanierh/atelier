#include "AnimationPlaybackParameters.h"
#include "DataReader.h"
#include <iostream>
#include <iterator>
#include <map>
using namespace atelier::skate;
struct Writer
{
    std::vector<std::uint8_t> data;
    void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) data.push_back(std::uint8_t(v>>(8*i)));}
    void Float(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    void String(std::string_view v) {Word(std::uint32_t(v.size()));data.insert(data.end(),v.begin(),v.end());}
    void Name(AttributeName v) {for (auto w:v) Word(w);}
    void Attribute(const AnimationAttribute& a) {Name(a.name);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto p:a.payload) {Word(p.has_value());if (p) Word(*p);}}
    void Transition(TransitionSettings s) {Word(s.kind);Float(s.seconds);Word(s.under);Word(s.matching);Word(s.use_channels_from_weights);}
    void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
};
struct Service:PlaybackService
{
    std::map<std::string,float> motion,filtered;
    std::map<AttributeName,AnimationAttribute> last;
    std::optional<std::string> last_error;
    std::vector<std::pair<std::uint32_t,std::string>> responses;
    std::size_t played=0;
    mutable Writer events;
    std::optional<float> MotionIntent(std::string_view name) const override {const auto i=motion.find(std::string(name));events.Word(1);events.String(name);events.Word(i!=motion.end());if (i!=motion.end()) {events.Float(i->second);return i->second;}return {};}
    std::optional<float> FilteredIntent(std::string_view name) const override {const auto i=filtered.find(std::string(name));events.Word(2);events.String(name);events.Word(i!=filtered.end());if (i!=filtered.end()) {events.Float(i->second);return i->second;}return {};}
    bool LastAttribute(AttributeName name,std::optional<AnimationAttribute>& output,std::string& error) override {events.Word(3);events.Name(name);if (last_error) {events.Word(2);events.String(*last_error);error=*last_error;return false;}const auto i=last.find(name);events.Word(i!=last.end());if (i!=last.end()) {output=i->second;events.Attribute(i->second);}else output.reset();error.clear();return true;}
    void SetAttribute(SettableAttribute a) override {events.Word(4);events.Name(a.name);events.Float(a.value);events.Word(a.normalized);events.Word(std::uint32_t(a.sequence_id));for (auto& entry:motion) if (EncodeAnimationName(entry.first)==a.name) entry.second=a.value;}
    void SetConstructionValue(AttributeName name,AttributeName value) override {events.Word(5);events.Name(name);events.Name(value);}
    void SetPostureEnabled(bool value) override {events.Word(6);events.Word(value);}
    bool Play(const PlaybackRequest& request,bool& did_play,std::string& error) override {events.Word(7);events.String(request.animation);events.Float(request.speed);events.Float(request.start_time);events.Transition(request.transition);const auto response=played<responses.size()?responses[played]:std::pair<std::uint32_t,std::string>{1,{}};++played;events.Word(response.first);if (response.first==2) {events.String(response.second);error=response.second;return false;}did_play=response.first!=0;error.clear();return true;}
};
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& bytes):DataReader{bytes} {}
    AttributeName Name() {AttributeName n;for (auto& w:n) w=Word();return n;}
    AnimationAttribute Attribute() {AnimationAttribute a;a.name=Name();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for (auto& p:a.payload) if (Word()!=0) p=Word();return a;}
    std::optional<std::string> OptionalString() {if (Word()!=0) return String();return {};}
    TransitionSettings Transition() {TransitionSettings s;s.kind=Word();s.seconds=Float();s.under=Word();s.matching=Word();s.use_channels_from_weights=Word()!=0;return s;}
    PlaybackParameter Parameter() {PlaybackParameter p;p.source=PlaybackParameterSource(Word());if (p.source==PlaybackParameterSource::LastAnimation) p.last_animation=Name();else p.intent=String();if (Word()!=0) p.rename=Name();if (Word()!=0) p.default_value=Float();p.normalized=Word()!=0;return p;}
    std::vector<PlaybackParameter> Parameters() {const auto n=Word();std::vector<PlaybackParameter> ps;for (std::uint32_t i=0;i<n;++i) ps.push_back(Parameter());return ps;}
    PlayAnimation Operation() {PlayAnimation o;o.animation=String();o.switch_animation=OptionalString();o.mirror_animation=OptionalString();o.no_board_animation=OptionalString();o.playback_speed=Float();o.apply_posture=Word()!=0;o.transition=Transition();o.parameters=Parameters();return o;}
    std::optional<bool> OptionalBool() {const auto v=Word();return v==0?std::nullopt:std::optional<bool>(v==2);}
    PlaybackContext Context() {PlaybackContext c;c.is_switch=OptionalBool();c.is_mirrored=OptionalBool();c.board_available=OptionalBool();c.pro_skater=Name();if (Word()!=0) c.transition_override=Transition();return c;}
    std::map<std::string,float> Values() {std::map<std::string,float> values;const auto n=Word();for (std::uint32_t i=0;i<n;++i) {const auto name=String();const auto value=Float();values[name]=value;}return values;}
    Service Host() {Service s;s.motion=Values();s.filtered=Values();s.last_error=OptionalString();auto n=Word();for (std::uint32_t i=0;i<n;++i) {auto a=Attribute();s.last[a.name]=a;}n=Word();for (std::uint32_t i=0;i<n;++i) {const auto kind=Word();const auto error=kind==2?String():std::string{};s.responses.emplace_back(kind,error);}return s;}
};
int main()
{
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);Writer output;const auto n=input.Word();std::string error;
    for (std::uint32_t i=0;i<n;++i)
    {
        const auto kind=input.Word();auto service=input.Host();
        if (kind==1) {const bool beginning=input.Word()!=0;for (const auto& p:input.Parameters()) output.Status(p.Update(beginning,service,service,error),error);}
        else
        {
            const auto operation=input.Operation();auto context=input.Context();PlayAnimationInstance instance;const auto steps=input.Word();
            for (std::uint32_t j=0;j<steps;++j)
            {
                bool ok=true;switch (input.Word()) {case 0:ok=instance.Begin(operation,context,service,error);break;case 1:ok=instance.Update(operation,service,error);break;case 2:instance.End();break;case 3:service.motion=input.Values();break;default:return 2;}
                output.Status(ok,error);output.Word(context.transition_override.has_value());if (context.transition_override) output.Transition(*context.transition_override);
            }
        }
        output.Word(std::uint32_t(service.events.data.size()));output.data.insert(output.data.end(),service.events.data.begin(),service.events.data.end());
    }
    if (!input.ok || input.Remaining()!=0) return 2;std::cout.write(reinterpret_cast<const char*>(output.data.data()),output.data.size());return std::cout?0:2;
}
