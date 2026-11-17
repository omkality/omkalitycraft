use super::*;
use crate::protocol::{ConsoleResult, Overview};
use ratatui::{Terminal, backend::TestBackend};

fn demo() -> serde_json::Value {
    serde_json::from_slice(include_bytes!("../fixtures/demo.json")).unwrap()
}
fn parse(v: &serde_json::Value) -> bool {
    Overview::parse(&serde_json::to_vec(v).unwrap()).is_ok()
}

#[test]
fn rejects_drift_and_inconsistent_operation_state() {
    assert!(parse(&demo()));
    for (key, value) in [
        ("schema_version", serde_json::json!(true)),
        ("schema_version", serde_json::json!(2)),
        ("unexpected", serde_json::json!(0)),
        ("ok", serde_json::json!(false)),
    ] {
        let mut v = demo();
        v[key] = value;
        assert!(!parse(&v));
    }
    let mut v = demo();
    v["operations"][0]["terminal"] = serde_json::json!(true);
    assert!(!parse(&v));
    let mut v = demo();
    v["operations"][0]["kind"] = serde_json::json!("restores");
    v["operations"][0]["phase"] = serde_json::json!("stopped");
    assert!(!parse(&v));
    let mut v = demo();
    v["operations"][0]["server_id"] = serde_json::json!("other");
    assert!(!parse(&v));
    let mut v = demo();
    v["operations"][0]
        .as_object_mut()
        .unwrap()
        .remove("backup_operation_id");
    assert!(!parse(&v));
    let mut v = demo();
    v["metrics"][0]["state"] = serde_json::json!("stale");
    assert!(!parse(&v));
    let mut v = demo();
    v["server_ids"] = serde_json::json!(["\u{1b}[2J"]);
    assert!(!parse(&v));
}

#[test]
fn consumes_python_operation_contract_examples() {
    let examples: serde_json::Value = serde_json::from_str(include_str!(
        "../../docs/contracts/owner-result-v1.examples.json"
    ))
    .unwrap();
    for value in examples.as_object().unwrap().values() {
        if !value["operation"].is_null() {
            let op: protocol::Operation =
                serde_json::from_value(value["operation"].clone()).unwrap();
            assert!(op.valid());
        }
    }
}

#[test]
fn console_requires_correlation_and_safe_text() {
    let base = serde_json::json!({"schema_version":1,"action":"owner.console","server_id":"dj2","command":"save","ok":true,"effect":"unknown","output":"Saved the game","error":null});
    assert!(ConsoleResult::parse(&serde_json::to_vec(&base).unwrap(), "dj2", "save").is_ok());
    assert!(ConsoleResult::parse(&serde_json::to_vec(&base).unwrap(), "other", "save").is_err());
    let mut v = base.clone();
    v["output"] = serde_json::json!("\u{1b}[2J");
    assert!(ConsoleResult::parse(&serde_json::to_vec(&v).unwrap(), "dj2", "save").is_err());
    let mut v = base;
    v.as_object_mut().unwrap().remove("error");
    assert!(ConsoleResult::parse(&serde_json::to_vec(&v).unwrap(), "dj2", "save").is_err());
}

#[test]
fn renders_resizes_and_keeps_unknown_distinct_from_zero() {
    let mut app = App::new(true);
    app.accept(Overview::parse(&serde_json::to_vec(&demo()).unwrap()).unwrap());
    for (w, h) in [(120, 38), (84, 28), (40, 10), (1, 1)] {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
        terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
        if w == 120 {
            let text: String = terminal
                .backend()
                .buffer()
                .content
                .iter()
                .map(|c| c.symbol())
                .collect();
            assert!(text.contains("19.9"));
            assert!(text.contains("ДЕМО"));
        }
    }
    app.move_operation(500);
    assert_eq!(app.operation.selected(), Some(app.filtered().len() - 1));
    app.move_operation(-500);
    assert_eq!(app.operation.selected(), Some(0));
    app.confirm = Some("SAVE dj2".into());
    let mut terminal = Terminal::new(TestBackend::new(120, 38)).unwrap();
    terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
    let mut v = demo();
    v["metrics"][0]["state"] = serde_json::json!("missing");
    v["metrics"][0]["value"] = serde_json::Value::Null;
    v["metrics_status"] = serde_json::json!("partial");
    app.confirm = None;
    app.accept(Overview::parse(&serde_json::to_vec(&v).unwrap()).unwrap());
    terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
    let text: String = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|c| c.symbol())
        .collect();
    assert!(text.contains("нет данных"));
}

fn python_command(script: &str) -> std::process::Command {
    let mut c = std::process::Command::new(env::var_os("OMK_TEST_PYTHON").unwrap_or_else(|| {
        if cfg!(windows) {
            "python".into()
        } else {
            "python3".into()
        }
    }));
    c.args(["-c", script]);
    c
}

