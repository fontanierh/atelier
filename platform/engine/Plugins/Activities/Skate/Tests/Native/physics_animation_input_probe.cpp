// SPDX-License-Identifier: Apache-2.0
#include "PhysicsAnimationInput.h"
#include "DataReader.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
struct Input
{
    detail::DataReader r;
    explicit Input(const std::vector<std::uint8_t>& b):r{b} {r.at=0;}
    std::uint32_t Word() {return r.Word();}
    float Float() {const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
    template<std::size_t N> std::array<float,N> Floats() {std::array<float,N> a;for (auto& f:a) f=Float();return a;}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> a;for (auto& f:a) f=Word();return a;}
    std::string String() {return r.String();}
    AnimationAttribute Attribute() {AnimationAttribute a;a.name=Words<5>();a.kind=std::uint8_t(Word());a.status=std::uint8_t(Word());a.sequence_id=std::int32_t(Word());a.begin_time=Float();a.end_time=Float();for (auto& w:a.payload) {if (Word()) w=Word();else w.reset();}return a;}
};
struct Output
{
    std::vector<std::uint8_t> bytes;
    void Word(std::uint32_t w) {for (unsigned i=0;i<4;++i) bytes.push_back(std::uint8_t(w>>(i*8)));}
    void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
    void String(std::string_view s) {Word(std::uint32_t(s.size()));bytes.insert(bytes.end(),s.begin(),s.end());}
    void Block(const Output& s) {Word(std::uint32_t(s.bytes.size()/4));bytes.insert(bytes.end(),s.bytes.begin(),s.bytes.end());}
};
// GENERATED_PROTOCOL
struct Actions final:ActionMap
{
    std::array<float,18> values{};std::vector<std::uint32_t> calls;
    float Value(std::uint32_t action) override {calls.push_back(action);return values[action-64];}
    std::uint8_t State(std::uint32_t action) override {return Value(action)!=0;}
};
std::vector<std::uint8_t> Read(std::string path) {std::ifstream s(path,std::ios::binary);return {std::istreambuf_iterator<char>(s),{}};}
void Snapshot(Output& out,const PhysicsAnimationInput& input,const Actions& actions)
{
    Output row;Observe(row,input.fields);Observe(row,input.extra);Observe(row,input.contacts);Observe(row,input.output);Observe(row,input.JumpCache());Observe(row,input.Settings());
    for (bool value:input.HeightOverrides()) row.Word(value);row.Word(std::uint32_t(input.RightToe()));row.Word(std::uint32_t(input.BoneNames().size()));for (auto name:input.BoneNames()) for (auto w:name) row.Word(w);row.Word(std::uint32_t(actions.calls.size()));for (auto action:actions.calls) row.Word(action);out.Block(row);
}
int main(int argc,char** argv)
{
    if (argc!=3) return 2;SettingsDatabase settings;AnimationRig original;std::string error;if (!settings.Load(Read(argv[1]),error)||!original.Load(Read(argv[2]),error)) {std::cerr<<error;return 2;}
    const std::vector<std::uint8_t> data{std::istreambuf_iterator<char>(std::cin),{}};Input i(data);Output out;const auto programs=i.Word();
    for (std::uint32_t p=0;p<programs;++p)
    {
        auto rig=original;const auto variant=i.Word();if (variant==1) {for (auto& bone:rig.bones) for (auto& c:bone.name) if (c>='a'&&c<='z') c=char(c-32);}
        else if (variant==2) {for (auto& bone:rig.bones) {auto folded=bone.name;for(auto& c:folded) if(c>='A'&&c<='Z')c=char(c+32);if(folded=="righttoebase")bone.name="MissingRightToe";}}
        else if (variant==3) rig.bones[0].name="RightToeBase";
        PhysicsAnimationInput input;Actions actions;const auto mode=i.String();const bool loaded=input.Load(settings,rig,mode,error);out.Word(p);out.Word(loaded);out.String(error);const auto commands=i.Word();
        if (!loaded) {if (commands) return 2;continue;}
        Snapshot(out,input,actions);
        for (std::uint32_t c=0;c<commands;++c)
        {
            actions.calls.clear();const auto opcode=i.Word();bool ok=true;error.clear();
            if (opcode==0) {input.fields=ReadScalarAttributeInputs(i);input.extra=ReadExtendedAttributes(i);input.contacts=ReadContactEventState(i);input.output=ReadAnimationControlOutput(i);}
            else if (opcode==1) input.ResetProcessed();
            else if (opcode==2) input.FinishOutputPublication();
            else if (opcode==3) ok=input.SelectPhysicsMode(i.Word(),error);
            else if (opcode==4)
            {
                const auto count=i.Word();std::vector<AnimationAttribute> attrs;for (std::uint32_t n=0;n<count;++n) attrs.push_back(i.Attribute());const auto bones=i.Word();std::vector<Mat4> hierarchy;for (std::uint32_t n=0;n<bones;++n) hierarchy.push_back({i.Floats<4>(),i.Floats<4>(),i.Floats<4>(),i.Floats<4>()});const float dt=i.Float();const auto flags=i.Word();const bool impulse=i.Word()!=0;actions.values=i.Floats<18>();ok=input.Process(attrs,hierarchy,dt,flags,impulse,actions,error);
            }
            else return 2;
            out.Word(p);out.Word(c);out.Word(opcode);out.Word(ok);out.String(error);Snapshot(out,input,actions);
        }
    }
    if (!i.r.ok||i.r.at!=data.size()) return 2;std::cout.write(reinterpret_cast<const char*>(out.bytes.data()),std::streamsize(out.bytes.size()));
}
