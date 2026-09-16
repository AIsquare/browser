# DOM extraction prototype — fixed Markdown/code extraction

This version keeps the existing Playwright + BeautifulSoup architecture but fixes code-block extraction so visual line-number gutters are not copied into the Markdown.

## Install

```powershell
pip install playwright beautifulsoup4 lxml
playwright install chromium
```

## Run

```powershell
python dom_extract.py
```

## What was fixed

- Code is extracted from the `<code>` element when present, avoiding sibling UI such as line-number gutters.
- Common line-number/gutter elements are removed when necessary.
- A leading `1, 2, 3, ...` line-number sequence is removed as a fallback.
- Code language hints such as `language-python` / `lang-python` are preserved.
- Markdown code fences are emitted as real fences, with a language hint when available.
- If the code itself contains triple backticks, a `~~~` fence is used instead.

The rest of the extractor architecture is unchanged.
