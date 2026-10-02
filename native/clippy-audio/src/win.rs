// WASAPI capture -> named pipe. Windows only.
use crate::logic::*;
use std::mem::size_of;
use std::time::{Duration, Instant};
use windows::core::{implement, Interface, Ref, Result, HRESULT, PCWSTR, PWSTR};
use windows::Win32::Foundation::*;
use windows::Win32::Graphics::Dxgi::*;
use windows::Win32::Graphics::Gdi::{EnumDisplayDevicesW, DISPLAY_DEVICEW};
use windows::Win32::Media::Audio::*;
use windows::Win32::Storage::FileSystem::{WriteFile, PIPE_ACCESS_OUTBOUND};
use windows::Win32::System::Com::StructuredStorage::*;
use windows::Win32::System::Com::*;
use windows::Win32::System::Diagnostics::ToolHelp::*;
use windows::Win32::System::Pipes::*;
use windows::Win32::System::Threading::*;
use windows::Win32::System::Variant::VT_BLOB;

const FLAGS_CONVERT: u32 = AUDCLNT_STREAMFLAGS_AUTOCONVERTPCM | AUDCLNT_STREAMFLAGS_SRC_DEFAULT_QUALITY;

pub fn run(cmd: Cmd) -> i32 {
    match run_inner(cmd) {
        Ok(()) => 0,
        Err(e) => {
            eprintln!("clippy-audio: {e}");
            1
        }
    }
}

fn run_inner(cmd: Cmd) -> Result<()> {
    unsafe { CoInitializeEx(None, COINIT_MULTITHREADED).ok()? };
    match cmd {
        Cmd::List => {
            println!("{}", json_list(&list_sessions()?));
            Ok(())
        }
        Cmd::Monitors => {
            println!("{}", json_monitors(&monitors()?));
            Ok(())
        }
        Cmd::Capture { pipe, src } => capture(&pipe, &src),
    }
}

fn wstr(w: &[u16]) -> String {
    String::from_utf16_lossy(&w[..w.iter().position(|&c| c == 0).unwrap_or(w.len())])
}

/// Outputs of adapter 0, the one ffmpeg's ddagrab opens by default, so the index is its output_idx.
// ponytail: monitors wired to another GPU (hybrid laptops) are not listed; ddagrab would need that adapter's device
fn monitors() -> Result<Vec<(String, i32, i32, bool)>> {
    let mut v = Vec::new();
    unsafe {
        let adapter = CreateDXGIFactory1::<IDXGIFactory1>()?.EnumAdapters1(0)?;
        while let Ok(out) = adapter.EnumOutputs(v.len() as u32) {
            let d = out.GetDesc()?;
            let r = d.DesktopCoordinates;
            let mut dd = DISPLAY_DEVICEW { cb: size_of::<DISPLAY_DEVICEW>() as u32, ..Default::default() };
            let name = if EnumDisplayDevicesW(PCWSTR(d.DeviceName.as_ptr()), 0, &mut dd, 0).as_bool() {
                wstr(&dd.DeviceString)
            } else {
                wstr(&d.DeviceName)
            };
            // the primary monitor is the one at the desktop origin
            v.push((name, r.right - r.left, r.bottom - r.top, r.left == 0 && r.top == 0));
        }
    }
    Ok(v)
}

fn processes() -> Vec<Proc> {
    let mut v = Vec::new();
    unsafe {
        let Ok(snap) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else { return v };
        let mut e = PROCESSENTRY32W { dwSize: size_of::<PROCESSENTRY32W>() as u32, ..Default::default() };
        let mut ok = Process32FirstW(snap, &mut e).is_ok();
        while ok {
            v.push(Proc { pid: e.th32ProcessID, ppid: e.th32ParentProcessID, name: wstr(&e.szExeFile) });
            ok = Process32NextW(snap, &mut e).is_ok();
        }
        let _ = CloseHandle(snap);
    }
    v
}

fn enumerator() -> Result<IMMDeviceEnumerator> {
    unsafe { CoCreateInstance(&MMDeviceEnumerator, None, CLSCTX_ALL) }
}

fn list_sessions() -> Result<Vec<(u32, String)>> {
    let procs = processes();
    let mut out = Vec::new();
    unsafe {
        let devs = enumerator()?.EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE)?;
        for i in 0..devs.GetCount()? {
            let Ok(mgr) = devs.Item(i)?.Activate::<IAudioSessionManager2>(CLSCTX_ALL, None) else { continue };
            let sessions = mgr.GetSessionEnumerator()?;
            for j in 0..sessions.GetCount()? {
                let Ok(c) = sessions.GetSession(j)?.cast::<IAudioSessionControl2>() else { continue };
                let pid = c.GetProcessId().unwrap_or(0);
                if let Some(p) = procs.iter().find(|p| p.pid == pid && pid != 0) {
                    out.push((pid, p.name.clone(), depth(&procs, pid)));
                }
            }
        }
    }
    Ok(dedup_by_name(out))
}

