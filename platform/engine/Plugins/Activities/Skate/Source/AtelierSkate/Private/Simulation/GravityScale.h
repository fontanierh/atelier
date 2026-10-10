#pragma once
namespace atelier::skate
{
// The player's gravity scale (FeelTuning::gravity). The stock code writes gravity in a dozen places as a literal
// -9.8 (or 19.6, or 1/9.8) beside the settings' WorldGravity; each of them multiplies (or divides) by this, so the
// rider, the board, the jump and every predicted arc keep agreeing with one another. GameplayRuntime::Advance sets it
// for its own thread before each tick, so sessions on different threads keep their own. At 1 every product is exact.
inline thread_local float gravity_scale=1.0f;
inline float GravityScale() {return gravity_scale;}
}
