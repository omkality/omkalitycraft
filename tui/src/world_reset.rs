use crate::protocol::valid_server;
use ratatui::{
    Frame,
    crossterm::event::KeyCode,
    layout::Rect,
    style::{Color, Style},
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};
use serde::Deserialize;

#[derive(Clone, Debug)]
pub struct Request {
    pub server: String,
    pub command: &'static str,
    pub confirmation: Option<String>,
    pub world: Option<i32>,
}

impl Request {
    pub fn inspect(server: String) -> Self {
        Self {
            server,
            command: "inspect",
            confirmation: None,
            world: None,
        }
    }

    pub fn valid(&self) -> bool {
        valid_server(&self.server)
            && match self.command {
                "inspect" => self.confirmation.is_none(),
                "prepare" | "apply" | "start" => {
                    self.confirmation.as_deref().is_some_and(|s| hex(s, 64))
                }
                _ => false,
            }
    }

    pub fn mutating(&self) -> bool {
        self.command != "inspect"
    }
}

fn hex(s: &str, length: usize) -> bool {
    s.len() == length
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct World {
    dimension: i32,
    name: String,
    description: String,
}

fn valid_text(text: &str, limit: usize) -> bool {
    !text.is_empty()
        && text.trim() == text
        && text.chars().count() <= limit
        && !text.chars().any(char::is_control)
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Receipt {
    schema_version: u32,
    action: String,
    pub server_id: String,
    command: String,
    pub ok: bool,
    effect: String,
    error: Option<String>,
    dimension: Option<i32>,
    stage: String,
    confirmation: Option<String>,
    maintenance: Option<String>,
    backup: Option<String>,
    resource: Option<String>,
    installation: Option<String>,
    #[serde(default)]
    worlds: Vec<World>,
}

impl Receipt {
    pub fn parse(raw: &[u8], request: &Request) -> Result<Self, String> {
        let value: Self = serde_json::from_slice(raw).map_err(|_| "Неверный ответ вайпа")?;
        if value.schema_version != 1
            || value.action != "owner.world-reset"
            || value.server_id != request.server
            || value.command != request.command
            || !matches!(value.effect.as_str(), "none" | "applied" | "unknown")
            || value.ok != value.error.is_none()
            || value.ok
                && value.effect
                    != if request.mutating() {
                        "applied"
                    } else {
                        "none"
                    }
            || !value.ok && value.effect == "applied"
            || value.error.as_deref().is_some_and(|s| {
                !matches!(
                    s,
                    "invalid_request"
                        | "state_changed"
                        | "ingress_not_drained"
                        | "owner_busy"
                        | "operation_rejected"
                        | "join_closed"
                )
            })
            || !matches!(
                value.stage.as_str(),
                "unconfigured"
                    | "unsupported"
                    | "no-ingress"
                    | "used-target"
                    | "prepare"
                    | "apply"
                    | "start"
                    | "review"
                    | "complete"
            )
            || (value.stage == "unconfigured") != value.dimension.is_none()
            || request.world.is_some_and(|world| {
                value.ok
                    && (Some(world) != value.dimension
                        || !value.worlds.iter().any(|entry| entry.dimension == world))
            })
            || value.worlds.len() > 64
            || value.worlds.iter().enumerate().any(|(index, world)| {
                !valid_text(&world.name, 64)
                    || !valid_text(&world.description, 240)
                    || value.worlds[..index]
                        .iter()
                        .any(|entry| entry.dimension == world.dimension)
            })
            || matches!(value.stage.as_str(), "prepare" | "apply" | "start")
                != value.confirmation.is_some()
            || value.confirmation.as_deref().is_some_and(|s| !hex(s, 64))
            || [
                &value.maintenance,
                &value.backup,
                &value.resource,
                &value.installation,
            ]
            .into_iter()
            .flatten()
            .any(|s| !hex(s, 32))
            || matches!(value.stage.as_str(), "apply" | "start" | "complete")
                && (value.backup.is_none()
                    || value.maintenance.is_none()
                    || value.resource.is_none())
            || matches!(value.stage.as_str(), "start" | "complete") && value.installation.is_none()
            || value.ok
                && request.mutating()
                && !matches!(
                    (request.command, value.stage.as_str()),
                    ("prepare", "apply") | ("apply", "start") | ("start", "complete")
                )
        {
            return Err(
                "Ответ вайпа не соответствует запросу. Откройте состояние мира заново.".into(),
            );
        }
        Ok(value)
    }

    fn label(&self) -> &str {
        match self.stage.as_str() {
            "prepare" => "Подготовить вайп и резервную копию",
            "apply" => "Установить новый мир",
            "start" => "Запустить сервер с новым миром",
            _ => "",
        }
    }

    fn status(&self) -> &str {
        if let Some(error) = self.error.as_deref() {
            return match error {
                "state_changed" => "Состояние изменилось. Откройте вайп заново.",
                "owner_busy" => "Другая операция уже выполняется.",
                "ingress_not_drained" => "Дождитесь, пока все игроки выйдут.",
                "join_closed" => "Новый мир запустился. Игровой вход открыть не удалось.",
                _ if self.effect == "unknown" => {
                    "Этап прервался. Проверьте состояние и журналы перед продолжением."
                }
                _ => "Проверьте настройки резервного копирования и вайпа.",
            };
        }
        match self.stage.as_str() {
            "unconfigured" => "Для этого сервера вайп не настроен.",
            "unsupported" => "Этот мир требует отдельной процедуры сброса.",
            "no-ingress" => "Настройте управление игровым входом.",
            "used-target" => "Не удалось подготовить следующий вайп.",
            "prepare" => {
                if self.dimension == Some(0) {
                    "Выйдите с сервера.\nВайп сбросит все миры и игровой прогресс.\nСервер остановится и создаст резервную копию."
                } else {
                    "Выйдите с сервера.\nСервер остановится и создаст резервную копию."
                }
            }
            "apply" => {
                "Копия проверена. Прежний мир сохранится в истории. Сервер останется остановленным."
            }
            "start" => {
                "Новый мир установлен. Запуск проверит его. Игровой вход откроется после проверки."
            }
            "complete" => "Сервер запущен с новым миром.",
            _ => "Этап требует проверки в журналах владельца.",
        }
    }
}

pub struct Form {
    receipt: Receipt,
    confirming: bool,
    yes: bool,
}

impl Form {
    pub fn new(receipt: Receipt) -> Self {
        Self {
            receipt,
            confirming: false,
            yes: false,
        }
    }

    pub fn key(&mut self, key: KeyCode) -> Option<Request> {
        let worlds = &self.receipt.worlds;
        let selected = worlds
            .iter()
            .position(|entry| Some(entry.dimension) == self.receipt.dimension);
        if !self.confirming && worlds.len() > 1 && matches!(key, KeyCode::Up | KeyCode::Down) {
            let index = match (key, selected) {
                (KeyCode::Up, Some(index)) => (index + worlds.len() - 1) % worlds.len(),
                (_, Some(index)) => (index + 1) % worlds.len(),
                (_, None) => 0,
            };
            let mut request = Request::inspect(self.receipt.server_id.clone());
            request.world = Some(worlds[index].dimension);
            return Some(request);
        }
        if !self.receipt.ok || self.receipt.confirmation.is_none() {
            return None;
        }
        match (self.confirming, key) {
            (true, KeyCode::Left | KeyCode::Right | KeyCode::Tab) => self.yes = !self.yes,
            (true, KeyCode::Enter) if self.yes => {
                return Some(Request {
                    server: self.receipt.server_id.clone(),
                    command: match self.receipt.stage.as_str() {
                        "prepare" => "prepare",
                        "apply" => "apply",
                        "start" => "start",
                        _ => return None,
                    },
                    confirmation: self.receipt.confirmation.clone(),
                    world: selected.map(|index| worlds[index].dimension),
                });
            }
            (_, KeyCode::Enter) => {
                self.confirming = !self.confirming;
                self.yes = false;
            }
            _ => {}
        }
        None
    }

    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        let w = area.width.saturating_sub(4).min(82);
        let h = 21.min(area.height);
        let popup = Rect::new((area.width - w) / 2, (area.height - h) / 2, w, h);
        let mut body = format!("\nСервер  {}\n", self.receipt.server_id);
        let worlds = &self.receipt.worlds;
        if let Some(index) = worlds
            .iter()
            .position(|world| Some(world.dimension) == self.receipt.dimension)
        {
            let world = &worlds[index];
            body.push_str(&format!(
                "Мир  {} ({} из {})\n{}\n",
                world.name,
                index + 1,
                worlds.len(),
                world.description
            ));
        } else if let Some(dimension) = self.receipt.dimension {
            if self.receipt.stage == "unsupported" {
                body.push_str(&format!("Мир  DIM{dimension}\n"));
            } else {
                body.push_str(&format!("Мир  Ресурсный мир DJ2 (DIM{dimension})\n"));
                body.push_str(
                    "Мир для добычи ресурсов. После вайпа его чанки сгенерируются заново.\n",
                );
            }
        }
        body.push_str(&format!("\n{}\n", self.receipt.status()));
        if self.confirming {
            let choices = if self.yes {
                "  Нет      [ Да, выполнить ]"
            } else {
                "[ Нет, вернуться ]       Да"
            };
            body.push_str(&format!(
                "\n{}\n{choices}\n← → / Tab · Enter · Esc",
                self.receipt.label()
            ));
        } else {
            if self.receipt.ok && self.receipt.confirmation.is_some() {
                body.push_str(&format!("\nEnter — {}\n", self.receipt.label()));
            }
            if worlds.len() > 1 {
                body.push_str("\n↑ ↓ — выбрать мир");
            }
            body.push_str("\nEsc — закрыть");
        }
        frame.render_widget(Clear, popup);
        frame.render_widget(
            Paragraph::new(body)
                .wrap(Wrap { trim: false })
                .block(
                    Block::default()
                        .borders(Borders::ALL)
                        .title(if self.confirming {
                            " Вайп · Вы уверены? "
                        } else {
                            " Вайп мира "
                        }),
                )
                .style(
                    Style::default()
                        .bg(Color::Rgb(18, 24, 31))
                        .fg(Color::Rgb(218, 226, 235)),
                ),
            popup,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sealed() -> serde_json::Value {
        serde_json::json!({
            "schema_version": 1,
            "action": "owner.world-reset",
            "server_id": "dj2",
            "command": "inspect",
            "ok": true,
            "effect": "none",
            "error": null,
            "dimension": -18000,
            "stage": "apply",
            "confirmation": "a".repeat(64),
            "maintenance": "b".repeat(32),
            "backup": "c".repeat(32),
            "resource": "d".repeat(32),
            "installation": null
        })
    }

    #[test]
    fn world_picker_keeps_selection_and_refuses_a_reply_for_another_world() {
        let mut value = sealed();
        value["worlds"] = serde_json::json!([
            {"dimension": -18000, "name": "Ресурсы", "description": "Добыча ресурсов"},
            {"dimension": 0, "name": "Основной мир", "description": "Общий мир игроков"}
        ]);
        let query = Request::inspect("dj2".into());
        let receipt = Receipt::parse(&serde_json::to_vec(&value).unwrap(), &query).unwrap();
        let mut form = Form::new(receipt);
        let next = form.key(KeyCode::Down).unwrap();
        assert_eq!(next.world, Some(0));
        assert!(!next.mutating());
        assert!(Receipt::parse(&serde_json::to_vec(&value).unwrap(), &next).is_err());
        value["dimension"] = serde_json::json!(0);
        value["stage"] = serde_json::json!("unsupported");
        value["confirmation"] = serde_json::Value::Null;
        let selected = Receipt::parse(&serde_json::to_vec(&value).unwrap(), &next).unwrap();
        assert!(Form::new(selected).key(KeyCode::Enter).is_none());
    }

    #[test]
    fn installation_requires_explicit_yes_and_keeps_original_binding() {
        let query = Request::inspect("dj2".into());
        let receipt = Receipt::parse(&serde_json::to_vec(&sealed()).unwrap(), &query).unwrap();
        let mut form = Form::new(receipt);
        assert!(form.key(KeyCode::Enter).is_none());
        assert!(form.key(KeyCode::Enter).is_none());
        assert!(form.key(KeyCode::Enter).is_none());
        assert!(form.key(KeyCode::Right).is_none());
        let command = form.key(KeyCode::Enter).unwrap();
        assert!(command.valid());
        assert_eq!(command.server, "dj2");
        assert_eq!(command.command, "apply");
        assert_eq!(command.confirmation, Some("a".repeat(64)));
    }

    #[test]
    fn receipt_rejects_a_missing_backup_or_another_server() {
        let query = Request::inspect("dj2".into());
        let mut value = sealed();
        value["backup"] = serde_json::Value::Null;
        assert!(Receipt::parse(&serde_json::to_vec(&value).unwrap(), &query).is_err());
        let mut value = sealed();
        value["server_id"] = serde_json::json!("other");
        assert!(Receipt::parse(&serde_json::to_vec(&value).unwrap(), &query).is_err());
    }

    #[test]
    fn selected_world_confirmation_carries_the_exact_dimension() {
        for dimension in [0, -1, 420, 49000] {
            let mut value = sealed();
            value["dimension"] = serde_json::json!(dimension);
            value["worlds"] = serde_json::json!([
                {"dimension": dimension, "name": "Выбранный мир", "description": "Сохранение мира"}
            ]);
            let mut query = Request::inspect("dj2".into());
            query.world = Some(dimension);
            let receipt = Receipt::parse(&serde_json::to_vec(&value).unwrap(), &query).unwrap();
            let mut form = Form::new(receipt);
            assert!(form.key(KeyCode::Enter).is_none());
            assert!(form.key(KeyCode::Right).is_none());
            let request = form.key(KeyCode::Enter).unwrap();
            assert_eq!(request.world, Some(dimension));
            assert_eq!(request.command, "apply");
            assert_eq!(request.confirmation, Some("a".repeat(64)));
        }
    }
}
