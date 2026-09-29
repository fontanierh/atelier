#!/bin/zsh
# Film the scripted fox fight (-fightfilm) at 1080p60 into build/yorimichi/fightfilm/<take>/ (frames, camera.csv, audio.json, film.json).
#   games/yorimichi/tools/film_fight.sh <take> [extra -set= preferences]; then mix_fight_film.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; BUILD="${ATELIER_BUILD_ROOT:-$ROOT/build}/yorimichi"
TAKE="${1:?take name}"; SET="${2:-}"
E="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"; P="$ROOT/games/yorimichi/unreal"
OUT="$BUILD/fightfilm/$TAKE"; rm -rf "$OUT"; mkdir -p "$OUT"
cp "$P/Saved/settings.txt" "$OUT/settings.before.txt" 2>/dev/null || true
trap 'cp "$OUT/settings.before.txt" "$P/Saved/settings.txt" 2>/dev/null || true' EXIT
PYTHONPATH="$ROOT/platform/studio" python3 -m atelier.safety.guarded --report "$OUT/guard" --timeout 1800 --purpose "Fight film $TAKE" -- \
  "$E/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$P/Yorimichi.uproject" \
  -game -RenderOffscreen -ForceRes -resx=1920 -resy=1080 -fightfilm "-reviewdir=$OUT" \
  -UseFixedTimeStep -FPS=60 -unattended -nosplash -stdout -noshaderworker \
  "-set=show_fps=0${SET:+;$SET}" "-ExecCmds=r.DynamicRes.OperationMode 0,r.ScreenPercentage 100" "-abslog=$OUT/game.log" > /dev/null 2>&1
grep -E "FIGHT FILM" "$OUT/game.log" | sed 's/^.*FIGHT FILM/FIGHT FILM/' | tail -40
