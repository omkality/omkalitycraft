use ratatui::{
    Frame,
    layout::Rect,
    style::{Color, Style},
};

include!("ore_pixels.rs");

fn blend(pixel: [u8; 4]) -> Color {
    let a = u32::from(pixel[3]);
    let channel = |v: u8, bg: u8| ((u32::from(v) * a + u32::from(bg) * (255 - a)) / 255) as u8;
    Color::Rgb(
        channel(pixel[0], 18),
        channel(pixel[1], 24),
        channel(pixel[2], 31),
    )
}

pub fn draw(frame: &mut Frame, area: Rect) {
    const WIDTH: u16 = 16;
    const HEIGHT: u16 = 8;
    for y in 0..area.height.min(HEIGHT) {
        for x in 0..area.width.min(WIDTH) {
            let top = ORE[(y * 2 * WIDTH + x) as usize];
            let bottom = ORE[((y * 2 + 1) * WIDTH + x) as usize];
            frame.buffer_mut()[(area.x + x, area.y + y)]
                .set_symbol("▀")
                .set_style(Style::default().fg(blend(top)).bg(blend(bottom)));
        }
    }
}
