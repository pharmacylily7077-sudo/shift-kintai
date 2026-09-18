from datetime import datetime, date, time
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

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
    weekly_schedule: Optional[str] = None
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

    @field_validator("hourly_wage")
    @classmethod
    def validate_wage(cls, v):
        if v is not None and v < 0:
            raise ValueError("時給は0以上である必要があります")
        return v

class UserConditionUpdate(BaseModel):
    full_name: Optional[str] = None
    wage_type: Optional[str] = None  # "HOURLY" or "MONTHLY"
    hourly_wage: Optional[int] = None
    monthly_salary: Optional[int] = None
    work_days: Optional[str] = None
    weekly_schedule: Optional[str] = None
    default_start_time: Optional[str] = None  # "09:00"
    default_end_time: Optional[str] = None    # "18:00"
    default_break_minutes: Optional[int] = None
    color: Optional[str] = None

    @field_validator("wage_type")
    @classmethod
    def validate_wage_type(cls, v):
        if v is not None and v not in ["HOURLY", "MONTHLY"]:
            raise ValueError("wage_type は 'HOURLY' または 'MONTHLY' である必要があります")
        return v

    @field_validator("monthly_salary")
    @classmethod
    def validate_monthly_salary(cls, v):
        if v is not None and v < 0:
            raise ValueError("月給は0円以上である必要があります")
        return v

    @field_validator("default_break_minutes")
    @classmethod
    def validate_break(cls, v):
        if v is not None and v < 0:
            raise ValueError("休憩時間は0分以上である必要があります")
        return v

    @field_validator("hourly_wage")
    @classmethod
    def validate_wage(cls, v):
        if v is not None and v < 0:
            raise ValueError("時給は0円以上である必要があります")
        return v

class UserAdminCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "staff"
    wage_type: str = "HOURLY"
    hourly_wage: int = 1500
    work_days: str = "0,1,2,3,4"
    weekly_schedule: Optional[str] = None
    default_start_time: Optional[str] = "09:00"
    default_end_time: Optional[str] = "18:00"
    default_break_minutes: int = 60
    color: str = "#059669"

    @field_validator("hourly_wage")
    @classmethod
    def validate_wage(cls, v):
        if v < 0:
            raise ValueError("時給は0円以上である必要があります")
        return v

# --- シフト希望関連 ---
class ShiftRequestCreate(BaseModel):
    date: date
    request_type: str = "OFF"  # "OFF" or "PAID_LEAVE"
    reason: Optional[str] = None

    @field_validator("request_type")
    @classmethod
    def validate_request_type(cls, v):
        if v not in ["OFF", "PAID_LEAVE"]:
            raise ValueError("request_type は 'OFF' または 'PAID_LEAVE' である必要があります")
        return v

class ShiftRequestReview(BaseModel):
    status: str  # "APPROVED" or "REJECTED"
    admin_comment: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ["APPROVED", "REJECTED"]:
            raise ValueError("status は 'APPROVED' または 'REJECTED' である必要があります")
        return v

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

    @field_validator("break_minutes")
    @classmethod
    def validate_break(cls, v):
        if v < 0:
            raise ValueError("休憩時間は0分以上である必要があります")
        return v

    @model_validator(mode="after")
    def validate_shift_times(self):
        if self.start_time and self.end_time:
            st = datetime.strptime(self.start_time, "%H:%M").time()
            et = datetime.strptime(self.end_time, "%H:%M").time()
            if et <= st:
                raise ValueError("終了時刻は開始時刻より後である必要があります")
        return self

class ShiftAutoGenerateRequest(BaseModel):
    year: int
    month: int
    overwrite: bool = False

    @field_validator("year")
    @classmethod
    def validate_year(cls, v):
        if v < 2000 or v > 2100:
            raise ValueError("年は2000〜2100年の範囲で指定してください")
        return v

    @field_validator("month")
    @classmethod
    def validate_month(cls, v):
        if v < 1 or v > 12:
            raise ValueError("月は1〜12の範囲で指定してください")
        return v

class ShiftResponse(ShiftBase):
    id: int
    user_name: Optional[str] = None
    user_color: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

