#!/usr/bin/env python3
"""Compare the C++ port against the actual Rust source (no Unreal or disc required).

python games/yorimichi/tools/check_skate_reference.py --rust path/to/mashup/skate
Compiles reference modules in a temporary directory; does not edit the Rust checkout.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
HEADER = ROOT/'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Public/SkateNativeTuning.h'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rust', type=Path, required=True)
    args = parser.parse_args()
    source = args.rust.resolve()/'crates/skate-core/src'
    with tempfile.TemporaryDirectory(prefix='skate-reference-') as folder:
        work = Path(folder)
        # Have the C++ preset provide the same numeric inputs to both implementations.
        exporter = '#include "' + str(HEADER) + '"\n#include <iostream>\n#include <iomanip>\nint main(){using namespace SkateNative;auto s=RetailSettings();std::cout<<std::setprecision(9);\n'
        fields = [('hard_turn_increase', 'HardTurnIncrease'), ('damping', 'Damping'),
                  ('speed_graph_max_speed', 'SpeedGraphMax'), ('push_scalar_increment', 'PushIncrement'),
                  ('push_scalar_decrement', 'PushDecrement'), ('push_scalar_min', 'PushSteerMin'),
                  ('manual_scalar', 'ManualSteer'), ('general_scalar', 'GeneralSteer'),
                  ('tight_trucks_scalar', 'TightTrucks'), ('tilt_blending', 'TiltBlend')]
        for rust, cpp in fields:
            exporter += f'std::cout<<"{rust}: "<<s.{cpp}<<"f32,\\n";\n'
        for rust, cpp in [('speed_graph', 'SteerSpeed'), ('input_graph', 'SteerInput')]:
            exporter += f'std::cout<<"{rust}: point_graph::PointGraph {{ ";\n'
            for axis in ('X', 'Y'):
                exporter += f'std::cout<<"{axis.lower()}: ["; for(int i=0;i<8;++i)std::cout<<s.{cpp}.{axis}[i]<<"f32,";std::cout<<"],";\n'
            exporter += 'std::cout<<"},\\n";\n'
        exporter += 'std::cout<<"PATTERNS\\n";for(auto p:RetailPatterns()){std::cout<<p.Name<<" "<<p.ToleranceSquared;for(auto v:p.Points)std::cout<<" "<<v.X<<" "<<v.Y;std::cout<<"\\n";}}'
        def compile_cpp(name, code):
            path = work/(name+'.cpp'); path.write_text(code)
            subprocess.run(['clang++', '-std=c++17', '-O2', str(path), '-o', str(work/name)], check=True)
        compile_cpp('export', exporter)
        fields_text, patterns_text = subprocess.check_output([str(work/'export')], text=True).split('PATTERNS\n')
        pattern_expr = []
        for line in patterns_text.splitlines():
            parts = line.split(); points = list(zip(parts[2::2], parts[3::2]))
            pattern_expr.append('gesture::Pattern {name: "'+parts[0]+'".into(), tolerance_squared: '+parts[1]+'f32, points: vec!['+
                                ','.join(f'[{x}f32,{y}f32]' for x, y in points)+'] }')
        rust = '\n'.join(f'#[path="{source/path}"] mod {name};' for name, path in
                         [('point_graph', 'point_graph.rs'), ('steering', 'riding/steering.rs'), ('gesture', 'input/gesture.rs')])
        rust += '''
fn main() {
let s=steering::SteeringSettings {FIELDS};
let mut trucks=steering::TruckSteeringState::default();let mut push=1.0;let mut turn=0.0;
for i in 0..360 {
let value=((i%41) as f32-20.0)/20.0;
let input=steering::SteeringInput {turn:value,hard_turn:if i%53==0 {1.0}else{0.0},absolute_body_speed:(i%28) as f32,
flipped_controls_scalar:if i>=180 {-1.0}else{1.0},balance:if i%3==0 {1.0}else{0.0},truck_tightness:0.5,pushing:i%80<40};
let target=steering::calculate_tilt(&s,input,Some(&mut push),Some(&mut turn));
trucks.update(target,s.tilt_blending,0,if i%7==0 {1<<26}else{3<<26});
println!("S {} {} {} {}",trucks.deck_tilt,trucks.targets[0],trucks.targets[1],push);
}
let patterns=vec![PATTERNS];
for (i,p) in patterns.iter().enumerate() {
let mut r=gesture::Recognizer::new(patterns.clone()).unwrap();let settings=gesture::Settings {maximum_misses:10,difficulty:1};
r.sample([0.0,0.0],settings);
for (n,point) in p.points.iter().enumerate(){if let Some(found)=r.sample(*point,settings){println!("G {} {} {} {}",i,n,found.pattern,found.strength);}}
}
}
'''.replace('FIELDS', fields_text).replace('PATTERNS', ',\n'.join(pattern_expr))
        (work/'reference.rs').write_text(rust)
        subprocess.run(['rustc', '--edition=2024', '-Awarnings', str(work/'reference.rs'), '-o', str(work/'reference')], check=True)
        cpp = '#include "'+str(HEADER)+'"\n#include <iostream>\n#include <iomanip>\n' + '''
int main(){using namespace SkateNative; auto s=RetailSettings();Steering st;std::cout<<std::setprecision(9);
for(int i=0;i<360;++i){float value=(float(i%41)-20)/20;
st.Update(s,value,i%53==0?1:0,float(i%28),i>=180?-1:1,i%3==0,.5f,i%80<40,i%7!=0,true);
std::cout<<"S "<<st.DeckTilt<<" "<<st.Targets[0]<<" "<<st.Targets[1]<<" "<<st.PushScalar<<"\\n";}
auto patterns=RetailPatterns();for(unsigned i=0;i<patterns.size();++i){Gestures g;g.Patterns=patterns;g.Update({});
for(unsigned n=0;n<patterns[i].Points.size();++n){auto r=g.Update(patterns[i].Points[n]);if(r.Index>=0)std::cout<<"G "<<i<<" "<<n<<" "<<r.Index<<" "<<r.Strength<<"\\n";}}
}
'''
        compile_cpp('port', cpp)
        reference = subprocess.check_output([str(work/'reference')], text=True).splitlines()
        port = subprocess.check_output([str(work/'port')], text=True).splitlines()
        assert len(reference) == len(port), (len(reference), len(port))
        maximum = 0
        for index, (left, right) in enumerate(zip(reference, port)):
            a, b = left.split(), right.split()
            assert a[0] == b[0], (index, left, right)
            if a[0] == 'G':
                assert a[1:4] == b[1:4], (index, left, right)
            delta = max(abs(float(x)-float(y)) for x, y in zip(a[1:], b[1:]))
            maximum = max(maximum, delta)
            assert delta < 1e-6, (index, left, right, delta)
        print(f'PASS: 360 steering/contact frames and 78 gesture variants match Rust; max scalar error {maximum:.3g}.')


if __name__ == '__main__':
    main()
