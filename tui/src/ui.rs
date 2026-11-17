use crate::protocol::Overview;
use ratatui::{
    Frame,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Clear, List, ListItem, ListState, Paragraph, Wrap},
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
}

impl App {
    pub fn new(demo: bool) -> Self {
        Self { overview: None, selected_server: 0, operation: ListState::default(), message: "1  Список игроков\n2  Forge TPS по измерениям\n3  Сохранение мира (с подтверждением)\n\nОтвет команды появится здесь.\nPgUp/PgDn — прокрутка ответа.".into(), loading: false, failed: false, refreshed: None, demo, confirm: None, scroll: 0 }
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
            Constraint::Length(3),
            Constraint::Length(7),
            Constraint::Min(14),
            Constraint::Length(3),
        ])
        .split(area);
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
            Span::raw(" /  управление сервером    "),
            Span::styled(mode, Style::default().fg(WARN)),
        ]))
        .block(block(" owner terminal · 0.1 ")),
        rows[0],
    );
    let metrics =
        Layout::horizontal([Constraint::Percentage(50), Constraint::Percentage(50)]).split(rows[1]);
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
        Layout::horizontal([Constraint::Percentage(48), Constraint::Percentage(52)]).split(rows[2]);
    let left = Layout::vertical([
        Constraint::Length(3),
        Constraint::Min(5),
        Constraint::Length(5),
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
        left[1],
        &mut app.operation,
    );
    frame.render_widget(
        Paragraph::new(details)
            .style(Style::default().fg(MUTED))
            .block(block(" Выбранная операция "))
            .wrap(Wrap { trim: false }),
        left[2],
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
            " r обновить   ← → сервер   ↑ ↓ операция   q выход    |    {status}"
        ))
        .style(
            Style::default().fg(if app.failed || age.is_some_and(|a| a > 20) {
                WARN
            } else {
                MUTED
            }),
        )
        .block(block(" просмотр обновляется каждые 10 с ")),
        rows[3],
    );
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
