use serde::{Deserialize, Serialize};
use crate::update_files::{FILES, replace_files};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::HashMap, fs, io::Read, path::{Path, PathBuf}, process::{Command, Stdio},
    sync::{Mutex, atomic::AtomicBool}, time::{Duration, Instant}};

const RESULT: &str = ".miniima-update-result.json";

#[derive(Clone, Deserialize)]
pub struct Prepared { stage_dir: PathBuf, version: String, token: String }

#[derive(Deserialize)]
struct Manifest { version: String, token: String, files: HashMap<String, String> }

#[derive(Default)]
pub struct UpdateState {
    pub prepared: Mutex<Option<Prepared>>,
    pub preparing: AtomicBool,
    pub installing: AtomicBool,
}

pub fn app_directory() -> Result<PathBuf, String> {
    std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf))
        .ok_or_else(|| "无法确定应用目录。".into())
}

fn safe_stage(app: &Path, stage: &Path) -> Result<PathBuf, String> {
    let app = app.canonicalize().map_err(|_| "无法读取应用目录。")?;
    let stage = stage.canonicalize().map_err(|_| "更新暂存目录已不存在，请重新下载。")?;
    if stage.parent() != Some(app.as_path()) || !stage.file_name().and_then(|s| s.to_str())
        .is_some_and(|name| name.starts_with(".miniima-update-") && name.len() > 20) {
        return Err("更新暂存目录无效。".into());
    }
    Ok(stage)
}

