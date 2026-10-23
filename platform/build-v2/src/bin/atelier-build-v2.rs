//! Thin private controller entry. Normal route activation retains its production gates.
fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    if args.len() == 1 && args[0] == "--identity" {
        if let Some(source) = atelier_build_v2::controller::source_identity() {
            println!("{source}");
            return;
        }
        eprintln!("controller has no frozen distribution identity");
    } else if args.len() == 6
        && args[0] == "--request-fd"
        && args[2] == "--report-fd"
        && args[4] == "--liveness-fd"
    {
        let descriptors: Result<Vec<i32>, _> = [1, 3, 5]
            .into_iter()
            .map(|index| args[index].to_string_lossy().parse())
            .collect();
        if let Ok(descriptors) = descriptors {
            use std::os::fd::FromRawFd;
            if descriptors
                .iter()
                .any(|fd| *fd < 3 || unsafe { libc::fcntl(*fd, libc::F_GETFL) } < 0)
                || descriptors[0] == descriptors[1]
                || descriptors[0] == descriptors[2]
                || descriptors[1] == descriptors[2]
            {
                eprintln!("invalid inherited controller descriptors");
                std::process::exit(2);
            }
            // These distinct open descriptors were inherited specifically for this
            // single-threaded entry; no other Rust owner has been constructed.
            let inherited = descriptors
                .into_iter()
                .map(|fd| unsafe { std::fs::File::from_raw_fd(fd) })
                .collect::<Vec<_>>();
            let inherited: [std::fs::File; 3] = inherited.try_into().unwrap();
            match atelier_build_v2::controller_transport::run(inherited) {
                Ok(()) => return,
                Err(reason) => eprintln!("controller refused: {reason}"),
            }
        } else {
            eprintln!("invalid controller descriptors");
        }
    } else {
        eprintln!("invalid private controller invocation");
    }
    std::process::exit(2);
}
