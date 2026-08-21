import importlib
import json
import os
import socketserver
import subprocess
import threading
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.error import HTTPError

import pytest


def write_tracking(md_path: Path, rows: list[str]):
    header = (
        "# Word Tracking\n\n"
        "| Word | Status | Audio | IPA | Word Type | Date Added | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
    )
    md_path.write_text(header + "\n".join(rows) + "\n", encoding="utf-8")


def _sprache_template(language: str) -> str:
    return (
        "<template><title>Sprache</title>"
        f'<part><name index="1"/><value>{language}</value></part></template>'
    )


def _wortart_template(wortart: str, language: str = "Deutsch") -> str:
    return (
        "<template><title>Wortart</title>"
        f'<part><name index="1"/><value>{wortart}</value></part>'
        f'<part><name index="2"/><value>{language}</value></part></template>'
    )


def _grundformverweis_template(lemma: str, kind: str = "Konj") -> str:
    return (
        f"<template><title>Grundformverweis {kind}</title>"
        f'<part><name index="1"/><value>{lemma}</value></part></template>'
    )


def parsetree_payload(title: str, sections: list[dict]) -> dict:
    """Build an action=parse response with prop=parsetree XML.

    sections: list of {
        "wortart": str OR "wortarten": list[str],  # multi-POS h3 supported
        "grundformverweis": str | None,
        "grundformverweis_kind": str (default "Konj"),
    }.
    """
    parts: list[str] = [f'<h level="2" i="1">== {title} ({_sprache_template("Deutsch")}) ==</h>']
    for index, section in enumerate(sections, start=2):
        wortarten = section.get("wortarten")
        if wortarten is None:
            wortarten = [section["wortart"]]
        wortart_xml = ", ".join(_wortart_template(w) for w in wortarten)
        parts.append(f'<h level="3" i="{index}">=== {wortart_xml} ===</h>')
        gf = section.get("grundformverweis")
        if gf:
            kind = section.get("grundformverweis_kind", "Konj")
            parts.append(_grundformverweis_template(gf, kind))
    parsetree = "<root>" + "\n".join(parts) + "</root>"
    return {"parse": {"title": title, "parsetree": parsetree}}


def german_entry(title: str, *wortarten: str) -> dict:
    """Test helper: build a parsetree payload with one Wortart per h3 section."""
    sections = [{"wortart": wortart} for wortart in wortarten]
    return parsetree_payload(title, sections)


def resolve_test_python(project_root: Path) -> str:
    project_venv_python = project_root / ".venv" / "bin" / "python"
    if project_venv_python.exists():
        return str(project_venv_python)

    active_venv = os.environ.get("VIRTUAL_ENV")
    if active_venv:
        active_venv_python = Path(active_venv) / "bin" / "python"
        if active_venv_python.exists():
            return str(active_venv_python)

    configured_python = os.environ.get("TEST_SUBPROCESS_PYTHON")
    if configured_python:
        return configured_python

    pytest.fail(
        "Subprocess test python is undefined. Provide .venv, VIRTUAL_ENV, or TEST_SUBPROCESS_PYTHON."
    )


@pytest.fixture
def add_words_module():
    mod = importlib.import_module("flashcards.scripts.add_words")
    return importlib.reload(mod)


@pytest.fixture
def tracking_file(tmp_path, monkeypatch):
    import paths

    tracking = tmp_path / "word_tracking.md"
    write_tracking(tracking, [])
    monkeypatch.setattr(paths, "WORD_TRACKING_FILE", tracking, raising=False)
    monkeypatch.setattr(
        importlib.import_module("flashcards.scripts.add_words"), "WORD_TRACKING_FILE", tracking
    )
    return tracking


def test_parse_lookup_candidate_noun_only(add_words_module):
    candidate = add_words_module.parse_lookup_candidate("Arm", german_entry("Arm", "Substantiv"))
    assert candidate.lemma == "Arm"
    assert candidate.supported_types == ("Noun",)


