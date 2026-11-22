use std::{
    collections::HashSet,
    time::{SystemTime, UNIX_EPOCH},
};

use ratatui::{
    Frame,
    crossterm::event::KeyCode,
    layout::{Constraint, Layout, Rect},
    style::{Color, Style},
    text::{Line, Span},
    widgets::{List, Paragraph},
};
use serde::Deserialize;

const ACCENT: Color = Color::Rgb(114, 205, 220);
const MUTED: Color = Color::Rgb(139, 155, 172);
const BAN: Color = Color::Rgb(235, 114, 119);
const MUTE: Color = Color::Rgb(237, 184, 104);

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Profile {
    profile: String,
    player: String,
    ban_until: Option<u64>,
    permanent: bool,
    lock_pending: bool,
    mute_until: Option<u64>,
}

impl Profile {
    fn ban(&self, now: u64) -> bool {
        self.permanent || self.ban_until.is_some_and(|until| until > now)
    }
    fn mute(&self, now: u64) -> bool {
        self.mute_until.is_some_and(|until| until > now)
    }
}

pub fn valid_profile(value: &str) -> bool {
    value.len() == 36
        && value.bytes().enumerate().all(|(index, byte)| {
            if matches!(index, 8 | 13 | 18 | 23) {
                byte == b'-'
            } else {
                byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
            }
        })
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Snapshot {
    schema_version: u32,
    action: String,
    pub ok: bool,
    profiles: Vec<Profile>,
}

impl Snapshot {
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let value: Self =
            serde_json::from_slice(bytes).map_err(|_| "Неверный список ограничений")?;
        let mut seen = HashSet::new();
        if value.schema_version != 1
            || value.action != "owner.project-restrictions"
            || value.profiles.len() > 2300
            || !value.ok && !value.profiles.is_empty()
            || value.profiles.iter().any(|entry| {
                !valid_profile(&entry.profile)
                    || !crate::moderation::valid_player(&entry.player)
                    || !seen.insert(&entry.profile)
                    || entry.permanent && entry.ban_until.is_some()
                    || entry.lock_pending && !entry.permanent
                    || !entry.permanent && entry.ban_until.is_none() && entry.mute_until.is_none()
                    || [entry.ban_until, entry.mute_until]
                        .into_iter()
                        .flatten()
                        .any(|date| !(1..=253402300799).contains(&date))
            })
        {
            return Err("Список ограничений не соответствует запросу".into());
        }
        Ok(value)
    }
}

#[derive(Default, PartialEq, Eq)]
enum Filter {
    #[default]
    All,
    Ban,
    Mute,
}

pub enum Input {
    Refresh,
    Restore {
        command: &'static str,
        player: String,
        profile: String,
    },
}

#[derive(Default)]
pub struct Panel {
    profiles: Vec<Profile>,
    available: bool,
    selected: usize,
    offset: usize,
    filter: Filter,
    query: String,
    searching: bool,
}

fn now() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

impl Panel {
    pub fn update(&mut self, snapshot: Option<Snapshot>) {
        let time = now();
        let selected = self
            .filtered(time)
            .get(self.selected)
            .map(|entry| entry.profile.clone());
        self.available = snapshot.as_ref().is_some_and(|snapshot| snapshot.ok);
        self.profiles = snapshot.map_or_else(Vec::new, |value| value.profiles);
        if let Some(profile) = selected
            && let Some(index) = self
                .filtered(time)
                .iter()
                .position(|entry| entry.profile == profile)
        {
            self.selected = index;
        }
    }

    pub fn cancel_search(&mut self) -> bool {
        if self.searching {
            self.query.clear();
            self.selected = 0;
            self.searching = false;
            return true;
        }
        false
    }

    fn filtered(&self, time: u64) -> Vec<&Profile> {
        let query = self.query.to_ascii_lowercase();
        self.profiles
            .iter()
            .filter(|entry| {
                let ban = entry.ban(time);
                let mute = entry.mute(time);
                (match self.filter {
                    Filter::All => ban || mute,
                    Filter::Ban => ban,
                    Filter::Mute => mute,
                }) && entry.player.to_ascii_lowercase().contains(&query)
            })
            .collect()
    }

