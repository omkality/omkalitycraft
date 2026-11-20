use crate::protocol::{
    ConsoleResult, InvitationResult, Overview, TpsHistory, TpsWindow, valid_server,
};
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
    Moderation(crate::moderation::Action),
    Invite,
    WorldReset(crate::world_reset::Request),
}
pub enum Reply {
    Overview(Overview, Option<Result<TpsHistory, String>>),
    Console(ConsoleResult),
    Moderation(crate::moderation::Receipt),
    Invitation(InvitationResult),
    WorldReset(crate::world_reset::Receipt),
}

struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[cfg(windows)]
pub fn copy_clipboard(code: &str) -> std::io::Result<bool> {
    use std::{io::Write, os::windows::process::CommandExt};

    let system = std::env::var_os("SystemRoot")
        .map(PathBuf::from)
        .filter(|path| path.is_absolute())
        .ok_or_else(|| std::io::Error::other("Windows system path unavailable"))?;
    let mut child = OwnedChild(
        Command::new(system.join("System32/clip.exe"))
            .creation_flags(0x08000000)
            .stdin(Stdio::piped())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()?,
    );
    child
        .0
        .stdin
        .take()
        .ok_or_else(|| std::io::Error::other("Clipboard input unavailable"))?
        .write_all(code.as_bytes())?;
    let deadline = Instant::now() + Duration::from_secs(2);
    loop {
        if let Some(status) = child.0.try_wait()? {
            return Ok(status.success());
        }
        if Instant::now() >= deadline {
            return Ok(false);
        }
        thread::sleep(Duration::from_millis(20));
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
            return Err("Запрос прерван; результат команды неизвестен".into());
        }
        if Instant::now() >= deadline {
            return Err("CLI не ответил вовремя; результат команды неизвестен".into());
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
            Request::Invite => {
                command.args(["access", "invite", "--show-code"]);
            }
            Request::WorldReset(action) => {
                if !action.valid() {
                    return Err("Неверный запрос вайпа".into());
                }
                command.args([
                    "world-reset",
                    "--server",
                    &action.server,
                    "--command",
                    action.command,
                ]);
                if let Some(confirmation) = &action.confirmation {
                    command.args(["--confirm", confirmation]);
                }
            }
            Request::Moderation(a) => {
                if !valid_server(&a.server)
                    || !matches!(a.command.as_str(), "kick" | "ban" | "mute" | "unban")
                {
                    return Err("Неверная команда модерации".into());
                }
                if a.project() {
                    command.arg("project-moderation");
                } else {
                    command.args(["moderation", "--server", &a.server]);
                }
                command.args([
                    "--command",
                    &a.command,
                    "--player",
                    &a.player,
                    "--duration",
                    &a.duration,
                    "--reason",
                    &a.reason,
                ]);
                if a.command == "ban" {
                    command.arg("--confirm-ban");
                }
            }
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
        let timeout = match &request {
            Request::WorldReset(a) if a.mutating() => 24 * 60 * 60,
            Request::Moderation(_) => 25,
            _ => 15,
        };
        let (bytes, success) = capture(command, &cancel, Duration::from_secs(timeout))?;
        let (reply, ok) = match request {
            Request::Invite => {
                let value = InvitationResult::parse(&bytes)?;
                let ok = value.ok;
                (Reply::Invitation(value), ok)
            }
            Request::WorldReset(action) => {
                let value = crate::world_reset::Receipt::parse(&bytes, &action)?;
                let ok = value.ok;
                (Reply::WorldReset(value), ok)
            }
            Request::Moderation(a) => {
                let value = crate::moderation::Receipt::parse(&bytes, &a)?;
                let ok = value.ok;
                (Reply::Moderation(value), ok)
            }
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