def test_parse_lookup_candidate_adverb_only(add_words_module):
    candidate = add_words_module.parse_lookup_candidate("dort", german_entry("dort", "Adverb"))
    assert candidate.lemma == "dort"
    assert candidate.supported_types == ("Adverb",)


def test_parse_lookup_candidate_maps_adverb_and_verb_subtypes(add_words_module):
    candidate = add_words_module.parse_lookup_candidate(
        "hinaus",
        german_entry("hinaus", "Lokaladverb", "Temporaladverb"),
    )
    assert candidate.supported_types == ("Adverb",)

    modal = add_words_module.parse_lookup_candidate(
        "dürfen",
        german_entry("dürfen", "Modalverb"),
    )
    assert modal.supported_types == ("Verb",)


def test_parse_lookup_candidate_unsupported_only_yields_empty_types(add_words_module):
    candidate = add_words_module.parse_lookup_candidate("eins", german_entry("eins", "Numerale"))
    assert candidate.supported_types == ()


def test_parse_lookup_candidate_marks_inflected_form_page(add_words_module):
    # Real de.wiktionary: Konjugierte Form / Deklinierte Form pages carry
    # Grundformverweis to the canonical lemma and must NOT report supported POS.
    payload_dict = parsetree_payload(
        "Hinausgegangen",
        [{"wortart": "Konjugierte Form", "grundformverweis": "hinausgehen"}],
    )
    candidate = add_words_module.parse_lookup_candidate("Hinausgegangen", payload_dict)
    assert candidate.is_inflected is True
    assert candidate.lemma == "hinausgehen"
    assert candidate.supported_types == ()


def test_parse_lookup_candidate_marks_mixed_page_as_inflected(add_words_module):
    # besser carries supported POS (Adjektiv, Adverb) AND an inflected-form
    # Wortart (Komparativ) plus Grundformverweis to gut. The inflected marker
    # must dominate so callers re-query the lemma.
    payload_dict = parsetree_payload(
        "besser",
        [
            {"wortart": "Adjektiv"},
            {"wortart": "Adverb"},
            {
                "wortart": "Komparativ",
                "grundformverweis": "gut",
                "grundformverweis_kind": "Dekl",
            },
        ],
    )
    candidate = add_words_module.parse_lookup_candidate("besser", payload_dict)
    assert candidate.is_inflected is True
    assert candidate.lemma == "gut"
    assert candidate.supported_types == ()


def test_parse_lookup_candidate_picks_dekl_over_konj_on_multi_redirect_page(add_words_module):
    # bessere has TWO inflected sections each with its own Grundformverweis:
    # Konjugierte Form -> bessern (verb), Deklinierte Form -> gut (adjective).
    # INFLECTED_GRUNDFORM_PRIORITY prefers Deklinierte Form for B1 capture.
    payload_dict = parsetree_payload(
        "bessere",
        [
            {
                "wortart": "Konjugierte Form",
                "grundformverweis": "bessern",
                "grundformverweis_kind": "Konj",
            },
            {
                "wortart": "Deklinierte Form",
                "grundformverweis": "gut",
                "grundformverweis_kind": "Dekl",
            },
        ],
    )
    candidate = add_words_module.parse_lookup_candidate("bessere", payload_dict)
    assert candidate.is_inflected is True
    assert candidate.lemma == "gut"


def test_resolve_lookup_candidate_re_queries_lemma_on_inflected_hit(add_words_module, monkeypatch):
    # Hinausgegangen (Konjugierte Form) -> hinausgehen (Verb). One re-query.
    payloads = {
        "Hinausgegangen": parsetree_payload(
            "Hinausgegangen",
            [{"wortart": "Konjugierte Form", "grundformverweis": "hinausgehen"}],
        ),
        "hinausgehen": german_entry("hinausgehen", "Verb"),
    }
    calls = []

    def fake_fetch(word, timeout):
        calls.append(word)
        return payloads[word]

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)
    candidate = add_words_module.resolve_lookup_candidate("Hinausgegangen", 10)
    assert candidate.lemma == "hinausgehen"
    assert candidate.supported_types == ("Verb",)
    assert candidate.is_inflected is False
    assert calls == ["Hinausgegangen", "hinausgehen"]


