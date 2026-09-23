from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException

from src.models import (
    OrderStatusQuery,
    OrderStatusResponse,
    PolicyQuery,
    PolicyResponse,
    ProductInfoResponse,
    ProductSearchQuery,
    ReturnEvaluationResponse,
    ReturnQuery,
    TriageQuery,
    TriageResponse,
)
from src.openai_client import OpenAIClient
from src.prompts import (
    build_order_status_prompt,
    build_policy_prompt,
    build_product_prompt,
    build_return_prompt,
    build_triage_prompt,
)
from src.retrieval import (
    find_order_by_tracking,
    find_product_by_name,
    find_products_by_category,
    load_orders,
    load_products,
)

app = FastAPI(title="EcoMarket AI Assistant", version="0.1.0")
openai_client = OpenAIClient()


def local_order_response(order):
    status = order["status"]
    message = f"Tu pedido {order['tracking_number']} está en estado: {status}."
    if status == "Retrasado":
        message = f"Lamentamos el retraso. Tu pedido {order['tracking_number']} está retrasado."
    return OrderStatusResponse(
        numero_seguimiento=order["tracking_number"],
        estado=status,
        fecha_estimada=order.get("estimated_delivery"),
        transportadora=order.get("carrier"),
        enlace_rastreo=order.get("tracking_url"),
        mensaje_cliente=message,
        fuentes=[order.get("source", "sistema_pedidos_demo")],
    )


def local_return_response(product, query):
    category = (query.category or "").lower()
    condition = (query.condition or "").lower()
    days = query.received_days_ago
    is_hygiene_open = category == "higiene" and condition == "abierto"
    is_custom = bool(query.custom or product.get("custom", False))
    eligible = days is not None and days <= 30 and not is_hygiene_open and not is_custom
    if eligible:
        reason = "El producto está dentro del plazo de 30 días y no presenta una restricción registrada."
        next_steps = ["Solicitar la devolución desde el canal de soporte.", "Enviar el producto para revisión."]
    else:
        reason = "El producto no cumple las condiciones disponibles para una devolución automática."
        next_steps = ["Revisar el caso con un agente de EcoMarket."]
    return ReturnEvaluationResponse(
        es_elegible=eligible,
        motivo=reason,
        pasos_siguientes=next_steps,
        informacion_faltante=[] if days is not None else ["received_days_ago"],
        requiere_agente=not eligible,
        respuesta_cliente=reason,
        fuentes=["politica_devoluciones_demo", "catalogo_demo"],
    )


def local_product_response(product, customer_message: str):
    return ProductInfoResponse(
        encontrado=True,
        nombre=product["name"],
        categoria=product.get("category"),
        precio=product.get("price"),
        condicion=product.get("condition"),
        personalizable=bool(product.get("custom", False)),
        mensaje_cliente=f"He revisado la información del producto {product['name']}. Puedes consultar su categoría, precio y condiciones generales.",
        requiere_agente=False,
        fuentes=["catalogo_demo"],
    )


def local_policy_response(question: str, category: str | None = None):
    return PolicyResponse(
        respuesta="La política disponible indica que los productos nuevos tienen devoluciones dentro de 30 días, pero los productos de higiene abiertos o personalizados requieren revisión humana.",
        regla_aplicada="devoluciones_y_excepciones",
        fuentes=["politica_devoluciones_demo"],
        requiere_agente=category is not None and category.lower() in {"higiene", "personalizado"},
    )


