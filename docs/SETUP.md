# Setting up a Mac

The [requirements](../README.md#requirements) are in the top-level README. This page covers Xcode and Metal, and the
extra preparation a Mac reached over SSH needs.

## Xcode and Metal

Unreal needs full Xcode, not the command-line tools alone. After installing it, select it, accept its licence and
install Metal:

```sh
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -license accept
sudo xcodebuild -runFirstLaunch
xcodebuild -downloadComponent MetalToolchain
uv run atelier setup                  # compiles and links a small Metal shader to check the installation
```

## A Mac accessed over SSH

For a Mac accessed over SSH, run `uv run atelier setup --headless` before compiling. On the tested installed
UE **5.8.2 CL 56702186**, this repairs the build tool's protected Documents lookup, uses explicit default build
configuration, and caps C++ and shader compiles at three workers (C++ at priority 10). It rebuilds the managed .NET
build tool and shared library under the render lock and memory guard. Originals and logs are retained in
`~/.cache/atelier/toolchain/`; other engine versions are refused without modification. Repeating it is safe. Use
`--workers N` to set another cap.

This mode bypasses user and project `BuildConfiguration.xml`; pass desired build settings on the command line.
It also needs Rosetta for the managed tool's Intel protobuf compiler; setup checks this before modifying the engine.
Install it with `softwareupdate --install-rosetta --agree-to-license` if missing.

AutomationTool (UAT, used by packaging) loads its own copies of the build tool's DLLs and reads the XML config
in-process. On .NET 10, `SpecialFolder.Personal` is `~/Documents`, and looking it up waits on the macOS privacy prompt,
so a headless UAT would hang at startup. The repair therefore also patches that lookup to use `UE_HEADLESS_USER_DIR`,
and replaces UAT's shipped copies with the rebuilt ones (originals kept, restored on failure). `unreal.package`
exports the variable for UAT and the build tool it starts.
