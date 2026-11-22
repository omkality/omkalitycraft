use crate::protocol::{Overview, TPS_WINDOWS, TpsHistory, TpsWindow};
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};
use std::time::{Duration, Instant};

pub const BG: Color = Color::Rgb(12, 16, 21);
const PANEL: Color = Color::Rgb(18, 24, 31);
const TEXT: Color = Color::Rgb(218, 226, 235);
const MUTED: Color = Color::Rgb(139, 155, 172);
const ACCENT: Color = Color::Rgb(114, 205, 220);
const WARN: Color = Color::Rgb(237, 184, 104);
const ERROR: Color = Color::Rgb(235, 114, 119);
const STATS_ERROR_DURATION: Duration = Duration::from_secs(5);
const MAIN_MENU: &str = "1  Игроки проекта\n2  Forge TPS по измерениям\n3  Сохранение мира (с подтверждением)\n4  Ограничения игроков\n\nk  Кик   b  Бан   m  Выдать мут\ns  Статистика игрока\nl  Список приглашений · o отозвать\nw  Вайп миров\n\nPgUp/PgDn — прокрутка ответа.";

pub enum Confirmation {
    Save(String),
    Invitation { approved: bool },
    Exit { approved: bool },
}

pub struct CommandPage {
    pub message: String,
    pub scroll: u16,
    forge_tps: Option<Vec<Line<'static>>>,
}

impl CommandPage {
    fn new(message: String) -> Self {
        Self {
            message,
            scroll: 0,
            forge_tps: None,
        }
    }
}

pub struct App {
    pub overview: Option<Overview>,
    pub selected_server: usize,
    menu: CommandPage,
    section: Option<(String, CommandPage)>,
    detail: Option<CommandPage>,
    pub loading: bool,
    pub activity: Option<&'static str>,
    pub failed: bool,
    pub refreshed: Option<Instant>,
    pub demo: bool,
    pub confirm: Option<Confirmation>,
    pub moderation: Option<crate::moderation::Form>,
    pub restrictions: Option<crate::restrictions::Panel>,
    pub world_reset: Option<crate::world_reset::Form>,
    pub resetting: Option<&'static str>,
    pub reset_progress: Option<crate::world_reset::Progress>,
    animation_start: Instant,
    pub history: Option<TpsHistory>,
    pub history_failed: bool,
    pub branding_header: bool,
    pub window_index: usize,
    pub range_picker: Option<usize>,
    stats_error: Option<(String, Instant)>,
}

impl App {
    pub fn new(demo: bool) -> Self {
        Self {
            overview: None,
            selected_server: 0,
            menu: CommandPage::new(MAIN_MENU.into()),
            section: None,
            detail: None,
            loading: false,
            activity: None,
            failed: false,
            refreshed: None,
            demo,
            confirm: None,
            moderation: None,
            restrictions: None,
            world_reset: None,
            resetting: None,
            reset_progress: None,
            animation_start: Instant::now(),
            history: None,
            history_failed: false,
            branding_header: false,
            window_index: 0,
            range_picker: None,
            stats_error: None,
        }
    }

    pub fn set_menu_message(&mut self, message: String) {
        self.menu = CommandPage::new(message);
    }

    pub fn show_section(&mut self, command: String, message: String) {
        self.section = Some((command, CommandPage::new(message)));
        self.restrictions = None;
        self.detail = None;
        self.clear_stats_error();
    }

    pub fn show_restrictions(&mut self, snapshot: Option<crate::restrictions::Snapshot>) {
        self.section = None;
        self.detail = None;
        self.clear_stats_error();
        self.restrictions.get_or_insert_default().update(snapshot);
    }

    pub fn restrictions_panel(&mut self) -> Option<&mut crate::restrictions::Panel> {
        if self.detail.is_some() {
            None
        } else {
            self.restrictions.as_mut()
        }
    }

    pub fn show_forge_tps(&mut self, server: &str, output: &str) {
        self.show_section("tps".into(), format!("Forge TPS · {server}\n\n{output}"));
        self.command_page_mut().forge_tps = forge_tps_lines(server, output);
    }

