let adminYear = new Date().getFullYear();
let adminMonth = new Date().getMonth() + 1;
let staffList = [];

document.addEventListener('DOMContentLoaded', async () => {
  // 当月をCSV初期値に設定
  const monthInput = document.getElementById('csv-target-month');
  if (monthInput) {
    monthInput.value = `${adminYear}-${String(adminMonth).padStart(2, '0')}`;
  }

  // 自動生成モーダルの年月初期値
  const autoGenMonth = document.getElementById('auto-gen-month');
  if (autoGenMonth) {
    autoGenMonth.value = `${adminYear}-${String(adminMonth).padStart(2, '0')}`;
  }

  await loadStaffUsers();
  loadAttendanceSummary();
  loadShiftRequests();
  loadCorrectionRequests();
  loadAdminShifts();
});

// 1. スタッフ一覧取得（シフト登録・雇用条件モーダルのセレクトボックス）
async function loadStaffUsers() {
  try {
    const res = await fetch('/api/admin/users');
    if (res.status === 401 || res.status === 403) {
      window.location.href = '/login';
      return;
    }
    staffList = await res.json();

    const select = document.getElementById('shift-user-select');
    if (select) {
      select.innerHTML = staffList
        .map(u => `<option value="${u.id}">${u.full_name} (${u.role === 'admin' ? '管理者' : u.username})</option>`)
        .join('');
    }

    const condSelect = document.getElementById('condition-user-select');
    if (condSelect) {
      const currentVal = condSelect.value;
      condSelect.innerHTML = staffList
        .map(u => `<option value="${u.id}">${u.full_name} (${u.role === 'admin' ? '管理者' : u.username})</option>`)
        .join('');
      if (currentVal && staffList.some(u => String(u.id) === String(currentVal))) {
        condSelect.value = currentVal;
      }
    }

    const filterSelect = document.getElementById('admin-staff-filter');
    if (filterSelect) {
      const currentFilter = filterSelect.value || 'ALL';
      filterSelect.innerHTML = '<option value="ALL">全スタッフ表示</option>' +
        staffList.map(u => `<option value="${u.id}">${u.full_name} (${u.role === 'admin' ? '管理者' : 'スタッフ'})</option>`).join('');
      if (staffList.some(u => String(u.id) === currentFilter) || currentFilter === 'ALL') {
        filterSelect.value = currentFilter;
      }
    }
  } catch (err) {
    console.error(err);
  }
}

// 2. リアルタイム出勤モニタリング
async function loadAttendanceSummary() {
  try {
    const today = new Date();
    const dateStr = `${today.getFullYear()}年${today.getMonth() + 1}月${today.getDate()}日`;
    document.getElementById('today-monitor-date').textContent = `${dateStr} のリアルタイム稼働状況`;

    const res = await fetch('/api/admin/attendance/summary');
    if (!res.ok) throw new Error('勤怠サマリー取得失敗');

    const data = await res.json();
    const tbody = document.getElementById('attendance-summary-tbody');
    tbody.innerHTML = '';

    if (data.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="py-6 text-center text-slate-400">登録されたスタッフがいません</td></tr>';
      return;
    }

    data.forEach(item => {
      const tr = document.createElement('tr');

      // シフト表示
      let shiftText = '<span class="text-slate-300">シフトなし</span>';
      if (item.shift) {
        if (item.shift.shift_type === 'NORMAL') {
          shiftText = `<span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded font-medium">${item.shift.start_time || ''} - ${item.shift.end_time || ''}</span>`;
        } else if (item.shift.shift_type === 'PAID_LEAVE') {
          shiftText = `<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded">有給休暇</span>`;
        } else {
          shiftText = `<span class="bg-slate-100 text-slate-500 px-2 py-0.5 rounded">公休</span>`;
        }
      }

      // 状況バッジ
      const statusClassMap = {
        '未出勤': 'bg-slate-100 text-slate-600',
        '勤務中': 'bg-emerald-100 text-emerald-800 font-bold',
        '休憩中': 'bg-amber-100 text-amber-800 font-bold',
        '退勤済': 'bg-blue-50 text-blue-700',
        '有給休暇': 'bg-emerald-100 text-emerald-800',
        '公休': 'bg-slate-100 text-slate-500'
      };
      const statusBadge = `<span class="px-2.5 py-1 rounded-full text-[11px] ${statusClassMap[item.status_text] || 'bg-slate-100'}">${item.status_text}</span>`;

      // 打刻
      const cin = item.record && item.record.clock_in ? item.record.clock_in : '-';
      const cout = item.record && item.record.clock_out ? item.record.clock_out : '-';
      
      let workH = '-';
      if (item.record && item.record.total_work_minutes > 0) {
        const h = Math.floor(item.record.total_work_minutes / 60);
        const m = item.record.total_work_minutes % 60;
        workH = `${h}時間${m}分`;
      }

      // アラート
      let alertContent = '<span class="text-slate-300">-</span>';
      if (item.is_alert) {
        alertContent = `<span class="inline-flex items-center text-rose-600 font-bold bg-rose-50 px-2 py-1 rounded text-[11px]"><i data-lucide="alert-circle" class="w-3.5 h-3.5 mr-1"></i>${item.alert_message}</span>`;
      }

      tr.innerHTML = `
        <td class="py-3 px-4 font-bold text-slate-800">${item.full_name}</td>
        <td class="py-3 px-4">${shiftText}</td>
        <td class="py-3 px-4">${statusBadge}</td>
        <td class="py-3 px-4 font-mono">${cin}</td>
        <td class="py-3 px-4 font-mono">${cout}</td>
        <td class="py-3 px-4 font-semibold text-slate-700">${workH}</td>
        <td class="py-3 px-4">${alertContent}</td>
      `;
      tbody.appendChild(tr);
    });

    lucide.createIcons({ root: tbody });
  } catch (err) {
    console.error(err);
  }
}

