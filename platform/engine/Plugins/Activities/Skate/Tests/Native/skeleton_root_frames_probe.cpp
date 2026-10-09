#include "SkeletonBoardFrames.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
using namespace atelier::skate;
namespace
{
std::vector<std::uint32_t> output;
std::uint32_t Word(){std::uint32_t w;if(std::fread(&w,4,1,stdin)!=1)std::abort();return w;}
float Float(){const auto w=Word();float f;std::memcpy(&f,&w,4);return f;}
template<std::size_t N> std::array<float,N> Floats(){std::array<float,N> r;for(auto& v:r)v=Float();return r;}
Mat4 Matrix(){Mat4 m;for(auto& c:m)c=Floats<4>();return m;}
void Out(std::uint32_t w){output.push_back(w);}
void Out(float f){std::uint32_t w;std::memcpy(&w,&f,4);Out(w);}
void Out(Vec4 v){for(const auto f:v)Out(f);}
void Out(const Mat4& m){for(const auto& c:m)Out(c);}
SkeletonRootFrames Root()
{
    SkeletonRootFrames r;r.board=Matrix();r.inverse_board=Matrix();r.previous_board_position=Floats<4>();r.predicted_board_position=Floats<4>();
    const bool supplied=Word()!=0;const auto prediction=Floats<4>();if(supplied)r.supplied_prediction=prediction;
    r.animation_to_board=Matrix();r.animation_to_world=Matrix();r.world_to_animation=Matrix();r.heading_alignment=Matrix();r.initialize_heading=Word()!=0;return r;
}
SkeletonBoardFrames Board()
{
    SkeletonBoardFrames b;b.physical_board=Matrix();b.skate_root=Matrix();b.animation_target=Matrix();b.com_frame=Matrix();b.lifted_com_frame=Matrix();
    b.centre_of_mass=Floats<4>();b.previous_centre_of_mass=Floats<4>();b.com_velocity=Floats<4>();b.local_centre_of_mass=Floats<4>();b.local_board_position=Floats<4>();b.lift_height=Float();return b;
}
void Out(const SkeletonRootFrames& r)
{
    Out(r.board);Out(r.inverse_board);Out(r.previous_board_position);Out(r.predicted_board_position);
    Out(std::uint32_t(r.supplied_prediction.has_value()));Out(r.supplied_prediction.value_or(Vec4{}));
    Out(r.animation_to_board);Out(r.animation_to_world);Out(r.world_to_animation);Out(r.heading_alignment);Out(std::uint32_t(r.initialize_heading));
}
void Out(const SkeletonBoardFrames& b)
{
    Out(b.physical_board);Out(b.skate_root);Out(b.animation_target);Out(b.com_frame);Out(b.lifted_com_frame);
    Out(b.centre_of_mass);Out(b.previous_centre_of_mass);Out(b.com_velocity);Out(b.local_centre_of_mass);Out(b.local_board_position);Out(b.lift_height);
}
}
int main()
{
    const auto cases=Word();for(std::uint32_t index=0;index<cases;++index)
    {
        SkeletonRootFrames r;SkeletonBoardFrames b;if(Word()){r=Root();b=Board();}
        const auto count=Word();Out(index);Out(count);const auto size_at=output.size();Out(0u);const auto start=output.size();Out(r);Out(b);
        for(std::uint32_t n=0;n<count;++n)
        {
            const auto op=Word();Out(op);switch(op)
            {
            case 0:{const auto board=Matrix();const auto velocity=Floats<4>();const float dt=Float();const auto animation=Matrix(),reckoning=Matrix();r.Update(board,velocity,dt,animation,reckoning);break;}
            case 1:{const auto board=Matrix(),animation=Matrix(),reckoning=Matrix();r.UpdateTeleport(board,animation,reckoning);break;}
            case 2:r.ResetInitialAlignment(Matrix());break;
            case 3:{const bool supplied=Word()!=0;const auto prediction=Floats<4>();r.supplied_prediction=supplied?std::optional<Vec4>(prediction):std::nullopt;break;}
            case 4:r.initialize_heading=Word()!=0;r.heading_alignment=Matrix();break;
            case 5:b.Reset(Matrix());break;
            case 6:b.PublishLocalObservations(r,Matrix());break;
            case 7:{const auto com=Floats<4>();const float dt=Float();const auto flags=Word();b.PublishCentreOfMass(com,dt,flags);break;}
            case 8:case 9:{const auto mapped=Matrix(),actual=Matrix();auto flags=Word();const auto target=op==8?b.PrepareGround(r,mapped,actual,flags):b.PrepareTeleport(r,mapped,actual,flags);Out(flags);Out(target);break;}
            case 10:{const auto frame=Matrix();const auto position=Floats<4>();const float height=Float();b.UpdateComLift(frame,position,height);break;}
            case 11:{const auto frame=Matrix();Out(OrthonormalizeSkeletonFrame(frame));Out(InverseSkeletonRigid(frame));break;}
            default:std::abort();
            }
            Out(r);Out(b);
        }
        output[size_at]=std::uint32_t(output.size()-start);
    }
    if(std::fgetc(stdin)!=EOF)return 3;
    if(std::fwrite(output.data(),4,output.size(),stdout)!=output.size())return 2;
}
