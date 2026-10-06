#!/bin/zsh
# Film a horse race (-racefilm) at 1080p60 into build/yorimichi/racefilm/<take>/ (frames, camera.csv, audio.json, film.json).
#   games/yorimichi/tools/film_race.sh <take> [cup 0|1|2] [horse] [autoplay accuracy] [extra -set= preferences]; then mix_race_film.py
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"; BUILD="${ATELIER_BUILD_ROOT:-$ROOT/build}/yorimichi"
TAKE="${1:?take name}"; CUP="${2:-1}"; HORSE="${3:-HorseRoan}"; AUTO="${4:-0.93}"; SET="${5:-}"
E="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"; P="$ROOT/games/yorimichi/unreal"
OUT="$BUILD/racefilm/$TAKE"; rm -rf "$OUT"; mkdir -p "$OUT"
cp "$P/Saved/settings.txt" "$OUT/settings.before.txt" 2>/dev/null || true
cp "$P/Saved/hippodrome.json" "$OUT/hippodrome.before.json" 2>/dev/null || true
cleanup() {
  # Put back the player's preferences and race records, and end the Turnkey check the game leaves orphaned (ours only).
  cp "$OUT/settings.before.txt" "$P/Saved/settings.txt" 2>/dev/null || true
  if [[ -f "$OUT/hippodrome.before.json" ]]; then cp "$OUT/hippodrome.before.json" "$P/Saved/hippodrome.json"; else rm -f "$P/Saved/hippodrome.json"; fi
  ps -axo pid=,ppid=,command= | awk -v project="$P/Yorimichi.uproject" '$2 == 1 && /Turnkey/ && index($0, project) { print $1 }' | xargs -n1 kill 2>/dev/null || true
}
trap cleanup EXIT
PYTHONPATH="$ROOT/platform/studio" python3 -m atelier.safety.guarded --report "$OUT/guard" --timeout 1800 --purpose "Race film $TAKE" -- \
  "$E/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" "$P/Yorimichi.uproject" \
  -game -RenderOffscreen -ForceRes -resx=1920 -resy=1080 -racefilm "-racecup=$CUP" "-racehorse=$HORSE" "-raceauto=$AUTO" "-reviewdir=$OUT" \
  -UseFixedTimeStep -FPS=60 -unattended -nosplash -stdout -noshaderworker \
  "-set=show_fps=0${SET:+;$SET}" "-ExecCmds=r.DynamicRes.OperationMode 0,r.ScreenPercentage 100" "-abslog=$OUT/game.log" > /dev/null 2>&1
grep -E "RACE|Hippodrome" "$OUT/game.log" | sed 's/^.*\(RACE\|Hippodrome\)/\1/' | tail -40