// 2.5 シフト希望（休み希望・有休希望）一覧・審査
async function loadShiftRequests() {
  try {
    const res = await fetch('/api/admin/shift-requests');
    if (!res.ok) throw new Error('シフト希望取得失敗');

    const list = await res.json();
    const tbody = document.getElementById('shift-requests-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const pendingList = list.filter(r => r.status === 'PENDING');
    const badge = document.getElementById('shift-requests-pending-badge');
    if (badge) {
      badge.textContent = `審査待ち: ${pendingList.length}件`;
    }

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="py-6 text-center text-slate-400">現在、シフト希望（休み希望）はありません</td></tr>';
      return;
    }

    list.forEach(item => {
      const tr = document.createElement('tr');

      let typeBadge = '';
      if (item.request_type === 'OFF') {
        typeBadge = '<span class="bg-rose-100 text-rose-800 font-bold px-2 py-0.5 rounded text-[11px]">🏖️ 希望休</span>';
      } else {
        typeBadge = '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[11px]">🌿 有休希望</span>';
      }

      let statusBadge = '';
      if (item.status === 'PENDING') {
        statusBadge = '<span class="bg-amber-100 text-amber-800 font-bold px-2 py-0.5 rounded text-[10px]">審査待ち</span>';
      } else if (item.status === 'APPROVED') {
        statusBadge = '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[10px]">承認済</span>';
      } else {
        statusBadge = '<span class="bg-slate-100 text-slate-500 font-bold px-2 py-0.5 rounded text-[10px]">却下</span>';
      }

      let actionButtons = '-';
      if (item.status === 'PENDING') {
        actionButtons = `
          <div class="flex items-center justify-center space-x-2">
            <button onclick="reviewShiftRequest(${item.id}, 'APPROVED')" class="bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1 rounded-lg text-xs font-bold transition shadow-xs">
              承認
            </button>
            <button onclick="reviewShiftRequest(${item.id}, 'REJECTED')" class="bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 px-2.5 py-1 rounded-lg text-xs font-bold transition">
              却下
            </button>
          </div>
        `;
      }

      tr.innerHTML = `
        <td class="py-3 px-4 font-bold text-slate-800">${item.user_name || 'スタッフ'}</td>
        <td class="py-3 px-4 font-mono font-semibold">${item.date}</td>
        <td class="py-3 px-4">${typeBadge}</td>
        <td class="py-3 px-4 text-slate-600 max-w-xs truncate" title="${item.reason || '特になし'}">${item.reason || '特になし'}</td>
        <td class="py-3 px-4 text-center">${statusBadge}</td>
        <td class="py-3 px-4 text-center">${actionButtons}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

async function reviewShiftRequest(id, status) {
  const comment = prompt(status === 'APPROVED' ? '承認コメント（任意）:' : '却下理由（任意）:');
  if (comment === null) return;

  try {
    const res = await fetch(`/api/admin/shift-requests/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status, admin_comment: comment })
    });

    if (!res.ok) throw new Error('審査処理に失敗しました');

    showToast(`シフト希望を${status === 'APPROVED' ? '承認' : '却下'}しました`);
    loadShiftRequests();
    loadAdminShifts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 3. 打刻修正申請一覧・審査
