// SPDX-License-Identifier: Apache-2.0
#include "GestureInputPublication.h"
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> input,output;std::size_t at=0;
std::uint32_t R(){if(at+4>input.size())throw std::runtime_error("truncated word");std::uint32_t value=0;for(unsigned i=0;i<4;++i)value|=std::uint32_t(input[at++])<<(8*i);return value;}
float F(){const auto bits=R();float value;std::memcpy(&value,&bits,4);return value;}
std::string S(){const auto size=R();if(at+size>input.size())throw std::runtime_error("truncated string");std::string value(reinterpret_cast<const char*>(input.data()+at),size);at+=size;return value;}
void W(std::uint32_t value){for(unsigned i=0;i<4;++i)output.push_back(std::uint8_t(value>>(8*i)));}
void Snapshot(const IntentMap& map,const std::vector<std::string>& names){W(std::uint32_t(map.Size()));for(const auto& name:names){const auto value=map.Get(name);W(value!=nullptr);if(value){std::uint32_t bits;std::memcpy(&bits,value,4);W(bits);}}}
std::vector<std::uint8_t> File(const char* name){std::ifstream file(name,std::ios::binary);if(!file)throw std::runtime_error("missing native data");return {std::istreambuf_iterator<char>(file),{}};}
}
int main(int argc,char** argv)
{
    try
    {
        if(argc<3)throw std::runtime_error("expected settings and gestures");std::string error;
        SettingsDatabase settings;if(!settings.Load(File(argv[1]),error))throw std::runtime_error(error);
        std::vector<GestureSet> bank;if(!LoadGestureData(File(argv[2]),bank,error))throw std::runtime_error(error);
        GestureInputPublication publication;if(!publication.Load(settings,bank,error))throw std::runtime_error(error);
        input.assign(std::istreambuf_iterator<char>(std::cin),{});std::vector<std::string> names;const auto count=R();for(std::uint32_t i=0;i<count;++i)names.push_back(S());
        const auto commands=R();for(std::uint32_t i=0;i<commands;++i)
        {
            const auto operation=R();W(operation);
            if(operation==0){if(!publication.Load(settings,bank,error))throw std::runtime_error(error);}
            else if(operation==1)
            {
                std::array<StickPoint,2> axes;for(auto& stick:axes)for(auto& value:stick)value=F();const auto difficulty=R(),flags=R(),state=R();
                IntentMap action;const auto size=R();for(std::uint32_t row=0;row<size;++row){const auto name=S();action.Insert(name,F());}
                if(!publication.Publish(axes,difficulty,flags,state,action,error))throw std::runtime_error(error);Snapshot(action,names);
            }
            else throw std::runtime_error("unknown operation");
        }
        if(at!=input.size())throw std::runtime_error("unconsumed input");std::cout.write(reinterpret_cast<const char*>(output.data()),std::streamsize(output.size()));return std::cout?0:2;
    }
    catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 2;}
}
