use std::{path::Path, path::PathBuf};

use ratatui::{
    Frame,
    crossterm::event::KeyCode,
    layout::{Constraint, Layout, Rect},
    style::{Color, Style},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};
use serde::Deserialize;

#[derive(Deserialize)]
struct Entry {
    id: String,
    name: Option<String>,
    received_at: String,
    kind: String,
    pack: String,
}

impl Entry {
    fn valid(&self) -> bool {
        valid_id(&self.id)
            && self
                .name
                .as_deref()
                .is_none_or(crate::moderation::valid_player)
            && self.received_at.len() == 25
            && self.received_at.ends_with("+00:00")
            && self
                .received_at
                .bytes()
                .all(|byte| byte.is_ascii_digit() || b"-:T+".contains(&byte))
            && matches!(
                self.kind.as_str(),
                "minecraft_crash" | "jvm_crash" | "abnormal_exit"
            )
            && crate::protocol::valid_server(&self.pack)
    }

    fn label(&self) -> String {
        let cause = match self.kind.as_str() {
            "minecraft_crash" => "Сбой Minecraft",
            "jvm_crash" => "Сбой Java",
            _ => "Игра аварийно закрылась",
        };
        let date = self.received_at[..19].replace('T', " ");
        let player = self.name.as_deref().unwrap_or("Ник неизвестен");
        format!("{date}  {player}  {}  {cause}", self.pack)
    }
}

/// Metadata from the private report inbox.
#[derive(Deserialize)]
pub struct Listing {
    pub ok: bool,
    directory: Option<PathBuf>,
    #[serde(default)]
    reports: Vec<Entry>,
}

impl Listing {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let value: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный список отчётов")?;
        if value.ok
            && (!value.directory.as_deref().is_some_and(valid_path)
                || value.reports.len() > 20
                || !value.reports.iter().all(Entry::valid))
        {
            return Err("Неверный список отчётов".into());
        }
        Ok(value)
    }
}

/// The file exported by the owner backend for a selected report.
#[derive(Deserialize)]
pub struct Export {
    pub ok: bool,
    report_file: Option<PathBuf>,
}

impl Export {
    pub fn parse(bytes: &[u8], id: &str, windows: bool) -> Result<Self, String> {
        let value: Self = serde_json::from_slice(bytes).map_err(|_| "Неверный ответ выгрузки")?;
        if value.ok
            && !value.report_file.as_deref().is_some_and(|path| {
                valid_path(path)
                    && path.file_name().and_then(|name| name.to_str())
                        == Some(&file_name(id, windows))
            })
        {
            return Err("Неверный путь к выгруженному отчёту".into());
        }
        Ok(value)
    }
}

pub fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn valid_path(path: &Path) -> bool {
    path.is_absolute()
        && path
            .to_str()
            .is_some_and(|value| value.len() <= 1024 && !value.chars().any(char::is_control))
}

fn file_name(id: &str, windows: bool) -> String {
    if windows {
        format!("client-crash-{id}.json")
    } else {
        format!("{id}.json")
    }
}

pub enum Input {
    Refresh,
    Export(String),
}

pub struct Panel {
    listing: Option<Listing>,
    selected: usize,
    message: Option<String>,
    windows: bool,
}

impl Panel {
    pub fn new(windows: bool) -> Self {
        Self {
            listing: None,
            selected: 0,
            message: None,
            windows,
        }
    }

    pub fn listed(&mut self, listing: Listing) {
        self.selected = 0;
        self.message = (!listing.ok).then(|| "Не удалось прочитать список. r обновить".into());
        self.listing = listing.ok.then_some(listing);
    }

    pub fn exported(&mut self, export: Export) {
        self.message = Some(match export.report_file.filter(|_| export.ok) {
            Some(_) if self.windows => "Запрос на скачивание отправлен.".into(),
            Some(_) => "Отчёт сохранён.".into(),
            None => "Не удалось выгрузить отчёт. Обновите список по r.".into(),
        });
    }

    pub fn error(&mut self, message: String) {
        self.message = Some(message);
    }

    fn entries(&self) -> &[Entry] {
        self.listing
            .as_ref()
            .map_or(&[], |value| value.reports.as_slice())
    }

    pub fn key(&mut self, key: KeyCode) -> Option<Input> {
        match key {
            KeyCode::Up => self.selected = self.selected.saturating_sub(1),
            KeyCode::Down => {
                self.selected = (self.selected + 1).min(self.entries().len().saturating_sub(1))
            }
            KeyCode::Enter => {
                return Some(Input::Export(self.entries().get(self.selected)?.id.clone()));
            }
            KeyCode::Char('r') => return Some(Input::Refresh),
            _ => return None,
        }
        self.message = None;
        None
    }