fn hash_file(path: &Path) -> Result<String, String> {
    let mut file = fs::File::open(path).map_err(|_| "更新文件不完整，请重新下载。")?;
    let mut hash = Sha256::new();
    let mut buffer = [0u8; 65536];
    loop {
        let count = file.read(&mut buffer).map_err(|_| "无法读取更新文件。")?;
        if count == 0 { break; }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}

fn validate(app: &Path, prepared: &Prepared) -> Result<PathBuf, String> {
    let stage = safe_stage(app, &prepared.stage_dir)?;
    let bytes = fs::read(stage.join("prepared.json")).map_err(|_| "更新信息已丢失，请重新下载。")?;
    let manifest: Manifest = serde_json::from_slice(&bytes).map_err(|_| "更新信息无效。")?;
    if manifest.token != prepared.token || manifest.version != prepared.version || manifest.files.len() != FILES.len() {
        return Err("更新信息不匹配，请重新下载。".into());
    }
    for name in FILES {
        let path = stage.join(name);
        let metadata = fs::symlink_metadata(&path).map_err(|_| "更新文件不完整。")?;
        if !metadata.is_file() || metadata.file_type().is_symlink() || path.canonicalize().ok().as_deref() != Some(path.as_path())
            || manifest.files.get(name) != Some(&hash_file(&path)?) {
            return Err("更新文件校验失败，请重新下载。".into());
        }
    }
    Ok(stage)
}

pub fn remember(state: &UpdateState, value: Value) -> Result<Value, String> {
    let prepared: Prepared = serde_json::from_value(value).map_err(|_| "后台返回的更新信息无效。")?;
    validate(&app_directory()?, &prepared)?;
    let version = prepared.version.clone();
    *state.prepared.lock().unwrap() = Some(prepared);
    Ok(json!({"version": version}))
}

pub fn launch_helper(prepared: Prepared) -> Result<(), String> {
    let app = app_directory()?;
    let stage = validate(&app, &prepared)?;
    let helper = stage.join("miniima-updater.exe");
    fs::copy(std::env::current_exe().map_err(|_| "无法读取当前程序。")?, &helper)
        .map_err(|_| "无法启动更新，请检查应用目录权限。")?;
    let mut command = Command::new(helper);
    command.args(["--miniima-apply-update", &std::process::id().to_string()])
        .arg(&app).arg(&stage).arg(&prepared.token).arg(&prepared.version)
        .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn().map_err(|_| "无法启动更新辅助进程。")?;
    let start = Instant::now();
    while start.elapsed() < Duration::from_secs(8) {
        if stage.join("helper-ready").exists() { return Ok(()); }
        if child.try_wait().ok().flatten().is_some() { break; }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = child.kill();
    let _ = child.wait();
    Err("更新辅助进程未就绪，当前程序未被修改，请重试。".into())
}

#[cfg(windows)]
fn wait_for_parent(pid: u32) -> Result<(), String> {
    use windows_sys::Win32::{Foundation::CloseHandle, System::Threading::{OpenProcess, WaitForSingleObject}};
    unsafe {
        let process = OpenProcess(0x00100000, 0, pid); // SYNCHRONIZE
        if process.is_null() { return Ok(()); }
        let status = WaitForSingleObject(process, 45000);
        CloseHandle(process);
        if status != 0 { return Err("应用尚未退出，已取消替换。".into()); }
    }
    Ok(())
}

#[cfg(not(windows))]
fn wait_for_parent(_: u32) -> Result<(), String> { Err("仅支持 Windows 桌面内更新。".into()) }

fn start_app(app: &Path) -> Result<(), String> {
    Command::new(app.join("Miniima.exe")).current_dir(app).spawn()
        .map(|_| ()).map_err(|_| "无法重新启动应用。".into())
}

fn save_result(app: &Path, stage: &Path, success: bool, message: &str) -> Result<(), String> {
    fs::write(app.join(RESULT), json!({"success": success, "message": message,
        "cleanup_stage": if success { Some(stage) } else { None }}).to_string())
        .map_err(|_| "无法保存更新结果。".into())
}

/// The same executable has a small helper mode which runs before Tauri/WebView starts.
pub fn run_helper_if_requested() -> bool {
    let args: Vec<_> = std::env::args_os().collect();
    if args.get(1).and_then(|s| s.to_str()) != Some("--miniima-apply-update") { return false; }
    if args.len() != 7 { return true; }
    let app = PathBuf::from(&args[3]);
    let prepared = Prepared { stage_dir: PathBuf::from(&args[4]), token: args[5].to_string_lossy().into(), version: args[6].to_string_lossy().into() };
    let Ok(stage) = validate(&app, &prepared) else { return true };
    if std::env::current_exe().ok().and_then(|p| p.canonicalize().ok()) != Some(stage.join("miniima-updater.exe")) { return true; }
    let Some(pid) = args[2].to_str().and_then(|s| s.parse::<u32>().ok()) else { return true };
    if fs::write(stage.join("helper-ready"), b"ready").is_err() { return true; }
    let outcome = wait_for_parent(pid).and_then(|_| replace_files(&app, &stage, || {
        save_result(&app, &stage, true, &format!("已更新到 {}。", prepared.version))?;
        start_app(&app)
    }));
    if let Err(message) = outcome {
        let _ = save_result(&app, &stage, false, &message);
        let _ = start_app(&app);
    }
    true
}

pub fn previous_result() -> Option<Value> {
    let app = app_directory().ok()?;
    let path = app.join(RESULT);
    let result: Value = serde_json::from_slice(&fs::read(&path).ok()?).ok()?;
    if let Some(stage) = result.get("cleanup_stage").and_then(Value::as_str).and_then(|p| safe_stage(&app, Path::new(p)).ok()) {
        std::thread::spawn(move || {
            std::thread::sleep(Duration::from_secs(3));
            let _ = fs::remove_dir_all(stage);
        });
    }
    let _ = fs::remove_file(path);
    Some(json!({"success": result["success"], "message": result["message"]}))
}

#[derive(Serialize)]
pub struct Info { pub current_version: &'static str, pub can_install: bool }
pub fn info() -> Info { Info { current_version: env!("CARGO_PKG_VERSION"), can_install: cfg!(windows) && !cfg!(debug_assertions) } }