def test_resolve_lookup_candidate_re_queries_for_mixed_inflected_page(
    add_words_module, monkeypatch
):
    # besser (Adjektiv+Adverb+Komparativ) -> gut (Adjektiv+Adverb -> compound).
    payloads = {
        "besser": parsetree_payload(
            "besser",
            [
                {"wortart": "Adjektiv"},
                {"wortart": "Adverb"},
                {
                    "wortart": "Komparativ",
                    "grundformverweis": "gut",
                    "grundformverweis_kind": "Dekl",
                },
            ],
        ),
        "gut": german_entry("gut", "Adjektiv", "Adverb"),
    }

    monkeypatch.setattr(
        add_words_module, "fetch_parse_payload", lambda word, timeout: payloads[word]
    )
    candidate = add_words_module.resolve_lookup_candidate("besser", 10)
    assert candidate.lemma == "gut"
    assert candidate.supported_types == ("Adjective", "Adverb")


def test_resolve_lookup_candidate_does_not_toggle_when_lemma_requery_fails(
    add_words_module, monkeypatch
):
    # Per AC-5: input-as-written wins exclusively once it parses. When the
    # first variant resolves to an inflected page AND the lemma re-query
    # fails or yields no POS, we must NOT fall through to the case-toggled
    # variant — that would silently store a different lexical item.
    calls = []

    def fake_fetch(word, timeout):
        calls.append(word)
        if word == "Hinausgegangen":
            return parsetree_payload(
                "Hinausgegangen",
                [{"wortart": "Konjugierte Form", "grundformverweis": "hinausgehen"}],
            )
        if word == "hinausgehen":
            raise add_words_module.LookupErrorResult("no Wiktionary entry")
        raise AssertionError(f"unexpected fetch: {word}")

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)
    with pytest.raises(add_words_module.LookupErrorResult, match="no supported part of speech"):
        add_words_module.resolve_lookup_candidate("Hinausgegangen", 10)
    # Only the input-as-written variant and its lemma re-query were tried.
    # The case-toggled variant (hinausgegangen lowercase) must NOT be fetched.
    assert calls == ["Hinausgegangen", "hinausgehen"]


def test_parse_lookup_candidate_homonym_lemma_plus_weak_inflected_stays_lemma(
    add_words_module,
):
    # Real shape for `lieb` / `lecker` / `dringend`: a primary adjective lemma
    # PLUS a secondary inflected-form entry on the same page (Konjugierte Form
    # / Deklinierte Form / Partizip I) whose Grundformverweis points to an
    # unrelated verb/noun. The page is a lemma; the weak inflected marker
    # must not displace it.
    payload_dict = parsetree_payload(
        "lieb",
        [
            {"wortart": "Adjektiv"},
            {"wortart": "Konjugierte Form", "grundformverweis": "lieben"},
        ],
    )
    candidate = add_words_module.parse_lookup_candidate("lieb", payload_dict)
    assert candidate.is_inflected is False
    assert candidate.lemma == "lieb"
    assert candidate.supported_types == ("Adjective",)


def test_parse_lookup_candidate_handles_multi_wortart_per_h3(add_words_module):
    # Real de.wiktionary pages like `schal`, `tageweise`, `fraglos` pack
    # multiple POS into ONE h3 (### Adjektiv, Adverb). Each {{Wortart}}
    # template must yield its own PosSection so multi-POS routing fires.
    payload_dict = parsetree_payload(
        "tageweise",
        [{"wortarten": ["Adjektiv", "Adverb"]}],
    )
    candidate = add_words_module.parse_lookup_candidate("tageweise", payload_dict)
    assert candidate.lemma == "tageweise"
    # Adjective + Adverb is a defined compound in WordType.
    assert candidate.supported_types == ("Adjective", "Adverb")
    assert candidate.is_inflected is False


