#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
mod updater;
mod update_files;
mod exports;
use bridge::Bridge;
use serde_json::Value;
use std::path::PathBuf;
use tauri::Manager;
use tauri::{ipc::Channel, AppHandle};
use tauri_plugin_dialog::DialogExt;

#[tauri::command]
async fn backend_stream_request(method: String, params: Value, on_event: Channel<Value>,
    bridge: tauri::State<'_, Bridge>) -> Result<Value, String> {
    if !matches!(method.as_str(), "conversations.send" | "conversations.retry") {
        return Err("不支持的生成操作。".into());
    }
    bridge.request_events(method, params, Some(on_event)).await
}

#[tauri::command]
async fn export_conversation(conversation_id: String, app: AppHandle,
    bridge: tauri::State<'_, Bridge>) -> Result<Value, String> {
    let data = bridge.request("conversations.export".into(), serde_json::json!({"conversation_id": conversation_id})).await?;
    let filename = data["filename"].as_str().ok_or("导出内容无效。")?.to_owned();
    let markdown = data["markdown"].as_str().ok_or("导出内容无效。")?.to_owned();
    tauri::async_runtime::spawn_blocking(move || {
        let selected = app.dialog().file().add_filter("Markdown", &["md"]).set_file_name(&filename).blocking_save_file();
        let Some(selected) = selected else { return Ok(serde_json::json!({"saved": false})); };
        let mut path = selected.into_path().map_err(|_| "请选择本地文件位置。")?;
        if path.extension().is_none() { path.set_extension("md"); }
        exports::write_markdown(&path, &markdown)?;
        Ok(serde_json::json!({"saved": true, "filename": path.file_name().map(|name| name.to_string_lossy().into_owned())}))
    }).await.map_err(|_| "导出操作被中断。".to_owned())?
}

#[tauri::command]
async fn backend_request(method: String, mut params: Value, bridge: tauri::State<'_, Bridge>) -> Result<Value, String> {
    if method == "updates.prepare" { return Err("请使用应用内更新操作。".into()); }
    if method == "updates.check" { params = serde_json::json!({"current_version": env!("CARGO_PKG_VERSION")}); }
    let mut result = bridge.request(method.clone(), params).await?;
    if method == "updates.check" { result["can_install"] = serde_json::json!(updater::info().can_install); }
    Ok(result)
}

#[tauri::command]
fn update_info() -> Value {
    serde_json::json!({"current_version": updater::info().current_version, "can_install": updater::info().can_install,
        "previous_result": updater::previous_result()})
}

#[tauri::command]
async fn prepare_update(version: String, bridge: tauri::State<'_, Bridge>, state: tauri::State<'_, updater::UpdateState>) -> Result<Value, String> {
    use std::sync::atomic::Ordering;
    if !updater::info().can_install { return Err("开发预览不安装更新，请使用发布版。".into()); }
    if bridge.is_busy() || state.preparing.swap(true, Ordering::SeqCst) { return Err("仍有任务正在处理，请稍后更新。".into()); }
    let result = async {
        let app_dir = updater::app_directory()?;
        let value = bridge.request("updates.prepare".into(), serde_json::json!({
            "current_version": env!("CARGO_PKG_VERSION"), "app_dir": app_dir, "expected_version": version })).await?;
        updater::remember(&state, value)
    }.await;
    state.preparing.store(false, Ordering::SeqCst);
    result
}

#[tauri::command]
async fn install_update(app: tauri::AppHandle, bridge: tauri::State<'_, Bridge>, state: tauri::State<'_, updater::UpdateState>) -> Result<(), String> {
    use std::sync::atomic::Ordering;
    if !updater::info().can_install || bridge.is_busy() || state.installing.swap(true, Ordering::SeqCst) {
        return Err("当前无法重启更新，请等待任务完成后重试。".into());
    }
    let prepared = state.prepared.lock().unwrap().clone();
    let result = match prepared {
        Some(prepared) => tauri::async_runtime::spawn_blocking(move || updater::launch_helper(prepared)).await
            .map_err(|_| "无法启动更新辅助进程。".to_owned()).and_then(|r| r),
        None => Err("请先下载更新。".into()),
    };
    if result.is_ok() { bridge.shutdown(); app.exit(0); }
    else { state.installing.store(false, Ordering::SeqCst); }
    result
}

fn backend_path() -> PathBuf {
    let mut path = std::env::current_exe().expect("Application path unavailable");
    path.set_file_name("miniima-backend.exe");
    if cfg!(debug_assertions) && !path.exists() {
        return PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("binaries/miniima-backend-x86_64-pc-windows-msvc.exe");
    }
    path
}

fn main() {
    if updater::run_helper_if_requested() { return; }
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(updater::UpdateState::default())
        .setup(|app| {
            let bridge = Bridge::start(&backend_path()).map_err(std::io::Error::other)?;
            app.manage(bridge);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_request, backend_stream_request, export_conversation, update_info, prepare_update, install_update])
        .build(tauri::generate_context!())
        .expect("Unable to start Mini-ima");
    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
            if let Some(bridge) = handle.try_state::<Bridge>() { bridge.shutdown(); }
        }
    });
}
