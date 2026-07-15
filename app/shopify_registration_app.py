import csv
import hashlib
import html
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd
import streamlit as st

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shopify_data_generator.paths import ENV_FILE, SCRIPTS_DIR, data_path, runtime_path


SHOPIFY_API_VERSION = "2025-10"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_USER_MODELS_URL = "https://openrouter.ai/api/v1/models/user"
GOOGLE_CUSTOM_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"
BRAVE_WEB_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
SERPAPI_SEARCH_URL = "https://serpapi.com/search.json"
SEARXNG_DEFAULT_BASE_URL = "http://localhost:8888"
MIRAKL_DEFAULT_BASE_URL = "https://shopapotheke.mirakl.net"
MIRAKL_MARKETPLACES = {
    "shop_apotheke": {
        "label": "Shop Apotheke",
        "slug": "shop_apotheke",
        "default_instance": "shopapotheke.mirakl.net",
        "api_key_env": "MIRAKL_API_KEY",
        "api_key_keys": ["MIRAKL_API_KEY", "MIRAKL_SHOP_APOTHEKE_API_KEY"],
        "base_url_keys": ["MIRAKL_BASE_URL", "MIRAKL_SHOP_APOTHEKE_BASE_URL"],
        "instance_keys": ["MIRAKL_INSTANCE", "MIRAKL_SHOP_APOTHEKE_INSTANCE"],
    },
    "douglas": {
        "label": "Douglas",
        "slug": "douglas",
        "default_instance": "douglas-prod.mirakl.net",
        "api_key_env": "MIRAKL_DOUGLAS_API_KEY",
        "api_key_keys": ["MIRAKL_DOUGLAS_API_KEY", "DOUGLAS_MIRAKL_API_KEY"],
        "base_url_keys": ["MIRAKL_DOUGLAS_BASE_URL", "DOUGLAS_MIRAKL_BASE_URL"],
        "instance_keys": ["MIRAKL_DOUGLAS_INSTANCE", "DOUGLAS_MIRAKL_INSTANCE"],
    },
}
ROOT = REPO_ROOT
SEO_TITLE_MAX = 69
SEO_DESCRIPTION_MAX = 159
DISALLOWED_SEO_DESCRIPTION_SYMBOLS = set("!¡?¿#@$%^*_=+~`|\\/<>[]{}")
CONTENT_LANGUAGE_OPTIONS = ["German", "English", "Korean", "French", "Spanish", "Italian", "Dutch"]
BARCODE_MODE_OPTIONS = ["auto from web", "manual"]
OPENROUTER_MODEL_SORT_OPTIONS = [
    "Name A-Z",
    "Cheapest input",
    "Cheapest output",
    "Cheapest input + output",
    "Largest context",
    "Performance tier (heuristic)",
]
OPENROUTER_MODEL_COST_FILTER_OPTIONS = ["All", "Paid only", "Free only"]
OPENROUTER_DEFAULT_FALLBACK_MODEL = "openai/gpt-4o-mini"
CONTENT_LANGUAGE_HINTS = {
    "German": "German for Germany, natural ecommerce German",
    "English": "English, natural ecommerce English",
    "Korean": "Korean, natural ecommerce Korean",
    "French": "French, natural ecommerce French",
    "Spanish": "Spanish, natural ecommerce Spanish",
    "Italian": "Italian, natural ecommerce Italian",
    "Dutch": "Dutch, natural ecommerce Dutch",
}
VOLUME_UNITS = {"ML", "CL", "L"}
WEIGHT_UNITS = {"MG", "G", "KG"}
UNIT_PRICE_REFERENCE_OPTIONS = ["1 L", "1 KG"]
BULK_INPUT_COLUMNS = [
    "product_name",
    "vendor",
    "inventory_quantity",
    "content_language",
    "barcode_mode",
    "manual_barcode",
    "price_mode",
    "discounted_price",
    "retail_price",
    "measurement_label",
    "image_urls",
]
BULK_REQUIRED_COLUMNS = ["product_name", "vendor", "inventory_quantity"]
BULK_TEMPLATE_SAMPLE = {
    "product_name": "mixsoon Bean Cream [65ml]",
    "vendor": "mixsoon",
    "inventory_quantity": 0,
    "content_language": "German",
    "barcode_mode": "auto from web",
    "manual_barcode": "",
    "price_mode": "manual",
    "discounted_price": "",
    "retail_price": "",
    "measurement_label": "65 ml",
    "image_urls": "https://example.com/product-front.jpg\nhttps://example.com/product-box.jpg",
}


def render_professional_theme() -> None:
    st.markdown(
        """
<style>
:root {
    --app-bg: #f5f7fa;
    --panel-bg: #ffffff;
    --panel-subtle: #f9fafb;
    --border: #d9e1e8;
    --border-strong: #c6d1dc;
    --text: #18212f;
    --muted: #5f6c7b;
    --accent: #0f766e;
    --accent-dark: #115e59;
    --success: #157347;
    --warning: #a16207;
    --danger: #b42318;
}

.stApp {
    background: var(--app-bg);
    color: var(--text);
}

[data-testid="stHeader"] {
    background: rgba(245, 247, 250, 0.92);
    backdrop-filter: blur(8px);
    border-bottom: 1px solid rgba(217, 225, 232, 0.75);
}

.block-container {
    max-width: 1480px;
    padding-top: 1.35rem;
    padding-bottom: 3rem;
}

h1, h2, h3 {
    color: var(--text);
    letter-spacing: 0;
}

h2, h3 {
    padding-top: 0.65rem;
}

p, label, span, div {
    letter-spacing: 0;
}

[data-testid="stSidebar"] {
    background: #ffffff;
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.8rem;
}

[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-size: 1rem;
    margin-bottom: 0.2rem;
}

[data-testid="stSidebar"] .stButton > button {
    width: 100%;
}

.app-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1.25rem;
    padding: 0.2rem 0 1rem;
    margin-bottom: 1rem;
    border-bottom: 1px solid var(--border);
}

.app-kicker {
    color: var(--accent);
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.app-title {
    margin: 0.18rem 0 0;
    color: var(--text);
    font-size: clamp(1.85rem, 3vw, 2.65rem);
    font-weight: 760;
    line-height: 1.04;
}

.app-meta {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    min-height: 2rem;
    padding: 0.32rem 0.58rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--muted);
    background: var(--panel-bg);
    font-size: 0.82rem;
    font-weight: 650;
    white-space: nowrap;
}

.status-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
    margin: 0.15rem 0 1.15rem;
}

.status-tile {
    min-height: 5.15rem;
    padding: 0.75rem 0.82rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel-bg);
}

.status-label {
    color: var(--muted);
    font-size: 0.73rem;
    font-weight: 720;
    letter-spacing: 0.06em;
    text-transform: uppercase;
}

.status-value {
    display: flex;
    align-items: center;
    gap: 0.48rem;
    margin-top: 0.48rem;
    color: var(--text);
    font-size: 0.98rem;
    font-weight: 720;
}

.status-detail {
    margin-top: 0.28rem;
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.28;
    overflow-wrap: anywhere;
}

.status-dot {
    width: 0.58rem;
    height: 0.58rem;
    flex: 0 0 auto;
    border-radius: 999px;
    background: var(--danger);
}

.status-ok .status-dot {
    background: var(--success);
}

.status-warning .status-dot {
    background: var(--warning);
}

.sidebar-status {
    display: grid;
    gap: 0.45rem;
    margin: 0.2rem 0 0.3rem;
}

.sidebar-status-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.55rem 0.65rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel-subtle);
}

.sidebar-status-label {
    color: var(--text);
    font-size: 0.85rem;
    font-weight: 650;
}

.sidebar-pill {
    border-radius: 999px;
    padding: 0.18rem 0.48rem;
    color: #ffffff;
    background: var(--danger);
    font-size: 0.72rem;
    font-weight: 720;
    line-height: 1.3;
    white-space: nowrap;
}

.sidebar-pill.ok {
    background: var(--success);
}

.stButton > button,
.stDownloadButton > button {
    border-radius: 6px;
    border: 1px solid var(--border-strong);
    background: #ffffff;
    color: var(--text);
    font-weight: 680;
    min-height: 2.45rem;
    box-shadow: none;
}

.stButton > button:hover,
.stDownloadButton > button:hover {
    border-color: var(--accent);
    color: var(--accent-dark);
}

.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"],
.stDownloadButton > button[kind="primary"],
.stDownloadButton > button[data-testid="stBaseButton-primary"] {
    border-color: var(--accent);
    background: var(--accent);
    color: #ffffff;
}

.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
.stDownloadButton > button[data-testid="stBaseButton-primary"]:hover {
    border-color: var(--accent-dark);
    background: var(--accent-dark);
    color: #ffffff;
}

[data-testid="stMetric"] {
    padding: 0.72rem 0.8rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel-bg);
}

[data-testid="stMetricLabel"] {
    color: var(--muted);
}

[data-testid="stMetricValue"] {
    color: var(--text);
    font-size: 1.55rem;
    font-weight: 760;
}

[data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--panel-bg);
}

[data-testid="stAlert"] {
    border-radius: 8px;
    border-width: 1px;
}

.stTextInput input,
.stNumberInput input,
.stTextArea textarea,
.stSelectbox div[data-baseweb="select"] > div,
.stMultiSelect div[data-baseweb="select"] > div {
    border-radius: 6px;
    border-color: var(--border-strong);
    background: #ffffff;
}

div[data-testid="stRadio"] > div {
    gap: 0.55rem;
}

hr {
    margin: 1.25rem 0;
    border-color: var(--border);
}

@media (max-width: 920px) {
    .app-header {
        align-items: flex-start;
        flex-direction: column;
    }

    .status-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 620px) {
    .status-grid {
        grid-template-columns: 1fr;
    }
}
</style>
        """,
        unsafe_allow_html=True,
    )


def status_state(ok: bool, warning: bool = False) -> str:
    if ok:
        return "ok"
    if warning:
        return "warning"
    return "missing"


def render_app_header() -> None:
    st.markdown(
        """
<div class="app-header">
    <div>
        <div class="app-kicker">Shopify Product Registration</div>
        <h1 class="app-title">Product Operations Console</h1>
    </div>
    <div class="app-meta">Draft mode</div>
</div>
        """,
        unsafe_allow_html=True,
    )


def render_status_grid(items: list[dict[str, str]]) -> None:
    tiles = []
    for item in items:
        state = html.escape(item["state"])
        label = html.escape(item["label"])
        value = html.escape(item["value"])
        detail = html.escape(item.get("detail", ""))
        tiles.append(
            f"""
<div class="status-tile status-{state}">
    <div class="status-label">{label}</div>
    <div class="status-value"><span class="status-dot"></span>{value}</div>
    <div class="status-detail">{detail}</div>
</div>
            """
        )
    st.markdown(f'<div class="status-grid">{"".join(tiles)}</div>', unsafe_allow_html=True)


def render_sidebar_status(items: list[dict[str, str]]) -> None:
    rows = []
    for item in items:
        state = item["state"]
        pill_class = "ok" if state == "ok" else ""
        status_label = "Ready" if state == "ok" else "Missing"
        rows.append(
            f"""
<div class="sidebar-status-row">
    <span class="sidebar-status-label">{html.escape(item["label"])}</span>
    <span class="sidebar-pill {pill_class}">{status_label}</span>
</div>
            """
        )
    st.markdown(f'<div class="sidebar-status">{"".join(rows)}</div>', unsafe_allow_html=True)


REQUIRED_TEXT_METAFIELDS = {
    "custom.inci",
    "custom.benefits",
    "custom.how_to_use",
    "custom.beschreibung_frontend",
    "custom.key_features",
    "custom.skin_type",
    "custom.zahlenfakten_frontend",
}

REQUIRED_PRODUCT_REFERENCE_METAFIELDS = {
    "shopify--discovery--product_recommendation.complementary_products": "Complementary products",
    "shopify--discovery--product_recommendation.related_products": "Related products",
}
REQUIRED_PRODUCT_REFERENCE_DRAFT_KEYS = {
    "shopify--discovery--product_recommendation.complementary_products": "complementary_product_handles",
    "shopify--discovery--product_recommendation.related_products": "related_product_handles",
}

REQUIRED_SEARCH_BOOST_METAFIELD = "shopify--discovery--product_search_boost.queries"
BLOCKED_AI_METAFIELDS = {
    "shopify--discovery--product_recommendation.related_products_display",
    REQUIRED_SEARCH_BOOST_METAFIELD,
}


