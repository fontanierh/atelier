// SPDX-License-Identifier: Apache-2.0
#include "BoardGroundAngle.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
float BoardGroundAngleBetween(Vec3 a,Vec3 b)
{
    const float a_squared=Dot3(a,a),b_squared=Dot3(b,b);const std::uint32_t bits=0x38d1b717;float epsilon;std::memcpy(&epsilon,&bits,4);
    if(!(a_squared>epsilon && b_squared>epsilon))return 0;
    const float ia=InverseLengthSquared(a_squared,1),ib=InverseLengthSquared(b_squared,1);
    a={a.x*ia,a.y*ia,a.z*ia};b={b.x*ib,b.y*ib,b.z*ib};
    return Acos(VectorMin(VectorMax(Dot3(a,b),-1.0f),1.0f));
}
}