    pub fn key(&mut self, key: KeyCode, shortcut: KeyCode, idle: bool) -> Option<Input> {
        if self.searching {
            match key {
                KeyCode::Enter => self.searching = false,
                KeyCode::Backspace => {
                    self.query.pop();
                    self.selected = 0;
                }
                KeyCode::Char(c)
                    if self.query.len() < 16 && (c.is_ascii_alphanumeric() || c == '_') =>
                {
                    self.query.push(c);
                    self.selected = 0;
                }
                _ => {}
            }
            return None;
        }
        let time = now();
        match shortcut {
            KeyCode::Tab => {
                self.filter = match self.filter {
                    Filter::All => Filter::Ban,
                    Filter::Ban => Filter::Mute,
                    Filter::Mute => Filter::All,
                };
                self.selected = 0;
            }
            KeyCode::Char('f' | '/') => self.searching = true,
            KeyCode::Char('r' | '4') if idle => return Some(Input::Refresh),
            KeyCode::Char('u' | 'n') if idle => {
                let entries = self.filtered(time);
                let entry = entries.get(self.selected.min(entries.len().saturating_sub(1)))?;
                let command = match shortcut {
                    KeyCode::Char('u') if entry.ban(time) => "unban",
                    KeyCode::Char('n') if entry.mute(time) => "unmute",
                    _ => return None,
                };
                return Some(Input::Restore {
                    command,
                    player: entry.player.clone(),
                    profile: entry.profile.clone(),
                });
            }
            KeyCode::Up => self.selected = self.selected.saturating_sub(1),
            KeyCode::PageUp => self.selected = self.selected.saturating_sub(10),
            KeyCode::Down | KeyCode::PageDown => {
                let step = if key == KeyCode::Down { 1 } else { 10 };
                self.selected =
                    (self.selected + step).min(self.filtered(time).len().saturating_sub(1));
            }
            _ => {}
        }
        None
    }

    pub fn draw(&mut self, frame: &mut Frame, area: Rect) {
        let regions = Layout::vertical([
            Constraint::Length(3),
            Constraint::Min(1),
            Constraint::Length(2),
        ])
        .split(area);
        let time = now();
        let entries = self.filtered(time);
        let selected = self.selected.min(entries.len().saturating_sub(1));
        let visible = usize::from(regions[1].height).max(1);
        let offset = self
            .offset
            .min(selected)
            .max((selected + 1).saturating_sub(visible));
        let tabs = [
            (Filter::All, "Все"),
            (Filter::Ban, "Баны"),
            (Filter::Mute, "Муты"),
        ]
        .map(|(filter, label)| {
            if self.filter == filter {
                Span::styled(format!("[{label}]  "), Style::default().fg(ACCENT))
            } else {
                Span::styled(format!(" {label}   "), Style::default().fg(MUTED))
            }
        });
        let query = if self.query.is_empty() && !self.searching {
            "—"
        } else {
            &self.query
        };
        let search_label = "Поиск: ";
        frame.render_widget(
            Paragraph::new(vec![
                Line::styled(
                    "Ограничения игроков · весь проект",
                    Style::default().fg(ACCENT),
                ),
                Line::from(tabs.to_vec()),
                Line::raw(format!(
                    "{search_label}{query}   ·   Найдено: {}",
                    entries.len(),
                )),
            ]),
            regions[0],
        );
        let cursor_column = (search_label.chars().count() + self.query.len()) as u16;
        if self.searching && regions[0].height >= 3 && cursor_column < regions[0].width {
            frame.set_cursor_position((regions[0].x + cursor_column, regions[0].y + 2));
        }
        if entries.is_empty() {
            let text = if !self.available {
                "Не удалось загрузить ограничения."
            } else if self.query.is_empty() {
                "Действующих ограничений нет."
            } else {
                "Совпадений нет."
            };
            frame.render_widget(Paragraph::new(text), regions[1]);
        } else {
            let lines =
                entries
                    .iter()
                    .enumerate()
                    .skip(offset)
                    .take(visible)
                    .map(|(index, entry)| {
                        let ban = if entry.lock_pending {
                            "Пермач · проверка".into()
                        } else if entry.permanent {
                            "Пермач".into()
                        } else {
                            remaining("Бан", entry.ban_until, time)
                        };
                        let muted = remaining("Мут", entry.mute_until, time);
                        let marker = if selected == index { "›" } else { " " };
                        Line::from(vec![
                            Span::styled(
                                format!("{marker} {:<16} ", entry.player),
                                Style::default().fg(if selected == index {
                                    ACCENT
                                } else {
                                    Color::White
                                }),
                            ),
                            Span::styled(format!("{ban:<19}"), Style::default().fg(BAN)),
                            Span::styled(muted, Style::default().fg(MUTE)),
                        ])
                    });
            frame.render_widget(List::new(lines), regions[1]);
        }
        let selected_entry = entries.get(selected);
        let controls = if self.searching {
            vec![
                Line::raw("Введите часть ника"),
                Line::raw("Enter применить · Esc очистить"),
            ]
        } else {
            vec![
                Line::raw("↑↓ выбор · Tab фильтр · f поиск"),
                Line::from(vec![
                    Span::styled(
                        "u снять бан",
                        Style::default().fg(if selected_entry.is_some_and(|e| e.ban(time)) {
                            ACCENT
                        } else {
                            MUTED
                        }),
                    ),
                    Span::raw(" · "),
                    Span::styled(
                        "n снять мут",
                        Style::default().fg(if selected_entry.is_some_and(|e| e.mute(time)) {
                            ACCENT
                        } else {
                            MUTED
                        }),
                    ),
                    Span::raw(" · r обновить"),
                ]),
            ]
        };
        frame.render_widget(Paragraph::new(controls), regions[2]);
        self.offset = offset;
        self.selected = selected;
    }
}

