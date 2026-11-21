use ratatui::crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
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

impl Action {
    pub fn permanent_ban(&self) -> bool {
        self.command == "ban" && self.duration == "perm"
    }

    pub fn project(&self) -> bool {
        self.command != "kick"
    }

    pub fn scope(&self) -> &str {
        if self.project() {
            "Весь проект"
        } else {
            &self.server
        }
    }
}

#[derive(Deserialize, Debug)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    schema_version: u32,
    action: String,
    server_id: Option<String>,
    unreachable: Option<Vec<String>>,
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
        let bound = if request.project() {
            v.action == "owner.project-moderation"
                && v.server_id.is_none()
                && v.unreachable.as_ref().is_some_and(|servers| {
                    servers.len() <= 100
                        && servers.iter().all(|id| crate::protocol::valid_server(id))
                })
        } else {
            v.action == "owner.moderation"
                && v.server_id.as_deref() == Some(request.server.as_str())
                && v.unreachable.is_none()
        };
        if v.schema_version != 1
            || !bound
            || v.command != request.command
            || v.player != request.player
            || !matches!(v.effect.as_str(), "none" | "applied" | "unknown")
            || v.ok
                && !(v.effect == "applied" || v.command == "revoke-invite" && v.effect == "none")
            || !v.ok && v.effect == "applied"
            || v.ok != v.error.is_none()
            || v.ok
                && ((matches!(v.command.as_str(), "kick" | "unban" | "revoke-invite")
                    || request.permanent_ban())
                    != v.expires_at.is_none())
            || v.expires_at == Some(0)
            || v.error.as_deref().is_some_and(|s| {
                !matches!(
                    s,
                    "invalid_request"
                        | "player_offline"
                        | "unavailable"
                        | "already_banned"
                        | "refused"
                        | "not_banned"
                        | "changed"
                        | "ambiguous"
                        | "inconsistent_servers"
                        | "profile_not_found"
                        | "account_locked"
                        | "operator_account"
                )
            })
        {
            return Err("Ответ модерации не соответствует запросу; автоповтора нет".into());
        }
        Ok(v)
    }
    pub fn message(&self) -> String {
        if self.command == "revoke-invite" {
            return match (self.ok, self.effect.as_str()) {
                (true, "applied") => "Приглашение отозвано.",
                (true, _) => "Приглашение уже не действует.",
                (_, "unknown") => "Результат неизвестен. Проверьте список приглашений.",
                _ => "Не удалось отозвать приглашение.",
            }
            .into();
        }
        let permanent_ban = self.command == "ban" && self.ok && self.expires_at.is_none();
        format!(
            "Область: {}\nИгрок: {}\nДействие: {}\n\n{}{}{}",
            self.server_id.as_deref().unwrap_or("Весь проект"),
            self.player,
            self.command,
            if permanent_ban {
                "Бессрочный бан применён. Вход на проект закрыт."
            } else if self.ok && self.server_id.is_none() {
                "Записано в общий список проекта."
            } else if self.ok {
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
                        "player_offline" => "игрок не найден среди подключённых",
                        "ambiguous" => "этот ник соответствует нескольким UUID",
                        "profile_not_found" => "профиль с таким ником не найден в Drasl",
                        "inconsistent_servers" =>
                            "серверы используют разные списки проекта или нуждаются в обновлении",
                        "not_banned" => "у игрока нет бана",
                        "changed" => "бан изменился; проверьте его заново",
                        "already_banned" => "уже есть бан; он сохранён",
                        "account_locked" => "у аккаунта другая блокировка или незавершённый разбан",
                        "operator_account" => "этот аккаунт используется админкой",
                        "unavailable" => "проверьте общий список и подключение серверов",
                        _ => "сервер отказал",
                    }
                ))
                .unwrap_or_default(),
            self.unreachable
                .as_ref()
                .filter(|ids| !ids.is_empty())
                .map(|ids| if permanent_ban {
                    format!("\nНе подтверждено отключение на: {}", ids.join(", "))
                } else {
                    format!("\nНе удалось проверить соединение с: {}", ids.join(", "))
                })
                .unwrap_or_default(),
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