#[test]
fn history_contract_rejects_wrong_binding_and_timestamps() {
    let fixture: serde_json::Value =
        serde_json::from_slice(include_bytes!("../fixtures/tps-history.json")).unwrap();
    let parse =
        |v: &serde_json::Value| protocol::TpsHistory::parse(&serde_json::to_vec(v).unwrap(), "dj2");
    assert!(parse(&fixture).is_ok());
    for (field, bad) in [
        ("server_id", serde_json::json!("other")),
        ("schema_version", serde_json::json!(true)),
        ("step", serde_json::json!(10)),
        ("state", serde_json::json!("missing")),
        ("extra", serde_json::json!(0)),
    ] {
        let mut v = fixture.clone();
        v[field] = bad;
        assert!(parse(&v).is_err());
    }
    let mut v = fixture.clone();
    v["points"][1]["timestamp"] = serde_json::json!(0);
    assert!(parse(&v).is_err());
    let mut v = fixture;
    v["points"][0].as_object_mut().unwrap().remove("tps");
    assert!(parse(&v).is_err());
}

#[test]
fn history_gaps_split_lines_without_turning_into_zero() {
    let mut v: serde_json::Value =
        serde_json::from_slice(include_bytes!("../fixtures/tps-history.json")).unwrap();
    v["points"][10]["tps"] = serde_json::Value::Null;
    v["state"] = serde_json::json!("partial");
    v["points"][11]["tps"] = serde_json::json!(0);
    let history = protocol::TpsHistory::parse(&serde_json::to_vec(&v).unwrap(), "dj2").unwrap();
    let segments = ui::tps_segments(&history);
    assert_eq!(segments.len(), 2);
    assert_eq!(segments[0].len(), 10);
    assert_eq!(segments[1][0].1, 0.0);
    let mut app = App::new(true);
    app.accept(Overview::parse(&serde_json::to_vec(&demo()).unwrap()).unwrap());
    app.accept_history(Some(Ok(history)));
    for (w, h) in [(120, 38), (84, 28), (120, 34)] {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
        terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
        app.about = true;
        terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
        app.about = false;
    }
    app.overview
        .as_mut()
        .unwrap()
        .server_ids
        .push("other".into());
    app.selected_server = 1;
    app.accept_history(Some(Err("failed".into())));
    assert!(app.history.is_none() && app.history_failed);
}

#[test]
fn subprocess_timeout_output_limit_and_exit_are_bounded() {
    let cancel = AtomicBool::new(false);
    assert!(
        backend::capture(
            python_command("import time;time.sleep(30)"),
            &cancel,
            Duration::from_millis(300)
        )
        .is_err()
    );
    assert!(
        backend::capture(
            python_command("print('x'*300000)"),
            &cancel,
            Duration::from_secs(5)
        )
        .is_err()
    );
    assert!(
        backend::capture(
            python_command("raise SystemExit(2)"),
            &cancel,
            Duration::from_secs(5)
        )
        .is_err()
    );
    let (bytes, ok) = backend::capture(
        python_command("print('reply');raise SystemExit(1)"),
        &cancel,
        Duration::from_secs(5),
    )
    .unwrap();
    assert!(!ok && bytes.starts_with(b"reply"));
    cancel.store(true, Ordering::Relaxed);
    assert!(
        backend::capture(
            python_command("import time;time.sleep(30)"),
            &cancel,
            Duration::from_secs(5)
        )
        .is_err()
    );
}

#[test]
fn real_python_cli_reads_an_isolated_config_without_writes() {
    let Some(python) = env::var_os("OMK_TEST_PYTHON") else {
        eprintln!("Set OMK_TEST_PYTHON for real CLI integration (required in CI)");
        return;
    };
    let root = tempfile::tempdir().unwrap();
    let private = root.path().join(".omk-admin");
    std::fs::create_dir(&private).unwrap();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(&private, std::fs::Permissions::from_mode(0o700)).unwrap();
    }
    let config = private.join("operator.toml");
    std::fs::write(&config, "schema=1\n[servers.dj2]\nroot=\"../server\"\n").unwrap();
    let b = Backend {
        python,
        repo: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .unwrap()
            .to_owned(),
        config,
    };
    match b
        .request(Request::Overview(None), Arc::new(AtomicBool::new(false)))
        .unwrap()
    {
        Reply::Overview(v, history) => {
            assert_eq!(history.unwrap().unwrap().state, "disabled");
            assert!(v.ok);
            assert_eq!(v.server_ids, vec!["dj2"]);
            assert!(v.operations.is_empty());
            assert_eq!(v.metrics_status, "disabled");
        }
        _ => panic!("Wrong reply"),
    }
    assert_eq!(std::fs::read_dir(private).unwrap().count(), 1);
}