async function loadCorrectionRequests() {
  try {
    const res = await fetch('/api/admin/correction-requests');
    if (!res.ok) throw new Error('修正申請取得失敗');

    const list = await res.json();
    const tbody = document.getElementById('correction-requests-tbody');
    tbody.innerHTML = '';

    const pendingList = list.filter(r => r.status === 'PENDING');
    document.getElementById('pending-count-badge').textContent = `保留中: ${pendingList.length}件`;

    if (list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="py-6 text-center text-slate-400">現在、修正申請はありません</td></tr>';
      return;
    }

    list.forEach(item => {
      const tr = document.createElement('tr');

      const cinStr = item.requested_clock_in ? new Date(item.requested_clock_in).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : '-';
      const coutStr = item.requested_clock_out ? new Date(item.requested_clock_out).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : '-';

      let statusBadge = '';
      if (item.status === 'PENDING') {
        statusBadge = '<span class="bg-amber-100 text-amber-800 font-bold px-2 py-0.5 rounded text-[10px]">審査待ち</span>';
      } else if (item.status === 'APPROVED') {
        statusBadge = '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[10px]">承認済</span>';
      } else {
        statusBadge = '<span class="bg-rose-100 text-rose-800 font-bold px-2 py-0.5 rounded text-[10px]">却下</span>';
      }

      let actionButtons = '-';
      if (item.status === 'PENDING') {
        actionButtons = `
          <div class="flex items-center justify-center space-x-2">
            <button onclick="reviewCorrection(${item.id}, 'APPROVED')" class="bg-emerald-600 hover:bg-emerald-700 text-white px-2.5 py-1 rounded-lg text-xs font-bold transition shadow-xs">
              承認
            </button>
            <button onclick="reviewCorrection(${item.id}, 'REJECTED')" class="bg-rose-50 hover:bg-rose-100 text-rose-600 border border-rose-200 px-2.5 py-1 rounded-lg text-xs font-bold transition">
              却下
            </button>
          </div>
        `;
      }

      tr.innerHTML = `
        <td class="py-3 px-4 font-bold text-slate-800">${item.user_name || 'スタッフ'}</td>
        <td class="py-3 px-4">${item.target_date}</td>
        <td class="py-3 px-4 font-mono font-semibold text-slate-700">${cinStr} 〜 ${coutStr}</td>
        <td class="py-3 px-4">${item.requested_break_minutes}分</td>
        <td class="py-3 px-4 text-slate-600 max-w-xs truncate" title="${item.reason}">${item.reason}</td>
        <td class="py-3 px-4 text-center">${statusBadge}</td>
        <td class="py-3 px-4 text-center">${actionButtons}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error(err);
  }
}

async function reviewCorrection(id, status) {
  const comment = prompt(status === 'APPROVED' ? '承認時のコメント（任意）:' : '却下理由（任意）:');
  if (comment === null) return;

  try {
    const res = await fetch(`/api/admin/correction-requests/${id}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: status, admin_comment: comment })
    });

    if (!res.ok) throw new Error('審査処理に失敗しました');

    showToast(`申請を${status === 'APPROVED' ? '承認' : '却下'}しました`);
    loadCorrectionRequests();
    loadAttendanceSummary();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 4. シフト管理
async function loadAdminShifts() {
  try {
    document.getElementById('admin-calendar-title').textContent = `${adminYear}年${adminMonth}月`;
    const res = await fetch(`/api/admin/shifts?year=${adminYear}&month=${adminMonth}`);
    if (!res.ok) throw new Error('シフト取得失敗');

    let shifts = await res.json();

    // スタッフ絞り込みフィルター適用
    const filterVal = document.getElementById('admin-staff-filter')?.value;
    if (filterVal && filterVal !== 'ALL') {
      const selectedUserId = parseInt(filterVal, 10);
      shifts = shifts.filter(s => s.user_id === selectedUserId);
    }

    renderAdminCalendarGrid(shifts);
    renderAdminCalendarList(shifts);
  } catch (err) {
    console.error(err);
  }
}

