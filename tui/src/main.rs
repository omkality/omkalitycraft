mod backend;
mod branding;
mod moderation;
mod protocol;
mod restrictions;
mod startup;
mod tps_grid;
mod ui;
mod wipe_report;
mod world_reset;

use backend::{Backend, ModerationRefresh, Reply, Request};
use ratatui::{
    Terminal,
    backend::TestBackend,
    crossterm::event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
};
use std::{
    env,
    ffi::OsString,
    io,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};
use ui::{App, Confirmation};

struct Options {
    backend: Option<Backend>,
    snapshot: Option<PathBuf>,
    branding_header: bool,
    window_index: usize,
    reports: wipe_report::Destination,
}

fn options() -> Result<Option<Options>, String> {
    let mut args = env::args_os().skip(1);
    let sidecar = startup::defaults()?;
    let mut python = sidecar
        .as_ref()
        .map(|v| v.python.clone().into_os_string())
        .unwrap_or_else(|| OsString::from(if cfg!(windows) { "python" } else { "python3" }));
    let mut repo = sidecar
        .as_ref()
        .map(|v| v.repo.clone())
        .unwrap_or(env::current_dir().map_err(|_| "Не удалось определить рабочую папку")?);
    let mut config = sidecar.map(|v| v.config);
    let mut demo = false;
    let mut snapshot = None;
    let mut branding_header = true;
    let mut window_index = 0;
    let mut export_dir = None;
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--help" | "-h") => {
                println!(
                    "omk-tui --repo PATH --python EXECUTABLE --config PATH\n        [--snapshot FILE.svg] [--compact-header] [--window 5m|15m|1h|3h]\nomk-tui --demo [--snapshot FILE.svg] [--compact-header] [--window 5m|15m|1h|3h]\n\n← → server / 1 players / 2 TPS / 3 save / 4 restrictions / k kick / b ban / m mute / u unban / n unmute / s statistics / i invite / r refresh / t period\nEsc goes back; from the main menu it asks before closing.\nTPS history: 5m / 15m / 1h / 3h, refresh every 5 seconds.\nRun locally on the owner host (or inside an SSH terminal). See docs/OWNER_TUI.md."
                );
                return Ok(None);
            }
            Some("--demo") => demo = true,
            Some("--branding-header") => branding_header = true,
            Some("--compact-header") => branding_header = false,
            Some("--window") => {
                let key = args.next().ok_or("--window требует 5m, 15m, 1h или 3h")?;
                window_index = protocol::TPS_WINDOWS
                    .iter()
                    .position(|w| Some(w.key) == key.to_str())
                    .ok_or("--window требует 5m, 15m, 1h или 3h")?;
            }
            Some("--python") => python = args.next().ok_or("--python требует путь")?,
            Some("--repo") => repo = PathBuf::from(args.next().ok_or("--repo требует путь")?),
            Some("--config") => {
                config = Some(PathBuf::from(args.next().ok_or("--config требует путь")?))
            }
            Some("--snapshot") => {
                snapshot = Some(PathBuf::from(args.next().ok_or("--snapshot требует путь")?))
            }
            Some("--windows-report-dir") => {
                let path = PathBuf::from(args.next().ok_or("--windows-report-dir требует путь")?);
                if !path.is_absolute() {
                    return Err("--windows-report-dir требует абсолютный путь".into());
                }
                export_dir = Some(path);
            }
            _ => return Err("Неизвестный аргумент; используйте --help".into()),
        }
    }
    if env::args_os().len() == 1 && config.is_none() {
        use std::io::IsTerminal;
        if io::stdin().is_terminal() && io::stdout().is_terminal() {
            demo = true;
        }
    }
    if demo && config.is_some() {
        return Err("--demo и --config несовместимы".into());
    }
    Ok(Some(Options {
        backend: if demo {
            None
        } else {
            Some(Backend {
                python,
                repo,
                config: config.ok_or("Укажите --config или --demo")?,
            })
        },
        snapshot,
        branding_header,
        window_index,
        reports: wipe_report::Destination { export_dir },
    }))
}

