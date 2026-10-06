
import math
live.SHOT=[0]
def _closeup(dt):
    live.SHOT[0]+=1; n=live.SHOT[0]
    if n < 48: return
    if n > 70: unreal.MegaParkValidation.restore_player_camera(); live.stop('closeup'); return
    s=live.skate_state(); yaw=math.radians(float(s.split('yaw=')[1].split()[0]))
    pawn=unreal.GameplayStatics.get_player_pawn(live.L.game_world(), 0)
    at=next(c for c in pawn.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck').get_world_location()
    ahead=unreal.Vector(math.cos(yaw), math.sin(yaw), 0.0); right=unreal.Vector(-math.sin(yaw), math.cos(yaw), 0.0)
    unreal.MegaParkValidation.review_camera(at+right*150.0+ahead*30.0+unreal.Vector(0,0,-2), at+unreal.Vector(0,0,-4), 38.0)
    if n == 62: live.L.screenshot(PATH)
live.behave('closeup', _closeup)