// 管理者用 7列月間グリッドカレンダー（メイン表示）
function renderAdminCalendarGrid(shifts) {
  const container = document.getElementById('admin-calendar-grid-cells');
  if (!container) return;
  container.innerHTML = '';

  const firstDay = new Date(adminYear, adminMonth - 1, 1);
  const lastDay = new Date(adminYear, adminMonth, 0);
  const totalDays = lastDay.getDate();
  const startDayOfWeek = firstDay.getDay(); // 0=日, ..., 6=土

  // 日付ごとのシフトにグループ化
  const shiftsByDate = {};
  shifts.forEach(s => {
    if (!shiftsByDate[s.date]) shiftsByDate[s.date] = [];
    shiftsByDate[s.date].push(s);
  });

  // 月初の前の余白セル
  for (let i = 0; i < startDayOfWeek; i++) {
    const blank = document.createElement('div');
    blank.className = 'min-h-[90px] sm:min-h-[120px] p-1.5 sm:p-2 rounded-xl bg-slate-50/40 border border-slate-100/60 opacity-30';
    container.appendChild(blank);
  }

  const todayStr = new Date().toISOString().slice(0, 10);

  // 1日〜末日
  for (let day = 1; day <= totalDays; day++) {
    const dateObj = new Date(adminYear, adminMonth - 1, day);
    const dateStr = `${adminYear}-${String(adminMonth).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayOfWeek = dateObj.getDay();
    const isToday = dateStr === todayStr;

    let dayNumColor = 'text-slate-800';
    if (dayOfWeek === 0) dayNumColor = 'text-rose-600 font-black';
    if (dayOfWeek === 6) dayNumColor = 'text-blue-600 font-black';

    const cell = document.createElement('div');
    cell.className = `min-h-[125px] sm:min-h-[145px] p-1.5 sm:p-2 rounded-2xl border transition-all ${
      isToday 
        ? 'bg-indigo-50/50 border-indigo-300 ring-1 ring-indigo-200' 
        : 'bg-white border-slate-200 hover:border-slate-300 shadow-2xs'
    } group`;
    cell.onclick = (e) => {
      if (e.target.closest('button')) return;
      openAddShiftModal(dateStr);
    };

    const headerHtml = `
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs sm:text-sm font-black ${isToday ? 'bg-indigo-600 text-white w-5 h-5 rounded-full flex items-center justify-center text-[10px]' : dayNumColor}">
          ${day}
        </span>
        <div class="flex items-center space-x-1 no-print">
          ${isToday ? '<span class="text-[9px] font-black text-indigo-700 bg-indigo-100 px-1 rounded hidden sm:inline">今日</span>' : ''}
          <button onclick="event.stopPropagation(); openAddShiftModal('${dateStr}')" class="opacity-0 group-hover:opacity-100 text-indigo-600 hover:text-indigo-800 p-0.5 rounded hover:bg-indigo-50 transition" title="この日にシフト追加">
            <i data-lucide="plus" class="w-3.5 h-3.5"></i>
          </button>
        </div>
      </div>
    `;

    const dayShifts = shiftsByDate[dateStr] || [];
    let shiftItemsHtml = '';

    if (dayShifts.length > 0) {
      shiftItemsHtml = dayShifts.map(s => {
        const staffColor = s.user_color || '#059669';

        let badgeStyle = `background-color: ${staffColor}15; border-left: 3.5px solid ${staffColor}; border-top: 1px solid ${staffColor}30; border-right: 1px solid ${staffColor}30; border-bottom: 1px solid ${staffColor}30;`;
        let typeText = `${s.start_time || ''}〜${s.end_time || ''}`;
        
        if (s.shift_type === 'PAID_LEAVE') {
          badgeStyle = `background-color: #ecfdf5; border-left: 3.5px solid #059669; border: 1px solid #10b981;`;
          typeText = '有給休暇';
        } else if (s.shift_type === 'HOLIDAY') {
          badgeStyle = `background-color: #f1f5f9; border-left: 3.5px solid #64748b;`;
          typeText = '公休';
        }

        // 表示用通称名の抽出（例: 「三宅 興之（薬局長）」→「三宅」、「小林 彩乃（薬剤師）」→「小林彩乃」、「寺内（調剤事務）」→「寺内」）
        let shortName = s.user_name || 'スタッフ';
        if (shortName.includes('（')) shortName = shortName.split('（')[0].trim();
        else if (shortName.includes('(')) shortName = shortName.split('(')[0].trim();
        if (shortName.includes(' ') && shortName.length > 3) {
          shortName = shortName.split(' ')[0];
        }

        return `
          <div style="${badgeStyle}" class="shift-badge-print mt-1 rounded-lg px-1.5 py-1 text-[10px] sm:text-[11px] flex items-center justify-between group/item leading-tight shadow-2xs">
            <span class="flex items-center space-x-1 overflow-visible">
              <strong class="font-extrabold text-slate-900 whitespace-nowrap">${shortName}</strong>
              <span class="font-semibold text-slate-700 whitespace-nowrap text-[9px] sm:text-[10px]">${typeText}</span>
            </span>
            <button onclick="event.stopPropagation(); deleteShift(${s.id})" class="shift-delete-btn opacity-0 group-hover/item:opacity-100 text-rose-500 hover:text-rose-700 ml-1 flex-shrink-0 font-bold" title="削除">
              &times;
            </button>
          </div>
        `;
      }).join('');
    } else {
      shiftItemsHtml = `
        <div class="mt-2 text-center text-[10px] text-slate-300 group-hover:text-slate-400 py-1 transition no-print">
          + 追加
        </div>
      `;
    }

    cell.innerHTML = `
      <div>
        ${headerHtml}
        <div class="space-y-1 max-h-[110px] sm:max-h-[135px] overflow-y-auto">
          ${shiftItemsHtml}
        </div>
      </div>
    `;

    container.appendChild(cell);
  }

  // 末尾の余白セル
  const totalCells = startDayOfWeek + totalDays;
  const remainingCells = (7 - (totalCells % 7)) % 7;
  for (let i = 0; i < remainingCells; i++) {
    const blank = document.createElement('div');
    blank.className = 'min-h-[125px] sm:min-h-[145px] p-1.5 sm:p-2 rounded-2xl bg-slate-50/40 border border-slate-100/60 opacity-30';
    container.appendChild(blank);
  }

  lucide.createIcons({ root: container });
}

