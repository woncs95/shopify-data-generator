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
from shopify_data_generator.metafield_saving import load_definitions


API_VERSION = "2025-10"


METAFIELD_DEFINITIONS_QUERY = """
query ProductMetafieldDefinitions($first: Int!, $after: String) {
  metafieldDefinitions(first: $first, after: $after, ownerType: PRODUCT) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes {
      id
      name
      namespace
      key
      description
      type {
        name
      }
      access {
        admin
        storefront
      }
      validations {
        name
        value
      }
    }
  }
}
"""


LOCATIONS_QUERY = """
query ActiveLocations($first: Int!) {
  locations(first: $first) {
    nodes {
      id
      name
      isActive
      fulfillsOnlineOrders
      hasActiveInventory
      shipsInventory
    }
  }
}
"""


PRODUCT_TAGS_QUERY = """
query ProductTags($first: Int!, $after: String) {
  productTags(first: $first, after: $after) {
    pageInfo {
      hasNextPage
      endCursor
    }
    nodes
  }
}
"""


PRODUCT_CATALOG_QUERY = """
query ProductCatalog($first: Int!, $after: String) {
  products(first: $first, after: $after) {
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


def shopify_graphql(host: str, token: str, query: str, variables: dict) -> dict:
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


def fetch_paginated(host: str, token: str, query: str, connection_name: str) -> list:
    after = None
    nodes = []
    while True:
        data = shopify_graphql(host, token, query, {"first": 250, "after": after})
        connection = data[connection_name]
        nodes.extend(connection.get("nodes") or [])
        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            break
        after = page_info["endCursor"]
    return nodes


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
    metafields = fetch_paginated(host, token, METAFIELD_DEFINITIONS_QUERY, "metafieldDefinitions")
    constraints = load_definitions(lambda q, v: shopify_graphql(host, token, q, v))
    tags = fetch_paginated(host, token, PRODUCT_TAGS_QUERY, "productTags")
    products = fetch_paginated(host, token, PRODUCT_CATALOG_QUERY, "products")
    locations = shopify_graphql(host, token, LOCATIONS_QUERY, {"first": 50})["locations"]["nodes"]

    metafield_rows = []
    for item in sorted(metafields, key=lambda value: (value["namespace"], value["key"])):
        metafield_rows.append(
            {
                "id": item["id"],
                "name": item.get("name") or "",
                "namespace": item["namespace"],
                "key": item["key"],
                "type": (item.get("type") or {}).get("name") or "",
                "admin_access": (item.get("access") or {}).get("admin") or "",
                "storefront_access": (item.get("access") or {}).get("storefront") or "",
                "validations": json.dumps(item.get("validations") or [], ensure_ascii=False),
                "constraints": json.dumps(constraints[f"{item['namespace']}.{item['key']}"].get("constraints"), ensure_ascii=False),
                "description": item.get("description") or "",
            }
        )

    location_rows = [
        {
            "id": item["id"],
            "name": item["name"],
            "isActive": item["isActive"],
            "fulfillsOnlineOrders": item["fulfillsOnlineOrders"],
            "hasActiveInventory": item["hasActiveInventory"],
            "shipsInventory": item["shipsInventory"],
        }
        for item in locations
    ]
    tag_rows = [{"tag": tag} for tag in sorted(set(tags), key=str.lower)]
    product_rows = [
        {
            "id": item["id"],
            "title": item["title"],
            "handle": item["handle"],
            "vendor": item.get("vendor") or "",
            "status": item.get("status") or "",
            "productType": item.get("productType") or "",
        }
        for item in sorted(products, key=lambda value: value["title"].lower())
    ]

    metafields_path = DATA_DIR / "shopify_product_metafield_definitions.csv"
    locations_path = DATA_DIR / "shopify_locations.csv"
    tags_path = DATA_DIR / "shopify_product_tags.csv"
    products_path = DATA_DIR / "shopify_product_catalog.csv"
    context_path = DATA_DIR / "shopify_registration_context.json"

    write_csv(
        metafields_path,
        metafield_rows,
        [
            "id",
            "name",
            "namespace",
            "key",
            "type",
            "admin_access",
            "storefront_access",
            "validations",
            "constraints",
            "description",
        ],
    )
    write_csv(
        locations_path,
        location_rows,
        [
            "id",
            "name",
            "isActive",
            "fulfillsOnlineOrders",
            "hasActiveInventory",
            "shipsInventory",
        ],
    )
    write_csv(tags_path, tag_rows, ["tag"])
    write_csv(products_path, product_rows, ["id", "title", "handle", "vendor", "status", "productType"])

    context = {
        "store": host,
        "api_version": API_VERSION,
        "metafield_definition_count": len(metafield_rows),
        "location_count": len(location_rows),
        "tag_count": len(tag_rows),
        "product_count": len(product_rows),
        "recommended_location_id": location_rows[0]["id"] if len(location_rows) == 1 else "",
        "recommended_location_name": location_rows[0]["name"] if len(location_rows) == 1 else "",
        "outputs": {
            "metafields": str(metafields_path),
            "locations": str(locations_path),
            "tags": str(tags_path),
            "products": str(products_path),
        },
    }
    context_path.write_text(json.dumps(context, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(context, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
