from sqlalchemy import (
    Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger,
    String, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

def _now():
    return func.now()


class User(Base):
    __tablename__ = "Users"
    user_id = Column(Integer, primary_key=True)
    username = Column(String(64), nullable=False, unique=True)
    email = Column(String(254), nullable=False, unique=True)
    password_hash = Column(Text, nullable=False)
    role = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, server_default="true")
    last_login_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())


class Project(Base):
    __tablename__ = "Projects"
    project_id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False, server_default="planned")
    manager_id = Column(Integer, ForeignKey("Users.user_id"), nullable=False)
    start_date = Column(Date)
    due_date = Column(Date)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    manager = relationship("User")
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "Tasks"
    task_id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("Projects.project_id", ondelete="CASCADE"), nullable=False)
    assignee_id = Column(Integer, ForeignKey("Users.user_id"))
    title = Column(String(200), nullable=False)
    status = Column(String(20), nullable=False, server_default="todo")
    due_date = Column(Date)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    project = relationship("Project", back_populates="tasks")
    assignee = relationship("User")


class Asset(Base):
    __tablename__ = "Assets"
    asset_id = Column(Integer, primary_key=True)
    asset_type = Column(String(10), nullable=False)
    name = Column(String(150), nullable=False)
    category = Column(String(100))
    brand = Column(String(100))
    serial_no = Column(String(100), unique=True)
    condition = Column(String(50), nullable=False, server_default="good")
    status = Column(String(20), nullable=False, server_default="available")
    image_path = Column(String(255))
    added_by = Column(Integer, ForeignKey("Users.user_id"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    vehicle = relationship("VehicleDetail", uselist=False, cascade="all, delete-orphan")
    assignments = relationship("AssetAssignment", back_populates="asset")


class VehicleDetail(Base):
    __tablename__ = "Vehicle_Details"
    asset_id = Column(Integer, ForeignKey("Assets.asset_id", ondelete="CASCADE"), primary_key=True)
    plate_no = Column(String(20), nullable=False, unique=True)
    make = Column(String(100))
    model = Column(String(100))
    mileage = Column(Integer, nullable=False, server_default="0")


class Request(Base):
    __tablename__ = "Requests"
    request_id = Column(Integer, primary_key=True)
    requester_id = Column(Integer, ForeignKey("Users.user_id"), nullable=False)
    asset_id = Column(Integer, ForeignKey("Assets.asset_id"))
    project_id = Column(Integer, ForeignKey("Projects.project_id"))
    item_name = Column(String(200))
    reason = Column(Text)
    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    requester = relationship("User")
    asset = relationship("Asset")
    procurement = relationship("Procurement", back_populates="request", uselist=False)


class AssetAssignment(Base):
    __tablename__ = "Asset_Assignments"
    assignment_id = Column(Integer, primary_key=True)
    asset_id = Column(Integer, ForeignKey("Assets.asset_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("Users.user_id"), nullable=False)
    project_id = Column(Integer, ForeignKey("Projects.project_id"))
    request_id = Column(Integer, ForeignKey("Requests.request_id"))
    assigned_by = Column(Integer, ForeignKey("Users.user_id"))
    assigned_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    due_back = Column(Date)
    returned_at = Column(DateTime(timezone=True))
    return_condition = Column(String(50))
    asset = relationship("Asset", back_populates="assignments")
    user = relationship("User", foreign_keys=[user_id])


class Procurement(Base):
    __tablename__ = "Procurements"
    procurement_id = Column(Integer, primary_key=True)
    request_id = Column(Integer, ForeignKey("Requests.request_id", ondelete="SET NULL"), unique=True)
    requested_by = Column(Integer, ForeignKey("Users.user_id"), nullable=False)
    item_name = Column(String(200), nullable=False)
    quantity = Column(Integer, nullable=False, server_default="1")
    estimated_cost = Column(Numeric(12, 2), nullable=False)
    supplier = Column(String(200))
    status = Column(String(20), nullable=False, server_default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    request = relationship("Request", back_populates="procurement")
    approvals = relationship("Approval", back_populates="procurement", cascade="all, delete-orphan")
    disbursement = relationship("Disbursement", back_populates="procurement", uselist=False)


class Approval(Base):
    __tablename__ = "Approvals"
    approval_id = Column(Integer, primary_key=True)
    procurement_id = Column(Integer, ForeignKey("Procurements.procurement_id", ondelete="CASCADE"), nullable=False)
    level = Column(SmallInteger, nullable=False)
    approver_id = Column(Integer, ForeignKey("Users.user_id"))
    decision = Column(String(10), nullable=False, server_default="pending")
    comment = Column(Text)
    decided_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    procurement = relationship("Procurement", back_populates="approvals")
    approver = relationship("User")


class Disbursement(Base):
    __tablename__ = "Disbursements"
    disbursement_id = Column(Integer, primary_key=True)
    procurement_id = Column(Integer, ForeignKey("Procurements.procurement_id"), nullable=False, unique=True)
    amount = Column(Numeric(12, 2), nullable=False)
    status = Column(String(12), nullable=False, server_default="pending")
    paid_by = Column(Integer, ForeignKey("Users.user_id"))
    paid_at = Column(DateTime(timezone=True))
    receipt_ref = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())
    procurement = relationship("Procurement", back_populates="disbursement")
    payer = relationship("User")


class Notification(Base):
    __tablename__ = "Notifications"
    notification_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("Users.user_id", ondelete="CASCADE"), nullable=False)
    message = Column(String(500), nullable=False)
    notif_type = Column(String(30), nullable=False, server_default="info")
    is_read = Column(Boolean, nullable=False, server_default="false")
    email_sent = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())


class AuditLog(Base):
    __tablename__ = "Audit_Log"
    audit_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("Users.user_id", ondelete="SET NULL"))
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50))
    entity_id = Column(Integer)
    details = Column(JSONB)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=_now())