// 管理者用 リスト表示（補助）
function renderAdminCalendarList(shifts) {
  const tbody = document.getElementById('shifts-tbody');
  if (!tbody) return;
  tbody.innerHTML = '';

  if (shifts.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="py-6 text-center text-slate-400">当月の登録シフトはありません。「シフト追加」から登録してください</td></tr>';
    return;
  }

  shifts.sort((a, b) => a.date.localeCompare(b.date));

  shifts.forEach(s => {
    const tr = document.createElement('tr');

    let typeBadge = '';
    if (s.shift_type === 'NORMAL') {
      typeBadge = '<span class="bg-slate-100 text-slate-700 px-2 py-0.5 rounded text-[11px]">通常</span>';
    } else if (s.shift_type === 'PAID_LEAVE') {
      typeBadge = '<span class="bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded text-[11px]">有給休暇</span>';
    } else {
      typeBadge = '<span class="bg-slate-100 text-slate-500 px-2 py-0.5 rounded text-[11px]">公休</span>';
    }

    const timeRange = s.shift_type === 'NORMAL' && s.start_time ? `${s.start_time} - ${s.end_time}` : '-';

    tr.innerHTML = `
      <td class="py-3 px-4 font-mono">${s.date}</td>
      <td class="py-3 px-4 font-bold text-slate-800">${s.user_name}</td>
      <td class="py-3 px-4">${typeBadge}</td>
      <td class="py-3 px-4 font-mono font-medium">${timeRange}</td>
      <td class="py-3 px-4">${s.shift_type === 'NORMAL' ? `${s.break_minutes}分` : '-'}</td>
      <td class="py-3 px-4 text-slate-500">${s.note || '-'}</td>
      <td class="py-3 px-4 text-center">
        <button onclick="deleteShift(${s.id})" class="text-rose-500 hover:text-rose-700 p-1 rounded hover:bg-rose-50 transition" title="削除">
          <i data-lucide="trash-2" class="w-4 h-4"></i>
        </button>
      </td>
    `;
    tbody.appendChild(tr);
  });

  lucide.createIcons({ root: tbody });
}

function switchAdminView(view) {
  const gridView = document.getElementById('admin-calendar-grid-view');
  const listView = document.getElementById('admin-calendar-list-view');
  const tabCal = document.getElementById('admin-tab-calendar');
  const tabList = document.getElementById('admin-tab-list');

  if (view === 'calendar') {
    gridView.classList.remove('hidden');
    listView.classList.add('hidden');
    tabCal.className = 'px-3 py-1.5 rounded-lg bg-white text-indigo-700 shadow-xs flex items-center space-x-1 transition';
    tabList.className = 'px-3 py-1.5 rounded-lg hover:text-slate-900 flex items-center space-x-1 transition';
  } else {
    gridView.classList.add('hidden');
    listView.classList.remove('hidden');
    tabCal.className = 'px-3 py-1.5 rounded-lg hover:text-slate-900 flex items-center space-x-1 transition';
    tabList.className = 'px-3 py-1.5 rounded-lg bg-white text-indigo-700 shadow-xs flex items-center space-x-1 transition';
  }
}

function resetAdminToCurrentMonth() {
  const now = new Date();
  adminYear = now.getFullYear();
  adminMonth = now.getMonth() + 1;
  loadAdminShifts();
}

function changeAdminMonth(delta) {
  adminMonth += delta;
  if (adminMonth < 1) {
    adminMonth = 12;
    adminYear -= 1;
  } else if (adminMonth > 12) {
    adminMonth = 1;
    adminYear += 1;
  }
  loadAdminShifts();
}

