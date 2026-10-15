use serde_json::{json, Value};
use std::{collections::HashMap, io::{BufRead, BufReader, Write}, path::Path, process::{Child, ChildStdin, Command, Stdio},
    sync::{Arc, Mutex, atomic::{AtomicU64, Ordering}}, time::Duration};
use tokio::sync::oneshot;

type Reply = Result<Value, String>;

#[derive(Default)]
struct Pending {
    requests: Mutex<HashMap<String, oneshot::Sender<Reply>>>,
}

impl Pending {
    fn deliver(&self, response: Value) {
        let Some(id) = response.get("id").and_then(Value::as_str) else { return };
        let Some(sender) = self.requests.lock().unwrap().remove(id) else { return };
        let result = if let Some(error) = response.get("error") {
            Err(error.get("message").and_then(Value::as_str).unwrap_or("本地请求失败。").to_owned())
        } else if let Some(value) = response.get("result") {
            Ok(value.clone())
        } else {
            Err("本地后台返回了无效响应。".to_owned())
        };
        let _ = sender.send(result);
    }

    fn fail_all(&self) {
        for (_, sender) in self.requests.lock().unwrap().drain() {
            let _ = sender.send(Err("本地后台已退出，请重新启动应用。".to_owned()));
        }
    }
}

#[cfg(windows)]
struct ProcessJob(isize);

#[cfg(windows)]
impl ProcessJob {
    fn attach(child: &Child) -> Result<Self, String> {
        use std::os::windows::io::AsRawHandle;
        use windows_sys::Win32::{Foundation::CloseHandle, System::JobObjects::{CreateJobObjectW,
            SetInformationJobObject, AssignProcessToJobObject, JobObjectExtendedLimitInformation,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE}};
        unsafe {
            let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if handle.is_null() { return Err("无法创建后台进程管理器。".into()); }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let configured = SetInformationJobObject(handle, JobObjectExtendedLimitInformation,
                &info as *const _ as *const _, std::mem::size_of_val(&info) as u32);
            if configured == 0 || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0 {
                CloseHandle(handle);
                return Err("无法管理后台进程，请重新启动应用。".into());
            }
            Ok(Self(handle as isize))
        }
    }
}

#[cfg(windows)]
impl Drop for ProcessJob {
    fn drop(&mut self) {
        unsafe { windows_sys::Win32::Foundation::CloseHandle(self.0 as _); }
    }
}

pub struct Bridge {
    stdin: Mutex<Option<ChildStdin>>,
    child: Mutex<Option<Child>>,
    pending: Arc<Pending>,
    sequence: AtomicU64,
    #[cfg(windows)]
    job: Mutex<Option<ProcessJob>>,
}

