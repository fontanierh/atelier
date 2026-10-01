// SPDX-License-Identifier: Apache-2.0
use std::io::{Read,Write};
mod climbing {
    use bevy::prelude::*;
    mod clip;
    mod contacts;
    mod ledge {
        use bevy::prelude::*;
        // GENERATED_ORIGINAL_LEDGE_DECLARATION
    }
    // GENERATED_ORIGINAL_SMOOTH
    fn word(data:&mut &[u8])->u32{let(a,b)=data.split_at(4);*data=b;u32::from_le_bytes(a.try_into().unwrap())}
    fn float(data:&mut &[u8])->f32{f32::from_bits(word(data))}
    fn v3(data:&mut &[u8])->Vec3{Vec3::new(float(data),float(data),float(data))}
    fn v4(data:&mut &[u8])->Quat{Quat::from_xyzw(float(data),float(data),float(data),float(data))}
    fn m4(data:&mut &[u8])->Mat4{let mut a=[0.;16];for v in &mut a{*v=float(data);}Mat4::from_cols_array(&a)}
    fn out(o:&mut Vec<u8>,v:u32){o.extend(v.to_le_bytes());}
    fn f(o:&mut Vec<u8>,v:f32){out(o,v.to_bits());}
    fn vec3(o:&mut Vec<u8>,v:Vec3){for v in v.to_array(){f(o,v)}}
    fn quat(o:&mut Vec<u8>,q:Quat){for v in q.to_array(){f(o,v)}}
    fn matrix(o:&mut Vec<u8>,m:Mat4){for v in m.to_cols_array(){f(o,v)}}
    fn text(o:&mut Vec<u8>,s:&str){out(o,s.len()as u32);o.extend(s.as_bytes());}
    fn status(o:&mut Vec<u8>,r:Result<(),String>){match r{Ok(())=>{out(o,1);text(o,"")},Err(e)=>{out(o,0);text(o,&e)}}}
    fn transform(o:&mut Vec<u8>,t:Transform){vec3(o,t.translation);quat(o,t.rotation);vec3(o,t.scale);}
    fn pose(o:&mut Vec<u8>,locals:&[Transform],c:&clip::Clip){out(o,locals.len()as u32);for t in locals{transform(o,*t)}let globals=c.globals(locals);out(o,globals.len()as u32);for m in &globals{matrix(o,*m)}vec3(o,c.hands(&globals));vec3(o,c.feet(&globals));vec3(o,contacts::clearance(c,&globals));}
    fn clip(o:&mut Vec<u8>,c:&clip::Clip){text(o,&c.name);f(o,c.fps);f(o,c.duration());out(o,c.names.len()as u32);for n in &c.names{text(o,n)}out(o,c.parents.len()as u32);for p in &c.parents{out(o,*p as u32)}out(o,c.frames.len()as u32);for frame in &c.frames{out(o,frame.len()as u32);for s in frame{for v in s{f(o,*v)}}}}
    fn owner(o:&mut Vec<u8>,r:&Option<clip::Clips>){out(o,r.is_some()as u32);if let Some(r)=r{clip(o,&r.reach);clip(o,&r.mantle)}}
    pub(super)fn run(root:&std::path::Path,mut data:&[u8],o:&mut Vec<u8>){
      let mut current=None;let count=word(&mut data);out(o,count);
      for _ in 0..count{let op=word(&mut data);out(o,op);
       match op{
        0=>{let a=v3(&mut data);let b=v3(&mut data);let v=v3(&mut data);let q=v4(&mut data);let r=v4(&mut data);let t=float(&mut data);let m=m4(&mut data);let k=m4(&mut data);status(o,Ok(()));f(o,a.dot(b));vec3(o,a.cross(b));f(o,a.length());f(o,a.distance(b));vec3(o,a.normalize());let normal=a.try_normalize();out(o,normal.is_some()as u32);if let Some(n)=normal{vec3(o,n)}vec3(o,a.normalize_or_zero());vec3(o,a.lerp(b,t));vec3(o,a.normalize().any_orthonormal_vector());
         f(o,q.length());quat(o,q.normalize());quat(o,q.inverse());quat(o,q*r);quat(o,Quat::from_rotation_y(t));quat(o,Quat::from_rotation_arc(a.normalize(),b.normalize()));quat(o,q.slerp(r,t));vec3(o,q*v);vec3(o,m.transform_point3(v));vec3(o,m.transform_vector3(v));matrix(o,m*k);matrix(o,m.inverse());f(o,m.determinant());let tr=Transform::from_matrix(m);transform(o,tr);matrix(o,tr.to_matrix());f(o,smooth(t));let mut native=m.to_cols_array_2d();native[3][3]=0.;for c in native{for v in c{f(o,v)}}for c in &mut native[..3]{c[3]=0.}native[3][3]=1.;matrix(o,Mat4::from_cols_array_2d(&native));
        },
        1=>{let i=word(&mut data);match clip::Clips::load(&root.join(format!("case-{i}"))){Ok(loaded)=>{current=loaded;status(o,Ok(()));},Err(e)=>status(o,Err(e))}owner(o,&current);},
        2|3=>{let which=word(&mut data);let time=float(&mut data);let mut root=Mat4::IDENTITY;let mut ledge=ledge::Ledge{anchor:Vec3::ZERO,landing:Vec3::ZERO,forward:Vec3::ZERO,palms:[Vec3::ZERO;2],normals:[Vec3::ZERO;2]};let mut weight=0.;if op==3{root=m4(&mut data);ledge.anchor=v3(&mut data);ledge.landing=v3(&mut data);ledge.forward=v3(&mut data);for p in &mut ledge.palms{*p=v3(&mut data)}for n in &mut ledge.normals{*n=v3(&mut data)}weight=float(&mut data);}
         let Some(c)=&current else{status(o,Err("Missing authored climbing clips".into()));continue;};let c=if which==0{&c.reach}else{&c.mantle};let mut locals=c.sample(time);if op==3{contacts::hands(c,&mut locals,root,ledge,weight)}status(o,Ok(()));pose(o,&locals,c);if op==3{for i in 0..2{let(p,q)=contacts::wrist(ledge,i);vec3(o,p);quat(o,q)}}
        },
        _=>panic!("invalid opcode {op}"),
       }
      }
      assert!(data.is_empty());
    }
}
fn main(){let root=std::env::args().nth(1).unwrap();let mut input=Vec::new();std::io::stdin().read_to_end(&mut input).unwrap();let mut output=Vec::new();climbing::run(std::path::Path::new(&root),&input,&mut output);std::io::stdout().write_all(&output).unwrap();}
