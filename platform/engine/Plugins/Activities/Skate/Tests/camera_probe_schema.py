"""Observation-only camera probe schema from the frozen Rust declarations.

Generated implementations append to complete original modules. They read fields
and never replace, edit, intercept or omit a production method or callback.
"""
import hashlib
import re

CORE_TYPES = {
    'tracker': ('ScalarTracker', 'ScalarTrackerParameters'),
    'angle_tracker': ('AngleTracker',),
    'vector_tracker': ('VectorTracker',),
    'anchors': ('AnchorInputs', 'AnchorState', 'Anchors'),
    'subject': ('Subject', 'ReferencePointInputs'),
    'subject_pose': ('SubjectPoseInputs', 'PublishedSubjectPose', 'SubjectPosePublisher'),
    'manager_subject': ('ManagerSubject',),
    'compass': ('CompassSettings', 'CompassInputs', 'Compass', 'CompassPoseInputs'),
    'manager_state': ('ManagerState',),
    'manager': ('ManagerSettings', 'CameraMan'),
    'manager_frame': ('CameraFrame',),
    'shake': ('ShakeSamples', 'ShakeSettings', 'ShakeEffect'),
    'frame_composer': ('FrameSettings', 'FrameSubject', 'FrameComposer'),
    'look_input': ('LookSettings', 'LookInput'),
    'path_prediction': ('PathObstacle', 'PredictionPath'),
    'path_evaluator': ('PathEvaluator',),
    'positioner': ('FatLine', 'FatLineResult', 'PositionerConfig', 'Positioner'),
    'avoidance': ('AvoidanceSettings', 'AvoidancePath'),
    'rig_tracking': ('AngleTrackingSettings', 'AnchorTrackingSettings'),
    'rig_positioning': ('DistanceTrackingSettings', 'RigPositioningSettings'),
    'rig': ('Breadcrumbs', 'RigSettings', 'RigFields', 'Rig'),
    'rig_orientation': ('OrientationTrackerSettings', 'OrientationSettings', 'RigOrientation'),
    'shot': ('Shot',),
    'shot_manager': ('ShotDefinition', 'ShotPlacement', 'ShotNode', 'ShotManager'),
    'drop_predictor': ('DropSettings', 'Probe', 'DropPredictor'),
    'slow_motion': ('SlowMotionSettings', 'SlowMotionController', 'SimulationRateRequest'),
}
HOST_TYPES = {
    'subject': ('CameraSubjectSnapshot', 'SubjectPublisher'),
    'graph_subject': ('CameraGraphSubject', 'CameraGraphEnvironment'),
    'trajectory': ('TrajectoryResult',),
}
INPUT_TYPES = ('Subject', 'ManagerSubject', 'SubjectPoseInputs', 'AnchorInputs',
               'ReferencePointInputs', 'CompassPoseInputs', 'CameraGraphSubject',
               'CameraSubjectSnapshot', 'CameraGraphEnvironment', 'PathObstacle',
               'FatLine', 'PredictionPath', 'TrajectoryQuery')
CPP_NAMES = {'Probe': 'DropProbe'}


def declaration(source, name):
    match = re.search(r'\bstruct\s+' + re.escape(name) + r'\s*([({])', source)
    if not match:
        raise ValueError(f'Missing frozen camera declaration {name}')
    opening = match.end() - 1
    left, right = ('{', '}') if source[opening] == '{' else ('(', ')')
    depth, at = 1, opening + 1
    while depth:
        if source[at] == left:
            depth += 1
        elif source[at] == right:
            depth -= 1
        at += 1
    if left == '(':
        body = source[opening + 1:at - 1].strip()
        assert body == 'pub ScalarTracker', body
        fields = [('0', 'ScalarTracker')]
    else:
        body = re.sub(r'//[^\n]*', '', source[opening + 1:at - 1])
        fields, start, depths = [], 0, {'[': 0, '<': 0, '(': 0}
        closing = {']': '[', '>': '<', ')': '('}
        for index, char in enumerate(body):
            if char in depths:
                depths[char] += 1
            elif char in closing:
                depths[closing[char]] -= 1
            elif char == ',' and not any(depths.values()):
                entry = body[start:index].strip()
                start = index + 1
                if not entry:
                    continue
                field = re.fullmatch(r'(?:pub(?:\([^)]*\))?\s+)?(\w+)\s*:\s*(.+)', entry, re.S)
                if not field:
                    raise ValueError(f'Unsupported frozen field {name}: {entry}')
                fields.append((field[1], re.sub(r'\s+', '', field[2])))
        assert not body[start:].strip(), (name, body[start:])
    prefix = source[:match.start()].encode()
    raw = source[match.start():at].encode()
    return dict(name=name, fields=fields, begin_byte=len(prefix), end_byte=len(prefix) + len(raw),
                declaration_sha256=hashlib.sha256(raw).hexdigest())


