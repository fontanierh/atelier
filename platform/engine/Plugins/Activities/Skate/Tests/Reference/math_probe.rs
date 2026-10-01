//! Temporary frozen-source math oracle. The generated module shells add only
//! visibility adapters; all numerical implementation modules remain unchanged.
use std::io::{Read,Write};
type V=[f32;4];
type M=[V;4];
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let word=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;word}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->V {std::array::from_fn(|_|self.scalar())}
    fn vector3(&mut self)->math::Vector3 {math::Vector3::new(self.scalar(),self.scalar(),self.scalar())}
    fn matrix(&mut self)->M {std::array::from_fn(|_|self.vector())}
}
fn word(out:&mut Vec<u8>,value:u32) {out.extend(value.to_le_bytes());}
fn scalar(out:&mut Vec<u8>,value:f32) {word(out,value.to_bits());}
fn vector(out:&mut Vec<u8>,value:V) {for lane in value {scalar(out,lane);}}
fn vector3(out:&mut Vec<u8>,value:math::Vector3) {for lane in [value.x,value.y,value.z] {scalar(out,lane);}}
fn matrix(out:&mut Vec<u8>,value:M) {for row in value {vector(out,row);}}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();
    let mut reader=Reader{bytes,at:0};let count=reader.word();let mut out=Vec::new();
    for case_id in 0..count {
        let operation=reader.word();word(&mut out,case_id);word(&mut out,operation);
        match operation {
            0=>{
                let v=reader.scalar();
                scalar(&mut out,physics::native_arithmetic::reciprocal_estimate(v));
                scalar(&mut out,physics::native_arithmetic::reciprocal_square_root_estimate(v));
                scalar(&mut out,animation::foot_ik::probe_reciprocal(v,1));
                scalar(&mut out,animation::foot_ik::probe_reciprocal(v,2));
                scalar(&mut out,physics::board_motion_output::inverse_length_squared(v,1));
                scalar(&mut out,physics::board_motion_output::inverse_length_squared(v,2));
                scalar(&mut out,trigonometry::sin(v));scalar(&mut out,trigonometry::cos(v));
                let (s,c)=trigonometry::sin_cos(v);scalar(&mut out,s);scalar(&mut out,c);
                scalar(&mut out,trigonometry::asin(v));scalar(&mut out,trigonometry::acos(v));scalar(&mut out,input::angle::atan(v));
            },
            1=>{
                let a=reader.vector();let b=reader.vector();let limit=reader.scalar();
                scalar(&mut out,physics::native_arithmetic::dot3(a,b));scalar(&mut out,physics::native_arithmetic::dot4(a,b));
                scalar(&mut out,physics::native_arithmetic::vector_min(a[0],b[0]));scalar(&mut out,physics::native_arithmetic::vector_max(a[0],b[0]));
                vector(&mut out,animation::foot_ik::probe_cross(a,b));vector(&mut out,animation::foot_ik::probe_normalize(a));
                scalar(&mut out,animation::foot_ik::probe_length(a));vector(&mut out,animation::foot_ik::probe_limit_length(a,limit));
            },
            2=>{
                let a=reader.vector();let b=reader.vector();let weight=reader.scalar();
                vector(&mut out,animation::probe_quaternion_multiply(a,b));
                for lane in animation::probe_quaternion_rotate(a,[b[0],b[1],b[2]]) {scalar(&mut out,lane);}
                let first=animation::output::Sqt{scale:[1.;4],rotation:a,translation:[0.;4]};
                let second=animation::output::Sqt{rotation:b,..first};
                vector(&mut out,animation::pose_blend::blend_sample(first,second,weight).rotation);
            },
            3=>{
                let a=reader.matrix();let b=reader.matrix();let weight=reader.scalar();
                let mut composed=[[[0.;4];4];2];
                animation::output::compose_hierarchy(2,&[-1,0],-99,&[b,a],&mut composed).unwrap();matrix(&mut out,composed[1]);
                matrix(&mut out,animation::foot_ik::inverse_affine(&a));
                let (axis,angle)=animation::foot_ik::probe_rotation_axis_angle(&a);vector(&mut out,axis);scalar(&mut out,angle);
                let (interpolated,remaining)=animation::foot_ik::interpolate_native(&a,&b,weight);matrix(&mut out,interpolated);scalar(&mut out,remaining);
                matrix(&mut out,animation::foot_ik::interpolate_affine(&a,&b,weight));
            },
            4=>{
                let input=animation::output::Sqt{scale:reader.vector(),rotation:reader.vector(),translation:reader.vector()};
                matrix(&mut out,animation::output::sqt_to_matrix(input));
            },
            5=>{
                let x=std::array::from_fn(|_|reader.scalar());let y=std::array::from_fn(|_|reader.scalar());
                scalar(&mut out,point_graph::PointGraph::<8>{x,y}.evaluate(reader.scalar()));
            },
            6=>{let points=reader.matrix();scalar(&mut out,camera::probe_shake_curve(points,reader.scalar()));},
            7=>{
                let point=reader.vector3();let vertices=std::array::from_fn(|_|reader.vector3());
                let result=physics::probe_closest(point,vertices);vector3(&mut out,result.0);word(&mut out,result.1);scalar(&mut out,result.2);scalar(&mut out,result.3);
            },
            8=>{
                let start=reader.vector3();let direction=reader.vector3();let vertices=std::array::from_fn(|_|reader.vector3());
                let result=physics::triangle_query::thin_triangle(start,direction,vertices);word(&mut out,u32::from(result.is_some()));
                let hit=result.unwrap_or(physics::triangle_query::TriangleLineHit{position:math::Vector3::ZERO,normal:math::Vector3::ZERO,fraction:0.,volume_parameter:[0.;3]});
                vector3(&mut out,hit.position);vector3(&mut out,hit.normal);scalar(&mut out,hit.fraction);
                for lane in hit.volume_parameter {scalar(&mut out,lane);}
            },
            9=>{let axis=reader.vector();matrix(&mut out,animation::foot_ik::probe_axis_rotation(axis,reader.scalar()));},
            _=>panic!("Invalid math operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&out).unwrap();
}
