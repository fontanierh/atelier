//! A child that has forked but not yet exec'd still holds every inherited descriptor, so a
//! just-released checkout lock can look busy. Callers retry with a bounded deadline; this pins
//! that contract deterministically with a controlled `pre_exec` window.
#![cfg(unix)]
use atelier_build_v2::checkout_locks::{CheckoutLocks, LockError};
use std::fs;
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::process::CommandExt;
use std::path::PathBuf;
use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

static NEXT: AtomicU64 = AtomicU64::new(0);

struct Workspace(PathBuf);

impl Workspace {
    fn new() -> Self {
        let path = std::env::temp_dir().canonicalize().unwrap().join(format!(
            "atelier-v2-locks-spawn-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&path).unwrap();
        Self(path)
    }

    fn locks(&self) -> CheckoutLocks {
        CheckoutLocks::open(&self.0).unwrap()
    }
}

impl Drop for Workspace {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.0).unwrap();
    }
}

#[test]
fn lock_busy_is_transient_during_spawn() {
    const RELEASE_TIMEOUT_MS: i32 = 5_000;
    const RELEASE_TIMEOUT_EXIT: i32 = 75;

    let workspace = Workspace::new();
    let locks = workspace.locks();
    let build = locks.try_build_exclusive().unwrap();

    let (mut ready_reader, ready_writer) = std::io::pipe().unwrap();
    let ready_write_fd = ready_writer.as_raw_fd();
    let (release_reader, mut release_writer) = std::io::pipe().unwrap();
    let release_read_fd = release_reader.as_raw_fd();
    let release_write_fd = release_writer.as_raw_fd();
    let mut command = Command::new("/usr/bin/true");
    // SAFETY: after fork and before exec this only calls async-signal-safe functions: close,
    // write, poll, read and _exit. The child closes its own copy of the release write end, so the
    // parent's byte or its panic-time EOF is the only release; exec cannot happen before the
    // parent asserts Busy. A broken handshake exits with a distinct code instead of proceeding.
    unsafe {
        command.pre_exec(move || {
            if libc::write(ready_write_fd, b"x".as_ptr().cast(), 1) != 1 {
                return Err(std::io::Error::last_os_error());
            }
            if libc::close(release_write_fd) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            let mut pollfd = libc::pollfd {
                fd: release_read_fd,
                events: libc::POLLIN,
                revents: 0,
            };
            loop {
                let ready = libc::poll(&mut pollfd, 1, RELEASE_TIMEOUT_MS);
                if ready > 0 {
                    break;
                }
                if ready == 0 {
                    libc::_exit(RELEASE_TIMEOUT_EXIT);
                }
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::Interrupted {
                    return Err(error);
                }
            }
            let mut byte = [0u8; 1];
            loop {
                let count = libc::read(release_read_fd, byte.as_mut_ptr().cast(), 1);
                if count >= 0 {
                    return Ok(());
                }
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::Interrupted {
                    return Err(error);
                }
            }
        });
    }

    std::thread::scope(|scope| {
        let spawner = scope.spawn(move || {
            let mut command = command;
            command.spawn()
        });

        let mut pollfd = libc::pollfd {
            fd: ready_reader.as_raw_fd(),
            events: libc::POLLIN,
            revents: 0,
        };
        let ready = unsafe { libc::poll(&mut pollfd, 1, 2000) };
        assert_eq!(ready, 1, "child did not reach its pre-exec window");
        let mut byte = [0u8; 1];
        ready_reader.read_exact(&mut byte).unwrap();
        drop(ready_writer);
        drop(build);

        assert!(
            matches!(locks.try_build_exclusive(), Err(LockError::Busy)),
            "a fork that has not exec'd yet must keep the inherited build lock busy"
        );

        // Release only after the Busy assertion: the child cannot exec before this point.
        release_writer.write_all(b"y").unwrap();
        drop(release_writer);

        let started = Instant::now();
        let guard = loop {
            match locks.try_build_exclusive() {
                Ok(guard) => break guard,
                Err(LockError::Busy) => {
                    assert!(
                        started.elapsed() < Duration::from_secs(2),
                        "checkout build lock stayed busy beyond 2 s after the spawn exec'd"
                    );
                    std::thread::sleep(Duration::from_millis(2));
                }
                Err(error) => panic!("unexpected checkout lock error: {error}"),
            }
        };
        drop(guard);

        let mut child = spawner
            .join()
            .expect("spawner thread")
            .expect("spawn /usr/bin/true");
        let status = child.wait().unwrap();
        assert_eq!(
            status.code(),
            Some(0),
            "child did not take the release handshake or hit its bounded timeout: {status}"
        );
    });
}