struct Pending {
    cancel: Arc<AtomicBool>,
    receiver: mpsc::Receiver<Result<Reply, String>>,
    handle: Option<thread::JoinHandle<()>>,
    mutating: bool,
    reset_step: Option<&'static str>,
    player_stats: bool,
    overview: bool,
}
impl Pending {
    fn start(backend: Backend, request: Request) -> Self {
        let reset_step = match &request {
            Request::WorldReset(action) => Some(action.command),
            _ => None,
        };
        let player_stats = matches!(&request, Request::PlayerStats { .. });
        let overview = matches!(&request, Request::Overview(..));
        let mutating = matches!(&request, Request::WorldReset(a) if a.mutating())
            || matches!(&request, Request::Console { command, .. } if command == "save")
            || matches!(&request, Request::Moderation(..) | Request::Invite);
        let cancel = Arc::new(AtomicBool::new(false));
        let c = cancel.clone();
        let (sender, receiver) = mpsc::channel();
        let handle = thread::spawn(move || {
            let _ = sender.send(backend.request(request, c));
        });
        Self {
            cancel,
            receiver,
            handle: Some(handle),
            mutating,
            reset_step,
            player_stats,
            overview,
        }
    }
}
impl Drop for Pending {
    fn drop(&mut self) {
        self.cancel.store(true, Ordering::Relaxed);
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
    }
}

fn main() {
    if let Err(error) = execute() {
        eprintln!(
            "omk-tui: {error}\nЗапуск: omk-tui --demo или omk-tui --repo PATH --python EXE --config PATH."
        );
        startup::pause_on_double_click();
        std::process::exit(1);
    }
}

fn execute() -> Result<(), String> {
    let Some(options) = options()? else {
        return Ok(());
    };
    let mut app = App::new(options.backend.is_none());
    app.branding_header = options.branding_header;
    app.window_index = options.window_index;
    if app.demo {
        app.accept(protocol::Overview::parse(include_bytes!(
            "../fixtures/demo.json"
        ))?);
        app.accept_history(Some(demo_history(app.window())));
    }
    if app.demo && env::args_os().len() == 1 {
        app.set_menu_message("Демо: подключение к серверу не настроено.\nДля подключения укажите --repo, --python и --config.\nКоманды в демо отключены.".into());
    }
    if let Some(path) = options.snapshot {
        if let Some(backend) = options.backend {
            match backend.request(
                Request::Overview(None, app.window()),
                Arc::new(AtomicBool::new(false)),
            )? {
                Reply::Overview(v, history) if v.ok => {
                    app.accept(v);
                    app.accept_history(history);
                }
                _ => return Err("Backend не вернул рабочий обзор".into()),
            }
        }
        return snapshot(&mut app, path);
    }
    #[cfg(windows)]
    startup::widen_standalone_console();
    let mut terminal = ratatui::init();
    let result = interactive(&mut terminal, &mut app, options.backend, &options.reports);
    ratatui::restore();
    result.map_err(|_| "Ошибка терминала; результат незавершённой команды неизвестен".into())
}

const COPY_FAILED: &str = "Не удалось скопировать. Код можно выделить вручную.";

#[cfg(windows)]
const COPY_PENDING: &str = "Копирование в буфер…";

#[cfg(windows)]
struct ClipboardCopy {
    receiver: mpsc::Receiver<bool>,
    deadline: Instant,
}

#[cfg(windows)]
impl ClipboardCopy {
    fn start(code: String) -> Self {
        let (sender, receiver) = mpsc::channel();
        let deadline = Instant::now() + Duration::from_secs(2);
        let _ = thread::Builder::new().spawn(move || {
            let copied = backend::copy_clipboard(&code, deadline).unwrap_or(false);
            let _ = sender.send(copied);
        });
        Self { receiver, deadline }
    }

