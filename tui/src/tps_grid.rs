use crate::protocol::{TpsHistory, TpsWindow};
use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
};

const PANEL: Color = Color::Rgb(18, 24, 31);
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

fn dim(color: Color) -> Color {
    let Color::Rgb(r, g, b) = color else {
        return EMPTY;
    };
    let channel = |value: u8, bg: u16| ((u16::from(value) * 2 + bg * 3) / 5) as u8;
    Color::Rgb(channel(r, 18), channel(g, 24), channel(b, 31))
}

// A narrow terminal must not hide a short dip or bridge a missing sample.
pub fn column_values(history: &TpsHistory, count: usize) -> Vec<Option<f64>> {
    let count = count.min(history.points.len());
    (0..count)
        .map(|column| {
            let start = column * history.points.len() / count;
            let end = (column + 1) * history.points.len() / count;
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
    let columns = usize::from((area.width - 3) / 2).min(61);
    let values = history
        .map(|h| column_values(h, columns))
        .unwrap_or_else(|| vec![None; columns]);
    let height = area.height - 1;
    let right = area.x + 4 + (columns as u16 - 1) * 2;
    for row in 0..height {
        if row == 0 || row == height / 2 || row == height - 1 {
            let value = 20.0 * f64::from(height - 1 - row) / f64::from(height - 1);
            let label = format!("{:>2.0}", value);
            frame
                .buffer_mut()
                .set_string(area.x, area.y + row, label, Style::default().fg(MUTED));
        }
        for (column, value) in values.iter().enumerate() {
            let tile = if let Some(value) = value {
                let level = (value / 20.0 * f64::from(height - 1)).round() as u16;
                let from_bottom = height - 1 - row;
                let color = if stale { MUTED } else { color(*value) };
                if from_bottom == level {
                    color
                } else if from_bottom < level {
                    dim(color)
                } else {
                    EMPTY
                }
            } else {
                EMPTY
            };
            // One column by half a row is square in a conventional 1:2 terminal font.
            // The following character and lower half-row form the grid's gutters.
            frame.buffer_mut()[(area.x + 4 + column as u16 * 2, area.y + row)]
                .set_symbol("▀")
                .set_style(Style::default().fg(tile).bg(PANEL));
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
