// Shared tree protocol scaffolding is prepended by the parity driver.
#include "AnimationChannels.h"
static ChannelSettings Settings(Input& input)
{
    ChannelSettings s;s.priority=std::int32_t(input.Word());s.keep_alive=input.Word()!=0;s.mirrored=input.Word()!=0;s.speed=input.Float();s.blend_in=input.Float();s.hold_during_blend_in=input.Word()!=0;s.blend_out=input.Float();s.hold_during_blend_out=input.Word()!=0;s.use_attributes=input.Word()!=0;return s;
}
static void ChannelSnapshot(const AnimationChannels& channels)
{
    Word(std::uint32_t(channels.Entries().size()));for (const auto& c:channels.Entries())
    {
        String(c.name);const auto& s=c.playback.settings;Word(std::uint32_t(s.priority));Word(s.keep_alive);Word(s.mirrored);Float(s.speed);Float(s.blend_in);Word(s.hold_during_blend_in);Float(s.blend_out);Word(s.hold_during_blend_out);Word(s.use_attributes);
        Float(c.playback.weight);Float(c.playback.influence);Word(c.playback.Expired());Word(c.playback.CanTransition(false));Word(c.playback.CanTransition(true));Snapshot(c.tree);
    }
}
int main(int argc,char** argv)
{
    if (argc!=2) return 1;AnimationMetadata fixture;std::string error;if (!Load(fixture,{argv[1]},error)) return 2;
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);const auto count=input.Word();
    for (std::uint32_t i=0;i<count;++i)
    {
        AnimationChannels channels;const auto n=input.Word();for (std::uint32_t j=0;j<n;++j)
        {
            switch (input.Word())
            {
                case 0:{const auto name=input.String();AnimationTree tree;if (!input.Tree(tree,error)) return 2;const auto settings=Settings(input);channels.Insert(name,std::move(tree),settings);Status(true,error);break;}
                case 1:channels.End(input.String());Status(true,error);break;
                case 2:{const auto name=input.String();const auto seconds=input.Float();const bool last=input.Word()!=0;channels.EndWith(name,seconds,last);Status(true,error);break;}
                case 3:{const auto name=input.String();const auto value=input.Float();Boolean(true,channels.Influence(name,value),error);break;}
                case 4:{const auto name=input.String();Boolean(true,channels.CanTransition(name,input.Word()!=0),error);break;}
                case 5:{const auto name=input.String();AnimationTree tree;if (!input.Tree(tree,error)) return 2;const auto settings=Settings(input);const auto transition=input.Transition();const bool resurrect=input.Word()!=0;channels.Transition(name,std::move(tree),settings,transition,resurrect);Status(true,error);break;}
                case 6:channels.Retire();Status(true,error);break;
                case 7:{const auto dt=input.Float(),phase=input.Float();Status(channels.Advance(dt,phase,error),error);break;}
                case 8:{const auto a=input.Settable();Status(channels.PrepareSelectionSpaces(a,error),error);break;}
                case 9:{const auto a=input.Settable();Status(channels.SetAttributes(a,error),error);break;}
                case 10:{const auto n=input.Word();std::vector<AnimationAttribute> base;for (std::uint32_t k=0;k<n;++k) base.push_back(input.Attribute());const auto mask=input.Word();std::vector<AnimationAttribute> output;const bool ok=channels.Attributes(std::move(base),mask,output,error);Status(ok,error);if (ok) Attributes(output);break;}
                case 11:{const auto name=input.Name();const auto mask=input.Word();auto a=input.Attribute();bool found=false;const bool ok=channels.QueryAttribute(name,mask,a,found,error);Boolean(ok,found,error);Attribute(a);break;}
                case 12:{const AnimationEvaluation p{input.Float(),input.Word()!=0};std::vector<PoseCommand> c(1);c[0].kind=PoseCommand::Kind::Pose;c[0].name="SENTINEL";Status(channels.Evaluate(p,c,error),error);Commands(c);break;}
                case 13:{const auto n=input.Word();Word(n);for (std::uint32_t k=0;k<n;++k) {const auto name=input.String();Word(channels.Has(name));Float(channels.Remaining(name));Float(channels.Elapsed(name));Word(channels.InTransition(name));}break;}
                case 14:channels.ResetFromStock();Status(true,error);break;
                default:return 2;
            }
            ChannelSnapshot(channels);
        }
    }
    if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
