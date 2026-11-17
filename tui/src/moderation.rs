use ratatui::crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};
use serde::Deserialize;

#[derive(Clone, Debug)]
pub struct Action {
    pub server: String,
    pub command: String,
    pub player: String,
    pub duration: String,
    pub reason: String,
}

#[derive(Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    schema_version: u32,
    action: String,
    pub server_id: String,
    pub command: String,
    pub player: String,
    pub ok: bool,
    pub effect: String,
    pub expires_at: Option<u64>,
    pub error: Option<String>,
}
impl Receipt {
    pub fn parse(bytes: &[u8], request: &Action) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ модерации")?;
        if v.schema_version != 1
            || v.action != "owner.moderation"
            || v.server_id != request.server
            || v.command != request.command
            || v.player != request.player
            || !matches!(v.effect.as_str(), "none" | "applied" | "unknown")
            || v.ok != (v.effect == "applied")
            || v.ok != v.error.is_none()
            || v.ok && ((v.command == "kick") != v.expires_at.is_none())
            || v.error.as_deref().is_some_and(|s| {
                !matches!(
                    s,
                    "invalid_request"
                        | "player_offline"
                        | "unavailable"
                        | "already_banned"
                        | "refused"
                )
            })
        {
            return Err("Ответ модерации не соответствует запросу; автоповтора нет".into());
        }
        Ok(v)
    }
    pub fn message(&self) -> String {
        format!(
            "Сервер: {}\nИгрок: {}\nДействие: {}\n\n{}{}",
            self.server_id,
            self.player,
            self.command,
            if self.ok {
                "Сервер подтвердил выполнение."
            } else if self.effect == "unknown" {
                "Результат неизвестен. Команда могла выполниться. Автоповтора нет."
            } else {
                "Команда отклонена, изменения не применены."
            },
            self.error
                .as_ref()
                .map(|e| format!(
                    "\nПричина: {}",
                    match e.as_str() {
                        "invalid_request" => "проверьте ник, срок и подтверждение",
                        "player_offline" => "игрок уже не в сети",
                        "already_banned" => "уже есть бан; он сохранён",
                        "unavailable" => "сервер/Core/RCON недоступен",
                        _ => "сервер отказал",
                    }
                ))
                .unwrap_or_default()
        )
    }
}

pub fn seconds(value: &str) -> Option<u64> {
    if !value.is_ascii() || value.len() < 2 || value.len() > 9 {
        return None;
    }
    let (number, unit) = value.split_at(value.len() - 1);
    if number.starts_with('0') || !number.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let factor = match unit {
        "s" => 1,
        "m" => 60,
        "h" => 3600,
        "d" => 86400,
        "w" => 604800,
        _ => return None,
    };
    number
        .parse::<u64>()
        .ok()?
        .checked_mul(factor)
        .filter(|n| *n > 0 && *n <= 31536000)
}

