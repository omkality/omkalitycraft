use serde::Deserialize;
use std::{
    env, fs,
    io::{self, IsTerminal, Read},
    path::PathBuf,
};

/// Non-secret local launch paths. Credentials are still checked by the owner backend.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Defaults {
    schema_version: u32,
    pub repo: PathBuf,
    pub python: PathBuf,
    pub config: PathBuf,
}
/// Load build-time or adjacent defaults for a launch without arguments.
pub fn defaults() -> Result<Option<Defaults>, String> {
    if env::args_os().len() > 1 {
        return Ok(None);
    }
    if let Some(encoded) = option_env!("OMK_TUI_EMBEDDED_DEFAULTS") {
        return parse(encoded.as_bytes())
            .map(Some)
            .map_err(|_| "Неверная встроенная конфигурация TUI".into());
    }
    let path = env::current_exe()
        .map_err(|_| "Не удалось определить папку программы")?
        .with_file_name("owner-tui.json");
    if !path.exists() {
        return Ok(None);
    }
    if fs::metadata(&path)
        .map_err(|_| "Не удалось прочитать owner-tui.json")?
        .len()
        > 8192
    {
        return Err("owner-tui.json слишком большой".into());
    }
    let mut bytes = Vec::new();
    fs::File::open(path)
        .map_err(|_| "Не удалось прочитать owner-tui.json")?
        .take(8193)
        .read_to_end(&mut bytes)
        .map_err(|_| "Не удалось прочитать owner-tui.json")?;
    parse(&bytes).map(Some)
}
fn parse(bytes: &[u8]) -> Result<Defaults, String> {
    if bytes.len() > 8192 {
        return Err("owner-tui.json слишком большой".into());
    }
    let value: Defaults = serde_json::from_slice(bytes).map_err(|_| "Неверный owner-tui.json")?;
    if value.schema_version != 1
        || !value.repo.is_absolute()
        || !value.python.is_absolute()
        || !value.config.is_absolute()
    {
        return Err(
            "owner-tui.json требует schema_version 1 и абсолютные пути repo/python/config".into(),
        );
    }
    Ok(value)
}

/// Give a standalone classic Windows console enough room for the dashboard.
#[cfg(windows)]
pub fn widen_standalone_console() {
    use windows_sys::Win32::{
        System::Console::{
            CONSOLE_SCREEN_BUFFER_INFO, COORD, GetConsoleProcessList, GetConsoleScreenBufferInfo,
            GetConsoleWindow, GetLargestConsoleWindowSize, GetStdHandle, SMALL_RECT,
            STD_OUTPUT_HANDLE, SetConsoleScreenBufferSize, SetConsoleWindowInfo,
        },
        UI::WindowsAndMessaging::IsWindowVisible,
    };

    const COLUMNS: i16 = 136;
    const ROWS: i16 = 35;
    if env::args_os().len() != 1 || !io::stdout().is_terminal() {
        return;
    }

    let mut attached_pid = 0;
    let mut info = CONSOLE_SCREEN_BUFFER_INFO::default();
    // A visible console window belongs to the classic host. A pseudoconsole's
    // HWND only serves its message queue. All output pointers refer to local data.
    unsafe {
        if GetConsoleProcessList(&mut attached_pid, 1) != 1
            || attached_pid != std::process::id()
            || IsWindowVisible(GetConsoleWindow()) == 0
        {
            return;
        }
        let output = GetStdHandle(STD_OUTPUT_HANDLE);
        if GetConsoleScreenBufferInfo(output, &mut info) == 0 {
            return;
        }
        let limit = GetLargestConsoleWindowSize(output);
        let previous = info.srWindow;
        let previous_width = previous.Right - previous.Left + 1;
        let previous_height = previous.Bottom - previous.Top + 1;
        let width = previous_width.max(COLUMNS.min(limit.X));
        let height = previous_height.max(ROWS.min(limit.Y));
        if width == previous_width && height == previous_height {
            return;
        }

        let buffer = COORD {
            X: info.dwSize.X.max(width),
            Y: info.dwSize.Y.max(height),
        };
        if (buffer.X != info.dwSize.X || buffer.Y != info.dwSize.Y)
            && SetConsoleScreenBufferSize(output, buffer) == 0
        {
            return;
        }
        let window = SMALL_RECT {
            Left: 0,
            Top: 0,
            Right: width - 1,
            Bottom: height - 1,
        };
        SetConsoleWindowInfo(output, 1, &window);
    }
}

pub fn pause_on_double_click() {
    if cfg!(windows)
        && env::args_os().len() == 1
        && io::stdin().is_terminal()
        && io::stderr().is_terminal()
    {
        eprintln!("Нажмите Enter, чтобы закрыть окно.");
        let mut line = String::new();
        let _ = io::stdin().read_line(&mut line);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sidecar_is_bounded_strict_and_requires_absolute_paths() {
        let root = env::temp_dir();
        let good = serde_json::json!({"schema_version":1,"repo":root,"python":root.join("python"),"config":root.join("operator.toml")});
        assert!(parse(&serde_json::to_vec(&good).unwrap()).is_ok());
        for (key, value) in [
            ("schema_version", serde_json::json!(2)),
            ("python", serde_json::json!("python")),
            ("extra", serde_json::json!(true)),
        ] {
            let mut bad = good.clone();
            bad[key] = value;
            assert!(parse(&serde_json::to_vec(&bad).unwrap()).is_err());
        }
        assert!(parse(&vec![b' '; 8193]).is_err());
    }
}
