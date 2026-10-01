// Channel ownership harness; the check script provides shared tree IO and
// verbatim frozen host methods and MotionChannels implementation.
fn channel_settings(input:&mut Input)->skate_core::animation::channel_playback::ChannelSettings {
    skate_core::animation::channel_playback::ChannelSettings{priority:input.word() as i32,keep_alive:input.word()!=0,mirrored:input.word()!=0,speed:input.float(),blend_in:input.float(),hold_during_blend_in:input.word()!=0,blend_out:input.float(),hold_during_blend_out:input.word()!=0,use_attributes:input.word()!=0}
}
fn channel_run()->Result<(),String> {
    let args:Vec<_>=std::env::args().collect();let mut bytes=Vec::new();std::io::stdin().read_to_end(&mut bytes).unwrap();let mut input=Input{bytes,at:8};let count=input.word();let mut out=Vec::new();
    for _ in 0..count {
        let mut channels=motion_channels::MotionChannels::default();let mut host=MotionAnimation::new(load_metadata(&[&args[1]])?);let n=input.word();
        for _ in 0..n {match input.word() {
            0=>{let name=input.string();let tree=input.tree()?;let settings=channel_settings(&mut input);channels.insert(name,tree,settings);status(&mut out,Ok(()));},
            1=>{channels.end(&input.string());status(&mut out,Ok(()));},
            2=>{let name=input.string();let seconds=input.float();let from_last_frame=input.word()!=0;channels.end_with(&name,seconds,from_last_frame);status(&mut out,Ok(()));},
            3=>{let name=input.string();let value=input.float();boolean(&mut out,Ok(channels.influence(&name,value)));},
            4=>{let name=input.string();boolean(&mut out,Ok(channels.can_transition(&name,input.word()!=0)));},
            5=>{let name=input.string();let tree=input.tree()?;let settings=channel_settings(&mut input);let transition=input.transition();let resurrect=input.word()!=0;channels.transition(&name,tree,settings,transition,resurrect);status(&mut out,Ok(()));},
            6=>{channels.retire();status(&mut out,Ok(()));},
            7=>{let dt=input.float();let phase=input.float();status(&mut out,panic_result(||channels.advance(dt,phase)));},
            8=>{let a=input.settable();status(&mut out,channels.prepare_trees(|tree|host.prepare_selection_spaces(tree,&a)));},
            9=>{let a=input.settable();status(&mut out,channels.set_attributes(&a));},
            10=>{let n=input.word();let base=(0..n).map(|_|input.attribute()).collect();let mask=input.word();match channels.attributes(base,mask) {Ok(a)=>{word(&mut out,1);attributes(&mut out,&a);},Err(e)=>{word(&mut out,0);string(&mut out,&e);}}},
            11=>{let name=input.name();let mask=input.word();let mut a=input.attribute();boolean(&mut out,channels.query_attribute(name,mask,&mut a));attribute(&mut out,&a);},
            12=>{let p=Evaluation{cull_threshold:input.float(),update_history:input.word()!=0};let mut c=vec![PoseCommand::Pose{name:"SENTINEL".into()}];status(&mut out,channels.evaluate(p,&mut c));commands(&mut out,&c);},
            13=>{let n=input.word();word(&mut out,n);for _ in 0..n {let name=input.string();word(&mut out,u32::from(channels.has(&name)));word(&mut out,channels.remaining(&name).to_bits());word(&mut out,channels.elapsed(&name).to_bits());word(&mut out,u32::from(channels.in_transition(&name)));}},
            14=>{channels.reset_from_stock();status(&mut out,Ok(()));},
            _=>unreachable!(),
        }channels.probe_snapshot(&mut out);}
    }assert_eq!(input.at,input.bytes.len());std::io::stdout().write_all(&out).map_err(|e|e.to_string())?;Ok(())
}
fn main() {std::panic::set_hook(Box::new(|_|{}));if let Err(e)=channel_run() {eprintln!("{e}");std::process::exit(2);}}
