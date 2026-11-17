mod backend;
mod branding;
mod protocol;
mod tps_grid;
mod ui;

use backend::{Backend, Reply, Request};
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
use ui::App;

struct Options {
    backend: Option<Backend>,
    snapshot: Option<PathBuf>,
    about: bool,
    branding_header: bool,
    window_index: usize,
}

fn options() -> Result<Option<Options>, String> {
    let mut args = env::args_os().skip(1);
    let mut python = OsString::from(if cfg!(windows) { "python" } else { "python3" });
    let mut repo = env::current_dir().map_err(|_| "Не удалось определить рабочую папку")?;
    let mut config = None;
    let mut demo = false;
    let mut snapshot = None;
    let mut about = false;
    let mut branding_header = true;
    let mut window_index = 0;
    while let Some(arg) = args.next() {
        match arg.to_str() {
            Some("--help" | "-h") => {
                println!(
                    "omk-tui --repo PATH --python EXECUTABLE --config PATH\n        [--snapshot FILE.svg] [--compact-header] [--about] [--window 5m|15m|1h|3h]\nomk-tui --demo [--snapshot FILE.svg] [--compact-header] [--about] [--window 5m|15m|1h|3h]\n\n← → server / ↑ ↓ operation / 1 players / 2 TPS / 3 save / r refresh / t period / F1 project / q quit\nTPS history: 5m / 15m / 1h / 3h, refresh every 5 seconds.\nRun locally on the owner host (or inside an SSH terminal). See docs/OWNER_TUI.md."
                );
                return Ok(None);
            }
            Some("--demo") => demo = true,
            Some("--about") => about = true,
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
            _ => return Err("Неизвестный аргумент; используйте --help".into()),
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
        about,
        branding_header,
        window_index,
    }))
}

struct Pending {
    cancel: Arc<AtomicBool>,
    receiver: mpsc::Receiver<Result<Reply, String>>,
    handle: Option<thread::JoinHandle<()>>,
    saving: bool,
}
impl Pending {
    fn start(backend: Backend, request: Request) -> Self {
        let saving = matches!(&request, Request::Console { command, .. } if command == "save");
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
            saving,
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
        eprintln!("omk-tui: {error}");
        std::process::exit(1);
    }
}

fn execute() -> Result<(), String> {
    let Some(options) = options()? else {
        return Ok(());
    };
    let mut app = App::new(options.backend.is_none());
    app.about = options.about;
    app.branding_header = options.branding_header;
    app.window_index = options.window_index;
    if app.demo {
        app.accept(protocol::Overview::parse(include_bytes!(
            "../fixtures/demo.json"
        ))?);
        app.accept_history(Some(demo_history(app.window())));
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
    let mut terminal = ratatui::init();
    let result = interactive(&mut terminal, &mut app, options.backend);
    ratatui::restore();
    match result {
        Ok(true) => {
            eprintln!("Сохранение могло выполниться: ответ не подтверждён. Автоповтора нет.");
            Ok(())
        }
        Ok(false) => Ok(()),
        Err(_) => Err("Ошибка терминала; результат незавершённой команды неизвестен".into()),
    }
}

fn interactive(
    terminal: &mut ratatui::DefaultTerminal,
    app: &mut App,
    backend: Option<Backend>,
) -> io::Result<bool> {
    let mut pending = backend
        .as_ref()
        .map(|b| Pending::start(b.clone(), Request::Overview(None, app.window())));
    let mut next_refresh = Instant::now() + Duration::from_secs(5);
    loop {
        app.loading = pending.is_some();
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
                            app.message = "Обзор недоступен. Проверьте private operator config и права.\nr — повторить чтение.".into();
                        }
                        Ok(Reply::Console(v)) => {
                            app.scroll = 0;
                            app.failed = !v.ok;
                            app.message = if v.ok {
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
                        }
                        Err(error) => {
                            app.failed = true;
                            app.message = format!("{error}\n\nАвтоматической отправки команд нет.");
                        }
                    }
                    pending = None;
                    app.loading = false;
                }
                Err(mpsc::TryRecvError::Disconnected) => {
                    app.failed = true;
                    app.message =
                        "Рабочий процесс завершился без ответа. Результат команды неизвестен."
                            .into();
                    pending = None;
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
            if key.code == KeyCode::F(1) && app.confirm.is_none() && app.range_picker.is_none() {
                app.about = !app.about;
                continue;
            }
            if app.about && key.code == KeyCode::Esc {
                app.about = false;
                continue;
            }
            if app.range_picker.is_some() && key.code == KeyCode::Esc {
                app.range_picker = None;
                continue;
            }
            if key.code == KeyCode::Char('c') && key.modifiers.contains(KeyModifiers::CONTROL)
                || app.confirm.is_none() && matches!(key.code, KeyCode::Char('q') | KeyCode::Esc)
            {
                let uncertain = pending.as_ref().is_some_and(|p| p.saving);
                drop(pending.take());
                if uncertain {
                    app.message = "Сохранение могло выполниться: результат неизвестен".into();
                }
                return Ok(uncertain);
            }
            if app.about {
                continue;
            }
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
            } else if let Some(input) = app.confirm.as_mut() {
                match key.code {
                    KeyCode::Esc => app.confirm = None,
                    KeyCode::Backspace => {
                        input.pop();
                    }
                    KeyCode::Char(c) if input.len() < 60 && c.is_ascii() && !c.is_control() => {
                        input.push(c)
                    }
                    KeyCode::Enter => {
                        if app.confirm.as_deref()
                            == app.server().map(|s| format!("SAVE {s}")).as_deref()
                        {
                            request = app.server().map(|s| Request::Console {
                                server: s.into(),
                                command: "save".into(),
                            });
                            app.confirm = None;
                        }
                    }
                    _ => {}
                }
            } else {
                match key.code {
                    KeyCode::Up => app.move_operation(-1),
                    KeyCode::Down => app.move_operation(1),
                    KeyCode::PageUp => app.scroll = app.scroll.saturating_sub(10),
                    KeyCode::PageDown => app.scroll = app.scroll.saturating_add(10).min(8192),
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
                            app.operation.select(None);
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
                    KeyCode::Char(c @ ('1' | '2' | '3')) if pending.is_none() && !app.demo => {
                        if c == '3' {
                            if app.server().is_some() {
                                app.confirm = Some(String::new());
                            }
                        } else {
                            request = app.server().map(|s| Request::Console {
                                server: s.into(),
                                command: if c == '1' { "players" } else { "tps" }.into(),
                            });
                        }
                    }
                    _ => {}
                }
            }
        }
        if pending.is_none()
            && app.confirm.is_none()
            && app.range_picker.is_none()
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