impl Bridge {
    pub fn start(path: &Path) -> Result<Self, String> {
        let mut command = Command::new(path);
        command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null());
        command.env("PYTHONUTF8", "1").env("PYTHONIOENCODING", "utf-8");
        #[cfg(windows)] {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000); // CREATE_NO_WINDOW; backend stdio remains piped.
        }
        let mut child = command.spawn().map_err(|_| "无法启动本地后台，请检查应用目录中的后台程序。")?;
        #[cfg(windows)]
        let job = match ProcessJob::attach(&child) {
            Ok(job) => job,
            Err(error) => { let _ = child.kill(); let _ = child.wait(); return Err(error); }
        };
        let stdin = child.stdin.take().ok_or("本地后台输入不可用。")?;
        let stdout = child.stdout.take().ok_or("本地后台输出不可用。")?;
        let pending = Arc::new(Pending::default());
        let reader_pending = Arc::clone(&pending);
        std::thread::spawn(move || {
            for line in BufReader::new(stdout).lines() {
                let Ok(line) = line else { break };
                let Ok(response) = serde_json::from_str::<Value>(&line) else { break };
                reader_pending.deliver(response);
            }
            reader_pending.fail_all();
        });
        Ok(Self { stdin: Mutex::new(Some(stdin)), child: Mutex::new(Some(child)), pending,
            sequence: AtomicU64::new(1), #[cfg(windows)] job: Mutex::new(Some(job)) })
    }

    pub async fn request(&self, method: String, params: Value) -> Reply {
        if !allowed_method(&method) || !params.is_object() { return Err("不支持的桌面请求。".into()); }
        if self.child.lock().unwrap().as_mut().and_then(|child| child.try_wait().ok()).flatten().is_some() {
            return Err("本地后台已退出，请重新启动应用。".into());
        }
        let id = self.sequence.fetch_add(1, Ordering::Relaxed).to_string();
        let (sender, receiver) = oneshot::channel();
        self.pending.requests.lock().unwrap().insert(id.clone(), sender);
        let message = json!({"id": id, "method": method, "params": params}).to_string() + "\n";
        let written = self.stdin.lock().unwrap().as_mut().map(|input| input.write_all(message.as_bytes()));
        if !matches!(written, Some(Ok(()))) {
            self.pending.requests.lock().unwrap().remove(&id);
            return Err("无法向本地后台发送请求。".into());
        }
        match tokio::time::timeout(Duration::from_secs(300), receiver).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => Err("本地请求被中断，请重新启动应用。".into()),
            Err(_) => { self.pending.requests.lock().unwrap().remove(&id);
                Err("处理时间较长，请稍后刷新查看结果。".into()) }
        }
    }

    pub fn shutdown(&self) {
        self.stdin.lock().unwrap().take();
        #[cfg(windows)] self.job.lock().unwrap().take(); // Kill the complete PyInstaller process tree.
        if let Some(mut child) = self.child.lock().unwrap().take() { let _ = child.kill(); let _ = child.wait(); }
        self.pending.fail_all();
    }
}

impl Drop for Bridge { fn drop(&mut self) { self.shutdown(); } }

fn allowed_method(method: &str) -> bool {
    matches!(method, "initialize" | "kb.list" | "kb.create" | "kb.delete" | "docs.list" | "docs.preview" |
        "docs.import" | "search" | "ask" | "settings.get" | "settings.update" | "settings.qwen" |
        "connections.test" | "doctor" | "conversations.list" | "conversations.get" |
        "conversations.send" | "conversations.retry" | "conversations.delete" |
        "trash.list" | "trash.restore" | "trash.purge" | "trash.empty")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_response_to_id_without_disturbing_other_requests() {
        let pending = Pending::default();
        let (one, mut first) = oneshot::channel();
        let (two, mut second) = oneshot::channel();
        pending.requests.lock().unwrap().insert("1".into(), one);
        pending.requests.lock().unwrap().insert("2".into(), two);
        pending.deliver(json!({"id":"2", "result":["ok"]}));
        assert_eq!(second.try_recv().unwrap().unwrap(), json!(["ok"]));
        assert!(first.try_recv().is_err());
        pending.deliver(json!({"id":"1", "error":{"code":"provider", "message":"连接失败"}}));
        assert_eq!(first.try_recv().unwrap().unwrap_err(), "连接失败");
    }

    #[test]
    fn backend_exit_fails_every_waiter() {
        let pending = Pending::default();
        let (sender, mut receiver) = oneshot::channel();
        pending.requests.lock().unwrap().insert("1".into(), sender);
        pending.fail_all();
        assert!(receiver.try_recv().unwrap().unwrap_err().contains("已退出"));
        assert!(pending.requests.lock().unwrap().is_empty());
    }

    #[test]
    fn rejects_arbitrary_commands_and_ignores_late_responses() {
        assert!(!allowed_method("shell.exec"));
        assert!(allowed_method("ask"));
        for method in ["conversations.list", "conversations.get", "conversations.send",
            "conversations.retry", "conversations.delete", "trash.list", "trash.restore",
            "trash.purge", "trash.empty"] {
            assert!(allowed_method(method));
        }
        Pending::default().deliver(json!({"id":"unknown", "result":true}));
    }
}
