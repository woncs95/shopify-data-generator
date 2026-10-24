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

## Product categories and metafield recovery

Select a Shopify product category before generating a new draft. Use **Load existing
product category** when updating an existing product. Only compatible metafields
are offered to AI; previous values remain visible when the category changes.
Definitions and the product's actual category are checked again before saving.

**Recommend categories with AI** researches the product and ranks up to three real
Shopify taxonomy categories, with a reason and confidence for each. Review the
suggestion and click **Use recommended category**, or use manual search. No category
is saved to Shopify until you submit the product. Research from the recommendation
is reused when generating the draft. Category recommendations use OpenRouter and
may incur model costs.

Metafields are saved in batches of at most 25, with category-constrained fields
separate from other fields. A failed batch stays queued and the app reports
**Product saved / metafields incomplete**, including the failing field names.
Correct inputs and use **Retry failed metafields only** to avoid repeating product,
variant, or inventory writes. Clearing an editable failed value or explicitly
excluding a field omits it from retry; this does not delete an existing Shopify value.

Bulk uploads accept an optional `category_id` column containing a Shopify taxonomy
category GID. The screen selection is the default for new products. Existing
products retain their category unless the row explicitly specifies `category_id`.
The bulk AI category option fills missing categories for new products only; rows
without a high-confidence recommendation stop for category review.
Bulk partial results retain their product IDs and failed payloads. **Retry failed
bulk metafields only** retries those values using each product's current Shopify
category; invalid values must be corrected through the registration form.

## Product image discovery

Image discovery uses **OpenRouter web first**, then **SearXNG**, then **SerpAPI**.
A fallback runs only if the previous provider produces no usable product images
(including search errors, blocked pages, or rejected image files). The normal
text/ingredient research workflow is separate and retains its existing search order.

OpenRouter finds official brand/authorized retailer product pages, not invented
image URLs. The app extracts structured product/gallery images, checks product
names, brand evidence and stated sizes, validates image bytes and dimensions, and
removes duplicates. Official status is AI-identified and its evidence is shown;
fallback retailer authorization is explicitly unverified. Review the visual product,
packaging and variant before selecting images.

Generate a draft or use **Find / refresh product images**. Review thumbnails and
source links, select images, then click **Use selected images** to replace the
approved URL list. **Download all discovered image links** exports every retained
candidate. Image inputs reset when the product identity changes.

Each provider examines up to 8 pages and 80 image candidates. Downloads are limited
to 15 MB; images need a short side of at least 150 px and a long side of 500 px.
The app flags when search limits are reached. JavaScript-only galleries and blocked
pages may not be extractable; results are all verified candidates within these
limits, not a guarantee of every image on the internet.

Bulk rows with an empty `image_urls` cell can use the same search order to attach
up to 20 images; the result retains all discovered links and warnings. Existing
user-provided image URLs take precedence. OpenRouter web image search uses the web
plugin regardless of the separate draft-generation web toggle and can incur costs.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
