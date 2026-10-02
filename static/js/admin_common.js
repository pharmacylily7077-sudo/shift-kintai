/**
 * リリー薬局 シフト・勤怠管理システム
 * 管理者ダッシュボード - 共通状態・定数・初期化
 */

let adminYear = new Date().getFullYear();
let adminMonth = new Date().getMonth() + 1;
let adminData = null;
let activeEdit = null;
let staffConditionsData = [];
let shareTextData = null;
let activeShareTab = 'group';
let currentTimecardUserId = null;
let currentTimecardData = null;
let activeTimecardEditRow = null;

const SHIFT_CLASSES = {
  FULL: 'bg-emerald-100 text-emerald-800',
  FIRST: 'bg-amber-100 text-amber-800',
  SECOND: 'bg-indigo-100 text-indigo-800',
  AM: 'bg-cyan-100 text-cyan-800',
  PM: 'bg-purple-100 text-purple-800',
  OFF: 'bg-slate-50 text-slate-300',
  PAID_LEAVE: 'bg-teal-100 text-teal-800 font-black border border-teal-300',
  HOPE_OFF: 'bg-fuchsia-100 text-fuchsia-800 font-black border border-fuchsia-300',
};

const SHIFT_TEXT = {
  FULL: '全日',
  FIRST: '前半',
  SECOND: '後半',
  AM: '午前',
  PM: '午後',
  OFF: '休',
  PAID_LEAVE: '有休',
  HOPE_OFF: '希休',
};

document.addEventListener('DOMContentLoaded', () => {
  loadAdminShifts();
  loadLeaveRequests();
  loadStaffConditions();
  loadCompliance();
});

async function logout() {
  await fetch('/api/auth/logout', { method: 'POST' });
  window.location.href = '/login';
}
