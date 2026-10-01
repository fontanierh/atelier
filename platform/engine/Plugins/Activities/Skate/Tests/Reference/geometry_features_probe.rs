//! Public native GP callbacks, using unmodified frozen numerical modules.
use std::io::{Read,Write};
use physics::world_contact::{
    PrimitiveKind,project_direction,project_directions,separating_axis_candidates,best_separating_direction,
    initialize_feature_segment,capsule_maximum_feature,triangle_maximum_feature,box_maximum_feature,build_feature_edge_planes,
};
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let value=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;value}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn kind(&mut self)->PrimitiveKind {match self.word(){0=>PrimitiveKind::Sphere,1=>PrimitiveKind::Capsule,2=>PrimitiveKind::Triangle,3=>PrimitiveKind::Box,_=>panic!("Invalid primitive kind")}}
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};
    let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let operation=reader.word();out.extend([index,operation]);
        match operation {
            0=>{
                let kind=reader.kind();let gp=reader.words();let directions=reader.word();let outputs=reader.word();
                let directions:Vec<[u32;4]>=(0..directions).map(|_|reader.words()).collect();
                let mut outputs:Vec<[u32;12]>=(0..outputs).map(|_|reader.words()).collect();let mut single=outputs.clone();
                for (&direction,interval) in directions.iter().zip(&mut single) {project_direction(&gp,kind,direction,interval);}
                project_directions(&gp,kind,&directions,&mut outputs);
                for interval in single {out.extend(interval);}for interval in outputs {out.extend(interval);}
            },
            1=>{
                let a=reader.words();let b=reader.words();let mut output=std::array::from_fn(|_|reader.words());
                let a_kind=reader.kind();let b_kind=reader.kind();out.push(separating_axis_candidates(&a,&b,&mut output) as u32);
                for axis in output {out.extend(axis);}let (separation,normal)=best_separating_direction(&a,a_kind,&b,b_kind);
                out.extend(separation);out.extend(normal);
            },
            2=>{let mut output=reader.words();let origin=reader.words();let end=reader.words();initialize_feature_segment(&mut output,origin,end);out.extend(output);},
            3=>{
                let gp=reader.words();let direction=reader.words();let mut output=reader.words();let mut scratch=reader.words();
                capsule_maximum_feature(&gp,direction,&mut output,&mut scratch);out.extend(output);out.extend(scratch);
            },
            4=>{
                let gp=reader.words();let mode=reader.word();let direction=reader.words();let mut output=reader.words();
                triangle_maximum_feature(&gp,mode,direction,&mut output);out.extend(output);
            },
            5=>{
                let gp=reader.words();let mode=reader.word();let direction=reader.words();let mut output=reader.words();let incoming=reader.words();
                box_maximum_feature(&gp,mode,direction,&mut output,incoming);out.extend(output);
            },
            6=>{
                let mut output=reader.words();let mode=reader.word();let direction=reader.words();
                build_feature_edge_planes(&mut output,mode,direction);out.extend(output);
            },
            _=>panic!("Invalid geometry feature operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());
    std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
