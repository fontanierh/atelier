//! Independent frozen-reader export. Originals are never edited or instrumented.
use skate_data::{abin::{Bank,RecordData},animation_banks::AnimationBanks,animation_metadata::{AnimationMetadata,ClipMetadata,TreeMetadata}};
use serde_json::{Value,json};
use std::{fs,io::Write,path::Path,collections::BTreeSet};
fn clip(c:&ClipMetadata,name:&str)->Value {json!({"name":name,"source_offset":c.source_offset,"fps_bits":c.fps_bits,"frames_bits":c.frames_bits,
    "base_speed_bits":c.base_speed_bits,"flags_word":c.flags_word,"attributes":c.attributes.iter().map(|a|json!({"name":a.name,"type_id":a.type_id,
    "begin_bits":a.begin_bits,"end_bits":a.end_bits,"source_offset":a.source_offset,"payload_words":a.payload_words})).collect::<Vec<_>>()})}
fn tree(t:TreeMetadata<'_>,name:&str)->(&'static str,Value) {match t {
    TreeMetadata::Clip(c)=>("clips",clip(c,name)),
    TreeMetadata::PhaseBlend(t)=>("phase_blends",json!({"name":name,"source_offset":t.source_offset,"parameter":t.parameter,"children":t.children})),
    TreeMetadata::BlendSpace(t)=>("blend_spaces",json!({"name":name,"source_offset":t.source_offset,"parameters":t.parameters,"children":t.children,
        "simplexes":t.simplexes.iter().map(|s|json!({"children":s.children,"vertex_bits":s.vertex_bits,"normal_bits":s.normal_bits,"scale_bits":s.scale_bits})).collect::<Vec<_>>()})),
    TreeMetadata::Selector(t)=>("selectors",json!({"name":name,"source_offset":t.source_offset,"parameter":t.parameter,"default":t.default,"children":t.children,"values":t.values})),
    TreeMetadata::SelectionSpace(t)=>("selection_spaces",json!({"name":name,"source_offset":t.source_offset,
        "parameters":t.parameters.iter().map(|p|json!({"name":p.name,"mode":p.mode,"weight_bits":p.weight_bits,"minimum_bits":p.minimum_bits,"maximum_bits":p.maximum_bits})).collect::<Vec<_>>(),
        "candidates":t.candidates.iter().map(|c|json!({"child":c.child,"value_bits":c.value_bits})).collect::<Vec<_>>()})),
}}
fn word(out:&mut Vec<u8>,v:u32) {out.extend(v.to_le_bytes());}
fn wide(out:&mut Vec<u8>,v:u64) {out.extend(v.to_le_bytes());}
fn string(out:&mut Vec<u8>,v:&str) {word(out,v.len() as u32);out.extend(v.as_bytes());}
fn number(v:&Value)->u32 {v.as_u64().unwrap().try_into().unwrap()}
fn strings(out:&mut Vec<u8>,v:&Value) {let a=v.as_array().unwrap();word(out,a.len() as u32);for x in a {string(out,x.as_str().unwrap());}}
fn words(out:&mut Vec<u8>,v:&Value) {let a=v.as_array().unwrap();word(out,a.len() as u32);for x in a {word(out,number(x));}}
fn matrix(out:&mut Vec<u8>,v:&Value) {let a=v.as_array().unwrap();word(out,a.len() as u32);for x in a {words(out,x);}}
fn identity(out:&mut Vec<u8>,v:&Value) {string(out,v["name"].as_str().unwrap());wide(out,v["source_offset"].as_u64().unwrap());}
fn pack(file:&Value)->Vec<u8> {
    let mut out=b"ATMETA01".to_vec();string(&mut out,file["source_bank"].as_str().unwrap());string(&mut out,file["source_sha256"].as_str().unwrap());wide(&mut out,file["source_bytes"].as_u64().unwrap());
    for key in ["clips","phase_blends","blend_spaces","selectors","selection_spaces","unsupported_trees"] {
        let a=file[key].as_array().unwrap();word(&mut out,a.len() as u32);
        for t in a {identity(&mut out,t);match key {
            "clips"=>{for k in ["fps_bits","frames_bits","base_speed_bits","flags_word"] {word(&mut out,number(&t[k]));}
                let attrs=t["attributes"].as_array().unwrap();word(&mut out,attrs.len() as u32);for a in attrs {string(&mut out,a["name"].as_str().unwrap());
                    for k in ["type_id","begin_bits","end_bits"] {word(&mut out,number(&a[k]));}wide(&mut out,a["source_offset"].as_u64().unwrap());words(&mut out,&a["payload_words"]);}},
            "phase_blends"=>{string(&mut out,t["parameter"].as_str().unwrap());strings(&mut out,&t["children"]);},
            "blend_spaces"=>{strings(&mut out,&t["parameters"]);strings(&mut out,&t["children"]);let ss=t["simplexes"].as_array().unwrap();word(&mut out,ss.len() as u32);for s in ss {words(&mut out,&s["children"]);matrix(&mut out,&s["vertex_bits"]);matrix(&mut out,&s["normal_bits"]);words(&mut out,&s["scale_bits"]);}},
            "selectors"=>{string(&mut out,t["parameter"].as_str().unwrap());string(&mut out,t["default"].as_str().unwrap());strings(&mut out,&t["children"]);strings(&mut out,&t["values"]);},
            "selection_spaces"=>{let ps=t["parameters"].as_array().unwrap();word(&mut out,ps.len() as u32);for p in ps {string(&mut out,p["name"].as_str().unwrap());for k in ["mode","weight_bits","minimum_bits","maximum_bits"] {word(&mut out,number(&p[k]));}}
                let cs=t["candidates"].as_array().unwrap();word(&mut out,cs.len() as u32);for c in cs {string(&mut out,c["child"].as_str().unwrap());words(&mut out,&c["value_bits"]);}},
            _=>word(&mut out,number(&t["type_id"])),
        }}
    }out
}
fn kind_offset(t:TreeMetadata<'_>)->(u32,u64) {match t {TreeMetadata::Clip(t)=>(2,t.source_offset),TreeMetadata::BlendSpace(t)=>(6,t.source_offset),TreeMetadata::PhaseBlend(t)=>(7,t.source_offset),TreeMetadata::Selector(t)=>(8,t.source_offset),TreeMetadata::SelectionSpace(t)=>(11,t.source_offset)}}
fn query(metadata:&AnimationMetadata,names:&str)->Vec<u8> {
    let mut out=Vec::new();for name in names.lines() {
        match metadata.clip(name) {Ok(c)=>{word(&mut out,1);wide(&mut out,c.source_offset);word(&mut out,c.flags_word);},Err(_)=>word(&mut out,0)}
        match metadata.tree(name) {Ok(t)=>{let(k,o)=kind_offset(t);word(&mut out,k);wide(&mut out,o);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}
        match metadata.source_for(name) {Some(s)=>{word(&mut out,1);string(&mut out,&s.source_bank);string(&mut out,&s.source_sha256);wide(&mut out,s.source_bytes);},None=>word(&mut out,0)}
    }out
}
fn run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let mode=&args[1];
    if mode=="query" {let metadata=AnimationMetadata::load(Path::new(&args[2]))?;let names=fs::read_to_string(&args[3]).map_err(|e|e.to_string())?;std::io::stdout().write_all(&query(&metadata,&names)).unwrap();return Ok(());}
    if mode=="merge" {let mut metadata=AnimationMetadata::load(Path::new(&args[2]))?;let other=AnimationMetadata::load(Path::new(&args[3]))?;match metadata.merge(other) {Ok(())=>{},Err(e)=>{println!("{e}");return Ok(());}}let names=fs::read_to_string(&args[4]).map_err(|e|e.to_string())?;std::io::stdout().write_all(&query(&metadata,&names)).unwrap();return Ok(());}
    let banks=AnimationBanks::load(Path::new(&args[2]))?;let output=Path::new(&args[3]);fs::create_dir_all(output).map_err(|e|e.to_string())?;
    let mut all_names=BTreeSet::new();
    for (bank_id,bank) in banks.banks.iter().enumerate() {
        let source_bank=if bank_id==0 {"OnBoard.abin"} else {"OffBoard.abin"};
        let mut file=json!({"version":1,"source_bank":source_bank,"source_sha256":banks.identities[bank_id],"source_bytes":bank.bytes().len(),"clips":[],"phase_blends":[],"blend_spaces":[],"selectors":[],"selection_spaces":[],"unsupported_trees":[]});
        // Only the temporary input copy's header names are made unique. All
        // readers remain original, every payload and offset stays untouched.
        // This exposes overwritten records through the original public API.
        let mut bytes=bank.bytes().to_vec();
        for (i,r) in bank.records().iter().enumerate() {
            let name=format!("EXPORT_{i}");let words=skate_core::animation::playback_parameters::intent_key(&name);
            for (j,w) in words.into_iter().enumerate() {bytes[r.header.offset+16+j*4..r.header.offset+20+j*4].copy_from_slice(&w.to_be_bytes());}
        }
        let unique=Bank::parse(bytes).map_err(|e|e.to_string())?;
        let metadata=AnimationMetadata::from_bank(&unique,source_bank.into(),banks.identities[bank_id].clone())?;
        for (i,r) in bank.records().iter().enumerate() {
            if matches!(r.data,RecordData::Pose(_)|RecordData::Hierarchy(_)|RecordData::PhysicsPose(_)) {continue;}
            let(k,v)=if matches!(r.data,RecordData::Opaque) && !matches!(r.header.type_id,6|7|8|11) {("unsupported_trees",json!({"name":r.header.name,"source_offset":r.header.offset,"type_id":r.header.type_id}))}
                else {tree(metadata.tree(&format!("EXPORT_{i}"))?,&r.header.name)};
            file[k].as_array_mut().unwrap().push(v);all_names.insert(r.header.name.to_ascii_lowercase());
        }
        // Compare every consumed field from all effective direct/tree lookups
        // on the UNMODIFIED bank with the corresponding exported record. This
        // guards the temporary header-name rewrite, not only its offsets/kinds.
        let original=AnimationMetadata::from_bank(bank,source_bank.into(),banks.identities[bank_id].clone())?;
        let names=bank.records().iter().map(|r|r.header.name.as_str()).collect::<BTreeSet<_>>();
        for name in names {
            let mut expected=Vec::new();
            if let Ok(c)=original.clip(name) {expected.push(("clips",clip(c,name)));}
            if let Ok(t)=original.tree(name) {expected.push(tree(t,name));}
            for (key,value) in expected {
                let exported=file[key].as_array().unwrap().iter().find(|v|v["name"]==value["name"] && v["source_offset"]==value["source_offset"])
                    .ok_or_else(||format!("Original {key}/{name} lookup missing from export"))?;
                if exported!=&value {return Err(format!("Original {key}/{name} payload differs after header-name export"));}
            }
        }
        // Parse the export through the untouched loader before accepting it.
        AnimationMetadata::parse(&serde_json::to_string(&file).unwrap())?;
        fs::write(output.join(format!("bank-{bank_id}.json")),serde_json::to_vec_pretty(&file).unwrap()).map_err(|e|e.to_string())?;
        fs::write(output.join(format!("bank-{bank_id}.raw")),pack(&file)).map_err(|e|e.to_string())?;
    }
    all_names.insert("missing_animation".into());all_names.insert("bad-name".into());
    let names=all_names.into_iter().collect::<Vec<_>>().join("\n")+"\n";
    fs::write(output.join("queries.txt"),&names).map_err(|e|e.to_string())?;
    fs::write(output.join("queries.raw"),query(&banks.metadata()?,&names)).map_err(|e|e.to_string())?;
    Ok(())
}
fn main() {if let Err(error)=run() {eprintln!("{error}");std::process::exit(2);}}
