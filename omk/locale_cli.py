"""Read-only checks of a candidate language overlay, never game configuration."""

import hashlib

from omk.locale_overlay import MAX_LANG_BYTES, audit_lang


def add_locale_commands(sub):
    locale = sub.add_parser(
        "locale", help="Review language overlays without installing"
    )
    audit = locale.add_subparsers(dest="action", required=True).add_parser("audit")
    audit.add_argument("--source", required=True, help="Candidate English .lang file")
    audit.add_argument(
        "--locale", required=True, help="Candidate translated .lang file"
    )
    audit.add_argument("--previous-source", help="Previous English .lang file")


def _read(path):
    with open(path, "rb") as stream:
        raw = stream.read(MAX_LANG_BYTES + 1)
    if len(raw) > MAX_LANG_BYTES:
        raise ValueError("Oversized language file")
    return raw


def audit_locale_files(args):
    try:
        source, locale = _read(args.source), _read(args.locale)
        previous = _read(args.previous_source) if args.previous_source else None
        result = audit_lang(source, locale, previous)
    except OSError, ValueError:
        return {"ok": False, "error": "Unreadable or invalid language input"}
    result.update(
        ok=not result["missing"] and not result["format_mismatches"],
        read_only=True,
        semantic_review_required=True,
        sha256={
            "source": hashlib.sha256(source).hexdigest(),
            "locale": hashlib.sha256(locale).hexdigest(),
            **(
                {"previous_source": hashlib.sha256(previous).hexdigest()}
                if previous is not None
                else {}
            ),
        },
    )
    return result
