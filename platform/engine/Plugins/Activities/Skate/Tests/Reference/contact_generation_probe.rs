//! Original public typed contact generation/compilation; raw compile wrapper stays in the same crate.
use std::io::{Read,Write};
use math::Vector3;
use physics::contact::{RetailContactInput,RetailContactBodyState,RetailContact,RetailContactWorkspace,generate_contact};
use physics::contact_solver::build_contact_jacobian;
struct Reader {bytes:Vec<u8>,at:usize}
impl Reader {
    fn word(&mut self)->u32 {let v=u32::from_le_bytes(self.bytes[self.at..self.at+4].try_into().unwrap());self.at+=4;v}
    fn scalar(&mut self)->f32 {f32::from_bits(self.word())}
    fn vector(&mut self)->Vector3 {Vector3::new(self.scalar(),self.scalar(),self.scalar())}
    fn words<const N:usize>(&mut self)->[u32;N] {std::array::from_fn(|_|self.word())}
    fn input(&mut self)->RetailContactInput {RetailContactInput{position_on_a:self.vector(),position_on_b:self.vector(),normal:self.vector(),restitution:self.scalar(),static_friction:self.scalar(),dynamic_friction:self.scalar(),tag:self.word()}}
    fn body(&mut self)->RetailContactBodyState {RetailContactBodyState{contact_body_id:self.word(),center_of_mass:self.vector(),reaction_id:self.word(),inverse_inertia_full:self.vector(),inverse_mass:self.scalar(),inverse_inertia_split:self.vector(),state:self.word(),force_acceleration:self.vector(),kinetic_energy:self.scalar(),torque_acceleration:self.vector(),cool_down:self.word(),linear_velocity:self.vector(),angular_velocity:self.vector()}}
}
fn lanes(v:Vector3,w:u32)->[u32;4] {[v.x.to_bits(),v.y.to_bits(),v.z.to_bits(),w]}
fn workspace(w:RetailContactWorkspace)->[[u32;4];5] {[lanes(w.center_of_mass,w.reaction_id),lanes(w.inverse_inertia_full,w.inverse_mass.to_bits()),lanes(w.inverse_inertia_split,w.state),lanes(w.force_acceleration,w.kinetic_energy.to_bits()),lanes(w.torque_acceleration,w.cool_down)]}
fn encode(c:RetailContact)->[u32;64] {
    let mut words=[0;64];let header=[lanes(c.position_on_a,c.body_a_id),lanes(c.position_on_b,c.body_b_id),lanes(c.normal,c.restitution.to_bits()),lanes(c.tangent_0,c.static_friction.to_bits()),lanes(c.tangent_1,c.dynamic_friction.to_bits()),lanes(c.relative_velocity,c.tag)];
    for (i,v) in header.into_iter().enumerate(){words[i*4..i*4+4].copy_from_slice(&v);}
    for (i,(a,b)) in workspace(c.body_a_workspace).into_iter().zip(workspace(c.body_b_workspace)).enumerate(){words[24+i*8..28+i*8].copy_from_slice(&a);words[28+i*8..32+i*8].copy_from_slice(&b);}words
}
fn main() {
    let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut reader=Reader{bytes,at:0};let count=reader.word();let mut out=Vec::new();
    for index in 0..count {
        let op=reader.word();out.extend([index,op]);
        match op {
            0|1=>{let input=reader.input();let a=reader.body();let b=reader.body();let contact=generate_contact(input,a,b);out.extend(encode(contact));if op==1{let row=build_contact_jacobian(contact,reader.scalar());out.extend(*row.words());out.extend([row.reaction_index_a as u32,row.reaction_index_b as u32]);}},
            2=>{let mut record=reader.words();let a=record[27];let b=record[31];physics::solver::compile_contact(&mut record,reader.scalar());out.extend(record);out.extend([a,b]);},
            _=>panic!("Invalid contact generation operation"),
        }
    }
    assert_eq!(reader.at,reader.bytes.len());std::io::stdout().write_all(&out.into_iter().flat_map(u32::to_le_bytes).collect::<Vec<_>>()).unwrap();
}