    fn status(&self) -> Option<&'static str> {
        match self.receiver.try_recv() {
            Ok(true) => Some("Скопировано в буфер обмена."),
            Err(mpsc::TryRecvError::Empty) if Instant::now() < self.deadline => None,
            _ => Some(COPY_FAILED),
        }
    }
}

fn interactive(
    terminal: &mut ratatui::DefaultTerminal,
    app: &mut App,
    backend: Option<Backend>,
    reports: &wipe_report::Destination,
) -> io::Result<()> {
    let mut pending = backend
        .as_ref()
        .map(|b| Pending::start(b.clone(), Request::Overview(None, app.window())));
    let mut name_lookup: Option<Pending> = None;
    let mut next_refresh = Instant::now() + Duration::from_secs(5);
    #[cfg(windows)]
    let mut clipboard_copy: Option<ClipboardCopy> = None;
    loop {
        if let Some(lookup) = &name_lookup {
            let names = match lookup.receiver.try_recv() {
                Ok(Ok(Reply::Console(v))) => Some(v.player_names()),
                Err(mpsc::TryRecvError::Empty) => None,
                _ => Some(None),
            };
            if let Some(names) = names {
                if let Some(form) = &mut app.moderation {
                    form.finish_name_lookup(names);
                }
                name_lookup = None;
            }
        }
        #[cfg(windows)]
        if let Some(status) = clipboard_copy.as_ref().and_then(ClipboardCopy::status) {
            let page = app.command_page_mut();
            page.message = page.message.replacen(COPY_PENDING, status, 1);
            clipboard_copy = None;
        }
        #[cfg(windows)]
        let copying = clipboard_copy.is_some();
        #[cfg(not(windows))]
        let copying = false;
        app.loading = pending.is_some() || name_lookup.is_some() || copying;
        app.resetting = pending
            .as_ref()
            .and_then(|work| work.reset_step)
            .filter(|step| *step != "inspect");
        if let Some(work) = &pending {
            match work.receiver.try_recv() {
                Ok(result) => {
                    match result {
                        Ok(Reply::Overview(v, history)) if v.ok => {
                            app.accept(v);
                            app.accept_history(history);
                        }
                        Ok(Reply::Overview(_, _)) => {
                            app.failed = true;
                            app.set_menu_message("Обзор недоступен. Проверьте настройки админки и права.\nr — повторить чтение.".into());
                        }
                        Ok(Reply::Moderation(v, section)) => {
                            match section {
                                Some(ModerationRefresh::Membership(command, message)) => {
                                    app.refresh_section(&command, message);
                                }
                                Some(ModerationRefresh::Restrictions(snapshot)) => {
                                    app.show_restrictions(snapshot);
                                }
                                None => {}
                            }
                            app.failed = !v.ok;
                            app.show_detail(v.message());
                        }
                        Ok(Reply::Restrictions(snapshot)) => {
                            app.failed = !snapshot.ok;
                            app.show_restrictions(Some(snapshot));
                        }
                        Ok(Reply::PlayerStats(v)) => {
                            let ok = v.ok;
                            let message = v.message();
                            app.finish_player_stats(
                                if ok { Ok(message) } else { Err(message) },
                                Instant::now(),
                            );
                        }
                        Ok(Reply::Invitation(v)) => {
                            app.failed = !v.ok;
                            #[cfg(windows)]
                            {
                                app.show_detail(v.message(v.code().map(|_| COPY_PENDING)));
                                clipboard_copy =
                                    v.code().map(|code| ClipboardCopy::start(code.to_owned()));
                            }
                            #[cfg(not(windows))]
                            {
                                let status = v.code().map(clipboard_status);
                                app.show_detail(v.message(status));
                            }
                        }
                        Ok(Reply::WorldReset(v)) => {
                            app.failed = !v.ok;
                            let report = (!v.ok).then(|| reports.save(&v.report()));
                            let form = world_reset::Form::new(v);
                            app.world_reset = Some(if let Some(report) = report {
                                form.with_report(report)
                            } else {
                                form
                            });
                        }
                        Ok(Reply::Console(v)) if v.ok && v.command == "tps" => {
                            app.failed = false;
                            app.show_forge_tps(&v.server_id, &v.output);
                        }
                        Ok(Reply::Console(v)) => {
                            app.failed = !v.ok;
                            let message = if let Some(list) = v.membership_message() {
                                list
                            } else if v.ok && v.command == "invites" {
                                format!("Активные приглашения\n\n{}\n\no — отозвать", v.output)
                            } else if v.ok {
                                format!(
                                    "Сервер: {}\nКоманда: {}\n\nОтвет сервера:\n{}{}",
                                    v.server_id,
                                    v.command,
                                    v.output,
                                    if v.command == "save" {
                                        "\n\nОтвет не является проверкой резервной копии."
                                    } else {
                                        ""
                                    }
                                )
                            } else {
                                format!(
                                    "Команда {} не подтверждена.\nПроверьте конфигурацию RCON и сервер.\n{}",
                                    v.command,
                                    if v.effect == "unknown" {
                                        "Сохранение могло выполниться. Автоповтора нет."
                                    } else {
                                        "Изменений команда не запрашивала."
                                    }
                                )
                            };
                            if v.command == "save" {
                                app.show_detail(message);
                            } else {
                                app.show_section(v.command, message);
                            }
                        }
                        Err(_) if work.player_stats => {
                            app.finish_player_stats(
                                Err("Не удалось загрузить статистику.".into()),
                                Instant::now(),
                            );
                        }
                        Err(error) => {
                            app.failed = true;
                            let message = request_error(&error, work, reports);
                            if work.overview {
                                app.set_menu_message(message);
                            } else {
                                app.show_detail(message);
                            }
                        }
                    }
                    pending = None;
                    app.loading = false;
                    app.resetting = None;
                }
                Err(mpsc::TryRecvError::Disconnected) if work.player_stats => {
                    app.finish_player_stats(
                        Err("Не удалось загрузить статистику.".into()),
                        Instant::now(),
                    );
                    pending = None;
                    app.loading = false;
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    app.failed = true;
                    let message = request_error(
                        "Рабочий процесс завершился без ответа. Результат команды неизвестен.",
                        work,
                        reports,
                    );
                    if work.overview {
                        app.set_menu_message(message);
                    } else {
                        app.show_detail(message);
                    }
                    pending = None;
                    app.loading = false;
                    app.resetting = None;
                }
                Err(mpsc::TryRecvError::Empty) => {}
            }
        }
        terminal.draw(|f| ui::draw(f, app))?;
        let mut request = None;
        if event::poll(Duration::from_millis(100))?
            && let Event::Key(key) = event::read()?
        {
            if key.kind != KeyEventKind::Press {
                continue;
            }
            if key.code == KeyCode::Esc {
                if app.dismiss_dialog() {
                    if app.moderation.is_none() {
                        name_lookup = None;
                    }
                    continue;
                }
                if pending.as_ref().is_some_and(|work| work.mutating) {
                    continue;
                }
                if pending.as_ref().is_some_and(|work| !work.overview) {
                    drop(pending.take());
                } else {
                    app.back_or_confirm_exit();
                }
                continue;
            }
            if key.modifiers.contains(KeyModifiers::CONTROL) {
                continue;
            }
            if pending
                .as_ref()
                .is_some_and(|work| work.reset_step.is_some())
            {
                continue;
            }
            if let Some(form) = &mut app.world_reset {
                if let Some(action) = form.key(key.code) {
                    app.world_reset = None;
                    request = Some(Request::WorldReset(action));
                }
                if let (Some(b), Some(request)) = (&backend, request) {
                    drop(pending.take());
                    pending = Some(Pending::start(b.clone(), request));
                    next_refresh = Instant::now() + Duration::from_secs(5);
                }
                continue;
            }
            if let Some(form) = &mut app.moderation {
                if let Some(a) = form.key(key.code) {
                    name_lookup = None;
                    if let Some(b) = &backend {
                        drop(pending.take());
                        let request = if a.command == "stats" {
                            app.clear_stats_error();
                            Request::PlayerStats {
                                server: a.server,
                                player: a.player,
                            }
                        } else {
                            app.failed = false;
                            app.show_detail(format!(
                                "Отправка: {} · {} · {}",
                                a.scope(),
                                a.command,
                                a.player
                            ));
                            let refresh = if app.restrictions.is_some() {
                                Some("restrictions".into())
                            } else if a.permanent_ban() || a.command == "unban" {
                                app.membership_section().map(str::to_owned)
                            } else {
                                None
                            };
                            Request::Moderation(a, refresh)
                        };
                        pending = Some(Pending::start(b.clone(), request));
                        next_refresh = Instant::now() + Duration::from_secs(5);
                    }
                    app.moderation = None;
                }
                continue;
            }
            let shortcut = shortcut_key(key.code);
            if let Some(selected) = app.range_picker {
                match key.code {
                    KeyCode::Up => app.range_picker = Some(selected.saturating_sub(1)),
                    KeyCode::Down => {
                        app.range_picker = Some((selected + 1).min(protocol::TPS_WINDOWS.len() - 1))
                    }
                    KeyCode::Enter => {
                        app.window_index = selected;
                        app.range_picker = None;
                        app.history = None;
                        app.history_failed = false;
                        if app.demo {
                            app.accept_history(Some(demo_history(app.window())));
                        } else {
                            request = Some(Request::Overview(
                                app.server().map(str::to_owned),
                                app.window(),
                            ));
                        }
                    }
                    _ => {}
                }
            } else if let Some(
                Confirmation::Invitation { approved } | Confirmation::Exit { approved },
            ) = app.confirm.as_mut()
            {
                match key.code {
                    KeyCode::Left => *approved = false,
                    KeyCode::Right => *approved = true,
                    KeyCode::Tab => *approved = !*approved,
                    KeyCode::Enter => {
                        let approved = *approved;
                        let confirmation = app.confirm.take();
                        if approved && matches!(confirmation, Some(Confirmation::Exit { .. })) {
                            return Ok(());
                        }
                        if approved {
                            drop(pending.take());
                            app.failed = false;
                            app.show_detail("Создаётся приглашение…".into());
                            request = Some(Request::Invite);
                        }
                    }
                    _ => {}
                }
            } else if let Some(Confirmation::Save(input)) = app.confirm.as_mut() {
                match key.code {
                    KeyCode::Backspace => {
                        input.pop();
                    }
                    KeyCode::Char(c) if input.len() < 60 && c.is_ascii() && !c.is_control() => {
                        input.push(c)
                    }
                    KeyCode::Enter => {
                        let input = input.clone();
                        if app.server().is_some_and(|s| input == format!("SAVE {s}")) {
                            request = app.server().map(|s| Request::Console {
                                server: s.into(),
                                command: "save".into(),
                            });
                            app.confirm = None;
                        }
                    }
                    _ => {}
                }
            } else if let Some(panel) = app.restrictions_panel() {
                let idle = pending.as_ref().is_none_or(|work| work.overview);
                match panel.key(key.code, shortcut, idle) {
                    Some(restrictions::Input::Refresh) => {
                        drop(pending.take());
                        request = Some(Request::Restrictions);
                    }
                    Some(restrictions::Input::Restore {
                        command,
                        player,
                        profile,
                    }) => {
                        app.moderation = app.server().map(|server| {
                            moderation::Form::for_profile(server.into(), command, player, profile)
                        });
                    }
                    None => {}
                }
            } else {
                #[cfg(windows)]
                let clipboard_idle = clipboard_copy.is_none();
                #[cfg(not(windows))]
                let clipboard_idle = true;
                match shortcut {
                    KeyCode::Char('i')
                        if clipboard_idle
                            && pending.as_ref().is_none_or(|work| !work.mutating)
                            && !app.demo =>
                    {
                        app.confirm = Some(Confirmation::Invitation { approved: false });
                    }
                    KeyCode::Char('w')
                        if pending.as_ref().is_none_or(|work| !work.mutating) && !app.demo =>
                    {
                        if let (Some(b), Some(server)) = (&backend, app.server()) {
                            drop(pending.take());
                            pending = Some(Pending::start(
                                b.clone(),
                                Request::WorldReset(world_reset::Request::inspect(
                                    server.to_owned(),
                                )),
                            ));
                            next_refresh = Instant::now() + Duration::from_secs(5);
                        }
                    }
                    KeyCode::Char(c @ ('k' | 'b' | 'm' | 'u' | 'n' | 'o' | 's'))
                        if pending.as_ref().is_none_or(|work| !work.mutating) && !app.demo =>
                    {
                        app.moderation = app.server().map(|s| {
                            moderation::Form::new(
                                s.into(),
                                match c {
                                    'k' => "kick",
                                    'b' => "ban",
                                    'u' => "unban",
                                    'n' => "unmute",
                                    'o' => "revoke-invite",
                                    's' => "stats",
                                    _ => "mute",
                                },
                            )
                        });
                        if c != 'o'
                            && let (Some(b), Some(form)) = (&backend, &mut app.moderation)
                        {
                            form.start_name_lookup();
                            name_lookup = Some(Pending::start(
                                b.clone(),
                                Request::Console {
                                    server: form.action.server.clone(),
                                    command: "player-names".into(),
                                },
                            ));
                        }
                    }
                    KeyCode::PageUp => {
                        let page = app.command_page_mut();
                        page.scroll = page.scroll.saturating_sub(10);
                    }
                    KeyCode::PageDown => {
                        let page = app.command_page_mut();
                        page.scroll = page.scroll.saturating_add(10).min(8192);
                    }
                    KeyCode::Char('t') if pending.is_none() => {
                        app.range_picker = Some(app.window_index);
                    }
                    KeyCode::Left | KeyCode::Right if pending.is_none() => {
                        let len = app.overview.as_ref().map_or(0, |v| v.server_ids.len());
                        if len > 0 {
                            app.selected_server = (app.selected_server
                                + if key.code == KeyCode::Right {
                                    1
                                } else {
                                    len - 1
                                })
                                % len;
                            request = Some(Request::Overview(
                                app.server().map(str::to_owned),
                                app.window(),
                            ));
                        }
                    }
                    KeyCode::Char('r') => {
                        request = Some(Request::Overview(
                            app.server().map(str::to_owned),
                            app.window(),
                        ))
                    }
                    KeyCode::Char(c @ ('1' | '2' | '3' | '4' | 'l'))
                        if pending.is_none() && !app.demo =>
                    {
                        if c == '3' {
                            if app.server().is_some() {
                                app.confirm = Some(Confirmation::Save(String::new()));
                            }
                        } else if c == '4' {
                            request = Some(Request::Restrictions);
                        } else {
                            request = app.server().map(|s| Request::Console {
                                server: s.into(),
                                command: match c {
                                    '1' => "roster",
                                    'l' => "invites",
                                    _ => "tps",
                                }
                                .into(),
                            });
                        }
                    }
                    _ => {}
                }
            }
        }
        if request.is_none()
            && pending.is_none()
            && app.confirm.is_none()
            && app.range_picker.is_none()
            && app.moderation.is_none()
            && app.world_reset.is_none()
            && Instant::now() >= next_refresh
        {
            request = Some(Request::Overview(
                app.server().map(str::to_owned),
                app.window(),
            ));
        }
        if pending.is_none()
            && let (Some(b), Some(request)) = (&backend, request)
        {
            next_refresh = Instant::now() + Duration::from_secs(5);
            pending = Some(Pending::start(b.clone(), request));
            app.loading = true;
        }
    }
}

