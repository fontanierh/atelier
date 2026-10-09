#include "AnimationPlayback.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input:detail::DataReader
{
    explicit Input(const std::vector<std::uint8_t>& value):DataReader{value} {}
    std::uint64_t Wide() {const auto low=Word(),high=Word();return low|(std::uint64_t(high)<<32);}
    std::vector<std::uint32_t> Words() {const auto n=Word();std::vector<std::uint32_t> v;for (std::uint32_t i=0;i<n;++i) v.push_back(Word());return v;}
    AttributeName Name() {AttributeName n;for (auto& v:n) v=Word();return n;}
    AnimationAttribute Attribute() {AnimationAttribute a;a.name=Name();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for (auto& p:a.payload) if (Word()!=0) p=Word();return a;}
    std::vector<AnimationAttribute> Attributes() {const auto n=Word();std::vector<AnimationAttribute> v;for (std::uint32_t i=0;i<n;++i) v.push_back(Attribute());return v;}
    Sqt Pose() {Sqt s;for (auto* v:{&s.scale,&s.rotation,&s.translation}) for (auto& x:*v) x=Float();return s;}
    ChannelSettings Settings() {ChannelSettings s;s.priority=std::int32_t(Word());s.keep_alive=Word()!=0;s.mirrored=Word()!=0;s.speed=Float();s.blend_in=Float();s.hold_during_blend_in=Word()!=0;s.blend_out=Float();s.hold_during_blend_out=Word()!=0;s.use_attributes=Word()!=0;return s;}
};
static void Word(std::uint32_t value) {for (unsigned i=0;i<4;++i) std::cout.put(char(value>>(8*i)));}
static void Wide(std::uint64_t value) {Word(std::uint32_t(value));Word(std::uint32_t(value>>32));}
static void String(std::string_view value) {Word(std::uint32_t(value.size()));std::cout.write(value.data(),value.size());}
static void Float(float value) {std::uint32_t bits;std::memcpy(&bits,&value,4);Word(bits);}
static void Attribute(const AnimationAttribute& a) {for (auto v:a.name) Word(v);Word(a.kind);Word(a.status);Word(std::uint32_t(a.sequence_id));Float(a.begin_time);Float(a.end_time);for (auto v:a.payload) {Word(v.has_value());if (v) Word(*v);}}
static void Attributes(const std::vector<AnimationAttribute>& values) {Word(std::uint32_t(values.size()));for (const auto& v:values) Attribute(v);}
static void Pose(const Sqt& s) {for (const auto* v:{&s.scale,&s.rotation,&s.translation}) for (auto x:*v) Float(x);}
static void Settings(ChannelSettings s) {Word(std::uint32_t(s.priority));Word(s.keep_alive);Word(s.mirrored);Float(s.speed);Float(s.blend_in);Word(s.hold_during_blend_in);Float(s.blend_out);Word(s.hold_during_blend_out);Word(s.use_attributes);}
static void Status(bool ok,const std::string& error) {Word(ok);if (!ok) String(error);}
static std::vector<std::uint8_t> Read(const std::string& path) {std::ifstream file(path,std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
static PlaybackClip Clip(Input& r)
{
    const auto frames=r.Float(),fps=r.Float(),base=r.Float();const auto flags=r.Word(),n=r.Word();std::vector<PlaybackClipAttribute> attrs;
    for (std::uint32_t i=0;i<n;++i) {PlaybackClipAttribute a;a.name=r.Name();a.kind=std::uint8_t(r.Word());a.begin=r.Float();a.end=r.Float();a.payload=r.Words();attrs.push_back(std::move(a));}
    PlaybackClip c(frames,fps,base,flags,std::move(attrs));c.clock.time=r.Float();c.clock.previous_time=r.Float();c.clock.loops_since_evaluation=r.Word();return c;
}
static void DumpClock(const PlaybackClip& c,AdvanceResult r)
{
    for (auto value:{c.clock.time,c.clock.previous_time,c.clock.length,c.clock.speed,c.clock.SampleTime()}) Float(value);Word(c.clock.loops_since_evaluation);
    Word(r.crossed_end);Float(r.overshoot);Float(r.remaining_before_wrap);
    for (const auto p:{std::pair<float,float>{-1,-1},{0,0},{0,1},{0.25f,0.75f},{1,1},{1,0},{-0.0f,0.5f}}) Word(c.clock.AttributeStatus(p.first,p.second));
}
int main(int argc,char** argv)
{
    if (argc!=2) return 1;const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input r(bytes);const auto cases=r.Word();std::string error;
    for (std::uint32_t index=0;index<cases;++index) switch (r.Word())
    {
        case 1:{auto c=Clip(r);const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {AdvanceResult result{r.Word()!=0,r.Float(),r.Float()};switch (r.Word()) {case 0:{const auto dt=r.Float(),phase=r.Float();if (!c.clock.Advance(dt,phase,result,error)) return 3;break;}case 1:c.clock.SetSpeed(r.Float());break;case 2:c.clock.SetTime(r.Float());break;case 3:c.clock.CommitEvaluation();break;default:return 2;}DumpClock(c,result);}break;}
        case 2:{const auto words=r.Words();const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {float output;const bool ok=SampleAnimationCurve(words,r.Float(),output,error);Status(ok,error);if (ok) Float(output);}break;}
        case 3:{const auto c=Clip(r);const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {const auto mask=r.Word();const auto name=r.Name();std::vector<AnimationAttribute> a;const bool bulk=c.Attributes(mask,a,error);Status(bulk,error);if (bulk) Attributes(a);
            std::optional<AnimationAttribute> output;const bool one=c.Attribute(name,mask,output,error);if (!one) Status(false,error);else if (!output) Word(2);else {Word(1);Attribute(*output);}}break;}
        case 4:{const auto op=r.Word();auto a=r.Attribute();const auto b=r.Attribute();const auto weight=r.Float();AttributeMirror mirror;const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {const auto source=r.Name(),target=r.Name();mirror.names.emplace_back(source,target);}bool ok=false;
            switch (op) {case 0:ok=BlendAnimationAttribute(a,b,weight,error);break;case 1:ok=ScaleAnimationAttribute(a,weight,error);break;case 2:ok=AddWeightedAnimationAttribute(a,b,weight,error);break;case 3:a.CopyFrom(b);ok=true;break;case 4:ok=mirror.Apply(a,error);break;default:return 2;}Status(ok,error);Attribute(a);break;}
        case 5:{ChannelPlayback c(r.Settings());const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {bool advances=false;switch (r.Word()) {case 0:{const auto dt=r.Float(),length=r.Float(),time=r.Float();c.influence=r.Float();advances=c.Advance(dt,length,time);break;}case 1:c.End();break;case 2:{const auto seconds=r.Float();const bool hold=r.Word()!=0;c.EndWith(seconds,hold);break;}case 3:{const auto settings=r.Settings();const bool resurrect=r.Word()!=0;c.Transition(settings,resurrect);break;}case 4:c.DidAdvance({r.Word()!=0,0,0});break;default:return 2;}
            Word(advances);Float(c.weight);Float(c.influence);Word(c.Expired());Word(c.CanTransition(false));Word(c.CanTransition(true));Settings(c.settings);}const auto a=r.Attributes(),b=r.Attributes();Attributes(c.MergeAttributes(a,b));break;}
        case 6:{const auto n=r.Word();std::vector<SelectionParameter> ps;std::vector<float> vs,cs;for (std::uint32_t i=0;i<n;++i) {SelectionParameter p;p.mode=r.Word();p.weight=r.Float();p.minimum=r.Float();p.maximum=r.Float();ps.push_back(p);vs.push_back(r.Float());cs.push_back(r.Float());}Float(SelectionDistance(ps,vs,cs));break;}
        case 7:{const auto time=r.Float(),fps=r.Float();const auto frames=r.Wide();const bool blend=r.Word()!=0;const auto offset=r.Float();FrameSelection result;const bool ok=SelectAnimationFrames(time,fps,std::size_t(frames),blend,offset,result,error);Status(ok,error);if (ok) {Wide(result.first);Wide(result.second);Float(result.coefficient);}break;}
        case 8:{const auto op=r.Word();const auto weight=r.Float();const bool use_first=r.Word()!=0;const auto n=r.Word();std::vector<std::vector<Sqt>> poses;std::vector<float> weights;for (std::uint32_t i=0;i<n;++i) {weights.push_back(r.Float());const auto bones=r.Word();std::vector<Sqt> p;for (std::uint32_t j=0;j<bones;++j) p.push_back(r.Pose());poses.push_back(std::move(p));}
            if (op==2) {std::vector<Sqt> result;const bool ok=WeightedBlendPoses(poses,weights,result,error);Status(ok,error);if (ok) {Word(std::uint32_t(result.size()));for (const auto& s:result) Pose(s);}}
            else {Word(1);Word(1);Pose(op==0?BlendPoseSample(poses[0][0],poses[1][0],weight):ChannelBlendPoseSample(poses[0][0],poses[1][0],weight,use_first));}break;}
        case 9:{PacketAttributes packet;const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {switch (r.Word()) {case 0:packet.Clear();break;case 1:packet.Append(r.Attribute());break;case 2:{const auto m=r.Word();std::vector<MotionGraphAttribute> motion;for (std::uint32_t j=0;j<m;++j) {MotionGraphAttribute a;a.name=r.Name();a.value=r.Float();motion.push_back(a);}packet.ReplaceFrom(motion,r.Attributes());break;}default:return 2;}Word(std::uint32_t(packet.Size()));for (std::size_t j=0;j<packet.Size();++j) Attribute(packet[j]);}break;}
        case 10:{const auto name=r.String();AnimationClipSamples clip;if (!clip.Load(Read(std::string(argv[1])+"/clips/"+name+".skate"),error)) return 2;const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {std::vector<Sqt> output;const bool ok=SampleAnimationClip(clip,r.Float(),output,error);Status(ok,error);if (ok) {Word(std::uint32_t(output.size()));for (const auto& s:output) Pose(s);}}break;}
        case 11:{const auto left=r.Attributes(),right=r.Attributes();const auto weight=r.Float();std::vector<AnimationAttribute> output;const bool ok=IntersectAnimationAttributes(left,right,weight,output,error);Status(ok,error);if (ok) Attributes(output);break;}
        case 12:{SettableAttributes entries;const auto n=r.Word();for (std::uint32_t i=0;i<n;++i) {if (r.Word()==0) entries.Clear();else {SettableAttribute a;a.name=r.Name();a.value=r.Float();a.normalized=r.Word()!=0;a.sequence_id=std::int32_t(r.Word());entries.SetAttribute(a);}Word(std::uint32_t(entries.Entries().size()));for (const auto& a:entries.Entries()) {for (auto w:a.name) Word(w);Float(a.value);Word(a.normalized);Word(std::uint32_t(a.sequence_id));}}break;}
        case 13:{auto c=Clip(r);c.clock.length=r.Float();AdvanceResult result{r.Word()!=0,r.Float(),r.Float()};const auto dt=r.Float(),phase=r.Float();const bool ok=c.clock.Advance(dt,phase,result,error);Status(ok,error);DumpClock(c,result);break;}
        default:return 2;
    }
    if (!r.ok || r.Remaining()!=0) return 2;return std::cout?0:2;
}
