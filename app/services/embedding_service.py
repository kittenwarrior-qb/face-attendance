from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from app.models.employee_face import EmployeeFace
from app.repositories.face_repository import FaceRepository


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    a_norm = a / (np.linalg.norm(a) + 1e-10)
    b_norm = b / (np.linalg.norm(b) + 1e-10)
    return float(np.dot(a_norm, b_norm))


@dataclass
class MatchResult:
    employee_id: str
    score: float


class EmbeddingService:
    """Business logic for storing embeddings and matching a probe embedding against them."""

    def __init__(self, repository: FaceRepository, threshold: float) -> None:
        self._repository = repository
        self._threshold = threshold

    def register(
        self,
        db: Session,
        employee_id: str,
        embedding: np.ndarray,
        image_path: str | None = None,
    ) -> EmployeeFace:
        return self._repository.create(db, employee_id, embedding.tolist(), image_path)

    def find_best_match(self, db: Session, embedding: np.ndarray) -> MatchResult | None:
        """Compare `embedding` against every stored embedding (brute-force, fine for ~hundreds of rows)."""
        records = self._repository.get_all(db)

        best_score = -1.0
        best_employee_id: str | None = None
        for record in records:
            score = cosine_similarity(embedding, np.array(record.embedding, dtype=np.float32))
            if score > best_score:
                best_score = score
                best_employee_id = record.employee_id

        if best_employee_id is not None and best_score >= self._threshold:
            return MatchResult(employee_id=best_employee_id, score=best_score)
        return None
