use crate::protocol::{TpsHistory, TpsWindow};
use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
};

const EMPTY: Color = Color::Rgb(38, 48, 60);
const MUTED: Color = Color::Rgb(139, 155, 172);

pub fn color(tps: f64) -> Color {
    if tps >= 19.0 {
        Color::Rgb(112, 214, 156)
    } else if tps >= 15.0 {
        Color::Rgb(240, 205, 108)
    } else if tps >= 10.0 {
        Color::Rgb(236, 158, 91)
    } else {
        Color::Rgb(231, 110, 121)
    }
}

fn shade(color: Color, percent: u16) -> Color {
    let Color::Rgb(r, g, b) = color else {
        return EMPTY;
    };
    let channel =
        |value: u8, bg: u16| ((u16::from(value) * percent + bg * (100 - percent)) / 100) as u8;
    Color::Rgb(channel(r, 18), channel(g, 24), channel(b, 31))
}

fn tile(value: Option<f64>, row: u16, height: u16, column: usize, stale: bool) -> Color {
    let alternate = !(usize::from(row) + column).is_multiple_of(2);
    let empty = if alternate {
        Color::Rgb(30, 39, 49)
    } else {
        EMPTY
    };
    let Some(value) = value else {
        return empty;
    };
    let level = (value / 20.0 * f64::from(height - 1)).round() as u16;
    let from_bottom = height - 1 - row;
    let base = if stale { MUTED } else { color(value) };
    if from_bottom == level {
        shade(base, if alternate { 86 } else { 100 })
    } else if from_bottom < level {
        shade(base, if alternate { 36 } else { 48 })
    } else {
        empty
    }
}

// A narrow terminal must not hide a short dip or bridge a missing sample.
pub fn column_values(history: &TpsHistory, count: usize) -> Vec<Option<f64>> {
    if history.points.is_empty() {
        return vec![None; count];
    }
    (0..count)
        .map(|column| {
            let start = column * history.points.len() / count;
            let end = ((column + 1) * history.points.len() / count).max(start + 1);
            history.points[start..end]
                .iter()
                .try_fold(20.0, |min, p| p.tps.map(|value| f64::min(min, value)))
        })
        .collect()
}

pub fn legend(stale: bool) -> Line<'static> {
    Line::from(
        [
            (20.0, "▀ ≥19  "),
            (16.0, "▀ ≥15  "),
            (12.0, "▀ ≥10  "),
            (0.0, "▀ <10"),
        ]
        .into_iter()
        .map(|(value, label)| {
            Span::styled(
                label,
                Style::default().fg(if stale { MUTED } else { color(value) }),
            )
        })
        .collect::<Vec<_>>(),
    )
}

pub fn draw(
    frame: &mut Frame,
    history: Option<&TpsHistory>,
    area: Rect,
    window: TpsWindow,
    stale: bool,
) {
    if area.width < 20 || area.height < 3 {
        return;
    }
    let columns = usize::from(area.width - 4);
    let values = history
        .map(|h| column_values(h, columns))
        .unwrap_or_else(|| vec![None; columns]);
    let height = area.height - 1;
    let right = area.x + 4 + columns as u16 - 1;
    for row in 0..height {
        if row == 0 || row == height / 2 || row == height - 1 {
            let value = 20.0 * f64::from(height - 1 - row) / f64::from(height - 1);
            let label = format!("{:>2.0}", value);
            frame
                .buffer_mut()
                .set_string(area.x, area.y + row, label, Style::default().fg(MUTED));
        }
        for (column, value) in values.iter().enumerate() {
            // Each character holds two touching square cells; alternating shades
            // retain the grid without large horizontal or vertical gutters.
            let top = tile(*value, row * 2, height * 2, column, stale);
            let bottom = tile(*value, row * 2 + 1, height * 2, column, stale);
            frame.buffer_mut()[(area.x + 4 + column as u16, area.y + row)]
                .set_symbol("▀")
                .set_style(Style::default().fg(top).bg(bottom));
        }
    }
    let axis_y = area.y + height;
    let last = if stale {
        "посл. ответ"
    } else {
        "сейчас"
    };
    for (x, label) in [
        (area.x + 4, window.first),
        (
            area.x + 4 + (right - area.x - 4) / 2 - window.middle.chars().count() as u16 / 2,
            window.middle,
        ),
        (right + 1 - last.chars().count() as u16, last),
    ] {
        frame
            .buffer_mut()
            .set_string(x, axis_y, label, Style::default().fg(MUTED));
    }
}