    fn spinner(&self) -> char {
        const FRAMES: [char; 4] = ['|', '/', '-', '\\'];
        let frame = (self.animation_start.elapsed().as_millis() / 100) % FRAMES.len() as u128;
        FRAMES[frame as usize]
    }

    pub fn membership_section(&self) -> Option<&str> {
        let (command, _) = self.section.as_ref()?;
        matches!(command.as_str(), "roster" | "permanent-bans").then_some(command)
    }

    pub fn refresh_section(&mut self, command: &str, message: String) {
        if let Some((current, page)) = &mut self.section
            && current == command
        {
            page.scroll = page
                .scroll
                .min(message.lines().count().saturating_sub(1) as u16);
            page.message = message;
        }
    }

    pub fn show_detail(&mut self, message: String) {
        self.detail = Some(CommandPage::new(message));
        self.clear_stats_error();
    }

    pub fn command_page(&self) -> &CommandPage {
        self.detail
            .as_ref()
            .or(self.section.as_ref().map(|(_, page)| page))
            .unwrap_or(&self.menu)
    }

    pub fn command_page_mut(&mut self) -> &mut CommandPage {
        self.detail
            .as_mut()
            .or(self.section.as_mut().map(|(_, page)| page))
            .unwrap_or(&mut self.menu)
    }

    pub fn dismiss_dialog(&mut self) -> bool {
        if let Some(form) = &mut self.world_reset {
            if !form.dismiss_confirmation() {
                self.world_reset = None;
            }
            return true;
        }
        if let Some(form) = &mut self.moderation {
            if !form.dismiss_confirmation() {
                self.moderation = None;
            }
            return true;
        }
        self.confirm.take().is_some()
            || self.range_picker.take().is_some()
            || self
                .restrictions_panel()
                .is_some_and(crate::restrictions::Panel::cancel_search)
    }

    pub fn back_or_confirm_exit(&mut self) {
        self.clear_stats_error();
        if self.detail.take().is_none()
            && self.section.take().is_none()
            && self.restrictions.take().is_none()
        {
            self.confirm = Some(Confirmation::Exit { approved: false });
        }
    }

    fn at_menu(&self) -> bool {
        self.section.is_none()
            && self.restrictions.is_none()
            && self.detail.is_none()
            && self.confirm.is_none()
            && self.range_picker.is_none()
            && self.moderation.is_none()
            && self.world_reset.is_none()
    }

    pub fn server(&self) -> Option<&str> {
        self.overview
            .as_ref()?
            .server_ids
            .get(self.selected_server)
            .map(String::as_str)
    }
    pub fn window(&self) -> TpsWindow {
        TPS_WINDOWS[self.window_index]
    }
    pub fn accept(&mut self, value: Overview) {
        let selected = self.server().map(str::to_owned);
        self.selected_server = selected
            .and_then(|s| value.server_ids.iter().position(|v| v == &s))
            .unwrap_or(0);
        self.overview = Some(value);
        self.refreshed = Some(Instant::now());
        self.failed = false;
        if !self.demo && self.menu.message != MAIN_MENU {
            self.set_menu_message(MAIN_MENU.into());
        }
    }

    pub fn accept_history(&mut self, result: Option<Result<TpsHistory, String>>) {
        if self
            .history
            .as_ref()
            .is_some_and(|h| Some(h.server_id.as_str()) != self.server())
        {
            self.history = None;
        }
        match result {
            Some(Ok(history))
                if Some(history.server_id.as_str()) == self.server()
                    && history.step == self.window().step =>
            {
                self.history = Some(history);
                self.history_failed = false;
            }
            _ => self.history_failed = true,
        }
    }

    pub fn clear_stats_error(&mut self) {
        self.stats_error = None;
    }

    pub fn finish_player_stats(&mut self, result: Result<String, String>, now: Instant) {
        match result {
            Ok(card) => self.show_detail(card),
            Err(message) => self.stats_error = Some((message, now + STATS_ERROR_DURATION)),
        }
    }

    fn stats_error(&mut self, now: Instant) -> Option<&str> {
        let _ = self.stats_error.take_if(|(_, expires)| now >= *expires);
        self.stats_error
            .as_ref()
            .map(|(message, _)| message.as_str())
    }
}

