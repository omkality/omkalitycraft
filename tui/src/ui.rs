use crate::protocol::{Overview, TpsHistory};
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    symbols::Marker,
    text::{Line, Span},
    widgets::{
        Axis, Block, Borders, Chart, Clear, Dataset, GraphType, List, ListItem, ListState,
        Paragraph, Wrap,
    },
};
use std::time::Instant;

pub const BG: Color = Color::Rgb(12, 16, 21);
const PANEL: Color = Color::Rgb(18, 24, 31);
const TEXT: Color = Color::Rgb(218, 226, 235);
const MUTED: Color = Color::Rgb(139, 155, 172);
const ACCENT: Color = Color::Rgb(114, 205, 220);
const WARN: Color = Color::Rgb(237, 184, 104);

pub struct App {
    pub overview: Option<Overview>,
    pub selected_server: usize,
    pub operation: ListState,
    pub message: String,
    pub loading: bool,
    pub failed: bool,
    pub refreshed: Option<Instant>,
    pub demo: bool,
    pub confirm: Option<String>,
    pub scroll: u16,
    pub history: Option<TpsHistory>,
    pub history_failed: bool,
    pub about: bool,
    pub branding_header: bool,
}

impl App {
    pub fn new(demo: bool) -> Self {
        Self { overview: None, selected_server: 0, operation: ListState::default(), message: "1  Список игроков\n2  Forge TPS по измерениям\n3  Сохранение мира (с подтверждением)\n\nОтвет команды появится здесь.\nPgUp/PgDn — прокрутка ответа.".into(), loading: false, failed: false, refreshed: None, demo, confirm: None, scroll: 0, history: None, history_failed: false, about: false, branding_header: false }
    }
    pub fn server(&self) -> Option<&str> {
        self.overview
            .as_ref()?
            .server_ids
            .get(self.selected_server)
            .map(String::as_str)
    }
    pub fn filtered(&self) -> Vec<&crate::protocol::Operation> {
        self.overview
            .as_ref()
            .map(|v| {
                v.operations
                    .iter()
                    .filter(|o| o.server_id.as_deref() == self.server())
                    .collect()
            })
            .unwrap_or_default()
    }
    pub fn move_operation(&mut self, delta: isize) {
        let len = self.filtered().len();
        if len > 0 {
            self.operation.select(Some(
                self.operation
                    .selected()
                    .unwrap_or(0)
                    .saturating_add_signed(delta)
                    .min(len - 1),
            ));
        }
    }
    pub fn accept(&mut self, value: Overview) {
        let selected = self.server().map(str::to_owned);
        let op = self
            .filtered()
            .get(self.operation.selected().unwrap_or(0))
            .map(|o| (o.kind.clone(), o.id.clone()));
        self.selected_server = selected
            .and_then(|s| value.server_ids.iter().position(|v| v == &s))
            .unwrap_or(0);
        self.overview = Some(value);
        let index = op.and_then(|(kind, id)| {
            self.filtered()
                .iter()
                .position(|o| o.id == id && o.kind == kind)
        });
        self.operation.select(if self.filtered().is_empty() {
            None
        } else {
            Some(index.unwrap_or(0))
        });
        self.refreshed = Some(Instant::now());
        self.failed = false;
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
            Some(Ok(history)) if Some(history.server_id.as_str()) == self.server() => {
                self.history = Some(history);
                self.history_failed = false;
            }
            _ => self.history_failed = true,
        }
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
        frame.render_widget(Paragraph::new("OmkalityCraft · Owner\nНужно окно от 84 × 28. Увеличьте терминал.\nq / Ctrl+C — выход").style(Style::default().fg(TEXT)).wrap(Wrap { trim: false }), area);
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
        frame.render_widget(block(" Мёртвум "), columns[0]);
        crate::branding::draw(frame, Rect::new(columns[0].x + 2, columns[0].y + 1, 16, 8));
        columns[1]
    } else {
        rows[0]
    };
    let top = Layout::vertical([Constraint::Length(3), Constraint::Length(7)]).split(top);
    let mode = if app.demo {
        "ДЕМО · команды отключены"
    } else {
        "OWNER · локальный Python backend"
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
    let left = Layout::vertical([
        Constraint::Length(3),
        Constraint::Length(if body[0].height >= 22 { 11 } else { 9 }),
        Constraint::Min(0),
        Constraint::Length(if body[0].height >= 20 { 4 } else { 0 }),
    ])
    .split(body[0]);
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
    let ops = app.filtered();
    let selected = ops.get(app.operation.selected().unwrap_or(0)).copied();
    let details = selected
        .map(|o| {
            format!(
                "{}\n{}\nФаза workflow; готовность сервера отдельно.",
                o.id,
                if o.terminal == Some(true) {
                    "Workflow завершён"
                } else {
                    "Workflow не завершён"
                }
            )
        })
        .unwrap_or_else(|| {
            "Нет последних операций.\nЭто не проверка работоспособности сервера.".into()
        });
    let items: Vec<ListItem> = ops
        .iter()
        .map(|o| {
            ListItem::new(format!(
                "{:<12} {:<15} {}",
                o.kind,
                o.phase.as_deref().unwrap_or("неизвестно"),
                &o.id[..8]
            ))
        })
        .collect();
    let title = app
        .overview
        .as_ref()
        .map(|v| {
            format!(
                " Операции · ↑ ↓  / пропущено {}{} ",
                v.skipped,
                if v.truncated {
                    " / список ограничен"
                } else {
                    ""
                }
            )
        })
        .unwrap_or_else(|| " Последние операции ".into());
    frame.render_stateful_widget(
        List::new(items)
            .block(block(&title))
            .highlight_symbol("› ")
            .highlight_style(Style::default().bg(Color::Rgb(31, 52, 64)).fg(ACCENT)),
        left[2],
        &mut app.operation,
    );
    frame.render_widget(
        Paragraph::new(details)
            .style(Style::default().fg(MUTED))
            .block(block(" Выбранная операция "))
            .wrap(Wrap { trim: false }),
        left[3],
    );
    frame.render_widget(
        Paragraph::new(app.message.as_str())
            .scroll((app.scroll, 0))
            .style(Style::default().fg(if app.failed { WARN } else { TEXT }))
            .block(block(" Команды · 1 игроки / 2 TPS / 3 save "))
            .wrap(Wrap { trim: false }),
        body[1],
    );
    let age = app.refreshed.map(|t| t.elapsed().as_secs());
    let status = if app.loading {
        "Запрос выполняется…".into()
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
    frame.render_widget(
        Paragraph::new(format!(
            " r обновить   ← → сервер   ↑ ↓ операция   F1 проект   q выход  |  {status}"
        ))
        .style(
            Style::default().fg(if app.failed || age.is_some_and(|a| a > 20) {
                WARN
            } else {
                MUTED
            }),
        )
        .block(block(" просмотр обновляется каждые 5 с ")),
        rows[2],
    );
    if app.about {
        let w = 58;
        let h = 23;
        let popup = Rect::new((area.width - w) / 2, (area.height - h) / 2, w, h);
        frame.render_widget(Clear, popup);
        frame.render_widget(block(" OMKALITYCRAFT · руда мёртвума "), popup);
        crate::branding::draw_large(
            frame,
            Rect::new(popup.x + (w - 32) / 2, popup.y + 2, 32, 16),
        );
        frame.render_widget(
            Paragraph::new("Плоская текстура руды мёртвума\nF1 / Esc — вернуться к графику")
                .centered()
                .style(Style::default().fg(TEXT).bg(PANEL)),
            Rect::new(popup.x + 1, popup.y + 19, w - 2, 2),
        );
    }
    if let Some(input) = &app.confirm {
        let w = area.width.min(72);
        let popup = Rect::new((area.width - w) / 2, area.height / 2 - 4, w, 8);
        frame.render_widget(Clear, popup);
        let text = format!(
            "Команда: save-all flush\nСервер: {}\nДля отправки введите SAVE {} и нажмите Enter.\nEsc — отмена. Повторной отправки автоматически нет.\n\n> {}",
            app.server().unwrap_or("?"),
            app.server().unwrap_or("?"),
            input
        );
        frame.render_widget(
            Paragraph::new(text)
                .style(Style::default().fg(WARN))
                .block(block(" Сохранение мира ")),
            popup,
        );
    }
}

pub fn tps_segments(history: &TpsHistory) -> Vec<Vec<(f64, f64)>> {
    let mut segments = Vec::new();
    let mut current = Vec::new();
    for p in &history.points {
        if let Some(tps) = p.tps {
            current.push((p.timestamp as f64 - history.end as f64, tps));
        } else if !current.is_empty() {
            segments.push(std::mem::take(&mut current));
        }
    }
    if !current.is_empty() {
        segments.push(current);
    }
    segments
}

fn render_tps(frame: &mut Frame, app: &App, area: Rect) {
    let history = app
        .history
        .as_ref()
        .filter(|h| Some(h.server_id.as_str()) == app.server());
    let stale = app.history_failed
        || app.failed
        || app.refreshed.is_some_and(|t| t.elapsed().as_secs() > 20);
    let title = format!(
        " TPS · {} · последние 5 минут{} ",
        app.server().unwrap_or("сервер"),
        if stale { " · устарело" } else { "" }
    );
    let segments = history.map(tps_segments).unwrap_or_default();
    let datasets = segments
        .iter()
        .map(|segment| {
            Dataset::default()
                .data(segment)
                .graph_type(if segment.len() > 1 {
                    GraphType::Line
                } else {
                    GraphType::Scatter
                })
                .marker(Marker::HalfBlock)
                .style(Style::default().fg(if stale { MUTED } else { ACCENT }))
        })
        .collect::<Vec<_>>();
    let note = match history {
        Some(h) if h.state == "disabled" => "Мониторинг не подключён".into(),
        Some(h) if h.state == "missing" => "За этот период нет измерений".into(),
        Some(h) => {
            let values = h.points.iter().filter_map(|p| p.tps).collect::<Vec<_>>();
            let min = values.iter().copied().fold(20.0, f64::min);
            format!("min {min:.1} · {} / 61 точек · шаг 5 с", values.len())
        }
        None => "История TPS пока недоступна".into(),
    };
    let rows = Layout::vertical([Constraint::Min(1), Constraint::Length(1)]).split(area);
    frame.render_widget(
        Chart::new(datasets)
            .block(block(&title))
            .x_axis(
                Axis::default()
                    .bounds([-300.0, 0.0])
                    .labels([
                        "−5 мин",
                        "−2:30",
                        if stale {
                            "последний ответ"
                        } else {
                            "сейчас"
                        },
                    ])
                    .style(Style::default().fg(MUTED)),
            )
            .y_axis(
                Axis::default()
                    .bounds([0.0, 20.0])
                    .labels(["0", "10", "20"])
                    .style(Style::default().fg(MUTED)),
            ),
        rows[0],
    );
    frame.render_widget(
        Paragraph::new(note).style(Style::default().fg(if stale { WARN } else { MUTED }).bg(BG)),
        rows[1],
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
        lines.push(Line::from(vec![
            Span::styled(format!(" {label:<17}"), Style::default().fg(MUTED)),
            Span::styled(value, Style::default().fg(ACCENT)),
        ]));
    }
    let state = current
        .map(|v| v.metrics_status.as_str())
        .unwrap_or("unavailable");
    lines.push(Line::styled(
        match state {
            "disabled" => " Мониторинг не подключён",
            "unavailable" => " Prometheus недоступен / конфигурация неверна",
            "partial" => " Часть показателей недоступна",
            _ => " Prometheus · свежие измерения",
        },
        Style::default().fg(MUTED),
    ));
    frame.render_widget(Paragraph::new(lines).block(block(title)), area);
}
