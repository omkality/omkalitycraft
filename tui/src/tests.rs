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
fn player_names_reply_accepts_only_a_bounded_list_of_nicknames() {
    let mut value = serde_json::json!({
        "schema_version": 1, "action": "owner.console", "server_id": "dj2",
        "command": "player-names", "ok": true, "effect": "none", "error": null,
        "output": "A1\nprobe_2",
    });
    let parse = |payload: &serde_json::Value| {
        ConsoleResult::parse(&serde_json::to_vec(payload).unwrap(), "dj2", "player-names")
    };
    assert_eq!(
        parse(&value).unwrap().player_names().unwrap(),
        ["A1", "probe_2"]
    );
    value["output"] = serde_json::json!("");
    assert!(parse(&value).unwrap().player_names().unwrap().is_empty());
    for invalid in [
        "Good\nBad Name".into(),
        "Good\n\u{1b}[2J".into(),
        "Good\n\nOther".into(),
        "a\n".repeat(1001),
    ] {
        value["output"] = serde_json::json!(invalid);
        assert!(parse(&value).is_err());
    }
}

#[test]
fn player_stats_uses_nickname_only_and_rejects_unbound_output() {
    assert_eq!(shortcut_key(KeyCode::Char('ы')), KeyCode::Char('s'));
    let mut form = moderation::Form::new("dj2".into(), "stats");
    assert!(form.key(KeyCode::Enter).is_none());
    for c in "FirstJoin".chars() {
        assert!(form.key(KeyCode::Char(c)).is_none());
    }
    let action = form.key(KeyCode::Enter).unwrap();
    assert_eq!(action.player, "FirstJoin");
    assert_eq!(action.command, "stats");
    assert!(action.duration.is_empty() && action.reason.is_empty());
    assert!(!form.confirming);

    let base = serde_json::json!({
        "schema_version": 1, "action": "owner.player-stats", "server_id": "dj2",
        "player": "FirstJoin", "ok": true, "output": "Наиграно · 1 ч", "error": null,
    });
    let parse = |value: &serde_json::Value, player| {
        protocol::PlayerStatsResult::parse(&serde_json::to_vec(value).unwrap(), "dj2", player)
    };
    assert_eq!(
        parse(&base, "FirstJoin").unwrap().message(),
        "Наиграно · 1 ч"
    );
    assert!(parse(&base, "Other").is_err());
    let mut unsafe_output = base;
    unsafe_output["output"] = serde_json::json!("\u{1b}[2J");
    assert!(parse(&unsafe_output, "FirstJoin").is_err());
}

#[test]
fn failed_player_lookup_keeps_the_roster_and_the_error_expires() {
    let missing = serde_json::json!({
        "schema_version": 1, "action": "owner.player-stats", "server_id": "dj2",
        "player": "MissingProfile", "ok": false, "output": "", "error": "profile_not_found",
    });
    let error = protocol::PlayerStatsResult::parse(
        &serde_json::to_vec(&missing).unwrap(),
        "dj2",
        "MissingProfile",
    )
    .unwrap()
    .message();
    let roster = "Игроки проекта\n\nFirstJoin\nSecondJoin";
    let mut app = App::new(false);
    app.show_section("roster".into(), roster.into());
    app.command_page_mut().scroll = 1;
    let mut terminal = Terminal::new(TestBackend::new(84, 28)).unwrap();
    let mut render = |app: &mut App| {
        terminal.draw(|f| ui::draw(f, app)).unwrap();
        terminal
            .backend()
            .buffer()
            .content
            .iter()
            .map(|cell| cell.symbol())
            .collect::<String>()
    };

    let now = Instant::now();
    app.finish_player_stats(Err(error.clone()), now);
    let active = render(&mut app);
    assert!(active.contains("FirstJoin") && active.contains("SecondJoin"));
    assert!(active.contains("Ошибка · Игрок MissingProfile"));
    assert!(!app.failed);
    assert_eq!(app.command_page().message, roster);
    assert_eq!(app.command_page().scroll, 1);

    app.finish_player_stats(Err(error), now - Duration::from_secs(5));
    let expired = render(&mut app);
    assert!(expired.contains("FirstJoin") && expired.contains("SecondJoin"));
    assert!(!expired.contains("MissingProfile"));
    assert_eq!(app.command_page().scroll, 1);

    app.finish_player_stats(Ok("Карточка FirstJoin".into()), now);
    assert!(render(&mut app).contains("Карточка FirstJoin"));
    assert_eq!(app.command_page().scroll, 0);
}

