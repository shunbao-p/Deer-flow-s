from __future__ import annotations

import logging
import threading
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from main import AdvancedGraphRAGSystem

logger = logging.getLogger(__name__)


class LegalServiceNotReady(RuntimeError):
    """Raised when augmentation is requested before the runtime is ready."""


class LegalAugmentationService:
    """Singleton lifecycle wrapper around AdvancedGraphRAGSystem."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._system: Optional["AdvancedGraphRAGSystem"] = None
        self._initialized = False
        self._startup_error = ""
        self._reranker_ready = False
        self._reranker_model = ""
        self._reranker_prewarm_latency_ms = 0
        self._reranker_prewarm_reason = ""

    @property
    def startup_error(self) -> str:
        return self._startup_error

    @property
    def initialized(self) -> bool:
        return self._initialized

    @property
    def system_ready(self) -> bool:
        return bool(self._system and getattr(self._system, "system_ready", False))

    def startup(self) -> None:
        with self._lock:
            if self._initialized and self._system is not None:
                return
            try:
                from main import AdvancedGraphRAGSystem

                system = AdvancedGraphRAGSystem()
                system.initialize_system()
                system.build_knowledge_base(allow_rebuild=False)
                self._prewarm_reranker(system)
                self._system = system
                self._initialized = True
                self._startup_error = ""
                logger.info(
                    "Legal augmentation startup complete: reranker_ready=%s model=%s latency_ms=%s reason=%s",
                    self._reranker_ready,
                    self._reranker_model,
                    self._reranker_prewarm_latency_ms,
                    self._reranker_prewarm_reason or "",
                )
            except Exception as exc:
                self._startup_error = str(exc)
                logger.exception("Legal augmentation startup failed")
                raise

    def _prewarm_reranker(self, system: "AdvancedGraphRAGSystem") -> None:
        result: dict[str, Any] = {
            "ready": False,
            "reason": "prewarm_not_started",
            "model": "",
            "latency_ms": 0,
        }
        try:
            retrieval = getattr(system, "traditional_retrieval", None)
            if retrieval is None:
                result["reason"] = "traditional_retrieval_unavailable"
            else:
                prewarm = getattr(retrieval, "prewarm_cross_encoder", None)
                if callable(prewarm):
                    result = prewarm()
                else:
                    result["reason"] = "prewarm_method_missing"
                result["model"] = str(
                    result.get("model", "") or getattr(retrieval, "reranker_model_name", "")
                ).strip()
        except Exception as exc:
            result = {
                "ready": False,
                "reason": f"prewarm_exception:{exc.__class__.__name__}",
                "model": "",
                "latency_ms": 0,
            }
            logger.warning("Reranker prewarm failed: %s", exc.__class__.__name__)

        self._reranker_ready = bool(result.get("ready", False))
        self._reranker_model = str(result.get("model", "") or "").strip()
        self._reranker_prewarm_latency_ms = int(result.get("latency_ms", 0) or 0)
        self._reranker_prewarm_reason = str(result.get("reason", "") or "")

    def shutdown(self) -> None:
        with self._lock:
            if self._system is not None:
                cleanup = getattr(self._system, "_cleanup", None)
                if callable(cleanup):
                    cleanup()
            self._system = None
            self._initialized = False
            self._reranker_ready = False
            self._reranker_model = ""
            self._reranker_prewarm_latency_ms = 0
            self._reranker_prewarm_reason = ""
            self._startup_error = ""

    def health(self) -> dict[str, Any]:
        if self.system_ready:
            status = "ready"
        elif self._startup_error:
            status = "failed"
        else:
            status = "starting"
        return {
            "status": status,
            "initialized": self._initialized,
            "system_ready": self.system_ready,
            "startup_error": self._startup_error,
            "reranker_ready": self._reranker_ready,
            "reranker_model": self._reranker_model,
            "reranker_prewarm_latency_ms": self._reranker_prewarm_latency_ms,
            "reranker_prewarm_reason": self._reranker_prewarm_reason,
        }

    def augment(
        self,
        question: str,
        explain_routing: bool = False,
        eval_fast_mode: Optional[bool] = None,
    ) -> dict[str, Any]:
        if not self.system_ready or self._system is None:
            raise LegalServiceNotReady(self._startup_error or "legal runtime is not ready")
        resolved_fast = bool(eval_fast_mode) if eval_fast_mode is not None else False
        return self._system.ask_question_payload(
            question,
            explain_routing=explain_routing,
            eval_fast_mode=resolved_fast,
        )
