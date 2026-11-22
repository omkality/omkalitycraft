use std::{
    env, io,
    io::Write,
    path::PathBuf,
    time::{SystemTime, UNIX_EPOCH},
};

const FILE_NAME: &str = "OmkalityCraft-Wipe.log";

pub struct Destination {
    pub export_dir: Option<PathBuf>,
}

impl Destination {
    /// Save a private, bounded diagnostic before showing the location in the TUI.
    pub fn save(&self, details: &str) -> String {
        self.write(details)
            .unwrap_or_else(|_| "Не удалось сохранить журнал вайпа.".into())
    }

    fn write(&self, details: &str) -> io::Result<String> {
        let directory = match &self.export_dir {
            Some(path) => path.clone(),
            None => {
                let executable = env::current_exe()?;
                executable
                    .parent()
                    .ok_or(io::ErrorKind::NotFound)?
                    .to_owned()
            }
        };
        let file = directory.join(FILE_NAME);
        let mut output = tempfile::NamedTempFile::new_in(&directory)?;
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default();
        writeln!(
            output,
            "OmkalityCraft | World reset | UTC timestamp {}",
            timestamp.as_secs()
        )?;
        writeln!(output, "{details}")?;
        #[cfg(unix)]
        if self.export_dir.is_some() {
            use std::os::unix::fs::PermissionsExt;
            output
                .as_file()
                .set_permissions(std::fs::Permissions::from_mode(0o640))?;
        }
        output.persist(&file)?;
        Ok(if self.export_dir.is_some() {
            format!("Журнал рядом с Windows EXE\n.\\{FILE_NAME} · загрузка займёт несколько секунд")
        } else {
            format!("Журнал\n{}", file.display())
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn saves_latest_report_for_windows_export() {
        let dir = tempfile::tempdir().unwrap();
        let destination = Destination {
            export_dir: Some(dir.path().to_owned()),
        };
        let path = dir.path().join(FILE_NAME);
        assert!(destination.save("first attempt").contains(FILE_NAME));
        assert!(destination.save("current failure").contains(FILE_NAME));
        let data = std::fs::read_to_string(path).unwrap();
        assert!(data.starts_with("OmkalityCraft | World reset |"));
        assert!(data.ends_with("current failure\n"));
        assert_eq!(dir.path().read_dir().unwrap().count(), 1);
    }
}
