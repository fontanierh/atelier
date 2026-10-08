#!/bin/sh
# Builds the board world into build/board-world/dist, where `atelier board serve` serves it at /world.
# The compile is heavy (a few hundred crates), so run it through the render guard as a compile:
#   uv run python -m atelier.safety.guarded --report build/board-world/guard --kind compile \
#       --purpose 'board world wasm' -- nice -n 10 platform/web/board-world/build.sh
set -eu
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
export CARGO_TARGET_DIR="$repo/build/board-world/target"
dist="$repo/build/board-world/dist"
PATH="$HOME/.cargo/bin:$PATH"
cargo +stable build --manifest-path "$here/Cargo.toml" --release --target wasm32-unknown-unknown --locked -j "${JOBS:-3}"
mkdir -p "$dist"
wasm-bindgen --target web --no-typescript --out-dir "$dist" --out-name board_world \
    "$CARGO_TARGET_DIR/wasm32-unknown-unknown/release/board_world.wasm"
if command -v wasm-opt >/dev/null; then
    wasm-opt -Oz --enable-bulk-memory --enable-nontrapping-float-to-int --enable-sign-ext --enable-mutable-globals \
        "$dist/board_world_bg.wasm" -o "$dist/board_world_bg.wasm"
fi
ls -l "$dist"