def test_extract_pos_sections_emits_one_per_wortart_in_multi_pos_h3(add_words_module):
    payload_dict = parsetree_payload(
        "tageweise",
        [{"wortarten": ["Adjektiv", "Adverb"]}],
    )
    sections = add_words_module.extract_pos_sections(payload_dict["parse"]["parsetree"])
    assert [s.wortart for s in sections] == ["Adjektiv", "Adverb"]
    assert all(s.grundformverweis is None for s in sections)


def test_extract_pos_sections_scopes_grundformverweis_per_section(add_words_module):
    # Each Grundformverweis must be associated with its own h3 subsection.
    payload_dict = parsetree_payload(
        "bessere",
        [
            {
                "wortart": "Konjugierte Form",
                "grundformverweis": "bessern",
                "grundformverweis_kind": "Konj",
            },
            {
                "wortart": "Deklinierte Form",
                "grundformverweis": "gut",
                "grundformverweis_kind": "Dekl",
            },
        ],
    )
    parsetree = payload_dict["parse"]["parsetree"]
    sections = add_words_module.extract_pos_sections(parsetree)
    assert [s.wortart for s in sections] == ["Konjugierte Form", "Deklinierte Form"]
    assert [s.grundformverweis for s in sections] == ["bessern", "gut"]


def test_fetch_parse_payload_sends_descriptive_user_agent(add_words_module, monkeypatch):
    captured = {}

    class FakeResponse:
        status = 200

        def read(self):
            return b'{"parse": {"title": "x", "wikitext": ""}}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        captured["ua"] = request.get_header("User-agent")
        return FakeResponse()

    monkeypatch.setattr(add_words_module, "urlopen", fake_urlopen)
    add_words_module.fetch_parse_payload("foo", 10)
    assert captured["ua"], "User-Agent header must be set (Wikimedia blocks default urllib UA)"
    assert "github" in captured["ua"].lower() or "/" in captured["ua"]


def test_fetch_parse_payload_http_404(add_words_module, monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 404, "missing", hdrs=None, fp=None)

    monkeypatch.setattr(add_words_module, "urlopen", fake_urlopen)
    with pytest.raises(add_words_module.LookupErrorResult, match="no Wiktionary entry"):
        add_words_module.fetch_parse_payload("foo", 10)


def test_fetch_parse_payload_http_5xx(add_words_module, monkeypatch):
    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "boom", hdrs=None, fp=None)

    monkeypatch.setattr(add_words_module, "urlopen", fake_urlopen)
    with pytest.raises(
        add_words_module.LookupErrorResult, match="Wiktionary unreachable: HTTP 503"
    ):
        add_words_module.fetch_parse_payload("foo", 10)


def test_fetch_parse_payload_timeout(add_words_module, monkeypatch):
    monkeypatch.setattr(
        add_words_module, "urlopen", lambda request, timeout: (_ for _ in ()).throw(TimeoutError())
    )
    with pytest.raises(add_words_module.LookupErrorResult, match="Wiktionary unreachable: timeout"):
        add_words_module.fetch_parse_payload("foo", 10)


def test_resolve_lookup_candidate_toggles_case_only_on_miss(add_words_module, monkeypatch):
    payloads = {
        "Lieb": german_entry("Lieb", "Adjektiv"),
    }
    calls = []

    def fake_fetch(word, timeout):
        calls.append(word)
        if word not in payloads:
            raise add_words_module.LookupErrorResult("no Wiktionary entry")
        return payloads[word]

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)

    candidate = add_words_module.resolve_lookup_candidate("lieb", 10)
    assert candidate.lemma == "Lieb"
    assert candidate.supported_types == ("Adjective",)
    # Only the input-as-written then the case-toggled variant — no extras.
    assert calls == ["lieb", "Lieb"]


def test_resolve_lookup_candidate_does_not_toggle_when_input_case_is_valid(
    add_words_module, monkeypatch
):
    calls = []
    payloads = {
        "arm": german_entry("arm", "Adjektiv"),
        "Arm": german_entry("Arm", "Substantiv"),
    }

    def fake_fetch(word, timeout):
        calls.append(word)
        return payloads[word]

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)

    candidate = add_words_module.resolve_lookup_candidate("arm", 10)
    assert candidate.lemma == "arm"
    assert candidate.supported_types == ("Adjective",)
    assert calls == ["arm"]


