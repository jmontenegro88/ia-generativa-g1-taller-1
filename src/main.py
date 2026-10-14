from __future__ import annotations

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
from src.knowledge_base import (
    KnowledgeBase,
    format_knowledge_context,
    knowledge_sources,
)
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
knowledge_base = KnowledgeBase()


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


def local_return_response(sources):
    reason = "No puedo confirmar automáticamente la elegibilidad; la política recuperada requiere revisión humana."
    return ReturnEvaluationResponse(
        es_elegible=False,
        motivo=reason,
        pasos_siguientes=["Solicitar a un agente que revise la política y los datos del producto."],
        requiere_agente=True,
        respuesta_cliente=reason,
        fuentes=sources,
    )


def local_product_response(product, sources):
    return ProductInfoResponse(
        encontrado=True,
        nombre=product["name"],
        categoria=product.get("category"),
        precio=product.get("price"),
        condicion=product.get("condition"),
        personalizable=bool(product.get("custom", False)),
        mensaje_cliente=(
            f"{product['name']}: categoría {product.get('category', 'no especificada')}; "
            f"precio {product.get('price', 'no especificado')}; "
            f"condición {product.get('condition', 'no especificada')}."
        ),
        requiere_agente=False,
        fuentes=sources,
    )


def local_policy_response(context: str, sources):
    if context:
        answer = (
            "La generación automática no está disponible. Estos son los fragmentos "
            f"recuperados para responder la consulta: {context}"
        )
    else:
        answer = "No se recuperó una regla aplicable; un agente debe revisar la consulta."
    return PolicyResponse(
        respuesta=answer,
        regla_aplicada=None,
        fuentes=sources,
        requiere_agente=True,
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

    policy_query = (
        f"Evaluar devolución: {product['name']}; categoría: {query.category or product.get('category')}; "
        f"condición: {query.condition}; días desde entrega: {query.received_days_ago}; "
        f"motivo: {query.reason or 'no especificado'}."
    )
    policy_documents = knowledge_base.search(
        policy_query,
        document_type="politica",
        category="devoluciones",
    )
    policy_context = format_knowledge_context(policy_documents)
    sources = knowledge_sources(policy_documents)
    if not any(source.startswith("data/productos.json") for source in sources):
        sources.append("data/productos.json")

    if not policy_documents:
        response = local_return_response(sources)
        response.motivo = "No se recuperó la política vigente; no se puede confirmar la elegibilidad."
        response.respuesta_cliente = response.motivo
        mode = "human_escalation"
    else:
        prompt = build_return_prompt(policy_context, product, query.model_dump_json())
        result = openai_client.generate(
            prompt,
            schema=ReturnEvaluationResponse.model_json_schema(),
            schema_name="return_evaluation_response",
        )
        if result.get("fallback"):
            response = local_return_response(sources)
            mode = "local_fallback"
        else:
            response = ReturnEvaluationResponse.model_validate(result["data"])
            mode = "openai"
    response.fuentes = sources
    return {
        "product": product,
        "query": query.model_dump(),
        "response": response.model_dump(),
        "mode": mode,
    }


@app.post("/api/products/search")
def product_search(query: ProductSearchQuery):
    products = load_products()
    knowledge_documents = []
    product_query = query.query or query.product_name
    semantic_match = False
    if query.product_name:
        product = find_product_by_name(products, query.product_name)
        if product is not None:
            candidate_products = [product]
        else:
            semantic_match = True
            candidate_products = products
            product_query = query.product_name
    elif query.category:
        candidate_products = find_products_by_category(products, query.category)
        if not candidate_products:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "categoria": query.category,
                "mensaje_cliente": "No encontré productos para esa categoría.",
                "requiere_agente": False,
            })
    elif query.query:
        exact_or_contained_product = next(
            (
                item
                for item in products
                if query.query.casefold() in item["name"].casefold()
            ),
            None,
        )
        if exact_or_contained_product:
            candidate_products = [exact_or_contained_product]
        else:
            semantic_match = True
            candidate_products = products
            product_query = query.query
    else:
        raise HTTPException(status_code=400, detail={
            "encontrado": False,
            "mensaje_cliente": "Debe indicar un nombre, una categoría o un texto para buscar el producto.",
            "requiere_agente": False,
        })

    if semantic_match:
        knowledge_documents = knowledge_base.search(
            product_query or "",
            document_type="producto",
            k=len(products),
        )
        if not knowledge_documents:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "nombre": product_query,
                "mensaje_cliente": "No fue posible identificar un producto relacionado en el catálogo con esa búsqueda.",
                "requiere_agente": False,
            })
    else:
        knowledge_documents = knowledge_base.search(
            candidate_products[0]["name"],
            document_type="producto",
            k=len(products),
        )

    candidate_skus = {str(item["sku"]) for item in candidate_products}
    knowledge_documents = [
        document
        for document in knowledge_documents
        if str(document.metadata.get("sku")) in candidate_skus
    ]
    ordered_candidate_products = [
        item
        for item in products
        if str(item["sku"]) in candidate_skus
    ]
    sources_by_sku = {
        str(item["sku"]): f"data/productos.json (SKU {item['sku']})"
        for item in ordered_candidate_products
    }
    prompt = build_product_prompt(
        ordered_candidate_products,
        query.model_dump_json(),
    )
    result = openai_client.generate(
        prompt,
        schema=ProductInfoResponse.model_json_schema(),
        schema_name="product_info_response",
    )
    if result.get("fallback"):
        if semantic_match or len(ordered_candidate_products) > 1:
            raise HTTPException(
                status_code=503,
                detail={
                    "mensaje_cliente": (
                        "No se pudo seleccionar un producto del catálogo con suficiente "
                        "confianza en este momento. Intenta nuevamente o solicita ayuda a un agente."
                    ),
                    "requiere_agente": True,
                },
            )
        context_product = ordered_candidate_products[0]
        selected_sku = str(context_product["sku"])
        response = local_product_response(
            context_product,
            [sources_by_sku[selected_sku]],
        )
        mode = "local_fallback"
    else:
        response = ProductInfoResponse.model_validate(result["data"])
        mode = "openai"
        if not response.encontrado:
            raise HTTPException(status_code=404, detail={
                "encontrado": False,
                "nombre": product_query or query.category or query.product_name,
                "mensaje_cliente": response.mensaje_cliente,
                "requiere_agente": response.requiere_agente,
            })
        context_product = next(
            (
                item
                for item in ordered_candidate_products
                if item["name"].casefold() == response.nombre.strip().casefold()
            ),
            None,
        )
        if context_product is None:
            raise HTTPException(
                status_code=502,
                detail="El modelo seleccionó un producto que no está entre los candidatos del catálogo.",
            )
        response.nombre = context_product["name"]
        response.categoria = context_product.get("category")
        response.precio = context_product.get("price")
        response.condicion = context_product.get("condition")
        response.personalizable = bool(context_product.get("custom", False))
        sources = [sources_by_sku[str(context_product["sku"])]]
        knowledge_documents = [
            document
            for document in knowledge_documents
            if str(document.metadata.get("sku")) == str(context_product["sku"])
        ]
        sources = knowledge_sources(knowledge_documents) or sources
    response.fuentes = sources
    return {
        "product": context_product if response.encontrado else None,
        "response": response.model_dump(),
        "mode": mode,
    }


@app.post("/api/policies/answer")
def policy_answer(query: PolicyQuery):
    policy_documents = knowledge_base.search(
        query.question,
        document_type="politica",
        category=query.category,
    )
    policy_context = format_knowledge_context(policy_documents)
    sources = knowledge_sources(policy_documents)
    if not policy_documents:
        response = local_policy_response("", sources)
        mode = "human_escalation"
        return {
            "query": query.model_dump(),
            "response": response.model_dump(),
            "mode": mode,
        }

    prompt = build_policy_prompt(policy_context, query.question, query.category)
    result = openai_client.generate(
        prompt,
        schema=PolicyResponse.model_json_schema(),
        schema_name="policy_response",
    )
    if result.get("fallback"):
        response = local_policy_response(policy_context, sources)
        mode = "local_fallback"
    else:
        response = PolicyResponse.model_validate(result["data"])
        mode = "openai"
    response.fuentes = sources
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
