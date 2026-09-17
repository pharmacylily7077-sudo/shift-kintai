let currentYear = new Date().getFullYear();
let currentMonth = new Date().getMonth() + 1;
let currentDashboardData = null;

// 初期化
document.addEventListener('DOMContentLoaded', () => {
  initClock();
  loadDashboard();
  loadCalendar();
});

// 1. リアルタイム時計
function initClock() {
  const clockEl = document.getElementById('live-clock');
  const dateEl = document.getElementById('today-date-str');

  function update() {
    const now = new Date();
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    if (clockEl) clockEl.textContent = `${hours}:${minutes}:${seconds}`;

    const year = now.getFullYear();
    const month = now.getMonth() + 1;
    const date = now.getDate();
    const days = ['日', '月', '火', '水', '木', '金', '土'];
    const day = days[now.getDay()];
    if (dateEl) dateEl.textContent = `${year}年${month}月${date}日 (${day})`;
  }

  update();
  setInterval(update, 1000);
}

// 2. ダッシュボード情報取得・表示
async function loadDashboard() {
  try {
    const res = await fetch('/api/me/dashboard');
    if (res.status === 401) {
      window.location.href = '/login';
      return;
    }
    if (!res.ok) throw new Error('ダッシュボード取得失敗');

    const data = await res.json();
    currentDashboardData = data;
    renderDashboard(data);
  } catch (err) {
    console.error(err);
    showToast('データの取得に失敗しました', 'error');
  }
}