def test_resolve_lookup_candidate_neither_variant_resolves(add_words_module, monkeypatch):
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: (_ for _ in ()).throw(
            add_words_module.LookupErrorResult("no Wiktionary entry")
        ),
    )
    with pytest.raises(add_words_module.LookupErrorResult, match="no Wiktionary entry"):
        add_words_module.resolve_lookup_candidate("lieb", 10)


def test_resolve_lookup_candidate_preserves_unsupported_pos_over_toggled_404(
    add_words_module, monkeypatch
):
    def fake_fetch(word, timeout):
        if word == "hinaus":
            return german_entry("hinaus", "Lokaladverb")
        raise add_words_module.LookupErrorResult("no Wiktionary entry")

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)

    candidate = add_words_module.resolve_lookup_candidate("hinaus", 10)
    assert candidate.lemma == "hinaus"
    assert candidate.supported_types == ("Adverb",)


def test_resolve_lookup_candidate_reports_unsupported_when_toggled_variant_is_404(
    add_words_module, monkeypatch
):
    def fake_fetch(word, timeout):
        if word == "hinaus":
            return german_entry("hinaus", "Toponym")
        raise add_words_module.LookupErrorResult("no Wiktionary entry")

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)

    with pytest.raises(add_words_module.LookupErrorResult, match="no supported part of speech"):
        add_words_module.resolve_lookup_candidate("hinaus", 10)