def local_triage_response(issue_type: str, customer_message: str, order_id: str | None = None, tracking_number: str | None = None, category: str | None = None):
    ticket_type = (issue_type or "general").lower()
    if ticket_type in {"pedido", "tracking", "envio", "delivery"}:
        category_label = "pedido"
        priority = "media"
        summary = "La solicitud parece relacionada con el estado o entrega del pedido."
        steps = ["Verificar número de seguimiento.", "Consultar el estado operativo del pedido.", "Responder con la información confirmada."]
    elif ticket_type in {"devolucion", "return", "refund"}:
        category_label = "devolucion"
        priority = "alta"
        summary = "La solicitud requiere revisión de política de devoluciones y puede implicar criterios comerciales."
        steps = ["Confirmar el producto y el plazo.", "Comprobar restricciones de la política.", "Escalar a agente si es un caso especial o ambiguo."]
    else:
        category_label = "general"
        priority = "media"
        summary = "La solicitud es general y puede resolverse con información del catálogo o de políticas."
        steps = ["Confirmar la intención del cliente.", "Buscar el contexto relevante.", "Responder con ayuda o escalar si es necesario."]

    return TriageResponse(
        categoria=category_label,
        prioridad=priority,
        requiere_agente=priority == "alta" or bool(order_id or tracking_number),
        resumen=summary,
        pasos_siguientes=steps,
        fuentes=["clasificacion_demo", "politica_devoluciones_demo"],
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/api/orders/status")
def order_status(query: OrderStatusQuery):
    orders = load_orders()
    order = find_order_by_tracking(orders, query.tracking_number)
    if order is None:
        raise HTTPException(status_code=404, detail={
            "encontrado": False,
            "numero_seguimiento": query.tracking_number,
            "estado": "No encontrado",
            "mensaje_cliente": "No encontré ese número de seguimiento. Verifica el código e intenta nuevamente.",
            "requiere_agente": False,
        })

    prompt = build_order_status_prompt(order, query.tracking_number)
    result = openai_client.generate(
        prompt,
        schema=OrderStatusResponse.model_json_schema(),
        schema_name="order_status_response",
    )
    if result.get("fallback"):
        response = local_order_response(order)
        mode = "local_fallback"
    else:
        response = OrderStatusResponse.model_validate(result["data"])
        mode = "openai"
    return {
        "order": order,
        "response": response.model_dump(),
        "mode": mode,
        "query": query.model_dump(),
    }


@app.post("/api/returns/evaluate")
def return_evaluation(query: ReturnQuery):
    products = load_products()
    product = None
    if query.product_name:
        product = next((item for item in products if item["name"].lower() == query.product_name.lower()), None)
    if product is None:
        raise HTTPException(status_code=404, detail={
            "es_elegible": False,
            "motivo": "No se encontró información del producto solicitado.",
            "informacion_faltante": ["product_name"],
            "requiere_agente": True,
        })

    policy = """Los productos nuevos y sin uso pueden devolverse dentro de los 30 días posteriores a la entrega.
Los productos defectuosos o dañados pueden devolverse dentro de los 30 días, con descripción del problema y evidencia cuando sea posible.
Los productos perecederos no pueden devolverse por razones de seguridad, excepto cuando exista un daño o defecto confirmado al recibirlos.
Los productos de higiene abiertos no pueden devolverse, excepto cuando exista un defecto de fabricación.
Los productos personalizados no pueden devolverse salvo defecto comprobado.
El reembolso se procesa después de recibir y revisar el producto.
Los casos ambiguos o que impliquen una compensación especial deben escalarse a un agente."""
    prompt = build_return_prompt(policy, product, query.model_dump_json())
    result = openai_client.generate(
        prompt,
        schema=ReturnEvaluationResponse.model_json_schema(),
        schema_name="return_evaluation_response",
    )
    if result.get("fallback"):
        response = local_return_response(product, query)
        mode = "local_fallback"
    else:
        response = ReturnEvaluationResponse.model_validate(result["data"])
        mode = "openai"
    return {
        "product": product,
        "query": query.model_dump(),
        "response": response.model_dump(),
        "mode": mode,
    }


@app.post("/api/products/search")
def product_search(query: ProductSearchQuery):
    products = load_products()
    if query.product_name:
        product = find_product_by_name(products, query.product_name)
        if product is None:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "nombre": query.product_name,
                "mensaje_cliente": "No encontré ese producto en el catálogo actual.",
                "requiere_agente": False,
            })
        context_product = product
    elif query.category:
        matches = find_products_by_category(products, query.category)
        if not matches:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "categoria": query.category,
                "mensaje_cliente": "No encontré productos para esa categoría.",
                "requiere_agente": False,
            })
        context_product = matches[0]
    elif query.query:
        product = next((item for item in products if query.query.lower() in item["name"].lower()), None)
        if product is None:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "mensaje_cliente": "No encontré ningún producto que coincida con esa búsqueda.",
                "requiere_agente": False,
            })
        context_product = product
    else:
        raise HTTPException(status_code=400, detail={
            "encontrado": False,
            "mensaje_cliente": "Debe indicar un nombre, una categoría o un texto para buscar el producto.",
            "requiere_agente": False,
        })

    prompt = build_product_prompt(context_product, query.model_dump_json())
    result = openai_client.generate(
        prompt,
        schema=ProductInfoResponse.model_json_schema(),
        schema_name="product_info_response",
    )
    if result.get("fallback"):
        response = local_product_response(context_product, query.model_dump_json())
        mode = "local_fallback"
    else:
        response = ProductInfoResponse.model_validate(result["data"])
        mode = "openai"
    return {
        "product": context_product,
        "response": response.model_dump(),
        "mode": mode,
    }


@app.post("/api/policies/answer")
def policy_answer(query: PolicyQuery):
    policy_path = Path(__file__).resolve().parent.parent / "data" / "politica_devoluciones.md"
    policy_text = policy_path.read_text(encoding="utf-8") if policy_path.exists() else "No hay política disponible."
    prompt = build_policy_prompt(policy_text, query.question, query.category)
    result = openai_client.generate(
        prompt,
        schema=PolicyResponse.model_json_schema(),
        schema_name="policy_response",
    )
    if result.get("fallback"):
        response = local_policy_response(query.question, query.category)
        mode = "local_fallback"
    else:
        response = PolicyResponse.model_validate(result["data"])
        mode = "openai"
    return {
        "query": query.model_dump(),
        "response": response.model_dump(),
        "mode": mode,
    }


@app.post("/api/support/triage")
def support_triage(query: TriageQuery):
    prompt = build_triage_prompt(
        issue_type=query.issue_type,
        customer_message=query.customer_message,
        order_id=query.order_id,
        tracking_number=query.tracking_number,
        category=query.category,
    )
    result = openai_client.generate(
        prompt,
        schema=TriageResponse.model_json_schema(),
        schema_name="triage_response",
    )
    if result.get("fallback"):
        response = local_triage_response(
            query.issue_type,
            query.customer_message,
            query.order_id,
            query.tracking_number,
            query.category,
        )
        mode = "local_fallback"
    else:
        response = TriageResponse.model_validate(result["data"])
        mode = "openai"
    return {
        "query": query.model_dump(),
        "response": response.model_dump(),
        "mode": mode,
    }


@app.get("/api/metrics/summary")
def metrics_summary():
    return {
        "metricas_clave": {
            "tiempo_promedio_primera_respuesta_seg": 18.4,
            "tasa_resolucion_automatica_pct": 86.0,
            "tasa_escalamiento_pct": 14.0,
            "tasa_json_valido_pct": 98.5,
            "tasa_recontacto_pct": 7.2,
            "costo_promedio_por_consulta_usd": 0.04,
        },
        "objetivo": "Monitorear calidad, escalamiento y costo de la atención automatizada.",
        "fuentes": ["documentacion_taller", "operacion_demo"],
    }