fn request_error(error: &str, work: &Pending, reports: &wipe_report::Destination) -> String {
    if let Some(step) = work.reset_step {
        let path = reports.save(&format!("Step: {step}\n{error}"));
        format!("{error}\n\n{path}")
    } else {
        error.to_owned()
    }
}

#[cfg(not(windows))]
fn clipboard_status(code: &str) -> &'static str {
    if crossterm::execute!(
        io::stdout(),
        crossterm::clipboard::CopyToClipboard::to_clipboard_from(code),
    )
    .is_ok()
    {
        return "Запрос копирования отправлен терминалу.";
    }
    COPY_FAILED
}

fn demo_history(window: protocol::TpsWindow) -> Result<protocol::TpsHistory, String> {
    let mut value: serde_json::Value =
        serde_json::from_slice(include_bytes!("../fixtures/tps-history.json"))
            .map_err(|_| "Неверные демо-данные")?;
    value["end"] = window.seconds.into();
    value["step"] = window.step.into();
    for (i, point) in value["points"]
        .as_array_mut()
        .ok_or("Нет демо-точек")?
        .iter_mut()
        .enumerate()
    {
        point["timestamp"] = (i as u64 * u64::from(window.step)).into();
    }
    protocol::TpsHistory::parse(
        &serde_json::to_vec(&value).map_err(|_| "Ошибка демо JSON")?,
        "dj2",
        window,
    )
}

