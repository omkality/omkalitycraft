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
    draw_pixels(frame, area, &ORE, 16, 8);
}

pub fn draw_large(frame: &mut Frame, area: Rect) {
    draw_pixels(frame, area, &ORE_LARGE, 32, 16);
}

fn draw_pixels(frame: &mut Frame, area: Rect, pixels: &[[u8; 4]], width: u16, height: u16) {
    for y in 0..area.height.min(height) {
        for x in 0..area.width.min(width) {
            let top = pixels[(y * 2 * width + x) as usize];
            let bottom = pixels[((y * 2 + 1) * width + x) as usize];
            frame.buffer_mut()[(area.x + x, area.y + y)]
                .set_symbol("▀")
                .set_style(Style::default().fg(blend(top)).bg(blend(bottom)));
        }
    }
}
