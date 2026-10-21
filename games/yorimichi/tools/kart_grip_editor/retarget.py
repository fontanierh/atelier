"""Seed another character from an authored grip, preserving its own anatomical bind frames."""
import numpy as np

from grip_data import bone_names, mirror_left, pack, unpack, wheel_frame


def anatomical_frames(bind):
    """Axes from joint positions distinguish an imported bone roll from a rig's resting curl."""
    knuckles = [bind[f'finger_{i}_L'][:3, 3] for i in range(4)]
    span = knuckles[3]-knuckles[0]
    frames = {}
    names = bone_names('L')
    for i, name in enumerate(names):
        if name == 'hand_L':
            forward = np.mean(knuckles, axis=0)-bind[name][:3, 3]
        elif (i-1) % 3 != 2:
            forward = bind[names[i+1]][:3, 3]-bind[name][:3, 3]
        else:
            forward = bind[name][:3, 1]
        forward = forward/np.linalg.norm(forward)
        across = span-forward*np.dot(span, forward)
        across = across/np.linalg.norm(across)
        basis = np.column_stack((forward, across, np.cross(forward, across)))
        frames[name] = bind[name][:3, :3].T @ basis
    return frames


def fitted_arm(source, source_meta, target_meta, left, fit):
    """Match Cairo's elbow flexion with a telescopic-column fit instead of stretching shorter arms."""
    required = ('upperarm_L', 'forearm_L', 'hand_L')
    if not all(n in source_meta['bind_world'] and n in target_meta['bind_world'] for n in required):
        return list(source.get('arm_poles', {'L': target_meta['layout'].get('elbow', [-.1, .33, .57])})['L'])
    def arm(meta):
        bind = {n: unpack(meta['bind_world'][n])[:3, 3] for n in required}
        a, b = np.linalg.norm(bind[required[0]]-bind[required[1]]), np.linalg.norm(bind[required[1]]-bind[required[2]])
        pivot = unpack(meta['seated_world']['pelvis'])[:3, 3]
        point = unpack(meta['seated_world']['upperarm_L'])[:3, 3]
        angle = np.radians(fit['shoulder_lean_degrees']); c, s = np.cos(angle), np.sin(angle)
        shoulder = pivot+np.array([[c,0,s],[0,1,0],[-s,0,c]]) @ (point-pivot)
        return shoulder, a, b
    source_s, source_a, source_b = arm(source_meta)
    source_wrist = (wheel_frame(dict(source_meta, **fit)) @ unpack(source['hands']['L']['hand_L']))[:3, 3]
    delta = source_wrist-source_s; distance = np.linalg.norm(delta); direction = delta/distance
    d = min(distance, source_a+source_b-1e-5)
    along = (source_a**2-source_b**2+d*d)/(2*d)
    pole = np.array(source['arm_poles']['L'])*source_meta['scale']-source_s
    side = pole-direction*np.dot(pole,direction); side /= np.linalg.norm(side)
    source_elbow = source_s+direction*along+side*np.sqrt(max(0,source_a**2-along**2))
    cosine = np.clip((source_a**2+source_b**2-distance**2)/(2*source_a*source_b), -1, 1)
    target_s, a, b = arm(target_meta)
    desired = np.sqrt(a*a+b*b-2*a*b*cosine)
    target_wrist = (wheel_frame(dict(target_meta, **fit)) @ unpack(left['hand_L']))[:3, 3]
    tilt = np.radians(target_meta['layout']['steering_tilt_degrees']+fit['wheel_tilt_offset_degrees'])
    step = target_meta['scale']*np.array([-1/np.tan(tilt),0,1])
    v = target_wrist-target_s
    roots = np.roots([np.dot(step,step),2*np.dot(v,step),np.dot(v,v)-desired**2])
    options = [float(r.real) for r in roots if abs(r.imag)<1e-7 and abs(fit['wheel_height_offset']+r.real)<.25]
    if options:
        fit['wheel_height_offset'] += min(options, key=abs)
    return ((target_s+(source_elbow-source_s)*(a/source_a))/target_meta['scale']).tolist()


def retarget(source, source_meta, target_meta):
    """Copy normalized wheel contacts and bind-relative turns; never copy another rig's finger lengths."""
    fit = {key: source.get(key, 0) for key in
           ('shoulder_lean_degrees', 'wheel_height_offset', 'wheel_tilt_offset_degrees')}
    source_meta = dict(source_meta, **fit)
    target_meta = dict(target_meta, **fit)
    source_wheel, target_wheel = wheel_frame(source_meta), wheel_frame(target_meta)
    inverse = np.linalg.inv(target_wheel)
    source_bind = {n: unpack(m) for n, m in source_meta['bind_world'].items()}
    target_bind = {n: unpack(m) for n, m in target_meta['bind_world'].items()}
    source_axes, target_axes = anatomical_frames(source_bind), anatomical_frames(target_bind)
    source_world = {n: source_wheel @ unpack(m) for n, m in source['hands']['L'].items()}
    world = {}
    for name in bone_names('L'):
        result = np.eye(4)
        result[:3, :3] = source_world[name][:3, :3] @ source_axes[name] @ target_axes[name].T
        if name == 'hand_L':
            # Temporary wrist anchor. Shift below to preserve knuckle contact rather than wrist distance.
            result[:3, 3] = (target_wheel @ np.append(unpack(source['hands']['L'][name])[:3, 3], 1))[:3]
        else:
            parent = target_meta['parents'][name]
            offset = np.linalg.inv(target_bind[parent]) @ target_bind[name]
            result[:3, 3] = (world[parent] @ np.append(offset[:3, 3], 1))[:3]
        world[name] = result
    knuckles = [f'finger_{i}_L' for i in range(4)]
    anchor = np.mean([unpack(source['hands']['L'][n])[:3, 3] for n in knuckles], axis=0)
    target_anchor = np.mean([(inverse @ world[n])[:3, 3] for n in knuckles], axis=0)
    shift = target_wheel[:3, :3] @ (anchor-target_anchor)
    for value in world.values():
        value[:3, 3] += shift
    left = {name: pack(inverse @ world[name]) for name in bone_names('L')}
    pole = fitted_arm(source, source_meta, target_meta, left, fit)
    target_meta.update(fit)
    return {'schema': 1, 'character': target_meta['id'], 'model_sha256': target_meta['model_sha256'],
            'authored_side': 'L', 'mirror': 'anatomical-bind', 'hands': {'L': left, 'R': mirror_left(left, target_meta)},
            'arm_poles': {'L': pole, 'R': [pole[0], -pole[1], pole[2]]}, **fit}
