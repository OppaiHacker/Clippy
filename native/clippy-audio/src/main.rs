#![cfg_attr(not(windows), allow(dead_code))]
mod logic;
#[cfg(windows)]
mod win;

#[cfg(windows)]
fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    match logic::parse_args(&args) {
        Ok(cmd) => std::process::exit(win::run(cmd)),
        Err(e) => {
            eprintln!("clippy-audio: {e}");
            std::process::exit(2);
        }
    }
}

#[cfg(not(windows))]
fn main() {
    eprintln!("clippy-audio only runs on Windows");
    std::process::exit(2);
}
