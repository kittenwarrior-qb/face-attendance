from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models.employee_face import EmployeeFace


class FaceRepository:
    """Data-access layer for the employee_face table. No business logic here."""

    def create(
        self,
        db: Session,
        employee_id: str,
        embedding: list[float],
        image_path: str | None = None,
    ) -> EmployeeFace:
        record = EmployeeFace(employee_id=employee_id, embedding=embedding, image_path=image_path)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    def get_all(self, db: Session) -> list[EmployeeFace]:
        return db.query(EmployeeFace).all()

    def get_by_employee_id(self, db: Session, employee_id: str) -> list[EmployeeFace]:
        return db.query(EmployeeFace).filter(EmployeeFace.employee_id == employee_id).all()

    def delete_by_employee_id(self, db: Session, employee_id: str) -> int:
        result = db.execute(delete(EmployeeFace).where(EmployeeFace.employee_id == employee_id))
        db.commit()
        return result.rowcount