def schemas(read):
    values = {}
    for owner, modules in (('skate-core', CORE_TYPES), ('skate-host', HOST_TYPES)):
        for module, names in modules.items():
            path = f'crates/{owner}/src/camera/{module}.rs'
            source = read(path)
            for name in names:
                item = declaration(source, name)
                item['source'] = path
                item['source_sha256'] = hashlib.sha256(source.encode()).hexdigest()
                if name in values:
                    raise AssertionError(f'Duplicate camera schema type {name}')
                values[name] = item
    path = 'crates/skate-core/src/camera/trajectory_query.rs'
    item = declaration(read(path), 'TrajectoryQuery')
    item['source'] = path
    item['source_sha256'] = hashlib.sha256(read(path).encode()).hexdigest()
    values['TrajectoryQuery'] = item
    return values


RUST_OBSERVER = r'''
// Migration observer: representation only, never called by production methods.
pub trait Observe { fn observe(&self, output: &mut Vec<u8>); }
impl Observe for f32 { fn observe(&self,o:&mut Vec<u8>) { self.to_bits().observe(o); } }
impl Observe for u32 { fn observe(&self,o:&mut Vec<u8>) { o.extend(self.to_le_bytes()); } }
impl Observe for i32 { fn observe(&self,o:&mut Vec<u8>) { (*self as u32).observe(o); } }
impl Observe for u8 { fn observe(&self,o:&mut Vec<u8>) { u32::from(*self).observe(o); } }
impl Observe for bool { fn observe(&self,o:&mut Vec<u8>) { u32::from(*self).observe(o); } }
impl Observe for usize { fn observe(&self,o:&mut Vec<u8>) { (*self as u32).observe(o); } }
impl Observe for u64 { fn observe(&self,o:&mut Vec<u8>) { (*self as u32).observe(o); ((*self>>32) as u32).observe(o); } }
impl Observe for String { fn observe(&self,o:&mut Vec<u8>) { self.len().observe(o);o.extend(self.as_bytes()); } }
impl<T:Observe,const N:usize> Observe for [T;N] { fn observe(&self,o:&mut Vec<u8>) { for v in self { v.observe(o); } } }
impl<T:Observe> Observe for Vec<T> { fn observe(&self,o:&mut Vec<u8>) { self.len().observe(o);for v in self { v.observe(o); } } }
impl<T:Observe> Observe for Option<T> { fn observe(&self,o:&mut Vec<u8>) { self.is_some().observe(o);if let Some(v)=self {v.observe(o);} } }
impl<K:Observe,V:Observe> Observe for std::collections::BTreeMap<K,V> {fn observe(&self,o:&mut Vec<u8>) {self.len().observe(o);for (k,v) in self {k.observe(o);v.observe(o);}}}
impl<A:Observe,B:Observe> Observe for (A,B) { fn observe(&self,o:&mut Vec<u8>) { self.0.observe(o);self.1.observe(o); } }
impl Observe for crate::math::Basis3 { fn observe(&self,o:&mut Vec<u8>) {self.columns.observe(o);} }
impl<const N:usize> Observe for crate::point_graph::PointGraph<N> { fn observe(&self,o:&mut Vec<u8>) {self.x.observe(o);self.y.observe(o);} }
pub struct Input { pub data:Vec<u8>,pub at:usize }
impl Input {
    pub fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.data[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    pub fn float(&mut self)->f32 {f32::from_bits(self.word())}
    pub fn boolean(&mut self)->bool {self.word()!=0}
    pub fn string(&mut self)->String {let n=self.word() as usize;let v=String::from_utf8(self.data[self.at..self.at+n].to_vec()).unwrap();self.at+=n;v}
}
pub trait ReadValue {fn read(input:&mut Input)->Self;}
impl ReadValue for f32 {fn read(r:&mut Input)->Self {r.float()}}
impl ReadValue for u32 {fn read(r:&mut Input)->Self {r.word()}}
impl ReadValue for u8 {fn read(r:&mut Input)->Self {r.word() as u8}}
impl ReadValue for i32 {fn read(r:&mut Input)->Self {r.word() as i32}}
impl ReadValue for usize {fn read(r:&mut Input)->Self {r.word() as usize}}
impl ReadValue for u64 {fn read(r:&mut Input)->Self {u64::from(r.word())|(u64::from(r.word())<<32)}}
impl ReadValue for bool {fn read(r:&mut Input)->Self {r.boolean()}}
impl ReadValue for String {fn read(r:&mut Input)->Self {r.string()}}
impl<T:ReadValue,const N:usize> ReadValue for [T;N] {fn read(r:&mut Input)->Self {core::array::from_fn(|_|T::read(r))}}
impl<T:ReadValue> ReadValue for Vec<T> {fn read(r:&mut Input)->Self {(0..r.word()).map(|_|T::read(r)).collect()}}
impl<T:ReadValue> ReadValue for Option<T> {fn read(r:&mut Input)->Self {r.boolean().then(||T::read(r))}}
impl ReadValue for crate::math::Basis3 {fn read(r:&mut Input)->Self {Self{columns:ReadValue::read(r)}}}
'''