// ---- capture source ----

#[derive(PartialEq, Clone)]
enum Key {
    Device(String),
    Pid(u32),
}

fn wfx() -> WAVEFORMATEX {
    WAVEFORMATEX {
        wFormatTag: 3, // WAVE_FORMAT_IEEE_FLOAT
        nChannels: 2,
        nSamplesPerSec: RATE as u32,
        nAvgBytesPerSec: RATE as u32 * FRAME_BYTES as u32,
        nBlockAlign: FRAME_BYTES as u16,
        wBitsPerSample: 32,
        cbSize: 0,
    }
}

struct Capturer {
    key: Key,
    client: IAudioClient,
    cap: IAudioCaptureClient,
    event: HANDLE,
}

impl Drop for Capturer {
    fn drop(&mut self) {
        unsafe {
            let _ = self.client.Stop();
            let _ = CloseHandle(self.event);
        }
    }
}

impl Capturer {
    fn new(key: Key, client: IAudioClient, flags: u32) -> Result<Self> {
        unsafe {
            client.Initialize(AUDCLNT_SHAREMODE_SHARED, flags | AUDCLNT_STREAMFLAGS_EVENTCALLBACK, 0, 0, &wfx(), None)?;
            let event = CreateEventW(None, false, false, PCWSTR::null())?;
            client.SetEventHandle(event)?;
            let cap = client.GetService::<IAudioCaptureClient>()?;
            client.Start()?;
            Ok(Self { key, client, cap, event })
        }
    }

    /// Append all pending frames (interleaved f32) to `out`.
    fn read(&self, out: &mut Vec<f32>) -> Result<()> {
        unsafe {
            while self.cap.GetNextPacketSize()? > 0 {
                let (mut p, mut n, mut fl) = (std::ptr::null_mut(), 0u32, 0u32);
                self.cap.GetBuffer(&mut p, &mut n, &mut fl, None, None)?;
                let len = n as usize * 2;
                if fl & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 || p.is_null() {
                    out.resize(out.len() + len, 0.0);
                } else {
                    out.extend_from_slice(std::slice::from_raw_parts(p as *const f32, len));
                }
                self.cap.ReleaseBuffer(n)?;
            }
        }
        Ok(())
    }
}

#[implement(IActivateAudioInterfaceCompletionHandler)]
struct Handler(HANDLE);

impl IActivateAudioInterfaceCompletionHandler_Impl for Handler_Impl {
    fn ActivateCompleted(&self, _op: Ref<IActivateAudioInterfaceAsyncOperation>) -> Result<()> {
        unsafe { SetEvent(self.0) }
    }
}

fn open_process(pid: u32, exclude: bool) -> Result<Capturer> {
    let mut params = AUDIOCLIENT_ACTIVATION_PARAMS {
        ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        Anonymous: AUDIOCLIENT_ACTIVATION_PARAMS_0 {
            ProcessLoopbackParams: AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
                TargetProcessId: pid,
                ProcessLoopbackMode: if exclude {
                    PROCESS_LOOPBACK_MODE_EXCLUDE_TARGET_PROCESS_TREE
                } else {
                    PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE
                },
            },
        },
    };
    // blob points at our stack: never let PROPVARIANT's Drop free it
    let mut pv = std::mem::ManuallyDrop::new(PROPVARIANT::default());
    unsafe {
        let inner = &mut *pv.Anonymous.Anonymous;
        inner.vt = VT_BLOB;
        inner.Anonymous.blob.cbSize = size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>() as u32;
        inner.Anonymous.blob.pBlobData = &mut params as *mut _ as *mut u8;

        let done = CreateEventW(None, false, false, PCWSTR::null())?;
        let handler: IActivateAudioInterfaceCompletionHandler = Handler(done).into();
        let op = match ActivateAudioInterfaceAsync(VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, &IAudioClient::IID, Some(&*pv), &handler) {
            Ok(op) => op,
            Err(e) => {
                let _ = CloseHandle(done);
                return Err(e);
            }
        };
        if WaitForSingleObject(done, 5000) != WAIT_OBJECT_0 {
            return Err(E_FAIL.into()); // event leaked on purpose: handler may still fire
        }
        let _ = CloseHandle(done);
        let mut hr = HRESULT(0);
        let mut unk = None;
        op.GetActivateResult(&mut hr, &mut unk)?;
        hr.ok()?;
        let client: IAudioClient = unk.ok_or(windows::core::Error::from(E_FAIL))?.cast()?;
        Capturer::new(Key::Pid(pid), client, AUDCLNT_STREAMFLAGS_LOOPBACK | FLAGS_CONVERT)
    }
}

