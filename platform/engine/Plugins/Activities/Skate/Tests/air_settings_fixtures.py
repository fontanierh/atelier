"""Shared original AirSettings ordered loader fixtures for independent proofs."""
import copy
import json
from check_gesture_parity import converter

def loader_fixtures(assets):
 data=json.loads((assets/'private/stock/skater-collections.json').read_text())
 order=[('physics_airstates','default','BodySpinInputFilter','words')]+[('physics_mode',m,'GrindLockDist','float')for m in('easy','normal','hardcore','motorized','test')]+[('physics_airstates','default',n,'float')for n in('SpeedToAlignToGround_PhysAir','MaxSpinSpeed','DontAlignAnglePhysicsAir')]+[('physics_steering','default','SteeringTiltBlending','float')]
 def resolve(d,field):
  category,key,name,_=field
  for _ in range(len(d['collections'])+1):
   r=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key));actual=next((n for n in r['fields']if converter.name_id(n)==converter.name_id(name)),None)
   if actual is not None:return r['fields'],actual
   key=r['parent'];assert key
  raise AssertionError(field)
 def change(d,f,kind):
  category,key,name,typ=f;fields,n=resolve(d,f);old=copy.deepcopy(fields[n])
  if kind=='missing':
   record=next(r for r in d['collections']if converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))
   # Stop this one fixture key's inheritance so another mode's independent
   # override survives. All five distance reads keep their distinct errors.
   record['parent']=''
   for field in list(record['fields']):
    if converter.name_id(field)==converter.name_id(name):del record['fields'][field]
  elif kind=='collection':d['collections']=[r for r in d['collections']if not(converter.name_id(r['class'])==converter.name_id(category)and converter.name_id(r['key'])==converter.name_id(key))]
  elif kind=='type':fields[n]={**old,'type':'EA::Reflection::Boolean'}
  elif kind=='width':fields[n]={**old,'data':old['data']+'cafebabe'}
  elif kind=='short':fields[n]={**old,'data':'deadbeef'if typ=='words'else ''}
  elif kind=='nan':fields[n]={**old,'data':('7fc01234'+old['data'][8:])if typ=='words'else '7fc01234'}
  elif kind=='inf':fields[n]={**old,'data':('7f800000'+old['data'][8:])if typ=='words'else '7f800000'}
  else:raise AssertionError(kind)
 result=[]
 for pos,f in enumerate(order):
  for kind in('missing','collection','type','width','short','nan','inf'):
   d=copy.deepcopy(data);change(d,f,kind);success=f[3]=='words'and kind in('type','nan','inf')
   result.append(dict(label=f'{pos:02d}-{f[2]}-{kind}',data=d,success=success,first_position=pos))
  # Every suffix is independently invalid so a changed implementation read
  # order cannot pass by stopping at an unrelated earlier field.
  for later in range(pos+1,len(order)):
   d=copy.deepcopy(data);change(d,f,'width');change(d,order[later],'width');result.append(dict(label=f'compound-{pos:02d}-before-{later:02d}',data=d,success=False,first_position=pos,second_position=later))
 return result