def rust_observe(item, host=False):
    trait = 'skate_core::migration_camera_observer::Observe' if host else 'crate::migration_camera_observer::Observe'
    body = '\n'.join(f'        {trait}::observe(&self.{name}, output);' for name, _ in item['fields'])
    return f'\nimpl {trait} for {item["name"]} {{\n    fn observe(&self, output:&mut Vec<u8>) {{\n{body}\n    }}\n}}\n'


def rust_read(item, host=False):
    namespace = 'skate_core' if host else 'crate'
    trait = f'{namespace}::migration_camera_observer::ReadValue'
    fields = ','.join(f'{name}:{trait}::read(input)' for name, _ in item['fields'])
    return f'\nimpl {trait} for {item["name"]} {{ fn read(input:&mut {namespace}::migration_camera_observer::Input)->Self {{Self{{{fields}}}}} }}\n'


def input_closure(values):
    wanted = set(INPUT_TYPES)
    pending = list(wanted)
    while pending:
        name = pending.pop()
        for _, kind in values[name]['fields']:
            for child in re.findall(r'\b[A-Z]\w*\b', kind):
                if child in values and child not in wanted:
                    wanted.add(child)
                    pending.append(child)
    return wanted


def cpp_name(name):
    return CPP_NAMES.get(name, name)


def cpp_type(value):
    if '::' in value:
        value = value.rsplit('::', 1)[-1]
    scalar = {'f32': 'float', 'u32': 'std::uint32_t', 'u8': 'std::uint8_t',
              'i32': 'std::int32_t', 'usize': 'std::size_t', 'u64': 'std::uint64_t',
              'bool': 'bool', 'String': 'std::string'}
    if value in scalar:
        return scalar[value]
    if value.startswith('['):
        match = re.fullmatch(r'\[(.+);(\d+)\]', value)
        assert match, value
        return f'std::array<{cpp_type(match[1])},{match[2]}>'
    for rust, cpp in (('Vec', 'std::vector'), ('Option', 'std::optional')):
        if value.startswith(rust + '<'):
            return f'{cpp}<{cpp_type(value[len(rust) + 1:-1])}>'
    if value.startswith('('):
        # The only tuple is DropPredictor's fixed pair of query arrays.
        depth, split = 0, None
        for index, char in enumerate(value[1:-1], 1):
            if char in '[<(':
                depth += 1
            elif char in ']> )'.replace(' ', ''):
                depth -= 1
            elif char == ',' and depth == 0:
                split = index
                break
        assert split is not None, value
        return f'std::pair<{cpp_type(value[1:split])},{cpp_type(value[split + 1:-1])}>'
    return cpp_name(value)


def cpp_observers(values):
    declarations, bodies = [], []
    for item in values.values():
        name = cpp_name(item['name'])
        declarations.append(f'void WriteValue(Output&,const {name}&);')
        fields = [f'output.Word(std::uint32_t(value.{field}));' if kind == 'usize' else
                  f'WriteValue(output,value.{"state" if field == "0" else field});'
                  for field, kind in item['fields']]
        bodies.append(f'void WriteValue(Output& output,const {name}& value){{' + ''.join(fields) + '}')
    reads = []
    for name in values:
        if name not in input_closure(values):
            continue
        item = values[name]
        declarations.append(f'template<> {name} ReadValue<{name}>(Input& input);')
        fields = [f'value.{field}=ReadValue<{cpp_type(kind)}>(input);' for field, kind in item['fields']]
        reads.append(f'template<> {name} ReadValue<{name}>(Input& input){{{name} value;' + ''.join(fields) + 'return value;}')
    return '\n'.join(declarations) + '\n// @CPP_GENERIC_WRITERS@\n' + '\n'.join(bodies + reads)


