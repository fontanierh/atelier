//! Thin distribution entry; normal execution is wired after production launcher gates.
fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "--identity" {
        if let Some(source) = atelier_build_v2::controller::source_identity() {
            println!("{source}");
            return;
        }
        eprintln!("controller has no frozen distribution identity");
    } else {
        eprintln!(
            "normal controller execution is pending the accepted production launcher boundary"
        );
    }
    std::process::exit(2);
}