function openAddShiftModal(targetDate = null) {
  const dateInput = document.getElementById('shift-date');
  if (targetDate) {
    dateInput.value = targetDate;
  } else {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
  document.getElementById('shift-type').value = 'NORMAL';
  toggleShiftTypeFields();
  document.getElementById('shift-modal').classList.remove('hidden');
}

function closeAddShiftModal() {
  document.getElementById('shift-modal').classList.add('hidden');
}

function toggleShiftTypeFields() {
  const type = document.getElementById('shift-type').value;
  const timeGroup = document.getElementById('shift-time-group');
  const breakGroup = document.getElementById('shift-break-group');
  if (type === 'NORMAL') {
    timeGroup.classList.remove('hidden');
    breakGroup.classList.remove('hidden');
  } else {
    timeGroup.classList.add('hidden');
    breakGroup.classList.add('hidden');
  }
}

async function handleShiftSubmit(e) {
  e.preventDefault();
  const userId = parseInt(document.getElementById('shift-user-select').value, 10);
  const dateStr = document.getElementById('shift-date').value;
  const shiftType = document.getElementById('shift-type').value;
  const startTime = shiftType === 'NORMAL' ? document.getElementById('shift-start-time').value : null;
  const endTime = shiftType === 'NORMAL' ? document.getElementById('shift-end-time').value : null;
  const breakMinutes = shiftType === 'NORMAL' ? parseInt(document.getElementById('shift-break-minutes').value, 10) : 0;
  const note = document.getElementById('shift-note').value.trim();

  try {
    const res = await fetch('/api/admin/shifts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        date: dateStr,
        shift_type: shiftType,
        start_time: startTime,
        end_time: endTime,
        break_minutes: breakMinutes,
        note: note
      })
    });

    if (!res.ok) throw new Error('シフト登録に失敗しました');

    showToast('シフトを登録しました');
    closeAddShiftModal();
    loadAdminShifts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function deleteShift(id) {
  if (!confirm('このシフトを削除しますか？')) return;
  try {
    const res = await fetch(`/api/admin/shifts/${id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('シフト削除に失敗しました');
    showToast('シフトを削除しました');
    loadAdminShifts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 5. CSVダウンロード
function downloadCsv() {
  const monthVal = document.getElementById('csv-target-month').value;
  if (!monthVal) {
    showToast('対象年月を選択してください', 'error');
    return;
  }
  const [y, m] = monthVal.split('-');
  window.location.href = `/api/admin/export-csv?year=${parseInt(y, 10)}&month=${parseInt(m, 10)}`;
}

// 6. 薬局貼り出し用「月間シフト表 印刷機能」
function printShiftTable() {
  // 印刷ヘッダーにタイトルと印刷日時を反映
  const titleEl = document.getElementById('print-sheet-title');
  if (titleEl) {
    titleEl.textContent = `${adminYear}年${adminMonth}月度 勤務シフト表`;
  }
  const timeEl = document.getElementById('print-timestamp');
  if (timeEl) {
    const now = new Date();
    timeEl.textContent = `${now.getFullYear()}/${now.getMonth() + 1}/${now.getDate()} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  }

  // カレンダー表示タブに切り替えてから印刷
  switchAdminView('calendar');
  window.print();
}

// 7. 雇用条件設定モーダル
function openConditionModal() {
  const select = document.getElementById('condition-user-select');
  if (select) {
    if (!select.value && select.options.length > 0) {
      select.selectedIndex = 0;
    }
    onConditionUserChange();
  }
  document.getElementById('condition-modal').classList.remove('hidden');
}

function closeConditionModal() {
  document.getElementById('condition-modal').classList.add('hidden');
}

const WEEKDAYS = [
  { id: 0, name: '月', color: 'text-slate-800' },
  { id: 1, name: '火', color: 'text-slate-800' },
  { id: 2, name: '水', color: 'text-slate-800' },
  { id: 3, name: '木', color: 'text-slate-800' },
  { id: 4, name: '金', color: 'text-slate-800' },
  { id: 5, name: '土', color: 'text-blue-600' },
  { id: 6, name: '日', color: 'text-rose-600' }
];

function renderWeekdayTable(tbodyId, prefix, scheduleJson, fallbackWorkDays, fallbackStart, fallbackEnd, fallbackBreak) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  tbody.innerHTML = '';

  let scheduleMap = {};
  if (scheduleJson) {
    try {
      scheduleMap = typeof scheduleJson === 'string' ? JSON.parse(scheduleJson) : scheduleJson;
    } catch (e) {
      scheduleMap = {};
    }
  }

  const workDayList = (fallbackWorkDays || '0,1,2,4,5').split(',').map(s => s.trim());
  const dStart = fallbackStart || '09:00';
  const dEnd = fallbackEnd || '18:00';
  const dBreak = fallbackBreak !== undefined ? fallbackBreak : 60;

  WEEKDAYS.forEach(day => {
    const dStr = String(day.id);
    const daySetting = scheduleMap[dStr];

    const isChecked = daySetting ? Boolean(daySetting.work) : workDayList.includes(dStr);
    const sTime = daySetting ? (daySetting.start || dStart) : (day.id === 3 || day.id === 5 ? '09:00' : dStart);
    const eTime = daySetting ? (daySetting.end || dEnd) : (day.id === 3 || day.id === 5 ? '13:00' : dEnd);
    const bMin = daySetting ? (daySetting.break !== undefined ? daySetting.break : dBreak) : (day.id === 3 || day.id === 5 ? 0 : dBreak);

    const tr = document.createElement('tr');
    tr.className = isChecked ? 'hover:bg-purple-50/40' : 'bg-slate-50/60 opacity-60';
    tr.innerHTML = `
      <td class="py-2 px-3 text-center font-bold ${day.color}">${day.name}</td>
      <td class="py-2 px-2 text-center">
        <input type="checkbox" id="${prefix}-work-${day.id}" ${isChecked ? 'checked' : ''}
          onchange="toggleWeekdayRow('${prefix}', ${day.id})"
          class="w-4 h-4 text-purple-600 rounded border-slate-300 focus:ring-purple-500 cursor-pointer">
      </td>
      <td class="py-2 px-2">
        <input type="time" id="${prefix}-start-${day.id}" value="${sTime}" ${isChecked ? '' : 'disabled'}
          class="px-2 py-1 rounded-lg border border-slate-200 text-xs w-full focus:ring-1 focus:ring-purple-500 focus:outline-none disabled:bg-slate-100 disabled:text-slate-400">
      </td>
      <td class="py-2 px-2">
        <input type="time" id="${prefix}-end-${day.id}" value="${eTime}" ${isChecked ? '' : 'disabled'}
          class="px-2 py-1 rounded-lg border border-slate-200 text-xs w-full focus:ring-1 focus:ring-purple-500 focus:outline-none disabled:bg-slate-100 disabled:text-slate-400">
      </td>
      <td class="py-2 px-2">
        <input type="number" id="${prefix}-break-${day.id}" value="${bMin}" min="0" step="5" ${isChecked ? '' : 'disabled'}
          class="px-2 py-1 rounded-lg border border-slate-200 text-xs w-full focus:ring-1 focus:ring-purple-500 focus:outline-none disabled:bg-slate-100 disabled:text-slate-400">
      </td>
    `;
    tbody.appendChild(tr);
  });
}

