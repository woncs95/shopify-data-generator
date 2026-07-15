import argparse
import csv
import html
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from shopify_data_generator.paths import REPO_ROOT, RUNTIME_DIR


SHOPIFY_API_VERSION = "2025-10"
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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
mutation UpdateVariant($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    product {
      id
      title
    }
    productVariants {
      id
      sku
      price
      barcode
      compareAtPrice
      inventoryItem {
        id
        sku
        tracked
      }
    }
    userErrors {
      field
      message
    }
  }
}
"""


PRODUCT_DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description_html": {"type": "string"},
        "vendor": {"type": "string"},
        "product_type": {"type": "string"},
        "handle": {"type": "string"},
        "tags": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 20,
        },
        "seo_title": {"type": "string"},
        "seo_description": {"type": "string"},
        "variant": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "barcode": {"type": "string"},
                "price": {"type": "string"},
                "compare_at_price": {"type": "string"},
                "tracked": {"type": "boolean"},
                "requires_shipping": {"type": "boolean"},
            },
            "required": [
                "sku",
                "barcode",
                "price",
                "compare_at_price",
                "tracked",
                "requires_shipping",
            ],
            "additionalProperties": False,
        },
        "confidence": {
            "type": "string",
            "enum": ["high", "medium", "low"],
        },
        "review_notes": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 10,
        },
    },
    "required": [
        "title",
        "description_html",
        "vendor",
        "product_type",
        "handle",
        "tags",
        "seo_title",
        "seo_description",
        "variant",
        "confidence",
        "review_notes",
    ],
    "additionalProperties": False,
}


@dataclass
class Config:
    root: Path
    shopify_token: str
    shopify_host: str
    openrouter_key: str | None
    openrouter_model: str | None


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


def load_config(root: Path, model: str | None) -> Config:
    env = load_dotenv(root / ".env")
    shopify_token = env.get("SHOPIFY_API", "").strip()
    shopify_store = env.get("SHOPIFY_STORE_NAME", "").strip()
    if not shopify_token:
        raise SystemExit("SHOPIFY_API is missing from .env")
    if not shopify_store:
        raise SystemExit("SHOPIFY_STORE_NAME is missing from .env")
    return Config(
        root=root,
        shopify_token=shopify_token,
        shopify_host=normalize_shopify_host(shopify_store),
        openrouter_key=(env.get("OPENROUTER_API_KEY") or "").strip() or None,
        openrouter_model=model or (env.get("OPENROUTER_MODEL") or "").strip() or None,
    )


def request_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code}: {body}") from error


def shopify_graphql(config: Config, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    data = request_json(
        f"https://{config.shopify_host}/admin/api/{SHOPIFY_API_VERSION}/graphql.json",
        {"query": query, "variables": variables},
        {"X-Shopify-Access-Token": config.shopify_token},
    )
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def compact_row(row: dict[str, str]) -> dict[str, str]:
    return {
        key.strip(): value.strip()
        for key, value in row.items()
        if key and value and value.strip()
    }


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return slug.strip("-")[:240]


def safe_decimal(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "0.00"
    cleaned = re.sub(r"[^0-9.,-]", "", text).replace(",", ".")
    try:
        return f"{Decimal(cleaned):.2f}"
    except InvalidOperation:
        return "0.00"


def fallback_draft(row: dict[str, str]) -> dict[str, Any]:
    title = (
        row.get("title")
        or row.get("name")
        or row.get("product_title")
        or row.get("product_name")
        or "Untitled product"
    )
    description = (
        row.get("description_html")
        or row.get("description")
        or row.get("body")
        or row.get("bodyHtml")
        or ""
    )
    if description and "<" not in description:
        description = f"<p>{html.escape(description)}</p>"
    vendor = row.get("vendor") or row.get("brand") or row.get("manufacturer") or ""
    product_type = row.get("product_type") or row.get("type") or row.get("category") or ""
    sku = row.get("sku") or row.get("SKU") or row.get("seller_sku") or ""
    barcode = row.get("barcode") or row.get("ean") or row.get("gtin") or row.get("upc") or ""
    price = row.get("price") or row.get("retail_price") or row.get("sale_price") or "0.00"
    compare_at_price = row.get("compare_at_price") or row.get("msrp") or ""
    tags = [
        value.strip()
        for value in ",".join(
            [
                row.get("tags", ""),
                vendor,
                product_type,
            ]
        ).split(",")
        if value.strip()
    ]
    return {
        "title": title.strip(),
        "description_html": description.strip(),
        "vendor": vendor.strip(),
        "product_type": product_type.strip(),
        "handle": slugify(row.get("handle") or title),
        "tags": sorted(set(tags))[:20],
        "seo_title": title.strip()[:70],
        "seo_description": re.sub(r"<[^>]+>", "", description).strip()[:320],
        "variant": {
            "sku": sku.strip(),
            "barcode": barcode.strip(),
            "price": safe_decimal(price),
            "compare_at_price": safe_decimal(compare_at_price) if compare_at_price else "",
            "tracked": True,
            "requires_shipping": True,
        },
        "confidence": "low",
        "review_notes": ["Generated without OpenRouter; review before applying."],
    }


def enrich_with_openrouter(config: Config, row: dict[str, str]) -> dict[str, Any]:
    if not config.openrouter_key:
        raise RuntimeError("OPENROUTER_API_KEY is missing from .env")
    if not config.openrouter_model:
        raise RuntimeError("Set OPENROUTER_MODEL in .env or pass --model.")

    system_prompt = (
        "You transform raw supplier marketplace rows into Shopify product draft data. "
        "Use the input facts; do not invent certifications, medical claims, dimensions, "
        "ingredients, or regulatory claims. If a field is missing, leave it blank or add "
        "a review note. Create clean customer-facing copy and valid simple HTML."
    )
    user_prompt = json.dumps(row, ensure_ascii=False, indent=2)
    payload = {
        "model": config.openrouter_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "shopify_product_draft",
                "strict": True,
                "schema": PRODUCT_DRAFT_SCHEMA,
            },
        },
    }
    data = request_json(
        OPENROUTER_URL,
        payload,
        {"Authorization": f"Bearer {config.openrouter_key}"},
    )
    if data.get("error"):
        raise RuntimeError(json.dumps(data["error"], indent=2))
    content = data["choices"][0]["message"]["content"]
    return json.loads(content)


def normalize_draft(draft: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(draft)
    normalized["title"] = str(normalized.get("title") or "Untitled product").strip()
    normalized["handle"] = slugify(normalized.get("handle") or normalized["title"])
    normalized["description_html"] = str(normalized.get("description_html") or "").strip()
    normalized["vendor"] = str(normalized.get("vendor") or "").strip()
    normalized["product_type"] = str(normalized.get("product_type") or "").strip()
    normalized["tags"] = [str(tag).strip() for tag in normalized.get("tags") or [] if str(tag).strip()]
    normalized["seo_title"] = str(normalized.get("seo_title") or normalized["title"]).strip()[:70]
    normalized["seo_description"] = str(normalized.get("seo_description") or "").strip()[:320]
    variant = dict(normalized.get("variant") or {})
    variant["price"] = safe_decimal(variant.get("price"))
    if variant.get("compare_at_price"):
        variant["compare_at_price"] = safe_decimal(variant.get("compare_at_price"))
    normalized["variant"] = variant
    return normalized


def to_shopify_product_input(draft: dict[str, Any]) -> dict[str, Any]:
    product_input = {
        "title": draft["title"],
        "status": "DRAFT",
    }
    optional_map = {
        "descriptionHtml": draft.get("description_html"),
        "vendor": draft.get("vendor"),
        "productType": draft.get("product_type"),
        "handle": draft.get("handle"),
        "tags": draft.get("tags"),
    }
    for key, value in optional_map.items():
        if value:
            product_input[key] = value
    seo = {
        key: value
        for key, value in {
            "title": draft.get("seo_title"),
            "description": draft.get("seo_description"),
        }.items()
        if value
    }
    if seo:
        product_input["seo"] = seo
    return product_input


def create_shopify_draft(config: Config, draft: dict[str, Any]) -> dict[str, Any]:
    create_data = shopify_graphql(
        config,
        CREATE_PRODUCT_MUTATION,
        {"product": to_shopify_product_input(draft)},
    )["productCreate"]
    if create_data.get("userErrors"):
        return {"ok": False, "stage": "productCreate", "errors": create_data["userErrors"]}

    product = create_data["product"]
    variant_nodes = product.get("variants", {}).get("nodes") or []
    if not variant_nodes:
        return {"ok": True, "product": product, "variant_update": "skipped_no_default_variant"}

    variant_id = variant_nodes[0]["id"]
    variant = draft.get("variant") or {}
    variant_input = {
        "id": variant_id,
        "price": variant.get("price") or "0.00",
        "inventoryItem": {
            "sku": variant.get("sku") or "",
            "tracked": bool(variant.get("tracked", True)),
            "requiresShipping": bool(variant.get("requires_shipping", True)),
        },
    }
    if variant.get("barcode"):
        variant_input["barcode"] = variant["barcode"]
    if variant.get("compare_at_price"):
        variant_input["compareAtPrice"] = variant["compare_at_price"]

    update_data = shopify_graphql(
        config,
        UPDATE_VARIANT_MUTATION,
        {"productId": product["id"], "variants": [variant_input]},
    )["productVariantsBulkUpdate"]
    if update_data.get("userErrors"):
        return {
            "ok": False,
            "stage": "productVariantsBulkUpdate",
            "product": product,
            "errors": update_data["userErrors"],
        }
    return {"ok": True, "product": product, "variant_update": update_data["productVariants"]}


def read_products_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return [compact_row(row) for row in csv.DictReader(file)]


def write_review_csv(path: Path, records: list[dict[str, Any]]) -> None:
    fieldnames = [
        "row_number",
        "title",
        "handle",
        "vendor",
        "product_type",
        "sku",
        "barcode",
        "price",
        "confidence",
        "review_notes",
        "shopify_status",
        "shopify_product_id",
        "shopify_handle",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            draft = record["draft"]
            variant = draft.get("variant") or {}
            result = record.get("shopify_result") or {}
            product = result.get("product") or {}
            writer.writerow(
                {
                    "row_number": record["row_number"],
                    "title": draft.get("title", ""),
                    "handle": draft.get("handle", ""),
                    "vendor": draft.get("vendor", ""),
                    "product_type": draft.get("product_type", ""),
                    "sku": variant.get("sku", ""),
                    "barcode": variant.get("barcode", ""),
                    "price": variant.get("price", ""),
                    "confidence": draft.get("confidence", ""),
                    "review_notes": " | ".join(draft.get("review_notes") or []),
                    "shopify_status": "created" if result.get("ok") else "not_applied",
                    "shopify_product_id": product.get("id", ""),
                    "shopify_handle": product.get("handle", ""),
                    "error": json.dumps(result.get("errors", ""), ensure_ascii=False)
                    if result.get("errors")
                    else record.get("error", ""),
                }
            )


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draft and optionally register Shopify products.")
    parser.add_argument("--input", required=True, help="CSV file containing raw product rows.")
    parser.add_argument("--model", help="OpenRouter model id. Can also be set as OPENROUTER_MODEL.")
    parser.add_argument("--limit", type=int, help="Only process the first N rows.")
    parser.add_argument("--apply", action="store_true", help="Create Shopify DRAFT products.")
    parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Use deterministic CSV mapping only, without OpenRouter enrichment.",
    )
    parser.add_argument(
        "--out-prefix",
        default="product_registration",
        help="Output file prefix for review CSV and JSONL.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = REPO_ROOT
    config = load_config(root, args.model)
    input_path = Path(args.input)
    if not input_path.is_absolute():
        input_path = Path.cwd() / input_path
    rows = read_products_csv(input_path)
    if args.limit:
        rows = rows[: args.limit]

    records = []
    for index, row in enumerate(rows, start=1):
        try:
            draft = fallback_draft(row) if args.no_ai else enrich_with_openrouter(config, row)
            draft = normalize_draft(draft)
            record = {"row_number": index, "source": row, "draft": draft}
            if args.apply:
                record["shopify_result"] = create_shopify_draft(config, draft)
            records.append(record)
            print(f"processed row {index}: {draft['title']}", file=sys.stderr)
        except Exception as error:
            fallback = normalize_draft(fallback_draft(row))
            records.append(
                {
                    "row_number": index,
                    "source": row,
                    "draft": fallback,
                    "error": str(error),
                }
            )
            print(f"row {index} failed: {error}", file=sys.stderr)

    out_prefix = Path(args.out_prefix)
    if out_prefix.is_absolute():
        output_base = out_prefix
    elif out_prefix.parent != Path("."):
        output_base = Path.cwd() / out_prefix
    else:
        output_base = RUNTIME_DIR / out_prefix
    output_base.parent.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_base.with_name(f"{output_base.name}_drafts.jsonl")
    review_path = output_base.with_name(f"{output_base.name}_review.csv")
    write_jsonl(jsonl_path, records)
    write_review_csv(review_path, records)

    print(
        json.dumps(
            {
                "input_rows": len(rows),
                "apply": args.apply,
                "created": sum(1 for record in records if (record.get("shopify_result") or {}).get("ok")),
                "drafts_jsonl": str(jsonl_path),
                "review_csv": str(review_path),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