fn default_device(src: &Source) -> Result<IMMDevice> {
    let flow = if *src == Source::Mic { eCapture } else { eRender };
    unsafe { enumerator()?.GetDefaultAudioEndpoint(flow, eConsole) }
}

fn device_id(d: &IMMDevice) -> String {
    unsafe { d.GetId().map(|p: PWSTR| p.to_string().unwrap_or_default()).unwrap_or_default() }
}

/// What we should currently be capturing from, if anything.
fn desired(src: &Source) -> Option<Key> {
    match src {
        Source::System | Source::Mic => default_device(src).ok().map(|d| Key::Device(device_id(&d))),
        Source::Include(exe) => pick_root(&processes(), exe).map(Key::Pid),
        // nothing to exclude yet: exclude our own tree (silent) = capture everything
        Source::Exclude(exe) => Some(Key::Pid(pick_root(&processes(), exe).unwrap_or_else(std::process::id))),
    }
}

fn open(src: &Source, key: Key) -> Result<Capturer> {
    match (src, key) {
        (Source::System, Key::Device(_)) | (Source::Mic, Key::Device(_)) => {
            let dev = default_device(src)?;
            let id = device_id(&dev);
            let client = unsafe { dev.Activate::<IAudioClient>(CLSCTX_ALL, None)? };
            let extra = if *src == Source::System { AUDCLNT_STREAMFLAGS_LOOPBACK } else { 0 };
            Capturer::new(Key::Device(id), client, extra | FLAGS_CONVERT)
        }
        (Source::Include(_), Key::Pid(p)) => open_process(p, false),
        (Source::Exclude(_), Key::Pid(p)) => open_process(p, true),
        _ => Err(E_FAIL.into()),
    }
}

// ---- pipe ----

struct Pipe(HANDLE);

impl Pipe {
    fn write(&self, mut b: &[u8]) -> bool {
        while !b.is_empty() {
            let mut n = 0u32;
            if unsafe { WriteFile(self.0, Some(b), Some(&mut n), None) }.is_err() || n == 0 {
                return false; // client gone
            }
            b = &b[n as usize..];
        }
        true
    }
}

fn capture(name: &str, src: &Source) -> Result<()> {
    let path: Vec<u16> = format!("\\\\.\\pipe\\{name}\0").encode_utf16().collect();
    let pipe = unsafe {
        let h = CreateNamedPipeW(
            PCWSTR(path.as_ptr()),
            PIPE_ACCESS_OUTBOUND,
            PIPE_TYPE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
            1,
            1 << 20,
            0,
            0,
            None,
        );
        if h.is_invalid() {
            return Err(windows::core::Error::from_thread());
        }
        if let Err(e) = ConnectNamedPipe(h, None) {
            if e.code() != ERROR_PIPE_CONNECTED.to_hresult() {
                return Err(e);
            }
        }
        Pipe(h)
    };

    let is_proc = matches!(src, Source::Include(_) | Source::Exclude(_));
    let check_every = Duration::from_secs(if is_proc { 2 } else { 1 });
    let start = Instant::now();
    let mut next_check = start;
    let mut cur: Option<Capturer> = None;
    let (mut written, mut frames) = (0u64, Vec::<f32>::new());
    let mut bytes = Vec::<u8>::new();

    loop {
        let now = Instant::now();
        if now >= next_check {
            next_check = now + check_every;
            let want = desired(src);
            if cur.as_ref().map(|c| &c.key) != want.as_ref() {
                cur = None; // detach (drop stops the client)
                if let Some(k) = want {
                    match open(src, k) {
                        Ok(c) => cur = Some(c),
                        Err(e) => eprintln!("clippy-audio: open failed: {e}"),
                    }
                }
            }
        }

        frames.clear();
        if let Some(c) = &cur {
            unsafe { WaitForSingleObject(c.event, 10) };
            if let Err(e) = c.read(&mut frames) {
                eprintln!("clippy-audio: read failed, detaching: {e}");
                cur = None;
                next_check = Instant::now() + Duration::from_secs(1);
            }
        } else {
            std::thread::sleep(Duration::from_millis(10));
        }

        let target = target_frames(start.elapsed());
        let take = take_frames(written, target, frames.len() / 2);
        bytes.clear();
        for s in &frames[..take * 2] {
            bytes.extend_from_slice(&s.to_le_bytes());
        }
        written += take as u64;
        let pad = pad_frames(written, target);
        bytes.resize(bytes.len() + pad * FRAME_BYTES, 0);
        written += pad as u64;
        if !bytes.is_empty() && !pipe.write(&bytes) {
            return Ok(());
        }
    }
}
