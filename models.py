from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Boolean, Date, Time,
    DateTime, ForeignKey, Text, Enum as SAEnum, Float
)
from sqlalchemy.orm import relationship
from database import Base
import enum


class Position(str, enum.Enum):
    PHARMACIST = "PHARMACIST"   # 薬剤師
    CLERK = "CLERK"             # 調剤事務
    ASSISTANT = "ASSISTANT"     # 調剤補助


class EmploymentType(str, enum.Enum):
    FULLTIME = "FULLTIME"       # 正社員（濃色）
    PARTTIME = "PARTTIME"       # パート（薄色）


class ShiftType(str, enum.Enum):
    FULL = "FULL"       # 全日 9:00-19:00
    AM = "AM"           # 午前診 9:00-13:00
    PM = "PM"           # 午後診 15:00-19:00
    FIRST = "FIRST"     # 前半 9:00-18:00
    SECOND = "SECOND"   # 後半 10:00-19:00
    OFF = "OFF"         # 休み


class ClockStatus(str, enum.Enum):
    NONE = "NONE"
    WORKING = "WORKING"
    BREAK = "BREAK"
    DONE = "DONE"


class RequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(50), nullable=False)
    position = Column(SAEnum(Position), nullable=False)
    employment_type = Column(SAEnum(EmploymentType), default=EmploymentType.FULLTIME)
    default_shift = Column(SAEnum(ShiftType), default=ShiftType.FULL)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    # マイルームカスタマイズ
    theme_color = Column(String(20), default="emerald")  # emerald/blue/rose/violet/amber/slate
    theme_bg = Column(String(20), default="simple")      # simple/sakura/ocean/night

    # 自己管理データ（暗号化せず本人管理前提）
    hourly_wage = Column(Integer, default=0)
    paid_leave_remaining = Column(Float, default=0.0)
    fixed_off_weekdays = Column(String(50), default="6") # "6" = 日曜休み (0=月 ... 6=日)

    created_at = Column(DateTime, default=datetime.utcnow)

    # リレーション
    shifts = relationship("Shift", back_populates="user", cascade="all, delete-orphan")
    time_records = relationship("TimeRecord", back_populates="user", cascade="all, delete-orphan")
    personal_schedules = relationship("PersonalSchedule", back_populates="user", cascade="all, delete-orphan")
    leave_requests = relationship("LeaveRequest", back_populates="user", cascade="all, delete-orphan")
    sent_messages = relationship("Message", foreign_keys="Message.from_user_id", back_populates="sender")
    received_messages = relationship("Message", foreign_keys="Message.to_user_id", back_populates="recipient")

    @property
    def position_color(self):
        """ポジション×雇用形態の色コード"""
        colors = {
            (Position.PHARMACIST, EmploymentType.FULLTIME): "#16a34a",
            (Position.PHARMACIST, EmploymentType.PARTTIME): "#86efac",
            (Position.CLERK, EmploymentType.FULLTIME): "#2563eb",
            (Position.CLERK, EmploymentType.PARTTIME): "#93c5fd",
            (Position.ASSISTANT, EmploymentType.FULLTIME): "#dc2626",
            (Position.ASSISTANT, EmploymentType.PARTTIME): "#fca5a5",
        }
        return colors.get((self.position, self.employment_type), "#94a3b8")

    @property
    def position_label(self):
        labels = {
            Position.PHARMACIST: "薬剤師",
            Position.CLERK: "調剤事務",
            Position.ASSISTANT: "調剤補助",
        }
        return labels.get(self.position, "")

    @property
    def shift_time_range(self):
        """デフォルトシフトの時間帯"""
        ranges = {
            ShiftType.FULL: "9:00〜19:00",
            ShiftType.AM: "9:00〜13:00",
            ShiftType.PM: "15:00〜19:00",
            ShiftType.FIRST: "9:00〜18:00",
            ShiftType.SECOND: "10:00〜19:00",
            ShiftType.OFF: "休み",
        }
        return ranges.get(self.default_shift, "")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    shift_type = Column(SAEnum(ShiftType), nullable=False)
    note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="shifts")

    @property
    def time_range(self):
        ranges = {
            ShiftType.FULL: "9:00〜19:00",
            ShiftType.AM: "9:00〜13:00",
            ShiftType.PM: "15:00〜19:00",
            ShiftType.FIRST: "9:00〜18:00",
            ShiftType.SECOND: "10:00〜19:00",
            ShiftType.OFF: "休み",
        }
        return ranges.get(self.shift_type, "")

    @property
    def shift_label(self):
        labels = {
            ShiftType.FULL: "全日",
            ShiftType.AM: "午前診",
            ShiftType.PM: "午後診",
            ShiftType.FIRST: "前半",
            ShiftType.SECOND: "後半",
            ShiftType.OFF: "休み",
        }
        return labels.get(self.shift_type, "")


class TimeRecord(Base):
    """自己申告勤怠"""
    __tablename__ = "time_records"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    clock_in = Column(Time, nullable=True)
    clock_out = Column(Time, nullable=True)
    break_start = Column(Time, nullable=True)
    break_end = Column(Time, nullable=True)
    status = Column(SAEnum(ClockStatus), default=ClockStatus.NONE)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="time_records")

    @property
    def work_minutes(self):
        if not self.clock_in or not self.clock_out:
            return 0
        from datetime import datetime, timedelta
        ci = datetime.combine(date.today(), self.clock_in)
        co = datetime.combine(date.today(), self.clock_out)
        total = (co - ci).total_seconds() / 60
        if self.break_start and self.break_end:
            bs = datetime.combine(date.today(), self.break_start)
            be = datetime.combine(date.today(), self.break_end)
            total -= (be - bs).total_seconds() / 60
        return max(0, int(total))


class PersonalSchedule(Base):
    """個人スケジュール・体調・家計簿（マイルーム専用）"""
    __tablename__ = "personal_schedules"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    title = Column(String(200), default="")
    category = Column(String(20), default="PRIVATE")  # WORK/PRIVATE/HEALTH/BUDGET
    note = Column(Text, default="")
    health_status = Column(String(10), nullable=True)  # GOOD/OK/TIRED
    amount = Column(Integer, nullable=True)             # 家計簿用
    is_income = Column(Boolean, nullable=True)         # True=収入, False=支出
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="personal_schedules")


class LeaveRequest(Base):
    """休暇申請（本人↔管理者のみ・他スタッフ不可視）"""
    __tablename__ = "leave_requests"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    date = Column(Date, nullable=False)
    request_type = Column(String(20), default="ADVANCE")  # URGENT/ADVANCE
    leave_type = Column(String(20), default="OFF")         # OFF/PAID_LEAVE
    reason = Column(Text, default="")
    status = Column(SAEnum(RequestStatus), default=RequestStatus.PENDING)
    admin_note = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="leave_requests")


class Message(Base):
    """管理者↔スタッフ個別メッセージ"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    sender = relationship("User", foreign_keys=[from_user_id], back_populates="sent_messages")
    recipient = relationship("User", foreign_keys=[to_user_id], back_populates="received_messages")