    pub fn draw(&self, frame: &mut Frame, loading: bool) {
        let area = frame.area();
        let width = area.width.saturating_sub(2).min(106);
        let height = area.height.min(22);
        let popup = Rect::new(
            area.x + (area.width - width) / 2,
            area.y + (area.height - height) / 2,
            width,
            height,
        );
        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Краш-отчёты игроков ");
        let [heading, list, detail, controls] = Layout::vertical([
            Constraint::Length(2),
            Constraint::Min(1),
            Constraint::Length(8),
            Constraint::Length(1),
        ])
        .areas(block.inner(popup));
        frame.render_widget(Clear, popup);
        frame.render_widget(block, popup);
        frame.render_widget(
            Paragraph::new("Последние полученные отчёты · время UTC"),
            heading,
        );
        let offset = self
            .selected
            .saturating_add(1)
            .saturating_sub(usize::from(list.height));
        let mut lines: Vec<_> = self
            .entries()
            .iter()
            .enumerate()
            .skip(offset)
            .take(list.height.into())
            .map(|(index, entry)| {
                if index == self.selected {
                    Line::styled(
                        format!("› {}", entry.label()),
                        Style::default().fg(Color::Cyan),
                    )
                } else {
                    Line::from(format!("  {}", entry.label()))
                }
            })
            .collect();
        if lines.is_empty() {
            lines.push(Line::from(if self.listing.is_some() {
                "Полученных отчётов пока нет."
            } else if loading {
                "Читаем список..."
            } else {
                "Список недоступен."
            }));
        }
        frame.render_widget(Paragraph::new(lines), list);
        let mut message = self.message.as_deref().unwrap_or("").to_owned();
        if let Some(entry) = self.entries().get(self.selected)
            && let Some(directory) = self
                .listing
                .as_ref()
                .and_then(|value| value.directory.as_ref())
        {
            use std::fmt::Write;
            let _ = writeln!(
                message,
                "\nПуть выгрузки на сервере\n{}",
                directory.join(file_name(&entry.id, self.windows)).display()
            );
            if self.windows {
                let _ = writeln!(
                    message,
                    "Рядом с EXE\nCrashReports\\{}",
                    file_name(&entry.id, true)
                );
            }
        }
        frame.render_widget(Paragraph::new(message).wrap(Wrap { trim: false }), detail);
        let action = if self.windows {
            "скачать"
        } else {
            "выгрузить"
        };
        frame.render_widget(
            Paragraph::new(format!(
                " ↑/↓ выбрать · Enter {action} · r обновить · Esc назад"
            )),
            controls,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn download_uses_the_selected_row_and_keeps_the_two_paths_visible() {
        let directory = std::env::temp_dir();
        let id = "a".repeat(32);
        let other = "b".repeat(32);
        let entry = |id: &str| {
            serde_json::json!({
                "id": id,
                "name": "TestPlayer",
                "received_at": "2026-11-25T07:00:00+00:00",
                "kind": "jvm_crash", "pack": "dj2"
            })
        };
        let listing = serde_json::json!({
            "ok": true, "directory": directory, "reports": [entry(&id), entry(&other)]
        });
        let mut panel = Panel::new(true);
        assert!(panel.key(KeyCode::Enter).is_none());
        panel.listed(Listing::parse(&serde_json::to_vec(&listing).unwrap()).unwrap());
        panel.key(KeyCode::Down);
        assert!(
            matches!(panel.key(KeyCode::Enter), Some(Input::Export(selected)) if selected == other)
        );
        let path = directory.join(file_name(&other, true));
        let receipt = serde_json::json!({"ok": true, "report_file": path});
        let receipt = serde_json::to_vec(&receipt).unwrap();
        assert!(Export::parse(&receipt, &id, true).is_err());
        panel.exported(Export::parse(&receipt, &other, true).unwrap());
        let backend = ratatui::backend::TestBackend::new(110, 30);
        let mut terminal = ratatui::Terminal::new(backend).unwrap();
        terminal.draw(|frame| panel.draw(frame, false)).unwrap();
        let output: String = terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|cell| cell.symbol())
            .collect();
        assert!(output.contains("Запрос на скачивание отправлен."));
        assert!(output.contains("Путь выгрузки на сервере"));
        assert!(output.contains(&format!("CrashReports\\{}", file_name(&other, true))));
    }
}
