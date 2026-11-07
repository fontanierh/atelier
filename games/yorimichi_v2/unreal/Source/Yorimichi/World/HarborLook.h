#pragma once

class AJapanWorld;

// Bounded harbor treatment; does not alter saved settings or other districts.
void InitializeHarborLook(AJapanWorld* World);
void UpdateHarborLook(AJapanWorld* World);

// Keep the pond bridge's thin joinery free of screen-space GI occlusion streaks.
void InitializeGardenBridgeLook(AJapanWorld* World);

