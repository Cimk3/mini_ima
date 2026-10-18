use std::{fs::{self, OpenOptions}, io::Write, path::Path, time::{SystemTime, UNIX_EPOCH}};

pub fn write_markdown(path: &Path, text: &str) -> Result<(), String> {
    let parent = path.parent().ok_or("保存位置无效。")?;
    let nonce = SystemTime::now().duration_since(UNIX_EPOCH).map_err(|_| "无法创建导出文件。")?.as_nanos();
    let temporary = parent.join(format!(".miniima-export-{}-{nonce}.tmp", std::process::id()));
    let result = (|| {
        let mut file = OpenOptions::new().write(true).create_new(true).open(&temporary)
            .map_err(|_| "无法写入所选目录，请选择其他位置。")?;
        file.write_all(text.as_bytes()).and_then(|_| file.sync_all())
            .map_err(|_| "导出写入失败，原文件未被修改。")?;
        drop(file);
        fs::rename(&temporary, path).map_err(|_| "无法保存导出文件，请检查权限或文件占用。")?;
        Ok(())
    })();
    if result.is_err() { let _ = fs::remove_file(&temporary); }
    result
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn replaces_utf8_file_and_preserves_target_when_rename_fails() {
        let root = std::env::temp_dir().join(format!("miniima-export-{}-{}", std::process::id(),
            SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos()));
        fs::create_dir(&root).unwrap();
        let target = root.join("中文.md");
        fs::write(&target, "old").unwrap();
        write_markdown(&target, "# 完整对话\n").unwrap();
        assert_eq!(fs::read_to_string(&target).unwrap(), "# 完整对话\n");
        let directory = root.join("occupied.md");
        fs::create_dir(&directory).unwrap();
        assert!(write_markdown(&directory, "new").is_err());
        assert!(directory.is_dir());
        assert_eq!(fs::read_dir(&root).unwrap().count(), 2);
        fs::remove_dir_all(&root).unwrap();
    }
}
