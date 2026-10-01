"""Declaration-only protocol generation for canonical input producer probes.

Reads pinned original fields, never translates numerical implementation methods.
All emitted adapters and corpus material belong under build/.
"""
from collections import OrderedDict
import re
import struct
import check_animation_trees_parity as trees
from check_animation_playback_parity import bits

CORE='crates/skate-core/src/'
TYPE_FILES=[CORE+'player/input_phase/types.rs',CORE+'player/input_phase/air_output.rs',CORE+'player/input_phase/pose_output.rs',CORE+'player/input_phase/grind_output.rs',CORE+'player/input_phase/grind_input.rs',CORE+'animation/output/actor_packet.rs',CORE+'input/animation_packet.rs',CORE+'player/teleport_state.rs',CORE+'animation/output/packet_reset.rs','crates/skate-host/src/physics/animation_phase_packet.rs']
RENAMES={'AdditionalResetFields':'AnimationAdditionalResetFields','Output':'TeleportOutputFields'}


def declarations(extra=False):
    selected={'PlayerInputState','PhysicalPlayerInput','ProcessedPhysicsInput','AnimationInputPacket','ExternalPhysicsInput','AnimationPacketFields','NativeRelativeReference','ProbeFields','LineTestFields','StateVariantFields','CurrentStateFields','SkateboardMotionFields','SystemReckoningFields','GroundOutputFields','CollisionOutputFields','PhysicsOutputFields','OffBoardOutputFields','AirOutputFields','SkeletonOutputFields','AnimationOutputFields','ScoringOutputFields','GrindOutputFields','GrindInvestigationFields','Output'}
    if extra:selected|={'AdditionalResetFields','AnimationProfile'}
    definitions=OrderedDict();sources={}
    for path in TYPE_FILES:
        source=trees.source_at_reference(path);sources[path]=source
        for match in re.finditer(r'\bstruct (\w+)(?:<[^{}]+>)?\s*\{',source):
            name=match[1]
            if name not in selected or (name=='Output' and not path.endswith('teleport_state.rs')):continue
            body=source[match.end():source.index('\n}',match.end())];body=re.sub(r'//[^\n]*','',body)
            fields=[]
            for field,kind in re.findall(r'^\s*pub(?:\([^)]*\))?\s+(\w+)\s*:\s*([^,\n]+),',body,re.M):
                kind=re.sub(r'\s+','',kind);kind=kind.replace("&'a",'&').replace('crate::player::teleport_state::Output','TeleportOutputFields').replace('super::grind_input::','').replace('super::grind_output::','').replace('super::','')
                fields.append((field,kind))
            assert fields,(path,name);definitions[RENAMES.get(name,name)]=fields
    assert selected-{'Output','AdditionalResetFields'}<=set(definitions),selected-set(definitions)
    return definitions,sources


def array(kind):
    if not kind.startswith('['):return None
    depth=0
    for i,c in enumerate(kind):
        if c in '[<':depth+=1
        elif c in ']>':depth-=1
        elif c==';' and depth==1:return kind[1:i],int(kind[i+1:-1])
    return None


def option(kind):return kind[7:-1] if kind.startswith('Option<') else None


def cpp_kind(kind):
    a=array(kind);o=option(kind)
    if a:return f'std::array<{cpp_kind(a[0])},{a[1]}>'
    if o:return f'std::optional<{cpp_kind(o)}>'
    if kind.startswith('&'):return cpp_kind(kind[1:])
    return dict(f32='float',u8='std::uint8_t',u16='std::uint16_t',u32='std::uint32_t',i32='std::int32_t',u64='std::uint64_t',bool='bool').get(kind,kind)


def rust_kind(kind):return 'skate_core::player::teleport_state::Output' if kind=='TeleportOutputFields' else 'skate_core::animation::output::packet_reset::AdditionalResetFields' if kind=='AnimationAdditionalResetFields' else kind


