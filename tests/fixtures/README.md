# Test fixtures

Small binary fixtures for the extraction tests (PRD 5). Most inputs are generated **in-test** from
the runtime libraries (`python-docx`/`openpyxl`/`python-pptx`, and `pypdf` for blank/encrypted PDFs),
so only files that need an external generator are committed here.

## `text_layer.pdf`

A one-page, born-digital (text-layer) PDF containing the strings
`Hello Aretea board deck` and `Q3 revenue up 12 percent`. Committed rather than generated in-test
because `pypdf` cannot author a text layer; regenerated once with `reportlab` in an ephemeral overlay
(no project dependency added):

```bash
uv run --with reportlab python - <<'PY'
import io, pathlib
from reportlab.pdfgen import canvas
buf = io.BytesIO()
c = canvas.Canvas(buf, pagesize=(300, 200))
c.setFont("Helvetica", 16)
c.drawString(30, 120, "Hello Aretea board deck")
c.drawString(30, 90, "Q3 revenue up 12 percent")
c.showPage(); c.save()
pathlib.Path("tests/fixtures/text_layer.pdf").write_bytes(buf.getvalue())
PY
```
