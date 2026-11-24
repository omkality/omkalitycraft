use ratatui::{
    Frame,
    crossterm::event::KeyCode,
    layout::{Constraint, Layout, Rect},
    text::Line,
    widgets::{Block, Borders, Clear, Paragraph, Wrap},
};

pub struct Form {
    servers: Vec<String>,
    number: String,
    scroll: u16,
    invalid: bool,
}

impl Form {
    pub fn new(servers: &[String]) -> Self {
        Self {
            servers: servers.to_vec(),
            number: String::new(),
            scroll: 0,
            invalid: false,
        }
    }

    pub fn key(&mut self, key: KeyCode) -> Option<String> {
        let multi_digit = self.servers.len() > 9;
        let choice = match key {
            KeyCode::Up => {
                self.scroll = self.scroll.saturating_sub(1);
                return None;
            }
            KeyCode::Down => {
                self.scroll = (self.scroll + 1).min(self.servers.len().saturating_sub(1) as u16);
                return None;
            }
            KeyCode::Char(digit) if digit.is_ascii_digit() && !multi_digit => {
                digit.to_digit(10).map(|number| number as usize)
            }
            KeyCode::Char(digit) if digit.is_ascii_digit() && self.number.len() < 3 => {
                self.number.push(digit);
                self.invalid = false;
                return None;
            }
            KeyCode::Backspace if multi_digit => {
                self.number.pop();
                self.invalid = false;
                return None;
            }
            KeyCode::Enter if multi_digit => self.number.parse::<usize>().ok(),
            _ => return None,
        };
        let server = choice
            .and_then(|number| number.checked_sub(1))
            .and_then(|index| self.servers.get(index));
        self.invalid = server.is_none();
        server.cloned()
    }

    pub fn draw(&mut self, frame: &mut Frame) {
        let area = frame.area();
        let width = area.width.saturating_sub(2).min(62);
        let height = area.height.min(self.servers.len() as u16 + 6);
        let popup = Rect::new(
            area.x + (area.width - width) / 2,
            area.y + (area.height - height) / 2,
            width,
            height,
        );
        let block = Block::default()
            .borders(Borders::ALL)
            .title(" Сохранить мир ");
        let [list, controls] =
            Layout::vertical([Constraint::Min(1), Constraint::Length(4)]).areas(block.inner(popup));
        self.scroll = self
            .scroll
            .min((self.servers.len() as u16).saturating_sub(list.height));
        let rows: Vec<Line> = self
            .servers
            .iter()
            .enumerate()
            .map(|(index, server)| Line::from(format!("{}  {server}", index + 1)))
            .collect();
        let mut hint = if self.servers.len() > 9 {
            format!("Введите номер и нажмите Enter.\n> {}", self.number)
        } else {
            "Нажмите номер сервера.".to_owned()
        };
        if self.invalid {
            hint.push_str("\nТакого номера нет в списке.");
        }
        hint.push_str("\nEsc — назад");
        frame.render_widget(Clear, popup);
        frame.render_widget(block, popup);
        frame.render_widget(Paragraph::new(rows).scroll((self.scroll, 0)), list);
        frame.render_widget(Paragraph::new(hint).wrap(Wrap { trim: true }), controls);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_key_saves_the_numbered_server() {
        let mut form = Form::new(&["dj2".into(), "second".into()]);
        assert_eq!(form.key(KeyCode::Enter), None);
        assert_eq!(form.key(KeyCode::Char('0')), None);
        assert_eq!(form.key(KeyCode::Char('3')), None);
        assert_eq!(form.key(KeyCode::Char('2')).as_deref(), Some("second"));
    }

    #[test]
    fn a_large_list_accepts_multi_digit_numbers() {
        let servers: Vec<_> = (1..=12).map(|number| format!("server-{number}")).collect();
        let mut form = Form::new(&servers);
        assert_eq!(form.key(KeyCode::Char('1')), None);
        assert_eq!(form.key(KeyCode::Char('2')), None);
        assert_eq!(form.key(KeyCode::Enter).as_deref(), Some("server-12"));
    }
}
