"""Explicit, source-pinned pagination of reviewed Patchouli text pages.

This does not measure a font or guess where to split. Each plan still needs
native acceptance. Recipes and template components are deliberately untouched.
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


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reviewed_boundary(text: str, cut: int) -> None:
    if not any(text.startswith(marker, cut) for marker in ("$(br2)", "$(br)", "$(li)")):
        raise ValueError("Split must precede a reviewed paragraph or list boundary")
    bold = link = False
    if "\u00a7" in text[:cut]:
        raise ValueError("Unreviewed legacy formatting before split")
    if text[:cut].count("$(") != len(_MACRO.findall(text[:cut])):
        raise ValueError("Unfinished formatting command before split")
    for match in _MACRO.finditer(text[:cut]):
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


def _split_page(page, offsets, index, titles):
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
        _reviewed_boundary(text, cut)
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
        index: _split_page(obj["pages"][index], offsets, index, titles)
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
