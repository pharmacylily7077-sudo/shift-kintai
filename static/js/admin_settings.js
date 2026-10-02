  async function loadStaffConditions() {
    const grid = document.getElementById('staff-conditions-grid');
    try {
      const res = await fetch('/api/admin/staff/conditions');
      if (!res.ok) return;
      const data = await res.json();
      staffConditionsData = data.staff || [];
      if (staffConditionsData.length === 0) {
        grid.innerHTML = '<div class="text-xs text-slate-400 py-6 text-center col-span-full">スタッフが見つかりません</div>';
        return;
      }
      grid.innerHTML = '';
      staffConditionsData.forEach(s => {
        const offText = s.fixed_off_labels.length > 0 ? s.fixed_off_labels.join('・') + '曜日' : 'なし（毎日出勤可能）';
        const card = document.createElement('div');
        card.className = 'p-4 rounded-2xl border border-slate-100 bg-slate-50/70 hover:bg-slate-50 transition space-y-3';
        
        let dowBadgeHtml = '';
        if (s.weekly_shift_pattern) {
          try {
            const wp = JSON.parse(s.weekly_shift_pattern);
            const dows = ['月','火','水','木','金','土'];
            const stShort = { FULL:'全', FIRST:'前', SECOND:'後', AM:'AM', PM:'PM', OFF:'休' };
            dowBadgeHtml = '<div class="grid grid-cols-6 gap-0.5 text-center text-[9px] font-bold mt-1 bg-slate-100 p-1 rounded-lg">';
            dows.forEach((d, idx) => {
              const val = wp[String(idx)] || 'OFF';
              const isOff = val === 'OFF';
              const col = isOff ? 'text-slate-400 bg-white/40' : 'text-blue-700 bg-white shadow-2xs';
              dowBadgeHtml += `<div class="p-0.5 rounded ${col}"><div class="text-[8px] text-slate-400">${d}</div><div>${stShort[val] || val}</div></div>`;
            });
            dowBadgeHtml += '</div>';
          } catch(e){}
        }

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2">
              <span class="w-3.5 h-3.5 rounded-full inline-block shadow-inner" style="background-color: ${s.color};"></span>
              <div>
                <div class="font-bold text-slate-900 text-xs">${s.full_name}</div>
                <div class="text-[10px] text-slate-400 font-semibold">${s.position_label}</div>
              </div>
            </div>
            <span class="px-2 py-0.5 rounded-lg bg-white border border-slate-200 text-[10px] font-bold text-slate-700 shadow-2xs">
              ${s.default_shift_label}
            </span>
          </div>

          <div class="space-y-1.5 text-xs text-slate-600 border-t border-slate-200/50 pt-2">
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-slate-400">勤務時間帯:</span>
              <span class="font-bold text-slate-800">${s.shift_time_range}</span>
            </div>
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-slate-400">固定定休日:</span>
              <span class="font-bold text-amber-700">${offText}</span>
            </div>
            ${dowBadgeHtml}
            <div class="flex items-center justify-between text-[11px]">
              <span class="text-slate-400">時給 / 有休残:</span>
              <span class="font-medium text-slate-700">¥${s.hourly_wage.toLocaleString()} / <span class="font-bold text-teal-700">${s.paid_leave_remaining}日</span></span>
            </div>
          </div>

          <div class="pt-1">
            <button onclick="openConditionModal(${s.id})"
              class="w-full py-1.5 rounded-xl bg-white border border-slate-200 hover:border-blue-400 hover:text-blue-600 text-[11px] font-bold text-slate-700 shadow-2xs transition flex items-center justify-center space-x-1">
              <i data-lucide="edit-3" class="w-3 h-3"></i>
              <span>曜日別シフト・条件を変更</span>
            </button>
          </div>
        `;
        grid.appendChild(card);
      });
      if (window.lucide) lucide.createIcons();
    } catch (e) {
      console.error(e);
    }
  }

  function openConditionModal(userId) {
    const s = staffConditionsData.find(x => x.id === userId);
    if (!s) return;
    document.getElementById('cond-user-id').value = s.id;
    document.getElementById('cond-modal-name').textContent = `${s.full_name} さんの勤務条件・シフト設定`;
    document.getElementById('cond-modal-color-dot').style.backgroundColor = s.color;
    document.getElementById('cond-default-shift').value = s.default_shift;
    document.getElementById('cond-hourly-wage').value = s.hourly_wage;
    document.getElementById('cond-paid-leave').value = s.paid_leave_remaining;
    if (document.getElementById('cond-password')) {
      document.getElementById('cond-password').value = '';
    }

    // 曜日別シフトの復元
    let pattern = {};
    if (s.weekly_shift_pattern) {
      try {
        pattern = JSON.parse(s.weekly_shift_pattern);
      } catch (e) {}
    }
    const offDays = (s.fixed_off_weekdays || '').split(',').map(x => x.trim());

    for (let dow = 0; dow <= 5; dow++) {
      const el = document.getElementById(`cond-dow-${dow}`);
      if (el) {
        if (pattern[String(dow)]) {
          el.value = pattern[String(dow)];
        } else if (offDays.includes(String(dow))) {
          el.value = 'OFF';
        } else if (dow === 5) {
          el.value = 'AM';
        } else {
          el.value = s.default_shift || 'FULL';
        }
      }
    }

    document.querySelectorAll('input[name="off-weekday"]').forEach(cb => {
      cb.checked = offDays.includes(cb.value);
    });

    document.getElementById('condition-edit-modal').classList.remove('hidden');
  }

  // 曜日別セレクトの変更時に定休日チェックボックスと連動
  document.addEventListener('DOMContentLoaded', () => {
    for (let dow = 0; dow <= 5; dow++) {
      const el = document.getElementById(`cond-dow-${dow}`);
      if (el) {
        el.addEventListener('change', () => {
          const cb = document.querySelector(`input[name="off-weekday"][value="${dow}"]`);
          if (cb) {
            cb.checked = (el.value === 'OFF');
          }
        });
      }
    }
  });

  function closeConditionModal() {
    document.getElementById('condition-edit-modal').classList.add('hidden');
  }

  async function handleSaveCondition(e) {
    e.preventDefault();
    const userId = document.getElementById('cond-user-id').value;
    const defaultShift = document.getElementById('cond-default-shift').value;
    const hourlyWage = parseInt(document.getElementById('cond-hourly-wage').value || '0', 10);
    const paidLeave = parseFloat(document.getElementById('cond-paid-leave').value || '0');
    const newPassword = document.getElementById('cond-password') ? document.getElementById('cond-password').value.trim() : '';

    // 曜日別シフトパターンの収集
    const weeklyPattern = {};
    const checkedDays = [];
    for (let dow = 0; dow <= 5; dow++) {
      const el = document.getElementById(`cond-dow-${dow}`);
      const val = el ? el.value : 'FULL';
      weeklyPattern[String(dow)] = val;
      if (val === 'OFF') {
        checkedDays.push(String(dow));
      }
    }
    weeklyPattern["6"] = "OFF"; // 日曜は休局
    checkedDays.push("6");

    const fixedOffWeekdays = checkedDays.join(',');

    const payload = {
      default_shift: defaultShift,
      weekly_shift_pattern: JSON.stringify(weeklyPattern),
      fixed_off_weekdays: fixedOffWeekdays,
      hourly_wage: hourlyWage,
      paid_leave_remaining: paidLeave
    };
    if (newPassword) {
      payload.new_password = newPassword;
    }

    try {
      const res = await fetch(`/api/admin/staff/${userId}/condition`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        showToast('勤務条件（曜日別シフト設定）を保存しました');
        closeConditionModal();
        loadStaffConditions();
        loadAdminShifts();
      } else {
        showToast('保存に失敗しました', 'error');
      }
    } catch (err) {
      showToast('エラーが発生しました', 'error');
    }
  }

