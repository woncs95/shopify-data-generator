import csv
import json
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shopify_data_generator.paths import DATA_DIR, ENV_FILE


API_VERSION = "2025-10"

INPUT_OBJECTS = [
    "ProductCreateInput",
    "ProductVariantsBulkInput",
    "InventoryItemInput",
    "InventoryItemMeasurementInput",
    "InventoryLevelInput",
    "MetafieldInput",
    "CreateMediaInput",
    "OptionCreateInput",
    "OptionValueCreateInput",
    "ProductClaimOwnershipInput",
    "SEOInput",
    "UnitPriceMeasurementInput",
    "VariantOptionValueInput",
]

INPUT_FIELDS_QUERY = """
query InputFields($typeName: String!) {
  __type(name: $typeName) {
    name
    kind
    inputFields {
      name
      description
      defaultValue
      type {
        kind
        name
        ofType {
          kind
          name
          ofType {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
  }
}
"""


def load_dotenv(path: Path) -> dict[str, str]:
    values = {}
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


def graphql_type_name(type_info: dict | None) -> str:
    if not type_info:
        return ""
    kind = type_info.get("kind")
    if kind == "NON_NULL":
        return f"{graphql_type_name(type_info.get('ofType'))}!"
    if kind == "LIST":
        return f"[{graphql_type_name(type_info.get('ofType'))}]"
    return type_info.get("name") or kind or ""


def unwrap_type(type_info: dict | None) -> tuple[str, str]:
    current = type_info
    while current and current.get("kind") in {"NON_NULL", "LIST"}:
        current = current.get("ofType")
    if not current:
        return "", ""
    return current.get("kind") or "", current.get("name") or ""


def query_shopify(host: str, token: str, query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        f"https://{host}/admin/api/{API_VERSION}/graphql.json",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": token,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"], indent=2))
    return data["data"]


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env = load_dotenv(ENV_FILE)
    token = env.get("SHOPIFY_API", "").strip()
    store = env.get("SHOPIFY_STORE_NAME", "").strip()
    if not token:
        raise SystemExit("SHOPIFY_API is missing from .env")
    if not store:
        raise SystemExit("SHOPIFY_STORE_NAME is missing from .env")

    host = normalize_shopify_host(store)
    rows = []
    for input_object in INPUT_OBJECTS:
        type_data = query_shopify(host, token, INPUT_FIELDS_QUERY, {"typeName": input_object}).get("__type")
        if not type_data:
            continue
        for field in sorted(type_data.get("inputFields") or [], key=lambda item: item["name"]):
            kind, named_type = unwrap_type(field.get("type"))
            rows.append(
                {
                    "input_object": input_object,
                    "column_name": field["name"],
                    "csv_header_suggestion": f"{input_object}.{field['name']}",
                    "graphQL_type": graphql_type_name(field.get("type")),
                    "named_type": named_type,
                    "type_kind": kind,
                    "default_value": field.get("defaultValue") or "",
                    "description": field.get("description") or "",
                }
            )

    out_path = DATA_DIR / "shopify_writable_product_columns.csv"
    with out_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "input_object",
                "column_name",
                "csv_header_suggestion",
                "graphQL_type",
                "named_type",
                "type_kind",
                "default_value",
                "description",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(
        json.dumps(
            {
                "store": host,
                "api_version": API_VERSION,
                "writable_field_count": len(rows),
                "output_path": str(out_path),
                "input_objects": INPUT_OBJECTS,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