pub fn valid_player(player: &str) -> bool {
    (1..=16).contains(&player.len())
        && player
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_')
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
                duration: if matches!(command, "ban" | "mute") {
                    "10m".into()
                } else {
                    String::new()
                },
                reason: String::new(),
            },
            field: 0,
            confirming: false,
            yes: false,
            error: String::new(),
        }
    }
    pub fn dismiss_confirmation(&mut self) -> bool {
        self.yes = false;
        std::mem::take(&mut self.confirming)
    }

    pub fn key(&mut self, key: KeyCode) -> Option<Action> {
        if self.confirming {
            match key {
                KeyCode::Left | KeyCode::Right | KeyCode::Tab => self.yes = !self.yes,
                KeyCode::Enter if self.yes => return Some(self.action.clone()),
                KeyCode::Enter => {
                    self.dismiss_confirmation();
                }
                _ => {}
            }
            return None;
        }
        let fields = match self.action.command.as_str() {
            "unban" | "revoke-invite" | "stats" => 1,
            "kick" => 2,
            _ => 3,
        };
        match key {
            KeyCode::Tab | KeyCode::Down => self.field = (self.field + 1) % fields,
            KeyCode::BackTab | KeyCode::Up => self.field = (self.field + fields - 1) % fields,
            KeyCode::Enter => {
                if self.action.command == "revoke-invite"
                    && (self.action.player.len() != 12
                        || !self
                            .action
                            .player
                            .bytes()
                            .all(|byte| byte.is_ascii_hexdigit()))
                {
                    self.error = "Введите 12 символов из списка приглашений (l).".into();
                } else if !valid_player(&self.action.player) {
                    self.error = "Ник: 1–16 латинских букв, цифр или _".into();
                } else if matches!(self.action.command.as_str(), "ban" | "mute")
                    && seconds(&self.action.duration).is_none()
                    && !self.action.permanent_ban()
                {
                    self.error = if self.action.command == "ban" {
                        "Срок: 10m, 20h, 1d или perm.".into()
                    } else {
                        "Срок: 10m, 20h, 1d; от 1s до 365d".into()
                    };
                } else if matches!(self.action.command.as_str(), "ban" | "revoke-invite") {
                    if self.action.command == "revoke-invite" {
                        self.action.player.make_ascii_lowercase();
                    }
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
            1 if matches!(self.action.command.as_str(), "ban" | "mute") => {
                &mut self.action.duration
            }
            _ => &mut self.action.reason,
        }
    }
    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        let w = area.width.saturating_sub(4).min(80);
        let unban = self.action.command == "unban";
        let invite = self.action.command == "revoke-invite";
        let stats = self.action.command == "stats";
        let h = if unban || invite || stats { 10 } else { 17 }.min(area.height);
        let popup = Rect::new((area.width - w) / 2, (area.height - h) / 2, w, h);
        frame.render_widget(Clear, popup);
        let title = if stats {
            " Статистика игрока "
        } else if invite && self.confirming {
            " Отозвать приглашение? "
        } else if invite {
            " Отзыв приглашения "
        } else if self.confirming {
            " Бан · Вы уверены? "
        } else if unban {
            " Разбан игрока "
        } else {
            " Модерация игрока "
        };
        let cursor = |field| if self.field == field { ">" } else { " " };
        let body = if stats {
            format!(
                "\n> Ник: {}\n{}\n\nEnter — посмотреть · Esc — отмена",
                self.action.player, self.error
            )
        } else if invite {
            let instruction = if !self.confirming {
                "Введите номер из списка приглашений (l). Enter — продолжить."
            } else if self.yes {
                "Нет     [ Да, отозвать ]"
            } else {
                "[ Нет ]     Да"
            };
            format!(
                "\nПриглашение: {}\n{}\n\n{instruction}",
                self.action.player, self.error
            )
        } else if self.confirming {
            format!(
                "\nОбласть: {}\nИгрок: {}\nБан на: {}\nПричина: {}\n\n{}\n\n← → / Tab — выбор · Enter — принять · Esc — назад",
                self.action.scope(),
                self.action.player,
                if self.action.permanent_ban() {
                    "perm (бессрочно)"
                } else {
                    self.action.duration.as_str()
                },
                self.action.reason,
                if self.yes {
                    "  Нет     [ Да, забанить ]"
                } else {
                    "[ Нет, вернуться ]     Да"
                }
            )
        } else if unban {
            format!(
                "\nОбласть: {}\n\n> Ник: {}\n{}\n\nEnter — снять бан · Esc — отмена",
                self.action.scope(),
                self.action.player,
                self.error
            )
        } else {
            format!(
                "\n{} · {}\n\n{} Ник: {}\n{}{} Причина: {}\n\n{}\n\nTab / ↑ ↓ — поле · Enter — {} · Esc — отмена",
                self.action.scope(),
                self.action.command,
                cursor(0),
                self.action.player,
                if self.action.command == "kick" {
                    String::new()
                } else {
                    format!(
                        "{} Срок: {}  {}\n",
                        cursor(1),
                        self.action.duration,
                        if self.action.command == "ban" {
                            "(10m, 20h, 1d или perm)"
                        } else {
                            "(s/m/h/d/w, до 365d)"
                        }
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
        let lines = body
            .lines()
            .map(|line| {
                if self.action.command == "ban"
                    && (line.contains("Срок:") || line.starts_with("Бан на:"))
                {
                    let mut spans = Vec::new();
                    for (index, part) in line.split("perm").enumerate() {
                        if index != 0 {
                            spans.push(Span::styled(
                                "perm",
                                Style::default().fg(Color::Rgb(235, 114, 119)),
                            ));
                        }
                        spans.push(Span::raw(part));
                    }
                    Line::from(spans)
                } else {
                    Line::raw(line)
                }
            })
            .collect::<Vec<_>>();
        frame.render_widget(
            Paragraph::new(lines)
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
    fn permanent_ban_requires_confirmation_and_a_receipt_without_expiry() {
        let mut form = Form::new("dj2".into(), "ban");
        form.action.player = "TestPlayer".into();
        form.action.duration = "perm".into();
        assert!(form.key(KeyCode::Enter).is_none());
        assert!(form.confirming);
        let mut terminal =
            ratatui::Terminal::new(ratatui::backend::TestBackend::new(96, 28)).unwrap();
        terminal.draw(|frame| form.draw(frame)).unwrap();
        assert!(
            terminal
                .backend()
                .buffer()
                .content
                .iter()
                .any(|cell| { cell.symbol() == "p" && cell.fg == Color::Rgb(235, 114, 119) })
        );
        form.key(KeyCode::Right);
        let request = form.key(KeyCode::Enter).unwrap();
        assert!(request.permanent_ban());
        let mut value = serde_json::json!({
            "schema_version": 1, "action": "owner.project-moderation", "command": "ban",
            "player": "TestPlayer", "ok": true, "effect": "applied", "expires_at": null,
            "error": null, "unreachable": [],
        });
        let receipt = Receipt::parse(&serde_json::to_vec(&value).unwrap(), &request).unwrap();
        assert!(receipt.message().contains("Бессрочный бан"));
        value["expires_at"] = serde_json::json!(2000000000_u64);
        assert!(Receipt::parse(&serde_json::to_vec(&value).unwrap(), &request).is_err());
        let mut mute = Form::new("dj2".into(), "mute");
        mute.action.player = "TestPlayer".into();
        mute.action.duration = "perm".into();
        assert!(mute.key(KeyCode::Enter).is_none());
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
        let good = serde_json::json!({"schema_version":1,"action":"owner.project-moderation","unreachable":[],"command":"ban","player":"TestPlayer","ok":true,"effect":"applied","expires_at":2000000000_u64,"error":null});
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
    #[test]
    fn unban_needs_only_a_name_and_no_duration_or_ban_confirmation() {
        let mut form = Form::new("alpha".into(), "unban");
        assert!(form.action.duration.is_empty());
        assert!(form.key(KeyCode::Enter).is_none());
        form.action.player = "OfflinePlayer".into();
        form.key(KeyCode::Tab);
        assert_eq!(form.field, 0);
        let request = form.key(KeyCode::Enter).unwrap();
        assert_eq!(request.command, "unban");
        assert!(request.duration.is_empty());
        assert!(!form.confirming);
    }
}