CREATE_PRODUCT_MUTATION = """
mutation CreateProduct($product: ProductCreateInput!) {
  productCreate(product: $product) {
    product {
      id
      title
      handle
      status
      variants(first: 1) {
        nodes {
          id
          inventoryItem {
            id
          }
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


UPDATE_VARIANT_MUTATION = """
mutation UpdateVariantWithInventoryItem($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants {
      id
      barcode
      price
      inventoryItem {
        id
        sku
        tracked
        countryCodeOfOrigin
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


SET_INVENTORY_MUTATION = """
mutation SetInventory($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup {
      createdAt
      reason
    }
    userErrors {
      field
      message
    }
  }
}
"""


UPDATE_PRODUCT_MEDIA_MUTATION = """
mutation UpdateProductWithMedia($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
  productUpdate(product: $product, media: $media) {
    product {
      id
      title
    }
    userErrors {
      field
      message
    }
  }
}
"""


UPDATE_PRODUCT_MUTATION = """
mutation UpdateExistingProduct($product: ProductUpdateInput!, $media: [CreateMediaInput!]) {
  productUpdate(product: $product, media: $media) {
    product {
      id
      title
      handle
      status
      variants(first: 1) {
        nodes {
          id
          inventoryItem {
            id
          }
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


SET_METAFIELDS_MUTATION = """
mutation SetProductMetafields($metafields: [MetafieldsSetInput!]!) {
  metafieldsSet(metafields: $metafields) {
    metafields {
      id
      namespace
      key
      type
    }
    userErrors {
      field
      message
    }
  }
}
"""


FIND_VARIANT_BY_BARCODE_QUERY = """
query FindVariantByBarcode($query: String!) {
  productVariants(first: 5, query: $query) {
    nodes {
      id
      sku
      barcode
      inventoryItem {
        id
      }
      product {
        id
        title
        handle
        status
      }
    }
  }
}
"""


FIND_PRODUCT_BY_HANDLE_QUERY = """
query FindProductByHandle($handle: String!) {
  productByIdentifier(identifier: {handle: $handle}) {
    id
    title
    handle
    status
    variants(first: 1) {
      nodes {
        id
        inventoryItem {
          id
        }
      }
    }
  }
}
"""


METAOBJECT_DEFINITION_CHOICES_QUERY = """
query MetaobjectDefinitionChoices($id: ID!, $first: Int!) {
  metaobjectDefinition(id: $id) {
    id
    name
    type
    displayNameKey
    metaobjects(first: $first) {
      nodes {
        id
        handle
        displayName
      }
    }
  }
}
"""


SHOPIFY_PRODUCTS_FOR_MIRAKL_QUERY = """
query ShopifyProductsForMirakl($first: Int!, $after: String, $query: String) {
  products(first: $first, after: $after, query: $query) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      title
      handle
      vendor
      status
      productType
      descriptionHtml
      media(first: 5) {
        nodes {
          ... on MediaImage {
            image {
              url
              altText
            }
          }
        }
      }
      variants(first: 10) {
        nodes {
          id
          title
          sku
          barcode
          price
          compareAtPrice
          inventoryQuantity
        }
      }
      metafields(first: 100) {
        nodes {
          namespace
          key
          type
          value
        }
      }
    }
  }
}
"""


CREATE_STAGED_IMAGE_UPLOAD_MUTATION = """
mutation CreateStagedImageUpload($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets {
      url
      resourceUrl
      parameters {
        name
        value
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


CREATE_SHOPIFY_FILE_MUTATION = """
mutation CreateShopifyFile($files: [FileCreateInput!]!) {
  fileCreate(files: $files) {
    files {
      id
      fileStatus
      alt
      createdAt
      ... on MediaImage {
        image {
          url
          width
          height
        }
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


SHOPIFY_FILE_IMAGE_URL_QUERY = """
query ShopifyFileImageUrl($id: ID!) {
  node(id: $id) {
    ... on MediaImage {
      id
      fileStatus
      image {
        url
        width
        height
      }
    }
  }
}
"""


AI_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "description_html": {"type": "string"},
        "product_type": {"type": "string"},
        "handle": {"type": "string"},
        "existing_tags": {"type": "array", "items": {"type": "string"}},
        "proposed_new_tags": {"type": "array", "items": {"type": "string"}},
        "barcode": {"type": "string"},
        "price": {"type": "string"},
        "compare_at_price": {"type": "string"},
        "weight_value": {"type": "number"},
        "weight_unit": {"type": "string", "enum": ["GRAMS", "KILOGRAMS", "OUNCES", "POUNDS"]},
        "image_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "alt": {"type": "string"},
                    "source_url": {"type": "string"},
                },
                "required": ["url", "alt", "source_url"],
                "additionalProperties": False,
            },
        },
        "complementary_product_handles": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "related_product_handles": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "search_product_boost_handles": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
        "metafields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "namespace": {"type": "string"},
                    "key": {"type": "string"},
                    "type": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    "source_url": {"type": "string"},
                },
                "required": ["namespace", "key", "type", "value", "confidence", "source_url"],
                "additionalProperties": False,
            },
        },
        "sources": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "title",
        "seo_title",
        "seo_description",
        "description_html",
        "product_type",
        "handle",
        "existing_tags",
        "proposed_new_tags",
        "barcode",
        "price",
        "compare_at_price",
        "weight_value",
        "weight_unit",
        "image_candidates",
        "complementary_product_handles",
        "related_product_handles",
        "search_product_boost_handles",
        "metafields",
        "sources",
        "warnings",
    ],
    "additionalProperties": False,
}


SEO_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "seo_description": {"type": "string"},
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "seo_description", "warnings"],
    "additionalProperties": False,
}


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def normalize_shopify_host(store: str) -> str:
    if store.startswith(("http://", "https://")):
        host = urlparse(store).netloc
    else:
        host = store
    host = host.removeprefix("admin.")
    if "." not in host:
        host = f"{host}.myshopify.com"
    return host


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return slug.strip("-")[:240]


def parse_measurement_label(label: str) -> tuple[float, str] | None:
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*(ml|milliliter|millilitre|l|liter|litre|mg|g|gram|kg|kilogram|ea|item|pcs|pieces)\b",
        label,
        re.I,
    )
    if not match:
        return None
    value = float(match.group(1).replace(",", "."))
    unit_map = {
        "ml": "ML",
        "milliliter": "ML",
        "millilitre": "ML",
        "l": "L",
        "liter": "L",
        "litre": "L",
        "mg": "MG",
        "g": "G",
        "gram": "G",
        "kg": "KG",
        "kilogram": "KG",
        "ea": "ITEM",
        "item": "ITEM",
        "pcs": "ITEM",
        "pieces": "ITEM",
    }
    return value, unit_map[match.group(2).lower()]


def measurement_unit_family(unit: str) -> str:
    if unit in VOLUME_UNITS:
        return "volume"
    if unit in WEIGHT_UNITS:
        return "weight"
    return ""


def default_reference_for_quantity_unit(quantity_unit: str) -> tuple[int, str] | None:
    family = measurement_unit_family(quantity_unit)
    if family == "volume":
        return 1, "L"
    if family == "weight":
        return 1, "KG"
    return None


def unit_price_reference_label(quantity_unit: str) -> str:
    reference = default_reference_for_quantity_unit(quantity_unit)
    if not reference:
        return ""
    return f"{reference[0]} {reference[1]}"


def unit_options_for_family(quantity_unit: str) -> list[str]:
    family = measurement_unit_family(quantity_unit)
    if family == "weight":
        return ["MG", "G", "KG"]
    if family == "volume":
        return ["ML", "CL", "L"]
    return []


def is_inci_identity(identity: str) -> bool:
    return identity == "custom.inci"


def is_required_text_metafield(identity: str) -> bool:
    return identity in REQUIRED_TEXT_METAFIELDS


def inci_has_truncation_marker(value: str) -> bool:
    lowered = value.lower()
    markers = [
        "etc",
        "etc.",
        "...",
        "\uc0dd\ub7b5",
        "and others",
        "and more",
        "among others",
        "including but not limited to",
        "additional ingredients",
    ]
    return any(marker in lowered for marker in markers)


def is_clean_product_tag(tag: str) -> bool:
    normalized = tag.strip()
    if not normalized:
        return False
    lowered = normalized.lower()
    blocked_exact = {"ss", "ssp", "geschenk", "weihnachten", "wholesale"}
    blocked_terms = [" soap", "bubble bath", "badebombe", "badepulver", "schaumbad"]
    if lowered in blocked_exact:
        return False
    if any(term in lowered for term in blocked_terms):
        return False
    if normalized.isupper() and len(normalized) <= 4:
        return False
    return True


def safe_decimal(value: Any, fallback: str = "0.00") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    cleaned = re.sub(r"[^0-9.,-]", "", text).replace(",", ".")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return fallback


def sanitize_seo_description(value: Any) -> str:
    text = str(value or "").strip()
    text = "".join(char for char in text if char not in DISALLOWED_SEO_DESCRIPTION_SYMBOLS)
    return re.sub(r"\s+", " ", text).strip()[:SEO_DESCRIPTION_MAX]


def seo_description_symbols(value: str) -> list[str]:
    return sorted({char for char in value if char in DISALLOWED_SEO_DESCRIPTION_SYMBOLS})


def parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def parse_image_urls(value: str, limit: int = 20) -> list[str]:
    urls = []
    for item in re.split(r"[\n,;]+", value or ""):
        url = item.strip()
        if not url or not url.startswith(("http://", "https://")):
            continue
        if url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def bulk_template_bytes() -> bytes:
    buffer = io.BytesIO()
    template_df = pd.DataFrame([BULK_TEMPLATE_SAMPLE], columns=BULK_INPUT_COLUMNS)
    instructions_df = pd.DataFrame(
        [
            {
                "column": "product_name",
                "required": "yes",
                "notes": "Raw product name the user gives to AI.",
            },
            {
                "column": "vendor",
                "required": "yes",
                "notes": "Brand/vendor name.",
            },
            {
                "column": "inventory_quantity",
                "required": "yes",
                "notes": "Quantity for the single configured Shopify location.",
            },
            {
                "column": "content_language",
                "required": "no",
                "notes": "Default German. Affects SEO description and editable text metafields only.",
            },
            {
                "column": "barcode_mode",
                "required": "no",
                "notes": "auto from web or manual. If manual_barcode has a value, it is used as barcode and SKU.",
            },
            {
                "column": "manual_barcode",
                "required": "no",
                "notes": "Barcode/SKU to use when barcode_mode is manual. Overrides AI-found barcode.",
            },
            {
                "column": "price_mode",
                "required": "no",
                "notes": "manual or auto from web.",
            },
            {
                "column": "discounted_price",
                "required": "no",
                "notes": "Discounted selling price. Required when price_mode is manual.",
            },
            {
                "column": "retail_price",
                "required": "no",
                "notes": "Retail/original price. Written to Shopify compare-at price.",
            },
            {
                "column": "measurement_label",
                "required": "no",
                "notes": "Example: 50 ml, 100 g, 5 ea. Used for unit price measurement.",
            },
            {
                "column": "image_urls",
                "required": "no",
                "notes": "One or more public image URLs separated by new lines, commas, or semicolons.",
            },
        ]
    )
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        template_df.to_excel(writer, index=False, sheet_name="Products")
        instructions_df.to_excel(writer, index=False, sheet_name="Instructions")
        products_sheet = writer.book["Products"]
        instructions_sheet = writer.book["Instructions"]
        products_sheet.freeze_panes = "A2"
        instructions_sheet.freeze_panes = "A2"
        for sheet in (products_sheet, instructions_sheet):
            for cell in sheet[1]:
                cell.style = "Headline 3"
            for column_cells in sheet.columns:
                max_length = max(len(str(cell.value or "")) for cell in column_cells)
                sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 14), 46)
    return buffer.getvalue()


def bulk_cell(row: pd.Series, column: str, default: Any = "") -> str:
    value = row.get(column, default)
    if pd.isna(value):
        return str(default)
    return str(value).strip()


def clean_barcode(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "").strip())


def normalize_barcode_mode(value: Any, manual_barcode: str = "") -> str:
    mode = str(value or "").strip().lower()
    if mode in {"manual", "manuell", "manually"} or manual_barcode.strip():
        return "manual"
    return "auto from web"


def barcode_from_mode(auto_barcode: Any, barcode_mode: str, manual_barcode: Any) -> str:
    clean_manual = clean_barcode(manual_barcode)
    if normalize_barcode_mode(barcode_mode, clean_manual) == "manual":
        return clean_manual
    return clean_barcode(auto_barcode)


def is_metaobject_reference_type(definition_type: str) -> bool:
    return definition_type == "metaobject_reference" or definition_type.startswith("list.metaobject_reference")


def is_product_reference_type(definition_type: str) -> bool:
    return definition_type == "product_reference" or definition_type.startswith("list.product_reference")


def metafield_definition_validations(row: Any) -> list[dict[str, Any]]:
    raw_validations = row["validations"] if "validations" in row else ""
    validations = parse_json_list(raw_validations)
    return [item for item in validations if isinstance(item, dict)]


def metaobject_definition_id_from_row(row: Any) -> str:
    for validation in metafield_definition_validations(row):
        if validation.get("name") == "metaobject_definition_id":
            return str(validation.get("value") or "").strip()
    return ""


def normalized_match_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def reference_option_label(option: dict[str, str]) -> str:
    display_name = option.get("displayName") or option.get("handle") or option.get("id") or ""
    handle = option.get("handle") or ""
    return f"{display_name} ({handle})" if handle and handle != display_name else display_name


def match_reference_option_ids(raw_value: Any, options: list[dict[str, str]], limit: int = 20) -> list[str]:
    text = str(raw_value or "").strip()
    if not text or not options:
        return []
    requested_values = []
    parsed = parse_json_list(text)
    if parsed:
        requested_values.extend(str(item or "").strip() for item in parsed)
    requested_values.extend(item.strip() for item in re.split(r"[\n,;|]+", text) if item.strip())
    requested_values = [item for item in dict.fromkeys(requested_values) if item]

    option_tokens = {}
    for option in options:
        option_id = option.get("id") or ""
        tokens = {
            option_id,
            option.get("handle") or "",
            option.get("displayName") or "",
            reference_option_label(option),
        }
        option_tokens[option_id] = {token for token in tokens if token}

    selected_ids = []
    for requested in requested_values:
        normalized_requested = normalized_match_text(requested)
        for option_id, tokens in option_tokens.items():
            normalized_tokens = {normalized_match_text(token) for token in tokens}
            exact_match = requested in tokens or normalized_requested in normalized_tokens
            contains_match = normalized_requested and any(
                normalized_requested == token
                or normalized_requested in token
                or token in normalized_requested
                for token in normalized_tokens
                if token
            )
            if (exact_match or contains_match) and option_id and option_id not in selected_ids:
                selected_ids.append(option_id)
                break
        if len(selected_ids) >= limit:
            break
    return selected_ids


def reference_metafield_value(definition_type: str, raw_value: Any) -> str:
    ids = [
        str(item or "").strip()
        for item in parse_json_list(raw_value)
        if str(item or "").strip().startswith("gid://shopify/Metaobject/")
    ]
    if not ids:
        ids = [
            item.strip()
            for item in re.split(r"[\n,;|]+", str(raw_value or ""))
            if item.strip().startswith("gid://shopify/Metaobject/")
        ]
    ids = list(dict.fromkeys(ids))
    if not ids:
        return ""
    if definition_type.startswith("list."):
        return json.dumps(ids, ensure_ascii=False)
    return ids[0]


def shopify_env_fingerprint(env: dict[str, str]) -> str:
    value = f"{env.get('SHOPIFY_STORE_NAME', '')}|{env.get('SHOPIFY_API', '')}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_metaobject_choices_cached(
    _env: dict[str, str],
    shopify_fingerprint: str,
    definition_ids: tuple[str, ...],
) -> dict[str, Any]:
    del shopify_fingerprint
    choices_by_definition_id: dict[str, list[dict[str, str]]] = {}
    warnings = []
    for definition_id in definition_ids:
        try:
            data = shopify_graphql(
                _env,
                METAOBJECT_DEFINITION_CHOICES_QUERY,
                {"id": definition_id, "first": 100},
            )
            definition = data.get("metaobjectDefinition") or {}
            nodes = ((definition.get("metaobjects") or {}).get("nodes")) or []
            choices_by_definition_id[definition_id] = [
                {
                    "id": str(node.get("id") or ""),
                    "handle": str(node.get("handle") or ""),
                    "displayName": str(node.get("displayName") or node.get("handle") or ""),
                }
                for node in nodes
                if node.get("id")
            ]
        except Exception as error:
            warnings.append(f"Could not load metaobject choices for {definition_id}: {error}")
    return {"choices": choices_by_definition_id, "warnings": warnings}


def reference_options_by_metafield_identity(
    env: dict[str, str],
    metafields_df: pd.DataFrame,
) -> tuple[dict[str, list[dict[str, str]]], list[str]]:
    if metafields_df.empty:
        return {}, []
    identity_to_definition_id = {}
    for _, row in metafields_df.iterrows():
        definition_type = str(row.get("type") or "")
        if not is_metaobject_reference_type(definition_type):
            continue
        definition_id = metaobject_definition_id_from_row(row)
        if definition_id:
            identity_to_definition_id[f"{row['namespace']}.{row['key']}"] = definition_id
    if not identity_to_definition_id:
        return {}, []
    result = fetch_metaobject_choices_cached(
        env,
        shopify_env_fingerprint(env),
        tuple(sorted(set(identity_to_definition_id.values()))),
    )
    choices_by_definition_id = result.get("choices") or {}
    options_by_identity = {
        identity: choices_by_definition_id.get(definition_id, [])
        for identity, definition_id in identity_to_definition_id.items()
    }
    return options_by_identity, list(result.get("warnings") or [])


def safe_int(value: Any, fallback: int = 0, minimum: int | None = None) -> int:
    try:
        parsed = int(float(str(value).strip()))
    except (TypeError, ValueError):
        parsed = fallback
    if minimum is not None:
        parsed = max(parsed, minimum)
    return parsed


def request_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def request_get_json(url: str, headers: dict[str, str] | None = None, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers=headers or {},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def request_binary(url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> bytes:
    request = urllib.request.Request(
        url,
        headers=headers or {},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def post_multipart_form(
    url: str,
    fields: list[tuple[str, str]],
    file_field: str,
    filename: str,
    content_type: str,
    file_bytes: bytes,
    timeout: int = 120,
) -> bytes:
    boundary = f"----codex-shopify-upload-{hashlib.sha256(filename.encode('utf-8')).hexdigest()[:16]}"
    chunks: list[bytes] = []
    for name, value in fields:
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            (
                f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8"),
            file_bytes,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    request = urllib.request.Request(
        url,
        data=b"".join(chunks),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def shopify_graphql(env: dict[str, str], query: str, variables: dict[str, Any]) -> dict[str, Any]:
    token = env.get("SHOPIFY_API", "").strip()
    store = env.get("SHOPIFY_STORE_NAME", "").strip()
    if not token or not store:
        raise RuntimeError("SHOPIFY_API and SHOPIFY_STORE_NAME are required in .env")
    host = normalize_shopify_host(store)
    data = request_json(
        f"https://{host}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        {"query": query, "variables": variables},
        {"X-Shopify-Access-Token": token},
    )
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def first_env_value(env: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = env.get(key, "").strip()
        if value:
            return value
    return ""


def normalize_mirakl_base_url(value: str) -> str:
    base_url = value.strip().rstrip("/")
    if not base_url:
        return ""
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    return base_url.rstrip("/")


def mirakl_marketplace_definition(marketplace_id: str) -> dict[str, Any]:
    return MIRAKL_MARKETPLACES.get(marketplace_id, MIRAKL_MARKETPLACES["shop_apotheke"])


def mirakl_base_url(env: dict[str, str], marketplace_id: str = "shop_apotheke") -> str:
    definition = mirakl_marketplace_definition(marketplace_id)
    configured_url = first_env_value(env, definition["base_url_keys"])
    configured_instance = first_env_value(env, definition["instance_keys"])
    if not configured_url and marketplace_id == "shop_apotheke":
        configured_url = env.get("MIRAKL_BASE_URL", "").strip()
    return normalize_mirakl_base_url(
        configured_url
        or configured_instance
        or definition["default_instance"]
        or MIRAKL_DEFAULT_BASE_URL
    )


def mirakl_api_key(env: dict[str, str], marketplace_id: str = "shop_apotheke") -> str:
    definition = mirakl_marketplace_definition(marketplace_id)
    return first_env_value(env, definition["api_key_keys"])


def mirakl_marketplace_config(env: dict[str, str], marketplace_id: str) -> dict[str, str]:
    definition = mirakl_marketplace_definition(marketplace_id)
    return {
        "id": marketplace_id,
        "label": str(definition["label"]),
        "slug": str(definition["slug"]),
        "api_key_env": str(definition["api_key_env"]),
        "base_url": mirakl_base_url(env, marketplace_id),
        "api_key": mirakl_api_key(env, marketplace_id),
    }


def mirakl_env_fingerprint(env: dict[str, str], marketplace_id: str = "shop_apotheke") -> str:
    source = f"{marketplace_id}:{mirakl_base_url(env, marketplace_id)}:{mirakl_api_key(env, marketplace_id)}"
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]


def mirakl_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        raise RuntimeError("A Mirakl API key is required in .env")
    return {
        "Authorization": api_key,
        "Accept": "application/json",
    }


def mirakl_get_json(
    base_url: str,
    api_key: str,
    path: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = "/" + path.lstrip("/")
    query = f"?{urlencode(params or {})}" if params else ""
    return request_get_json(
        f"{base_url}{path}{query}",
        headers=mirakl_headers(api_key),
        timeout=90,
    )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mirakl_hierarchies_cached(
    base_url: str,
    api_key: str,
    env_fingerprint: str,
) -> list[dict[str, Any]]:
    del env_fingerprint
    data = mirakl_get_json(base_url, api_key, "/api/hierarchies")
    if isinstance(data, list):
        return data
    return data.get("hierarchies") or data.get("data") or []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mirakl_attributes_cached(
    base_url: str,
    api_key: str,
    env_fingerprint: str,
    hierarchy_code: str = "",
) -> list[dict[str, Any]]:
    del env_fingerprint
    params = {"hierarchy_code": hierarchy_code} if hierarchy_code else None
    data = mirakl_get_json(base_url, api_key, "/api/products/attributes", params=params)
    if isinstance(data, list):
        return data
    return data.get("attributes") or data.get("data") or []


def fetch_shopify_products_for_mirakl(
    env: dict[str, str],
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    products = []
    cursor = None
    limit = max(1, min(int(limit), 1000))
    while len(products) < limit:
        page_size = min(100, limit - len(products))
        data = shopify_graphql(
            env,
            SHOPIFY_PRODUCTS_FOR_MIRAKL_QUERY,
            {"first": page_size, "after": cursor, "query": query or None},
        )
        connection = data["products"]
        products.extend(connection.get("nodes") or [])
        page_info = connection.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
        if not cursor:
            break
    return products


def html_to_plain_text(value: Any) -> str:
    text = re.sub(r"<[^>]+>", " ", str(value or ""))
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def first_product_image_url(product: dict[str, Any]) -> str:
    for node in ((product.get("media") or {}).get("nodes") or []):
        image = node.get("image") or {}
        url = str(image.get("url") or "").strip()
        if url:
            return url
    return ""


def is_shopify_cdn_image_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return "cdn.shopify.com" in host or "shopifycdn.net" in host


def shopify_cdn_square_image_url(url: str, size: int = 1000) -> str:
    clean_url = str(url or "").strip()
    if not clean_url:
        return ""
    if not is_shopify_cdn_image_url(clean_url):
        return clean_url
    parsed = urlparse(clean_url)
    query_pairs = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query_pairs.update(
        {
            "width": str(size),
            "height": str(size),
            "crop": "center",
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query_pairs)))


def mirakl_main_image_url(source_url: str, square_images: bool = True) -> str:
    if not square_images:
        return str(source_url or "").strip()
    return shopify_cdn_square_image_url(source_url, 1000)


def image_bytes_to_white_padded_jpeg(image_bytes: bytes, size: int = 1000) -> bytes:
    from PIL import Image, ImageOps

    with Image.open(io.BytesIO(image_bytes)) as source:
        source = ImageOps.exif_transpose(source)
        source.thumbnail((size, size), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (size, size), "white")
        if source.mode in {"RGBA", "LA"} or (source.mode == "P" and "transparency" in source.info):
            rgba_source = source.convert("RGBA")
            white_base = Image.new("RGBA", rgba_source.size, "white")
            white_base.alpha_composite(rgba_source)
            source_rgb = white_base.convert("RGB")
        else:
            source_rgb = source.convert("RGB")
        x = (size - source_rgb.width) // 2
        y = (size - source_rgb.height) // 2
        canvas.paste(source_rgb, (x, y))
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=95, optimize=True)
    return output.getvalue()


def shopify_file_image_url(env: dict[str, str], file_id: str, attempts: int = 8) -> dict[str, Any]:
    last_node: dict[str, Any] = {}
    for attempt in range(attempts):
        data = shopify_graphql(env, SHOPIFY_FILE_IMAGE_URL_QUERY, {"id": file_id})
        node = data.get("node") or {}
        last_node = node
        image = node.get("image") or {}
        if image.get("url"):
            return {
                "url": image.get("url"),
                "width": image.get("width"),
                "height": image.get("height"),
                "fileStatus": node.get("fileStatus"),
            }
        if attempt < attempts - 1:
            time.sleep(2)
    image = last_node.get("image") or {}
    return {
        "url": image.get("url") or "",
        "width": image.get("width"),
        "height": image.get("height"),
        "fileStatus": last_node.get("fileStatus"),
    }


def upload_white_padded_image_to_shopify_files(
    env: dict[str, str],
    source_url: str,
    product_title: str,
    handle: str,
) -> dict[str, Any]:
    clean_source_url = str(source_url or "").strip()
    if not clean_source_url:
        raise RuntimeError("No source image URL to pad and upload.")

    image_bytes = request_binary(clean_source_url, timeout=90)
    padded_bytes = image_bytes_to_white_padded_jpeg(image_bytes, size=1000)
    filename_base = slugify(handle or product_title or "mirakl-product-image")[:80] or "mirakl-product-image"
    source_hash = hashlib.sha256(clean_source_url.encode("utf-8")).hexdigest()[:10]
    filename = f"{filename_base}-mirakl-1000x1000-{source_hash}.jpg"

    staged = shopify_graphql(
        env,
        CREATE_STAGED_IMAGE_UPLOAD_MUTATION,
        {
            "input": [
                {
                    "filename": filename,
                    "mimeType": "image/jpeg",
                    "resource": "FILE",
                    "httpMethod": "POST",
                }
            ]
        },
    )["stagedUploadsCreate"]
    if staged.get("userErrors"):
        raise RuntimeError(json.dumps(staged["userErrors"], ensure_ascii=False))
    targets = staged.get("stagedTargets") or []
    if not targets:
        raise RuntimeError("Shopify did not return a staged upload target.")
    target = targets[0]
    fields = [
        (str(parameter.get("name") or ""), str(parameter.get("value") or ""))
        for parameter in target.get("parameters") or []
        if parameter.get("name")
    ]
    post_multipart_form(
        url=target["url"],
        fields=fields,
        file_field="file",
        filename=filename,
        content_type="image/jpeg",
        file_bytes=padded_bytes,
        timeout=180,
    )

    created = shopify_graphql(
        env,
        CREATE_SHOPIFY_FILE_MUTATION,
        {
            "files": [
                {
                    "alt": f"{product_title} Mirakl 1000x1000 white background",
                    "contentType": "IMAGE",
                    "originalSource": target["resourceUrl"],
                }
            ]
        },
    )["fileCreate"]
    if created.get("userErrors"):
        raise RuntimeError(json.dumps(created["userErrors"], ensure_ascii=False))
    files = created.get("files") or []
    if not files:
        raise RuntimeError("Shopify did not create a file record.")
    file_node = files[0]
    image = file_node.get("image") or {}
    url = image.get("url") or ""
    if not url and file_node.get("id"):
        image = shopify_file_image_url(env, file_node["id"])
        url = str(image.get("url") or "")
    return {
        "file_id": file_node.get("id") or "",
        "url": url,
        "width": image.get("width"),
        "height": image.get("height"),
        "fileStatus": file_node.get("fileStatus") or image.get("fileStatus"),
        "source_url": clean_source_url,
        "filename": filename,
        "bytes": len(padded_bytes),
    }


def shopify_product_metafield_map(product: dict[str, Any]) -> dict[str, str]:
    values = {}
    for metafield in ((product.get("metafields") or {}).get("nodes") or []):
        namespace = str(metafield.get("namespace") or "").strip()
        key = str(metafield.get("key") or "").strip()
        if namespace and key:
            values[f"{namespace}.{key}"] = str(metafield.get("value") or "").strip()
    return values


def mirakl_hierarchy_rows(hierarchies: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    by_code = {str(item.get("code") or ""): item for item in hierarchies}
    child_parent_codes = {str(item.get("parentCode") or item.get("parent_code") or "") for item in hierarchies}

    def hierarchy_label(item: dict[str, Any]) -> str:
        return str(
            item.get("label")
            or item.get("description")
            or item.get("name")
            or item.get("code")
            or ""
        ).strip()

    def hierarchy_path(item: dict[str, Any]) -> str:
        seen = set()
        labels = []
        current = item
        while current:
            code = str(current.get("code") or "")
            if code in seen:
                break
            seen.add(code)
            label = hierarchy_label(current)
            if label:
                labels.append(label)
            parent_code = str(current.get("parentCode") or current.get("parent_code") or "")
            current = by_code.get(parent_code)
        return ">".join(reversed(labels))

    for item in hierarchies:
        code = str(item.get("code") or "").strip()
        if not code:
            continue
        path = hierarchy_path(item)
        is_leaf = code not in child_parent_codes
        rows.append(
            {
                "code": code,
                "path": path or code,
                "label": f"{path or code} [{code}]",
                "is_leaf": "yes" if is_leaf else "no",
            }
        )
    return sorted(rows, key=lambda row: row["label"].lower())


def mirakl_attribute_code(attribute: dict[str, Any]) -> str:
    return str(attribute.get("code") or attribute.get("id") or "").strip()


def mirakl_attribute_required(attribute: dict[str, Any]) -> bool:
    required_value = attribute.get("required")
    if isinstance(required_value, bool):
        return required_value
    if str(required_value).strip().lower() in {"true", "yes", "1", "required"}:
        return True
    requirement_level = str(
        attribute.get("requirement_level")
        or attribute.get("requirementLevel")
        or attribute.get("requirement")
        or ""
    ).strip().upper()
    return requirement_level == "REQUIRED"


def mirakl_unit_from_shopify_unit(unit: str) -> str:
    return {
        "ML": "ml",
        "L": "l",
        "MG": "mg",
        "G": "g",
        "KG": "kg",
        "ITEM": "St",
    }.get(unit, "")


def mirakl_variant_rows(product: dict[str, Any]) -> list[dict[str, Any]]:
    variants = ((product.get("variants") or {}).get("nodes") or [])
    if variants:
        return variants
    return [
        {
            "id": "",
            "title": "Default Title",
            "sku": "",
            "barcode": "",
            "price": "",
            "compareAtPrice": "",
            "inventoryQuantity": "",
        }
    ]


def mirakl_best_product_identifier(product: dict[str, Any], variant: dict[str, Any]) -> str:
    for value in [variant.get("sku"), variant.get("barcode"), product.get("handle"), product.get("id")]:
        text = str(value or "").strip()
        if text:
            return text[:40]
    return slugify(str(product.get("title") or ""))[:40]


def mirakl_row_field_fallbacks(
    product: dict[str, Any],
    variant: dict[str, Any],
    measurement: tuple[float, str] | None,
    description: str,
    main_image: str,
) -> dict[str, str]:
    barcode = clean_barcode(variant.get("barcode") or variant.get("sku"))
    package_size = f"{measurement[0]:g}" if measurement else ""
    package_unit = mirakl_unit_from_shopify_unit(measurement[1]) if measurement else ""
    product_title = str(product.get("title") or "").strip()
    brand = str(product.get("vendor") or "").strip()
    product_type = str(product.get("productType") or "").strip()
    price = safe_decimal(variant.get("price"), fallback="")
    compare_at_price = safe_decimal(variant.get("compareAtPrice"), fallback="")
    return {
        "product_identification_number": mirakl_best_product_identifier(product, variant),
        "shop_sku": mirakl_best_product_identifier(product, variant),
        "sku": mirakl_best_product_identifier(product, variant),
        "name": product_title[:100],
        "title": product_title[:100],
        "ean": barcode if re.fullmatch(r"\d{8}|\d{12,14}", barcode) else "",
        "gtin": barcode if re.fullmatch(r"\d{8}|\d{12,14}", barcode) else "",
        "barcode": barcode,
        "brand": brand,
        "manufacturer": brand,
        "package_size": package_size,
        "package_size_unit": package_unit,
        "main_image": main_image,
        "image": main_image,
        "image_1": main_image,
        "description": description,
        "description_de": description,
        "long_description": description,
        "short_description": description[:500],
        "product_type": product_type,
        "price": price,
        "discounted_price": price,
        "retail_price": compare_at_price,
        "compare_at_price": compare_at_price,
    }


def build_mirakl_product_rows(
    products: list[dict[str, Any]],
    attributes: list[dict[str, Any]],
    category_path: str,
    square_main_images: bool = True,
    main_image_overrides: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    attribute_codes = [mirakl_attribute_code(attribute) for attribute in attributes]
    attribute_codes = [code for code in attribute_codes if code]
    required_codes = [
        mirakl_attribute_code(attribute)
        for attribute in attributes
        if mirakl_attribute_code(attribute) and mirakl_attribute_required(attribute)
    ]
    required_codes = list(dict.fromkeys(required_codes))
    base_columns = [
        "marketplace_category",
        "product_identification_number",
        "name",
        "ean",
        "brand",
        "package_size",
        "package_size_unit",
        "main_image",
        "description",
    ]
    columns = list(dict.fromkeys([*base_columns, *attribute_codes]))
    if "marketplace_category" not in columns:
        columns.insert(0, "marketplace_category")

    rows = []
    missing_rows = []
    image_report_rows = []
    main_image_overrides = main_image_overrides or {}
    for product in products:
        description = html_to_plain_text(product.get("descriptionHtml"))
        source_main_image = first_product_image_url(product)
        main_image = main_image_overrides.get(source_main_image) or mirakl_main_image_url(source_main_image, square_main_images)
        if not source_main_image:
            image_report_rows.append(
                {
                    "shopify_product": str(product.get("title") or ""),
                    "shopify_handle": str(product.get("handle") or ""),
                    "status": "missing image",
                    "source_image": "",
                    "mirakl_main_image": "",
                    "notes": "No Shopify product image was found for Mirakl main_image.",
                }
            )
        elif square_main_images and not main_image_overrides.get(source_main_image) and not is_shopify_cdn_image_url(source_main_image):
            image_report_rows.append(
                {
                    "shopify_product": str(product.get("title") or ""),
                    "shopify_handle": str(product.get("handle") or ""),
                    "status": "needs manual 1000x1000 public URL",
                    "source_image": source_main_image,
                    "mirakl_main_image": main_image,
                    "notes": "The first image is not a Shopify CDN URL, so the app cannot apply Shopify 1000x1000 crop parameters.",
                }
            )
        metafields = shopify_product_metafield_map(product)
        measurement_source = " ".join(
            str(value or "")
            for value in [product.get("title"), metafields.get("custom.measurement"), metafields.get("custom.package_size")]
        )
        measurement = parse_measurement_label(measurement_source)
        for variant in mirakl_variant_rows(product):
            fallbacks = mirakl_row_field_fallbacks(product, variant, measurement, description, main_image)
            row = {column: "" for column in columns}
            row["marketplace_category"] = category_path
            for column in columns:
                identity_value = metafields.get(column) or metafields.get(f"custom.{column}")
                if identity_value:
                    row[column] = identity_value
                elif column in fallbacks:
                    row[column] = fallbacks[column]

            missing = [code for code in required_codes if not str(row.get(code) or "").strip()]
            if missing:
                missing_rows.append(
                    {
                        "shopify_product": str(product.get("title") or ""),
                        "shopify_handle": str(product.get("handle") or ""),
                        "variant": str(variant.get("title") or ""),
                        "missing_required_mirakl_columns": ", ".join(missing),
                    }
                )
            rows.append(row)

    return pd.DataFrame(rows, columns=columns), pd.DataFrame(missing_rows), pd.DataFrame(image_report_rows)


def dataframe_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = io.StringIO()
    dataframe.to_csv(buffer, index=False, quoting=csv.QUOTE_MINIMAL)
    return buffer.getvalue().encode("utf-8-sig")


def find_existing_variant_by_barcode(env: dict[str, str], barcode: str) -> list[dict[str, Any]]:
    clean_barcode = barcode.strip().replace('"', '\\"')
    if not clean_barcode:
        return []
    data = shopify_graphql(
        env,
        FIND_VARIANT_BY_BARCODE_QUERY,
        {"query": f'barcode:"{clean_barcode}" OR sku:"{clean_barcode}"'},
    )
    return data["productVariants"]["nodes"]


def find_existing_product_by_handle(env: dict[str, str], handle: str) -> dict[str, Any] | None:
    clean_handle = slugify(handle)
    if not clean_handle:
        return None
    data = shopify_graphql(
        env,
        FIND_PRODUCT_BY_HANDLE_QUERY,
        {"handle": clean_handle},
    )
    return data.get("productByIdentifier")


def resolve_existing_product(
    env: dict[str, str],
    barcode: str,
    handle: str,
) -> tuple[dict[str, Any] | None, str]:
    existing_variants = find_existing_variant_by_barcode(env, barcode)
    if existing_variants:
        variant = existing_variants[0]
        product = dict(variant.get("product") or {})
        product["variants"] = {
            "nodes": [
                {
                    "id": variant["id"],
                    "inventoryItem": variant.get("inventoryItem"),
                }
            ]
        }
        return product, "barcode/SKU"

    existing_product = find_existing_product_by_handle(env, handle)
    if existing_product:
        return existing_product, "handle"

    return None, ""


@st.cache_data(show_spinner=False)
def read_csv_cached(path: str) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        return pd.DataFrame()
    return pd.read_csv(file_path)


def refresh_shopify_context() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "discover_shopify_registration_context.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or result.stdout)
    read_csv_cached.clear()


def openrouter_key_fingerprint(api_key: str) -> str:
    if not api_key:
        return "missing"
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def openrouter_base_model(model: str) -> str:
    model = model.strip()
    if model.endswith(":online"):
        return model[: -len(":online")]
    return model


def openrouter_provider(model: str) -> str:
    model = openrouter_base_model(model)
    if "/" not in model:
        return "custom"
    return model.split("/", 1)[0]


def openrouter_model(model: str, use_web: bool) -> str:
    model = openrouter_base_model(model)
    if use_web and ":online" not in model:
        return f"{model}:online"
    return model


def openrouter_price_value(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def openrouter_pricing_value(pricing: Any, key: str) -> float | None:
    if isinstance(pricing, list):
        values = [openrouter_price_value(item.get(key)) for item in pricing if isinstance(item, dict)]
        values = [value for value in values if value is not None]
        return min(values) if values else None
    if isinstance(pricing, dict):
        return openrouter_price_value(pricing.get(key))
    return None


def openrouter_price_label(price: float | None) -> str:
    if price is None:
        return "n/a"
    per_million = price * 1_000_000
    if per_million == 0:
        return "free"
    if per_million < 0.01:
        return f"${per_million:.4f}/M"
    if per_million < 1:
        return f"${per_million:.3f}/M"
    return f"${per_million:.2f}/M"


def openrouter_billing_tier(prompt_price: float | None, completion_price: float | None) -> str:
    prices = [price for price in [prompt_price, completion_price] if price is not None]
    if not prices:
        return "unknown"
    if all(price <= 0 for price in prices):
        return "free"
    return "paid"


def openrouter_performance_score(model_id: str, name: str, context_length: Any) -> tuple[int, str]:
    text = f"{model_id} {name}".lower()
    score = 40
    provider = openrouter_provider(model_id)
    if provider in {"openai", "anthropic", "google", "x-ai"}:
        score += 12
    if any(keyword in text for keyword in ["gpt-5", "opus", "grok-4", "gemini-2.5-pro", "deepseek-r1"]):
        score += 35
    elif any(keyword in text for keyword in ["sonnet", "gpt-4.1", "gpt-4o", "o3", "o4", "pro", "kimi-k2"]):
        score += 25
    elif any(keyword in text for keyword in ["qwen3", "deepseek", "llama-4", "mistral-large", "command-a"]):
        score += 15
    if any(keyword in text for keyword in ["mini", "flash", "haiku", "lite", "small", "nano", "free"]):
        score -= 12
    if any(keyword in text for keyword in ["reasoning", "thinking", "r1", "o3", "o4"]):
        score += 8
    try:
        context = int(context_length or 0)
    except (TypeError, ValueError):
        context = 0
    if context >= 1_000_000:
        score += 8
    elif context >= 128_000:
        score += 4
    if score >= 75:
        return score, "high"
    if score >= 55:
        return score, "balanced"
    return score, "budget"


def parse_openrouter_models(data: dict[str, Any]) -> list[dict[str, Any]]:
    models = []
    seen = set()
    for item in data.get("data") or []:
        model_id = str(item.get("id") or "").strip()
        if not model_id or model_id in seen:
            continue
        architecture = item.get("architecture") or {}
        output_modalities = architecture.get("output_modalities") or []
        if output_modalities and "text" not in output_modalities:
            continue
        top_provider = item.get("top_provider") or {}
        context_length = item.get("context_length") or top_provider.get("context_length")
        pricing = item.get("pricing") or {}
        prompt_price = openrouter_pricing_value(pricing, "prompt")
        completion_price = openrouter_pricing_value(pricing, "completion")
        combined_price = None
        if prompt_price is not None and completion_price is not None:
            combined_price = prompt_price + completion_price
        elif prompt_price is not None:
            combined_price = prompt_price
        elif completion_price is not None:
            combined_price = completion_price
        name = str(item.get("name") or model_id).strip()
        performance_score, performance_tier = openrouter_performance_score(model_id, name, context_length)
        models.append(
            {
                "id": model_id,
                "name": name,
                "context_length": context_length,
                "prompt_price": prompt_price,
                "completion_price": completion_price,
                "combined_price": combined_price,
                "billing_tier": openrouter_billing_tier(prompt_price, completion_price),
                "performance_score": performance_score,
                "performance_tier": performance_tier,
            }
        )
        seen.add(model_id)
    return models


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_openrouter_model_catalog(_api_key: str, key_fingerprint: str) -> dict[str, Any]:
    del key_fingerprint
    headers = {"Authorization": f"Bearer {_api_key}"} if _api_key else {}
    endpoints = []
    if _api_key:
        endpoints.append(("your key", OPENROUTER_USER_MODELS_URL, headers))
    endpoints.append(("all OpenRouter", OPENROUTER_MODELS_URL, headers))

    errors = []
    for source, url, endpoint_headers in endpoints:
        try:
            data = request_get_json(url, endpoint_headers)
        except Exception as error:
            errors.append(f"{source}: {error}")
            continue
        models = parse_openrouter_models(data)
        if models:
            return {"source": source, "models": models}
        errors.append(f"{source}: no text models returned")

    raise RuntimeError("; ".join(errors) or "OpenRouter returned no models")


def format_openrouter_model_option(model: dict[str, Any]) -> str:
    model_id = str(model.get("id") or "").strip()
    name = str(model.get("name") or model_id).strip()
    provider = openrouter_provider(model_id)
    short_model_id = model_id.split("/", 1)[1] if "/" in model_id else model_id
    label = f"{name} ({short_model_id})" if name and name != model_id else short_model_id
    try:
        context_length = int(model.get("context_length") or 0)
    except (TypeError, ValueError):
        context_length = 0
    if context_length:
        label = f"{label} - {context_length:,} ctx"
    prompt_label = openrouter_price_label(model.get("prompt_price"))
    completion_label = openrouter_price_label(model.get("completion_price"))
    billing_tier = str(model.get("billing_tier") or "unknown").strip()
    label = f"{label} - {billing_tier}"
    if prompt_label != "n/a" or completion_label != "n/a":
        label = f"{label} - in {prompt_label}, out {completion_label}"
    performance_tier = str(model.get("performance_tier") or "").strip()
    if performance_tier:
        label = f"{label} - {performance_tier}"
    if provider == "custom":
        label = f"{label} ({model_id})"
    return label


def sort_openrouter_models(
    model_ids: list[str],
    model_lookup: dict[str, dict[str, Any]],
    sort_mode: str,
) -> list[str]:
    def price_key(model_id: str, key: str) -> tuple[float, str]:
        value = model_lookup.get(model_id, {}).get(key)
        if value is None:
            return (float("inf"), model_id.lower())
        return (float(value), model_id.lower())

    def context_key(model_id: str) -> tuple[int, str]:
        try:
            context = int(model_lookup.get(model_id, {}).get("context_length") or 0)
        except (TypeError, ValueError):
            context = 0
        return (-context, model_id.lower())

    def performance_key(model_id: str) -> tuple[int, float, str]:
        score = int(model_lookup.get(model_id, {}).get("performance_score") or 0)
        combined_price = model_lookup.get(model_id, {}).get("combined_price")
        if combined_price is None:
            combined_price = float("inf")
        return (-score, float(combined_price), model_id.lower())

    if sort_mode == "Cheapest input":
        return sorted(model_ids, key=lambda model_id: price_key(model_id, "prompt_price"))
    if sort_mode == "Cheapest output":
        return sorted(model_ids, key=lambda model_id: price_key(model_id, "completion_price"))
    if sort_mode == "Cheapest input + output":
        return sorted(model_ids, key=lambda model_id: price_key(model_id, "combined_price"))
    if sort_mode == "Largest context":
        return sorted(model_ids, key=context_key)
    if sort_mode == "Performance tier (heuristic)":
        return sorted(model_ids, key=performance_key)
    return sorted(model_ids, key=lambda model_id: format_openrouter_model_option(model_lookup[model_id]).lower())


def filter_openrouter_models_by_cost(
    model_ids: list[str],
    model_lookup: dict[str, dict[str, Any]],
    cost_filter: str,
) -> list[str]:
    if cost_filter == "Paid only":
        return [model_id for model_id in model_ids if model_lookup.get(model_id, {}).get("billing_tier") == "paid"]
    if cost_filter == "Free only":
        return [model_id for model_id in model_ids if model_lookup.get(model_id, {}).get("billing_tier") == "free"]
    return model_ids


def openrouter_provider_options(model_ids: list[str]) -> list[str]:
    return sorted({openrouter_provider(model_id) for model_id in model_ids}, key=str.lower)


def openrouter_models_for_provider(model_ids: list[str], provider: str) -> list[str]:
    return [model_id for model_id in model_ids if openrouter_provider(model_id) == provider]


def openrouter_model_selector(
    label_prefix: str,
    default_model: str,
    model_options: list[str],
    model_lookup: dict[str, dict[str, Any]],
    sort_mode: str,
    provider_key: str,
    model_key: str,
    custom_key: str,
) -> str:
    default_model = openrouter_base_model(default_model)
    provider_options = openrouter_provider_options(model_options)
    default_provider = openrouter_provider(default_model)
    if default_provider not in provider_options and default_model in model_options:
        provider_options.insert(0, default_provider)

    provider_index = provider_options.index(default_provider) if default_provider in provider_options else 0
    provider = st.selectbox(
        f"{label_prefix} provider",
        options=provider_options,
        index=provider_index,
        key=provider_key,
    )

    provider_model_options = openrouter_models_for_provider(model_options, provider)
    if default_model not in provider_model_options and default_model in model_options and openrouter_provider(default_model) == provider:
        provider_model_options.insert(0, default_model)
    if not provider_model_options:
        provider_model_options = [default_model]
    provider_model_options = sort_openrouter_models(provider_model_options, model_lookup, sort_mode)

    model_index = provider_model_options.index(default_model) if default_model in provider_model_options else 0
    model = st.selectbox(
        f"{label_prefix} model",
        options=provider_model_options,
        index=model_index,
        format_func=lambda model_id: format_openrouter_model_option(model_lookup[model_id]),
        key=model_key,
    )
    if st.checkbox(f"Use custom {label_prefix.lower()} model ID", value=False, key=f"{custom_key}_enabled"):
        custom_model = st.text_input(f"Custom {label_prefix.lower()} model", value=model, key=custom_key)
        if custom_model.strip():
            model = openrouter_base_model(custom_model)
    return model


def content_language_hint(language: str) -> str:
    return CONTENT_LANGUAGE_HINTS.get(language, CONTENT_LANGUAGE_HINTS["German"])


def product_catalog_for_ai(products_df: pd.DataFrame) -> list[dict[str, str]]:
    catalog = []
    for _, row in products_df.iterrows():
        handle = str(row.get("handle") or "").strip()
        title = str(row.get("title") or "").strip()
        if not handle or not title:
            continue
        catalog.append(
            {
                "handle": handle,
                "title": title,
                "vendor": str(row.get("vendor") or "").strip(),
                "product_type": str(row.get("productType") or "").strip(),
                "status": str(row.get("status") or "").strip(),
            }
        )
    return catalog


def google_custom_search_credentials(env: dict[str, str]) -> tuple[str, str]:
    api_key = (
        env.get("GOOGLE_CUSTOM_SEARCH_API_KEY")
        or env.get("GOOGLE_API_KEY")
        or ""
    ).strip()
    search_engine_id = (
        env.get("GOOGLE_CUSTOM_SEARCH_CX")
        or env.get("GOOGLE_CUSTOM_SEARCH_ENGINE_ID")
        or env.get("GOOGLE_CSE_ID")
        or ""
    ).strip()
    return api_key, search_engine_id


def brave_search_credentials(env: dict[str, str]) -> str:
    return (
        env.get("BRAVE_SEARCH_API_KEY")
        or env.get("BRAVE_API_KEY")
        or ""
    ).strip()


def serpapi_credentials(env: dict[str, str]) -> str:
    return (
        env.get("SERPAPI_API_KEY")
        or env.get("SERP_API_KEY")
        or env.get("SERPAPI_KEY")
        or ""
    ).strip()


def searxng_base_url(env: dict[str, str]) -> str:
    return (
        env.get("SEARXNG_BASE_URL")
        or env.get("SEARXNG_URL")
        or ""
    ).strip().rstrip("/")


def product_research_queries(product_name: str, vendor: str) -> list[dict[str, str]]:
    product = re.sub(r"\s+", " ", product_name).strip()
    brand = re.sub(r"\s+", " ", vendor).strip()
    quoted_product = f'"{product}"' if product else ""
    quoted_brand = f'"{brand}"' if brand else ""
    base = " ".join(part for part in [quoted_brand, quoted_product] if part)
    query_specs = [
        ("official", f"{base} official product"),
        ("ingredients", f"{base} INCI ingredients ingredient list"),
        ("barcode", f"{base} barcode EAN UPC GTIN"),
        ("shopping", f"{base} price buy shopping"),
        ("amazon", f"site:amazon.de OR site:amazon.com {base}"),
        ("retailers", f"{base} korean skincare retailer"),
    ]
    seen = set()
    queries = []
    for query_type, query in query_specs:
        clean_query = re.sub(r"\s+", " ", query).strip()
        if clean_query and clean_query not in seen:
            queries.append({"type": query_type, "query": clean_query})
            seen.add(clean_query)
    return queries


@st.cache_data(ttl=86400, show_spinner=False)
def google_custom_search_cached(
    query: str,
    api_key_fingerprint: str,
    search_engine_id: str,
    api_key: str,
    num_results: int,
) -> dict[str, Any]:
    del api_key_fingerprint
    params = {
        "key": api_key,
        "cx": search_engine_id,
        "q": query,
        "num": max(1, min(int(num_results), 10)),
    }
    return request_get_json(f"{GOOGLE_CUSTOM_SEARCH_URL}?{urlencode(params)}", timeout=30)


def google_search_result_records(
    data: dict[str, Any],
    query_type: str,
    query: str,
) -> list[dict[str, str]]:
    records = []
    for item in data.get("items") or []:
        link = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not link or not title:
            continue
        parsed = urlparse(link)
        records.append(
            {
                "source": "google_custom_search",
                "query_type": query_type,
                "query": query,
                "title": title,
                "url": link,
                "display_link": str(item.get("displayLink") or parsed.netloc).strip(),
                "snippet": snippet,
            }
        )
    return records


@st.cache_data(ttl=86400, show_spinner=False)
def brave_search_cached(
    query: str,
    api_key_fingerprint: str,
    api_key: str,
    num_results: int,
) -> dict[str, Any]:
    del api_key_fingerprint
    params = {
        "q": query,
        "count": max(1, min(int(num_results), 20)),
        "country": "de",
        "search_lang": "en",
        "safesearch": "moderate",
        "spellcheck": "1",
    }
    return request_get_json(
        f"{BRAVE_WEB_SEARCH_URL}?{urlencode(params)}",
        headers={
            "Accept": "application/json",
            "X-Subscription-Token": api_key,
        },
        timeout=30,
    )


def brave_search_result_records(
    data: dict[str, Any],
    query_type: str,
    query: str,
) -> list[dict[str, str]]:
    records = []
    web_results = ((data.get("web") or {}).get("results") or [])
    for item in web_results:
        link = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("description") or item.get("snippet") or "").strip()
        if not link or not title:
            continue
        parsed = urlparse(link)
        records.append(
            {
                "source": "brave_search",
                "query_type": query_type,
                "query": query,
                "title": title,
                "url": link,
                "display_link": parsed.netloc,
                "snippet": snippet,
            }
        )
    return records


@st.cache_data(ttl=86400, show_spinner=False)
def serpapi_search_cached(
    query: str,
    engine: str,
    api_key_fingerprint: str,
    api_key: str,
    num_results: int,
) -> dict[str, Any]:
    del api_key_fingerprint
    params = {
        "engine": engine,
        "q": query,
        "api_key": api_key,
        "hl": "en",
        "gl": "de",
        "google_domain": "google.de",
        "num": max(1, min(int(num_results), 10)),
    }
    if engine == "google_shopping":
        params["device"] = "desktop"
    return request_get_json(f"{SERPAPI_SEARCH_URL}?{urlencode(params)}", timeout=60)


def serpapi_google_result_records(
    data: dict[str, Any],
    query_type: str,
    query: str,
) -> list[dict[str, str]]:
    records = []
    for item in data.get("organic_results") or []:
        link = str(item.get("link") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        if not link or not title:
            continue
        parsed = urlparse(link)
        records.append(
            {
                "source": "serpapi_google",
                "query_type": query_type,
                "query": query,
                "title": title,
                "url": link,
                "display_link": str(item.get("displayed_link") or parsed.netloc).strip(),
                "snippet": snippet,
            }
        )
    return records


def serpapi_shopping_result_records(
    data: dict[str, Any],
    query_type: str,
    query: str,
) -> list[dict[str, str]]:
    records = []
    shopping_results = (data.get("shopping_results") or []) + (data.get("inline_shopping_results") or [])
    for item in shopping_results:
        link = str(item.get("link") or item.get("product_link") or "").strip()
        title = str(item.get("title") or "").strip()
        if not link or not title:
            continue
        parsed = urlparse(link)
        facts = []
        for key in ["price", "old_price", "source", "rating", "reviews", "delivery", "snippet"]:
            value = item.get(key)
            if value not in [None, ""]:
                facts.append(f"{key}: {value}")
        if item.get("thumbnail"):
            facts.append(f"thumbnail: {item['thumbnail']}")
        records.append(
            {
                "source": "serpapi_google_shopping",
                "query_type": query_type,
                "query": query,
                "title": title,
                "url": link,
                "display_link": str(item.get("source") or parsed.netloc).strip(),
                "snippet": "; ".join(str(fact) for fact in facts),
            }
        )
    return records


@st.cache_data(ttl=86400, show_spinner=False)
def searxng_search_cached(
    base_url: str,
    query: str,
    num_results: int,
) -> dict[str, Any]:
    params = {
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": "1",
        "pageno": "1",
    }
    data = request_get_json(f"{base_url}/search?{urlencode(params)}", timeout=60)
    max_results = max(1, min(int(num_results), 20))
    if isinstance(data.get("results"), list):
        data["results"] = data["results"][:max_results]
    return data


def searxng_result_records(
    data: dict[str, Any],
    query_type: str,
    query: str,
) -> list[dict[str, str]]:
    records = []
    for item in data.get("results") or []:
        link = str(item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("content") or item.get("snippet") or "").strip()
        if not link or not title:
            continue
        parsed = urlparse(link)
        engine = item.get("engine") or item.get("engines") or ""
        if isinstance(engine, list):
            engine = ", ".join(str(value) for value in engine)
        records.append(
            {
                "source": "searxng",
                "query_type": query_type,
                "query": query,
                "title": title,
                "url": link,
                "display_link": f"{parsed.netloc} ({engine})" if engine else parsed.netloc,
                "snippet": snippet,
            }
        )
    return records


def collect_product_research(
    env: dict[str, str],
    product_name: str,
    vendor: str,
    results_per_query: int = 4,
) -> dict[str, Any]:
    searxng_url = searxng_base_url(env)
    serpapi_api_key = serpapi_credentials(env)

    records = []
    warnings = []
    seen_urls = set()

    def add_records(new_records: list[dict[str, str]]) -> None:
        for record in new_records:
            if record["url"] in seen_urls:
                continue
            records.append(record)
            seen_urls.add(record["url"])

    queries = product_research_queries(product_name, vendor)
    if searxng_url:
        for query_spec in queries:
            try:
                data = searxng_search_cached(
                    base_url=searxng_url,
                    query=query_spec["query"],
                    num_results=results_per_query,
                )
                add_records(searxng_result_records(data, query_spec["type"], query_spec["query"]))
            except Exception as error:
                warnings.append(f"SearXNG research failed for {query_spec['type']}: {error}")
        if records or not serpapi_api_key:
            return {"records": records[:30], "warnings": warnings}
        warnings.append("SearXNG returned no usable records; using SerpAPI fallback.")

    if not serpapi_api_key:
        return {
            "records": [],
            "warnings": [
                "Product research skipped because SEARXNG_BASE_URL is not configured and SERPAPI_API_KEY/SERPAPI_KEY is not configured."
            ],
        }

    queries = [query for query in queries if query["type"] != "retailers"]
    for query_spec in queries:
        engine = "google_shopping" if query_spec["type"] == "shopping" else "google"
        try:
            data = serpapi_search_cached(
                query=query_spec["query"],
                engine=engine,
                api_key_fingerprint=openrouter_key_fingerprint(serpapi_api_key),
                api_key=serpapi_api_key,
                num_results=results_per_query,
            )
            if data.get("error"):
                raise RuntimeError(str(data["error"]))
            if engine == "google_shopping":
                add_records(serpapi_shopping_result_records(data, query_spec["type"], query_spec["query"]))
            else:
                add_records(serpapi_google_result_records(data, query_spec["type"], query_spec["query"]))
        except Exception as error:
            warnings.append(f"SerpAPI research failed for {query_spec['type']}: {error}")
    return {"records": records[:30], "warnings": warnings}


def research_records_for_ai(research: dict[str, Any]) -> list[dict[str, str]]:
    compact_records = []
    for record in research.get("records") or []:
        compact_records.append(
            {
                "source": record.get("source", ""),
                "query_type": record.get("query_type", ""),
                "title": record.get("title", ""),
                "url": record.get("url", ""),
                "display_link": record.get("display_link", ""),
                "snippet": record.get("snippet", ""),
            }
        )
    return compact_records


def research_urls(research: dict[str, Any], limit: int = 12) -> list[str]:
    urls = []
    for record in research.get("records") or []:
        url = str(record.get("url") or "").strip()
        if url and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def openrouter_message_content(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("OpenRouter returned no choices")
    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                text = part.get("text") or part.get("content")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(part, str):
                parts.append(part)
        return "\n".join(parts).strip()
    finish_reason = choice.get("finish_reason") or data.get("finish_reason") or "unknown"
    raise RuntimeError(f"OpenRouter returned empty message content (finish_reason: {finish_reason})")


def json_object_text(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def request_openrouter_json(
    api_key: str,
    payload: dict[str, Any],
    schema_name: str,
    fallback_model: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key}"}
    model_candidates = [str(payload.get("model") or "").strip()]
    fallback_model = str(fallback_model or "").strip()
    if fallback_model and fallback_model not in model_candidates:
        model_candidates.append(fallback_model)

    errors = []
    attempt_number = 0
    for candidate_model in model_candidates:
        base_payload = dict(payload)
        base_payload["model"] = candidate_model
        fallback_payload = dict(base_payload)
        fallback_payload.pop("response_format", None)
        fallback_payload["messages"] = [
            *base_payload["messages"],
            {
                "role": "user",
                "content": (
                    f"Return only one valid JSON object for {schema_name}. "
                    "Do not use markdown, code fences, or commentary."
                ),
            },
        ]
        for attempt_payload in [base_payload, fallback_payload]:
            attempt_number += 1
            try:
                data = request_json(OPENROUTER_URL, attempt_payload, headers)
                if data.get("error"):
                    raise RuntimeError(json.dumps(data["error"], indent=2))
                content = openrouter_message_content(data)
                if not content:
                    raise RuntimeError("OpenRouter returned blank message content")
                return json.loads(json_object_text(content))
            except Exception as error:
                errors.append(f"attempt {attempt_number} ({candidate_model}): {error}")
    raise RuntimeError("; ".join(errors))


def generate_ai_draft(
    env: dict[str, str],
    model: str,
    fallback_model: str,
    use_web: bool,
    product_name: str,
    vendor: str,
    price_mode: str,
    manual_price: str,
    manual_compare_at_price: str,
    measurement_label: str,
    content_language: str,
    existing_tags: list[str],
    existing_products: list[dict[str, str]],
    allowed_metafields: list[dict[str, str]],
    product_research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = env.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in .env")

    language_hint = content_language_hint(content_language)
    system_prompt = (
        "You create Shopify draft product data for Korean beauty / commerce products. "
        "Use provided product_research_evidence first. Treat it as search evidence, not guaranteed truth. "
        "Prefer official brand, retailer, barcode, ingredient, and shopping pages when evidence conflicts. "
        "Use web evidence when available. You must search for the barcode/EAN and return it when found. "
        "If a barcode cannot be found from a reliable source, return it as blank; upload can still continue. "
        "Never invent a barcode, certification, ingredient list, weight, or claim without a source. "
        "Select only relevant, generic Shopify tags from the provided clean tag list. "
        "Do not pick unrelated soap, seasonal, wholesale, internal, or product-line tags. Use at most 6 tags. "
        "Do not optimize product title or SEO description; a separate SEO model handles final product title and SEO. "
        "For schema compatibility, return title as the raw/official source product name only, seo_title as blank, "
        "and seo_description as blank. "
        "The selected content language affects description_html and editable text metafields only. "
        "All returned custom text metafield values except custom.inci must be written in the selected content language. "
        "Do not translate or alter raw product title placeholder or INCI because of the content language. "
        "The INCI metafield custom.inci is mandatory: fill it from web sources as a complete ingredient list, "
        "without omissions, summaries, ellipses, 'etc.', 'and more', or Korean omission markers. "
        "If the full source INCI list is not available, return custom.inci as blank instead of shortening it. "
        "Mandatory metafields must be filled when reliable information is available: product benefits, how to use, "
        "description frontend, key features, skin type, and numbers and facts. "
        "For complementary products and related products, select only handles from the provided existing Shopify "
        "product catalog. Never invent a handle. Search product boosts are disabled, so do not recommend search "
        "boost products or queries. "
        "Consider allowed Google Merchant Center metafields and Shopify taxonomy metafields when relevant. "
        "For metaobject reference metafields, suggest only values from the allowed_values list when it is provided. "
        "Return only valid JSON matching the schema."
    )
    user_payload = {
        "raw_product_name": product_name,
        "vendor": vendor,
        "barcode_required_before_upload": False,
        "barcode_search_required": True,
        "price_mode": price_mode,
        "manual_price": manual_price,
        "manual_compare_at_price": manual_compare_at_price,
        "measurement_label": measurement_label,
        "content_language": content_language,
        "content_language_instruction": language_hint,
        "language_dependent_fields": [
            "description_html",
            "custom.benefits",
            "custom.how_to_use",
            "custom.beschreibung_frontend",
            "custom.key_features",
            "custom.skin_type",
            "custom.zahlenfakten_frontend",
        ],
        "language_locked_fields": ["title", "custom.inci"],
        "candidate_handle_to_exclude_from_related_products": slugify(product_name),
        "country_code_of_origin": "KR",
        "existing_shopify_tags": existing_tags,
        "existing_shopify_products_for_discovery": existing_products,
        "allowed_metafield_definitions": allowed_metafields,
        "product_research_evidence": research_records_for_ai(product_research or {}),
        "product_research_warnings": (product_research or {}).get("warnings", []),
        "rules": [
            "status is always DRAFT and should not be returned",
            "do not create the final product title; return title as the raw/official source product name placeholder only",
            "do not create SEO title; return seo_title as an empty string",
            "do not create SEO description; return seo_description as an empty string",
            f"description_html and required text metafield values must be written in {language_hint}",
            f"custom.benefits, custom.how_to_use, custom.beschreibung_frontend, custom.key_features, custom.skin_type, and custom.zahlenfakten_frontend must be written in {language_hint}",
            "custom.inci is the only custom text metafield that must not be translated",
            "non-content enum or choice metafields must keep valid Shopify choice values and must not be translated",
            "title placeholder must keep the official product name and must not be translated because of content_language",
            "custom.inci must preserve exact INCI ingredient names from sources and must not be translated",
            "sku must equal barcode when barcode is found; leave both blank when barcode is not found",
            "price is the discounted selling price and is manual unless price_mode is auto",
            "compare_at_price is the retail/original price and is optional; use manual_compare_at_price when provided",
            "existing_tags must be a relevant subset of existing_shopify_tags and contain at most 6 tags",
            "do not return proposed_new_tags unless no relevant existing tag exists",
            "Shopify inventory shipping weight defaults to 300 GRAMS; do not use product content volume such as 30ml as weight",
            "image candidates must be direct image URLs or leave the list empty",
            "metafield values must only be suggested for allowed metafield definitions",
            "do not return metafields for shopify--discovery--product_search_boost.queries",
            "do not return metafields for shopify--discovery--product_recommendation.related_products_display",
            "mm-google-shopping.custom_product is allowed, but should be true only when reliable evidence shows this is a custom product without standard identifiers",
            "Shopify taxonomy metaobject reference metafields must use one or more allowed_values labels, not invented values",
            "custom.inci must be included in metafields and must be complete when a source is found",
            "if complete INCI cannot be verified, return custom.inci as blank and add a warning; never use etc., and more, ellipses, summaries, or shortened lists",
            "complementary_product_handles should contain 3 to 5 existing handles that work well together with the new product when available",
            "related_product_handles should contain 3 to 5 existing handles for close alternatives or products in the same routine/category when available",
            "related_product_handles must never include the handle of the product being created",
            "search_product_boost_handles must always be an empty list",
            "prefer ACTIVE products for product discovery handles when relevant",
            "exclude the product being created from product discovery handles",
        ],
    }
    payload = {
        "model": openrouter_model(model, use_web),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ],
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "shopify_product_registration_draft",
                "strict": True,
                "schema": AI_SCHEMA,
            },
        },
    }
    result = request_openrouter_json(
        api_key,
        payload,
        "shopify_product_registration_draft",
        fallback_model=openrouter_model(fallback_model, use_web) if fallback_model else "",
    )
    if product_research:
        result["sources"] = list(dict.fromkeys([*(result.get("sources") or []), *research_urls(product_research)]))
        result["warnings"] = [*(result.get("warnings") or []), *((product_research or {}).get("warnings") or [])]
    return result


def generate_ai_seo_draft(
    env: dict[str, str],
    model: str,
    fallback_model: str,
    use_web: bool,
    draft: dict[str, Any],
    vendor: str,
    content_language: str,
    product_research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api_key = env.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required in .env")

    language_hint = content_language_hint(content_language)
    key_metafields = {
        f"{item.get('namespace')}.{item.get('key')}": item.get("value")
        for item in draft.get("metafields") or []
        if isinstance(item, dict) and f"{item.get('namespace')}.{item.get('key')}" in REQUIRED_TEXT_METAFIELDS
    }
    system_prompt = (
        "You write only Shopify SEO fields for Korean beauty ecommerce products. "
        "Use provided product_research_evidence first, especially official product names, size, and retailer naming. "
        "Create an SEO-optimized product title that is also safe to use as the Shopify product title. "
        "Do not translate the product title because of the selected language. Keep brand, product line, product type, "
        "and size/volume when available. Do not invent claims, barcode, certifications, or ingredient facts. "
        "The SEO description must be written in the selected content language. "
        "Return only valid JSON matching the schema."
    )
    user_payload = {
        "current_product_title": draft.get("title", ""),
        "vendor": vendor,
        "product_type": draft.get("product_type", ""),
        "barcode": draft.get("barcode", ""),
        "description_html": draft.get("description_html", ""),
        "key_metafields": key_metafields,
        "tags": draft.get("existing_tags", []),
        "product_research_evidence": research_records_for_ai(product_research or {}),
        "content_language": content_language,
        "content_language_instruction": language_hint,
        "rules": [
            f"title must be at most {SEO_TITLE_MAX} characters",
            "title is used as both Shopify product title and SEO title",
            "title must not be translated because of content_language",
            "title should be natural for search and include brand plus product name and size when available",
            f"seo_description must be at most {SEO_DESCRIPTION_MAX} characters",
            "seo_description must not contain disallowed symbols: ! ¡ ? ¿ # @ $ % ^ * _ = + ~ ` | \\ / < > [ ] { }",
            f"seo_description must be written in {language_hint}",
            "seo_description must be plain text without HTML or markdown",
        ],
    }
    payload = {
        "model": openrouter_model(model, use_web),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, indent=2)},
        ],
        "temperature": 0.15,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "shopify_product_seo_draft",
                "strict": True,
                "schema": SEO_SCHEMA,
            },
        },
    }
    return request_openrouter_json(
        api_key,
        payload,
        "shopify_product_seo_draft",
        fallback_model=openrouter_model(fallback_model, use_web) if fallback_model else "",
    )


def apply_seo_draft(draft: dict[str, Any], seo_draft: dict[str, Any]) -> dict[str, Any]:
    title = str(seo_draft.get("title") or draft.get("title") or "").strip()
    if not title:
        title = str(draft.get("title") or "").strip()
    if len(title) > SEO_TITLE_MAX:
        title = title[:SEO_TITLE_MAX].rstrip()
    result = dict(draft)
    result["title"] = title
    result["seo_title"] = title[:SEO_TITLE_MAX]
    result["seo_description"] = sanitize_seo_description(seo_draft.get("seo_description") or draft.get("seo_description"))
    result["handle"] = slugify(title)
    warnings = list(result.get("warnings") or [])
    warnings.extend(str(item).strip() for item in seo_draft.get("warnings") or [] if str(item).strip())
    result["warnings"] = warnings
    return result


def apply_optional_seo_draft(
    env: dict[str, str],
    model: str,
    fallback_model: str,
    use_web: bool,
    draft: dict[str, Any],
    vendor: str,
    content_language: str,
    product_research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        seo_draft = generate_ai_seo_draft(
            env=env,
            model=model,
            fallback_model=fallback_model,
            use_web=use_web,
            draft=draft,
            vendor=vendor,
            content_language=content_language,
            product_research=product_research,
        )
        return apply_seo_draft(draft, seo_draft)
    except Exception as error:
        result = dict(draft)
        warnings = list(result.get("warnings") or [])
        warnings.append(f"SEO model failed; kept product-data title/SEO description: {error}")
        result["warnings"] = warnings
        return result


def rich_text_value(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{"):
        return stripped
    paragraphs = [
        {
            "type": "paragraph",
            "children": [{"type": "text", "value": part.strip()}],
        }
        for part in re.split(r"\n{2,}", stripped)
        if part.strip()
    ]
    return json.dumps({"type": "root", "children": paragraphs}, ensure_ascii=False)


def metafield_value(definition_type: str, raw_value: str) -> str:
    value = raw_value.strip()
    if is_metaobject_reference_type(definition_type):
        return reference_metafield_value(definition_type, value)
    if definition_type == "rich_text_field":
        return rich_text_value(value)
    if definition_type == "boolean":
        return "true" if value.lower() in {"1", "true", "yes", "y", "ja"} else "false"
    if definition_type.startswith("list."):
        if value.startswith("["):
            return value
        items = [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
        return json.dumps(items, ensure_ascii=False)
    return value


def can_automate_metafield(definition_type: str) -> bool:
    blocked_prefixes = ("list.product_reference",)
    blocked = {"file_reference", "product_reference"}
    return definition_type not in blocked and not definition_type.startswith(blocked_prefixes)


def metafield_identity(row: Any) -> str:
    return f"{row['namespace']}.{row['key']}"


def can_ai_suggest_metafield(row: Any) -> bool:
    identity = metafield_identity(row)
    if identity in BLOCKED_AI_METAFIELDS:
        return False
    definition_type = str(row["type"])
    if is_product_reference_type(definition_type):
        return False
    return can_automate_metafield(definition_type)


def build_product_input(draft: dict[str, Any], vendor: str, tags: list[str]) -> dict[str, Any]:
    return {
        "title": draft["title"].strip(),
        "descriptionHtml": draft.get("description_html") or "",
        "vendor": vendor.strip(),
        "productType": draft.get("product_type") or "",
        "handle": slugify(draft.get("handle") or draft["title"]),
        "status": "DRAFT",
        "tags": tags,
        "seo": {
            "title": (draft.get("seo_title") or draft["title"])[:SEO_TITLE_MAX],
            "description": sanitize_seo_description(draft.get("seo_description")),
        },
    }


def build_product_update_input(product_id: str, draft: dict[str, Any], vendor: str, tags: list[str]) -> dict[str, Any]:
    product_input = build_product_input(draft, vendor, tags)
    product_input["id"] = product_id
    return product_input


def selected_metafields_for_shopify(
    product_id: str,
    metafield_defs: pd.DataFrame,
    approved_values: dict[str, str],
) -> list[dict[str, Any]]:
    inputs = []
    for _, row in metafield_defs.iterrows():
        identity = f"{row['namespace']}.{row['key']}"
        raw_value = approved_values.get(identity, "").strip()
        if not raw_value:
            continue
        definition_type = str(row["type"])
        if not can_automate_metafield(definition_type):
            continue
        value = metafield_value(definition_type, raw_value)
        if is_metaobject_reference_type(definition_type) and not value:
            continue
        inputs.append(
            {
                "ownerId": product_id,
                "namespace": str(row["namespace"]),
                "key": str(row["key"]),
                "type": definition_type,
                "value": value,
            }
        )
    return inputs


def product_reference_metafields_for_shopify(
    product_id: str,
    selected_product_references: dict[str, list[str]],
) -> list[dict[str, Any]]:
    inputs = []
    for identity, product_ids in selected_product_references.items():
        if not product_ids:
            continue
        namespace, key = identity.rsplit(".", 1)
        inputs.append(
            {
                "ownerId": product_id,
                "namespace": namespace,
                "key": key,
                "type": "list.product_reference",
                "value": json.dumps(product_ids, ensure_ascii=False),
            }
        )
    return inputs


def create_product_workflow(
    env: dict[str, str],
    draft: dict[str, Any],
    vendor: str,
    barcode: str,
    price: str,
    compare_at_price: str,
    inventory_qty: int,
    location_id: str,
    selected_tags: list[str],
    weight_value: float | None,
    weight_unit: str,
    unit_price_measurement: dict[str, Any] | None,
    image_urls: list[str],
    image_alt: str,
    metafield_inputs: list[dict[str, Any]],
    update_existing: bool = False,
) -> dict[str, Any]:
    if inventory_qty < 0:
        raise RuntimeError("Inventory quantity cannot be negative.")
    if not location_id:
        raise RuntimeError("A Shopify location is required for inventory.")

    existing_product, existing_match = resolve_existing_product(env, barcode, draft.get("handle") or draft["title"])
    action = "created"
    if existing_product and not update_existing:
        raise RuntimeError(
            f"Product already exists in Shopify with this {existing_match}: "
            f"{existing_product.get('title', 'unknown product')} "
            f"({existing_product.get('handle', 'no handle')}, {existing_product.get('status', 'unknown status')}). "
            "Enable 'Update existing product if found' to update it."
        )

    if existing_product:
        action = "updated"
        product_data = shopify_graphql(
            env,
            UPDATE_PRODUCT_MUTATION,
            {
                "product": build_product_update_input(existing_product["id"], draft, vendor, selected_tags),
                "media": [],
            },
        )["productUpdate"]
        if product_data.get("userErrors"):
            return {"ok": False, "stage": "productUpdate", "errors": product_data["userErrors"]}
    else:
        product_data = shopify_graphql(
            env,
            CREATE_PRODUCT_MUTATION,
            {"product": build_product_input(draft, vendor, selected_tags)},
        )["productCreate"]
        if product_data.get("userErrors"):
            return {"ok": False, "stage": "productCreate", "errors": product_data["userErrors"]}

    product = product_data["product"]
    variants = product.get("variants", {}).get("nodes") or []
    if not variants:
        return {"ok": False, "stage": "variantLookup", "errors": ["No default variant returned."]}

    variant_id = variants[0]["id"]
    inventory_item_id = variants[0]["inventoryItem"]["id"]
    clean_barcode = barcode.strip()
    inventory_item = {
        "tracked": True,
        "requiresShipping": True,
        "countryCodeOfOrigin": "KR",
    }
    if clean_barcode:
        inventory_item["sku"] = clean_barcode
    if weight_value and weight_value > 0:
        inventory_item["measurement"] = {
            "weight": {
                "value": weight_value,
                "unit": weight_unit,
            }
        }

    variant_input = {
        "id": variant_id,
        "price": safe_decimal(price),
        "inventoryPolicy": "DENY",
        "inventoryItem": inventory_item,
    }
    if clean_barcode:
        variant_input["barcode"] = clean_barcode
    compare_at_price_value = safe_decimal(compare_at_price, "")
    if compare_at_price_value:
        variant_input["compareAtPrice"] = compare_at_price_value
    if unit_price_measurement:
        variant_input["unitPriceMeasurement"] = unit_price_measurement

    variant_data = shopify_graphql(
        env,
        UPDATE_VARIANT_MUTATION,
        {"productId": product["id"], "variants": [variant_input]},
    )["productVariantsBulkUpdate"]
    if variant_data.get("userErrors"):
        return {
            "ok": False,
            "stage": "productVariantsBulkUpdate",
            "product": product,
            "errors": variant_data["userErrors"],
        }

    inventory_input = {
        "ignoreCompareQuantity": True,
        "name": "available",
        "reason": "correction",
        "referenceDocumentUri": (
            "shopify-registration-ui://inventory-adjustment/"
            f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        ),
        "quantities": [
            {
                "inventoryItemId": inventory_item_id,
                "locationId": location_id,
                "quantity": inventory_qty,
                "compareQuantity": None,
            }
        ],
    }
    inventory_data = shopify_graphql(env, SET_INVENTORY_MUTATION, {"input": inventory_input})[
        "inventorySetQuantities"
    ]
    if inventory_data.get("userErrors"):
        return {
            "ok": False,
            "stage": "inventorySetQuantities",
            "product": product,
            "errors": inventory_data["userErrors"],
        }

    media_result = None
    if image_urls:
        media_result = shopify_graphql(
            env,
            UPDATE_PRODUCT_MEDIA_MUTATION,
            {
                "product": {"id": product["id"]},
                "media": [
                    {
                        "mediaContentType": "IMAGE",
                        "originalSource": image_url,
                        "alt": image_alt.strip() or draft["title"],
                    }
                    for image_url in image_urls
                ],
            },
        )["productUpdate"]
        if media_result.get("userErrors"):
            return {
                "ok": False,
                "stage": "productUpdate.media",
                "product": product,
                "errors": media_result["userErrors"],
            }

    metafield_result = None
    if metafield_inputs:
        metafield_result = shopify_graphql(
            env,
            SET_METAFIELDS_MUTATION,
            {"metafields": metafield_inputs},
        )["metafieldsSet"]
        if metafield_result.get("userErrors"):
            return {
                "ok": False,
                "stage": "metafieldsSet",
                "product": product,
                "errors": metafield_result["userErrors"],
            }

    return {
        "ok": True,
        "action": action,
        "product": product,
        "variant": variant_data.get("productVariants"),
        "inventory": inventory_data.get("inventoryAdjustmentGroup"),
        "media": media_result,
        "metafields": metafield_result,
    }


def normalize_handle_list(value: Any, limit: int = 10) -> list[str]:
    if not isinstance(value, list):
        return []
    handles = []
    for item in value:
        handle = str(item or "").strip()
        if not handle:
            continue
        if handle not in handles:
            handles.append(handle)
        if len(handles) >= limit:
            break
    return handles


def normalize_metafield_suggestions(draft: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    warnings = [str(warning) for warning in draft.get("warnings") or [] if str(warning).strip()]
    normalized_metafields = []
    for item in draft.get("metafields") or []:
        if not isinstance(item, dict):
            continue
        normalized_item = dict(item)
        identity = f"{normalized_item.get('namespace')}.{normalized_item.get('key')}"
        value = str(normalized_item.get("value") or "")
        if identity == "custom.inci" and inci_has_truncation_marker(value):
            normalized_item["value"] = ""
            warnings.append(
                "INCI suggestion was removed because it contained an omission marker. "
                "The product can upload as draft, but INCI should be completed later from a full source list."
            )
        normalized_metafields.append(normalized_item)
    return normalized_metafields, warnings


def product_labels_from_handles(handles: list[str], product_handle_to_label: dict[str, str]) -> list[str]:
    labels = []
    for raw_handle in handles:
        handle = str(raw_handle or "").strip()
        if not handle:
            continue
        candidates = [handle]
        label_match = re.search(r"\(([^()]+)\)\s*$", handle)
        if label_match:
            candidates.insert(0, label_match.group(1).strip())
        slug = slugify(handle)
        if slug and slug not in candidates:
            candidates.append(slug)
        for candidate in candidates:
            label = product_handle_to_label.get(candidate)
            if label and label not in labels:
                labels.append(label)
                break
    return labels


def without_product_handle(labels: list[str], product_label_to_handle: dict[str, str], blocked_handle: str) -> list[str]:
    normalized_blocked_handle = slugify(blocked_handle)
    if not normalized_blocked_handle:
        return labels
    return [
        label
        for label in labels
        if slugify(product_label_to_handle.get(label, "")) != normalized_blocked_handle
    ]


def normalize_product_type(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def complementary_type_terms(product_type: str) -> set[str]:
    product_type = normalize_product_type(product_type)
    if any(term in product_type for term in {"serum", "ampoule", "essence"}):
        return {"toner", "cream", "cleanser", "sunscreen", "mask", "pad"}
    if "toner" in product_type:
        return {"serum", "ampoule", "essence", "cream", "cleanser", "pad"}
    if "cream" in product_type or "moisturizer" in product_type:
        return {"serum", "ampoule", "essence", "toner", "cleanser", "sunscreen"}
    if "cleanser" in product_type or "cleansing" in product_type:
        return {"toner", "serum", "ampoule", "essence", "cream", "pad"}
    if "sunscreen" in product_type or "sun" in product_type:
        return {"serum", "cream", "toner", "cleanser"}
    if "mask" in product_type or "pack" in product_type:
        return {"toner", "serum", "ampoule", "cream"}
    return {"toner", "serum", "ampoule", "essence", "cream", "cleanser", "sunscreen", "mask", "pad"}


def fallback_discovery_labels(
    products_df: pd.DataFrame,
    current_handle: str,
    vendor: str,
    product_type: str,
    target: str,
    limit: int = 5,
) -> list[str]:
    blocked_handle = slugify(current_handle)
    vendor_value = str(vendor or "").strip().lower()
    product_type_value = normalize_product_type(product_type)
    complement_terms = complementary_type_terms(product_type_value)
    scored: list[tuple[int, str]] = []

    for row in products_df.itertuples():
        handle = str(row.handle)
        if slugify(handle) == blocked_handle:
            continue
        label = f"{row.title} ({row.handle})"
        row_vendor = str(row.vendor or "").strip().lower()
        row_type = normalize_product_type(getattr(row, "productType", ""))
        row_status = str(row.status or "").strip().lower()
        row_text = normalize_product_type(f"{row.title} {row_type}")
        score = 0
        if row_status == "active":
            score += 2
        if vendor_value and row_vendor == vendor_value:
            score += 3
        if target == "related":
            if product_type_value and row_type == product_type_value:
                score += 6
            elif product_type_value and (product_type_value in row_type or row_type in product_type_value):
                score += 3
        else:
            if any(term in row_text for term in complement_terms):
                score += 5
            if product_type_value and row_type == product_type_value:
                score -= 2
        if score > 0:
            scored.append((score, label))

    scored.sort(key=lambda item: (-item[0], item[1].lower()))
    return [label for _, label in scored[:limit]]


def discovery_references_from_draft(
    draft: dict[str, Any],
    products_df: pd.DataFrame,
    product_label_to_id: dict[str, str],
    product_label_to_handle: dict[str, str],
    product_handle_to_label: dict[str, str],
    current_handle: str,
    vendor: str,
    product_type: str,
) -> dict[str, list[str]]:
    selected_product_references: dict[str, list[str]] = {}
    for identity in REQUIRED_PRODUCT_REFERENCE_METAFIELDS:
        draft_key = REQUIRED_PRODUCT_REFERENCE_DRAFT_KEYS[identity]
        fallback_target = "related" if draft_key == "related_product_handles" else "complementary"
        available_options = list(product_label_to_id)
        if draft_key == "related_product_handles":
            available_options = without_product_handle(available_options, product_label_to_handle, current_handle)
        default_labels = product_labels_from_handles(draft.get(draft_key, []), product_handle_to_label)
        default_labels = [label for label in default_labels if label in available_options]
        if len(default_labels) < 3:
            for fallback_label in fallback_discovery_labels(
                products_df=products_df,
                current_handle=current_handle,
                vendor=vendor,
                product_type=product_type,
                target=fallback_target,
            ):
                if fallback_label in available_options and fallback_label not in default_labels:
                    default_labels.append(fallback_label)
                if len(default_labels) >= 5:
                    break
        selected_product_references[identity] = [
            product_label_to_id[label]
            for label in default_labels
            if label in product_label_to_id
        ]
    return selected_product_references


def ai_metafield_values_from_draft(
    draft: dict[str, Any],
    allowed_metafields: list[dict[str, str]],
) -> dict[str, str]:
    ai_metafields = {
        f"{item.get('namespace')}.{item.get('key')}": item
        for item in draft.get("metafields") or []
        if isinstance(item, dict)
    }
    values = {}
    for item in allowed_metafields:
        identity = f"{item['namespace']}.{item['key']}"
        if identity == REQUIRED_SEARCH_BOOST_METAFIELD:
            continue
        suggestion = str(ai_metafields.get(identity, {}).get("value", "") or "").strip()
        if is_metaobject_reference_type(str(item.get("type") or "")):
            matched_ids = match_reference_option_ids(suggestion, item.get("reference_options") or [])
            values[identity] = json.dumps(matched_ids, ensure_ascii=False) if matched_ids else ""
        else:
            values[identity] = suggestion
    return values


def validate_registration_payload(
    draft: dict[str, Any],
    barcode: str,
    approved_metafield_values: dict[str, str],
    selected_product_references: dict[str, list[str]],
) -> list[str]:
    errors = []
    if len(str(draft.get("seo_title") or "")) > SEO_TITLE_MAX:
        errors.append("SEO title is too long")
    if len(str(draft.get("seo_description") or "")) > SEO_DESCRIPTION_MAX:
        errors.append("SEO description is too long")
    if seo_description_symbols(str(draft.get("seo_description") or "")):
        errors.append("SEO description contains disallowed symbols")
    for identity in sorted(REQUIRED_TEXT_METAFIELDS):
        if identity == "custom.inci":
            continue
        if not approved_metafield_values.get(identity, "").strip():
            errors.append(f"Required metafield missing: {identity}")
    for identity, label in REQUIRED_PRODUCT_REFERENCE_METAFIELDS.items():
        if not selected_product_references.get(identity):
            errors.append(f"Required product references missing: {label}")
    return errors


def product_missing_report(
    barcode: str,
    approved_metafield_values: dict[str, str],
) -> list[str]:
    missing = []
    if not barcode.strip():
        missing.append("barcode/SKU")
    inci_value = approved_metafield_values.get("custom.inci", "").strip()
    if not inci_value:
        missing.append("INCI")
    elif inci_has_truncation_marker(inci_value):
        missing.append("complete INCI")
    return missing


def unit_price_measurement_from_label(price: str, measurement_source: str) -> dict[str, Any] | None:
    if not str(price or "").strip():
        return None
    parsed_measurement = parse_measurement_label(measurement_source)
    if not parsed_measurement:
        return None
    reference = default_reference_for_quantity_unit(parsed_measurement[1])
    if not reference:
        return None
    return {
        "quantityValue": parsed_measurement[0],
        "quantityUnit": parsed_measurement[1],
        "referenceValue": reference[0],
        "referenceUnit": reference[1],
    }


def set_metafields_for_product(
    env: dict[str, str],
    product_id: str,
    safe_metafields: pd.DataFrame,
    approved_metafield_values: dict[str, str],
    selected_product_references: dict[str, list[str]],
) -> dict[str, Any] | None:
    metafield_inputs = selected_metafields_for_shopify(
        product_id=product_id,
        metafield_defs=safe_metafields[
            safe_metafields.apply(
                lambda row: f"{row['namespace']}.{row['key']}" in approved_metafield_values,
                axis=1,
            )
        ],
        approved_values=approved_metafield_values,
    )
    metafield_inputs.extend(
        product_reference_metafields_for_shopify(
            product_id=product_id,
            selected_product_references=selected_product_references,
        )
    )
    if not metafield_inputs:
        return None
    return shopify_graphql(env, SET_METAFIELDS_MUTATION, {"metafields": metafield_inputs})["metafieldsSet"]


def normalize_draft(
    draft: dict[str, Any],
    product_name: str,
    vendor: str,
    manual_price: str,
    manual_compare_at_price: str = "",
) -> dict[str, Any]:
    title = str(draft.get("title") or product_name).strip()
    metafields, warnings = normalize_metafield_suggestions(draft)
    return {
        "title": title,
        "seo_title": title[:SEO_TITLE_MAX],
        "seo_description": sanitize_seo_description(draft.get("seo_description")),
        "description_html": str(draft.get("description_html") or f"<p>{html.escape(title)}</p>").strip(),
        "product_type": str(draft.get("product_type") or "").strip(),
        "handle": slugify(draft.get("handle") or title),
        "vendor": vendor,
        "barcode": str(draft.get("barcode") or "").strip(),
        "price": safe_decimal(draft.get("price"), safe_decimal(manual_price)),
        "compare_at_price": safe_decimal(draft.get("compare_at_price"), safe_decimal(manual_compare_at_price, "")),
        "weight_value": 300.0,
        "weight_unit": "GRAMS",
        "existing_tags": [str(tag).strip() for tag in draft.get("existing_tags") or [] if str(tag).strip()],
        "proposed_new_tags": [str(tag).strip() for tag in draft.get("proposed_new_tags") or [] if str(tag).strip()],
        "image_candidates": draft.get("image_candidates") or [],
        "complementary_product_handles": normalize_handle_list(draft.get("complementary_product_handles")),
        "related_product_handles": normalize_handle_list(draft.get("related_product_handles")),
        "search_product_boost_handles": [],
        "metafields": metafields,
        "sources": draft.get("sources") or [],
        "warnings": warnings,
    }


def process_bulk_upload_row(
    env: dict[str, str],
    model: str,
    seo_model: str,
    fallback_model: str,
    use_web: bool,
    row: pd.Series,
    row_number: int,
    tag_options: list[str],
    discovery_products: list[dict[str, str]],
    products_df: pd.DataFrame,
    product_label_to_id: dict[str, str],
    product_label_to_handle: dict[str, str],
    product_handle_to_label: dict[str, str],
    safe_metafields: pd.DataFrame,
    allowed_metafields: list[dict[str, str]],
    location_id: str,
    update_existing: bool,
) -> dict[str, Any]:
    product_name = bulk_cell(row, "product_name")
    vendor = bulk_cell(row, "vendor")
    result_base = {"row": row_number, "product_name": product_name, "vendor": vendor}
    if not product_name or not vendor:
        return {
            **result_base,
            "status": "skipped",
            "stage": "input",
            "message": "Missing product_name or vendor",
            "missing_fields": "product_name/vendor",
            "evidence_urls": "",
        }

    price_mode = bulk_cell(row, "price_mode", "manual")
    if price_mode not in ["manual", "auto from web"]:
        price_mode = "manual"
    content_language = bulk_cell(row, "content_language", "German")
    if content_language not in CONTENT_LANGUAGE_OPTIONS:
        content_language = "German"
    manual_barcode = clean_barcode(bulk_cell(row, "manual_barcode"))
    barcode_mode = normalize_barcode_mode(bulk_cell(row, "barcode_mode", "auto from web"), manual_barcode)
    result_base["barcode_mode"] = barcode_mode
    discounted_price = bulk_cell(row, "discounted_price", bulk_cell(row, "manual_price"))
    retail_price = bulk_cell(row, "retail_price", bulk_cell(row, "compare_at_price"))
    measurement_label = bulk_cell(row, "measurement_label")
    inventory_qty = safe_int(bulk_cell(row, "inventory_quantity", "0"), fallback=0, minimum=0)
    image_urls = parse_image_urls(bulk_cell(row, "image_urls"))
    product_research = {"records": [], "warnings": []}

    try:
        product_research = collect_product_research(env, product_name, vendor)
        raw_draft = generate_ai_draft(
            env=env,
            model=model,
            fallback_model=fallback_model,
            use_web=use_web,
            product_name=product_name,
            vendor=vendor,
            price_mode=price_mode,
            manual_price=discounted_price,
            manual_compare_at_price=retail_price,
            measurement_label=measurement_label,
            content_language=content_language,
            existing_tags=tag_options,
            existing_products=discovery_products,
            allowed_metafields=allowed_metafields,
            product_research=product_research,
        )
        draft = normalize_draft(raw_draft, product_name, vendor, discounted_price, retail_price)
        draft["barcode"] = barcode_from_mode(draft.get("barcode"), barcode_mode, manual_barcode)
        draft = apply_optional_seo_draft(
            env=env,
            model=seo_model,
            fallback_model=fallback_model,
            use_web=use_web,
            draft=draft,
            vendor=vendor,
            content_language=content_language,
            product_research=product_research,
        )
        draft["content_language"] = content_language
        selected_tags = [tag for tag in draft["existing_tags"][:6] if tag in tag_options]
        barcode = str(draft.get("barcode") or "").strip()
        result_base["barcode"] = barcode
        approved_metafield_values = ai_metafield_values_from_draft(draft, allowed_metafields)
        missing_fields = product_missing_report(barcode, approved_metafield_values)
        current_handle = slugify(draft.get("handle") or draft["title"])
        selected_product_references = discovery_references_from_draft(
            draft=draft,
            products_df=products_df,
            product_label_to_id=product_label_to_id,
            product_label_to_handle=product_label_to_handle,
            product_handle_to_label=product_handle_to_label,
            current_handle=current_handle,
            vendor=vendor,
            product_type=draft.get("product_type") or "",
        )
        validation_errors = validate_registration_payload(
            draft=draft,
            barcode=barcode,
            approved_metafield_values=approved_metafield_values,
            selected_product_references=selected_product_references,
        )
        if validation_errors:
            return {
                **result_base,
                "status": "skipped",
                "stage": "validation",
                "message": "; ".join(validation_errors),
                "missing_fields": ", ".join(missing_fields),
                "evidence_urls": " | ".join(research_urls(product_research)),
            }

        price = discounted_price or draft["price"]
        unit_price_measurement = unit_price_measurement_from_label(
            price=price,
            measurement_source=measurement_label or product_name or draft["title"],
        )
        upload_result = create_product_workflow(
            env=env,
            draft=draft,
            vendor=vendor,
            barcode=barcode,
            price=price,
            compare_at_price=retail_price or draft.get("compare_at_price", ""),
            inventory_qty=inventory_qty,
            location_id=location_id,
            selected_tags=selected_tags,
            weight_value=float(draft.get("weight_value") or 300.0),
            weight_unit=draft.get("weight_unit") or "GRAMS",
            unit_price_measurement=unit_price_measurement,
            image_urls=image_urls,
            image_alt=draft["title"],
            metafield_inputs=[],
            update_existing=update_existing,
        )
        if not upload_result.get("ok"):
            return {
                **result_base,
                "status": "failed",
                "stage": upload_result.get("stage", "upload"),
                "message": json.dumps(upload_result.get("errors") or upload_result, ensure_ascii=False),
                "missing_fields": ", ".join(missing_fields),
                "evidence_urls": " | ".join(research_urls(product_research)),
            }

        metafields_result = set_metafields_for_product(
            env=env,
            product_id=upload_result["product"]["id"],
            safe_metafields=safe_metafields,
            approved_metafield_values=approved_metafield_values,
            selected_product_references=selected_product_references,
        )
        if metafields_result and metafields_result.get("userErrors"):
            return {
                **result_base,
                "status": "failed",
                "stage": "metafieldsSet",
                "message": json.dumps(metafields_result["userErrors"], ensure_ascii=False),
                "missing_fields": ", ".join(missing_fields),
                "evidence_urls": " | ".join(research_urls(product_research)),
            }
        upload_result["metafields"] = metafields_result
        return {
            **result_base,
            "status": upload_result.get("action", "created"),
            "stage": "complete",
            "message": upload_result["product"]["title"],
            "missing_fields": ", ".join(missing_fields),
            "evidence_urls": " | ".join(research_urls(product_research)),
            "handle": upload_result["product"].get("handle", ""),
            "product_id": upload_result["product"]["id"],
        }
    except Exception as error:
        return {
            **result_base,
            "status": "failed",
            "stage": "exception",
            "message": str(error),
            "missing_fields": "",
            "evidence_urls": " | ".join(research_urls(product_research)),
        }


def render_mirakl_upload_tab(env: dict[str, str]) -> None:
    st.subheader("Shopify Products to Mirakl")
    st.caption(
        "This workflow extracts Shopify products, maps them to Mirakl product-import columns, "
        "reports missing required fields, and gives you a CSV to review before enabling direct Mirakl upload."
    )

    marketplace_ids = list(MIRAKL_MARKETPLACES)
    marketplace_id = st.selectbox(
        "Mirakl marketplace",
        options=marketplace_ids,
        format_func=lambda item: str(MIRAKL_MARKETPLACES[item]["label"]),
        key="mirakl_marketplace_id",
    )
    marketplace = mirakl_marketplace_config(env, marketplace_id)
    marketplace_label = marketplace["label"]
    state_prefix = f"mirakl_{marketplace['slug']}"
    base_url = marketplace["base_url"]
    api_key = marketplace["api_key"]
    st.write("Mirakl endpoint:", f"{marketplace_label} - {base_url}")
    st.write("Mirakl API key:", "OK" if api_key else "Missing")
    st.write("Shopify token:", "OK" if env.get("SHOPIFY_API") else "Missing")
    if not api_key:
        st.warning(f"Add {marketplace['api_key_env']} to .env before loading {marketplace_label} categories and attributes.")
        return

    cache_col, info_col = st.columns([1, 3])
    with cache_col:
        if st.button(f"Refresh {marketplace_label} catalog cache"):
            fetch_mirakl_hierarchies_cached.clear()
            fetch_mirakl_attributes_cached.clear()
            st.rerun()
    with info_col:
        st.caption(f"{marketplace_label} Mirakl import endpoints are available, but direct upload stays off until the column mapping is confirmed.")

    try:
        hierarchies = fetch_mirakl_hierarchies_cached(base_url, api_key, mirakl_env_fingerprint(env, marketplace_id))
    except Exception as error:
        st.error(f"Could not load {marketplace_label} Mirakl hierarchies: {error}")
        return
    hierarchy_rows = mirakl_hierarchy_rows(hierarchies)
    if not hierarchy_rows:
        st.warning(f"No {marketplace_label} Mirakl categories were returned.")
        return

    category_left, category_right = st.columns([2, 1])
    with category_left:
        leaf_only = st.checkbox("Show only leaf categories", value=True, key=f"{state_prefix}_leaf_only")
        visible_categories = [
            row for row in hierarchy_rows if row["is_leaf"] == "yes"
        ] if leaf_only else hierarchy_rows
        category_label = st.selectbox(
            f"{marketplace_label} marketplace category",
            options=[row["label"] for row in visible_categories],
            key=f"{state_prefix}_category_label",
        )
    selected_category = next(row for row in visible_categories if row["label"] == category_label)
    with category_right:
        st.text_input("Selected category code", value=selected_category["code"], disabled=True)
        st.text_area("Selected category path", value=selected_category["path"], height=96, disabled=True)

    try:
        attributes = fetch_mirakl_attributes_cached(
            base_url,
            api_key,
            mirakl_env_fingerprint(env, marketplace_id),
            selected_category["code"],
        )
        if not attributes:
            attributes = fetch_mirakl_attributes_cached(base_url, api_key, mirakl_env_fingerprint(env, marketplace_id), "")
    except Exception as error:
        st.error(f"Could not load {marketplace_label} Mirakl attributes: {error}")
        return

    required_attribute_rows = [
        {
            "code": mirakl_attribute_code(attribute),
            "label": attribute.get("label") or attribute.get("description") or attribute.get("name") or "",
            "type": attribute.get("type") or attribute.get("format") or "",
        }
        for attribute in attributes
        if mirakl_attribute_code(attribute) and mirakl_attribute_required(attribute)
    ]
    attr_metrics = st.columns(3)
    attr_metrics[0].metric(f"{marketplace_label} categories", len(hierarchy_rows))
    attr_metrics[1].metric("Attributes for selected category", len(attributes))
    attr_metrics[2].metric("Required attributes", len(required_attribute_rows))
    with st.expander("Required Mirakl attributes for this category"):
        if required_attribute_rows:
            st.dataframe(pd.DataFrame(required_attribute_rows), width="stretch")
        else:
            st.info("No required attributes were returned for this category.")

    st.markdown("**Shopify source products**")
    query_col, limit_col = st.columns([2, 1])
    with query_col:
        status_filter = st.selectbox("Shopify status filter", ["ACTIVE", "DRAFT", "ALL"], index=0, key=f"{state_prefix}_status_filter")
        extra_query = st.text_input("Extra Shopify product query", placeholder="vendor:mixsoon", key=f"{state_prefix}_extra_query")
    with limit_col:
        max_products = st.number_input("Max products to export", min_value=1, max_value=1000, value=50, step=10, key=f"{state_prefix}_max_products")
    main_image_mode = st.radio(
        "Mirakl main image handling",
        [
            "White background padding 1000x1000 + upload to Shopify Files",
            "Shopify CDN 1000x1000 center crop URL",
            "Original image URL",
        ],
        index=0,
        help=f"{marketplace_label} Mirakl product import may require a square main image. Padding preserves the whole product image.",
        key=f"{state_prefix}_main_image_mode",
    )
    if main_image_mode.startswith("White background"):
        st.warning(f"This mode creates new 1000x1000 padded image files in Shopify Files and uses their public CDN URLs in the {marketplace_label} Mirakl CSV.")

    query_parts = []
    if status_filter != "ALL":
        query_parts.append(f"status:{status_filter}")
    if extra_query.strip():
        query_parts.append(extra_query.strip())
    shopify_query = " ".join(query_parts)

    if st.button(f"Fetch Shopify products and build {marketplace_label} Mirakl CSV", type="primary"):
        try:
            with st.spinner(f"Fetching Shopify products and mapping {marketplace_label} Mirakl columns..."):
                products = fetch_shopify_products_for_mirakl(env, shopify_query, int(max_products))
                main_image_overrides: dict[str, str] = {}
                image_upload_records: list[dict[str, Any]] = []
                if main_image_mode.startswith("White background"):
                    source_products_by_url: dict[str, dict[str, Any]] = {}
                    for product in products:
                        source_url = first_product_image_url(product)
                        if source_url and source_url not in source_products_by_url:
                            source_products_by_url[source_url] = product
                    if source_products_by_url:
                        progress = st.progress(0)
                        status_slot = st.empty()
                        for index, (source_url, product) in enumerate(source_products_by_url.items()):
                            title = str(product.get("title") or "Shopify product")
                            status_slot.info(f"Creating 1000x1000 padded image for {title}...")
                            try:
                                uploaded_image = upload_white_padded_image_to_shopify_files(
                                    env=env,
                                    source_url=source_url,
                                    product_title=title,
                                    handle=str(product.get("handle") or ""),
                                )
                                if not uploaded_image.get("url"):
                                    raise RuntimeError(f"Shopify file is {uploaded_image.get('fileStatus') or 'not ready'} and returned no CDN URL.")
                                main_image_overrides[source_url] = str(uploaded_image["url"])
                                image_upload_records.append(
                                    {
                                        "shopify_product": title,
                                        "shopify_handle": str(product.get("handle") or ""),
                                        "status": "uploaded",
                                        "source_image": source_url,
                                        "mirakl_main_image": uploaded_image["url"],
                                        "width": uploaded_image.get("width") or 1000,
                                        "height": uploaded_image.get("height") or 1000,
                                        "notes": "White padded 1000x1000 image uploaded to Shopify Files.",
                                    }
                                )
                            except Exception as upload_error:
                                image_upload_records.append(
                                    {
                                        "shopify_product": title,
                                        "shopify_handle": str(product.get("handle") or ""),
                                        "status": "upload failed",
                                        "source_image": source_url,
                                        "mirakl_main_image": "",
                                        "width": "",
                                        "height": "",
                                        "notes": str(upload_error),
                                    }
                                )
                            progress.progress((index + 1) / len(source_products_by_url))
                        status_slot.empty()
                    else:
                        image_upload_records.append(
                            {
                                "shopify_product": "",
                                "shopify_handle": "",
                                "status": "no source images",
                                "source_image": "",
                                "mirakl_main_image": "",
                                "width": "",
                                "height": "",
                                "notes": "No Shopify first images were available to pad and upload.",
                            }
                        )
                square_main_images = main_image_mode.startswith("Shopify CDN")
                rows_df, missing_df, image_report_df = build_mirakl_product_rows(
                    products=products,
                    attributes=attributes,
                    category_path=selected_category["path"],
                    square_main_images=square_main_images,
                    main_image_overrides=main_image_overrides,
                )
                failed_upload_records = [
                    record
                    for record in image_upload_records
                    if record.get("status") != "uploaded"
                ]
                if failed_upload_records:
                    image_report_df = pd.concat(
                        [image_report_df, pd.DataFrame(failed_upload_records)],
                        ignore_index=True,
                    )
            st.session_state[f"{state_prefix}_products"] = products
            st.session_state[f"{state_prefix}_rows_df"] = rows_df
            st.session_state[f"{state_prefix}_missing_df"] = missing_df
            st.session_state[f"{state_prefix}_image_report_df"] = image_report_df
            st.session_state[f"{state_prefix}_image_upload_df"] = pd.DataFrame(image_upload_records)
            st.session_state[f"{state_prefix}_category"] = selected_category
            st.success(f"Prepared {len(rows_df)} {marketplace_label} Mirakl row(s) from {len(products)} Shopify product(s).")
        except Exception as error:
            st.error(str(error))

    rows_df = st.session_state.get(f"{state_prefix}_rows_df")
    missing_df = st.session_state.get(f"{state_prefix}_missing_df")
    image_report_df = st.session_state.get(f"{state_prefix}_image_report_df")
    image_upload_df = st.session_state.get(f"{state_prefix}_image_upload_df")
    if isinstance(rows_df, pd.DataFrame) and not rows_df.empty:
        st.subheader(f"{marketplace_label} Mirakl CSV Preview")
        st.dataframe(rows_df, width="stretch")
        st.download_button(
            f"Download {marketplace_label} Mirakl product CSV",
            data=dataframe_csv_bytes(rows_df),
            file_name=f"mirakl_{marketplace['slug']}_product_import_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            width="stretch",
        )
        if isinstance(missing_df, pd.DataFrame) and not missing_df.empty:
            st.warning(f"Some rows are missing required {marketplace_label} Mirakl columns. Review these before upload.")
            st.dataframe(missing_df, width="stretch")
            st.download_button(
                "Download missing field report",
                data=dataframe_csv_bytes(missing_df),
                file_name=f"mirakl_{marketplace['slug']}_missing_required_fields_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                width="stretch",
            )
        else:
            st.success(f"No missing required {marketplace_label} Mirakl columns found in the prepared rows.")
        if isinstance(image_upload_df, pd.DataFrame) and not image_upload_df.empty:
            with st.expander("1000x1000 image upload report", expanded=True):
                st.dataframe(image_upload_df, width="stretch")
                st.download_button(
                    "Download image upload report",
                    data=dataframe_csv_bytes(image_upload_df),
                    file_name=f"mirakl_{marketplace['slug']}_image_upload_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    width="stretch",
                )
        if isinstance(image_report_df, pd.DataFrame) and not image_report_df.empty:
            st.warning("Some main images need attention before Mirakl upload.")
            st.dataframe(image_report_df, width="stretch")
            st.download_button(
                "Download image requirement report",
                data=dataframe_csv_bytes(image_report_df),
                file_name=f"mirakl_{marketplace['slug']}_image_requirement_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                width="stretch",
            )
        else:
            st.success(f"Main image URLs are prepared for {marketplace_label} Mirakl when Shopify CDN images are available.")


def main() -> None:
    st.set_page_config(
        page_title="Shopify Product Registration",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    render_professional_theme()

    env = load_dotenv(ENV_FILE)
    context_path = data_path("shopify_registration_context.json")
    openrouter_api_key = env.get("OPENROUTER_API_KEY", "").strip()
    searxng_url = searxng_base_url(env)
    serpapi_api_key = serpapi_credentials(env)
    tags_df = read_csv_cached(str(data_path("shopify_product_tags.csv")))
    metafields_df = read_csv_cached(str(data_path("shopify_product_metafield_definitions.csv")))
    locations_df = read_csv_cached(str(data_path("shopify_locations.csv")))
    products_df = read_csv_cached(str(data_path("shopify_product_catalog.csv")))

    shopify_ready = bool(env.get("SHOPIFY_API"))
    openrouter_ready = bool(openrouter_api_key)
    research_ready = bool(searxng_url or serpapi_api_key)
    context_ready = context_path.exists()
    connection_items = [
        {
            "label": "Shopify",
            "state": status_state(shopify_ready),
            "value": "Connected" if shopify_ready else "Missing",
            "detail": "Admin API token",
        },
        {
            "label": "OpenRouter",
            "state": status_state(openrouter_ready),
            "value": "Configured" if openrouter_ready else "Missing",
            "detail": "Draft generation",
        },
        {
            "label": "Research",
            "state": status_state(research_ready),
            "value": "Available" if research_ready else "Offline",
            "detail": searxng_url or ("SerpAPI fallback" if serpapi_api_key else "SearXNG or SerpAPI"),
        },
        {
            "label": "Context",
            "state": status_state(context_ready),
            "value": "Loaded" if context_ready else "Missing",
            "detail": context_path.name,
        },
    ]
    render_app_header()
    render_status_grid(connection_items)

    with st.sidebar:
        st.subheader("Connection")
        render_sidebar_status(connection_items)
        if st.button("Refresh Shopify context"):
            with st.spinner("Fetching metafields, tags, and locations..."):
                refresh_shopify_context()
            st.success("Context refreshed. Reloading...")
            st.rerun()
        if st.button("Refresh OpenRouter models"):
            fetch_openrouter_model_catalog.clear()
            st.rerun()

        default_model = openrouter_base_model(env.get("OPENROUTER_MODEL", "openai/gpt-4o-mini"))
        default_seo_model = openrouter_base_model(env.get("OPENROUTER_SEO_MODEL", default_model))
        default_fallback_model = openrouter_base_model(env.get("OPENROUTER_FALLBACK_MODEL", OPENROUTER_DEFAULT_FALLBACK_MODEL))
        model_catalog_error = ""
        try:
            with st.spinner("Loading OpenRouter models..."):
                model_catalog = fetch_openrouter_model_catalog(
                    openrouter_api_key,
                    openrouter_key_fingerprint(openrouter_api_key),
                )
        except Exception as error:
            model_catalog = {"source": "", "models": []}
            model_catalog_error = str(error)

        model_lookup = {item["id"]: item for item in model_catalog["models"]}
        model_options = list(model_lookup)
        for configured_label, configured_model in [
            ("Current .env product model", default_model),
            ("Current .env SEO model", default_seo_model),
            ("Current .env fallback model", default_fallback_model),
        ]:
            if configured_model and configured_model not in model_lookup:
                model_options.insert(0, configured_model)
                model_lookup[configured_model] = {"id": configured_model, "name": f"{configured_label}: {configured_model}"}

        if model_options:
            model_cost_filter = st.selectbox(
                "Show models",
                options=OPENROUTER_MODEL_COST_FILTER_OPTIONS,
                index=0,
            )
            visible_model_options = filter_openrouter_models_by_cost(
                model_options,
                model_lookup,
                model_cost_filter,
            )
            if not visible_model_options:
                st.warning(f"No {model_cost_filter.lower()} models found. Showing all models.")
                visible_model_options = model_options
            model_sort_mode = st.selectbox(
                "Sort model list by",
                options=OPENROUTER_MODEL_SORT_OPTIONS,
                index=0,
            )
            if model_sort_mode == "Performance tier (heuristic)":
                st.caption("Performance tier is a local heuristic from model/provider names, not an official benchmark score.")
            st.markdown("**Product data model**")
            model = openrouter_model_selector(
                label_prefix="Product data",
                default_model=default_model,
                model_options=visible_model_options,
                model_lookup=model_lookup,
                sort_mode=model_sort_mode,
                provider_key="openrouter_product_provider",
                model_key="openrouter_product_model",
                custom_key="openrouter_product_custom_model",
            )
            st.markdown("**SEO model**")
            seo_model = openrouter_model_selector(
                label_prefix="SEO",
                default_model=default_seo_model,
                model_options=visible_model_options,
                model_lookup=model_lookup,
                sort_mode=model_sort_mode,
                provider_key="openrouter_seo_provider",
                model_key="openrouter_seo_model",
                custom_key="openrouter_seo_custom_model",
            )
            st.markdown("**Fallback model**")
            fallback_model = openrouter_model_selector(
                label_prefix="Fallback",
                default_model=default_fallback_model,
                model_options=visible_model_options,
                model_lookup=model_lookup,
                sort_mode=model_sort_mode,
                provider_key="openrouter_fallback_provider",
                model_key="openrouter_fallback_model",
                custom_key="openrouter_fallback_custom_model",
            )
            st.caption("Fallback is used when the selected OpenRouter provider has no available backend or returns empty JSON.")
            st.caption(f"{len(model_options)} text models loaded from {model_catalog['source']}.")
        else:
            st.warning("Could not load OpenRouter model list. Using manual model ID.")
            if model_catalog_error:
                st.caption(model_catalog_error[:500])
            model = openrouter_base_model(st.text_input("Product data OpenRouter model", value=default_model))
            seo_model = openrouter_base_model(st.text_input("SEO OpenRouter model", value=default_seo_model))
            fallback_model = openrouter_base_model(st.text_input("Fallback OpenRouter model", value=default_fallback_model))
        use_web = st.checkbox("Use OpenRouter web search", value=True)
        st.caption("Web search can add cost on OpenRouter.")

    workflow = st.radio(
        "Workflow",
        ["Shopify draft registration", "Mirakl product export"],
        horizontal=True,
    )
    if workflow == "Mirakl product export":
        render_mirakl_upload_tab(env)
        return

    if tags_df.empty or metafields_df.empty or locations_df.empty or products_df.empty:
        st.warning("Run Refresh Shopify context before using the app.")
        return

    raw_tag_options = sorted(tags_df["tag"].dropna().astype(str).tolist(), key=str.lower)
    tag_options = [tag for tag in raw_tag_options if is_clean_product_tag(tag)]
    safe_metafields = metafields_df[metafields_df.apply(can_ai_suggest_metafield, axis=1)]
    discovery_products = product_catalog_for_ai(products_df)
    product_options = []
    product_label_to_id = {}
    product_label_to_handle = {}
    product_handle_to_label = {}
    for row in products_df.itertuples():
        label = f"{row.title} ({row.handle})"
        product_options.append(label)
        product_label_to_id[label] = row.id
        product_label_to_handle[label] = str(row.handle)
        product_handle_to_label[str(row.handle)] = label
    active_locations = locations_df[locations_df["isActive"].astype(str).str.lower() == "true"]
    default_location = active_locations.iloc[0].to_dict() if not active_locations.empty else locations_df.iloc[0].to_dict()

    summary_cols = st.columns(4)
    summary_cols[0].metric("Clean tags", len(tag_options))
    summary_cols[1].metric("AI metafields", len(safe_metafields))
    summary_cols[2].metric("Catalog products", len(products_df))
    summary_cols[3].metric("Active locations", len(active_locations))

    input_defaults = {
        "product_name_input": "",
        "vendor_input": "",
        "inventory_qty_input": 0,
        "price_mode_input": "manual",
        "barcode_mode_input": "auto from web",
        "manual_barcode_input": "",
        "content_language_input": "German",
        "manual_price_input": "",
        "compare_at_price_input": "",
        "measurement_label_input": "",
        "image_urls_input": "",
    }
    for key, value in input_defaults.items():
        st.session_state.setdefault(key, value)

    st.subheader("Input")
    left, right = st.columns(2)
    with left:
        product_name = st.text_input("Product name from user", placeholder="mixsoon Bean Cream [65ml]", key="product_name_input")
        vendor = st.text_input("Vendor / brand", placeholder="mixsoon", key="vendor_input")
        inventory_qty = st.number_input("Inventory quantity", min_value=0, step=1, key="inventory_qty_input")
        location_name = st.text_input("Inventory location", value=str(default_location["name"]), disabled=True)
        location_id = str(default_location["id"])
    with right:
        price_mode = st.radio("Price mode", ["manual", "auto from web"], horizontal=True, key="price_mode_input")
        barcode_mode = st.radio("Barcode mode", BARCODE_MODE_OPTIONS, horizontal=True, key="barcode_mode_input")
        manual_barcode = st.text_input(
            "Manual barcode / SKU",
            key="manual_barcode_input",
            disabled=barcode_mode != "manual",
            help="When barcode mode is manual, this value is used as both Shopify barcode and SKU.",
        )
        content_language = st.selectbox(
            "Content language",
            CONTENT_LANGUAGE_OPTIONS,
            help="Affects descriptions and text metafields only. Product title, SEO title, and INCI stay unchanged.",
            key="content_language_input",
        )
        manual_price = st.text_input("Discounted price", key="manual_price_input")
        compare_at_price_input = st.text_input("Retail price", key="compare_at_price_input")
        measurement_label = st.text_input("Product measurement label", placeholder="50 ml / 100 g / 5 ea", key="measurement_label_input")
        parsed_input_measurement = parse_measurement_label(measurement_label or product_name)
        suggested_reference_label = (
            unit_price_reference_label(parsed_input_measurement[1])
            if parsed_input_measurement
            else "1 L"
        )
        reference_option_index = (
            UNIT_PRICE_REFERENCE_OPTIONS.index(suggested_reference_label)
            if suggested_reference_label in UNIT_PRICE_REFERENCE_OPTIONS
            else 0
        )
        reference_locked = bool(parsed_input_measurement and suggested_reference_label)
        reference_option = st.selectbox(
            "Unit price reference",
            UNIT_PRICE_REFERENCE_OPTIONS,
            index=reference_option_index,
            disabled=reference_locked,
            help="Use 1 L for ml/l products and 1 KG for g/kg products.",
        )
        if parsed_input_measurement and suggested_reference_label:
            st.caption(f"Auto-matched to {suggested_reference_label} from the measurement label.")
        elif parsed_input_measurement:
            st.caption("Unit price is written only for ml/l or g/kg products.")

    st.divider()
    st.subheader("Metafields")
    st.caption(
        "AI suggestions can consider writable custom, Google Merchant Center, and Shopify taxonomy metafields. "
        "Search boosts and related-products display settings stay excluded. "
        "Shopify taxonomy reference metafields use valid metaobject IDs loaded from Shopify choices."
    )
    reference_options_by_identity, reference_option_warnings = reference_options_by_metafield_identity(env, safe_metafields)
    if reference_option_warnings:
        st.warning("\n".join(reference_option_warnings))
    safe_metafield_options = [f"{row.namespace}.{row.key} ({row.type})" for row in safe_metafields.itertuples()]
    selected_metafield_ids = st.multiselect(
        "Allow AI suggestions for these metafields",
        options=safe_metafield_options,
        default=safe_metafield_options,
    )
    selected_identities = {item.split(" ", 1)[0] for item in selected_metafield_ids}
    selected_identities.update(REQUIRED_TEXT_METAFIELDS)
    allowed_metafields = []
    for _, row in safe_metafields.iterrows():
        identity = f"{row['namespace']}.{row['key']}"
        if identity not in selected_identities:
            continue
        reference_options = reference_options_by_identity.get(identity, [])
        item = {
            "name": str(row["name"]),
            "namespace": str(row["namespace"]),
            "key": str(row["key"]),
            "type": str(row["type"]),
            "description": str(row.get("description") or ""),
        }
        if reference_options:
            item["allowed_values"] = [reference_option_label(option) for option in reference_options]
            item["reference_options"] = reference_options
        allowed_metafields.append(item)
    with st.expander("View all product metafield definitions"):
        st.dataframe(metafields_df[["name", "namespace", "key", "type", "admin_access"]], width="stretch")

    with st.expander("Bulk upload with XLSX"):
        st.caption(
            "Download the template, fill one row per product, then upload it here. "
            "Bulk mode automatically generates AI drafts and uploads valid rows to Shopify as DRAFT products. "
            "Bulk mode uses 1 L for ml/l products and 1 KG for g/kg products."
        )
        st.download_button(
            "Download bulk input template",
            data=bulk_template_bytes(),
            file_name="shopify_product_bulk_upload_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
        )
        bulk_update_existing = st.checkbox(
            "Bulk update existing products if found",
            value=False,
            help="If barcode/SKU or handle already exists, update that product instead of skipping it.",
        )
        bulk_file = st.file_uploader("Upload completed bulk XLSX", type=["xlsx"], key="bulk_xlsx_upload")
        if bulk_file is not None:
            try:
                bulk_df = pd.read_excel(bulk_file, sheet_name="Products", dtype=str).fillna("")
            except Exception as error:
                st.error(f"Could not read bulk XLSX: {error}")
                bulk_df = pd.DataFrame()
            if not bulk_df.empty:
                missing_columns = [column for column in BULK_REQUIRED_COLUMNS if column not in bulk_df.columns]
                if missing_columns:
                    st.error("Missing required columns: " + ", ".join(missing_columns))
                else:
                    st.dataframe(bulk_df, width="stretch")
                    st.warning(
                        "This will call OpenRouter for each row and create or update Shopify draft products for rows that pass validation."
                    )
                    if st.button("Generate AI drafts and upload all XLSX rows", type="primary"):
                        results = []
                        progress = st.progress(0)
                        status_slot = st.empty()
                        for index, row in bulk_df.iterrows():
                            product_label = bulk_cell(row, "product_name") or f"row {index + 2}"
                            status_slot.info(f"Processing {product_label}...")
                            result = process_bulk_upload_row(
                                env=env,
                                model=model,
                                seo_model=seo_model,
                                fallback_model=fallback_model,
                                use_web=use_web,
                                row=row,
                                row_number=index + 2,
                                tag_options=tag_options,
                                discovery_products=discovery_products,
                                products_df=products_df,
                                product_label_to_id=product_label_to_id,
                                product_label_to_handle=product_label_to_handle,
                                product_handle_to_label=product_handle_to_label,
                                safe_metafields=safe_metafields,
                                allowed_metafields=allowed_metafields,
                                location_id=location_id,
                                update_existing=bulk_update_existing,
                            )
                            results.append(result)
                            progress.progress((index + 1) / len(bulk_df))
                        status_slot.success("Bulk upload finished.")
                        results_df = pd.DataFrame(results)
                        st.session_state["bulk_upload_results"] = results_df
                        audit_path = runtime_path("last_bulk_upload_results.json")
                        audit_path.write_text(
                            json.dumps(results, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                    if "bulk_upload_results" in st.session_state:
                        st.dataframe(st.session_state["bulk_upload_results"], width="stretch")

    generate_disabled = not product_name.strip() or not vendor.strip()
    if st.button("Generate draft with OpenRouter", disabled=generate_disabled, type="primary"):
        with st.spinner("Researching product and generating product data..."):
            product_research = collect_product_research(env, product_name, vendor)
            draft = generate_ai_draft(
                env=env,
                model=model,
                fallback_model=fallback_model,
                use_web=use_web,
                product_name=product_name,
                vendor=vendor,
                price_mode=price_mode,
                manual_price=manual_price,
                manual_compare_at_price=compare_at_price_input,
                measurement_label=measurement_label,
                content_language=content_language,
                existing_tags=tag_options,
                existing_products=discovery_products,
                allowed_metafields=allowed_metafields,
                product_research=product_research,
            )
            normalized_draft = normalize_draft(draft, product_name, vendor, manual_price, compare_at_price_input)
            normalized_draft["barcode"] = barcode_from_mode(
                normalized_draft.get("barcode"),
                barcode_mode,
                manual_barcode,
            )
            normalized_draft = apply_optional_seo_draft(
                env=env,
                model=seo_model,
                fallback_model=fallback_model,
                use_web=use_web,
                draft=normalized_draft,
                vendor=vendor,
                content_language=content_language,
                product_research=product_research,
            )
            normalized_draft["content_language"] = content_language
            normalized_draft["research_records"] = product_research.get("records", [])
            st.session_state["draft"] = normalized_draft

    if "draft" not in st.session_state:
        st.info("Enter product name and vendor, then generate a draft.")
        return

    draft = st.session_state["draft"]
    draft_language = draft.get("content_language", "German")
    if draft_language != content_language:
        st.warning(
            "Content language changed from "
            f"{draft_language} to {content_language}. Generate the draft again so SEO description "
            "and editable metafields use the selected language. Product title, SEO title, and INCI stay unchanged."
        )
    measurement_source = measurement_label or product_name or draft["title"]
    parsed_measurement = parse_measurement_label(measurement_source)
    default_quantity_value = parsed_measurement[0] if parsed_measurement else 0.0
    default_quantity_unit = parsed_measurement[1] if parsed_measurement else "ML"
    if draft.get("research_records"):
        with st.expander("Product research evidence"):
            st.dataframe(pd.DataFrame(draft["research_records"]), width="stretch")
    st.subheader("Review Draft")
    col_a, col_b = st.columns(2)
    with col_a:
        title = st.text_input("SEO product title", value=draft["title"])
        seo_title = title[:SEO_TITLE_MAX]
        st.caption(f"SEO title follows SEO product title: {len(seo_title)}/{SEO_TITLE_MAX} characters")
        seo_description = st.text_area(
            "SEO description",
            value=draft["seo_description"],
            height=90,
            max_chars=SEO_DESCRIPTION_MAX,
        )
        st.caption(f"SEO description: {len(seo_description)}/{SEO_DESCRIPTION_MAX} characters")
        product_type = st.text_input("Product type", value=draft["product_type"])
        handle = st.text_input("Handle", value=draft["handle"])
        description_html = st.text_area("Description HTML", value=draft["description_html"], height=220)
    with col_b:
        review_barcode_default = barcode_from_mode(draft.get("barcode"), barcode_mode, manual_barcode)
        barcode = st.text_input(f"Barcode / SKU ({barcode_mode}, editable)", value=review_barcode_default)
        price = st.text_input("Discounted price", value=manual_price or draft["price"])
        compare_at_price = st.text_input("Retail price", value=compare_at_price_input or draft["compare_at_price"])
        weight_value = st.number_input("Weight value", min_value=0.0, value=float(draft["weight_value"]), step=1.0)
        weight_unit = st.selectbox(
            "Weight unit",
            ["GRAMS", "KILOGRAMS", "OUNCES", "POUNDS"],
            index=["GRAMS", "KILOGRAMS", "OUNCES", "POUNDS"].index(draft["weight_unit"])
            if draft["weight_unit"] in ["GRAMS", "KILOGRAMS", "OUNCES", "POUNDS"]
            else 0,
        )
        selected_tags = st.multiselect(
            "Clean Shopify tags",
            options=tag_options,
            default=[tag for tag in draft["existing_tags"][:6] if tag in tag_options],
        )
        with st.expander("Show raw Shopify tags"):
            st.write(", ".join(raw_tag_options))
        st.text_input("Country code of origin", value="KR", disabled=True)
        st.text_input("Inventory policy", value="DENY", disabled=True)

    current_product_handle = slugify(handle or draft.get("handle") or title)

    st.subheader("Unit Price Measurement")
    unit_family = measurement_unit_family(default_quantity_unit)
    unit_enabled = bool(price.strip()) and parsed_measurement is not None and bool(unit_family)
    if parsed_measurement and not unit_family:
        st.info("Unit price measurement is skipped because only ml/l and g/kg products can use the 1 L or 1 KG references.")
    use_unit_price = st.checkbox("Write unit price measurement", value=unit_enabled, disabled=not unit_enabled)
    unit_price_measurement = None
    if use_unit_price:
        quantity_value = st.number_input("Quantity value", min_value=0.0, step=1.0, value=float(default_quantity_value))
        quantity_unit_options = unit_options_for_family(default_quantity_unit)
        quantity_unit = st.selectbox(
            "Quantity unit",
            quantity_unit_options,
            index=quantity_unit_options.index(default_quantity_unit) if default_quantity_unit in quantity_unit_options else 0,
        )
        reference_value, reference_unit = default_reference_for_quantity_unit(quantity_unit) or (1, "L")
        st.text_input("Unit price reference", value=f"{reference_value} {reference_unit}", disabled=True)
        unit_price_measurement = {
            "quantityValue": quantity_value,
            "quantityUnit": quantity_unit,
            "referenceValue": reference_value,
            "referenceUnit": reference_unit,
        }

    st.subheader("Images")
    image_candidates = draft.get("image_candidates") or []
    image_choice = ""
    if image_candidates:
        labels = [
            f"{item.get('alt') or 'Image'} - {item.get('url')}"
            for item in image_candidates
            if item.get("url")
        ]
        selected_label = st.selectbox("AI/web image candidates", [""] + labels)
        if selected_label:
            image_choice = image_candidates[labels.index(selected_label)]["url"]
    if image_choice and not st.session_state.get("image_urls_input", "").strip():
        st.session_state["image_urls_input"] = image_choice
    image_urls_text = st.text_area(
        "Approved image URLs to save as Shopify product media",
        key="image_urls_input",
        height=110,
        help="Paste one or more public image URLs. Separate them with new lines, commas, or semicolons.",
    )
    approved_image_urls = parse_image_urls(image_urls_text)
    st.caption(f"{len(approved_image_urls)} image URL(s) will be uploaded to Shopify media.")
    image_alt = st.text_input("Image alt text", value=title)
    uploaded = st.file_uploader("Manual local image fallback")
    if uploaded is not None:
        st.warning("Local file upload to Shopify staged media is planned next. For now, paste a public image URL above.")

    st.subheader("Metafield Review")
    ai_metafields = {
        f"{item.get('namespace')}.{item.get('key')}": item
        for item in draft.get("metafields") or []
    }
    approved_metafield_values: dict[str, str] = {}
    if allowed_metafields:
        for item in allowed_metafields:
            identity = f"{item['namespace']}.{item['key']}"
            if identity == REQUIRED_SEARCH_BOOST_METAFIELD:
                continue
            suggestion = ai_metafields.get(identity, {}).get("value", "")
            label_prefix = "REQUIRED - " if is_required_text_metafield(identity) else ""
            definition_type = str(item["type"])
            label = f"{label_prefix}{item['name']} - {identity} ({definition_type})"
            if is_metaobject_reference_type(definition_type):
                reference_options = item.get("reference_options") or []
                option_labels = [reference_option_label(option) for option in reference_options]
                label_to_id = {
                    reference_option_label(option): option.get("id")
                    for option in reference_options
                    if option.get("id")
                }
                default_ids = match_reference_option_ids(suggestion, reference_options)
                default_labels = [
                    option_label
                    for option_label in option_labels
                    if label_to_id.get(option_label) in default_ids
                ]
                if option_labels:
                    selected_reference_labels = st.multiselect(
                        label,
                        options=option_labels,
                        default=default_labels,
                        help="AI can suggest labels, but Shopify stores metaobject IDs. Edit the selected choices before upload.",
                    )
                    selected_reference_ids = [
                        label_to_id[selected_label]
                        for selected_label in selected_reference_labels
                        if selected_label in label_to_id
                    ]
                    approved_metafield_values[identity] = (
                        json.dumps(selected_reference_ids, ensure_ascii=False)
                        if definition_type.startswith("list.")
                        else (selected_reference_ids[0] if selected_reference_ids else "")
                    )
                else:
                    st.text_area(
                        label,
                        value=suggestion,
                        height=90,
                        disabled=True,
                        help="No Shopify metaobject choices were loaded for this reference metafield, so it cannot be written safely yet.",
                    )
                    approved_metafield_values[identity] = ""
            else:
                approved_metafield_values[identity] = st.text_area(
                    label,
                    value=suggestion,
                    height=180 if is_inci_identity(identity) else 100,
                )
    else:
        st.info("No metafields selected for AI suggestions yet.")

    st.subheader("Required Product Discovery Metafields")
    st.caption("AI preselects existing Shopify products here. If AI returns none, the app suggests catalog matches you can edit.")
    selected_product_references: dict[str, list[str]] = {}
    for identity, label in REQUIRED_PRODUCT_REFERENCE_METAFIELDS.items():
        draft_key = REQUIRED_PRODUCT_REFERENCE_DRAFT_KEYS[identity]
        available_options = product_options
        fallback_target = "complementary"
        if draft_key == "related_product_handles":
            fallback_target = "related"
            available_options = without_product_handle(product_options, product_label_to_handle, current_product_handle)
        default_labels = product_labels_from_handles(draft.get(draft_key, []), product_handle_to_label)
        default_labels = [default_label for default_label in default_labels if default_label in available_options]
        if len(default_labels) < 3:
            for fallback_label in fallback_discovery_labels(
                products_df=products_df,
                current_handle=current_product_handle,
                vendor=vendor,
                product_type=product_type,
                target=fallback_target,
            ):
                if fallback_label in available_options and fallback_label not in default_labels:
                    default_labels.append(fallback_label)
                if len(default_labels) >= 5:
                    break
        selected_labels = st.multiselect(
            f"REQUIRED - {label}",
            options=available_options,
            default=default_labels,
            help="Choose existing Shopify products. The metafield stores product IDs.",
        )
        selected_product_references[identity] = [
            product_label_to_id[label]
            for label in selected_labels
            if label in product_label_to_id
        ]

    st.caption("Search product boosts are intentionally skipped and are not required.")

    if draft.get("warnings"):
        st.warning("\n".join(draft["warnings"]))
    if draft.get("sources"):
        with st.expander("Sources"):
            for source in draft["sources"]:
                st.write(source)

    updated_draft = {
        **draft,
        "title": title,
        "seo_title": seo_title,
        "seo_description": seo_description,
        "description_html": description_html,
        "product_type": product_type,
        "handle": handle,
        "barcode": barcode.strip(),
        "compare_at_price": compare_at_price,
    }

    st.subheader("Upload")
    st.caption("New products are created as Shopify DRAFT. Existing products can be updated only when you enable it below.")
    update_existing = st.checkbox(
        "Update existing product if found",
        value=False,
        help="If barcode/SKU or handle already exists, update that product instead of stopping.",
    )
    inci_value = approved_metafield_values.get("custom.inci", "").strip()
    inci_blocked = not inci_value or inci_has_truncation_marker(inci_value)
    missing_required_text_metafields = [
        identity
        for identity in sorted(REQUIRED_TEXT_METAFIELDS)
        if identity != "custom.inci"
        if not approved_metafield_values.get(identity, "").strip()
    ]
    missing_required_product_refs = [
        label
        for identity, label in REQUIRED_PRODUCT_REFERENCE_METAFIELDS.items()
        if not selected_product_references.get(identity)
    ]
    seo_description_bad_symbols = seo_description_symbols(seo_description)
    related_identity = "shopify--discovery--product_recommendation.related_products"
    self_related_selected = product_label_to_id.get(product_handle_to_label.get(current_product_handle, "")) in set(
        selected_product_references.get(related_identity, [])
    )
    seo_blocked = (
        len(seo_title) > SEO_TITLE_MAX
        or len(seo_description) > SEO_DESCRIPTION_MAX
        or bool(seo_description_bad_symbols)
    )
    if not barcode.strip():
        st.warning("Missing report: barcode/SKU was not found. The draft can still be uploaded without barcode and SKU.")
    if seo_blocked:
        st.error("SEO title must be under 70 characters. SEO description must be under 160 characters and contain no disallowed symbols.")
    if seo_description_bad_symbols:
        st.error("Remove these symbols from SEO description: " + " ".join(seo_description_bad_symbols))
    if self_related_selected:
        st.error("Related products cannot include the product itself.")
    if not inci_value:
        st.warning("Missing report: INCI is missing. The draft can still be uploaded and INCI can be added later.")
    elif inci_has_truncation_marker(inci_value):
        st.warning("Missing report: INCI looks incomplete. The draft can still be uploaded and INCI can be completed later.")
    if missing_required_text_metafields:
        st.error("Required metafields missing: " + ", ".join(missing_required_text_metafields))
    if missing_required_product_refs:
        st.error("Required product references missing: " + ", ".join(missing_required_product_refs))
    upload_disabled = (
        seo_blocked
        or self_related_selected
        or bool(missing_required_text_metafields)
        or bool(missing_required_product_refs)
    )
    if st.button("Create Shopify draft product", disabled=upload_disabled, type="primary"):
        try:
            # Fill ownerId after the product exists. The workflow recreates this list internally.
            result = create_product_workflow(
                env=env,
                draft=updated_draft,
                vendor=vendor,
                barcode=barcode.strip(),
                price=price,
                compare_at_price=compare_at_price,
                inventory_qty=int(inventory_qty),
                location_id=location_id,
                selected_tags=selected_tags,
                weight_value=weight_value,
                weight_unit=weight_unit,
                unit_price_measurement=unit_price_measurement,
                image_urls=approved_image_urls,
                image_alt=image_alt,
                metafield_inputs=[],
                update_existing=update_existing,
            )
            if result.get("ok"):
                product_id = result["product"]["id"]
                metafield_inputs = selected_metafields_for_shopify(
                    product_id=product_id,
                    metafield_defs=safe_metafields[
                        safe_metafields.apply(
                            lambda row: f"{row['namespace']}.{row['key']}" in approved_metafield_values,
                            axis=1,
                        )
                    ],
                    approved_values=approved_metafield_values,
                )
                metafield_inputs.extend(
                    product_reference_metafields_for_shopify(
                        product_id=product_id,
                        selected_product_references=selected_product_references,
                    )
                )
                if metafield_inputs:
                    metafields_result = shopify_graphql(
                        env,
                        SET_METAFIELDS_MUTATION,
                        {"metafields": metafield_inputs},
                    )["metafieldsSet"]
                    result["metafields"] = metafields_result
                audit_path = runtime_path("last_registration_result.json")
                audit_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
                action_label = "Updated existing product" if result.get("action") == "updated" else "Created draft product"
                st.success(f"{action_label}: {result['product']['title']}")
                st.json(result)
            else:
                st.error(f"Failed at {result.get('stage')}")
                st.json(result)
        except Exception as error:
            st.error(str(error))


if __name__ == "__main__":
    main()