CPP_GENERIC_WRITERS = r'''
template<class T,std::size_t N> void WriteValue(Output&,const std::array<T,N>&);
template<class T> void WriteValue(Output&,const std::vector<T>&);
template<class T> void WriteValue(Output&,const std::optional<T>&);
template<class A,class B> void WriteValue(Output&,const std::pair<A,B>&);
template<class K,class V> void WriteValue(Output&,const std::map<K,V>&);
template<std::size_t N> void WriteValue(Output&,const PointGraph<N>&);
template<class T> struct ArrayInfo { static constexpr bool value=false; };
template<class T,std::size_t N> struct ArrayInfo<std::array<T,N>> {static constexpr bool value=true;using Element=T;};
template<class T> struct VectorInfo { static constexpr bool value=false; };
template<class T> struct VectorInfo<std::vector<T>> {static constexpr bool value=true;using Element=T;};
template<class T> struct OptionalInfo { static constexpr bool value=false; };
template<class T> struct OptionalInfo<std::optional<T>> {static constexpr bool value=true;using Element=T;};
template<class T> T ReadValue(Input& input)
{
    if constexpr(std::is_same_v<T,float>) return input.Float();
    else if constexpr(std::is_same_v<T,std::uint64_t>) {const auto low=input.Word();return std::uint64_t(low)|(std::uint64_t(input.Word())<<32);}
    else if constexpr(std::is_integral_v<T>) return T(input.Word());
    else if constexpr(std::is_same_v<T,std::string>) return input.String();
    else if constexpr(ArrayInfo<T>::value) {T value;for(auto& lane:value)lane=ReadValue<typename ArrayInfo<T>::Element>(input);return value;}
    else if constexpr(VectorInfo<T>::value) {T value;const auto count=input.Word();value.reserve(count);for(std::uint32_t i=0;i<count;++i)value.push_back(ReadValue<typename VectorInfo<T>::Element>(input));return value;}
    else if constexpr(OptionalInfo<T>::value) {if(input.Word()!=0)return ReadValue<typename OptionalInfo<T>::Element>(input);return std::nullopt;}
    else {static_assert(!std::is_same_v<T,T>,"Missing camera probe read schema");}
}
template<class T,std::size_t N> void WriteValue(Output& output,const std::array<T,N>& value) {for(const auto& entry:value)WriteValue(output,entry);}
template<class T> void WriteValue(Output& output,const std::vector<T>& value) {output.Word(std::uint32_t(value.size()));for(const auto& entry:value)WriteValue(output,entry);}
template<class T> void WriteValue(Output& output,const std::optional<T>& value) {output.Word(value.has_value());if(value)WriteValue(output,*value);}
template<class A,class B> void WriteValue(Output& output,const std::pair<A,B>& value) {WriteValue(output,value.first);WriteValue(output,value.second);}
template<class K,class V> void WriteValue(Output& output,const std::map<K,V>& value) {output.Word(std::uint32_t(value.size()));for(const auto& entry:value) {WriteValue(output,entry.first);WriteValue(output,entry.second);}}
template<std::size_t N> void WriteValue(Output& output,const PointGraph<N>& value) {WriteValue(output,value.x);WriteValue(output,value.y);}
'''


def encoded_value(writer, kind, value, values):
    if '::' in kind:
        kind = kind.rsplit('::', 1)[-1]
    if kind == 'f32':
        writer.float(value)
    elif kind in ('u8', 'u32', 'i32', 'usize', 'bool'):
        writer.word(int(value) & 0xffffffff)
    elif kind == 'u64':
        writer.word(value & 0xffffffff)
        writer.word(value >> 32)
    elif kind == 'String':
        writer.string(value)
    elif kind.startswith('['):
        match = re.fullmatch(r'\[(.+);(\d+)\]', kind)
        assert len(value) == int(match[2]), (kind, len(value))
        for entry in value:
            encoded_value(writer, match[1], entry, values)
    elif kind.startswith('Vec<'):
        writer.word(len(value))
        for entry in value:
            encoded_value(writer, kind[4:-1], entry, values)
    else:
        fields = values[kind]['fields']
        assert set(value) == {field for field, _ in fields}, (kind, set(value), fields)
        for field, field_kind in fields:
            encoded_value(writer, field_kind, value[field], values)


def zero_value(kind, values):
    if '::' in kind:
        kind = kind.rsplit('::', 1)[-1]
    if kind in ('f32', 'u8', 'u32', 'i32', 'usize', 'u64', 'bool'):
        return 0
    if kind == 'String':
        return ''
    if kind.startswith('Vec<'):
        return []
    if kind.startswith('['):
        match = re.fullmatch(r'\[(.+);(\d+)\]', kind)
        return [zero_value(match[1], values) for _ in range(int(match[2]))]
    return {field: zero_value(field_kind, values) for field, field_kind in values[kind]['fields']}
