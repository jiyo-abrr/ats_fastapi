"""RabbitMQ (via FastStream) job queue plumbing shared by the FastAPI
process (which publishes) and `app/workers/` (which consumes) — review
F09/F26's arq/Redis migration to RabbitMQ. See
`docs/plans/rabbitmq-airflow-migration.md`.
"""

from faststream.rabbit import RabbitBroker, RabbitQueue

from app.core.config import settings

# Main evaluation-export queue. `x-dead-letter-*` routes a message here that
# fails every retry attempt (see the subscriber's `retry=3` in
# `app/workers/evaluation_export.py`) to EVALUATION_EXPORT_DLQ, via
# RabbitMQ's default exchange (empty name — its implicit routing is
# "deliver to the queue whose name equals the routing key", the simplest
# reliable way to point one queue's DLX at another named queue).
EVALUATION_EXPORT_QUEUE = RabbitQueue(
    "evaluation_export",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "evaluation_export.dlq",
    },
)
EVALUATION_EXPORT_DLQ = RabbitQueue("evaluation_export.dlq", durable=True)

# Process-wide broker — connected in main.py's lifespan (`broker.start()`)
# and closed there too (`broker.stop()`), same shape as
# `rate_limit.redis_client`. Not a FastAPI dependency's job to open/close a
# connection per request.
broker = RabbitBroker(settings.rabbitmq_url)


def get_broker() -> RabbitBroker:
    """FastAPI dependency — hands out the single process-wide broker."""
    return broker