#[test]
fn escape_returns_one_level_and_only_the_menu_opens_exit_confirmation() {
    let mut app = App::new(false);
    let menu = app.command_page().message.clone();
    app.show_section("roster".into(), "Игроки проекта\nMember".into());
    app.command_page_mut().scroll = 7;
    app.finish_player_stats(Ok("Карточка Member".into()), Instant::now());
    app.back_or_confirm_exit();
    assert_eq!(app.command_page().message, "Игроки проекта\nMember");
    assert_eq!(app.command_page().scroll, 7);
    assert!(app.confirm.is_none());

    let mut form = moderation::Form::new("dj2".into(), "ban");
    for c in "Member".chars() {
        form.key(KeyCode::Char(c));
    }
    form.key(KeyCode::Enter);
    form.key(KeyCode::Right);
    assert!(form.confirming);
    app.moderation = Some(form);
    assert!(app.dismiss_dialog());
    let form = app.moderation.as_mut().unwrap();
    assert!(!form.confirming);
    assert_eq!(form.action.player, "Member");
    assert!(form.key(KeyCode::Enter).is_none());
    assert!(form.key(KeyCode::Enter).is_none());
    assert!(app.dismiss_dialog());
    assert!(app.moderation.is_none());
    assert_eq!(app.command_page().scroll, 7);

    app.back_or_confirm_exit();
    assert_eq!(app.command_page().message, menu);
    assert!(app.confirm.is_none());
    app.back_or_confirm_exit();
    assert!(matches!(
        app.confirm,
        Some(Confirmation::Exit { approved: false })
    ));
    assert!(app.dismiss_dialog());
    assert_eq!(app.command_page().message, menu);
    assert!(app.confirm.is_none());
}

