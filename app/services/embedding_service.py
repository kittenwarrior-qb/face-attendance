from dataclasses import dataclass

import numpy as np

from app.services.odoo_service import OdooService
from app.utils.exceptions import OdooServiceError
from app.utils.logger import get_logger

logger = get_logger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(np.dot(a_norm, b_norm))


@dataclass
class MatchResult:
    employee_id: str
    employee_name: str
    score: float


class EmbeddingService:
    """Matches a probe embedding against an in-memory cache of registered
    embeddings. Odoo is the source of truth (via OdooService); this cache
    exists purely so /verify doesn't pay a network round-trip per employee
    on every scan. Loaded at startup and kept in sync via write-through on
    register() - it will miss registrations made any other way (e.g. directly
    in Odoo, or by another instance of this service).
    """

    def __init__(self, odoo_service: OdooService, threshold: float) -> None:
        self._odoo_service = odoo_service
        self._threshold = threshold
        self._cache: dict[str, tuple[np.ndarray, str]] = {}
        self.reload_cache()

    def reload_cache(self) -> None:
        try:
            self._cache = self._odoo_service.load_all_faces()
            logger.info("Loaded %d face embedding(s) from Odoo", len(self._cache))
        except OdooServiceError as exc:
            logger.error("Could not load embeddings from Odoo at startup, starting with empty cache: %s", exc)
            self._cache = {}

    def register(self, employee_id: str, embedding: np.ndarray, image_bytes: bytes | None = None) -> str:
        name = self._odoo_service.save_face(employee_id, embedding, image_bytes)
        self._cache[employee_id] = (embedding, name)
        return name

    def unregister(self, employee_id: str) -> None:
        odoo_employee_id = self._odoo_service.resolve_odoo_id(employee_id)
        self._odoo_service.delete_face(odoo_employee_id)
        self._cache.pop(employee_id, None)

    def find_best_match(self, embedding: np.ndarray) -> MatchResult | None:
        """Compare `embedding` against every cached embedding (brute-force, fine for ~hundreds of rows)."""
        best_score = -1.0
        best_employee_id: str | None = None
        best_employee_name = ""
        for employee_id, (stored, name) in self._cache.items():
            score = cosine_similarity(embedding, stored)
            if score > best_score:
                best_score = score
                best_employee_id = employee_id
                best_employee_name = name

        if best_employee_id is not None and best_score >= self._threshold:
            return MatchResult(employee_id=best_employee_id, employee_name=best_employee_name, score=best_score)
        return None

    def find_employee_match(self, embedding: np.ndarray, employee_id: str) -> MatchResult | None:
        """Compare a probe only with the employee bound to the signed Odoo session.

        A global nearest-neighbour lookup is unsafe when duplicate employee records
        carry similar or identical photos: it can select another employee first and
        only then fail the account check.  Account-bound scans must be one-to-one.
        """
        entry = self._cache.get(employee_id)
        if entry is None:
            # Recover registrations made by another service instance without making
            # every normal scan pay an Odoo round-trip.
            self.reload_cache()
            entry = self._cache.get(employee_id)
        if entry is None:
            return None

        stored, name = entry
        score = cosine_similarity(embedding, stored)
        if score < self._threshold:
            return None
        return MatchResult(employee_id=employee_id, employee_name=name, score=score)

    def registered_employee(self, employee_id: str) -> MatchResult | None:
        """Return cached identity metadata even when a probe is below threshold."""
        entry = self._cache.get(employee_id)
        if entry is None:
            self.reload_cache()
            entry = self._cache.get(employee_id)
        if entry is None:
            return None
        return MatchResult(employee_id=employee_id, employee_name=entry[1], score=0.0)
