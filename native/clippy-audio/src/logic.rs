// Platform-independent logic: CLI parsing, wall-clock pacing, process picking.
use std::time::Duration;

pub const RATE: u64 = 48000;
pub const FRAME_BYTES: usize = 8; // 2 ch * f32
const AHEAD_FRAMES: u64 = RATE / 20; // never run more than 50 ms ahead of wall time
const PAD_MIN_FRAMES: u64 = RATE / 50; // pad zeros once 20 ms behind

#[derive(Debug, PartialEq, Clone)]
pub enum Source {
    System,
    Mic,
    Include(String),
    Exclude(String),
}

#[derive(Debug, PartialEq)]
pub enum Cmd {
    List,
    Monitors,
    Capture { pipe: String, src: Source },
}

pub fn parse_args(args: &[String]) -> Result<Cmd, String> {
    match args.first().map(String::as_str) {
        Some("list") if args.len() == 1 => Ok(Cmd::List),
        Some("monitors") if args.len() == 1 => Ok(Cmd::Monitors),
        Some("capture") => {
            let (mut pipe, mut src) = (None, None);
            let mut it = args[1..].iter();
            while let Some(a) = it.next() {
                let mut val = || it.next().cloned().ok_or(format!("{a} needs a value"));
                let s = match a.as_str() {
                    "--pipe" => {
                        pipe = Some(val()?);
                        continue;
                    }
                    "--system" => Source::System,
                    "--mic" => Source::Mic,
                    "--include" => Source::Include(val()?),
                    "--exclude" => Source::Exclude(val()?),
                    _ => return Err(format!("unknown argument {a}")),
                };
                if src.replace(s).is_some() {
                    return Err("only one of --system/--mic/--include/--exclude".into());
                }
            }
            match (pipe, src) {
                (Some(pipe), Some(src)) if !pipe.is_empty() => Ok(Cmd::Capture { pipe, src }),
                _ => Err("capture needs --pipe NAME and one source".into()),
            }
        }
        _ => Err("usage: clippy-audio list | monitors | capture --pipe NAME (--system|--mic|--include EXE|--exclude EXE)".into()),
    }
}

pub fn target_frames(elapsed: Duration) -> u64 {
    (elapsed.as_nanos() * RATE as u128 / 1_000_000_000) as u64
}

/// Real frames to keep out of `avail`: drop what would put us >50 ms ahead.
pub fn take_frames(written: u64, target: u64, avail: usize) -> usize {
    let room = (target + AHEAD_FRAMES).saturating_sub(written);
    (avail as u64).min(room) as usize
}

/// Zero frames to append to catch up with wall time.
pub fn pad_frames(written: u64, target: u64) -> usize {
    let lag = target.saturating_sub(written);
    if lag >= PAD_MIN_FRAMES { lag as usize } else { 0 }
}

#[derive(Clone, Debug)]
pub struct Proc {
    pub pid: u32,
    pub ppid: u32,
    pub name: String,
}

/// Root pid of the process tree named `name` (parent is not the same exe).
pub fn pick_root(procs: &[Proc], name: &str) -> Option<u32> {
    let same = |p: &Proc| p.name.eq_ignore_ascii_case(name);
    let roots = procs.iter().filter(|p| same(p)).filter(|p| {
        !procs.iter().any(|q| q.pid == p.ppid && q.pid != p.pid && same(q))
    });
    roots.map(|p| p.pid).min().or_else(|| procs.iter().filter(|p| same(p)).map(|p| p.pid).min())
}

pub fn depth(procs: &[Proc], pid: u32) -> u32 {
    let (mut d, mut cur) = (0, pid);
    while d < 64 {
        match procs.iter().find(|p| p.pid == cur).and_then(|p| procs.iter().find(|q| q.pid == p.ppid && q.pid != p.pid)) {
            Some(parent) => {
                cur = parent.pid;
                d += 1;
            }
            None => break,
        }
    }
    d
}

