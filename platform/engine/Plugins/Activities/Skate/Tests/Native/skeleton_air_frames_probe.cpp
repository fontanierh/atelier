// SPDX-License-Identifier: Apache-2.0
// Root/board value transport is prepended by the checker.
#include "BoardAnimation.h"
#include "SkeletonAirFrames.h"
namespace
{
BoardAnimationSettings Settings()
{
    BoardAnimationSettings settings;
    for(auto* curve:{&settings.slow,&settings.fast}){curve->x=Floats<8>();curve->y=Floats<8>();}
    return settings;
}
void Snapshot(const SkeletonRootFrames& roots,const SkeletonBoardFrames& board,const BoardAnimation& animation)
{Out(roots);Out(board);Out(animation.rotation_error);Out(std::uint32_t(animation.blending));}
}
int main()
{
    const auto cases=Word();
    for(std::uint32_t c=0;c<cases;++c)
    {
        auto roots=Root();auto board=Board();auto settings=Settings();BoardAnimation animation;
        animation.rotation_error=Floats<4>();animation.blending=Word()!=0;
        const auto commands=Word();Out(c);Out(commands);const auto size_at=output.size();Out(0u);const auto start=output.size();Snapshot(roots,board,animation);
        for(std::uint32_t n=0;n<commands;++n)
        {
            const auto op=Word();Out(op);
            switch(op)
            {
            case 0:animation.Reset();break;
            case 1:{const auto target=Matrix(),deck=Matrix();animation.CapturePhysicsError(target,deck);break;}
            case 2:{const auto target=Matrix();Out(animation.Apply(target,Word()!=0,settings));break;}
            case 3:{const auto target=Floats<4>(),position=Floats<4>();Out(BoardAnimationTargetVelocity(target,position,Float()));break;}
            case 4:{const auto mapped=Matrix();auto flags=Word();Out(PrepareAnimatedAirFrames(roots,board,mapped,flags));Out(flags);break;}
            case 5:{const auto reckoning=Matrix();const auto target=Floats<4>(),local=Floats<4>();const bool requested=Word()!=0;const auto frames=Word();const bool goofy=Word()!=0;UpdateKnownAirRoots(roots,reckoning,target,local,{requested,frames,goofy});break;}
            case 6:{const auto mapped=Matrix();auto flags=Word();Out(PrepareKnownAirFrames(roots,board,mapped,flags));Out(flags);break;}
            case 7:FinishKnownAirFrames(roots,board,Matrix());break;
            case 8:{const auto reckoning=Matrix();const auto world=Floats<4>(),local=Floats<4>();UpdatePlantRoots(roots,reckoning,world,local);break;}
            case 9:animation.rotation_error=Floats<4>();animation.blending=Word()!=0;break;
            default:std::abort();
            }
            Snapshot(roots,board,animation);
        }
        output[size_at]=std::uint32_t(output.size()-start);
    }
    if(std::fgetc(stdin)!=EOF)return 3;
    return std::fwrite(output.data(),4,output.size(),stdout)==output.size()?0:2;
}