pub struct Form {
    pub action: Action,
    field: usize,
    pub confirming: bool,
    yes: bool,
    error: String,
}
impl Form {
    pub fn new(server: String, command: &str) -> Self {
        Self {
            action: Action {
                server,
                command: command.into(),
                player: String::new(),
                duration: if command == "kick" {
                    String::new()
                } else {
                    "10m".into()
                },
                reason: String::new(),
            },
            field: 0,
            confirming: false,
            yes: false,
            error: String::new(),
        }
    }
    pub fn key(&mut self, key: KeyCode) -> Option<Action> {
        if self.confirming {
            match key {
                KeyCode::Left | KeyCode::Right | KeyCode::Tab => self.yes = !self.yes,
                KeyCode::Enter if self.yes => return Some(self.action.clone()),
                KeyCode::Enter => {
                    self.confirming = false;
                    self.yes = false;
                }
                _ => {}
            }
            return None;
        }
        let fields = if self.action.command == "kick" { 2 } else { 3 };
        match key {
            KeyCode::Tab | KeyCode::Down => self.field = (self.field + 1) % fields,
            KeyCode::BackTab | KeyCode::Up => self.field = (self.field + fields - 1) % fields,
            KeyCode::Enter => {
                if self.action.player.is_empty()
                    || self.action.player.len() > 16
                    || !self
                        .action
                        .player
                        .bytes()
                        .all(|b| b.is_ascii_alphanumeric() || b == b'_')
                {
                    self.error = "Ник: 1–16 латинских букв, цифр или _".into();
                } else if self.action.command != "kick" && seconds(&self.action.duration).is_none()
                {
                    self.error = "Срок: 10m, 20h, 1d; от 1s до 365d".into();
                } else if self.action.command == "ban" {
                    self.confirming = true;
                    self.yes = false;
                    self.error.clear();
                } else {
                    return Some(self.action.clone());
                }
            }
            KeyCode::Backspace => {
                self.input().pop();
                self.error.clear();
            }
            KeyCode::Char(c)
                if !c.is_control() && c != '§' && self.input().chars().count() < 128 =>
            {
                self.input().push(c);
                self.error.clear();
            }
            _ => {}
        }
        None
    }
    fn input(&mut self) -> &mut String {
        match self.field {
            0 => &mut self.action.player,
            1 if self.action.command != "kick" => &mut self.action.duration,
            _ => &mut self.action.reason,
        }
    }
    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        let w = area.width.saturating_sub(4).min(80);
        let h = 17.min(area.height);
        let popup = Rect::new((area.width - w) / 2, (area.height - h) / 2, w, h);
        frame.render_widget(Clear, popup);
        let title = if self.confirming {
            " Бан · Вы уверены? "
        } else {
            " Модерация игрока "
        };
        let cursor = |field| if self.field == field { ">" } else { " " };
        let body = if self.confirming {
            format!(
                "\nСервер: {}\nИгрок: {}\nБан на: {}\nПричина: {}\n\nВы уверены? Игрок будет отключён.\n\n{}\n\n← → / Tab — выбор · Enter — принять · Esc — отмена",
                self.action.server,
                self.action.player,
                self.action.duration,
                self.action.reason,
                if self.yes {
                    "  Нет     [ Да, забанить ]"
                } else {
                    "[ Нет, вернуться ]     Да"
                }
            )
        } else {
            format!(
                "\n{} · {} (игрок должен быть в сети)\n\n{} Ник: {}\n{}{} Причина: {}\n\n{}\n\nTab / ↑ ↓ — поле · Enter — {} · Esc — отмена",
                self.action.server,
                self.action.command,
                cursor(0),
                self.action.player,
                if self.action.command == "kick" {
                    String::new()
                } else {
                    format!(
                        "{} Срок: {}  (s/m/h/d/w, до 365d)\n",
                        cursor(1),
                        self.action.duration
                    )
                },
                cursor(if self.action.command == "kick" { 1 } else { 2 }),
                self.action.reason,
                self.error,
                if self.action.command == "ban" {
                    "к подтверждению"
                } else {
                    "выполнить"
                }
            )
        };
        frame.render_widget(
            Paragraph::new(body)
                .wrap(Wrap { trim: false })
                .style(
                    Style::default()
                        .fg(Color::Rgb(218, 226, 235))
                        .bg(Color::Rgb(18, 24, 31)),
                )
                .block(Block::default().borders(Borders::ALL).title(title)),
            popup,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn durations() {
        for (s, n) in [
            ("10m", 600),
            ("20h", 72000),
            ("1d", 86400),
            ("365d", 31536000),
        ] {
            assert_eq!(seconds(s), Some(n));
        }
        for s in ["0s", "01d", "-1d", "1d2h", "366d", "99999999w", "x", "1💩"] {
            assert_eq!(seconds(s), None);
        }
    }
    #[test]
    fn ban_requires_second_screen_and_explicit_yes() {
        let mut f = Form::new("alpha".into(), "ban");
        f.action.player = "TestPlayer".into();
        assert!(f.key(KeyCode::Enter).is_none());
        assert!(f.confirming);
        assert!(f.key(KeyCode::Enter).is_none());
        assert!(!f.confirming);
        f.key(KeyCode::Enter);
        f.key(KeyCode::Right);
        assert_eq!(f.key(KeyCode::Enter).unwrap().player, "TestPlayer");
    }
    #[test]
    fn receipt_is_bound_and_modal_survives_resize() {
        let mut form = Form::new("alpha".into(), "ban");
        form.action.player = "TestPlayer".into();
        let good = serde_json::json!({"schema_version":1,"action":"owner.moderation","server_id":"alpha","command":"ban","player":"TestPlayer","ok":true,"effect":"applied","expires_at":2000000000_u64,"error":null});
        assert!(Receipt::parse(&serde_json::to_vec(&good).unwrap(), &form.action).is_ok());
        for (key, value) in [
            ("server_id", serde_json::json!("beta")),
            ("player", serde_json::json!("Other")),
            ("effect", serde_json::json!("none")),
            ("expires_at", serde_json::Value::Null),
        ] {
            let mut bad = good.clone();
            bad[key] = value;
            assert!(Receipt::parse(&serde_json::to_vec(&bad).unwrap(), &form.action).is_err());
        }
        form.action.reason = "Причина ".repeat(16);
        for confirming in [false, true] {
            form.confirming = confirming;
            for (w, h) in [(120, 38), (84, 28), (40, 15), (10, 5)] {
                let mut terminal =
                    ratatui::Terminal::new(ratatui::backend::TestBackend::new(w, h)).unwrap();
                terminal.draw(|frame| form.draw(frame)).unwrap();
            }
        }
    }
}
