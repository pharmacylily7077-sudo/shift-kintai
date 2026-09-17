from datetime import datetime, date, time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict

# --- 認証関連 ---
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    full_name: str

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

# --- ユーザー関連 ---
class UserBase(BaseModel):
    username: str
    full_name: str
    role: str
    wage_type: str
    hourly_wage: int
    monthly_salary: int
    paid_leave_granted: float
    paid_leave_carried: float
    paid_leave_base_date: Optional[date] = None
    is_active: bool
    work_days: Optional[str] = "0,1,2,4,5"
    default_start_time: Optional[time] = None
    default_end_time: Optional[time] = None
    default_break_minutes: int = 60
    color: str = "#059669"

class UserResponse(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class UserSettingsUpdate(BaseModel):
    hourly_wage: Optional[int] = None
    paid_leave_granted: Optional[float] = None
    paid_leave_carried: Optional[float] = None
    paid_leave_base_date: Optional[date] = None

class UserConditionUpdate(BaseModel):
    full_name: Optional[str] = None
    work_days: Optional[str] = None
    default_start_time: Optional[str] = None  # "09:00"
    default_end_time: Optional[str] = None    # "18:00"
    default_break_minutes: Optional[int] = None
    color: Optional[str] = None
    hourly_wage: Optional[int] = None

# --- シフト希望関連 ---
class ShiftRequestCreate(BaseModel):
    date: date
    request_type: str = "OFF"  # "OFF" or "PAID_LEAVE"
    reason: Optional[str] = None

class ShiftRequestReview(BaseModel):
    status: str  # "APPROVED" or "REJECTED"
    admin_comment: Optional[str] = None

class ShiftRequestResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    date: date
    request_type: str
    reason: Optional[str] = None
    status: str
    admin_comment: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- シフト関連 ---
class ShiftBase(BaseModel):
    user_id: int
    date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    break_minutes: int = 60
    shift_type: str = "NORMAL"
    note: Optional[str] = None

class ShiftCreate(BaseModel):
    user_id: int
    date: date
    start_time: Optional[str] = None  # "09:00"
    end_time: Optional[str] = None    # "18:00"
    break_minutes: int = 60
    shift_type: str = "NORMAL"
    note: Optional[str] = None

class ShiftAutoGenerateRequest(BaseModel):
    year: int
    month: int
    overwrite: bool = False

class ShiftResponse(ShiftBase):
    id: int
    user_name: Optional[str] = None
    user_color: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# --- 打刻関連 ---
class ClockRequest(BaseModel):
    action: str  # "IN" (出勤), "BREAK_START" (休憩入), "BREAK_END" (休憩戻), "OUT" (退勤)
    note: Optional[str] = None

class TimeRecordResponse(BaseModel):
    id: int
    user_id: int
    date: date
    clock_in: Optional[datetime] = None
    clock_out: Optional[datetime] = None
    break_start: Optional[datetime] = None
    break_end: Optional[datetime] = None
    total_break_minutes: int
    total_work_minutes: int
    status: str
    is_corrected: bool
    note: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# --- 打刻修正申請 ---
class CorrectionRequestCreate(BaseModel):
    target_date: date
    requested_clock_in: Optional[str] = None  # "YYYY-MM-DD HH:MM" or "HH:MM"
    requested_clock_out: Optional[str] = None
    requested_break_minutes: int = 60
    reason: str

class CorrectionRequestReview(BaseModel):
    status: str  # "APPROVED" or "REJECTED"
    admin_comment: Optional[str] = None

class CorrectionRequestResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    time_record_id: Optional[int] = None
    target_date: date
    requested_clock_in: Optional[datetime] = None
    requested_clock_out: Optional[datetime] = None
    requested_break_minutes: int
    reason: str
    status: str
    admin_comment: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

# --- ダッシュボード・シミュレーション関連 ---
class StaffDashboardResponse(BaseModel):
    user: UserResponse
    today_status: str  # "NONE", "WORKING", "ON_BREAK", "LEFT"
    today_record: Optional[TimeRecordResponse] = None
    today_shift: Optional[ShiftResponse] = None
    # 給与シミュレーション
    current_month_name: str
    confirmed_work_minutes: int
    confirmed_salary: int
    projected_remaining_minutes: int
    projected_remaining_salary: int
    projected_month_end_salary: int
    # 扶養枠シミュレーション (103万, 130万)
    annual_pace_salary: int
    tax_103_limit: int = 1030000
    tax_103_remaining: int
    tax_103_hours_remaining: float
    tax_130_limit: int = 1300000
    tax_130_remaining: int
    tax_130_hours_remaining: float
    # 有休サマリー
    paid_leave_total: float
    paid_leave_used: float
    paid_leave_remaining: float
    paid_leave_legal_obligation_progress: float  # 0.0 - 1.0 (5日基準)
    paid_leave_warning: bool
