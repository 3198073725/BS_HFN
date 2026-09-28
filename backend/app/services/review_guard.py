from app.extensions import db
from app.models import User


def lock_student(student_id):
    """Use one lock order for reset, enrolment and approval mutations."""
    return db.session.scalar(db.select(User).where(User.id == student_id)
        .with_for_update().execution_options(populate_existing=True))


def claim_pending(row, values, conflict_type, message):
    """Claim the transition in SQL before changing passwords or adding members."""
    model = type(row)
    result = db.session.execute(db.update(model).where(
        model.id == row.id, model.status == "PENDING",
    ).values(**values))
    if result.rowcount != 1:
        db.session.rollback()
        raise conflict_type(message)
