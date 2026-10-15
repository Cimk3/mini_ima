#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod bridge;
use bridge::Bridge;
use serde_json::Value;
use std::path::PathBuf;
use tauri::Manager;

#[tauri::command]
async fn backend_request(method: String, params: Value, bridge: tauri::State<'_, Bridge>) -> Result<Value, String> {
    bridge.request(method, params).await
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
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            let bridge = Bridge::start(&backend_path()).map_err(std::io::Error::other)?;
            app.manage(bridge);
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![backend_request])
        .build(tauri::generate_context!())
        .expect("Unable to start Mini-ima");
    app.run(|handle, event| {
        if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
            if let Some(bridge) = handle.try_state::<Bridge>() { bridge.shutdown(); }
        }
    });
}
