import * as T from 'three';

export const matrix = values => new T.Matrix4().fromArray(values);
export const frame = (position, rotation, scale = new T.Vector3(1, 1, 1)) => new T.Matrix4().compose(position, rotation, scale);
export const position = m => new T.Vector3().setFromMatrixPosition(m);
export const rotation = m => { const p=new T.Vector3(), q=new T.Quaternion(), s=new T.Vector3(); m.decompose(p,q,s);return q; };
export const sideNames = side => [`hand_${side}`,...[0,1,2,3].flatMap(i=>[`finger_${i}_${side}`,`finger_tip_${i}_${side}`,`finger_end_${i}_${side}`]),`thumb_${side}`,`thumb_tip_${side}`,`thumb_end_${side}`];
export function wheelTilt(meta){return meta.layout.steering_tilt_degrees+(meta.wheel_tilt_offset_degrees??0);}
export function wheelHub(meta){
  const base=meta.layout.steering_column_base??[.45564,0,.18],hub=[...meta.layout.steering];
  hub[2]+=meta.wheel_height_offset??0;
  hub[0]=base[0]-(hub[2]-base[2])/Math.tan(T.MathUtils.degToRad(wheelTilt(meta)));
  return new T.Vector3(...hub).multiplyScalar(meta.scale);
}
export function wheelFrame(meta, angle=0) {
  return new T.Matrix4().makeTranslation(...wheelHub(meta).toArray())
    .multiply(new T.Matrix4().makeRotationY(T.MathUtils.degToRad(wheelTilt(meta))))
    .multiply(new T.Matrix4().makeRotationX(angle)).scale(new T.Vector3().setScalar(meta.scale));
}

export function mirrorLeft(left, meta) {
  const wheel=wheelFrame(meta), inverse=wheel.clone().invert(), reflect=new T.Matrix4().makeScale(1,-1,1);
  const bind=Object.fromEntries(Object.entries(meta.bind_world).map(([n,m])=>[n,matrix(m)])), world={}, right={};
  for(const name of sideNames('L')){
    const target=name.replace(/_L$/,'_R'), posed=wheel.clone().multiply(matrix(left[name]));
    const delta=new T.Matrix4().makeRotationFromQuaternion(rotation(posed)).multiply(new T.Matrix4().makeRotationFromQuaternion(rotation(bind[name])).invert());
    const r=reflect.clone().multiply(delta).multiply(reflect).multiply(new T.Matrix4().makeRotationFromQuaternion(rotation(bind[target])));
    let at;
    if(name==='hand_L'){at=position(posed);at.y=-at.y;}
    else {const parent=meta.parents[target], local=bind[parent].clone().invert().multiply(bind[target]);at=position(local).applyMatrix4(world[parent]);}
    world[target]=frame(at,rotation(r));right[target]=inverse.clone().multiply(world[target]).toArray();
  }
  return right;
}

export function twoBone(hip, elbow, wrist, target, pole) {
  const a=hip.distanceTo(elbow), b=elbow.distanceTo(wrist), delta=target.clone().sub(hip), distance=delta.length();
  const direction=delta.normalize(), d=T.MathUtils.clamp(distance,Math.abs(a-b)+1e-5,a+b-1e-5);
  const side=pole.clone().sub(hip).addScaledVector(direction,-pole.clone().sub(hip).dot(direction)).normalize();
  const along=(a*a-b*b+d*d)/(2*d), height=Math.sqrt(Math.max(0,a*a-along*along));
  return {elbow:hip.clone().addScaledVector(direction,along).addScaledVector(side,height),
    wrist:hip.clone().addScaledVector(direction,d),miss:Math.max(0,distance-a-b)};
}


// The native simulation exposes the left front angle; its steering wheel turns 2.5 times as far.
// Blender's +Y is left, so positive steering-wheel roll means a negative road-wheel yaw.
export function frontSteering(layout, wheelAngle){
  const left=-wheelAngle/2.5;
  const length=Math.abs(layout.wheel_positions[0][0]-layout.wheel_positions[2][0]);
  const track=Math.abs(layout.wheel_positions[0][1]-layout.wheel_positions[1][1]);
  // Match SimulationSteering.h's existing Ackermann approximation exactly.
  const right=length*left/(length+track*left);
  return [left,right];
}
