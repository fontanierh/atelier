// SPDX-License-Identifier: Apache-2.0
#include "SkeletonBoardOffset.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
void SkateboardOffset::RefreshTransform(Mat4 frame){transform=frame;orientation_frames=height_frames=15.0f;orientation_refreshed=height_refreshed=true;}
void SkateboardOffset::RefreshHeight(float height,float frames){transform[3][1]=height;height_frames=frames;height_refreshed=true;}
void SkateboardOffset::Update(Mat4& board,std::array<Mat4,4>& targets)
{
    bool apply=false;
    if(orientation_frames>0.0f)
    {
        apply=true;if(!orientation_refreshed)
        {
            const float ratio=(orientation_frames-1.0f)/orientation_frames,weight=ratio*ratio,identity_weight=1.0f-weight;
            for(unsigned axis=0;axis<3;++axis)for(unsigned lane=0;lane<4;++lane)transform[axis][lane]=std::fma(transform[axis][lane],weight,SkeletonIdentity[axis][lane]*identity_weight);
            for(unsigned lane:{0u,2u,3u})transform[3][lane]*=weight;const auto unnormalized=transform;
            for(int axis=2;axis>=0;--axis)
            {
                auto vector=unnormalized[axis];for(int prior=2;prior>axis;--prior){const float projection=Dot3(transform[prior],unnormalized[axis]);for(unsigned lane=0;lane<4;++lane)vector[lane]-=transform[prior][lane]*projection;}
                const float reciprocal=InverseLengthSquared(Dot3(vector,vector),2);for(unsigned lane=0;lane<4;++lane)transform[axis][lane]=vector[lane]*reciprocal;
            }
            orientation_frames-=1.0f;
        }
    }
    if(height_frames>0.0f){apply=true;if(!height_refreshed){const float ratio=(height_frames-1.0f)/height_frames;transform[3][1]*=ratio*ratio;height_frames-=1.0f;}}
    if(apply){board=ComposeSkeletonAffine(transform,board);for(auto& target:targets)target=ComposeSkeletonAffine(transform,target);}orientation_refreshed=height_refreshed=false;
}
}
