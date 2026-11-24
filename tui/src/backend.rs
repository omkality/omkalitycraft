use crate::client_reports;
use crate::protocol::{
    ConsoleResult, InvitationEntry, InvitationResult, Overview, PlayerStatsResult, TpsHistory,
    TpsWindow, valid_server,
};
use crate::restrictions;
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
    pub windows_report_dir: Option<PathBuf>,
}

#[derive(Clone, Debug)]
pub enum Request {
    Overview(Option<String>, TpsWindow),
    Console { server: String, command: String },
    PlayerStats { server: String, player: String },
    Restrictions,
    Moderation(crate::moderation::Action, Option<String>),
    Invite,
    WorldReset(crate::world_reset::Request),
    ClientReports,
    ExportClientReport(String),
}
pub enum Reply {
    Overview(Overview, Option<Result<TpsHistory, String>>),
    Console(ConsoleResult),
    PlayerStats(PlayerStatsResult),
    Moderation(crate::moderation::Receipt, Option<ModerationRefresh>),
    Restrictions(restrictions::Snapshot),
    Invitation(InvitationResult),
    WorldReset(crate::world_reset::Receipt),
    ClientReports(client_reports::Listing),
    ClientReportExport(client_reports::Export),
}

pub enum ModerationRefresh {
    Membership(String, String),
    Restrictions(Option<restrictions::Snapshot>),
    Invitations(Option<Vec<InvitationEntry>>),
}

