from __future__ import annotations

import logging

from langchain.tools import tool

from deerflow.config.app_config import get_app_config
from deerflow.legal.client import LegalRAGClient, LegalRAGClientError
from deerflow.legal.contracts import LegalAugmentationFailure, LegalAugmentationRequest

logger = logging.getLogger(__name__)


def _failure(error_type: str, message: str) -> str:
    return LegalAugmentationFailure(error_type=error_type, message=message).model_dump_json()


@tool("legal_augmentation", parse_docstring=True)
async def legal_augmentation_tool(question: str, explain_routing: bool = False) -> str:
    """Retrieve grounded legal evidence from the internal law database.

    Use this when the user needs a legal conclusion, statute, right, duty, liability,
    or regulatory basis that must be grounded in the law database. Do not use it for
    ordinary facts, writing, coding, or other non-legal tasks.

    Args:
        question: A self-contained legal question. Include enough context from the
            conversation so the legal service does not need the Deer thread.
        explain_routing: Optional. If true, ask the legal service to include routing
            explanation metadata. Do not choose retrieval strategies yourself.
    """
    config = get_app_config().legal_rag
    if not config.enabled:
        return _failure("disabled", "legal rag is disabled")

    question = str(question or "").strip()
    if not question:
        return _failure("invalid_response", "question is empty")

    client = LegalRAGClient(config)
    try:
        result = await client.augment(
            LegalAugmentationRequest(question=question, explain_routing=bool(explain_routing))
        )
        return result.model_dump_json()
    except LegalRAGClientError as exc:
        return exc.to_failure().model_dump_json()
    finally:
        await client.aclose()