fn remaining(label: &str, until: Option<u64>, time: u64) -> String {
    let Some(seconds) = until
        .filter(|until| *until > time)
        .map(|until| until - time)
    else {
        return "—".into();
    };
    let minutes = seconds / 60;
    let duration = match minutes {
        0 => "<1м".into(),
        1..60 => format!("{minutes}м"),
        60..1440 => format!("{}ч {:02}м", minutes / 60, minutes % 60),
        _ => format!("{}д {}ч", minutes / 1440, minutes % 1440 / 60),
    };
    format!("{label} {duration}")
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::{Terminal, backend::TestBackend};

    #[test]
    fn scrolling_keeps_commands_visible_and_actions_bind_to_the_selected_profile() {
        let mut panel = Panel::default();
        let profiles = (0..100)
            .map(|index| Profile {
                profile: format!("12345678-1234-4234-8234-{index:012x}"),
                player: format!("Test{index:03}"),
                permanent: index == 99,
                lock_pending: false,
                ban_until: None,
                mute_until: Some(253402300799),
            })
            .collect();
        panel.update(Some(Snapshot {
            schema_version: 1,
            action: "owner.project-restrictions".into(),
            ok: true,
            profiles,
        }));
        let mut terminal = Terminal::new(TestBackend::new(65, 12)).unwrap();
        for _ in 0..10 {
            panel.key(KeyCode::PageDown, KeyCode::PageDown, true);
        }
        terminal.draw(|f| panel.draw(f, f.area())).unwrap();
        let buffer = terminal.backend().buffer();
        let row = |line| {
            (0..65)
                .map(|column| buffer[(column, line)].symbol())
                .collect::<String>()
        };
        assert!(row(11).contains("u снять бан · n снять мут"));
        assert!(row(9).contains("Test099") && row(9).contains("Пермач") && row(9).contains("Мут"));
        let key = KeyCode::Char('n');
        assert!(matches!(
            panel.key(key, key, true),
            Some(Input::Restore { command: "unmute", player, profile })
                if player == "Test099" && profile.ends_with("63")
        ));
        panel.key(KeyCode::Tab, KeyCode::Tab, true);
        assert_eq!(panel.filtered(now()).len(), 1);
        let key = KeyCode::Char('f');
        panel.key(key, key, true);
        let key = KeyCode::Char('z');
        panel.key(key, key, true);
        assert!(panel.filtered(now()).is_empty());
        terminal.draw(|f| panel.draw(f, f.area())).unwrap();
        assert_eq!(terminal.get_cursor_position().unwrap().x, 8);
        assert_eq!(terminal.get_cursor_position().unwrap().y, 2);
        assert!(panel.cancel_search());
        assert_eq!(panel.filtered(now()).len(), 1);
    }
}
