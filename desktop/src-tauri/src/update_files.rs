//! File replacement is separate from Tauri so the rollback checks run in seconds.
use std::{fs, path::Path, time::{Duration, Instant}};

pub(crate) const FILES: [&str; 3] = ["Miniima.exe", "miniima-backend.exe", "README.md"];

fn rename_retry(from: &Path, to: &Path) -> Result<(), String> {
    let start = Instant::now();
    loop {
        if fs::rename(from, to).is_ok() { return Ok(()); }
        if start.elapsed() > Duration::from_secs(8) { return Err("程序文件被占用或目录不可写。".into()); }
        std::thread::sleep(Duration::from_millis(150));
    }
}

/// Backups and staged files share the application's volume; unrelated files are untouched.
pub(crate) fn replace_files(app: &Path, stage: &Path, restart: impl FnOnce() -> Result<(), String>) -> Result<(), String> {
    let backup = stage.join("backup");
    fs::create_dir(&backup).map_err(|_| "无法创建更新备份。")?;
    let mut originals = Vec::new();
    let mut installed = Vec::new();
    let outcome = (|| {
        for name in FILES {
            if app.join(name).exists() {
                rename_retry(&app.join(name), &backup.join(name))?;
                originals.push(name);
            }
        }
        for name in FILES {
            rename_retry(&stage.join(name), &app.join(name))?;
            installed.push(name);
        }
        restart()
    })();
    if let Err(error) = outcome {
        let mut restored = true;
        for name in installed.iter().rev() {
            restored &= rename_retry(&app.join(name), &stage.join(name)).is_ok();
        }
        for name in originals.iter().rev() {
            restored &= rename_retry(&backup.join(name), &app.join(name)).is_ok();
        }
        return Err(if restored { format!("更新失败，已恢复旧版：{error}") }
            else { "更新失败，备份仍保留在应用目录的更新暂存文件夹中，请保留该文件夹。".into() });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture(label: &str) -> (std::path::PathBuf, std::path::PathBuf) {
        let root = std::env::temp_dir().join(format!("miniima-update-{}-{label}", std::process::id()));
        let stage = root.join("stage");
        fs::create_dir_all(&stage).unwrap();
        for name in FILES { fs::write(root.join(name), b"old").unwrap(); fs::write(stage.join(name), b"new").unwrap(); }
        fs::write(root.join("personal.txt"), b"keep").unwrap();
        (root, stage)
    }
    #[test]
    fn restart_failure_restores_programs_and_preserves_user_files() {
        let (root, stage) = fixture("rollback");
        assert!(replace_files(&root, &stage, || Err("restart".into())).unwrap_err().contains("已恢复旧版"));
        for name in FILES { assert_eq!(fs::read(root.join(name)).unwrap(), b"old"); }
        assert_eq!(fs::read(root.join("personal.txt")).unwrap(), b"keep");
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn successful_update_only_replaces_allowlisted_files() {
        let (root, stage) = fixture("success");
        replace_files(&root, &stage, || Ok(())).unwrap();
        for name in FILES { assert_eq!(fs::read(root.join(name)).unwrap(), b"new"); assert_eq!(fs::read(stage.join("backup").join(name)).unwrap(), b"old"); }
        assert_eq!(fs::read(root.join("personal.txt")).unwrap(), b"keep");
        fs::remove_dir_all(root).unwrap();
    }
}