struct OwnedChild(Child);
impl Drop for OwnedChild {
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

#[cfg(windows)]
pub fn copy_clipboard(code: &str, deadline: Instant) -> std::io::Result<bool> {
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
    if Instant::now() >= deadline {
        return Ok(false);
    }
    child
        .0
        .stdin
        .take()
        .ok_or_else(|| std::io::Error::other("Clipboard input unavailable"))?
        .write_all(code.as_bytes())?;
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

#[cfg(not(windows))]
pub fn queue_clipboard(socket: &std::path::Path, code: &str) -> std::io::Result<bool> {
    use std::io::Write;

    if !crate::protocol::valid_invite_code(code) {
        return Ok(false);
    }
    let mut child = OwnedChild(
        Command::new("/usr/bin/tmux")
            .arg("-S")
            .arg(socket)
            .args(["load-buffer", "-b", "omk-invite-clipboard", "-"])
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
    command: Command,
    cancel: &AtomicBool,
    timeout: Duration,
) -> Result<(Vec<u8>, bool), String> {
    capture_limit(command, cancel, timeout, MAX_OUTPUT, None)
}

const PROGRESS_PREFIX: &[u8] = b"OMK_PROGRESS ";

fn forward_progress(
    file: &mut File,
    size: u64,
    cursor: &mut u64,
    report: &dyn Fn(crate::world_reset::Progress),
) -> Result<(), String> {
    if size <= *cursor {
        return Ok(());
    }
    file.seek(SeekFrom::Start(*cursor))
        .map_err(|_| "Ошибка чтения хода вайпа")?;
    let mut chunk = Vec::new();
    file.take(size - *cursor)
        .read_to_end(&mut chunk)
        .map_err(|_| "Ошибка чтения хода вайпа")?;
    for line in chunk.split_inclusive(|b| *b == b'\n') {
        if line.last() != Some(&b'\n') {
            break;
        }
        *cursor += line.len() as u64;
        if let Some(value) = line.strip_prefix(PROGRESS_PREFIX)
            && let Ok(event) = serde_json::from_slice::<crate::world_reset::Progress>(value)
            && event.valid()
        {
            report(event);
        }
    }
    Ok(())
}

fn capture_limit(
    mut command: Command,
    cancel: &AtomicBool,
    timeout: Duration,
    limit: u64,
    report: Option<&dyn Fn(crate::world_reset::Progress)>,
) -> Result<(Vec<u8>, bool), String> {
    // Reopening the private file gives the reader its own cursor while the child writes.
    let channel = tempfile::NamedTempFile::new().map_err(|_| "Не удалось создать буфер ответа")?;
    let mut output = channel.reopen().map_err(|_| "Ошибка буфера")?;
    command
        .stdin(Stdio::null())
        .stdout(Stdio::from(channel.reopen().map_err(|_| "Ошибка буфера")?))
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
    let mut read = 0;
    let status = loop {
        if cancel.load(Ordering::Relaxed) {
            return Err("Запрос прерван; результат команды неизвестен".into());
        }
        if Instant::now() >= deadline {
            return Err("CLI не ответил вовремя; результат команды неизвестен".into());
        }
        let size = file_size(&output)?;
        if size > limit {
            return Err("Ответ CLI превысил лимит".into());
        }
        if let Some(report) = report {
            forward_progress(&mut output, size, &mut read, report)?;
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
    if file_size(&output)? > limit {
        return Err("Ответ CLI превысил лимит".into());
    }
    output
        .seek(SeekFrom::Start(0))
        .map_err(|_| "Ошибка чтения ответа")?;
    let mut bytes = Vec::new();
    output
        .take(limit + 1)
        .read_to_end(&mut bytes)
        .map_err(|_| "Ошибка чтения ответа")?;
    if bytes.len() as u64 > limit {
        return Err("Ответ CLI превысил лимит".into());
    }
    if report.is_some() {
        bytes = bytes
            .split_inclusive(|b| *b == b'\n')
            .filter(|line| !line.starts_with(PROGRESS_PREFIX))
            .flatten()
            .copied()
            .collect();
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
        self.request_reporting(request, cancel, None)
    }

    pub fn request_reporting(
        &self,
        request: Request,
        cancel: Arc<AtomicBool>,
        report: Option<&dyn Fn(crate::world_reset::Progress)>,
    ) -> Result<Reply, String> {
        let mut command = self.command();
        match &request {
            Request::Invite => {
                command.args(["access", "invite", "--show-code"]);
            }
            Request::Restrictions => {
                command.arg("project-restrictions");
            }
            Request::ClientReports | Request::ExportClientReport(_) => {
                command.arg("reports");
                if let Request::ExportClientReport(id) = &request {
                    if !client_reports::valid_id(id) {
                        return Err("Неверный номер краш-отчёта".into());
                    }
                    command.args(["export", "--id", id]);
                } else {
                    command.arg("browse");
                }
                if let Some(directory) = &self.windows_report_dir {
                    command.arg("--windows-relay-dir").arg(directory);
                }
            }
            Request::WorldReset(action) => {
                if !action.valid() {
                    return Err("Неверный запрос вайпа".into());
                }
                command.args([
                    "world-reset",
                    "--catalog",
                    "--server",
                    &action.server,
                    "--command",
                    action.command,
                ]);
                if let Some(world) = action.world {
                    command.args(["--world", &world.to_string()]);
                }
                if let Some(confirmation) = &action.confirmation {
                    command.args(["--confirm", confirmation]);
                }
                if report.is_some() && action.mutating() {
                    command.arg("--stream-progress");
                }
            }
            Request::PlayerStats { server, player } => {
                if !valid_server(server) || !crate::moderation::valid_player(player) {
                    return Err("Неверный запрос статистики игрока".into());
                }
                command.args(["player-stats", "--server", server, "--player", player]);
            }
            Request::Moderation(a, _) => {
                if !valid_server(&a.server)
                    || !matches!(
                        a.command.as_str(),
                        "kick" | "ban" | "mute" | "unban" | "unmute" | "revoke-invite"
                    )
                    || a.profile.as_deref().is_some_and(|profile| {
                        !matches!(a.command.as_str(), "unban" | "unmute")
                            || !restrictions::valid_profile(profile)
                    })
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
                if matches!(a.command.as_str(), "ban" | "revoke-invite") {
                    command.arg("--confirm-ban");
                }
                if let Some(profile) = &a.profile {
                    command.args(["--profile", profile]);
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
                if !valid_server(server)
                    || !matches!(
                        action.as_str(),
                        "players"
                            | "roster"
                            | "permanent-bans"
                            | "invites"
                            | "player-names"
                            | "tps"
                            | "save"
                            | "backup-status"
                    )
                {
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
            Request::Moderation(action, _) if action.permanent_ban() => 120,
            Request::Moderation(..) => 25,
            Request::PlayerStats { .. } => 300,
            _ => 15,
        };
        let timeout = Duration::from_secs(timeout);
        let (bytes, success) = if matches!(&request, Request::Restrictions) {
            capture_limit(command, &cancel, timeout, 512 * 1024, None)?
        } else {
            capture_limit(command, &cancel, timeout, MAX_OUTPUT, report)?
        };
        let (reply, ok) = match request {
            Request::ClientReports => {
                let value = client_reports::Listing::parse(&bytes)?;
                let ok = value.ok;
                (Reply::ClientReports(value), ok)
            }
            Request::ExportClientReport(id) => {
                let value =
                    client_reports::Export::parse(&bytes, &id, self.windows_report_dir.is_some())?;
                let ok = value.ok;
                (Reply::ClientReportExport(value), ok)
            }
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
            Request::Moderation(a, section) => {
                let value = crate::moderation::Receipt::parse(&bytes, &a)?;
                let ok = value.ok;
                let refresh =
                    section.filter(|_| ok == success && (ok || value.effect == "unknown"));
                let page = refresh.map(|command| {
                    if command == "restrictions" {
                        let snapshot = match self.request(Request::Restrictions, cancel) {
                            Ok(Reply::Restrictions(snapshot)) => Some(snapshot),
                            _ => None,
                        };
                        return ModerationRefresh::Restrictions(snapshot);
                    }
                    let reply = self.request(
                        Request::Console {
                            server: a.server,
                            command: command.clone(),
                        },
                        cancel,
                    );
                    if command == "invites" {
                        return ModerationRefresh::Invitations(match reply {
                            Ok(Reply::Console(list)) => list.invitations,
                            _ => None,
                        });
                    }
                    let message = match reply {
                        Ok(Reply::Console(list)) => list.membership_message(),
                        _ => None,
                    }
                    .unwrap_or_else(|| {
                        "Список не обновился. Нажмите 1 или 4, чтобы перечитать его.".into()
                    });
                    ModerationRefresh::Membership(command, message)
                });
                (Reply::Moderation(value, page), ok)
            }
            Request::Restrictions => {
                let value = restrictions::Snapshot::parse(&bytes)?;
                let ok = value.ok;
                (Reply::Restrictions(value), ok)
            }
            Request::PlayerStats { server, player } => {
                let value = PlayerStatsResult::parse(&bytes, &server, &player)?;
                let ok = value.ok;
                (Reply::PlayerStats(value), ok)
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
