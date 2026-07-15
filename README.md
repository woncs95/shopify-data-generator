# Shopify Data Generator

Streamlit tooling for discovering Shopify product context, preparing product registration data, and creating product drafts.

## Layout

- `app/` - Streamlit application code.
- `shopify_data_generator/` - shared Python modules and path helpers.
- `scripts/` - Shopify discovery and maintenance CLI helpers.
- `data/` - local CSV fixtures and generated Shopify context files.
- `runtime/` - local run outputs, logs, and generated review files.
- `infra/` - optional SearXNG support services.
- `tests/` - unittest coverage.
- root `*.py` files - thin compatibility wrappers for existing commands.

## Run

```powershell
.\run_registration_ui.bat
```

or:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app\shopify_registration_app.py
```

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