fn block(title: &str) -> Block<'_> {
    Block::default()
        .borders(Borders::ALL)
        .title(title)
        .border_style(Style::default().fg(Color::Rgb(48, 62, 76)))
        .style(Style::default().bg(PANEL))
}

pub fn draw(frame: &mut Frame, app: &mut App) {
    let area = frame.area();
    frame.render_widget(
        Block::default().style(Style::default().bg(BG).fg(TEXT)),
        area,
    );
    if area.width < 84 || area.height < 28 {
        let hint = if let Some(Confirmation::Exit { approved }) = app.confirm {
            exit_prompt(approved)
        } else {
            "OmkalityCraft · Owner\nНужно окно от 84 × 28. Увеличьте терминал.\nEsc — назад или выход".into()
        };
        frame.render_widget(
            Paragraph::new(hint)
                .style(Style::default().fg(TEXT))
                .wrap(Wrap { trim: false }),
            area,
        );
        return;
    }
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(10),
            Constraint::Min(14),
            Constraint::Length(3),
        ])
        .split(area);
    let top = if app.branding_header && area.height >= 34 {
        let columns =
            Layout::horizontal([Constraint::Length(20), Constraint::Min(1)]).split(rows[0]);
        frame.render_widget(block(""), columns[0]);
        crate::branding::draw(frame, Rect::new(columns[0].x + 2, columns[0].y + 1, 16, 8));
        columns[1]
    } else {
        rows[0]
    };
    let top = Layout::vertical([Constraint::Length(3), Constraint::Length(7)]).split(top);
    let mode = if app.demo {
        "ДЕМО · команды отключены"
    } else {
        "OWNER"
    };
    frame.render_widget(
        Paragraph::new(Line::from(vec![
            Span::styled(
                " OMKALITYCRAFT ",
                Style::default().fg(ACCENT).add_modifier(Modifier::BOLD),
            ),
            Span::raw(" /  "),
            Span::styled(mode, Style::default().fg(WARN)),
        ]))
        .block(block(" owner terminal · 0.1 ")),
        top[0],
    );
    let metrics =
        Layout::horizontal([Constraint::Percentage(50), Constraint::Percentage(50)]).split(top[1]);
    render_metrics(
        frame,
        app,
        metrics[0],
        " VPS / Docker host ",
        &[
            ("host_cpu", "CPU", "%"),
            ("host_ram", "RAM", "%"),
            ("host_disk", "Диск проекта", "%"),
        ],
    );
    render_metrics(
        frame,
        app,
        metrics[1],
        " Minecraft ",
        &[
            ("game_tps", "TPS", "/20"),
            ("game_mspt", "Средний tick", "ms"),
            ("game_players", "Игроки", ""),
        ],
    );
    let body =
        Layout::horizontal([Constraint::Percentage(48), Constraint::Percentage(52)]).split(rows[1]);
    let left = Layout::vertical([Constraint::Length(3), Constraint::Min(1)]).split(body[0]);
    let servers = app
        .overview
        .as_ref()
        .map(|v| {
            v.server_ids
                .iter()
                .enumerate()
                .map(|(i, s)| {
                    if i == app.selected_server {
                        format!("[ {s} ]")
                    } else {
                        format!("  {s}  ")
                    }
                })
                .collect::<Vec<_>>()
                .join(" ")
        })
        .unwrap_or_else(|| "Загрузка конфигурации…".into());
    frame.render_widget(
        Paragraph::new(servers)
            .style(Style::default().fg(ACCENT))
            .block(block(" Серверы · ← → ")),
        left[0],
    );
    render_tps(frame, app, left[1]);
    render_commands(frame, body[1], app);
    let age = app.refreshed.map(|t| t.elapsed().as_secs());
    let status = if app.loading {
        format!(
            "{}... {}",
            app.activity.unwrap_or("Запрос выполняется"),
            app.spinner()
        )
    } else if app.failed {
        "Ошибка · показания могут быть устаревшими".into()
    } else {
        age.map(|a| {
            format!(
                "Обновлено {a} с назад{}",
                if a > 20 { " · устарело" } else { "" }
            )
        })
        .unwrap_or_else(|| "Данных пока нет".into())
    };
    let back_hint = if app.at_menu() && app.resetting.is_none() {
        "Esc выход"
    } else {
        "Esc назад"
    };
    frame.render_widget(
        Paragraph::new(format!(
            " r обновить   ← → сервер   t период   i ключ   {back_hint}  |  {status}"
        ))
        .style(Style::default().fg(if app.loading {
            ACCENT
        } else if app.failed || age.is_some_and(|a| a > 20) {
            WARN
        } else {
            MUTED
        }))
        .block(block(" просмотр обновляется каждые 5 с ")),
        rows[2],
    );
    if let Some(selected) = app.range_picker {
        let popup = Rect::new((area.width - 44) / 2, (area.height - 10) / 2, 44, 10);
        frame.render_widget(Clear, popup);
        let mut lines = vec![Line::from(" За последнее время:"), Line::from("")];
        for (i, window) in TPS_WINDOWS.iter().enumerate() {
            lines.push(Line::styled(
                format!(
                    " {} {}",
                    if selected == i { "›" } else { " " },
                    window.label
                ),
                Style::default().fg(if selected == i { ACCENT } else { TEXT }),
            ));
        }
        lines.extend([
            Line::from(""),
            Line::from(" ↑/↓ выбор · Enter применить · Esc отмена"),
        ]);
        frame.render_widget(
            Paragraph::new(lines).block(block(" Период графика TPS ")),
            popup,
        );
    }
    if let Some(form) = &app.moderation {
        form.draw(frame);
    }
    if let Some(form) = &app.world_reset {
        form.draw(frame);
    }
    if let Some(confirmation) = &app.confirm {
        let w = area.width.min(72);
        let popup = Rect::new((area.width - w) / 2, area.height / 2 - 4, w, 8);
        frame.render_widget(Clear, popup);
        let (title, text) = match confirmation {
            Confirmation::Save(input) => {
                let server = app.server().unwrap_or("?");
                (
                    " Сохранение мира ",
                    format!(
                        "Команда: save-all flush\nСервер: {server}\nДля отправки введите SAVE {server} и нажмите Enter.\nEsc — отмена. Повторной отправки автоматически нет.\n\n> {input}"
                    ),
                )
            }
            Confirmation::Invitation { approved } => (
                " Приглашение в проект ",
                format!(
                    "Создать один одноразовый ключ регистрации?\n\n{}\n\n←/→ выбор · Enter подтвердить · Esc отменить",
                    if *approved {
                        "  Нет      › Да"
                    } else {
                        "› Нет        Да"
                    },
                ),
            ),
            Confirmation::Exit { approved } => (" Выход из TUI ", exit_prompt(*approved)),
        };
        frame.render_widget(
            Paragraph::new(text)
                .style(Style::default().fg(WARN))
                .block(block(title)),
            popup,
        );
    }
}