/// One entry per exe name (case-insensitive), lowest depth then lowest pid.
pub fn dedup_by_name(mut v: Vec<(u32, String, u32)>) -> Vec<(u32, String)> {
    v.sort_by(|a, b| (a.1.to_lowercase(), a.2, a.0).cmp(&(b.1.to_lowercase(), b.2, b.0)));
    v.dedup_by(|b, a| a.1.eq_ignore_ascii_case(&b.1));
    v.into_iter().map(|(p, n, _)| (p, n)).collect()
}

fn json_str(s: &str) -> String {
    format!("\"{}\"", s.replace('\\', "\\\\").replace('"', "\\\""))
}

/// DXGI outputs of the default adapter, in ddagrab `output_idx` order: (name, width, height, primary).
pub fn json_monitors(v: &[(String, i32, i32, bool)]) -> String {
    let items: Vec<String> = v
        .iter()
        .map(|(n, w, h, p)| format!("{{\"name\": {}, \"width\": {w}, \"height\": {h}, \"primary\": {p}}}", json_str(n)))
        .collect();
    format!("[{}]", items.join(", "))
}

pub fn json_list(v: &[(u32, String)]) -> String {
    let items: Vec<String> = v
        .iter()
        .map(|(p, n)| format!("{{\"pid\": {p}, \"name\": {}}}", json_str(n)))
        .collect();
    format!("[{}]", items.join(", "))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn a(s: &str) -> Vec<String> {
        s.split_whitespace().map(String::from).collect()
    }
    fn p(pid: u32, ppid: u32, name: &str) -> Proc {
        Proc { pid, ppid, name: name.into() }
    }

    #[test]
    fn args() {
        assert_eq!(parse_args(&a("list")), Ok(Cmd::List));
        assert_eq!(parse_args(&a("monitors")), Ok(Cmd::Monitors));
        assert_eq!(
            parse_args(&a("capture --pipe x --include Discord.exe")),
            Ok(Cmd::Capture { pipe: "x".into(), src: Source::Include("Discord.exe".into()) })
        );
        assert!(parse_args(&a("capture --pipe x")).is_err());
        assert!(parse_args(&a("capture --system --mic --pipe x")).is_err());
        assert!(parse_args(&a("capture --system")).is_err());
        assert!(parse_args(&a("capture --pipe x --include")).is_err());
        assert!(parse_args(&a("bogus")).is_err());
    }

    #[test]
    fn pacing() {
        assert_eq!(target_frames(Duration::from_secs(1)), 48000);
        assert_eq!(take_frames(0, 0, 10000), 2400);
        assert_eq!(take_frames(100, 1000, 480), 480);
        assert_eq!(take_frames(5000, 0, 480), 0);
        assert_eq!(pad_frames(0, 959), 0);
        assert_eq!(pad_frames(0, 960), 960);
        assert_eq!(pad_frames(500, 100), 0);
    }

    #[test]
    fn tree() {
        let ps = [p(1, 0, "explorer.exe"), p(10, 1, "Discord.exe"), p(11, 10, "discord.exe"), p(12, 11, "Discord.exe")];
        assert_eq!(pick_root(&ps, "DISCORD.EXE"), Some(10));
        assert_eq!(pick_root(&ps, "nope.exe"), None);
        assert_eq!(depth(&ps, 12), 3);
        let d = dedup_by_name(vec![(12, "Discord.exe".into(), 3), (10, "Discord.exe".into(), 1), (1, "a.exe".into(), 0)]);
        assert_eq!(d, vec![(1, "a.exe".to_string()), (10, "Discord.exe".to_string())]);
        assert_eq!(
            json_monitors(&[("Dell \"U\"".into(), 2560, 1440, true)]),
            r#"[{"name": "Dell \"U\"", "width": 2560, "height": 1440, "primary": true}]"#
        );
        assert_eq!(json_list(&d), r#"[{"pid": 1, "name": "a.exe"}, {"pid": 10, "name": "Discord.exe"}]"#);
    }
}
