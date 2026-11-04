# pacing

The desktop game's frame pacer, at the Frame rate setting's 60 (a lower cap is kept by the settings crate, and
Unlimited draws as fast as it can). Each frame starts on a fixed deadline, 62 a second, so every frame lands on the same
display refresh; on the Mac each frame also stays on screen at least a 60th of a second (through the vendored Metal
backend, vendor/wgpu-hal), so a 120 Hz display shows a steady 60 frames timed by the window server, not by a timer on
the CPU. The main thread runs at the interactive scheduling class, which macOS wakes on time. In the browser, which paces its own frames, the plugin does nothing.

Once a second it logs how far apart the frames really were, counted under 12 ms, about one 60 Hz frame, 20–29, 29–40
and over 40 ms, with the worst and the camera's place; each frame over 17.5 ms is also logged as a `SLOW` line saying
how long the pacer slept, how long the main thread waited for the render thread, and how long it worked.

- `lib.rs` holds the pacer and the frame log.
