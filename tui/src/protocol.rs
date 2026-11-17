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
    pub fn parse(bytes: &[u8], server: &str) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ истории TPS")?;
        let count = v.points.iter().filter(|p| p.tps.is_some()).count();
        let valid = v.schema_version == 1
            && v.action == "owner.tps-history"
            && v.server_id == server
            && valid_server(server)
            && v.step == 5
            && v.end.checked_sub(v.start) == Some(300)
            && v.start.is_multiple_of(5)
            && if v.ok {
                v.error.is_none()
                    && v.points.len() == 61
                    && v.points.iter().enumerate().all(|(i, p)| {
                        p.timestamp == v.start + i as u64 * 5
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
    pub truncated: bool,
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
}

impl ConsoleResult {
    pub fn parse(bytes: &[u8], server: &str, command: &str) -> Result<Self, String> {
        let v: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ команды")?;
        if v.schema_version != 1 || v.action != "owner.console" || v.server_id != server || v.command != command
            || !valid_server(server) || !matches!(command, "players" | "tps" | "save")
            || !matches!(v.effect.as_str(), "none" | "unknown")
            || (command != "save" && v.effect != "none")
            || v.output.chars().count() > 8192
            || v.output.chars().any(|c| (c.is_control() && c != '\n') || matches!(c, '\u{200b}'..='\u{200f}' | '\u{202a}'..='\u{202e}' | '\u{2060}'..='\u{206f}'))
            || if v.ok { v.error.is_some() } else { !v.output.is_empty() || !v.error.as_deref().is_some_and(|e| matches!(e, "invalid_configuration" | "console_unavailable")) }
        { return Err("Нарушен контракт команды v1".into()); }
        Ok(v)
    }
}
