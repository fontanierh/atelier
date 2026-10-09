#include "SkeletonTargets.h"
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Float(std::uint32_t w){float f;std::memcpy(&f,&w,4);return f;}
PoseMatrix Words(Mat4 frame){PoseMatrix out;for(std::size_t i=0;i<16;++i)std::memcpy(&out[i],&frame[i/4][i%4],4);return out;}
Mat4 Floats(PoseMatrix frame){Mat4 out;for(std::size_t i=0;i<16;++i)out[i/4][i%4]=Float(frame[i]);return out;}
Mat4 Orthonormalize(Mat4 frame){return Floats(OrthonormalizeRotation(Words(frame)));}
DriveParams Hard(float velocity,float strength){return {velocity,0,strength,DriveType::Hard};}
Vec3 ClampLength(Vec3 value,float maximum)
{
    const float magnitude=Length3(value);if(magnitude<Float(0x37800000))return value;
    const float bounded=maximum-magnitude>=0.0f ? magnitude:maximum;
    const float inverse=RefinedReciprocal(magnitude,2);
    return {(value.x*bounded)*inverse,(value.y*bounded)*inverse,(value.z*bounded)*inverse};
}
}
SkeletonTargets::SkeletonTargets(SimulationStep simulation)
{
    for(auto& body:bodies)
    {
        PartPose part{Words(SkeletonIdentity),Words(SkeletonIdentity),std::array<std::uint32_t,44>{},std::nullopt};
        SetPartTransform(part,Words(SkeletonIdentity));body=InitializeBody(part,{},simulation,BoardMotion::Static);
    }
    Basis3 basis;basis.columns={{{0,1,0},{0,0,1},{1,0,0}}};const DriveFrame extra{QuaternionFromBasis(basis),{}};
    for(std::size_t i=0;i<frames.size();++i)frames[i]={i>=2 ? extra:DriveFrame{},DriveFrame{}};
    const auto strong=Hard(Float(0x4415ffff),Float(0x470c9fff));const auto root=Hard(Float(0x426fffff),Float(0x470c9fff));
    dynamics={{{strong,strong},{root,root},{Hard(0,0),strong},{Hard(0,0),strong}}};
}
void SkeletonTargets::Reset(Mat4 hips,Mat4 spawn){SetTransform(0,Orthonormalize(hips));SetTransform(1,Orthonormalize(spawn));}
void SkeletonTargets::SetTransform(std::size_t index,Mat4 frame)
{
    if(index>=bodies.size())std::abort();auto& r=bodies[index].rates;
    PartPose part{Words(frame),Words(SkeletonIdentity),std::array<std::uint32_t,44>{},std::nullopt};
    SetPartTransform(part,Words(frame));const auto& w=*part.body;
    for(std::size_t i=0;i<4;++i)r.orientation[i]=Float(w[i]);r.position={Float(w[4]),Float(w[5]),Float(w[6])};
    for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)r.basis.columns[i][j]=Float(w[16+i*4+j]);
}
Mat4 SkeletonTargets::Transform(std::size_t index) const
{
    if(index>=bodies.size())std::abort();const auto& r=bodies[index].rates;auto frame=SkeletonIdentity;
    for(std::size_t i=0;i<3;++i)for(std::size_t j=0;j<3;++j)frame[i][j]=r.basis.columns[i][j];
    frame[3]={r.position.x,r.position.y,r.position.z,0};return frame;
}
void SkeletonTargets::ApplyFutureDeckDisplacement(Vec3 displacement)
{
    auto frame=Transform(0);frame[3][0]+=displacement.x;frame[3][1]+=displacement.y;frame[3][2]+=displacement.z;SetTransform(0,frame);
}
Mat4 SkeletonTargets::UpdateHookPositions(const SkeletonTargetInput& input)
{
    const auto hips=ComposeSkeletonAffine(input.animation_to_world,input.animation_hips);
    const auto board=ComposeSkeletonAffine(input.animation_to_world,input.animation_board);
    const auto animation_board_to_physics=ComposeSkeletonAffine(input.inverse_board,board);
    SetTransform(0,Orthonormalize(hips));SetTransform(1,Orthonormalize(input.skate_root));return animation_board_to_physics;
}
ExtraTargetPositions SkeletonTargets::UpdateExtraTargets(SkeletonBody& skeleton,const Mat4& com_frame,const Mat4& lifted_com_frame)
{
    SetTransform(2,lifted_com_frame);SetTransform(3,com_frame);
    const ExtraTargetPositions positions{com_frame[3],lifted_com_frame[3],com_frame[3]};
    const auto parts=skeleton.PartTransforms();
    for(std::size_t part=24;part<26;++part)
    {
        const auto target=part==24 ? lifted_com_frame[3]:com_frame[3];const auto current=parts[part][3];
        const Vec3 velocity{(target[0]-current[0])*60.0f,(target[1]-current[1])*60.0f,(target[2]-current[2])*60.0f};
        skeleton.BodiesMut()[part].rates.linear_velocity=ClampLength(velocity,40.0f);
    }
    return positions;
}
SkeletonTargetUpdate SkeletonTargets::UpdatePositions(SkeletonTargetInput input,SkeletonBody& skeleton)
{
    const auto previous=Transform(0)[3];const auto mapped=UpdateHookPositions(input);const auto hips=Transform(0)[3];Vec4 change;
    for(std::size_t i=0;i<4;++i)change[i]=previous[i]-hips[i];const auto positions=UpdateExtraTargets(skeleton,input.com_frame,input.lifted_com_frame);
    return {mapped,positions,!input.teleporting && !(Dot3(change,change)>1.0f)};
}
}
