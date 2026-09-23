from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class OrderRecord(BaseModel):
    tracking_number: str
    order_id: str
    status: str
    estimated_delivery: Optional[str] = None
    carrier: Optional[str] = None
    tracking_url: Optional[str] = None
    customer_id: Optional[str] = None
    source: str = "sistema_pedidos_demo"
    updated_at: Optional[str] = None
    product_name: Optional[str] = None


class ProductRecord(BaseModel):
    sku: str
    name: str
    category: str
    custom: bool = False
    condition: str = "nuevo"
    price: Optional[float] = None
    refund_policy: Optional[str] = None


class OrderStatusResponse(BaseModel):
    encontrado: bool = True
    numero_seguimiento: str
    estado: str
    fecha_estimada: Optional[str] = None
    transportadora: Optional[str] = None
    enlace_rastreo: Optional[str] = None
    mensaje_cliente: str
    requiere_agente: bool = False
    fuentes: List[str] = Field(default_factory=list)


class ReturnEvaluationRequest(BaseModel):
    product_name: str
    category: str
    condition: str = "nuevo"
    received_days_ago: Optional[int] = None
    custom: bool = False
    reason: Optional[str] = None
    order_id: Optional[str] = None


class ReturnEvaluationResponse(BaseModel):
    es_elegible: bool
    motivo: str
    pasos_siguientes: List[str] = Field(default_factory=list)
    informacion_faltante: List[str] = Field(default_factory=list)
    requiere_agente: bool = False
    respuesta_cliente: str
    fuentes: List[str] = Field(default_factory=list)


class OrderStatusQuery(BaseModel):
    tracking_number: str
    customer_id: Optional[str] = None
    channel: str = "chat"


class ReturnQuery(BaseModel):
    tracking_number: Optional[str] = None
    product_name: Optional[str] = None
    category: Optional[str] = None
    condition: Optional[str] = "nuevo"
    received_days_ago: Optional[int] = None
    reason: Optional[str] = None
    custom: bool = False


class ProductSearchQuery(BaseModel):
    product_name: Optional[str] = None
    category: Optional[str] = None
    query: Optional[str] = None


class ProductInfoResponse(BaseModel):
    encontrado: bool = True
    nombre: str
    categoria: Optional[str] = None
    precio: Optional[float] = None
    condicion: Optional[str] = None
    personalizable: bool = False
    mensaje_cliente: str
    requiere_agente: bool = False
    fuentes: List[str] = Field(default_factory=list)


class PolicyQuery(BaseModel):
    question: str
    category: Optional[str] = None


class PolicyResponse(BaseModel):
    respuesta: str
    regla_aplicada: Optional[str] = None
    fuentes: List[str] = Field(default_factory=list)
    requiere_agente: bool = False


class TriageQuery(BaseModel):
    issue_type: str
    customer_message: str
    order_id: Optional[str] = None
    tracking_number: Optional[str] = None
    category: Optional[str] = None


class TriageResponse(BaseModel):
    categoria: str
    prioridad: str
    requiere_agente: bool = False
    resumen: str
    pasos_siguientes: List[str] = Field(default_factory=list)
    fuentes: List[str] = Field(default_factory=list)
