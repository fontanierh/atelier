// SPDX-License-Identifier: Apache-2.0
#include "TruckDriveFrames.h"
#include "DrivePreparation.h"
#include "HookDrive.h"
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <iterator>
#include <vector>
using namespace atelier::skate;
namespace
{
[[noreturn]] void Fail(const char* message) {std::cerr<<message<<'\n';std::exit(2);}
struct Reader
{
    std::vector<std::uint8_t> bytes;std::size_t at=0;
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated drive lifecycle input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar() {const auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> v;for (auto& x:v) x=Word();return v;}
    AffineTransform Transform() {AffineTransform v;for (auto& c:v.basis.columns) for (auto& x:c) x=Scalar();v.translation={Scalar(),Scalar(),Scalar()};return v;}
};
struct Writer
{
    std::vector<std::uint32_t> words;
    void Word(std::uint32_t v) {words.push_back(v);}
    void Scalar(float v) {std::uint32_t bits;std::memcpy(&bits,&v,4);Word(bits);}
    template<std::size_t N> void Words(const std::array<std::uint32_t,N>& v) {words.insert(words.end(),v.begin(),v.end());}
    void Transform(AffineTransform v) {for (auto c:v.basis.columns) for (auto x:c) Scalar(x);Scalar(v.translation.x);Scalar(v.translation.y);Scalar(v.translation.z);}
    void State(const HookDriveState& state,std::uint8_t animated)
    {
        Words(state.frames);Words(state.dynamics);Word(animated);const auto d=state.SolverDynamics();
        for (const auto p:{d.linear,d.angular}) {Scalar(p.spring_or_max_velocity);Scalar(p.damping);Scalar(p.max_strength);Word(static_cast<std::uint32_t>(p.type));}
    }
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(v>>(8*i)));}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();Writer out;
        if (op==0)
        {
            const std::array<AffineTransform,2> base={reader.Transform(),reader.Transform()};const std::array<float,2> targets={reader.Scalar(),reader.Scalar()};
            for (const auto t:SteeringTruckTransforms(base,targets)) out.Transform(t);
            for (const auto f:SteeringDriveFrames(base,targets)) {const auto raw=PackDriveFrames(f);out.Words(raw.body_a.quaternion_lanes);out.Words(raw.body_a.translation_lanes);out.Words(raw.body_b.quaternion_lanes);out.Words(raw.body_b.translation_lanes);}
        }
        else if (op==1) {auto frames=reader.Words<16>();NormalizeDriveFrames(frames);out.Words(frames);}
        else if (op==2)
        {
            const auto n=reader.Word();std::vector<std::array<std::uint32_t,16>> frames;for (std::uint32_t i=0;i<n;++i) frames.push_back(reader.Words<16>());
            const auto k=reader.Word();std::vector<std::optional<std::size_t>> active;
            for (std::uint32_t i=0;i<k;++i) {const auto id=reader.Word();active.push_back(id==0xffffffff ? std::nullopt:std::optional<std::size_t>{id});}
            NormalizeActiveDriveFrames(frames,active);for (const auto& row:frames) out.Words(row);
        }
        else if (op==3)
        {
            auto frames=reader.Words<16>();const auto basis=reader.Words<12>();if (reader.Word()) SetParentAngularFrame(frames,basis);else SetChildAngularFrame(frames,basis);out.Words(frames);
        }
        else if (op==4)
        {
            HookDriveState state;state.frames=reader.Words<16>();state.dynamics=reader.Words<8>();auto animated=static_cast<std::uint8_t>(reader.Word());const auto n=reader.Word();out.Word(n);out.State(state,animated);
            for (std::uint32_t i=0;i<n;++i)
            {
                switch (reader.Word())
                {
                case 0:state=HookDriveState::Initial();break;case 1:state.EnableAnimationSoft(animated);break;case 2:state.EnableAngularSoft();break;case 3:state.EnableAngularOnly(animated);break;case 4:state.DisableAnimation(animated);break;case 5:state.DisableLinear();break;case 6:state.DisableAngular();break;
                case 7:SetChildAngularFrame(state.frames,reader.Words<12>());break;case 8:SetParentAngularFrame(state.frames,reader.Words<12>());break;case 9:NormalizeDriveFrames(state.frames);break;
                default:Fail("Invalid hook command");
                }
                out.State(state,animated);
            }
        }
        else Fail("Invalid drive lifecycle operation");
        Word(index);Word(op);Word(static_cast<std::uint32_t>(out.words.size()));for (auto v:out.words) Word(v);
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing drive lifecycle input");
}
