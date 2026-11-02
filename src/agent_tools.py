"""Herramientas del agente de devoluciones de EcoMarket.

Hay dos capas:

* ``ReturnService``: lógica de negocio pura (simula los sistemas externos de
  pedidos, logística inversa y mesa de ayuda). Es determinista y se prueba sin
  LLM. Las reglas de elegibilidad están codificadas a partir de
  ``data/politica_devoluciones.pdf`` y ``data/politica_garantias.json``: el LLM
  nunca decide por sí mismo si una devolución procede.
* ``AgentToolbox``: envuelve el servicio para un turno de conversación. Inyecta
  el contexto de sesión (cliente autenticado), registra cada llamada en la
  bitácora y expone las funciones como herramientas LangChain.

Todas las herramientas devuelven un diccionario con la misma envoltura:
``{"ok": bool, "codigo": str, "mensaje": str, ...}``. Los errores esperados
(pedido inexistente, formato inválido, no autorizado, no elegible) se devuelven
como datos, no como excepciones, para que el agente pueda explicarlos al
cliente.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
from datetime import date, timedelta
from typing import Any, Callable, Literal, Optional

from pydantic import BaseModel, Field

from src.action_log import ActionLogger
from src.config import (
    LABEL_VALIDITY_DAYS,
    RETURN_WINDOW_DAYS,
    WARRANTY_DAYS,
    agent_reference_date,
)
from src.knowledge_base import knowledge_sources
from src.retrieval import find_order_by_tracking, find_product_by_name, load_orders, load_products
from src.return_registry import ReturnRegistry

EstadoProducto = Literal[
    "nuevo_sin_uso",
    "abierto_o_usado",
    "defectuoso",
    "danado_en_envio",
    "desconocido",
]
ESTADOS_PRODUCTO = ("nuevo_sin_uso", "abierto_o_usado", "defectuoso", "danado_en_envio", "desconocido")
ESTADOS_CON_FALLA = {"defectuoso", "danado_en_envio"}
CATEGORIAS_POLITICA = {"devoluciones", "envios", "garantias"}
CATEGORIAS_PERECEDERAS = {"perecederos", "alimentos"}

TRACKING_PATTERN = re.compile(r"^ECO-\d{5}$")
FUENTE_POLITICA = "data/politica_devoluciones.pdf"
FUENTE_GARANTIA = "data/politica_garantias.json"
FUENTE_PEDIDOS = "data/pedidos.json"
FUENTE_CATALOGO = "data/productos.json"

# Casos que, según la política, deben pasar a una persona aunque la regla
# general permita la devolución (compensaciones especiales, seguridad, disputas).
SENSITIVE_PATTERNS = (
    "lesion",
    "herid",
    "quemad",
    "alergi",
    "intoxic",
    "demanda",
    "abogad",
    "legal",
    "denuncia",
    "compensacion",
    "indemniz",
)


def normalize_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def normalize_tracking(tracking_number: str) -> str:
    return (tracking_number or "").strip().upper()


def _result(ok: bool, codigo: str, mensaje: str, **data: Any) -> dict[str, Any]:
    return {"ok": ok, "codigo": codigo, "mensaje": mensaje, **data}


class ReturnService:
    """Sistemas simulados de pedidos, devoluciones y soporte."""

    def __init__(
        self,
        knowledge_base: Any = None,
        registry: ReturnRegistry | None = None,
        today_fn: Callable[[], date] = agent_reference_date,
        orders_loader: Callable[[], list[dict[str, Any]]] = load_orders,
        products_loader: Callable[[], list[dict[str, Any]]] = load_products,
    ) -> None:
        self._knowledge_base = knowledge_base
        self.registry = registry or ReturnRegistry()
        self.today_fn = today_fn
        self.orders_loader = orders_loader
        self.products_loader = products_loader

    @property
    def knowledge_base(self) -> Any:
        # Carga diferida: el modelo de embeddings solo se inicializa si el
        # agente necesita consultar políticas.
        if self._knowledge_base is None:
            from src.knowledge_base import KnowledgeBase

            self._knowledge_base = KnowledgeBase()
        return self._knowledge_base

    # ------------------------------------------------------------------ helpers
    def _lookup_order(
        self, tracking_number: str, customer_id: Optional[str]
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Devuelve (pedido, error). Aplica validación de formato y autorización."""
        tracking = normalize_tracking(tracking_number)
        if not TRACKING_PATTERN.match(tracking):
            return None, _result(
                False,
                "FORMATO_INVALIDO",
                "El número de seguimiento debe tener el formato ECO-12345.",
                numero_seguimiento=tracking_number,
            )
        order = find_order_by_tracking(self.orders_loader(), tracking)
        if order is None:
            return None, _result(
                False,
                "PEDIDO_NO_ENCONTRADO",
                f"No existe un pedido con el número de seguimiento {tracking}.",
                numero_seguimiento=tracking,
            )
        if customer_id and order.get("customer_id") != customer_id.strip().upper():
            # No se revelan datos del pedido a un cliente distinto del titular.
            return None, _result(
                False,
                "NO_AUTORIZADO",
                "El pedido no está asociado al cliente de la sesión actual.",
                numero_seguimiento=tracking,
            )
        return order, None

    def _days_since_delivery(self, order: dict[str, Any]) -> int | None:
        try:
            delivered = date.fromisoformat(str(order.get("estimated_delivery")))
        except ValueError:
            return None
        return (self.today_fn() - delivered).days

    @staticmethod
    def _order_summary(order: dict[str, Any]) -> dict[str, Any]:
        return {
            "numero_seguimiento": order["tracking_number"],
            "id_pedido": order["order_id"],
            "estado": order["status"],
            "fecha_entrega_estimada": order.get("estimated_delivery"),
            "transportadora": order.get("carrier"),
            "enlace_rastreo": order.get("tracking_url"),
            "producto": order.get("product_name"),
        }

    # -------------------------------------------------------------- herramientas
    def consultar_pedido(self, tracking_number: str, customer_id: Optional[str] = None) -> dict[str, Any]:
        order, error = self._lookup_order(tracking_number, customer_id)
        if error:
            return error
        summary = self._order_summary(order)
        if order["status"] == "Entregado":
            summary["dias_desde_entrega"] = self._days_since_delivery(order)
        return _result(
            True,
            "PEDIDO_ENCONTRADO",
            f"Pedido {order['tracking_number']} en estado {order['status']}.",
            pedido=summary,
            fuentes=[FUENTE_PEDIDOS],
        )

    def verificar_elegibilidad(
        self,
        tracking_number: str,
        estado_producto: str = "desconocido",
        motivo: str = "",
        customer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        order, error = self._lookup_order(tracking_number, customer_id)
        if error:
            return error

        estado_producto = estado_producto if estado_producto in ESTADOS_PRODUCTO else "desconocido"
        pedido = self._order_summary(order)
        base = {
            "pedido": pedido,
            "estado_producto": estado_producto,
            "plazo_devolucion_dias": RETURN_WINDOW_DAYS,
            "fuentes": [FUENTE_POLITICA, FUENTE_PEDIDOS],
        }

        def decision(
            resultado: str,
            mensaje: str,
            regla: str,
            *,
            elegible: bool | None,
            pasos: list[str] | None = None,
            requiere_agente: bool = False,
            requiere_evidencia: bool = False,
            faltante: list[str] | None = None,
            **extra: Any,
        ) -> dict[str, Any]:
            codigo = {
                "elegible": "ELEGIBLE",
                "no_elegible": "NO_ELEGIBLE",
                "requiere_revision": "REQUIERE_REVISION",
                "informacion_faltante": "INFORMACION_FALTANTE",
            }[resultado]
            return _result(
                True,
                codigo,
                mensaje,
                decision=resultado,
                elegible=elegible,
                regla_aplicada=regla,
                requiere_agente=requiere_agente,
                requiere_evidencia=requiere_evidencia,
                informacion_faltante=faltante or [],
                pasos_siguientes=pasos or [],
                **base,
                **extra,
            )

        # 1. Casos sensibles: la política exige revisión humana.
        motivo_normalizado = normalize_text(motivo)
        if any(pattern in motivo_normalizado for pattern in SENSITIVE_PATTERNS):
            base["fuentes"].append(FUENTE_GARANTIA)
            return decision(
                "requiere_revision",
                "El caso menciona seguridad, lesiones, una disputa legal o una compensación especial.",
                "Los casos ambiguos, de seguridad o que impliquen compensación especial se escalan a un agente.",
                elegible=None,
                requiere_agente=True,
                pasos=["Escalar a un agente humano con prioridad alta."],
            )

        # 2. Estado operativo del pedido.
        status = order["status"]
        if status == "Devuelto":
            return decision(
                "no_elegible",
                "Este pedido ya figura como devuelto.",
                "Solo se gestionan devoluciones de pedidos entregados y no devueltos.",
                elegible=False,
                pasos=["Si no recibiste el reembolso, un agente puede revisar el estado del proceso."],
            )
        if status == "Cancelado":
            return decision(
                "no_elegible",
                "El pedido fue cancelado, así que no hay un producto entregado que devolver.",
                "Solo se gestionan devoluciones de pedidos entregados.",
                elegible=False,
            )
        if status != "Entregado":
            return decision(
                "no_elegible",
                f"El pedido aún no ha sido entregado (estado: {status}). El plazo de devolución empieza con la entrega.",
                "El plazo de 30 días se cuenta a partir de la entrega.",
                elegible=False,
                pasos=[
                    "Esperar la entrega y solicitar la devolución dentro de los 30 días siguientes.",
                    "Si deseas cancelar el pedido, un agente debe revisarlo.",
                ],
            )

        # 3. Plazo desde la entrega.
        dias = self._days_since_delivery(order)
        if dias is None or dias < 0:
            return decision(
                "requiere_revision",
                "La fecha de entrega registrada es inconsistente; un agente debe verificarla.",
                "Información contradictoria o insuficiente se escala a un agente.",
                elegible=None,
                requiere_agente=True,
            )
        base["dias_desde_entrega"] = dias
        base["dias_restantes_devolucion"] = max(RETURN_WINDOW_DAYS - dias, 0)

        if dias > RETURN_WINDOW_DAYS:
            if estado_producto == "defectuoso" and dias <= WARRANTY_DAYS:
                base["fuentes"].append(FUENTE_GARANTIA)
                return decision(
                    "requiere_revision",
                    f"Han pasado {dias} días desde la entrega: fuera del plazo de devolución, "
                    f"pero dentro de la garantía de {WARRANTY_DAYS} días por defectos de fabricación.",
                    "Garantía de 90 días por defectos de fabricación; un agente revisa la evidencia.",
                    elegible=False,
                    requiere_agente=True,
                    requiere_evidencia=True,
                    pasos=[
                        "Tener a mano el comprobante de compra y fotografías del defecto.",
                        "Un agente revisará el caso de garantía.",
                    ],
                )
            pasos = []
            if dias <= WARRANTY_DAYS:
                pasos.append(
                    f"Si el producto tiene un defecto de fabricación, puede aplicar la garantía de {WARRANTY_DAYS} días."
                )
            return decision(
                "no_elegible",
                f"Han pasado {dias} días desde la entrega y el plazo de devolución es de {RETURN_WINDOW_DAYS} días.",
                "Los productos pueden devolverse dentro de los 30 días posteriores a la entrega.",
                elegible=False,
                pasos=pasos,
            )

        # 4. Producto y categoría.
        product = find_product_by_name(self.products_loader(), order.get("product_name", ""))
        if product is None:
            return decision(
                "requiere_revision",
                "El producto del pedido no aparece en el catálogo; no se puede confirmar su categoría.",
                "Información insuficiente se escala a un agente.",
                elegible=None,
                requiere_agente=True,
            )
        base["producto"] = {
            "sku": product["sku"],
            "nombre": product["name"],
            "categoria": product.get("category"),
            "personalizado": bool(product.get("custom", False)),
        }
        base["fuentes"].append(FUENTE_CATALOGO)
        categoria = str(product.get("category", "")).lower()

        if estado_producto == "desconocido":
            return decision(
                "informacion_faltante",
                "Para decidir necesito saber en qué estado está el producto.",
                "La elegibilidad depende de si el producto está nuevo, usado, defectuoso o dañado.",
                elegible=None,
                faltante=["estado_producto"],
                pasos=[
                    "Indicar si el producto está nuevo y sin uso, abierto/usado, tiene un defecto de "
                    "fabricación o llegó dañado."
                ],
            )

        tiene_falla = estado_producto in ESTADOS_CON_FALLA
        pasos_con_evidencia = [
            "Describir el problema y adjuntar fotografías cuando sea posible.",
            "El reembolso se procesa después de recibir y revisar el producto.",
        ]

        if product.get("custom"):
            if tiene_falla:
                return decision(
                    "requiere_revision",
                    "Los productos personalizados solo se devuelven con un defecto comprobado.",
                    "Los productos personalizados no pueden devolverse salvo defecto comprobado.",
                    elegible=None,
                    requiere_agente=True,
                    requiere_evidencia=True,
                    pasos=pasos_con_evidencia,
                )
            return decision(
                "no_elegible",
                "Los productos personalizados no pueden devolverse salvo defecto comprobado.",
                "Los productos personalizados no pueden devolverse salvo defecto comprobado.",
                elegible=False,
            )

        if categoria in CATEGORIAS_PERECEDERAS and not tiene_falla:
            return decision(
                "no_elegible",
                "Los productos perecederos no pueden devolverse por razones de seguridad.",
                "Los perecederos solo se devuelven con daño o defecto confirmado al recibirlos.",
                elegible=False,
            )

        if categoria == "higiene" and estado_producto == "abierto_o_usado":
            return decision(
                "no_elegible",
                "Los productos de higiene abiertos no pueden devolverse, salvo defecto de fabricación.",
                "Los productos de higiene abiertos no pueden devolverse, excepto cuando exista un defecto de fabricación.",
                elegible=False,
                pasos=["Si el producto tiene un defecto de fabricación, indícalo para revisar el caso."],
            )

        if estado_producto == "abierto_o_usado":
            return decision(
                "no_elegible",
                "Solo los productos nuevos y sin uso, o con defecto o daño, pueden devolverse.",
                "Los productos nuevos y sin uso pueden devolverse dentro de los 30 días posteriores a la entrega.",
                elegible=False,
                pasos=["Si el producto tiene un defecto de fabricación, indícalo para revisar el caso."],
            )

        if tiene_falla:
            return decision(
                "elegible",
                f"El producto puede devolverse por {'defecto' if estado_producto == 'defectuoso' else 'daño'} "
                f"dentro del plazo ({dias} de {RETURN_WINDOW_DAYS} días).",
                "Los productos defectuosos o dañados pueden devolverse dentro de los 30 días, con descripción y evidencia.",
                elegible=True,
                requiere_evidencia=True,
                pasos=pasos_con_evidencia,
            )

        return decision(
            "elegible",
            f"El producto está nuevo y sin uso, y la solicitud está dentro del plazo ({dias} de {RETURN_WINDOW_DAYS} días).",
            "Los productos nuevos y sin uso pueden devolverse dentro de los 30 días posteriores a la entrega.",
            elegible=True,
            pasos=["El reembolso se procesa después de recibir y revisar el producto."],
        )

    def generar_etiqueta(
        self,
        tracking_number: str,
        estado_producto: str = "desconocido",
        motivo: str = "",
        customer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        tracking = normalize_tracking(tracking_number)
        # Guardrail: la herramienta vuelve a verificar la elegibilidad y no
        # confía en que el LLM lo haya hecho antes.
        eligibility = self.verificar_elegibilidad(tracking, estado_producto, motivo, customer_id)
        if not eligibility["ok"]:
            return eligibility
        if eligibility["decision"] != "elegible":
            return _result(
                False,
                "NO_ELEGIBLE_PARA_ETIQUETA",
                "No se generó la etiqueta porque la devolución no es elegible de forma automática: "
                + eligibility["mensaje"],
                decision=eligibility["decision"],
                requiere_agente=eligibility["requiere_agente"],
                informacion_faltante=eligibility["informacion_faltante"],
                pasos_siguientes=eligibility["pasos_siguientes"],
                fuentes=eligibility["fuentes"],
            )

        existing = self.registry.get_label(tracking)
        if existing:
            return _result(
                True,
                "ETIQUETA_EXISTENTE",
                "Ya existía una etiqueta de devolución para este pedido; se reutiliza la misma.",
                etiqueta=existing,
                ya_existia=True,
            )

        today = self.today_fn()
        digest = hashlib.sha256(tracking.encode("utf-8")).hexdigest()[:8].upper()
        rma = f"RMA-{digest}"
        pedido = eligibility["pedido"]
        producto = eligibility["producto"]
        label = {
            "numero_rma": rma,
            "guia_devolucion": f"RET-{tracking.removeprefix('ECO-')}-{digest[:4]}",
            "numero_seguimiento_pedido": tracking,
            "id_pedido": pedido["id_pedido"],
            "producto": producto["nombre"],
            "sku": producto["sku"],
            "estado_producto": estado_producto,
            "motivo": (motivo or "No especificado")[:200],
            "transportadora": "EcoExpress Logística Inversa",
            "direccion_destino": "Centro de Devoluciones EcoMarket (dirección de demostración)",
            "url_etiqueta": f"https://labels.example.com/{rma}.pdf",
            "fecha_emision": today.isoformat(),
            "valida_hasta": (today + timedelta(days=LABEL_VALIDITY_DAYS)).isoformat(),
            "requiere_evidencia": eligibility["requiere_evidencia"],
            "estado": "pendiente_envio_cliente",
            "instrucciones": [
                "Empaca el producto con sus accesorios y, si es posible, en su empaque original.",
                "Imprime la etiqueta y pégala en un lugar visible del paquete.",
                f"Entrega el paquete en un punto EcoExpress antes del {(today + timedelta(days=LABEL_VALIDITY_DAYS)).isoformat()}.",
                "El reembolso se procesa después de recibir y revisar el producto.",
            ],
        }
        label["contenido_texto"] = _render_label_text(label)
        saved, already = self.registry.save_label(tracking, label)
        return _result(
            True,
            "ETIQUETA_EXISTENTE" if already else "ETIQUETA_GENERADA",
            "Etiqueta de devolución generada." if not already else "Ya existía una etiqueta para este pedido.",
            etiqueta=saved,
            ya_existia=already,
            fuentes=eligibility["fuentes"],
        )

    def consultar_politicas(self, pregunta: str, categoria: Optional[str] = None) -> dict[str, Any]:
        if not (pregunta or "").strip():
            return _result(False, "PREGUNTA_VACIA", "La consulta de política está vacía.")
        categoria = (categoria or "").strip().lower() or None
        if categoria and categoria not in CATEGORIAS_POLITICA:
            categoria = None
        try:
            documents = self.knowledge_base.search(pregunta, document_type="politica", category=categoria)
        except Exception as exc:  # fallo de embeddings o de Chroma
            return _result(
                False,
                "ERROR_BASE_CONOCIMIENTO",
                "No fue posible consultar la base de conocimiento en este momento.",
                detalle=str(exc)[:200],
            )
        if not documents:
            return _result(
                True,
                "SIN_RESULTADOS",
                "No se recuperaron fragmentos de política para la consulta.",
                fragmentos=[],
                fuentes=[],
                requiere_agente=True,
            )
        return _result(
            True,
            "FRAGMENTOS_RECUPERADOS",
            f"Se recuperaron {len(documents)} fragmentos de política.",
            fragmentos=[
                {
                    "fuente": doc.metadata.get("fuente", "fuente no identificada"),
                    "categoria": doc.metadata.get("categoria"),
                    "contenido": doc.page_content,
                }
                for doc in documents
            ],
            fuentes=knowledge_sources(documents),
        )

    def escalar(
        self,
        motivo: str,
        tracking_number: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> dict[str, Any]:
        motivo = (motivo or "").strip()
        if not motivo:
            return _result(False, "MOTIVO_VACIO", "Se requiere un motivo para escalar el caso.")
        tracking = normalize_tracking(tracking_number) if tracking_number else None
        prioridad = "alta" if any(p in normalize_text(motivo) for p in SENSITIVE_PATTERNS) else "media"
        ticket, already = self.registry.add_ticket(
            {
                "clave": f"{tracking or '-'}|{normalize_text(motivo)[:80]}",
                "numero_seguimiento": tracking,
                "cliente": customer_id,
                "motivo": motivo[:300],
                "prioridad": prioridad,
                "fecha": self.today_fn().isoformat(),
                "estado": "abierto",
            }
        )
        return _result(
            True,
            "TICKET_EXISTENTE" if already else "TICKET_CREADO",
            "El caso fue escalado a un agente humano.",
            numero_ticket=ticket["numero_ticket"],
            prioridad=ticket["prioridad"],
            tiempo_respuesta_estimado="24 horas hábiles" if ticket["prioridad"] == "media" else "4 horas hábiles",
            ya_existia=already,
        )


def _render_label_text(label: dict[str, Any]) -> str:
    lines = [
        "ECOMARKET - ETIQUETA DE DEVOLUCIÓN (DEMOSTRACIÓN)",
        "=" * 48,
        f"RMA:                 {label['numero_rma']}",
        f"Guía de devolución:  {label['guia_devolucion']}",
        f"Pedido:              {label['id_pedido']} ({label['numero_seguimiento_pedido']})",
        f"Producto:            {label['producto']} [{label['sku']}]",
        f"Transportadora:      {label['transportadora']}",
        f"Destino:             {label['direccion_destino']}",
        f"Emitida:             {label['fecha_emision']}",
        f"Válida hasta:        {label['valida_hasta']}",
        "",
        "Instrucciones:",
        *[f"  - {step}" for step in label["instrucciones"]],
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Esquemas de entrada de las herramientas (lo que ve el LLM).
# ---------------------------------------------------------------------------
class ConsultarPedidoInput(BaseModel):
    numero_seguimiento: str = Field(description="Número de seguimiento del pedido, formato ECO-12345.")


class ElegibilidadInput(BaseModel):
    numero_seguimiento: str = Field(description="Número de seguimiento del pedido, formato ECO-12345.")
    estado_producto: EstadoProducto = Field(
        default="desconocido",
        description=(
            "Estado del producto según el cliente: nuevo_sin_uso (sellado, sin usar, con etiquetas), "
            "abierto_o_usado, defectuoso (defecto de fabricación), danado_en_envio (llegó roto o dañado) "
            "o desconocido si el cliente no lo ha dicho. No lo supongas."
        ),
    )
    motivo: str = Field(default="", description="Motivo de la devolución con las palabras del cliente.")


class ConsultarPoliticasInput(BaseModel):
    pregunta: str = Field(description="Pregunta del cliente sobre políticas de EcoMarket.")
    categoria: Optional[Literal["devoluciones", "envios", "garantias"]] = Field(
        default=None, description="Categoría de la política, si es clara."
    )


class EscalarInput(BaseModel):
    motivo: str = Field(description="Resumen del caso y razón por la que requiere una persona.")
    numero_seguimiento: Optional[str] = Field(default=None, description="Número de seguimiento, si se conoce.")


TOOL_DESCRIPTIONS = {
    "consultar_estado_pedido": (
        "Consulta en el sistema de pedidos el estado, la fecha de entrega, la transportadora y el producto "
        "de un pedido por su número de seguimiento. Úsala para preguntas sobre dónde está o cuándo llega un pedido."
    ),
    "verificar_elegibilidad_producto": (
        "Verifica, con las reglas oficiales de la política de devoluciones, si el producto de un pedido puede "
        "devolverse. Devuelve la decisión (elegible, no_elegible, requiere_revision o informacion_faltante), "
        "la regla aplicada y los pasos siguientes. Úsala SIEMPRE antes de generar una etiqueta."
    ),
    "generar_etiqueta_devolucion": (
        "Genera la etiqueta de devolución (RMA, guía y enlace) de un pedido elegible. Vuelve a verificar la "
        "elegibilidad internamente y rechaza la operación si no procede. Úsala solo cuando el cliente quiere "
        "devolver el producto y la verificación resultó elegible."
    ),
    "consultar_politicas": (
        "Busca fragmentos de las políticas oficiales de EcoMarket (devoluciones, envíos, garantías) en la base "
        "de conocimiento RAG. Úsala para preguntas generales sobre reglas, plazos o condiciones que no requieren "
        "un pedido concreto."
    ),
    "escalar_a_agente_humano": (
        "Crea un ticket para que una persona del equipo de soporte revise el caso. Úsala cuando la verificación "
        "indique requiere_revision, cuando el cliente pida hablar con una persona o ante casos sensibles."
    ),
}


class AgentToolbox:
    """Herramientas ligadas a un turno de conversación.

    El ``customer_id`` proviene de la sesión (servidor), no del LLM: el modelo no
    puede actuar sobre pedidos de otro cliente aunque se lo pidan en el chat.
    """

    def __init__(
        self,
        service: ReturnService,
        logger: ActionLogger,
        customer_id: Optional[str] = None,
        session_id: Optional[str] = None,
        mode: str = "agente_llm",
    ) -> None:
        self.service = service
        self.logger = logger
        self.customer_id = (customer_id or "").strip().upper() or None
        self.session_id = session_id
        self.mode = mode
        self.trace: list[dict[str, Any]] = []

    def _run(self, name: str, args: dict[str, Any], fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:  # error inesperado: se informa como dato al agente
            result = _result(False, "ERROR_INTERNO", "La herramienta falló de forma inesperada.", detalle=str(exc)[:200])
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        self.trace.append({"herramienta": name, "argumentos": args, "resultado": result, "latencia_ms": latency_ms})
        self.logger.log(
            "tool_call",
            sesion=self.session_id,
            cliente=self.customer_id,
            modo=self.mode,
            herramienta=name,
            argumentos=args,
            ok=result.get("ok"),
            codigo=result.get("codigo"),
            decision=result.get("decision"),
            ya_existia=result.get("ya_existia"),
            latencia_ms=latency_ms,
        )
        return result

    # Métodos invocados tanto por el agente LLM como por el planificador de respaldo.
    def consultar_estado_pedido(self, numero_seguimiento: str) -> dict[str, Any]:
        args = {"numero_seguimiento": numero_seguimiento}
        return self._run(
            "consultar_estado_pedido", args, lambda: self.service.consultar_pedido(numero_seguimiento, self.customer_id)
        )

    def verificar_elegibilidad_producto(
        self, numero_seguimiento: str, estado_producto: str = "desconocido", motivo: str = ""
    ) -> dict[str, Any]:
        args = {"numero_seguimiento": numero_seguimiento, "estado_producto": estado_producto, "motivo": motivo}
        return self._run(
            "verificar_elegibilidad_producto",
            args,
            lambda: self.service.verificar_elegibilidad(numero_seguimiento, estado_producto, motivo, self.customer_id),
        )

    def generar_etiqueta_devolucion(
        self, numero_seguimiento: str, estado_producto: str = "desconocido", motivo: str = ""
    ) -> dict[str, Any]:
        args = {"numero_seguimiento": numero_seguimiento, "estado_producto": estado_producto, "motivo": motivo}
        return self._run(
            "generar_etiqueta_devolucion",
            args,
            lambda: self.service.generar_etiqueta(numero_seguimiento, estado_producto, motivo, self.customer_id),
        )

    def consultar_politicas(self, pregunta: str, categoria: Optional[str] = None) -> dict[str, Any]:
        args = {"pregunta": pregunta, "categoria": categoria}
        return self._run("consultar_politicas", args, lambda: self.service.consultar_politicas(pregunta, categoria))

    def escalar_a_agente_humano(self, motivo: str, numero_seguimiento: Optional[str] = None) -> dict[str, Any]:
        args = {"motivo": motivo, "numero_seguimiento": numero_seguimiento}
        return self._run(
            "escalar_a_agente_humano",
            args,
            lambda: self.service.escalar(motivo, numero_seguimiento, self.customer_id),
        )

    def langchain_tools(self) -> list[Any]:
        from langchain_core.tools import StructuredTool

        def as_tool(name: str, method: Callable[..., dict[str, Any]], schema: type[BaseModel]) -> StructuredTool:
            def run(**kwargs: Any) -> str:
                # El LLM recibe el resultado serializado como JSON.
                return json.dumps(method(**kwargs), ensure_ascii=False, default=str)

            return StructuredTool.from_function(
                func=run,
                name=name,
                description=TOOL_DESCRIPTIONS[name],
                args_schema=schema,
            )

        return [
            as_tool("consultar_estado_pedido", self.consultar_estado_pedido, ConsultarPedidoInput),
            as_tool("verificar_elegibilidad_producto", self.verificar_elegibilidad_producto, ElegibilidadInput),
            as_tool("generar_etiqueta_devolucion", self.generar_etiqueta_devolucion, ElegibilidadInput),
            as_tool("consultar_politicas", self.consultar_politicas, ConsultarPoliticasInput),
            as_tool("escalar_a_agente_humano", self.escalar_a_agente_humano, EscalarInput),
        ]

    @property
    def generated_label(self) -> dict[str, Any] | None:
        for step in reversed(self.trace):
            if step["herramienta"] == "generar_etiqueta_devolucion" and step["resultado"].get("ok"):
                return step["resultado"].get("etiqueta")
        return None
