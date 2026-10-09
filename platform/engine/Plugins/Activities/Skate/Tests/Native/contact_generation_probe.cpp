#include "ContactGeneration.h"
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
    std::uint32_t Word() {if (bytes.size()-at<4) Fail("Truncated contact generation input");std::uint32_t v=0;for (unsigned i=0;i<4;++i) v|=std::uint32_t(bytes[at++])<<(8*i);return v;}
    float Scalar() {const auto bits=Word();float v;std::memcpy(&v,&bits,4);return v;}
    Vec3 Vector() {return {Scalar(),Scalar(),Scalar()};}
    template<std::size_t N> std::array<std::uint32_t,N> Words() {std::array<std::uint32_t,N> v;for (auto& x:v) x=Word();return v;}
    ContactInput Input() {return {Vector(),Vector(),Vector(),Scalar(),Scalar(),Scalar(),Word()};}
    ContactBodyState Body()
    {
        ContactBodyState b;b.contact_body_id=Word();b.center_of_mass=Vector();b.reaction_id=Word();b.inverse_inertia_full=Vector();b.inverse_mass=Scalar();
        b.inverse_inertia_split=Vector();b.state=Word();b.force_acceleration=Vector();b.kinetic_energy=Scalar();b.torque_acceleration=Vector();b.cool_down=Word();b.linear_velocity=Vector();b.angular_velocity=Vector();return b;
    }
};
void Word(std::uint32_t v) {for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(v>>(8*i)));}
template<std::size_t N> void Words(const std::array<std::uint32_t,N>& v) {for (auto w:v) Word(w);}
void Compiled(const ContactConstraint& c) {Words(c.words);Word(static_cast<std::uint32_t>(c.reaction_a));Word(static_cast<std::uint32_t>(c.reaction_b));}
}
int main()
{
    Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto count=reader.Word();
    for (std::uint32_t index=0;index<count;++index)
    {
        const auto op=reader.Word();Word(index);Word(op);
        if (op==0 || op==1)
        {
            const auto input=reader.Input();const auto a=reader.Body(),b=reader.Body();Words(GenerateContact(input,a,b));
            if (op==1) Compiled(BuildContactJacobian(input,a,b,reader.Scalar()));
        }
        else if (op==2) {const auto record=reader.Words<64>();Compiled(BuildContactJacobian(record,reader.Scalar()));}
        else Fail("Invalid contact generation operation");
    }
    if (reader.at!=reader.bytes.size()) Fail("Trailing contact generation input");
}
