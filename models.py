from datetime import datetime, date, time
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, Time, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False, default="staff")  # "admin" or "staff"
    wage_type = Column(String(20), nullable=False, default="HOURLY")  # "HOURLY" or "MONTHLY"
    hourly_wage = Column(Integer, default=0, nullable=False)
    monthly_salary = Column(Integer, default=0, nullable=False)
    paid_leave_granted = Column(Float, default=0.0, nullable=False)
    paid_leave_carried = Column(Float, default=0.0, nullable=False)
    paid_leave_base_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # フェーズ2: 雇用条件（固定勤務ルール）& スタッフカラー
    work_days = Column(String(50), nullable=True, default="0,1,2,4,5")  # カンマ区切り曜日 (0=月..6=日)
    default_start_time = Column(Time, nullable=True)
    default_end_time = Column(Time, nullable=True)
    default_break_minutes = Column(Integer, default=60, nullable=False)
    color = Column(String(20), default="#059669", nullable=False)  # カレンダー表示用固定カラー
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    shifts = relationship("Shift", back_populates="user", cascade="all, delete-orphan")
    time_records = relationship("TimeRecord", back_populates="user", cascade="all, delete-orphan")
    correction_requests = relationship("CorrectionRequest", back_populates="user", cascade="all, delete-orphan")
    shift_requests = relationship("ShiftRequest", back_populates="user", cascade="all, delete-orphan")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    break_minutes = Column(Integer, default=60, nullable=False)
    shift_type = Column(String(20), default="NORMAL", nullable=False)  # "NORMAL", "PAID_LEAVE", "HOLIDAY"
    note = Column(String(255), nullable=True)

    user = relationship("User", back_populates="shifts")


class TimeRecord(Base):
    __tablename__ = "time_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    clock_in = Column(DateTime, nullable=True)
    clock_out = Column(DateTime, nullable=True)
    break_start = Column(DateTime, nullable=True)
    break_end = Column(DateTime, nullable=True)
    total_break_minutes = Column(Integer, default=0, nullable=False)
    total_work_minutes = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="NONE", nullable=False)  # "NONE", "WORKING", "ON_BREAK", "LEFT"
    is_corrected = Column(Boolean, default=False, nullable=False)
    note = Column(String(255), nullable=True)

    user = relationship("User", back_populates="time_records")
    correction_requests = relationship("CorrectionRequest", back_populates="time_record")


class CorrectionRequest(Base):
    __tablename__ = "correction_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    time_record_id = Column(Integer, ForeignKey("time_records.id"), nullable=True)
    target_date = Column(Date, nullable=False)
    requested_clock_in = Column(DateTime, nullable=True)
    requested_clock_out = Column(DateTime, nullable=True)
    requested_break_minutes = Column(Integer, default=60, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(20), default="PENDING", nullable=False)  # "PENDING", "APPROVED", "REJECTED"
    admin_comment = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="correction_requests")
    time_record = relationship("TimeRecord", back_populates="correction_requests")


class ShiftRequest(Base):
    __tablename__ = "shift_requests"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    request_type = Column(String(20), default="OFF", nullable=False)  # "OFF", "PAID_LEAVE"
    reason = Column(String(255), nullable=True)
    status = Column(String(20), default="PENDING", nullable=False)  # "PENDING", "APPROVED", "REJECTED"
    admin_comment = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="shift_requests")
