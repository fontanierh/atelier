#pragma once
#include "BoardAssembly.h"

namespace atelier::skate
{
// Grounded-state numerical corrections. Their phase/contact gates belong to
// the state owner; these functions write the same shared deck body as the solve.
float GroundCentreOfMassHeight(Vec4 com_to_deck_world);
float GroundCollisionForceProjection(Vec4 force, Vec4 velocity);
Vec4 GroundEdgeDirection(Vec4 start, Vec4 end);
Vec4 GroundEdgeUp(Vec4 direction);
Vec4 GroundHangForce(Vec4 start, Vec4 end, Vec4 deck);
Vec4 GroundWheelCatchDisplacement(Vec4 deck_y, Vec4 deck_z);
Vec4 GroundPinningVelocity(Vec4 position, float captured_x, float captured_z, float dt);
Vec4 GroundScaleToMagnitude(Vec4 vector, float squared, float magnitude);
void GroundApplyWorldForce(BodySnapshot& body, Vec3 deck_part_position, Vec3 force, Vec3 point);
}