fn exit_prompt(approved: bool) -> String {
    let choice = if approved {
        "  Нет      › Да"
    } else {
        "› Нет        Да"
    };
    format!("Закрыть админку?\n\n{choice}\n\n←/→ выбор · Enter подтвердить · Esc отменить")
}

fn render_commands(frame: &mut Frame, area: Rect, app: &mut App) {
    let panel = block(" Команды · 1/2/3/4 · k/b/m/s · w вайп ");
    let mut content = panel.inner(area);
    frame.render_widget(panel, area);
    if app.resetting.is_none()
        && let Some(restrictions) = app.restrictions_panel()
    {
        restrictions.draw(frame, content);
        return;
    }
    if let Some(error) = app.stats_error(Instant::now()) {
        let rows = Layout::vertical([Constraint::Min(1), Constraint::Length(2)]).split(content);
        content = rows[0];
        frame.render_widget(
            Paragraph::new(format!("Ошибка · {error}"))
                .style(Style::default().fg(ERROR))
                .wrap(Wrap { trim: true }),
            rows[1],
        );
    }
    let page = app.command_page();
    let (message, scroll) = if let Some(step) = app.resetting {
        let label = match step {
            "run" => "Вайп мира",
            "prepare" => "Подготовка мира и резервной копии",
            "apply" => "Установка нового мира",
            _ => "Запуск и проверка сервера",
        };
        let operation = app.reset_progress.as_ref().map_or_else(
            || label.to_owned(),
            |progress| format!("{}\n{}", progress.world, progress.label().unwrap_or(label)),
        );
        (
            Paragraph::new(Text::styled(
                format!("{operation}... {}", app.spinner()),
                Style::default().fg(ACCENT),
            )),
            0,
        )
    } else if let Some(lines) = &page.forge_tps {
        (Paragraph::new(lines.clone()), page.scroll)
    } else {
        (Paragraph::new(page.message.as_str()), page.scroll)
    };
    frame.render_widget(
        message
            .scroll((scroll, 0))
            .style(Style::default().fg(if app.failed { WARN } else { TEXT }))
            .wrap(Wrap { trim: false }),
        content,
    );
}

