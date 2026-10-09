#include "GraphGestureOperations.h"
#include <cstring>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> input,output;std::size_t at=0;
std::uint32_t R(){if(at+4>input.size())throw std::runtime_error("truncated word");std::uint32_t value=0;for(unsigned i=0;i<4;++i)value|=std::uint32_t(input[at++])<<(8*i);return value;}
std::string S(){const auto size=R();if(at+size>input.size())throw std::runtime_error("truncated string");std::string value(reinterpret_cast<const char*>(input.data()+at),size);at+=size;return value;}
void W(std::uint32_t value){for(unsigned i=0;i<4;++i)output.push_back(std::uint8_t(value>>(8*i)));}
void Text(std::string_view value){W(std::uint32_t(value.size()));output.insert(output.end(),value.begin(),value.end());}
void Optional(std::optional<std::string_view> value){W(bool(value));if(value)Text(*value);}
void Map(IntentMap& map){const auto size=R();for(std::uint32_t i=0;i<size;++i){const auto name=S();const auto bits=R();float value;std::memcpy(&value,&bits,4);map.Insert(name,value);}}
void Snapshot(const IntentMap& map,const std::vector<std::string>& names){W(std::uint32_t(map.Size()));for(const auto& name:names){const auto value=map.Get(name);W(value!=nullptr);if(value){std::uint32_t bits;std::memcpy(&bits,value,4);W(bits);}}}
}
int main()
{
    try
    {
        input.assign(std::istreambuf_iterator<char>(std::cin),{});const auto commands=R();
        for(std::uint32_t i=0;i<commands;++i)
        {
            const auto op=R();W(op);
            if(op==0){GestureGroup group;std::string error;const auto ok=ParseGestureGroup(S(),group,error);W(ok);if(ok)W(std::uint32_t(group));Text(error);}
            else if(op==1){const auto rows=GestureMappingRows(static_cast<GestureGroup>(R()));W(std::uint32_t(rows.size));for(std::size_t row=0;row<rows.size;++row){const auto& v=rows.data[row];Text(v.key);Text(v.normal);Text(v.mirrored);W(v.dark_catch);}}
            else if(op==2){const auto group=static_cast<GestureGroup>(R());const auto mirrored=R()!=0;IntentMap action;Map(action);W(HasGestureIntent(group,action));Optional(SelectGestureTrick(group,action,mirrored));}
            else if(op==3)
            {
                GestureTrickState state;IntentMap motion;Map(motion);const auto count=R();std::vector<std::string> names;for(std::uint32_t n=0;n<count;++n)names.push_back(S());
                const auto steps=R();for(std::uint32_t step=0;step<steps;++step)
                {
                    const auto phase=R();const auto mutations=R();for(std::uint32_t m=0;m<mutations;++m){const auto insert=R()!=0;const auto name=S();if(insert){const auto bits=R();float value;std::memcpy(&value,&bits,4);motion.Insert(name,value);}else motion.Remove(name);}
                    if(phase==0){const auto group=static_cast<GestureGroup>(R());const auto mirrored=R()!=0;std::optional<std::string> override_name;if(R())override_name=S();IntentMap action;Map(action);state.Begin(group,override_name?std::optional<std::string_view>(*override_name):std::nullopt,action,motion,mirrored);}
                    else if(phase==1)state.Update(motion);else if(phase==2)state.End(motion);else state={};Snapshot(motion,names);
                }
            }
            else throw std::runtime_error("unknown operation");
        }
        if(at!=input.size())throw std::runtime_error("unconsumed input");std::cout.write(reinterpret_cast<const char*>(output.data()),std::streamsize(output.size()));return std::cout?0:2;
    }
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
