# Sword trainer

Kaede, the sword teacher of Momiji Hamlet, spars with the player on the lawn beside the tea house. Walk up to
her and press Interact (E, D-pad Down): her menu picks the level (**Gentle**, **Steady**, **Master**), her sword or her
sword and shield, and yours (the player's "Shield" setting). A bout ends when either of you is knocked down at no
health; she says a word, bows if you won, and walks back to her spot.

Both fighters play the same move set: the player's merged move set (Link's moves from Breath of the Wild with Cairo's
double jump and two-handed guard, [the botw README](../assets/characters/botw/README.md#the-merged-move-set)). Kaede is
a person in the game's own body, not a creature with its own rules: an AI holds her stick and presses her buttons, so
every move she makes is one the player can make, and the move set's guard, parry, dodges, flurry rush and hit
reactions answer both sides alike.

## Her body

Concept to rig through the Tripo workflow, with the eyes and the baked light fixed
([TRIPO_CHARACTERS.md](TRIPO_CHARACTERS.md)); source `assets/characters/sword-trainer/` (the rig revision's blend,
`source-manifest.json`, `face.json`, `texture.json`). 1.68 m, the humanoid contract's 53 bones, her own clips Bow and
Talk, and the merged move set retargeted onto her by `cairo/botw.py --character sword-trainer`: Link's 106 clips, and
Cairo's own four (his double jump, his two-handed guard stance, parry and recoil), sampled from his source
(`botw.py --dump-own`) and retargeted bone for bone, so her set is Cairo's.

```sh
atelier build yorimichi characters.sword_trainer unreal.sword_trainer characters.sword_trainer_botw unreal.sword_trainer_botw
```

`unreal.sword_trainer` (`Scripts/import_sword_trainer.py`) imports `SK_SwordTrainer`, her material and clips and
`DA_SwordTrainerBase`; `unreal.sword_trainer_botw` runs `import_cairo_botw.py` with `BOTW_CHARACTER=sword-trainer`:
her move clips into `/Game/SwordTrainer/Botw`, `DA_SwordTrainer` and her move record `Content/Data/sword-trainer/botw.json`.
Until her body is built, Cairo's merged-move-set body stands in for her (`DA_CairoBotw`), so the fights work from a
plain build.

## How she fights

`ASwordTrainer` (`Source/Yorimichi/SwordTrainer.h/.cpp`) is an `AWandererCharacter` with `IsNpc()`: no camera, menus,
phone, map or board, an `AAIController` for her view. The move set (`UBotwMoveSet`) treats a sparring partner
(`IsSparringWith`, from the stance to the end of the bout) as a target: the blade sweep and arc reach it, its lock-on
and soft lock find it, and a blow that reaches it goes through its own `IncomingStrike` (a parried blow throws the
striker back, `Deflected`). Blows take `SparringDamage`: 10 a cut, 18 a strong blow, 28 at full power (which knocks
down), times her level's share for hers.

Her brain, each frame:

- **Circling.** At about 3 m she circles, her guard raised (strafing on the lock-on) for a share of the time and lowered
  for the rest, stepping in or out to hold the distance.
- **Openings**, by chance each second (the level's aggression) once her cooldown is over: a combo (up to the level's
  cuts, the move set homing each), a charged spin (the attack held through the first cut), a dash attack (sprinting
  in), a jump attack, a double jump into a jump attack, a feint (in, then the backflip out).
- **Answers.** The player's cuts strike from their first frame, so she answers the blow she can still see coming: the
  next cut of a combo (from the cut's input point) or a blow that winds up (the spin, the dash and jump attacks).
  After her reaction time she guards it, parries it (the guard up, the parry pressed so its window is open when the
  blow can land), hops aside or backflips early, or hops just as it comes for a perfect dodge and the flurry rush
  (without slowing the world: the player keeps their own time). Or she takes it.
- **Respect.** When the player is down she steps back and waits; when the player winds up a charged spin she backs off
  (or, at Master, cuts in before it is ready).

| Level | Reaction | Parry / dodge / guard | Perfect dodge | Aggression | Combo | Open after attacking | Damage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Gentle | 0.45 s | 0 / 15 / 30% | 0 | 0.35 /s | 2 | 1.1 s | 60% |
| Steady | 0.25 s | 25 / 25 / 25% | 35% of dodges | 0.65 /s | 3 | 0.6 s | 85% |
| Master | 0.12 s | 45 / 30 / 15% | 75% of dodges | 1.05 /s | 4 | 0.3 s | 100% |

The HUD shows "Talk to Kaede" near her, and in a bout her bar, her level, the bout count and her words.

## Live and review

`YorimichiLive`: `trainer_state()` (her bout, level, intent, health, the player's, counts of her openings and answers),
`trainer_bout(level, her_shield, player_shield)`, `trainer_menu()`, `trainer_end()`, `trainer_force(attack, answer)`
(her next opening or answer), `trainer_place(ground, yaw)`. `scenarios/trainer_film.py` films the approach, her menu,
a bout at each level, each forced opening and answer, and the end of a bout; `trainer_film_cut.py` captions it.
`-notrainer` leaves her out; scripted sessions have her only with `-trainer`.
