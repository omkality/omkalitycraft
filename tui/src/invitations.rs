use crate::protocol::InvitationEntry;
use ratatui::crossterm::event::KeyCode;
use ratatui::{
    Frame,
    layout::Rect,
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};

pub enum Selection {
    Copy(String),
    Revoke(String),
}

pub struct Form {
    rows: Vec<InvitationEntry>,
    revoke: bool,
    number: String,
    confirming: Option<usize>,
    yes: bool,
    error: bool,
}

impl Form {
    pub fn new(rows: &[InvitationEntry], revoke: bool) -> Self {
        Self {
            rows: rows.to_vec(),
            revoke,
            number: String::new(),
            confirming: None,
            yes: false,
            error: false,
        }
    }

    pub fn dismiss_confirmation(&mut self) -> bool {
        self.yes = false;
        self.confirming.take().is_some()
    }

    pub fn key(&mut self, key: KeyCode) -> Option<Selection> {
        if let Some(index) = self.confirming {
            match key {
                KeyCode::Left => self.yes = false,
                KeyCode::Right => self.yes = true,
                KeyCode::Tab => self.yes = !self.yes,
                KeyCode::Enter if self.yes => {
                    return Some(Selection::Revoke(self.rows[index].reference.clone()));
                }
                KeyCode::Enter => {
                    self.dismiss_confirmation();
                }
                _ => {}
            }
            return None;
        }
        match key {
            KeyCode::Char(digit) if digit.is_ascii_digit() && self.number.len() < 4 => {
                self.number.push(digit);
                self.error = false;
            }
            KeyCode::Backspace => {
                self.number.pop();
                self.error = false;
            }
            KeyCode::Enter => {
                let index = self
                    .number
                    .parse::<usize>()
                    .ok()
                    .and_then(|number| number.checked_sub(1))
                    .filter(|index| *index < self.rows.len());
                match index {
                    Some(index) if self.revoke => self.confirming = Some(index),
                    Some(index) => return Some(Selection::Copy(self.rows[index].code.clone())),
                    None => self.error = true,
                }
            }
            _ => {}
        }
        None
    }

    pub fn draw(&self, frame: &mut Frame) {
        let area = frame.area();
        let width = area.width.saturating_sub(4).min(72);
        let height = area.height.min(10);
        let popup = Rect::new(
            (area.width - width) / 2,
            (area.height - height) / 2,
            width,
            height,
        );
        let (title, text) = if let Some(index) = self.confirming {
            (
                " Отозвать приглашение? ",
                format!(
                    "\n№{}  {}\n\n{}\n\n←/→ выбор · Enter подтвердить · Esc назад",
                    index + 1,
                    self.rows[index].code,
                    if self.yes {
                        "  Нет     [ Да, отозвать ]"
                    } else {
                        "[ Нет ]     Да, отозвать"
                    },
                ),
            )
        } else {
            (
                if self.revoke {
                    " Отозвать приглашение "
                } else {
                    " Скопировать ключ "
                },
                format!(
                    "\nНомер из списка (1–{})\n> {}\n{}\n\nEnter — продолжить · Esc — назад",
                    self.rows.len(),
                    self.number,
                    if self.error {
                        "Такого номера нет в списке."
                    } else {
                        ""
                    },
                ),
            )
        };
        frame.render_widget(Clear, popup);
        frame.render_widget(
            Paragraph::new(text)
                .wrap(Wrap { trim: false })
                .block(Block::default().borders(Borders::ALL).title(title)),
            popup,
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn copy_preserves_case_and_revoke_uses_the_displayed_rows_reference() {
        let rows = [
            InvitationEntry {
                reference: "a01234567890".into(),
                code: "ProbeFirst".into(),
                date: "2026-11-22".into(),
            },
            InvitationEntry {
                reference: "b01234567890".into(),
                code: "Probe_lI01".into(),
                date: "2026-11-22".into(),
            },
        ];
        let mut copy = Form::new(&rows, false);
        copy.key(KeyCode::Char('2'));
        assert!(
            matches!(copy.key(KeyCode::Enter), Some(Selection::Copy(code)) if code == rows[1].code)
        );
        let mut revoke = Form::new(&rows, true);
        revoke.key(KeyCode::Char('2'));
        assert!(revoke.key(KeyCode::Enter).is_none());
        revoke.key(KeyCode::Right);
        assert!(
            matches!(revoke.key(KeyCode::Enter), Some(Selection::Revoke(reference)) if reference == rows[1].reference)
        );
    }
}
