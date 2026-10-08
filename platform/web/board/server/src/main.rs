//! The agent board's web server. `atelier board serve` builds and runs it; agents keep writing the same SQLite
//! mailbox with `atelier board`.
mod api;
mod db;
mod files;
mod floor;
mod http;
mod inbox;
mod markdown;
mod push;
mod store;
mod views;

use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use base64::Engine;
use rand::RngCore;

const USAGE: &str = "usage: atelier-board-server --assets DIR [--port N] [--public-origin https://host]... \
                     [--allowed-user LOGIN] [--sender NAME] [--remote-status FILE] [--world-build DIR] \
                     [--parent-pid PID] | --schema";

fn fail(message: &str) -> ! {
    eprintln!("{message}\n{USAGE}");
    std::process::exit(2);
}

fn main() {
    let mut args = std::env::args().skip(1);
    let (mut port, mut origins, mut allowed_user, mut sender) = (8890u16, Vec::new(), None, "operator".to_owned());
    let (mut remote_status, mut assets, mut world_build, mut parent) = (None, None, None, None);
    while let Some(arg) = args.next() {
        let mut value = || args.next().unwrap_or_else(|| fail(&format!("{arg} needs a value")));
        match arg.as_str() {
            "--schema" => {
                print!("{}", api::schema());
                return;
            }
            "--port" => port = value().parse().unwrap_or_else(|_| fail("port must be 0–65535")),
            "--public-origin" => origins.push(value()),
            "--allowed-user" => allowed_user = Some(value()),
            "--sender" => sender = value(),
            "--remote-status" => remote_status = Some(PathBuf::from(value())),
            "--assets" => assets = Some(PathBuf::from(value())),
            "--world-build" => world_build = Some(PathBuf::from(value())),
            "--parent-pid" => parent = Some(value().parse::<i32>().unwrap_or_else(|_| fail("bad parent pid"))),
            _ => fail(&format!("unknown argument {arg}")),
        }
    }
    let assets = assets.unwrap_or_else(|| fail("--assets is required"));
    if store::agent_name(&sender).is_err() {
        fail("the sender needs 1–80 letters, digits, dots, underscores or hyphens");
    }
    for origin in &origins {
        let netloc = origin.strip_prefix("https://").unwrap_or("");
        if netloc.is_empty() || netloc.contains(['/', '?', '#', '@']) {
            fail("public-origin must be an exact HTTPS origin without a path");
        }
    }
    if let Err(error) = db::ensure_schema() {
        eprintln!("The board's database cannot be opened: {error:?}");
        std::process::exit(1);
    }
    let runtime = tokio::runtime::Builder::new_multi_thread().enable_all().build().unwrap();
    runtime.block_on(serve(port, origins, allowed_user, sender, remote_status, assets, world_build, parent));
}

#[allow(clippy::too_many_arguments)]
async fn serve(port: u16, origins: Vec<String>, allowed_user: Option<String>, sender: String,
               remote_status: Option<PathBuf>, assets: PathBuf, world_build: Option<PathBuf>, parent: Option<i32>) {
    // A restart can briefly overlap the old server, which lets go of the port within a second or two.
    let mut attempts = 0;
    let listener = loop {
        match tokio::net::TcpListener::bind(("127.0.0.1", port)).await {
            Ok(listener) => break listener,
            Err(error) if error.kind() == std::io::ErrorKind::AddrInUse && attempts < 20 => attempts += 1,
            Err(error) => {
                eprintln!("Cannot listen on 127.0.0.1:{port}: {error}");
                std::process::exit(1);
            }
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    };
    let port = listener.local_addr().unwrap().port();
    let mut allowed: HashSet<String> = [format!("http://127.0.0.1:{port}"), format!("http://localhost:{port}")].into();
    allowed.extend(origins.iter().cloned());
    let mut token = [0u8; 32];
    rand::rngs::OsRng.fill_bytes(&mut token);
    let config = Arc::new(http::Config {
        port,
        origins: allowed,
        allowed_user: allowed_user.filter(|user| !user.is_empty()),
        // VAPID asks for a contact; the board's own HTTPS origin identifies this machine without personal details.
        push_subject: origins.first().cloned().unwrap_or_else(|| "https://localhost".into()),
        sender: sender.clone(),
        remote_status,
        world_build: world_build.unwrap_or_else(|| assets.join("../../../../build/board-world/dist")),
        assets,
        csrf: base64::engine::general_purpose::URL_SAFE_NO_PAD.encode(token),
    });
    let interval = std::env::var("ATELIER_BOARD_PUSH_INTERVAL")
        .ok()
        .and_then(|value| value.parse::<f64>().ok())
        .filter(|seconds| *seconds > 0.0)
        .unwrap_or(3.0);
    tokio::spawn(push::pusher(sender, config.push_subject.clone(), Duration::from_secs_f64(interval)));
    if let Some(parent) = parent {
        // The launcher owns this process: when it goes, so does the server, rather than holding the port.
        std::thread::spawn(move || loop {
            if unsafe { libc::getppid() } != parent {
                std::process::exit(0);
            }
            std::thread::sleep(Duration::from_secs(1));
        });
    }
    let app = axum::Router::new().fallback(move |request| http::handle(config.clone(), request));
    println!("Agent board listening on http://127.0.0.1:{port}");
    if let Err(error) = axum::serve(listener, app).await {
        eprintln!("The board server stopped: {error}");
        std::process::exit(1);
    }
}
