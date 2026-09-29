# Connected-controller HUD

> Moved from the prototype repository on 29 September 2026. Paths are translated to this repository where the file moved; paths still starting with `japan/` or `output/imagegen/` refer to the prototype archive (authoring tools, earlier revisions, review images). See [docs/MIGRATION.md](../../../docs/MIGRATION.md).

The HUD selects controller hints while a gamepad is attached and returns to keyboard hints after disconnect. It checks the platform connection state every 0.25 seconds; it does not require a button press or switch back when the mouse moves. This includes controllers attached before startup.

`FSlateApplication::IsGamepadAttached` supplies the connection state. UE 5.8's connected-device registry supplies the controller name when available. Recognized Xbox, PlayStation and Nintendo devices get their own lettering; unknown devices use physical positions (“Bottom button”, “Right button”, etc.) instead of guessing. On macOS, Unreal registers PS4/PS5/Xbox names when connecting through Apple's GameController backend. Its PlayStation SpecialLeft binding is the touchpad click.

| Action | Xbox | PlayStation | Nintendo / Switch |
|---|---|---|---|
| Move | Left stick | Left stick | Left stick |
| Look | Right stick | Right stick | Right stick |
| Sprint | Hold left stick click | Hold L3 | Hold left stick click |
| Jump / double jump | A | Cross | B |
| Dash | X | Square | Y |
| Roll | B | Circle | A |
| Crouch | Right stick click | R3 | Right stick click |
| Interact / board zeppelin | Y | Triangle | X |
| Map | View | Touchpad | Minus |
| Settings | Menu | Options | Plus |
| Equip sailboat / step ashore | D-pad Up | D-pad Up | D-pad Up |
| Flight speed | LB / RB | L1 / R1 | L / R |

Menu / Options and D-pad Up now invoke the existing settings and sailboat actions. D-pad Down is also mapped to the legacy skateboard toggle; Warm Original still rejects that action because its definition does not support skating. Nothing re-enables skateboarding on the new character. Stick-click sprint remains hold-to-sprint, matching the existing action binding.

Vehicle hints describe steering, sail control and stepping off instead of on-foot actions. Ladder and zeppelin prompts use the active interaction button. Controller mode suppresses the mouse-release tip, while retaining stamina rings and FPS. The two hint rows measure their text and fit the viewport rather than relying on a fixed-width background.

For visual QA only, `japan.ControllerHUD` supports `-1` automatic (default), `0` keyboard, `1` Xbox, `2` PlayStation, `3` Nintendo, `4` generic. This changes labels only and does not fake input or controller connection. Restore `-1` after QA. It is not a saved preference. State changes log `CONTROLS HUD style=... automatic=...`.

## Validation

Native Development Editor build passes. The real connected DualSense registers as `PS5 Wireless Controller` at startup, followed by `CONTROLS HUD style=2 automatic=1` before any gamepad input is required. The full 2228×1440 `ready.png` confirms both PlayStation hint rows, stamina rings and FPS; live desktop inspection shows 60 FPS. Evidence: `build/yorimichi/desktop-preview/20260914-095903/`. The six desktop-launcher tests pass. No forced HUD style is left enabled. Other physical controller families and unplug/replug were not manually exercised in this session; their labels/detection follow the same platform connection/registry path.

## September 14: camera direction and physical buttons

The user reported inverted right-stick look and unresponsive buttons. `FSceneViewport::OnAnalogValueChanged` in UE 5.8 negates `Gamepad_RightY` before forwarding it to player input. This project disables legacy input scales, so `StickLook` must apply `-Delta.Y` to camera pitch. Right-stick up now looks up; horizontal look and mouse look retain their existing signs.

The button mappings were already present. After rebuilding and restarting the desktop game, real DualSense Cross and Circle press/release events reached Slate, the game viewport and the Jump/Dodge action bindings. Circle entered the roll state. Keyboard Escape also opened and closed settings. The user then confirmed “it works.” The original button failure did not reproduce after restart; its underlying cause was not established, and no replacement button-routing workaround was added.

For a recurrence, append `-controllertrace` to the Unreal launch arguments. It logs `CONTROLLER TRACE` at Slate key-down (editor builds), viewport press/release, and Boolean action start/completion, including ready/menu/movement-lock state. Raw key logging is restricted to gamepad keys and Escape. Tracing observes events without consuming or injecting them; it is off in normal launches. Check the entire path rather than inferring working controls from controller HUD detection. Actions can correctly reject a press during another locked action, such as a jump pressed before a roll finishes.

Validation: native Development Editor build succeeded; `build/yorimichi/desktop-preview/20260914-103540/game.log` contains the physical input trace and `ready.json` verifies fullscreen 2228×1440 with the forward renderer. The corrected playtest was left running. The existing 60 FPS cap, native render scale, faster sprint and keyboard mappings are unchanged.
