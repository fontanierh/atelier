#include "SkeletonRoot.h"
#include "BoardGroundAngle.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float Scalar(std::uint32_t bits){float value;std::memcpy(&value,&bits,4);return value;}
float HeadingNegativeSine(float angle)
{
    // The frozen root producer inlines SinCos and stores -sin with FNMADD
    // for the final polynomial term. Negating the rounded shared SinCos
    // result instead changes this stored lane from +0 to -0 at zero heading.
    const float turns=std::nearbyint(angle*Scalar(0x3e22f983));
    const float x=std::fma(-Scalar(0x40c90fdb),turns,angle);
    const float x2=x*x,x3=x2*x,x4=x2*x2,x5=x3*x2,x6=x3*x3;
    const float x7=x4*x3,x8=x4*x4,x9=x5*x4,x10=x5*x5;
    const float x11=x6*x5,x12=x6*x6,x13=x7*x6,x15=x8*x7;
    const float x17=x9*x8,x19=x10*x9,x21=x11*x10,x23=x12*x11;
    float sine=std::fma(Scalar(0xbe2aaaab),x3,x);
    sine=std::fma(Scalar(0x3c088889),x5,sine);
    sine=std::fma(x7,Scalar(0xb9500d01),sine);
    const float powers[]={x9,x11,x13,x15,x17,x19,x21};
    const std::uint32_t coefficients[]={0x3638ef1d,0xb2d7322b,0x2f309231,0xab573f9f,0x274a963c,0xa317a4da,0x1eb8dc78};
    for(unsigned i=0;i<7;++i)sine=std::fma(Scalar(coefficients[i]),powers[i],sine);
    return std::fma(Scalar(0x1a3b0da1),x23,-sine);
}
}
Mat4 OrthonormalizeSkeletonFrame(Mat4 source)
{
    Mat4 result=source;
    for(int axis=2;axis>=0;--axis)
    {
        auto vector=source[axis];
        for(int prior=2;prior>axis;--prior)
        {
            const float projection=Dot3(result[prior],source[axis]);
            for(std::size_t lane=0;lane<4;++lane)vector[lane]-=result[prior][lane]*projection;
        }
        const float reciprocal=InverseLengthSquared(Dot3(vector,vector),2);
        for(std::size_t lane=0;lane<4;++lane)result[axis][lane]=vector[lane]*reciprocal;
    }
    return result;
}
void SkeletonRootFrames::UpdateTeleport(Mat4 physical_board,const Mat4& animation_board,const Mat4& reckoning_frame)
{
    initialize_heading=true;supplied_prediction=physical_board[3];
    Update(physical_board,Vec4{},0.0f,animation_board,reckoning_frame);
    previous_board_position=physical_board[3];
}
void SkeletonRootFrames::ResetInitialAlignment(Mat4 alignment)
{
    animation_to_world=alignment;world_to_animation=InverseSkeletonRigid(alignment);
}
void SkeletonRootFrames::Update(Mat4 physical_board,Vec4 board_velocity,float time_step,
    const Mat4& animation_board,const Mat4& reckoning_frame)
{
    previous_board_position=board[3];board=physical_board;inverse_board=InverseSkeletonRigid(physical_board);
    if(supplied_prediction){predicted_board_position=*supplied_prediction;supplied_prediction.reset();}
    else for(std::size_t i=0;i<4;++i)predicted_board_position[i]=std::fma(board_velocity[i],time_step,physical_board[3][i]);
    if(initialize_heading)
    {
        const Vec3 at{animation_board[2][0],0.0f,animation_board[2][2]};
        float angle=BoardGroundAngleBetween(at,Vec3{0.0f,0.0f,1.0f});
        const Vec4 at4{at.x,at.y,at.z,0.0f};const float squared=Dot3(at4,at4);
        if(squared>Scalar(0x38d1b717))
        {
            const float inverse=InverseLengthSquared(squared,1),x=at.x*inverse;
            if(0.0f>-x)angle=Scalar(0x40c90fdb)-angle;
        }
        const auto [sin,cos]=SinCos(angle);
        heading_alignment={{{cos,0.0f,HeadingNegativeSine(angle),0.0f},{0.0f,1.0f,0.0f,0.0f},
            {sin,0.0f,cos,0.0f},{0.0f,0.0f,0.0f,0.0f}}};
        initialize_heading=false;
    }
    auto remove_board_translation=SkeletonIdentity;
    for(std::size_t i=0;i<4;++i)remove_board_translation[3][i]=-animation_board[3][i];
    auto local=ComposeSkeletonAffine(heading_alignment,remove_board_translation);
    // The original root update inlines removal of the authored board offset.
    // Its translation uses negative parent operands in the fused chain. Keep
    // that operand order here too: negating the child in a separate affine
    // call changes the sign of propagated NaNs after a degenerate air frame.
    for(std::size_t lane=0;lane<4;++lane)
    {
        const float x=std::fma(-heading_alignment[0][lane],animation_board[3][0],heading_alignment[3][lane]);
        const float y=std::fma(-heading_alignment[1][lane],animation_board[3][1],x);
        local[3][lane]=std::fma(-heading_alignment[2][lane],animation_board[3][2],y);
    }
    animation_to_board=ComposeSkeletonAffine(reckoning_frame,local);
    auto world_translation=SkeletonIdentity;world_translation[3]=predicted_board_position;
    auto world=ComposeSkeletonAffine(world_translation,animation_to_board);
    // The original inlined identity placement replaces each unit-axis FMA
    // with a child-first add while retaining the zero-axis FMAs. This order
    // also matters when both the prediction and local translation are NaNs.
    const auto& t=animation_to_board[3];
    world[3][0]=std::fma(0.0f,t[2],std::fma(0.0f,t[1],t[0]+predicted_board_position[0]));
    world[3][1]=std::fma(0.0f,t[2],t[1]+std::fma(t[0],0.0f,predicted_board_position[1]));
    world[3][2]=t[2]+std::fma(0.0f,t[1],std::fma(t[0],0.0f,predicted_board_position[2]));
    world[3][3]=std::fma(0.0f,t[2],std::fma(0.0f,t[1],std::fma(t[0],0.0f,predicted_board_position[3])));
    animation_to_world=OrthonormalizeSkeletonFrame(world);
    world_to_animation=InverseSkeletonRigid(animation_to_world);
    // The source inlines the inverse translation as a basis-first vector
    // chain, Z then Y then X. Preserve both its order and NaN operands.
    for(std::size_t lane=0;lane<4;++lane)
    {
        const float z=world_to_animation[2][lane]*(0.0f-animation_to_world[3][2]);
        const float y=std::fma(world_to_animation[1][lane],0.0f-animation_to_world[3][1],z);
        world_to_animation[3][lane]=std::fma(world_to_animation[0][lane],0.0f-animation_to_world[3][0],y);
    }
}
}