#[test]
fn refreshed_membership_section_is_visible_after_dismissing_the_ban_result() {
    let mut app = App::new(false);
    app.show_section("roster".into(), "Игроки проекта\nMember".into());
    assert_eq!(app.membership_section(), Some("roster"));
    app.show_detail("Бессрочный бан применён".into());
    app.refresh_section("permanent-bans", "Неверный раздел".into());
    app.refresh_section("roster", "В списке пока нет игроков.".into());
    assert_eq!(app.command_page().message, "Бессрочный бан применён");
    app.back_or_confirm_exit();
    assert_eq!(app.command_page().message, "В списке пока нет игроков.");
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
    app.open_save_world();
    let mut terminal = Terminal::new(TestBackend::new(120, 38)).unwrap();
    terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
    let text: String = terminal
        .backend()
        .buffer()
        .content
        .iter()
        .map(|cell| cell.symbol())
        .collect();
    assert!(text.contains("1  dj2"));
    assert!(app.dismiss_dialog());
    let mut v = demo();
    v["metrics"][0]["state"] = serde_json::json!("missing");
    v["metrics"][0]["value"] = serde_json::Value::Null;
    v["metrics_status"] = serde_json::json!("partial");
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
    let parse = |v: &serde_json::Value| {
        protocol::TpsHistory::parse(
            &serde_json::to_vec(v).unwrap(),
            "dj2",
            protocol::TPS_WINDOWS[0],
        )
    };
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
fn history_gaps_remain_blank_and_zero_stays_visible() {
    let mut v: serde_json::Value =
        serde_json::from_slice(include_bytes!("../fixtures/tps-history.json")).unwrap();
    v["points"][10]["tps"] = serde_json::Value::Null;
    v["state"] = serde_json::json!("partial");
    v["points"][11]["tps"] = serde_json::json!(0);
    let history = protocol::TpsHistory::parse(
        &serde_json::to_vec(&v).unwrap(),
        "dj2",
        protocol::TPS_WINDOWS[0],
    )
    .unwrap();
    let columns = crate::tps_grid::column_values(&history, 61);
    assert_eq!(columns[10], None);
    assert_eq!(columns[11], Some(0.0));
    let mut app = App::new(true);
    app.accept(Overview::parse(&serde_json::to_vec(&demo()).unwrap()).unwrap());
    app.accept_history(Some(Ok(history)));
    for (w, h) in [(120, 38), (84, 28), (120, 34)] {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
        terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
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
fn periods_require_matching_contract_and_do_not_reuse_another_curve() {
    for (i, window) in protocol::TPS_WINDOWS.iter().enumerate() {
        let history = crate::demo_history(*window).unwrap();
        assert_eq!(history.end - history.start, window.seconds);
        assert_eq!(history.points.len(), 61);
        assert!(
            protocol::TpsHistory::parse(
                &serde_json::to_vec(&serde_json::json!({
                    "schema_version":1,"action":"owner.tps-history","server_id":"dj2",
                    "ok":true,"state":"missing","start":0,"end":window.seconds,
                    "step":window.step,"points":[],"error":null
                }))
                .unwrap(),
                "dj2",
                *window
            )
            .is_err()
        );
        let mut app = App::new(true);
        app.accept(Overview::parse(&serde_json::to_vec(&demo()).unwrap()).unwrap());
        app.window_index = i;
        app.accept_history(Some(Ok(history)));
        assert!(!app.history_failed);
        app.range_picker = Some(i);
        for (w, h) in [(120, 38), (84, 28)] {
            let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
            terminal.draw(|f| ui::draw(f, &mut app)).unwrap();
        }
        if i > 0 {
            app.accept_history(Some(crate::demo_history(protocol::TPS_WINDOWS[0])));
            assert!(app.history_failed && app.history.as_ref().unwrap().step == window.step);
        }
    }
    let fixture = include_bytes!("../fixtures/tps-history.json");
    assert!(protocol::TpsHistory::parse(fixture, "dj2", protocol::TPS_WINDOWS[3]).is_err());
}

#[test]
fn tps_grid_keeps_dips_gaps_zero_and_stale_colors_distinct() {
    use crate::tps_grid::{color, column_values};
    use ratatui::{layout::Rect, style::Color};
    assert_eq!(color(19.0), Color::Rgb(112, 214, 156));
    assert_eq!(color(0.0), Color::Rgb(231, 110, 121));
    assert_eq!(color(18.99), color(15.0));
    assert_eq!(color(14.99), color(10.0));
    assert_eq!(color(9.99), color(0.0));
    assert_ne!(color(15.0), color(10.0));
    let mut history = crate::demo_history(protocol::TPS_WINDOWS[0]).unwrap();
    for point in &mut history.points {
        point.tps = Some(20.0);
    }
    history.points[5].tps = None;
    history.points[40].tps = Some(0.0);
    assert_eq!(column_values(&history, 2), vec![None, Some(0.0)]);
    assert!(column_values(&history, 0).is_empty());
    for point in &mut history.points {
        point.tps = Some(20.0);
    }
    for (i, value) in [None, Some(0.0), Some(12.0), Some(16.0), Some(20.0)]
        .into_iter()
        .enumerate()
    {
        history.points[i].tps = value;
    }
    let mut terminal = Terminal::new(TestBackend::new(65, 10)).unwrap();
    terminal
        .draw(|f| {
            crate::tps_grid::draw(
                f,
                Some(&history),
                Rect::new(0, 0, 65, 10),
                protocol::TPS_WINDOWS[0],
                false,
            )
        })
        .unwrap();
    let buffer = terminal.backend().buffer();
    assert_ne!(buffer[(4, 8)].bg, color(0.0));
    assert_eq!(buffer[(5, 8)].bg, color(0.0));
    assert_eq!(buffer[(8, 0)].fg, color(20.0));
    assert_ne!(buffer[(8, 1)].fg, buffer[(8, 1)].bg);
    assert_eq!(buffer[(9, 0)].symbol(), "▀");
    terminal
        .draw(|f| {
            crate::tps_grid::draw(
                f,
                Some(&history),
                Rect::new(0, 0, 65, 10),
                protocol::TPS_WINDOWS[0],
                true,
            )
        })
        .unwrap();
    assert_eq!(
        terminal.backend().buffer()[(8, 0)].fg,
        Color::Rgb(139, 155, 172)
    );
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
        .request(
            Request::Overview(None, protocol::TPS_WINDOWS[0]),
            Arc::new(AtomicBool::new(false)),
        )
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
    match b
        .request(
            Request::PlayerStats {
                server: "dj2".into(),
                player: "FirstJoin".into(),
            },
            Arc::new(AtomicBool::new(false)),
        )
        .unwrap()
    {
        Reply::PlayerStats(v) => {
            assert!(!v.ok);
            assert_eq!(v.message(), "Не удалось проверить профиль игрока.");
        }
        _ => panic!("Wrong player stats reply"),
    }
    assert_eq!(std::fs::read_dir(private).unwrap().count(), 1);
}

#[test]
fn invitation_result_renders_only_a_valid_code_and_private_file() {
    use crate::protocol::InvitationResult;
    let path = env::temp_dir().join(".omk-admin/invitations/invite-test.json");
    let mut value = serde_json::json!({
        "ok": true,
        "single_use": true,
        "invitation_file": path,
        "code": "test-code_123",
    });
    let parse =
        |value: &serde_json::Value| InvitationResult::parse(&serde_json::to_vec(value).unwrap());
    let receipt = parse(&value).unwrap();
    assert_eq!(receipt.code(), Some("test-code_123"));
    let message = receipt.message(Some("clipboard feedback"));
    for part in [
        "test-code_123",
        "clipboard feedback",
        path.to_str().unwrap(),
    ] {
        assert!(message.contains(part));
    }
    value["single_use"] = false.into();
    assert!(parse(&value).is_err());
    value["single_use"] = true.into();
    value["code"] = "bad\ncode".into();
    assert!(parse(&value).is_err());
    let failure = serde_json::json!({
        "ok": false,
        "error": "upstream-detail-not-for-display",
        "error_type": "DraslError",
    });
    let failure = parse(&failure).unwrap();
    assert!(!failure.ok);
    assert_eq!(failure.code(), None);
    assert!(
        !failure
            .message(None)
            .contains("upstream-detail-not-for-display")
    );
}
