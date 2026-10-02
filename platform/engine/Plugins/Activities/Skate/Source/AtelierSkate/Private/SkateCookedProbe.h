// SPDX-License-Identifier: Apache-2.0
#pragma once

// Opt-in, runtime-module-only probe. The module owns registration lifetime.
// -SkateCookedProbe=<report.json> runs after engine initialization, before play,
// and exits with a nonzero status if any cooked-asset/session check fails.
void RegisterSkateCookedProbe();
void UnregisterSkateCookedProbe();