function renderDashboard(d) {
  // ステータスバッジ
  const badge = document.getElementById('current-status-badge');
  const statusMap = {
    NONE: { text: '未出勤', bg: 'bg-slate-100', textCol: 'text-slate-600', dot: 'bg-slate-400' },
    WORKING: { text: '勤務中', bg: 'bg-emerald-50', textCol: 'text-emerald-700', dot: 'bg-emerald-500' },
    ON_BREAK: { text: '休憩中', bg: 'bg-amber-50', textCol: 'text-amber-700', dot: 'bg-amber-500' },
    LEFT: { text: '退勤済（本日完了）', bg: 'bg-blue-50', textCol: 'text-blue-700', dot: 'bg-blue-500' },
  };

  const currentSt = statusMap[d.today_status] || statusMap.NONE;
  if (badge) {
    badge.textContent = currentSt.text;
    badge.parentElement.className = `inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold ${currentSt.bg} ${currentSt.textCol}`;
    badge.previousElementSibling.className = `w-2 h-2 rounded-full ${currentSt.dot} ${d.today_status === 'WORKING' ? 'animate-pulse' : ''}`;
  }

  // 打刻ボタン制御
  const btnIn = document.getElementById('btn-clock-in');
  const btnBreakStart = document.getElementById('btn-break-start');
  const btnBreakEnd = document.getElementById('btn-break-end');
  const btnOut = document.getElementById('btn-clock-out');

  const inDisplay = document.getElementById('clock-in-time-display');
  const outDisplay = document.getElementById('clock-out-time-display');

  if (d.today_record && d.today_record.clock_in) {
    const inDate = new Date(d.today_record.clock_in);
    inDisplay.textContent = `${String(inDate.getHours()).padStart(2, '0')}:${String(inDate.getMinutes()).padStart(2, '0')} 打刻`;
  } else {
    inDisplay.textContent = '未打刻';
  }

  if (d.today_record && d.today_record.clock_out) {
    const outDate = new Date(d.today_record.clock_out);
    outDisplay.textContent = `${String(outDate.getHours()).padStart(2, '0')}:${String(outDate.getMinutes()).padStart(2, '0')} 打刻`;
  } else {
    outDisplay.textContent = '未打刻';
  }

  // ステートマシンに応じたボタンの活性/非活性制御
  if (d.today_status === 'NONE') {
    btnIn.disabled = false;
    btnBreakStart.disabled = true;
    btnBreakEnd.disabled = true;
    btnOut.disabled = true;
  } else if (d.today_status === 'WORKING') {
    btnIn.disabled = true;
    btnBreakStart.disabled = false;
    btnBreakEnd.disabled = true;
    btnOut.disabled = false;
  } else if (d.today_status === 'ON_BREAK') {
    btnIn.disabled = true;
    btnBreakStart.disabled = true;
    btnBreakEnd.disabled = false;
    btnOut.disabled = false; // 休憩から直接退勤も許可
  } else if (d.today_status === 'LEFT') {
    btnIn.disabled = true;
    btnBreakStart.disabled = true;
    btnBreakEnd.disabled = true;
    btnOut.disabled = true;
  }

  // 今日のシフト予告
  const shiftNotice = document.getElementById('today-shift-notice');
  if (shiftNotice) {
    if (d.today_shift) {
      if (d.today_shift.shift_type === 'NORMAL') {
        shiftNotice.innerHTML = `本日のシフト: <span class="font-bold text-slate-800">${d.today_shift.start_time?.slice(0,5)} 〜 ${d.today_shift.end_time?.slice(0,5)}</span> (${d.today_shift.note || '通常出勤'})`;
      } else if (d.today_shift.shift_type === 'PAID_LEAVE') {
        shiftNotice.innerHTML = `本日のシフト: <span class="font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">有給休暇</span>`;
      } else {
        shiftNotice.innerHTML = `本日のシフト: <span class="font-bold text-slate-500">公休</span>`;
      }
    } else {
      shiftNotice.innerHTML = `本日のシフト: <span class="text-slate-400">予定なし</span>`;
    }
  }

  // 給与シミュレーション表示
  document.getElementById('salary-month-label').textContent = `${d.current_month_name} 概算＆着地見込み`;
  document.getElementById('confirmed-salary').textContent = `¥${d.confirmed_salary.toLocaleString()}`;
  const confHours = Math.floor(d.confirmed_work_minutes / 60);
  const confMins = d.confirmed_work_minutes % 60;
  document.getElementById('confirmed-hours').textContent = `実働: ${confHours}時間${String(confMins).padStart(2, '0')}分`;

  document.getElementById('projected-salary').textContent = `¥${d.projected_month_end_salary.toLocaleString()}`;
  const projHours = Math.round(d.projected_remaining_minutes / 60);
  document.getElementById('projected-hours').textContent = `残り予定: 約${projHours}時間`;

  // 扶養枠シミュレーション
  const paceMan = Math.round(d.annual_pace_salary / 10000);
  document.getElementById('annual-pace-text').textContent = `年換算: 約${paceMan}万円ペース`;

  const pct103 = Math.min(100, Math.round((d.annual_pace_salary / d.tax_103_limit) * 100));
  document.getElementById('tax-103-bar').style.width = `${pct103}%`;
  document.getElementById('tax-103-text').textContent = `残 ¥${d.tax_103_remaining.toLocaleString()}（あと約${d.tax_103_hours_remaining}時間）`;

  const pct130 = Math.min(100, Math.round((d.annual_pace_salary / d.tax_130_limit) * 100));
  document.getElementById('tax-130-bar').style.width = `${pct130}%`;
  document.getElementById('tax-130-text').textContent = `残 ¥${d.tax_130_remaining.toLocaleString()}（あと約${d.tax_130_hours_remaining}時間）`;

  document.getElementById('current-wage-display').textContent = `設定時給: ¥${d.user.hourly_wage.toLocaleString()}`;

  // 有休自己管理表示
  document.getElementById('paid-leave-total').textContent = `${d.paid_leave_total}日`;
  document.getElementById('paid-leave-breakdown').textContent = `(付与${d.user.paid_leave_granted} + 繰越${d.user.paid_leave_carried})`;
  document.getElementById('paid-leave-used').textContent = `${d.paid_leave_used}日`;
  document.getElementById('paid-leave-remaining').textContent = `${d.paid_leave_remaining}日`;

  const legalPct = Math.round(d.paid_leave_legal_obligation_progress * 100);
  document.getElementById('legal-progress-bar').style.width = `${legalPct}%`;
  document.getElementById('legal-progress-text').textContent = `${d.paid_leave_used} / 5日 (${legalPct}%)`;

  const warnBox = document.getElementById('legal-warning-box');
  if (d.paid_leave_warning) {
    warnBox.classList.remove('hidden');
  } else {
    warnBox.classList.add('hidden');
  }

  document.getElementById('paid-leave-base-date-display').textContent = d.user.paid_leave_base_date || '未設定';

  lucide.createIcons();
}

