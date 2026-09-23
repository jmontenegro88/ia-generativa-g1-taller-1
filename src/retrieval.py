from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from src.config import DATA_DIR


def load_orders() -> List[Dict[str, Any]]:
    file_path = DATA_DIR / "pedidos.json"
    with file_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_products() -> List[Dict[str, Any]]:
    file_path = DATA_DIR / "productos.json"
    with file_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def find_order_by_tracking(orders: Iterable[Dict[str, Any]], tracking_number: str) -> Optional[Dict[str, Any]]:
    normalized = (tracking_number or "").strip().upper()
    for order in orders:
        if str(order.get("tracking_number", "")).strip().upper() == normalized:
            return order
    return None


def get_order_context(order: Dict[str, Any]) -> Dict[str, Any]:
    context = {
        "tracking_number": order.get("tracking_number"),
        "order_id": order.get("order_id"),
        "status": order.get("status"),
        "estimated_delivery": order.get("estimated_delivery"),
        "carrier": order.get("carrier"),
        "tracking_url": order.get("tracking_url"),
        "customer_id": order.get("customer_id"),
        "source": order.get("source", "sistema_pedidos_demo"),
        "updated_at": order.get("updated_at"),
        "product_name": order.get("product_name"),
    }
    return context


def find_product_by_name(products: Iterable[Dict[str, Any]], product_name: str) -> Optional[Dict[str, Any]]:
    search = (product_name or "").strip().lower()
    for product in products:
        if str(product.get("name", "")).strip().lower() == search:
            return product
    return None


def find_products_by_category(products: Iterable[Dict[str, Any]], category: str) -> List[Dict[str, Any]]:
    if not category:
        return list(products)
    search = (category or "").strip().lower()
    matches = []
    for product in products:
        if str(product.get("category", "")).strip().lower() == search:
            matches.append(product)
    return matches
