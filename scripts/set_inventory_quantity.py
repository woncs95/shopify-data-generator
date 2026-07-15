import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from shopify_data_generator.paths import ENV_FILE


API_VERSION = "2025-10"


SET_INVENTORY_MUTATION = """
mutation SetInventory($input: InventorySetQuantitiesInput!) {
  inventorySetQuantities(input: $input) {
    inventoryAdjustmentGroup {
      createdAt
      reason
      referenceDocumentUri
    }
    userErrors {
      field
      message
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


def graphql(host: str, token: str, query: str, variables: dict) -> dict:
    request = urllib.request.Request(
        f"https://{host}/admin/api/{API_VERSION}/graphql.json",
        data=json.dumps({"query": query, "variables": variables}).encode("utf-8"),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set inventory quantity for an existing Shopify inventory item.")
    parser.add_argument("--inventory-item-id", required=True)
    parser.add_argument("--location-id", required=True)
    parser.add_argument("--quantity", type=int, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    env = load_dotenv(ENV_FILE)
    token = env.get("SHOPIFY_API", "").strip()
    store = env.get("SHOPIFY_STORE_NAME", "").strip()
    if not token or not store:
        raise SystemExit("SHOPIFY_API and SHOPIFY_STORE_NAME are required in .env")

    reference_document_uri = (
        "shopify-registration-ui://inventory-adjustment/"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )
    payload = {
        "input": {
            "ignoreCompareQuantity": True,
            "name": "available",
            "reason": "correction",
            "referenceDocumentUri": reference_document_uri,
            "quantities": [
                {
                    "inventoryItemId": args.inventory_item_id,
                    "locationId": args.location_id,
                    "quantity": args.quantity,
                    "compareQuantity": None,
                }
            ],
        }
    }
    result = graphql(
        normalize_shopify_host(store),
        token,
        SET_INVENTORY_MUTATION,
        payload,
    )["inventorySetQuantities"]
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