# --- 打刻関連 ---
class ClockRequest(BaseModel):
    action: str  # "IN" (出勤), "BREAK_START" (休憩入), "BREAK_END" (休憩戻), "OUT" (退勤)
    note: Optional[str] = None

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        if v not in ["IN", "BREAK_START", "BREAK_END", "OUT"]:
            raise ValueError("不正な打刻アクションです")
        return v

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

    @field_validator("requested_break_minutes")
    @classmethod
    def validate_break(cls, v):
        if v < 0:
            raise ValueError("休憩時間は0分以上である必要があります")
        return v

    @model_validator(mode="after")
    def validate_correction_times(self):
        if self.requested_clock_in and self.requested_clock_out:
            # 時刻パースチェック
            def parse_dt(val: str, ref_date: date) -> datetime:
                val = val.strip()
                if " " in val:
                    return datetime.strptime(val, "%Y-%m-%d %H:%M")
                elif "T" in val:
                    return datetime.fromisoformat(val)
                else:
                    t = datetime.strptime(val, "%H:%M").time()
                    return datetime.combine(ref_date, t)
            
            try:
                dt_in = parse_dt(self.requested_clock_in, self.target_date)
                dt_out = parse_dt(self.requested_clock_out, self.target_date)
                if dt_out <= dt_in:
                    raise ValueError("退勤日時は出勤日時より後である必要があります")
                diff_min = int((dt_out - dt_in).total_seconds() // 60)
                if self.requested_break_minutes > diff_min:
                    raise ValueError("休憩時間は勤務時間以内で指定してください")
            except ValueError as e:
                raise e
            except Exception:
                raise ValueError("日時の指定形式が不正です")
        return self

class CorrectionRequestReview(BaseModel):
    status: str  # "APPROVED" or "REJECTED"
    admin_comment: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v):
        if v not in ["APPROVED", "REJECTED"]:
            raise ValueError("status は 'APPROVED' または 'REJECTED' である必要があります")
        return v

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

# --- 管理者による勤怠直接更新 ---
class AdminTimeRecordUpdate(BaseModel):
    user_id: int
    date: date
    clock_in: Optional[str] = None   # "HH:MM" または "YYYY-MM-DD HH:MM"
    clock_out: Optional[str] = None  # "HH:MM" または "YYYY-MM-DD HH:MM"
    total_break_minutes: int = 60
    note: Optional[str] = None

    @field_validator("total_break_minutes")
    @classmethod
    def validate_break(cls, v):
        if v < 0:
            raise ValueError("休憩時間は0分以上である必要があります")
        return v

    @model_validator(mode="after")
    def validate_admin_time_record(self):
        if self.clock_in and self.clock_out:
            def parse_dt(val: str, ref_date: date) -> datetime:
                val = val.strip()
                if " " in val:
                    return datetime.strptime(val, "%Y-%m-%d %H:%M")
                elif "T" in val:
                    return datetime.fromisoformat(val)
                else:
                    t = datetime.strptime(val, "%H:%M").time()
                    return datetime.combine(ref_date, t)

            try:
                dt_in = parse_dt(self.clock_in, self.date)
                dt_out = parse_dt(self.clock_out, self.date)
                if dt_out <= dt_in:
                    raise ValueError("退勤日時は出勤日時より後である必要があります")
                diff_min = int((dt_out - dt_in).total_seconds() // 60)
                if self.total_break_minutes > diff_min:
                    raise ValueError("休憩時間は勤務時間以内で指定してください")
            except ValueError as e:
                raise e
            except Exception:
                raise ValueError("日時の指定形式が不正です")
        return self


# --- 月次給与集計 ---
class MonthlyPayrollItem(BaseModel):
    user_id: int
    username: str
    full_name: str
    role: str
    wage_type: str  # "HOURLY" or "MONTHLY"
    hourly_wage: int
    monthly_salary: int
    work_days_count: int
    scheduled_days_count: int
    total_work_minutes: int
    total_work_hours_str: str
    total_break_minutes: int
    paid_leave_days_count: float
    paid_leave_allowance: int
    work_salary: int
    total_estimated_salary: int

class MonthlyPayrollResponse(BaseModel):
    year: int
    month: int
    items: List[MonthlyPayrollItem]
    total_payout: int
    total_work_hours: float