// 3. 打刻処理
async function clockAction(action) {
  const confirmTexts = {
    IN: '出勤打刻しますか？',
    BREAK_START: '休憩に入りますか？',
    BREAK_END: '休憩から戻りますか？',
    OUT: '退勤打刻しますか？本日もお疲れ様でした！'
  };

  if (!confirm(confirmTexts[action])) return;

  try {
    const res = await fetch('/api/me/clock', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: action })
    });

    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || '打刻に失敗しました');
    }

    const labels = { IN: '出勤', BREAK_START: '休憩入', BREAK_END: '休憩戻', OUT: '退勤' };
    showToast(`${labels[action]}打刻を記録しました！`);

    // 再読込
    await loadDashboard();
    await loadCalendar();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 4. カレンダー取得・表示
async function loadCalendar() {
  try {
    document.getElementById('calendar-month-title').textContent = `${currentYear}年${currentMonth}月`;
    const res = await fetch(`/api/me/shifts?year=${currentYear}&month=${currentMonth}`);
    if (!res.ok) throw new Error('カレンダー取得失敗');

    const days = await res.json();
    renderCalendarGrid(days);
    renderCalendarList(days);
  } catch (err) {
    console.error(err);
  }
}

// 7列月間グリッドカレンダー（メイン表示）
function renderCalendarGrid(days) {
  const container = document.getElementById('calendar-grid-cells');
  if (!container) return;
  container.innerHTML = '';

  if (!days || days.length === 0) return;

  // 1日の曜日を特定 (0=日, 1=月, ..., 6=土)
  const firstDayDate = new Date(`${days[0].date}T00:00:00`);
  const startDayOfWeek = firstDayDate.getDay();

  // 月初の前の空白セル
  for (let i = 0; i < startDayOfWeek; i++) {
    const blank = document.createElement('div');
    blank.className = 'min-h-[78px] sm:min-h-[105px] p-1 sm:p-2 rounded-xl bg-slate-50/40 border border-slate-100/60 opacity-30';
    container.appendChild(blank);
  }

  const todayStr = new Date().toISOString().slice(0, 10);

  // 各日付マス目
  days.forEach(item => {
    const cell = document.createElement('div');
    const isToday = item.date === todayStr;
    const itemDate = new Date(`${item.date}T00:00:00`);
    const dayOfWeek = itemDate.getDay();

    let dayNumColor = 'text-slate-800';
    if (dayOfWeek === 0) dayNumColor = 'text-rose-600 font-black';
    if (dayOfWeek === 6) dayNumColor = 'text-blue-600 font-black';

    cell.className = `min-h-[78px] sm:min-h-[105px] p-1.5 sm:p-2 rounded-xl border transition flex flex-col justify-between cursor-pointer group ${
      isToday
        ? 'bg-emerald-50/70 border-emerald-400 ring-2 ring-emerald-400/40 shadow-xs'
        : 'bg-white border-slate-200 hover:border-emerald-400 hover:shadow-xs'
    }`;
    cell.onclick = () => openCorrectionModalForDate(item.date);
    cell.title = `${item.day}日の詳細（クリックで打刻修正申請）`;

    let dateHeaderHtml = `
      <div class="flex items-center justify-between">
        <span class="text-xs sm:text-sm font-black ${isToday ? 'bg-emerald-600 text-white w-5 h-5 rounded-full flex items-center justify-center text-[10px]' : dayNumColor}">
          ${item.day}
        </span>
        <div class="flex items-center space-x-1">
          ${isToday ? '<span class="text-[9px] font-black text-emerald-700 bg-emerald-100 px-1 rounded hidden sm:inline">今日</span>' : ''}
          <button onclick="event.stopPropagation(); openShiftRequestModal('${item.date}')" class="opacity-0 group-hover:opacity-100 text-teal-600 hover:text-teal-800 p-0.5 rounded hover:bg-teal-50 transition" title="この日に休み希望提出">
            <i data-lucide="palmtree" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </div>
    `;

    let shiftHtml = '';
    if (item.shift) {
      if (item.shift.shift_type === 'NORMAL') {
        shiftHtml = `
          <div class="mt-1 bg-emerald-50 text-emerald-800 border border-emerald-200/80 rounded px-1 py-0.5 text-[9px] sm:text-[10px] font-semibold truncate leading-tight">
            ${item.shift.start_time} - ${item.shift.end_time}
          </div>
        `;
      } else if (item.shift.shift_type === 'PAID_LEAVE') {
        shiftHtml = `
          <div class="mt-1 bg-green-100 text-green-800 border border-green-300 rounded px-1 py-0.5 text-[9px] sm:text-[10px] font-black truncate leading-tight">
            🌿 有休
          </div>
        `;
      } else if (item.shift.shift_type === 'HOLIDAY') {
        shiftHtml = `
          <div class="mt-1 bg-slate-100 text-slate-500 rounded px-1 py-0.5 text-[9px] sm:text-[10px] truncate leading-tight">
            公休
          </div>
        `;
      }
    }

    // シフト希望（休み希望）バッジ
    let shiftRequestHtml = '';
    if (item.shift_request) {
      if (item.shift_request.request_type === 'OFF') {
        if (item.shift_request.status === 'PENDING') {
          shiftRequestHtml = `
            <div class="mt-0.5 bg-amber-50 text-amber-800 border border-amber-200 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-bold truncate">
              🏖️ 希望休 (申請中)
            </div>
          `;
        } else if (item.shift_request.status === 'APPROVED') {
          shiftRequestHtml = `
            <div class="mt-0.5 bg-rose-50 text-rose-700 border border-rose-200 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-bold truncate">
              🏖️ 希望休 (承認済)
            </div>
          `;
        }
      } else if (item.shift_request.request_type === 'PAID_LEAVE') {
        if (item.shift_request.status === 'PENDING') {
          shiftRequestHtml = `
            <div class="mt-0.5 bg-amber-50 text-amber-800 border border-amber-200 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-bold truncate">
              🌿 有休 (申請中)
            </div>
          `;
        }
      }
    }

    let recordHtml = '';
    if (item.record) {
      if (item.record.is_corrected) {
        recordHtml = `
          <div class="mt-1 bg-purple-50 text-purple-700 border border-purple-200 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-bold truncate">
            ✓ 修正済
          </div>
        `;
      } else if (item.record.status === 'LEFT') {
        const h = Math.floor(item.record.total_work_minutes / 60);
        const m = item.record.total_work_minutes % 60;
        recordHtml = `
          <div class="mt-1 bg-slate-100 text-slate-700 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-medium truncate">
            ✓ ${h}h${m > 0 ? `${m}m` : ''}
          </div>
        `;
      } else if (item.record.status === 'WORKING') {
        recordHtml = `
          <div class="mt-1 bg-emerald-100 text-emerald-800 rounded px-1 py-0.5 text-[8px] sm:text-[9px] font-bold animate-pulse truncate">
            ● 勤務中
          </div>
        `;
      }
    }

    cell.innerHTML = `
      <div>
        ${dateHeaderHtml}
        ${shiftHtml}
        ${shiftRequestHtml}
      </div>
      <div>
        ${recordHtml}
      </div>
    `;

    container.appendChild(cell);
  });

  // 末尾の余白セル
  const totalCells = startDayOfWeek + days.length;
  const remainingCells = (7 - (totalCells % 7)) % 7;
  for (let i = 0; i < remainingCells; i++) {
    const blank = document.createElement('div');
    blank.className = 'min-h-[78px] sm:min-h-[105px] p-1 sm:p-2 rounded-xl bg-slate-50/40 border border-slate-100/60 opacity-30';
    container.appendChild(blank);
  }

  lucide.createIcons({ root: container });
}

