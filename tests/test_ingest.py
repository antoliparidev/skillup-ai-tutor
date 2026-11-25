from pathlib import Path

from skillup.ingest import MAX_CARATTERI, dividi, leggi_frontmatter, prepara

CAMPIONE = Path("sample_data")


def test_frontmatter_letto() -> None:
    fm, corpo = leggi_frontmatter('---\ncorso: "X"\npagina: "P"\n---\n# Titolo\n')
    assert fm == {"corso": "X", "pagina": "P"}
    assert "# Titolo" in corpo


def test_divide_ai_titoli_e_ai_summary() -> None:
    corpo = "## Primo\n" + "a" * 60 + "\n<summary>Secondo</summary>\n" + "b" * 60
    pezzi = dividi(corpo, "Pagina")
    assert [p.titolo for p in pezzi] == ["Primo", "Secondo"]


def test_non_spezza_il_codice() -> None:
    corpo = "## Codice\ntesto introduttivo abbastanza lungo\n```\n## non è un titolo\nx = 1\n```\n"
    pezzi = dividi(corpo, "Pagina")
    assert len(pezzi) == 1
    assert "## non è un titolo" in pezzi[0].testo


def test_blocco_di_codice_lungo_resta_intero() -> None:
    codice = "```\n" + "\n".join(f"riga {i}" for i in range(600)) + "\n```"
    corpo = "## Lungo\n" + "introduzione\n\n" + codice
    pezzi = dividi(corpo, "Pagina")
    assert any(p.testo.startswith("```") and p.testo.endswith("```") for p in pezzi)
    assert len(codice) > MAX_CARATTERI


def test_campione_ha_metadati_per_citare() -> None:
    righe = prepara(CAMPIONE)
    assert righe, "il campione deve produrre dei chunk"
    for r in righe:
        assert r["corso_id"] == "99_corso-inventato"
        assert r["link"].startswith("https://")