fn forge_tps_lines(server: &str, output: &str) -> Option<Vec<Line<'static>>> {
    let mut readings = Vec::new();
    let mut other = Vec::new();
    for mut line in output.lines().map(str::trim).filter(|s| !s.is_empty()) {
        while !line.is_empty() {
            let Some((name, tick, tps, rest)) = forge_reading(line) else {
                other.push(line.to_owned());
                break;
            };
            readings.push((name, tick, tps));
            line = rest.trim();
        }
    }
    if readings.is_empty() {
        return None;
    }
    let mut lines = vec![
        Line::styled(format!("Forge TPS · {server}"), Style::default().fg(ACCENT)),
        Line::default(),
        Line::styled(
            format!("{:<28} {:>8} {:>8}", "Измерение", "Тик, мс", "TPS"),
            Style::default().fg(MUTED),
        ),
        Line::styled(
            "──────────────────────────── ──────── ────────",
            Style::default().fg(MUTED),
        ),
    ];
    readings.sort_by_key(|(name, _, _)| *name != "Overall");
    for (index, (name, tick, tps)) in readings.into_iter().enumerate() {
        let overall = name == "Overall";
        let title = if overall {
            "Весь сервер"
        } else {
            name.trim_start_matches("Dim ").trim_start()
        };
        let mut label: String = title.chars().take(28).collect();
        if label != title {
            label.pop();
            label.push('…');
        }
        let background = if index % 2 == 0 { PANEL } else { BG };
        lines.push(
            Line::from(vec![
                Span::styled(
                    format!("{label:<28}"),
                    Style::default().fg(if overall { ACCENT } else { TEXT }),
                ),
                Span::styled(format!(" {tick:>8.2} "), Style::default().fg(MUTED)),
                Span::styled(
                    format!("{tps:>8.2}"),
                    Style::default().fg(crate::tps_grid::color(tps)),
                ),
            ])
            .style(Style::default().bg(background)),
        );
    }
    if !other.is_empty() {
        lines.push(Line::default());
        lines.extend(other.into_iter().map(Line::raw));
    }
    Some(lines)
}

fn forge_reading(line: &str) -> Option<(&str, f64, f64, &str)> {
    let (name, values) = line.split_once(": Mean tick time:")?;
    let name = name.trim();
    if name != "Overall" && !name.starts_with("Dim ") {
        return None;
    }
    let (tick, rest) = values.split_once(" ms. Mean TPS:")?;
    let rest = rest.trim_start();
    let end = rest
        .find(|c: char| !c.is_ascii_digit() && !matches!(c, '.' | ','))
        .unwrap_or(rest.len());
    let parse = |text: &str| {
        text.trim()
            .replace(',', ".")
            .parse::<f64>()
            .ok()
            .filter(|v| v.is_finite() && *v >= 0.0)
    };
    Some((name, parse(tick)?, parse(&rest[..end])?, &rest[end..]))
}

