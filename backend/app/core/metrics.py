from prometheus_client import Counter, Gauge, Histogram

ANALYSES_TOTAL = Counter(
    "verisonar_analyses_total",
    "Análisis de audio solicitados",
    ["status", "language"],
)
ANALYSIS_DURATION = Histogram(
    "verisonar_analysis_duration_seconds",
    "Duración del pipeline de análisis",
    buckets=(1, 5, 15, 30, 60, 120, 300),
)
DECEPTION_SCORE = Histogram(
    "verisonar_deception_index",
    "Índice de patrones de riesgo",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
RELIABILITY_SCORE = Histogram(
    "verisonar_reliability_index",
    "Índice de confiabilidad percibida",
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
)
CELERY_QUEUE_DEPTH = Gauge(
    "verisonar_celery_queue_depth",
    "Tareas pendientes por cola",
    ["queue"],
)
ACTIVE_STREAMS = Gauge(
    "verisonar_active_streams",
    "Sesiones WebSocket de audio en tiempo real",
)