function toggleWeekdayRow(prefix, dayId) {
  const cb = document.getElementById(`${prefix}-work-${dayId}`);
  const sInput = document.getElementById(`${prefix}-start-${dayId}`);
  const eInput = document.getElementById(`${prefix}-end-${dayId}`);
  const bInput = document.getElementById(`${prefix}-break-${dayId}`);
  const tr = cb.closest('tr');

  if (cb.checked) {
    tr.classList.remove('bg-slate-50/60', 'opacity-60');
    tr.classList.add('hover:bg-purple-50/40');
    sInput.disabled = false;
    eInput.disabled = false;
    bInput.disabled = false;
  } else {
    tr.classList.add('bg-slate-50/60', 'opacity-60');
    tr.classList.remove('hover:bg-purple-50/40');
    sInput.disabled = true;
    eInput.disabled = true;
    bInput.disabled = true;
  }
}

function getWeeklyScheduleFromTable(prefix) {
  const scheduleMap = {};
  const checkedDays = [];

  WEEKDAYS.forEach(day => {
    const cb = document.getElementById(`${prefix}-work-${day.id}`);
    const sInput = document.getElementById(`${prefix}-start-${day.id}`);
    const eInput = document.getElementById(`${prefix}-end-${day.id}`);
    const bInput = document.getElementById(`${prefix}-break-${day.id}`);

    const isWork = cb ? cb.checked : false;
    if (isWork) checkedDays.push(String(day.id));

    scheduleMap[String(day.id)] = {
      work: isWork,
      start: sInput ? sInput.value : '09:00',
      end: eInput ? eInput.value : '18:00',
      break: bInput ? parseInt(bInput.value, 10) || 0 : 0
    };
  });

  return {
    scheduleJson: JSON.stringify(scheduleMap),
    workDaysStr: checkedDays.join(',')
  };
}

function onConditionUserChange() {
  const select = document.getElementById('condition-user-select');
  if (!select) return;
  const userId = parseInt(select.value, 10);
  const user = staffList.find(u => u.id === userId);
  if (!user) return;

  const nameInput = document.getElementById('cond-full-name');
  if (nameInput) {
    nameInput.value = user.full_name || '';
  }

  // 削除ボタンの制御（管理者は削除不可）
  const deleteBtn = document.getElementById('cond-delete-staff-btn');
  if (deleteBtn) {
    if (user.role === 'admin') {
      deleteBtn.classList.add('hidden');
    } else {
      deleteBtn.classList.remove('hidden');
    }
  }

  // 曜日別勤務時間テーブルを描画
  renderWeekdayTable(
    'cond-weekday-tbody',
    'cond',
    user.weekly_schedule,
    user.work_days,
    user.default_start_time ? user.default_start_time.slice(0, 5) : '09:00',
    user.default_end_time ? user.default_end_time.slice(0, 5) : '18:00',
    user.default_break_minutes
  );

  document.getElementById('cond-hourly-wage').value = user.hourly_wage || 1500;
  document.getElementById('cond-color-picker').value = user.color || '#059669';
}