// リスト表示（補助）
function renderCalendarList(days) {
  const tbody = document.getElementById('calendar-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  const todayStr = new Date().toISOString().slice(0, 10);

  days.forEach(item => {
    const tr = document.createElement('tr');
    const isToday = item.date === todayStr;
    if (isToday) {
      tr.className = 'bg-emerald-50/40 font-medium';
    }

    let weekdayCol = 'text-slate-500';
    if (item.weekday === 'Sun') weekdayCol = 'text-rose-500 font-bold';
    if (item.weekday === 'Sat') weekdayCol = 'text-blue-500 font-bold';

    let shiftDisplay = '<span class="text-slate-300">-</span>';
    if (item.shift) {
      if (item.shift.shift_type === 'NORMAL') {
        shiftDisplay = `<span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded">${item.shift.start_time} - ${item.shift.end_time}</span>`;
      } else if (item.shift.shift_type === 'PAID_LEAVE') {
        shiftDisplay = `<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded">有給休暇</span>`;
      } else if (item.shift.shift_type === 'HOLIDAY') {
        shiftDisplay = `<span class="bg-slate-100 text-slate-500 px-2 py-0.5 rounded">公休</span>`;
      }
    }

    // シフト希望表示
    if (item.shift_request) {
      if (item.shift_request.request_type === 'OFF') {
        if (item.shift_request.status === 'PENDING') {
          shiftDisplay += ` <span class="bg-amber-100 text-amber-800 text-[10px] font-bold px-1.5 py-0.5 rounded">🏖️休申請中</span>`;
        } else if (item.shift_request.status === 'APPROVED') {
          shiftDisplay += ` <span class="bg-rose-100 text-rose-800 text-[10px] font-bold px-1.5 py-0.5 rounded">🏖️希望休</span>`;
        }
      } else if (item.shift_request.request_type === 'PAID_LEAVE' && item.shift_request.status === 'PENDING') {
        shiftDisplay += ` <span class="bg-amber-100 text-amber-800 text-[10px] font-bold px-1.5 py-0.5 rounded">🌿有休申請中</span>`;
      }
    }

    const cin = item.record && item.record.clock_in ? item.record.clock_in : '-';
    const cout = item.record && item.record.clock_out ? item.record.clock_out : '-';
    
    let workHours = '-';
    if (item.record && item.record.total_work_minutes > 0) {
      const h = Math.floor(item.record.total_work_minutes / 60);
      const m = item.record.total_work_minutes % 60;
      workHours = `${h}h ${m}m`;
    }

    let statusBadge = '<span class="text-slate-300">-</span>';
    if (item.record) {
      if (item.record.is_corrected) {
        statusBadge = '<span class="bg-purple-50 text-purple-700 px-2 py-0.5 rounded text-[10px] font-bold">修正済</span>';
      } else if (item.record.status === 'LEFT') {
        statusBadge = '<span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[10px]">完了</span>';
      } else if (item.record.status === 'WORKING') {
        statusBadge = '<span class="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded text-[10px] font-bold">勤務中</span>';
      }
    }

    tr.innerHTML = `
      <td class="py-3 px-4 flex items-center space-x-2">
        <span class="${isToday ? 'font-bold text-emerald-700' : 'text-slate-800'}">${item.day}日</span>
        <span class="text-[11px] ${weekdayCol}">(${item.weekday})</span>
        ${isToday ? '<span class="bg-emerald-500 text-white text-[9px] px-1 rounded font-bold">今日</span>' : ''}
      </td>
      <td class="py-3 px-4">${shiftDisplay}</td>
      <td class="py-3 px-4 font-mono">${cin}</td>
      <td class="py-3 px-4 font-mono">${cout}</td>
      <td class="py-3 px-4 font-semibold text-slate-700">${workHours}</td>
      <td class="py-3 px-4 text-center">${statusBadge}</td>
      <td class="py-3 px-4 text-center space-x-1.5">
        <button onclick="openShiftRequestModal('${item.date}')" class="text-teal-600 hover:text-teal-800 hover:underline text-[11px] font-semibold">
          希望休
        </button>
        <button onclick="openCorrectionModalForDate('${item.date}')" class="text-emerald-600 hover:text-emerald-800 hover:underline text-[11px]">
          打刻修正
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function switchView(view) {
  const gridView = document.getElementById('calendar-grid-view');
  const listView = document.getElementById('calendar-list-view');
  const tabCal = document.getElementById('tab-calendar');
  const tabList = document.getElementById('tab-list');

  if (view === 'calendar') {
    gridView.classList.remove('hidden');
    listView.classList.add('hidden');
    tabCal.className = 'px-3 py-1.5 rounded-lg bg-white text-emerald-700 shadow-xs flex items-center space-x-1 transition';
    tabList.className = 'px-3 py-1.5 rounded-lg hover:text-slate-900 flex items-center space-x-1 transition';
  } else {
    gridView.classList.add('hidden');
    listView.classList.remove('hidden');
    tabCal.className = 'px-3 py-1.5 rounded-lg hover:text-slate-900 flex items-center space-x-1 transition';
    tabList.className = 'px-3 py-1.5 rounded-lg bg-white text-emerald-700 shadow-xs flex items-center space-x-1 transition';
  }
}

function resetToCurrentMonth() {
  const now = new Date();
  currentYear = now.getFullYear();
  currentMonth = now.getMonth() + 1;
  loadCalendar();
}

function changeMonth(delta) {
  currentMonth += delta;
  if (currentMonth < 1) {
    currentMonth = 12;
    currentYear -= 1;
  } else if (currentMonth > 12) {
    currentMonth = 1;
    currentYear += 1;
  }
  loadCalendar();
}

// 5. 個人設定モーダル
function openSettingsModal() {
  if (!currentDashboardData) return;
  const u = currentDashboardData.user;
  document.getElementById('setting-hourly-wage').value = u.hourly_wage;
  document.getElementById('setting-paid-leave-granted').value = u.paid_leave_granted;
  document.getElementById('setting-paid-leave-carried').value = u.paid_leave_carried;
  document.getElementById('setting-paid-leave-base-date').value = u.paid_leave_base_date || '';
  document.getElementById('settings-modal').classList.remove('hidden');
}

function closeSettingsModal() {
  document.getElementById('settings-modal').classList.add('hidden');
}

async function handleSaveSettings(e) {
  e.preventDefault();
  const wage = parseInt(document.getElementById('setting-hourly-wage').value, 10);
  const granted = parseFloat(document.getElementById('setting-paid-leave-granted').value);
  const carried = parseFloat(document.getElementById('setting-paid-leave-carried').value);
  const baseDate = document.getElementById('setting-paid-leave-base-date').value || null;

  try {
    const res = await fetch('/api/me/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        hourly_wage: wage,
        paid_leave_granted: granted,
        paid_leave_carried: carried,
        paid_leave_base_date: baseDate
      })
    });

    if (!res.ok) throw new Error('設定の保存に失敗しました');

    showToast('設定を更新しました');
    closeSettingsModal();
    loadDashboard();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 6. 打刻修正申請モーダル
function openCorrectionModal() {
  const todayStr = new Date().toISOString().slice(0, 10);
  openCorrectionModalForDate(todayStr);
}

function openCorrectionModalForDate(dateStr) {
  document.getElementById('corr-target-date').value = dateStr;
  document.getElementById('corr-clock-in').value = '09:00';
  document.getElementById('corr-clock-out').value = '18:00';
  document.getElementById('corr-break-minutes').value = '60';
  document.getElementById('corr-reason').value = '';
  document.getElementById('correction-modal').classList.remove('hidden');
}

function closeCorrectionModal() {
  document.getElementById('correction-modal').classList.add('hidden');
}

async function handleCorrectionSubmit(e) {
  e.preventDefault();
  const targetDate = document.getElementById('corr-target-date').value;
  const clockIn = document.getElementById('corr-clock-in').value;
  const clockOut = document.getElementById('corr-clock-out').value;
  const breakMinutes = parseInt(document.getElementById('corr-break-minutes').value, 10);
  const reason = document.getElementById('corr-reason').value.trim();

  try {
    const res = await fetch('/api/me/correction-request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        target_date: targetDate,
        requested_clock_in: clockIn,
        requested_clock_out: clockOut,
        requested_break_minutes: breakMinutes,
        reason: reason
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || '申請に失敗しました');
    }

    showToast('打刻修正申請を管理者に送信しました');
    closeCorrectionModal();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 7. シフト希望（休み希望・有休希望）モーダル
function openShiftRequestModal(targetDate = null) {
  const dateInput = document.getElementById('req-target-date');
  if (targetDate) {
    dateInput.value = targetDate;
  } else {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
  document.getElementById('req-reason').value = '';
  document.getElementById('shift-request-modal').classList.remove('hidden');
  loadMyShiftRequests();
}

function closeShiftRequestModal() {
  document.getElementById('shift-request-modal').classList.add('hidden');
}

async function loadMyShiftRequests() {
  try {
    const res = await fetch('/api/me/shift-requests');
    if (!res.ok) throw new Error('希望履歴の取得に失敗しました');

    const list = await res.json();
    const tbody = document.getElementById('my-shift-requests-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="py-4 text-center text-slate-400">提出済みのシフト希望はありません</td></tr>';
      return;
    }

    list.forEach(item => {
      const tr = document.createElement('tr');

      let typeBadge = item.request_type === 'OFF'
        ? '<span class="bg-rose-100 text-rose-800 font-bold px-2 py-0.5 rounded text-[10px]">🏖️ 希望休</span>'
        : '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[10px]">🌿 有休希望</span>';

      let statusBadge = '';
      if (item.status === 'PENDING') {
        statusBadge = '<span class="bg-amber-100 text-amber-800 font-bold px-2 py-0.5 rounded text-[10px]">審査待ち</span>';
      } else if (item.status === 'APPROVED') {
        statusBadge = '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[10px]">承認済</span>';
      } else {
        statusBadge = '<span class="bg-slate-100 text-slate-500 font-bold px-2 py-0.5 rounded text-[10px]">却下</span>';
      }

      let actionBtn = '-';
      if (item.status === 'PENDING') {
        actionBtn = `
          <button onclick="cancelShiftRequest(${item.id})" class="text-rose-500 hover:text-rose-700 hover:underline font-bold text-[11px]">
            取消
          </button>
        `;
      }

      tr.innerHTML = `
        <td class="py-2.5 px-3 font-mono font-semibold">${item.date}</td>
        <td class="py-2.5 px-3">${typeBadge}</td>
        <td class="py-2.5 px-3 text-slate-600 truncate max-w-[120px]" title="${item.reason || ''}">${item.reason || '-'}</td>
        <td class="py-2.5 px-3 text-center">${statusBadge}</td>
        <td class="py-2.5 px-3 text-center">${actionBtn}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

async function handleShiftRequestSubmit(e) {
  e.preventDefault();
  const dateStr = document.getElementById('req-target-date').value;
  const reqType = document.getElementById('req-type').value;
  const reason = document.getElementById('req-reason').value.trim();

  try {
    const res = await fetch('/api/me/shift-requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        date: dateStr,
        request_type: reqType,
        reason: reason
      })
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'シフト希望の提出に失敗しました');
    }

    showToast('シフト希望を提出しました！');
    await loadMyShiftRequests();
    await loadCalendar();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function cancelShiftRequest(id) {
  if (!confirm('このシフト希望を取り消しますか？')) return;

  try {
    const res = await fetch(`/api/me/shift-requests/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('取消に失敗しました');

    showToast('シフト希望を取り消しました');
    await loadMyShiftRequests();
    await loadCalendar();
  } catch (err) {
    showToast(err.message, 'error');
  }
}
