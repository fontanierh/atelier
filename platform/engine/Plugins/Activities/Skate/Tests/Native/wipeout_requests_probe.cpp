#include "WipeoutRequests.h"
#include "DataReader.h"
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace
{
void Word(std::uint32_t w) {for (unsigned i=0;i<4;++i) std::cout.put(char(w>>(i*8)));}
void Float(float f) {std::uint32_t w;std::memcpy(&w,&f,4);Word(w);}
void Snapshot(const WipeoutRequests& s)
{
    for (bool v:s.reasons) Word(v);
    for (float v:s.values) Float(v);
    Word(s.count);Float(s.cooldown);Word(std::uint32_t(s.contact_frames));Float(s.balance);Word(s.mode);
}
}
int main()
{
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};
    detail::DataReader i{bytes};i.at=0;const auto count=i.Word();Word(count);
    for (std::uint32_t n=0;n<count;++n)
    {
        WipeoutRequests s;Snapshot(s);const auto commands=i.Word();Word(commands);
        for (std::uint32_t k=0;k<commands;++k)
        {
            const auto op=i.Word();Word(op);
            switch (op)
            {
            case 0:
                for (auto& v:s.reasons) v=i.Word()!=0;
                for (auto& v:s.values) v=i.Float();
                s.count=i.Word();s.cooldown=i.Float();
                {const auto word=i.Word();std::memcpy(&s.contact_frames,&word,4);}
                s.balance=i.Float();s.mode=i.Word();break;
            case 1:s.InitializePlayer();break;
            case 2:s.Teleport();break;
            case 3:s.EnterGround();break;
            case 4:{const auto index=i.Word();const auto value=i.Float();s.Request(index,value);break;}
            case 5:s.ClearAfterSelection();break;
            case 6:s.ResetSystems();break;
            case 7:
            {
                WipeoutRequestInput f;f.flags_2468=i.Word();f.flags_2476=i.Word();f.flags_2480=i.Word();f.flags_2484=i.Word();
                f.animation_up_y=i.Float();f.category=i.Word();Word(s.RequestsRunout(f));Word(s.RequestsWipeout(f));break;
            }
            default:return 2;
            }
            Snapshot(s);
        }
    }
    return !i.ok||i.Remaining()!=0?2:std::cout?0:2;
}