async function handleDeleteStaff() {
  const select = document.getElementById('condition-user-select');
  if (!select) return;
  const userId = parseInt(select.value, 10);
  const user = staffList.find(u => u.id === userId);
  if (!user) return;

  if (!confirm(`スタッフ「${user.full_name}」を削除（退職・非表示）しますか？\n※カレンダーや過去データとの整合性を保つため非表示になります。`)) {
    return;
  }

  try {
    const res = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE' });
    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || '削除に失敗しました');
    }
    showToast('スタッフを削除しました');
    closeConditionModal();
    setTimeout(() => {
      window.location.reload();
    }, 600);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function setPresetColor(color) {
  const picker = document.getElementById('cond-color-picker');
  if (picker) {
    picker.value = color;
  }
}

async function handleConditionSubmit(e) {
  e.preventDefault();
  const userId = parseInt(document.getElementById('condition-user-select').value, 10);
  const fullName = document.getElementById('cond-full-name').value.trim();
  
  const { scheduleJson, workDaysStr } = getWeeklyScheduleFromTable('cond');
  const hourlyWage = parseInt(document.getElementById('cond-hourly-wage').value, 10);
  const color = document.getElementById('cond-color-picker').value;

  try {
    const res = await fetch(`/api/admin/users/${userId}/condition`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        full_name: fullName,
        work_days: workDaysStr,
        weekly_schedule: scheduleJson,
        hourly_wage: hourlyWage,
        color: color
      })
    });

    if (!res.ok) throw new Error('雇用条件の保存に失敗しました');

    showToast('社員情報・曜日別条件を保存しました');
    closeConditionModal();

    const headerNameEl = document.getElementById('header-user-name');
    if (headerNameEl && userId === 1) {
      headerNameEl.textContent = fullName;
    }

    setTimeout(() => {
      window.location.reload();
    }, 600);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 8. 1ヶ月分一括自動生成
function openAutoGenerateModal() {
  const autoGenMonth = document.getElementById('auto-gen-month');
  if (autoGenMonth) {
    autoGenMonth.value = `${adminYear}-${String(adminMonth).padStart(2, '0')}`;
  }
  document.getElementById('auto-generate-modal').classList.remove('hidden');
}

function closeAutoGenerateModal() {
  document.getElementById('auto-generate-modal').classList.add('hidden');
}

async function handleAutoGenerateSubmit(e) {
  e.preventDefault();
  const monthVal = document.getElementById('auto-gen-month').value;
  if (!monthVal) return;

  const [y, m] = monthVal.split('-');
  const year = parseInt(y, 10);
  const month = parseInt(m, 10);
  const overwrite = document.getElementById('auto-gen-overwrite').checked;

  try {
    const res = await fetch('/api/admin/shifts/auto-generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        year: year,
        month: month,
        overwrite: overwrite
      })
    });

    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '自動生成に失敗しました');

    showToast(`シフト一括生成完了: 新規${data.generated}件, 更新${data.updated}件（希望休${data.skipped_requests}件スキップ）`);
    closeAutoGenerateModal();

    // カレンダーの表示月を生成月に合わせる
    adminYear = year;
    adminMonth = month;
    loadAdminShifts();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// 9. 新規スタッフ追加モーダル
function openAddStaffModal() {
  renderWeekdayTable('new-weekday-tbody', 'new', null, '0,1,2,4,5', '09:00', '18:00', 60);
  document.getElementById('add-staff-modal').classList.remove('hidden');
}

function closeAddStaffModal() {
  document.getElementById('add-staff-modal').classList.add('hidden');
}

async function handleAddStaffSubmit(e) {
  e.preventDefault();
  const fullName = document.getElementById('new-full-name').value.trim();
  const username = document.getElementById('new-username').value.trim();
  const password = document.getElementById('new-password').value.trim();
  const hourlyWage = parseInt(document.getElementById('new-hourly-wage').value, 10) || 1500;
  const color = document.getElementById('new-color-picker').value;

  const { scheduleJson, workDaysStr } = getWeeklyScheduleFromTable('new');

  try {
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: username,
        password: password,
        full_name: fullName,
        hourly_wage: hourlyWage,
        color: color,
        work_days: workDaysStr,
        weekly_schedule: scheduleJson,
        default_start_time: '09:00',
        default_end_time: '18:00',
        default_break_minutes: 60
      })
    });

    if (!res.ok) {
      const data = await res.json();
      throw new Error(data.detail || 'スタッフの登録に失敗しました');
    }

    showToast(`新スタッフ「${fullName}」を登録しました`);
    closeAddStaffModal();
    setTimeout(() => {
      window.location.reload();
    }, 600);
  } catch (err) {
    showToast(err.message, 'error');
  }
}