def read_expr(kind,language):
    a=array(kind);o=option(kind)
    if a:
        child=read_expr(a[0],language)
        return f'i.Array<{cpp_kind(a[0])},{a[1]}>([](Input& i){{return {child};}})' if language=='cpp' else f'std::array::from_fn(|_|{child})'
    if o:
        child=read_expr(o,language)
        return f'i.Optional<{cpp_kind(o)}>([](Input& i){{return {child};}})' if language=='cpp' else f'if i.word()!=0 {{Some({child})}} else {{None}}'
    if language=='cpp':
        if kind=='f32':return 'i.Float()'
        if kind=='u32':return 'i.Word()'
        if kind=='u64':return 'i.Wide()'
        if kind=='bool':return 'i.Word()!=0'
        if kind in ('u8','u16','i32'):return f'{cpp_kind(kind)}(i.Word())'
        if kind=='RawVector':return 'i.Words<4>()'
        if kind=='RawMatrix':return 'i.Array<RawVector,4>([](Input& i){return i.Words<4>();})'
        if kind=='AttributeName':return 'i.Words<5>()'
        if kind=='NativeReferenceBase':return 'NativeReferenceBase(i.Word())'
        return f'Read{kind}(i)'
    if kind=='f32':return 'i.float()'
    if kind=='u32':return 'i.word()'
    if kind=='u64':return 'i.wide()'
    if kind=='bool':return 'i.word()!=0'
    if kind in ('u8','u16','i32'):return f'i.word() as {kind}'
    if kind=='RawVector':return 'i.words::<4>()'
    if kind=='RawMatrix':return 'std::array::from_fn(|_|i.words::<4>())'
    if kind=='AttributeName':return 'AttributeName(i.words::<5>())'
    if kind=='NativeReferenceBase':return 'if i.word()==0 {NativeReferenceBase::Player} else {NativeReferenceBase::SurfaceSelector}'
    return f'read_{kind}(i)'


def observe_expr(kind,expr,language):
    a=array(kind);o=option(kind)
    if kind.startswith('&'):return observe_expr(kind[1:],expr,language)
    if a or kind in ('RawVector','RawMatrix','AttributeName'):
        child=a[0] if a else 'RawVector' if kind=='RawMatrix' else 'u32';items=expr if kind!='AttributeName' or language=='cpp' else '('+expr+').0'
        return f'for (const auto& v:{items}) {{{observe_expr(child,"v",language)}}}' if language=='cpp' else f'for v in &{items} {{{observe_expr(child,"*v",language)}}}'
    if o:return f'o.Word(bool({expr}));if ({expr}) {{{observe_expr(o,"*"+expr,language)}}}' if language=='cpp' else f'o.word({expr}.is_some() as u32);if let Some(v)=&{expr} {{{observe_expr(o,"*v",language)}}}'
    if language=='cpp':return f'o.Float({expr});' if kind=='f32' else f'o.Wide({expr});' if kind=='u64' else f'o.Word(std::uint32_t({expr}));' if kind in ('u8','u16','u32','i32','bool','NativeReferenceBase') else f'Observe(o,{expr});'
    return f'o.float({expr});' if kind=='f32' else f'o.wide({expr});' if kind=='u64' else f'o.word({expr} as u32);' if kind in ('u8','u16','u32','i32','bool','NativeReferenceBase') else f'observe_{kind}(o,&{expr});'