fn render_tps(frame: &mut Frame, app: &App, area: Rect) {
    let history = app
        .history
        .as_ref()
        .filter(|h| Some(h.server_id.as_str()) == app.server() && h.step == app.window().step);
    let stale = app.history_failed
        || app.failed
        || app.refreshed.is_some_and(|t| t.elapsed().as_secs() > 20);
    let title = format!(
        " TPS · {} · за {}{} ",
        app.server().unwrap_or("сервер"),
        app.window().label,
        if stale { " · устарело" } else { "" }
    );
    let note = match history {
        Some(h) if h.state == "disabled" => "Мониторинг не подключён".into(),
        Some(h) if h.state == "missing" => "За этот период нет измерений".into(),
        Some(h) => {
            let min = h
                .points
                .iter()
                .filter_map(|point| point.tps)
                .reduce(f64::min);
            min.map(|value| format!("Минимум за период: {value:.1} TPS"))
                .unwrap_or_else(|| "За этот период нет измерений".into())
        }
        None => "История TPS пока недоступна".into(),
    };
    let rows = Layout::vertical([
        Constraint::Min(1),
        Constraint::Length(1),
        Constraint::Length(1),
    ])
    .split(area);
    let border = block(&title);
    let inner = border.inner(rows[0]);
    frame.render_widget(border, rows[0]);
    crate::tps_grid::draw(frame, history, inner, app.window(), stale);
    frame.render_widget(
        Paragraph::new(crate::tps_grid::legend(stale)).style(Style::default().bg(BG)),
        rows[1],
    );
    frame.render_widget(
        Paragraph::new(note).style(Style::default().fg(if stale { WARN } else { MUTED }).bg(BG)),
        rows[2],
    );
}

fn render_metrics(
    frame: &mut Frame,
    app: &App,
    area: Rect,
    title: &str,
    keys: &[(&str, &str, &str)],
) {
    let current = app
        .overview
        .as_ref()
        .filter(|v| v.selected_server.as_deref() == app.server());
    let mut lines = Vec::new();
    for (key, label, unit) in keys {
        let metric = current.and_then(|v| v.metrics.iter().find(|m| &m.key == key));
        let value = metric
            .and_then(|m| m.value)
            .map(|v| {
                if *key == "game_players" {
                    format!("{v:.0}")
                } else {
                    format!("{v:.1} {unit}")
                }
            })
            .unwrap_or_else(|| match metric.map(|m| m.state.as_str()) {
                Some("stale") => "устарело".into(),
                Some("invalid") => "неоднозначные данные".into(),
                _ => "нет данных".into(),
            });
        let value = match app.reset_progress.as_ref() {
            Some(progress) if *key == "game_players" && progress.players_disconnected() => {
                "0".into()
            }
            Some(progress)
                if matches!(*key, "game_mspt" | "game_tps") && progress.server_stopped() =>
            {
                "—".into()
            }
            _ => value,
        };
        lines.push(Line::from(vec![
            Span::styled(format!(" {label:<17}"), Style::default().fg(MUTED)),
            Span::styled(value, Style::default().fg(ACCENT)),
        ]));
    }
    let state = current
        .map(|v| v.metrics_status.as_str())
        .unwrap_or("unavailable");
    let warning = match state {
        "disabled" => Some(" Мониторинг не подключён"),
        "unavailable" => Some(" Мониторинг недоступен"),
        "partial" => Some(" Часть показателей недоступна"),
        _ => None,
    };
    if let Some(warning) = warning {
        lines.push(Line::styled(warning, Style::default().fg(MUTED)));
    }
    frame.render_widget(Paragraph::new(lines).block(block(title)), area);
}

#[cfg(test)]
mod forge_tests {
    use super::*;

    #[test]
    fn forge_tps_separates_rcon_rows_and_colors_the_total_and_slow_dimensions() {
        let rows = forge_tps_lines(
            "dj2",
            "Dim 0 (overworld) : Mean tick time: 2.00 ms. Mean TPS: 20.000\n\
             Dim -1 (nether): Mean tick time: 63.12 ms. Mean TPS: 15.843\
             Overall: Mean tick time: 66.0 ms. Mean TPS: 15.151\nExtra status",
        )
        .unwrap();
        assert_eq!(rows[4].spans[0].content.trim(), "Весь сервер");
        assert_eq!(rows[5].spans[0].content.trim(), "0 (overworld)");
        assert_eq!(
            rows[5].spans[2].style.fg,
            Some(crate::tps_grid::color(20.0))
        );
        assert_eq!(
            rows[6].spans[2].style.fg,
            Some(crate::tps_grid::color(15.843))
        );
        assert_eq!(rows.last().unwrap().spans[0].content, "Extra status");
        assert!(forge_tps_lines("dj2", "You may not use this command").is_none());
    }
}
