import csv
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


API_VERSION = "2025-10"


PRODUCT_FIELDS_QUERY = """
query ProductFields {
  __type(name: "Product") {
    fields(includeDeprecated: true) {
      name
      isDeprecated
      deprecationReason
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
      args {
        name
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


def main() -> None:
    root = Path.cwd()
    env_path = root / ".env"
    if not env_path.exists():
        raise SystemExit(".env file not found")

    env = load_dotenv(env_path)
    token = env.get("SHOPIFY_API", "").strip()
    store = env.get("SHOPIFY_STORE_NAME", "").strip()
    if not token:
        raise SystemExit("SHOPIFY_API is missing from .env")
    if not store:
        raise SystemExit("SHOPIFY_STORE_NAME is missing from .env")

    host = normalize_shopify_host(store)
    payload = json.dumps({"query": PRODUCT_FIELDS_QUERY}).encode("utf-8")
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
        raise SystemExit(json.dumps(data["errors"], indent=2))

    raw_fields = data.get("data", {}).get("__type", {}).get("fields") or []
    fields = [
        {
            "column_name": field["name"],
            "graphQL_type": graphql_type_name(field.get("type")),
            "has_arguments": bool(field.get("args")),
            "deprecated": bool(field.get("isDeprecated")),
            "deprecation_reason": field.get("deprecationReason") or "",
        }
        for field in sorted(raw_fields, key=lambda item: item["name"])
    ]

    out_path = root / "shopify_product_column_names.csv"
    with out_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "column_name",
                "graphQL_type",
                "has_arguments",
                "deprecated",
                "deprecation_reason",
            ],
        )
        writer.writeheader()
        writer.writerows(fields)

    print(
        json.dumps(
            {
                "store": host,
                "api_version": API_VERSION,
                "product_field_count": len(fields),
                "output_path": str(out_path),
                "column_names": [field["column_name"] for field in fields],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
