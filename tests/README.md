# Tests

```bash
cd backend && pip install -r requirements.txt && pip install pytest
cd .. && pytest -q
```

`test_full_conversion_creates_docx` runs the whole pipeline and asserts a real
`.docx` (with a Word table, and OMML equations when pandoc is available) is
produced.
