"""Explicit, source-pinned layout operations for reviewed Patchouli pages.

This does not measure a font or guess where to split. Each plan still needs
native acceptance. Recipes and live processor inputs must stay unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from itertools import pairwise

_MACRO = re.compile(r"\$\(([^)]*)\)")
_TEXT_FIELDS = {"type", "text", "title", "anchor", "advancement", "flag"}


def _internal_reference(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split("#")
    if len(parts) > 2 or not re.fullmatch(r"[a-z0-9_.-]+(?:/[a-z0-9_.-]+)*", parts[0]):
        return False
    return all(p not in {".", ".."} for p in parts[0].split("/")) and (
        len(parts) == 1 or re.fullmatch(r"[a-z0-9_.-]+", parts[1]) is not None
    )


def _reference_page(obj: dict, pointer: object):
    if not isinstance(pointer, str):
        raise ValueError("A reviewed reference pointer is required")
    match = re.fullmatch(r"/pages/(\d+)/(text|entries/\d+)", pointer)
    if match is None:
        raise ValueError("Only page text and relations references can be changed")
    try:
        page = obj["pages"][int(match[1])]
    except (IndexError, TypeError) as error:
        raise ValueError("Reference source page is absent") from error
    if not isinstance(page, dict):
        raise ValueError("Reference source page must be an object")
    return page, match


def _reference_edit(obj: dict, edit: Mapping[str, object]) -> None:
    kind = edit.get("kind")
    page, match = _reference_page(obj, edit.get("pointer"))
    old, new = edit.get("old"), edit.get("new")
    if not isinstance(old, str) or not old or any(c in old for c in "$()\r\n\t"):
        raise ValueError("A nonempty exact source reference is required")
    if kind != "unlink" and not _internal_reference(new):
        raise ValueError("Invalid internal reference destination")
    if kind == "relation":
        if not match[2].startswith("entries/") or page.get("type") not in {
            "relations",
            "patchouli:relations",
        }:
            raise ValueError("Expected a relations page reference")
        try:
            index = int(match[2].split("/")[1])
            if page["entries"][index] != old:
                raise ValueError("Relations source reference changed")
            page["entries"][index] = new
        except (KeyError, IndexError, TypeError) as error:
            raise ValueError("Relations source reference is absent") from error
        return
    if kind not in {"inline", "unlink"} or match[2] != "text":
        raise ValueError("Unsupported reference edit")
    macro, count = edit.get("macro"), edit.get("count", 1)
    if macro not in {"l", "cat"} or type(count) is not int or count < 1:
        raise ValueError("Unreviewed reference macro or count")
    if kind == "unlink" and new is not None:
        raise ValueError("Unlink cannot introduce a destination")
    text = page.get("text")
    source_macro = f"$({macro}:{old})"
    if not isinstance(text, str) or text.count(source_macro) != count:
        raise ValueError("Inline source reference or occurrence count changed")
    destination = "" if kind == "unlink" else f"$({macro}:{new})"
    page["text"] = text.replace(source_macro, destination, count)


def _add_reference_anchor(obj: dict, index: int, anchor: str) -> None:
    if type(index) is not int or not 0 <= index < len(obj["pages"]):
        raise ValueError("Invalid anchor source page")
    if not isinstance(anchor, str) or re.fullmatch(r"[a-z0-9_.-]+", anchor) is None:
        raise ValueError("Invalid anchor identity")
    page = obj["pages"][index]
    if (
        not isinstance(page, dict)
        or page.get("type") not in {"text", "patchouli:text"}
        or "anchor" in page
        or any(isinstance(p, dict) and p.get("anchor") == anchor for p in obj["pages"])
    ):
        raise ValueError("Anchor requires an unanchored text page and unique identity")
    page["anchor"] = anchor


def repair_patchouli_references(
    source: bytes,
    *,
    expected_source_sha256: str,
    edits: Sequence[Mapping[str, object]],
    anchors: Mapping[int, str],
) -> bytes:
    """Apply reviewed internal references/anchors, without guessing a target.

    Callers must separately verify that target entries/categories/anchors exist
    and are usable in the installed mod. This only enforces the edit boundary.
    Removing a missing article's opening link keeps its label and reset marker.
    """
    if hashlib.sha256(source).hexdigest() != expected_source_sha256:
        raise ValueError("Book source SHA256 does not match the reviewed references")
    obj = json.loads(source.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or not isinstance(obj.get("pages"), list):
        raise ValueError("Book entry must contain a pages list")
    for edit in edits:
        _reference_edit(obj, edit)
    for index, anchor in anchors.items():
        _add_reference_anchor(obj, index, anchor)
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reviewed_boundary(
    text: str, cut: int, allow_word_boundaries: bool = False
) -> None:
    paragraph = any(
        text.startswith(marker, cut) for marker in ("$(br2)", "$(br)", "$(li)")
    )
    word = allow_word_boundaries and (text[cut - 1].isspace() or text[cut].isspace())
    if not paragraph and not word:
        raise ValueError("Split must precede a reviewed paragraph or list boundary")
    bold = link = False
    if "\u00a7" in text[:cut]:
        raise ValueError("Unreviewed legacy formatting before split")
    if text[:cut].count("$(") != len(_MACRO.findall(text[:cut])):
        raise ValueError("Unfinished formatting command before split")
    commands = list(_MACRO.finditer(text[:cut]))
    # Installed BookTextParser's empty/reset/clear commands call SpanState.reset.
    # Earlier styles cannot cross that reset. Unknown commands after it still fail.
    last_reset = max(
        (m.end() for m in commands if m[1] in {"", "reset", "clear"}), default=0
    )
    for match in commands:
        if match.start() < last_reset:
            continue
        command = match[1]
        if not command:
            bold = link = False
        elif command in {"/l", "/cat"}:
            link = False
        elif command == "bold":
            bold = True
        elif command.startswith(("l:", "cat:")):
            # Roots 3.1.9.2 PatchouliHack gives category links the same span
            # lifetime as ordinary entry links; /cat resets the link state.
            link = True
        elif command not in {"br", "br2", "li"}:
            raise ValueError("Unreviewed formatting command before split")
    if bold or link:
        raise ValueError("Active formatting cannot cross a page boundary")


def _split_page(page, offsets, index, titles, allow_word_boundaries=False):
    if not isinstance(page, dict) or page.get("type") not in {"text", "patchouli:text"}:
        raise ValueError("Only ordinary text pages can be split")
    if set(page) - _TEXT_FIELDS:
        raise ValueError("Unreviewed text page field")
    text = page.get("text")
    if not isinstance(text, str) or not text:
        raise ValueError("Expected nonempty literal page text")
    cuts = list(offsets)
    if (
        not cuts
        or any(type(n) is not int or not 0 < n < len(text) for n in cuts)
        or cuts != sorted(set(cuts))
    ):
        raise ValueError("Invalid or unordered split offsets")
    for cut in cuts:
        _reviewed_boundary(text, cut, allow_word_boundaries)
    if index in titles and (
        not isinstance(page.get("title"), str)
        or not isinstance(titles[index], str)
        or not titles[index].strip()
        or "$" in titles[index]
        or "\u00a7" in titles[index]
        or "\n" in titles[index]
    ):
        raise ValueError("Invalid reviewed title replacement")
    boundaries = [0, *cuts, len(text)]
    fragments = []
    for part, (start, end) in enumerate(pairwise(boundaries)):
        fragment = copy.deepcopy(page)
        fragment["text"] = text[start:end]
        if part:
            fragment.pop("anchor", None)
        if index in titles:
            fragment["title"] = titles[index]
        fragments.append(fragment)
    return fragments


def paginate_patchouli_entry(
    source: bytes,
    *,
    expected_source_sha256: str,
    splits: Mapping[int, Sequence[int]],
    titles: Mapping[int, str] | None = None,
    allow_word_boundaries: bool = False,
) -> bytes:
    """Split allowlisted text pages without deleting or rewriting body text.

    Offsets count Python Unicode characters in the original text. Gates are
    copied to every fragment; an anchor stays only on the first fragment.
    Explicit shorter titles replace existing titles on that page's fragments.
    All indexes refer to the input, so earlier insertions cannot shift a plan.
    """
    if hashlib.sha256(source).hexdigest() != expected_source_sha256:
        raise ValueError("Book source SHA256 does not match the reviewed plan")
    obj = json.loads(source.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or not isinstance(obj.get("pages"), list):
        raise ValueError("Book entry must contain a pages list")
    titles = {} if titles is None else titles
    if any(type(i) is not int or not 0 <= i < len(obj["pages"]) for i in splits):
        raise ValueError("Invalid source page index")
    if any(type(i) is not int or i not in splits for i in titles):
        raise ValueError("A title change requires an explicitly split page")
    planned = {
        index: _split_page(
            obj["pages"][index], offsets, index, titles, allow_word_boundaries
        )
        for index, offsets in splits.items()
    }
    if not planned:
        return source
    result = copy.deepcopy(obj)
    result["pages"] = [
        fragment
        for index, page in enumerate(obj["pages"])
        for fragment in planned.get(index, [page])
    ]
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _relocate_page(page: dict, move: Mapping[str, object], allow_word_boundaries: bool):
    expected = move.get("expected_type")
    if (
        not isinstance(page, dict)
        or not isinstance(expected, str)
        or page.get("type") != expected
    ):
        raise ValueError("Relocation consumer type differs from the reviewed plan")
    if expected in {"text", "patchouli:text"}:
        raise ValueError("Ordinary text pages must use pagination instead")
    text = page.get("text")
    if not isinstance(text, str) or not text or text.startswith("#"):
        raise ValueError("Only reviewed literal text can be relocated")
    prose = {"type": "text", "text": text}
    prose.update({key: page[key] for key in ("advancement", "flag") if key in page})
    offsets = move.get("offsets")
    if not isinstance(offsets, (list, tuple)):
        raise ValueError("Explicit relocation offsets are required")
    fragments = (
        _split_page(prose, offsets, 0, {}, allow_word_boundaries)
        if offsets
        else [prose]
    )
    original = copy.deepcopy(page)
    original["text"] = ""
    return [original, *fragments]


def relocate_patchouli_text(
    source: bytes,
    *,
    expected_source_sha256: str,
    moves: Sequence[Mapping[str, object]],
    allow_word_boundaries: bool = False,
) -> bytes:
    """Move reviewed recipe/template prose to following ordinary text pages.

    A plan must first identify the installed consumer and prove that its literal
    `text` value is what the renderer displays. No inference by page type/name.
    The original page, recipes, anchor and other payload stay in place; new
    fragments retain its standard page gates. This never writes a game folder.
    """
    if hashlib.sha256(source).hexdigest() != expected_source_sha256:
        raise ValueError("Book source SHA256 does not match the relocation plan")
    obj = json.loads(source.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or not isinstance(obj.get("pages"), list):
        raise ValueError("Book entry must contain a pages list")
    planned = {}
    for move in moves:
        index = move.get("page")
        if (
            type(index) is not int
            or not 0 <= index < len(obj["pages"])
            or index in planned
        ):
            raise ValueError("Invalid or duplicate relocation source page")
        planned[index] = _relocate_page(
            obj["pages"][index], move, allow_word_boundaries
        )
    result = copy.deepcopy(obj)
    result["pages"] = [
        fragment
        for index, page in enumerate(obj["pages"])
        for fragment in planned.get(index, [page])
    ]
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def expand_patchouli_template_pages(
    source: bytes,
    *,
    expected_source_sha256: str,
    pages: Sequence[int],
    expected_type: str,
    guards: Sequence[str],
) -> bytes:
    """Split a registered custom template using explicit component guards.

    Every clone keeps the template identity, variables and page gates; an anchor
    remains solely on the first clone. Each clone enables exactly one owned
    guard. Callers must provide the matching guarded template, inspect its live
    processor and accept native rendering. This does not register new template
    IDs (old Patchouli only discovers them in the owning mod JAR).
    """
    if hashlib.sha256(source).hexdigest() != expected_source_sha256:
        raise ValueError("Book source SHA256 does not match the template plan")
    obj = json.loads(source.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(obj, dict) or not isinstance(obj.get("pages"), list):
        raise ValueError("Book entry must contain a pages list")
    indexes = list(pages)
    if (
        not indexes
        or any(type(i) is not int or not 0 <= i < len(obj["pages"]) for i in indexes)
        or indexes != sorted(set(indexes))
    ):
        raise ValueError("Invalid or duplicate template source page")
    if (
        not isinstance(expected_type, str)
        or re.fullmatch(r"(?:[a-z0-9_.-]+:)?[a-z0-9_.-]+_template", expected_type)
        is None
    ):
        raise ValueError("Only explicitly reviewed custom templates can expand")
    names = list(guards)
    if (
        not 2 <= len(names) <= 4
        or any(
            not isinstance(n, str)
            or re.fullmatch(r"omk_layout_[a-z0-9_]{1,60}", n) is None
            for n in names
        )
        or len(set(names)) != len(names)
    ):
        raise ValueError("Distinct owned component guard names are required")
    planned = {}
    for index in indexes:
        page = obj["pages"][index]
        if not isinstance(page, dict) or page.get("type") != expected_type:
            raise ValueError("Template source page differs from the reviewed plan")
        if any(name in page for name in names):
            raise ValueError("Component guard already exists in processor input")
        fragments = []
        for part, name in enumerate(names):
            fragment = copy.deepcopy(page)
            fragment.update({guard: str(guard == name).lower() for guard in names})
            if part:
                fragment.pop("anchor", None)
            fragments.append(fragment)
        planned[index] = fragments
    result = copy.deepcopy(obj)
    result["pages"] = [
        fragment
        for index, page in enumerate(obj["pages"])
        for fragment in planned.get(index, [page])
    ]
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
