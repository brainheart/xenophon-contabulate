# Xenophon Contabulate

Static single-page contabulate search for Xenophon’s extant Greek works available in the Perseus Digital Library canonical Greek TEI corpus.

The app is fully deployable from `docs/` to GitHub Pages. There is no backend and no frontend build step: the site is plain HTML, CSS, JavaScript, and prebuilt JSON data files.

## Source Texts

The Greek source texts in `source_text/` come from the Perseus Digital Library TEI XML editions under author `tlg0032`:

- `tlg001` — *Hellenica*
- `tlg002` — *Memorabilia*
- `tlg003` — *Oeconomicus* / *Economics*
- `tlg004` — *Symposium*
- `tlg005` — *Apology*
- `tlg006` — *Anabasis*
- `tlg007` — *Cyropaedia*
- `tlg008` — *Hiero*
- `tlg009` — *Agesilaus*
- `tlg010` — *Constitution of the Lacedaemonians*
- `tlg011` — *Ways and Means*
- `tlg012` — *On the Cavalry Commander*
- `tlg013` — *On the Art of Horsemanship*
- `tlg014` — *On Hunting*

Perseus Digital Library: <https://www.perseus.tufts.edu/hopper/>  
Canonical Greek Literature repository: <https://github.com/PerseusDL/canonical-greekLit>

## Build

Rebuild the static JSON data:

```bash
python3 scripts/build_data.py
```

This writes:

- `docs/data/plays.json`
- `docs/data/characters.json`
- `docs/data/chunks.json`
- `docs/data/tokens.json`
- `docs/data/tokens2.json`
- `docs/data/tokens3.json`
- `docs/data/tokens_char.json`
- `docs/data/tokens_char2.json`
- `docs/data/tokens_char3.json`
- `docs/data/character_name_filter_config.json`
- `docs/lines/all_lines.json`

The internal data model follows the reference Contabulate app contract:

- `plays` = works
- `characters` = book-level units when a work has books; otherwise whole-work units
- `chunks` = section-level contexts (`Xen.Hell.1.1.1`, etc.)

## Local Preview

Serve the static site locally:

```bash
python3 -m http.server 4173
```

Then open:

```text
http://127.0.0.1:4173/docs/
```

## Tests

Python structure checks:

```bash
python3 -m pytest tests/test_build_output.py
```

Playwright smoke test:

```bash
npx playwright test
```

## Deployment

Publish the contents of `docs/` to GitHub Pages. The custom domain is configured through:

- `docs/CNAME`

with:

```text
xenophon.contabulate.org
```