def helpers(defs):
    cpp=[];rust=[]
    for name in defs:
        cpp.append(f'void Observe(Output&,const {name}&);')
        if name!='AnimationInputPacket':cpp.append(f'{name} Read{name}(Input&);')
    for name,fields in defs.items():
        cpp.append(f'void Observe(Output& o,const {name}& s) {{'+''.join(observe_expr(k,'s.'+f,'cpp') for f,k in fields)+'}')
        rust.append(f'fn observe_{name}(o:&mut Output,s:&{rust_kind(name)}) {{'+''.join(observe_expr(k,'s.'+f,'rust') for f,k in fields)+'}')
        if name=='AnimationInputPacket':continue
        cpp.append(f'{name} Read{name}(Input& i) {{{name} s;'+''.join('s.'+f+'='+read_expr(k,'cpp')+';' for f,k in fields)+'return s;}')
        rust.append(f'fn read_{name}(i:&mut Input)->{rust_kind(name)} {{'+rust_kind(name)+'{'+''.join(f+':'+read_expr(k,'rust')+',' for f,k in fields)+'}}')
    fields=[(f,k) for f,k in defs['AnimationInputPacket'] if not k.startswith('&')]
    cpp.append('AnimationInputPacket ReadPacket(Input& i,const AnimationPacketFields& publication,const ExternalPhysicsInput& external) {AnimationInputPacket s{publication,external};'+''.join('s.'+f+'='+read_expr(k,'cpp')+';' for f,k in fields)+'return s;}')
    rust.append("fn read_packet<'a>(i:&mut Input,publication:&'a AnimationPacketFields,external:&'a ExternalPhysicsInput)->AnimationInputPacket<'a> {AnimationInputPacket{publication,external_physics_10512:external,"+''.join(f+':'+read_expr(k,'rust')+',' for f,k in fields)+'}}')
    return '\n'.join(cpp),'\n'.join(rust)


def default(kind,defs,seed=0):
    a=array(kind);o=option(kind)
    if kind.startswith('&'):return default(kind[1:],defs,seed)
    if a:return [default(a[0],defs,seed+i) for i in range(a[1])]
    if o:return None
    if kind=='f32':return (.137,.317,.731,-.517)[seed%4]
    if kind in ('u8','u16'):return (0,1,2,255)[seed%4]
    if kind in ('u32','u64'):return (0,1,0x8a123456,0xffffffff)[seed%4]
    if kind=='i32':return seed%4-1
    if kind=='bool':return seed%2==1
    if kind=='RawVector':return [bits(v) for v in (.137+seed*.031,.317,-.731,.517)]
    if kind=='RawMatrix':return [default('RawVector',defs,seed+i) for i in range(4)]
    if kind=='AttributeName':return [seed+1,2,3,4,5]
    if kind=='NativeReferenceBase':return seed%2
    return {f:default(k,defs,seed+i) for i,(f,k) in enumerate(defs[kind])}


def encode(w,kind,value,defs):
    a=array(kind);o=option(kind)
    if kind.startswith('&'):return encode(w,kind[1:],value,defs)
    if o:
        w.word(value is not None)
        if value is not None:encode(w,o,value,defs)
    elif a:
        for v in value:encode(w,a[0],v,defs)
    elif kind=='f32':w.float(value)
    elif kind=='u64':w.wide(value)
    elif kind in ('u8','u16','u32','i32','bool','NativeReferenceBase'):w.word(int(value))
    elif kind in ('RawVector','AttributeName'):
        for v in value:w.word(v)
    elif kind=='RawMatrix':
        for v in value:encode(w,'RawVector',v,defs)
    else:
        for f,k in defs[kind]:encode(w,k,value[f],defs)

class Reader:
    def __init__(self,data):self.data=data;self.at=0
    def word(self):v=struct.unpack_from('<I',self.data,self.at)[0];self.at+=4;return v
    def wide(self):lo=self.word();return lo|(self.word()<<32)
    def string(self):n=self.word();s=self.data[self.at:self.at+n].decode();self.at+=n;return s
    def value(self,kind,defs):
        a=array(kind);o=option(kind)
        if kind.startswith('&'):return self.value(kind[1:],defs)
        if o:return self.value(o,defs) if self.word() else None
        if a:return [self.value(a[0],defs) for _ in range(a[1])]
        if kind=='u64':return self.wide()
        if kind in ('u8','u16','u32','i32','f32','bool','NativeReferenceBase'):return self.word()
        if kind=='RawVector':return [self.word() for _ in range(4)]
        if kind=='RawMatrix':return [self.value('RawVector',defs) for _ in range(4)]
        if kind=='AttributeName':return [self.word() for _ in range(5)]
        return {f:self.value(k,defs) for f,k in defs[kind]}