// Treat Russian keyboard positions as shortcuts only. Text fields keep the typed character.
fn shortcut_key(code: KeyCode) -> KeyCode {
    let KeyCode::Char(character) = code else {
        return code;
    };
    let character = character.to_lowercase().next().unwrap_or(character);
    let mapped = match character {
        'ц' => 'w',
        'к' => 'r',
        'е' => 't',
        'ш' => 'i',
        'л' => 'k',
        'и' => 'b',
        'ь' => 'm',
        'г' => 'u',
        'т' => 'n',
        'а' => 'f',
        'д' => 'l',
        'щ' => 'o',
        'ы' => 's',
        _ => character,
    };
    KeyCode::Char(mapped)
}

fn snapshot(app: &mut App, path: PathBuf) -> Result<(), String> {
    let mut terminal =
        Terminal::new(TestBackend::new(120, 38)).map_err(|_| "Ошибка test backend")?;
    terminal
        .draw(|f| ui::draw(f, app))
        .map_err(|_| "Ошибка отрисовки")?;
    let buffer = terminal.backend().buffer();
    let mut svg = String::from(
        "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1440\" height=\"912\" viewBox=\"0 0 1440 912\"><rect width=\"1440\" height=\"912\" fill=\"#0c1015\"/><g font-family=\"DejaVu Sans Mono,Consolas,monospace\" font-size=\"19\">",
    );
    for y in 0..38 {
        for x in 0..120 {
            let cell = &buffer[(x, y)];
            let bg = color(cell.bg, "#0c1015");
            let fg = color(cell.fg, "#dae2eb");
            if cell.symbol() == "▀" {
                // Block cells have exact half-row geometry; text fonts can add seams.
                svg.push_str(&format!("<rect x=\"{}\" y=\"{}\" width=\"12\" height=\"24\" fill=\"{}\"/><rect data-cell=\"upper-half\" x=\"{}\" y=\"{}\" width=\"12\" height=\"12\" fill=\"{}\"/>", x*12, y*24, bg, x*12, y*24, fg));
                continue;
            }
            let text = cell
                .symbol()
                .replace('&', "&amp;")
                .replace('<', "&lt;")
                .replace('>', "&gt;");
            svg.push_str(&format!("<rect x=\"{}\" y=\"{}\" width=\"12\" height=\"24\" fill=\"{}\"/><text x=\"{}\" y=\"{}\" fill=\"{}\">{}</text>", x*12, y*24, bg, x*12, y*24+19, fg, text));
        }
    }
    svg.push_str("</g></svg>");
    std::fs::write(path, svg).map_err(|_| "Не удалось сохранить SVG".into())
}

fn color(c: ratatui::style::Color, fallback: &str) -> String {
    match c {
        ratatui::style::Color::Rgb(r, g, b) => format!("#{r:02x}{g:02x}{b:02x}"),
        _ => fallback.into(),
    }
}

#[cfg(test)]
mod tests;
