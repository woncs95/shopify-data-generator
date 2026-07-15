import csv
import json
import sys
import urllib.request
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shopify_data_generator.paths import DATA_DIR, ENV_FILE


API_VERSION = "2025-10"


PRODUCT_FIELD_DETAILS_QUERY = """
query ProductFieldDetails {
  __type(name: "Product") {
    fields(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
      args {
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
              }
            }
          }
        }
      }
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


TYPE_DETAILS_QUERY = """
query TypeDetails($typeName: String!) {
  __type(name: $typeName) {
    name
    kind
    description
    enumValues(includeDeprecated: true) {
      name
      description
      isDeprecated
      deprecationReason
    }
    fields(includeDeprecated: true) {
      name
      description
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
            }
          }
        }
      }
      args {
        name
        type {
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


def format_args(args: list[dict] | None) -> str:
    if not args:
        return ""
    return "; ".join(
        f"{arg['name']}: {graphql_type_name(arg.get('type'))}"
        for arg in args
    )


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class ShopifySchemaClient:
    def __init__(self, host: str, token: str) -> None:
        self.host = host
        self.token = token

    def query(self, query: str, variables: dict | None = None) -> dict:
        payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        request = urllib.request.Request(
            f"https://{self.host}/admin/api/{API_VERSION}/graphql.json",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self.token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("errors"):
            raise RuntimeError(json.dumps(data["errors"], indent=2))
        return data["data"]

    @lru_cache(maxsize=None)
    def type_details(self, type_name: str) -> dict:
        return self.query(TYPE_DETAILS_QUERY, {"typeName": type_name}).get("__type") or {}


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    env_path = ENV_FILE
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
    client = ShopifySchemaClient(host, token)
    product_fields = client.query(PRODUCT_FIELD_DETAILS_QUERY)["__type"]["fields"]

    field_rows = []
    nested_rows = []
    queryable_path_rows = []
    enum_rows = []

    for field in sorted(product_fields, key=lambda item: item["name"]):
        kind, named_type = unwrap_type(field.get("type"))
        args = field.get("args") or []
        field_rows.append(
            {
                "column_name": field["name"],
                "graphQL_type": graphql_type_name(field.get("type")),
                "named_type": named_type,
                "type_kind": kind,
                "arguments": format_args(args),
                "deprecated": bool(field.get("isDeprecated")),
                "deprecation_reason": field.get("deprecationReason") or "",
                "description": field.get("description") or "",
            }
        )

        if kind in {"SCALAR", "ENUM"}:
            queryable_path_rows.append(
                {
                    "product_column": field["name"],
                    "query_path": field["name"],
                    "value_type": named_type,
                    "value_kind": kind,
                    "arguments_needed": format_args(args),
                    "description": field.get("description") or "",
                }
            )

        if kind == "ENUM":
            type_details = client.type_details(named_type)
            for value in type_details.get("enumValues") or []:
                enum_rows.append(
                    {
                        "type_name": named_type,
                        "product_column": field["name"],
                        "enum_value": value["name"],
                        "deprecated": bool(value.get("isDeprecated")),
                        "deprecation_reason": value.get("deprecationReason") or "",
                        "description": value.get("description") or "",
                    }
                )

        if kind not in {"OBJECT", "INTERFACE"} or not named_type:
            continue

        type_details = client.type_details(named_type)
        nested_fields = type_details.get("fields") or []
        for nested_field in sorted(nested_fields, key=lambda item: item["name"]):
            nested_kind, nested_named_type = unwrap_type(nested_field.get("type"))
            nested_rows.append(
                {
                    "product_column": field["name"],
                    "product_column_type": named_type,
                    "nested_field": nested_field["name"],
                    "nested_field_type": graphql_type_name(nested_field.get("type")),
                    "nested_named_type": nested_named_type,
                    "nested_type_kind": nested_kind,
                    "nested_arguments": format_args(nested_field.get("args") or []),
                    "nested_deprecated": bool(nested_field.get("isDeprecated")),
                    "nested_deprecation_reason": nested_field.get("deprecationReason") or "",
                    "nested_description": nested_field.get("description") or "",
                }
            )

        if named_type.endswith("Connection"):
            connection_nodes = next(
                (nested for nested in nested_fields if nested.get("name") == "nodes"),
                None,
            )
            _, node_type = unwrap_type(connection_nodes.get("type") if connection_nodes else None)
            node_details = client.type_details(node_type) if node_type else {}
            for node_field in sorted(node_details.get("fields") or [], key=lambda item: item["name"]):
                node_kind, node_named_type = unwrap_type(node_field.get("type"))
                queryable_path_rows.append(
                    {
                        "product_column": field["name"],
                        "query_path": f"{field['name']}.nodes.{node_field['name']}",
                        "value_type": graphql_type_name(node_field.get("type")),
                        "value_kind": node_kind,
                        "arguments_needed": format_args(args + (node_field.get("args") or [])),
                        "description": node_field.get("description") or "",
                    }
                )
        else:
            for nested_field in sorted(nested_fields, key=lambda item: item["name"]):
                nested_kind, _ = unwrap_type(nested_field.get("type"))
                queryable_path_rows.append(
                    {
                        "product_column": field["name"],
                        "query_path": f"{field['name']}.{nested_field['name']}",
                        "value_type": graphql_type_name(nested_field.get("type")),
                        "value_kind": nested_kind,
                        "arguments_needed": format_args(args + (nested_field.get("args") or [])),
                        "description": nested_field.get("description") or "",
                    }
                )

    details_path = DATA_DIR / "shopify_product_field_details.csv"
    nested_path = DATA_DIR / "shopify_product_nested_fields.csv"
    queryable_paths_path = DATA_DIR / "shopify_product_queryable_paths.csv"
    enum_values_path = DATA_DIR / "shopify_product_enum_values.csv"

    write_csv(
        details_path,
        field_rows,
        [
            "column_name",
            "graphQL_type",
            "named_type",
            "type_kind",
            "arguments",
            "deprecated",
            "deprecation_reason",
            "description",
        ],
    )
    write_csv(
        nested_path,
        nested_rows,
        [
            "product_column",
            "product_column_type",
            "nested_field",
            "nested_field_type",
            "nested_named_type",
            "nested_type_kind",
            "nested_arguments",
            "nested_deprecated",
            "nested_deprecation_reason",
            "nested_description",
        ],
    )
    write_csv(
        queryable_paths_path,
        queryable_path_rows,
        [
            "product_column",
            "query_path",
            "value_type",
            "value_kind",
            "arguments_needed",
            "description",
        ],
    )
    write_csv(
        enum_values_path,
        enum_rows,
        [
            "type_name",
            "product_column",
            "enum_value",
            "deprecated",
            "deprecation_reason",
            "description",
        ],
    )

    print(
        json.dumps(
            {
                "store": host,
                "api_version": API_VERSION,
                "product_field_count": len(field_rows),
                "nested_field_count": len(nested_rows),
                "queryable_path_count": len(queryable_path_rows),
                "enum_value_count": len(enum_rows),
                "outputs": {
                    "field_details": str(details_path),
                    "nested_fields": str(nested_path),
                    "queryable_paths": str(queryable_paths_path),
                    "enum_values": str(enum_values_path),
                },
                "sample_queryable_paths": [
                    row["query_path"]
                    for row in queryable_path_rows
                    if row["product_column"] in {"title", "status", "variants", "seo"}
                ][:20],
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