def test_plan_batch_unsupported_only_page_fails(add_words_module, monkeypatch, tracking_file):
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: german_entry("eins", "Numerale"),
    )
    staged_rows, records = add_words_module.plan_batch(
        ["eins"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )
    assert staged_rows == []
    assert [(record.status, record.word_type, record.error) for record in records] == [
        ("failed", None, "no supported part of speech")
    ]


def test_plan_batch_unexpected_exception_becomes_failed_record(
    add_words_module, monkeypatch, tracking_file
):
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: (_ for _ in ()).throw(ValueError("bad json")),
    )
    staged_rows, records = add_words_module.plan_batch(
        ["foo"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )
    assert staged_rows == []
    assert records[0].status == "failed"
    assert records[0].error == "unexpected error: bad json"


def test_plan_batch_compound_and_split_pos(add_words_module, monkeypatch, tracking_file):
    write_tracking(
        tracking_file,
        ["| bis | pending | ✅ Bis.wav | — | Preposition | — | — |"],
    )

    payloads = {
        "gleich": german_entry("gleich", "Adjektiv", "Adverb"),
        "bis": german_entry("bis", "Präposition", "Konjunktion"),
    }

    monkeypatch.setattr(
        add_words_module, "fetch_parse_payload", lambda word, timeout: payloads[word]
    )
    monkeypatch.setattr(
        add_words_module,
        "generate_audio",
        lambda lemma: (True, f"{lemma.capitalize()}.wav", f"Generated {lemma}"),
    )

    staged_rows, records = add_words_module.plan_batch(
        ["gleich", "bis"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )

    assert [row.word_type for row in staged_rows] == ["Adjective/Adverb", "Conjunction"]
    assert [record.status for record in records] == ["added", "skipped_dup", "added"]
    assert [record.word_type for record in records] == [
        "Adjective/Adverb",
        "Preposition",
        "Conjunction",
    ]


def test_plan_batch_audio_failure_marks_all_pos_failed(
    add_words_module, monkeypatch, tracking_file
):
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: german_entry("bis", "Präposition", "Konjunktion"),
    )
    monkeypatch.setattr(
        add_words_module,
        "generate_audio",
        lambda lemma: (False, None, "audio backend failed"),
    )

    staged_rows, records = add_words_module.plan_batch(
        ["bis"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )

    assert staged_rows == []
    assert [(record.word_type, record.status, record.error) for record in records] == [
        ("Preposition", "failed", "audio backend failed"),
        ("Conjunction", "failed", "audio backend failed"),
    ]


def test_read_existing_tracking_keys_normalizes_nfc_and_case(add_words_module):
    nfd_schoen = "scho" + "\u0308" + "n"
    content = (
        "# Word Tracking\n\n"
        "| Word | Status | Audio | IPA | Word Type | Date Added | Notes |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {nfd_schoen} | pending | ✅ X.wav | — | Adjective | — | — |\n"
        "| HeaderLike | pending | ✅ X.wav | — | — | — | — |\n"
    )
    keys = add_words_module.read_existing_tracking_keys(content)
    assert (add_words_module.normalize_lemma("schön"), "Adjective") in keys
    assert (add_words_module.normalize_lemma("HeaderLike"), "—") not in keys


def test_plan_batch_dedup_is_case_insensitive(add_words_module, monkeypatch, tracking_file):
    write_tracking(
        tracking_file,
        ["| Lieb | pending | ✅ Lieb.wav | — | Adjective | — | — |"],
    )
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: german_entry("Lieb", "Adjektiv"),
    )
    staged_rows, records = add_words_module.plan_batch(
        ["lieb"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )
    assert staged_rows == []
    assert [(record.word_type, record.status) for record in records] == [
        ("Adjective", "skipped_dup")
    ]


def test_compound_row_does_not_collide_with_single_pos(
    add_words_module, monkeypatch, tracking_file
):
    write_tracking(
        tracking_file,
        ["| gleich | pending | ✅ Gleich.wav | — | Adjective/Adverb | — | — |"],
    )
    monkeypatch.setattr(
        add_words_module,
        "fetch_parse_payload",
        lambda word, timeout: german_entry("gleich", "Adjektiv"),
    )
    monkeypatch.setattr(
        add_words_module, "generate_audio", lambda lemma: (True, "Gleich.wav", "ok")
    )
    staged_rows, records = add_words_module.plan_batch(
        ["gleich"],
        10,
        tracking_file.read_text(encoding="utf-8"),
        lambda _: None,
    )
    assert [row.word_type for row in staged_rows] == ["Adjective"]
    assert [(record.word_type, record.status) for record in records] == [("Adjective", "added")]


def test_atomic_write_text_cleans_up_temp_file_on_replace_failure(
    add_words_module, tmp_path, monkeypatch
):
    target = tmp_path / "tracking.md"
    target.write_text("old\n", encoding="utf-8")
    leaked = []
    original_replace = Path.replace

    def fake_replace(self, target_path):
        leaked.append(self)
        raise OSError("replace failed")

    monkeypatch.setattr(Path, "replace", fake_replace)
    with pytest.raises(OSError, match="replace failed"):
        add_words_module.atomic_write_text(target, "new\n")

    assert leaked
    assert not leaked[0].exists()
    monkeypatch.setattr(Path, "replace", original_replace)


def test_main_buffers_output_until_after_atomic_write(
    add_words_module, monkeypatch, tracking_file, capsys
):
    records = [
        add_words_module.BatchRecord(
            input_word="gut",
            lemma="gut",
            word_type="Adjective",
            status="added",
            audio="Gut.wav",
            error=None,
        )
    ]
    staged_rows = [
        add_words_module.StagedRow(
            word="gut",
            status="pending",
            audio_filename="Gut.wav",
            word_type="Adjective",
        )
    ]

    monkeypatch.setattr(
        add_words_module,
        "plan_batch",
        lambda words, timeout, tracking_content, console: (staged_rows, records),
    )
    monkeypatch.setattr(
        add_words_module,
        "atomic_write_text",
        lambda path, content: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(RuntimeError):
        add_words_module.main(["--words", "gut"])

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Resolving" not in captured.err
    assert "gut" not in tracking_file.read_text(encoding="utf-8")


def test_main_writes_rows_and_emits_ndjson(add_words_module, monkeypatch, tracking_file, capsys):
    # Real shape: Hinausgegangen page is an inflected form (Konjugierte Form)
    # pointing at hinausgehen via Grundformverweis. The script must re-query
    # hinausgehen to obtain the Verb POS.
    payloads = {
        "Hinausgegangen": parsetree_payload(
            "Hinausgegangen",
            [{"wortart": "Konjugierte Form", "grundformverweis": "hinausgehen"}],
        ),
        "hinausgehen": german_entry("hinausgehen", "Verb"),
    }

    monkeypatch.setattr(
        add_words_module, "fetch_parse_payload", lambda word, timeout: payloads[word]
    )
    monkeypatch.setattr(
        add_words_module,
        "generate_audio",
        lambda lemma: (True, "Hinausgehen.wav", "Generated hinausgehen"),
    )

    exit_code = add_words_module.main(["--words", "Hinausgegangen"])
    captured = capsys.readouterr()

    assert exit_code == 0
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record == {
        "input": "Hinausgegangen",
        "lemma": "hinausgehen",
        "type": "Verb",
        "status": "added",
        "audio": "Hinausgehen.wav",
        "error": None,
        "tracking_status": None,
    }
    assert "Resolving Hinausgegangen" in captured.err
    assert (
        "| hinausgehen | pending | ✅ Hinausgehen.wav | — | Verb | — | — |"
        in tracking_file.read_text(encoding="utf-8")
    )


def test_main_mixed_batch_integration(add_words_module, monkeypatch, tracking_file, capsys):
    write_tracking(
        tracking_file,
        [
            "| Lieb | pending | ✅ Lieb.wav | — | Adjective | — | — |",
            "| bis | pending | ✅ Bis.wav | — | Preposition | — | — |",
        ],
    )

    def fake_fetch(word, timeout):
        if word in {"ghost", "Ghost"}:
            raise add_words_module.LookupErrorResult("no Wiktionary entry")
        payloads = {
            "bearbeiten": german_entry("bearbeiten", "Verb"),
            "lieb": german_entry("Lieb", "Adjektiv"),
            "kaputt": german_entry("kaputt", "Adjektiv"),
            "gleich": german_entry("gleich", "Adjektiv", "Adverb"),
            "bis": german_entry("bis", "Präposition", "Konjunktion"),
        }
        return payloads[word]

    def fake_audio(lemma):
        if lemma == "kaputt":
            return False, None, "audio backend failed"
        return True, f"{lemma.capitalize()}.wav", f"Generated {lemma}"

    monkeypatch.setattr(add_words_module, "fetch_parse_payload", fake_fetch)
    monkeypatch.setattr(add_words_module, "generate_audio", fake_audio)

    exit_code = add_words_module.main(["--words", "bearbeiten lieb ghost kaputt gleich bis"])
    captured = capsys.readouterr()

    assert exit_code == 0
    records = [json.loads(line) for line in captured.out.splitlines() if line.strip()]
    assert records == [
        {
            "input": "bearbeiten",
            "lemma": "bearbeiten",
            "type": "Verb",
            "status": "added",
            "audio": "Bearbeiten.wav",
            "error": None,
            "tracking_status": None,
        },
        {
            "input": "lieb",
            "lemma": "Lieb",
            "type": "Adjective",
            "status": "skipped_dup",
            "audio": None,
            "error": None,
            "tracking_status": "pending",
        },
        {
            "input": "ghost",
            "lemma": "ghost",
            "type": None,
            "status": "failed",
            "audio": None,
            "error": "no Wiktionary entry",
            "tracking_status": None,
        },
        {
            "input": "kaputt",
            "lemma": "kaputt",
            "type": "Adjective",
            "status": "failed",
            "audio": None,
            "error": "audio backend failed",
            "tracking_status": None,
        },
        {
            "input": "gleich",
            "lemma": "gleich",
            "type": "Adjective/Adverb",
            "status": "added",
            "audio": "Gleich.wav",
            "error": None,
            "tracking_status": None,
        },
        {
            "input": "bis",
            "lemma": "bis",
            "type": "Preposition",
            "status": "skipped_dup",
            "audio": None,
            "error": None,
            "tracking_status": "pending",
        },
        {
            "input": "bis",
            "lemma": "bis",
            "type": "Conjunction",
            "status": "added",
            "audio": "Bis.wav",
            "error": None,
            "tracking_status": None,
        },
    ]

    content = tracking_file.read_text(encoding="utf-8")
    assert "| bearbeiten | pending | ✅ Bearbeiten.wav | — | Verb | — | — |" in content
    assert "| gleich | pending | ✅ Gleich.wav | — | Adjective/Adverb | — | — |" in content
    assert "| bis | pending | ✅ Bis.wav | — | Conjunction | — | — |" in content
    assert "| kaputt | pending | ✅ Kaputt.wav | — | Adjective | — | — |" not in content


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


@pytest.fixture
def wiktionary_server(tmp_path):
    responses = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlparse

            word = parse_qs(urlparse(self.path).query).get("page", [""])[0]
            status, body = responses[word]
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode("utf-8"))

        def log_message(self, format, *args):
            return

    server = ReusableTCPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/w/api.php", responses
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_subprocess_smoke(tmp_path, wiktionary_server):
    base_url, responses = wiktionary_server
    # Real-shape fixture: Hinausgegangen is a Konjugierte Form page that
    # redirects via Grundformverweis, then add_words.py re-queries hinausgehen
    # to fetch the actual Verb POS. This exercises the full
    # inflected-form -> lemma re-query path end-to-end.
    responses["Hinausgegangen"] = (
        200,
        parsetree_payload(
            "Hinausgegangen",
            [{"wortart": "Konjugierte Form", "grundformverweis": "hinausgehen"}],
        ),
    )
    responses["hinausgehen"] = (200, german_entry("hinausgehen", "Verb"))

    tracking = tmp_path / "word_tracking.md"
    write_tracking(tracking, [])

    audio_scripts_dir = tmp_path / "audio_scripts"
    audio_scripts_dir.mkdir()
    (audio_scripts_dir / "de_DE-thorsten-high.onnx").write_text("x", encoding="utf-8")
    (audio_scripts_dir / "de_DE-thorsten-high.onnx.json").write_text("{}", encoding="utf-8")

    audio_output_dir = tmp_path / "audio_out"
    audio_output_dir.mkdir()

    fake_modules = tmp_path / "fake_modules"
    fake_modules.mkdir()
    (fake_modules / "piper.py").write_text(
        "import argparse\n"
        "from pathlib import Path\n"
        "parser=argparse.ArgumentParser()\n"
        "parser.add_argument('--model')\n"
        "parser.add_argument('--config')\n"
        "parser.add_argument('--length-scale')\n"
        "parser.add_argument('--output_file')\n"
        "args=parser.parse_args()\n"
        "Path(args.output_file).write_bytes(b'RIFF')\n",
        encoding="utf-8",
    )

    project_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["ADD_WORDS_WIKTIONARY_BASE_URL"] = base_url
    env["ADD_WORDS_TRACKING_FILE"] = str(tracking)
    env["ADD_WORDS_AUDIO_SCRIPTS_DIR"] = str(audio_scripts_dir)
    env["ADD_WORDS_AUDIO_OUTPUT_DIR"] = str(audio_output_dir)
    env["PYTHONPATH"] = str(fake_modules)

    result = subprocess.run(
        [
            resolve_test_python(project_root),
            "flashcards/scripts/add_words.py",
            "--words",
            "Hinausgegangen",
        ],
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    stdout_lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    assert json.loads(stdout_lines[0]) == {
        "input": "Hinausgegangen",
        "lemma": "hinausgehen",
        "type": "Verb",
        "status": "added",
        "audio": "Hinausgehen.wav",
        "error": None,
        "tracking_status": None,
    }
    assert "Resolving Hinausgegangen" in result.stderr
    assert (
        "| hinausgehen | pending | ✅ Hinausgehen.wav | — | Verb | — | — |"
        in tracking.read_text(encoding="utf-8")
    )
