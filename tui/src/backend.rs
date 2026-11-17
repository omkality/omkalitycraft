use crate::protocol::{ConsoleResult, Overview, TpsHistory, TpsWindow, valid_server};
use std::{
    ffi::OsString,
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, Instant},
};

const MAX_OUTPUT: u64 = 262144;

#[derive(Clone)]
pub struct Backend {
    pub python: OsString,
    pub repo: PathBuf,
    pub config: PathBuf,
}

#[derive(Clone, Debug)]
pub enum Request {
    Overview(Option<String>, TpsWindow),
    Console { server: String, command: String },
}
#[derive(Debug)]
pub enum Reply {
    Overview(Overview, Option<Result<TpsHistory, String>>),
    Console(ConsoleResult),
}

struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

pub fn capture(
    mut command: Command,
    cancel: &AtomicBool,
    timeout: Duration,
) -> Result<(Vec<u8>, bool), String> {
    // A private anonymous file avoids pipe deadlocks and reader threads surviving a timeout.
    let mut output = tempfile::tempfile().map_err(|_| "Не удалось создать буфер ответа")?;
    command
        .stdin(Stdio::null())
        .stdout(Stdio::from(
            output.try_clone().map_err(|_| "Ошибка буфера")?,
        ))
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = OwnedChild(
        command
            .spawn()
            .map_err(|_| "Не удалось запустить Python CLI")?,
    );
    let deadline = Instant::now() + timeout;
    let status = loop {
        if cancel.load(Ordering::Relaxed) {
            return Err("Запрос прерван; результат сохранения неизвестен".into());
        }
        if Instant::now() >= deadline {
            return Err("CLI не ответил вовремя; результат сохранения неизвестен".into());
        }
        if file_size(&output)? > MAX_OUTPUT {
            return Err("Ответ CLI превысил лимит".into());
        }
        if let Some(status) = child
            .0
            .try_wait()
            .map_err(|_| "Не удалось прочитать exit code")?
        {
            break status;
        }
        thread::sleep(Duration::from_millis(20));
    };
    if !matches!(status.code(), Some(0 | 1)) {
        return Err("CLI завершился без контрактного результата".into());
    }
    if file_size(&output)? > MAX_OUTPUT {
        return Err("Ответ CLI превысил лимит".into());
    }
    output
        .seek(SeekFrom::Start(0))
        .map_err(|_| "Ошибка чтения ответа")?;
    let mut bytes = Vec::new();
    output
        .take(MAX_OUTPUT + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Ошибка чтения ответа")?;
    if bytes.len() as u64 > MAX_OUTPUT {
        return Err("Ответ CLI превысил лимит".into());
    }
    Ok((bytes, status.success()))
}

fn file_size(file: &File) -> Result<u64, String> {
    file.metadata()
        .map(|m| m.len())
        .map_err(|_| "Не удалось проверить размер ответа".into())
}

impl Backend {
    fn command(&self) -> Command {
        let mut command = Command::new(&self.python);
        command
            .current_dir(&self.repo)
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .args(["-m", "omk", "admin", "--config"])
            .arg(&self.config);
        command
    }

    fn history(
        &self,
        server: &str,
        window: TpsWindow,
        cancel: &AtomicBool,
    ) -> Result<TpsHistory, String> {
        if cancel.load(Ordering::Relaxed) {
            return Err("Чтение истории отменено".into());
        }
        let mut command = self.command();
        command.args(["tps-history", "--server", server, "--window", window.key]);
        let (bytes, success) = capture(command, cancel, Duration::from_secs(15))?;
        let value = TpsHistory::parse(&bytes, server, window)?;
        if value.ok != success {
            return Err("Exit code истории не совпадает с JSON".into());
        }
        if !value.ok {
            return Err("История TPS недоступна".into());
        }
        Ok(value)
    }

    pub fn request(&self, request: Request, cancel: Arc<AtomicBool>) -> Result<Reply, String> {
        let mut command = self.command();
        match &request {
            Request::Overview(server, _) => {
                command.arg("overview");
                if let Some(server) = server {
                    if !valid_server(server) {
                        return Err("Неверный сервер".into());
                    }
                    command.args(["--server", server]);
                }
            }
            Request::Console {
                server,
                command: action,
            } => {
                if !valid_server(server) || !matches!(action.as_str(), "players" | "tps" | "save") {
                    return Err("Неверная команда".into());
                }
                command.args(["console", "--server", server, "--command", action]);
                if action == "save" {
                    command.arg("--confirm-save");
                }
            }
        }
        let (bytes, success) = capture(command, &cancel, Duration::from_secs(15))?;
        let (reply, ok) = match request {
            Request::Overview(server, window) => {
                let value = Overview::parse(&bytes)?;
                if value.ok && server.is_some() && server != value.selected_server {
                    return Err("Обзор пришёл для другого сервера".into());
                }
                let ok = value.ok;
                let history = if ok && success {
                    value
                        .selected_server
                        .as_deref()
                        .map(|id| self.history(id, window, &cancel))
                } else {
                    None
                };
                (Reply::Overview(value, history), ok)
            }
            Request::Console { server, command } => {
                let value = ConsoleResult::parse(&bytes, &server, &command)?;
                let ok = value.ok;
                (Reply::Console(value), ok)
            }
        };
        if ok != success {
            return Err("Exit code не совпадает с JSON".into());
        }
        Ok(reply)
    }
}
