use serde::{Deserialize, Deserializer};

fn required_option<'de, T: Deserialize<'de>, D: Deserializer<'de>>(
    d: D,
) -> Result<Option<T>, D::Error> {
    Option::deserialize(d)
}

pub fn valid_server(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 48
        && s.as_bytes()[0].is_ascii_alphanumeric()
        && !s.as_bytes()[0].is_ascii_uppercase()
        && s.bytes()
            .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == b'_' || c == b'-')
}

fn identity(s: &str) -> bool {
    s.len() == 32
        && s.bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Operation {
    pub id: String,
    pub kind: String,
    #[serde(deserialize_with = "required_option")]
    pub server_id: Option<String>,
    #[serde(deserialize_with = "required_option")]
    pub phase: Option<String>,
    #[serde(deserialize_with = "required_option")]
    pub terminal: Option<bool>,
    #[serde(deserialize_with = "required_option")]
    pub backup_operation_id: Option<String>,
}

impl Operation {
    pub fn valid(&self) -> bool {
        let phases: &[&str] = match self.kind.as_str() {
            "backups" => &[
                "planned",
                "preparing",
                "publishing",
                "published",
                "acknowledging",
                "incomplete",
                "complete",
                "cancelled",
            ],
            "maintenance" => &[
                "planned",
                "stop-requested",
                "stopped",
                "start-requested",
                "complete",
                "cancelled",
            ],
            "restores" => &["planned", "applying", "incomplete", "staged"],
            _ => return false,
        };
        identity(&self.id)
            && self.server_id.as_deref().is_none_or(valid_server)
            && self.backup_operation_id.as_deref().is_none_or(identity)
            && match &self.phase {
                None => self.terminal.is_none(),
                Some(p) => {
                    phases.contains(&p.as_str())
                        && self.terminal
                            == Some(matches!(p.as_str(), "complete" | "cancelled" | "staged"))
                }
            }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Metric {
    pub key: String,
    #[serde(deserialize_with = "required_option")]
    pub value: Option<f64>,
    pub state: String,
}

pub const METRICS: [&str; 6] = [
    "host_cpu",
    "host_ram",
    "host_disk",
    "game_tps",
    "game_mspt",
    "game_players",
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TpsPoint {
    pub timestamp: u64,
    #[serde(deserialize_with = "required_option")]
    pub tps: Option<f64>,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TpsWindow {
    pub key: &'static str,
    pub seconds: u64,
    pub step: u32,
    pub label: &'static str,
    pub first: &'static str,
    pub middle: &'static str,
}

pub const TPS_WINDOWS: [TpsWindow; 4] = [
    TpsWindow {
        key: "5m",
        seconds: 300,
        step: 5,
        label: "5 минут",
        first: "−5 мин",
        middle: "−2:30",
    },
    TpsWindow {
        key: "15m",
        seconds: 900,
        step: 15,
        label: "15 минут",
        first: "−15 мин",
        middle: "−7:30",
    },
    TpsWindow {
        key: "1h",
        seconds: 3600,
        step: 60,
        label: "1 час",
        first: "−1 ч",
        middle: "−30 мин",
    },
    TpsWindow {
        key: "3h",
        seconds: 10800,
        step: 180,
        label: "3 часа",
        first: "−3 ч",
        middle: "−1:30 ч",
    },
];

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TpsHistory {
    pub schema_version: u32,
    pub action: String,
    pub server_id: String,
    pub ok: bool,
    pub state: String,
    pub start: u64,
    pub end: u64,
    pub step: u32,
    pub points: Vec<TpsPoint>,
    #[serde(deserialize_with = "required_option")]
    pub error: Option<String>,
}

impl TpsHistory {
    pub fn parse(bytes: &[u8], server: &str, window: TpsWindow) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ истории TPS")?;
        let count = v.points.iter().filter(|p| p.tps.is_some()).count();
        let valid = v.schema_version == 1
            && v.action == "owner.tps-history"
            && v.server_id == server
            && valid_server(server)
            && TPS_WINDOWS.contains(&window)
            && v.step == window.step
            && v.end.checked_sub(v.start) == Some(window.seconds)
            && v.start.is_multiple_of(5)
            && if v.ok {
                v.error.is_none()
                    && v.points.len() == 61
                    && v.points.iter().enumerate().all(|(i, p)| {
                        p.timestamp == v.start + i as u64 * u64::from(window.step)
                            && p.tps
                                .is_none_or(|n| n.is_finite() && (0.0..=20.0).contains(&n))
                    })
                    && match v.state.as_str() {
                        "available" => count == 61,
                        "partial" => count > 0 && count < 61,
                        "missing" | "disabled" => count == 0,
                        _ => false,
                    }
            } else {
                v.state == "unavailable"
                    && v.points.is_empty()
                    && v.error.as_deref().is_some_and(|e| {
                        matches!(e, "invalid_configuration" | "history_unavailable")
                    })
            };
        if valid {
            Ok(v)
        } else {
            Err("Нарушен контракт истории TPS".into())
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Overview {
    pub schema_version: u32,
    pub action: String,
    pub ok: bool,
    pub server_ids: Vec<String>,
    pub operations: Vec<Operation>,
    pub skipped: u32,
    #[serde(rename = "truncated")]
    _truncated: bool,
    #[serde(deserialize_with = "required_option")]
    pub selected_server: Option<String>,
    pub metrics_status: String,
    pub metrics: Vec<Metric>,
    #[serde(deserialize_with = "required_option")]
    pub error: Option<String>,
}

impl Overview {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let value: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный JSON обзора")?;
        let valid =
            value.schema_version == 1
                && value.action == "owner.overview"
                && value.server_ids.len() <= 100
                && value.operations.len() <= 128
                && value.skipped <= 128
                && value.server_ids.iter().all(|s| valid_server(s))
                && value.server_ids.windows(2).all(|w| w[0] < w[1])
                && value.operations.iter().all(|o| {
                    o.valid()
                        && o.phase.is_some()
                        && o.server_id
                            .as_ref()
                            .is_some_and(|s| value.server_ids.contains(s))
                })
                && !value.operations.iter().enumerate().any(|(i, o)| {
                    value.operations[..i]
                        .iter()
                        .any(|p| p.kind == o.kind && p.id == o.id)
                })
                && value
                    .selected_server
                    .as_ref()
                    .is_none_or(|s| value.server_ids.contains(s))
                && matches!(
                    value.metrics_status.as_str(),
                    "disabled" | "available" | "partial" | "unavailable"
                )
                && value.metrics.len() <= 6
                && value.metrics.iter().enumerate().all(|(i, m)| {
                    METRICS.contains(&m.key.as_str())
                        && !value.metrics[..i].iter().any(|p| p.key == m.key)
                        && match m.state.as_str() {
                            "fresh" => m.value.is_some_and(|v| {
                                v.is_finite()
                                    && v >= 0.0
                                    && v <= match m.key.as_str() {
                                        "host_cpu" | "host_ram" | "host_disk" => 100.0,
                                        "game_tps" => 20.0,
                                        _ => 1e9,
                                    }
                            }),
                            "missing" | "stale" | "invalid" => m.value.is_none(),
                            _ => false,
                        }
                })
                && if value.ok {
                    value.error.is_none()
                        && (value.server_ids.is_empty() == value.selected_server.is_none())
                        && value.metrics.len() == 6
                        && (value.metrics_status != "available"
                            || value.metrics.iter().all(|m| m.state == "fresh"))
                } else {
                    value.error.as_deref().is_some_and(|e| {
                        matches!(e, "invalid_configuration" | "overview_unavailable")
                    }) && value.operations.is_empty()
                        && value.server_ids.is_empty()
                        && value.metrics.is_empty()
                        && value.selected_server.is_none()
                };
        if valid {
            Ok(value)
        } else {
            Err("Нарушен контракт обзора v1".into())
        }
    }
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InvitationEntry {
    pub reference: String,
    pub code: String,
    pub date: String,
}

impl InvitationEntry {
    fn valid(&self) -> bool {
        self.reference.len() == 12
            && self
                .reference
                .bytes()
                .all(|b| b.is_ascii_digit() || matches!(b, b'a'..=b'f'))
            && valid_invite_code(&self.code)
            && self.date.len() == 10
            && self.date.bytes().enumerate().all(|(i, b)| {
                if matches!(i, 4 | 7) {
                    b == b'-'
                } else {
                    b.is_ascii_digit()
                }
            })
    }
}

pub fn valid_invite_code(code: &str) -> bool {
    (1..=128).contains(&code.len())
        && code
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-'))
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ConsoleResult {
    pub schema_version: u32,
    pub action: String,
    pub server_id: String,
    pub command: String,
    pub ok: bool,
    pub effect: String,
    pub output: String,
    #[serde(deserialize_with = "required_option")]
    pub error: Option<String>,
    pub invitations: Option<Vec<InvitationEntry>>,
}

impl ConsoleResult {
    pub fn parse(bytes: &[u8], server: &str, command: &str) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ команды")?;
        if v.schema_version != 1
            || v.action != "owner.console"
            || v.server_id != server
            || v.command != command
            || !valid_server(server)
            || !matches!(
                command,
                "players"
                    | "roster"
                    | "permanent-bans"
                    | "invites"
                    | "player-names"
                    | "tps"
                    | "save"
                    | "backup-status"
            )
            || !matches!(v.effect.as_str(), "none" | "unknown")
            || (command != "save" && v.effect != "none")
            || if command == "invites" && v.ok {
                !v.output.is_empty()
                    || !v.invitations.as_ref().is_some_and(|rows| {
                        let mut references = std::collections::HashSet::new();
                        rows.len() <= 1000
                            && rows
                                .iter()
                                .all(|row| row.valid() && references.insert(row.reference.as_str()))
                    })
            } else {
                v.invitations.is_some()
            }
            || if command == "player-names" {
                !valid_player_names(&v.output)
            } else {
                !valid_terminal_output(&v.output)
            }
            || if v.ok {
                v.error.is_some()
            } else {
                !v.output.is_empty()
                    || !v.error.as_deref().is_some_and(|e| {
                        matches!(e, "invalid_configuration" | "console_unavailable")
                    })
            }
        {
            return Err("Нарушен контракт команды v1".into());
        }
        Ok(v)
    }

    pub fn player_names(&self) -> Option<Vec<String>> {
        (self.ok && self.command == "player-names").then(|| {
            self.output
                .split_terminator('\n')
                .map(str::to_owned)
                .collect()
        })
    }

    pub fn membership_message(&self) -> Option<String> {
        if !self.ok {
            return None;
        }
        match self.command.as_str() {
            "roster" => Some(format!("Игроки проекта\n\n{}", self.output)),
            "permanent-bans" => Some(format!(
                "Бессрочные баны\n\n{}\n\nu — снять бан",
                self.output
            )),
            _ => None,
        }
    }
}

fn valid_player_names(output: &str) -> bool {
    output.len() < 17_000
        && output.split_terminator('\n').count() <= 1000
        && output
            .split_terminator('\n')
            .all(crate::moderation::valid_player)
}

fn valid_terminal_output(value: &str) -> bool {
    value.chars().count() <= 8192
        && !value.chars().any(|c| {
            (c.is_control() && c != '\n')
                || matches!(c, '\u{200b}'..='\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2060}'..='\u{206f}')
        })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlayerStatsResult {
    schema_version: u32,
    action: String,
    server_id: String,
    player: String,
    pub ok: bool,
    output: String,
    #[serde(deserialize_with = "required_option")]
    error: Option<String>,
}

impl PlayerStatsResult {
    pub fn parse(bytes: &[u8], server: &str, player: &str) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ статистики")?;
        let valid_payload = if v.ok {
            v.error.is_none() && !v.output.is_empty() && valid_terminal_output(&v.output)
        } else {
            v.output.is_empty()
                && matches!(
                    v.error.as_deref(),
                    Some("invalid_request" | "profile_not_found" | "profile_unavailable")
                )
        };
        if v.schema_version != 1
            || v.action != "owner.player-stats"
            || v.server_id != server
            || v.player != player
            || !valid_server(server)
            || !crate::moderation::valid_player(player)
            || !valid_payload
        {
            return Err("Ответ статистики не соответствует запросу".into());
        }
        Ok(v)
    }

    pub fn message(self) -> String {
        match self.error.as_deref() {
            Some("profile_not_found") => format!("Игрок {} не зарегистрирован.", self.player),
            Some("invalid_request") => "Проверьте ник игрока и выбранный сервер.".into(),
            Some(_) => "Не удалось проверить профиль игрока.".into(),
            None => self.output,
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct InvitationResult {
    pub ok: bool,
    invitation_file: Option<String>,
    code: Option<String>,
    single_use: Option<bool>,
    error: Option<String>,
    error_type: Option<String>,
}

impl InvitationResult {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let value: Self =
            serde_json::from_slice(bytes).map_err(|_| "Неверный ответ выдачи приглашения")?;
        let valid = if value.ok {
            value.error.is_none()
                && value.error_type.is_none()
                && value.single_use == Some(true)
                && value.code.as_deref().is_some_and(|code| {
                    (1..=128).contains(&code.len())
                        && code.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
                })
                && value.invitation_file.as_deref().is_some_and(|file| {
                    use std::path::Path;
                    let path = Path::new(file);
                    path.is_absolute()
                        && path.extension().is_some_and(|ext| ext == "json")
                        && path.parent().and_then(Path::file_name).is_some_and(|dir| dir == "invitations")
                        && !file.chars().any(|c| c.is_control() || matches!(c, '\u{200b}'..='\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2060}'..='\u{206f}'))
                })
        } else {
            value.invitation_file.is_none()
                && value.code.is_none()
                && value.single_use.is_none()
                && value.error.is_some()
                && value.error_type.is_some()
        };
        if !valid {
            return Err("Нарушен формат ответа выдачи приглашения".into());
        }
        Ok(value)
    }

    pub fn code(&self) -> Option<&str> {
        self.code.as_deref()
    }

    pub fn message(&self, clipboard_status: Option<&str>) -> String {
        if let (Some(code), Some(path)) = (&self.code, &self.invitation_file) {
            let clipboard = clipboard_status.unwrap_or_default();
            format!("Одноразовый ключ создан.\n\n{code}\n{clipboard}\n\nФайл:\n{path}")
        } else if matches!(
            self.error.as_deref(),
            Some("Authentication origin is not configured")
        ) {
            "Для выдачи ключа настройте Drasl в operator.toml и выполните вход владельца.".into()
        } else {
            "Выдача ключа не подтверждена.\nПроверьте доступ к Drasl и список access invites перед повтором.".into()
        }
    }
}
