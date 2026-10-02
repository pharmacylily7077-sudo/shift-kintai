  // --- 🔐 パスワード残業申請モーダル制御 ---
  function openAdminOvertimeModal() {
    const modal = document.getElementById('admin-overtime-modal');
    if (!modal) return;
    
    // 日付を当日に初期化
    const today = new Date().toISOString().slice(0, 10);
    const dateInput = document.getElementById('admin-ot-date');
    if (dateInput) dateInput.value = today;

    // パスワード・理由をクリア
    const pwInput = document.getElementById('admin-ot-password');
    if (pwInput) pwInput.value = '';
    const reasonInput = document.getElementById('admin-ot-reason');
    if (reasonInput) reasonInput.value = '';

    // スタッフ選択ドロップダウンの再確認
    if (adminData && adminData.users) {
      populateStaffSelect(adminData.users);
    }

    modal.classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
  }

  function closeAdminOvertimeModal() {
    const modal = document.getElementById('admin-overtime-modal');
    if (modal) modal.classList.add('hidden');
  }

  function toggleAdminOtPassword() {
    const pwInput = document.getElementById('admin-ot-password');
    if (!pwInput) return;
    pwInput.type = pwInput.type === 'password' ? 'text' : 'password';
  }

  function setAdminOvertimeReason(text) {
    const area = document.getElementById('admin-ot-reason');
    if (!area) return;
    if (area.value) {
      area.value += ' ' + text;
    } else {
      area.value = text;
    }
  }

  async function handleAdminOvertimeSubmit(e) {
    e.preventDefault();
    const userId = parseInt(document.getElementById('admin-ot-user').value, 10);
    const password = document.getElementById('admin-ot-password').value;
    const date = document.getElementById('admin-ot-date').value;
    const hours = parseFloat(document.getElementById('admin-ot-hours').value);
    const reason = document.getElementById('admin-ot-reason').value.trim();

    if (!userId) {
      showToast('対象スタッフを選択してください', 'error');
      return;
    }
    if (!password) {
      showToast('本人確認パスワードを入力してください', 'error');
      return;
    }
    if (!reason) {
      showToast('残業内容・理由を記入してください', 'error');
      return;
    }

    const btn = document.getElementById('btn-admin-ot-submit');
    if (btn) btn.disabled = true;

    try {
      const res = await fetch('/api/admin/overtime-apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          password: password,
          date: date,
          overtime_hours: hours,
          reason: reason
        })
      });

      const resData = await res.json();
      if (res.ok) {
        showToast(resData.message || '残業申請を受け付けました');
        closeAdminOvertimeModal();
        await loadLeaveRequests();
        const panel = document.getElementById('admin-leave-requests-panel');
        if (panel) {
          panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      } else {
        showToast(resData.detail || '残業申請に失敗しました', 'error');
      }
    } catch (err) {
      showToast('エラーが発生しました', 'error');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function handleSendMessage(e) {
    e.preventDefault();
    const toId = document.getElementById('msg-to-user').value;
    const content = document.getElementById('msg-content').value.trim();
    if (!toId || !content) return;

    try {
      const res = await fetch('/api/admin/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ to_user_id: parseInt(toId), content })
      });
      if (res.ok) {
        showToast('個別メッセージを送信しました');
        document.getElementById('msg-content').value = '';
      }
    } catch (e) {
      showToast('送信失敗', 'error');
    }
  }

  async function loadLeaveRequests() {
    const box = document.getElementById('leave-requests-container');
    try {
      const res = await fetch('/api/admin/leave-requests');
      const list = await res.json();
      if (!list || list.length === 0) {
        box.innerHTML = '<div class="text-xs text-slate-400 text-center py-6">現在届いている申請はありません</div>';
        return;
      }
      box.innerHTML = '';
      list.forEach(r => {
        const isPending = r.status === 'PENDING';
        const card = document.createElement('div');
        card.className = 'p-3 rounded-2xl border border-slate-100 bg-slate-50 space-y-2';

        let typeBadge = '';
        let typeDetail = '';
        let isOvertime = r.leave_type === 'OVERTIME';

        if (r.leave_type === 'PAID_LEAVE') {
          typeBadge = '<span class="px-2 py-0.5 rounded-full bg-teal-100 text-teal-800 font-bold text-[10px]">🏖️ 有給休暇</span>';
          typeDetail = '有休（給与満額支給・残日数1日消化）';
        } else if (isOvertime) {
          typeBadge = `<span class="px-2 py-0.5 rounded-full bg-gradient-to-r from-amber-500 to-orange-500 text-white font-bold text-[10px] shadow-2xs">⏰ 残業申請 (${r.overtime_hours || 0}h)</span>`;
          typeDetail = `残業時間: ${r.overtime_hours || 0} 時間`;
        } else {
          typeBadge = '<span class="px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 font-bold text-[10px]">☕ 希望休</span>';
          typeDetail = '希望休（公休）';
        }

        let statusBadge = '';
        if (r.status === 'APPROVED') {
          statusBadge = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800">承認済</span>';
        } else if (r.status === 'REJECTED') {
          statusBadge = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-rose-100 text-rose-800">却下</span>';
        } else {
          statusBadge = '<span class="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-300 animate-pulse">承認待ち</span>';
        }

        let reasonContent = '';
        if (r.reason) {
          if (isOvertime) {
            reasonContent = `
              <div class="mt-2 p-2.5 rounded-xl bg-amber-50 border border-amber-200 text-slate-800">
                <div class="text-[10px] font-bold text-amber-800 flex items-center space-x-1 mb-1">
                  <span>📝 残業内容・理由:</span>
                </div>
                <div class="text-xs font-bold text-slate-900 leading-relaxed">${r.reason}</div>
              </div>
            `;
          } else {
            reasonContent = `<div class="text-slate-700 mt-1 font-medium"><span class="text-slate-400 text-[10px]">理由:</span> ${r.reason}</div>`;
          }
        }

        card.className = `p-3 rounded-2xl border ${isOvertime && isPending ? 'border-amber-300 bg-amber-50/30 ring-1 ring-amber-200' : 'border-slate-100 bg-slate-50'} space-y-2 transition-all`;

        card.innerHTML = `
          <div class="flex items-center justify-between">
            <div class="font-bold text-xs text-slate-800 flex items-center space-x-1.5">
              <span>${r.user_name}</span>
              <span class="text-[10px] text-slate-400 font-normal">(${r.position_label})</span>
              ${typeBadge}
            </div>
            ${statusBadge}
          </div>
          <div class="text-xs text-slate-600 bg-white p-2.5 rounded-xl border border-slate-100">
            <div class="flex items-center justify-between">
              <span class="font-bold text-slate-800">${r.date}</span>
              <span class="text-[11px] font-semibold ${isOvertime ? 'text-amber-800' : 'text-slate-500'}">${typeDetail}</span>
            </div>
            ${reasonContent}
            ${r.admin_note ? `<div class="text-amber-800 mt-1.5 text-[11px] bg-slate-50 p-1.5 rounded-lg border border-slate-100"><span class="text-slate-400 text-[10px] font-bold">管理者返信:</span> ${r.admin_note}</div>` : ''}
          </div>
          ${isPending ? `
          <div class="flex items-center justify-end space-x-2 pt-1">
            <button onclick="reviewLeave(${r.id}, 'REJECTED')" class="px-2.5 py-1 rounded-lg bg-white hover:bg-rose-50 text-rose-600 border border-rose-200 text-[11px] font-bold transition">却下</button>
            <button onclick="reviewLeave(${r.id}, 'APPROVED')" class="px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-[11px] font-bold shadow-xs transition flex items-center space-x-1">
              <i data-lucide="check" class="w-3 h-3"></i>
              <span>承認する</span>
            </button>
          </div>` : ''}
        `;
        box.appendChild(card);
      });
      if (window.lucide) lucide.createIcons();
    } catch (e) {
      console.error(e);
    }
  }

  async function reviewLeave(reqId, status) {
    const note = prompt(status === 'APPROVED' ? '承認時の個別メッセージ（任意）:' : '却下理由の個別メッセージ（任意）:');
    try {
      const res = await fetch(`/api/admin/leave-requests/${reqId}/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status, admin_note: note || '' })
      });
      if (res.ok) {
        showToast(`申請を${status === 'APPROVED' ? '承認' : '却下'}しました`);
        loadLeaveRequests();
        loadAdminShifts();
      }
    } catch (e) {
      showToast('処理に失敗しました', 'error');
    }
  }

  // --- 1. スタッフ勤務条件・時間設定 ---
  async function loadCompliance() {
    const container = document.getElementById('compliance-summary-container');
    try {
      const res = await fetch(`/api/admin/compliance/paid-leave?year=${adminYear}`);
      if (!res.ok) return;
      const data = await res.json();

      let bannerClass = 'bg-emerald-50 border-emerald-200 text-emerald-800';
      let bannerIcon = 'shield-check';
      let bannerMsg = '全スタッフが法定有休（年5日取得義務）を順調に消化しています';

      if (data.action_required_count > 0) {
        bannerClass = 'bg-rose-50 border-rose-200 text-rose-800';
        bannerIcon = 'alert-triangle';
        bannerMsg = `【要対応】年5日取得義務の未達懸念スタッフが ${data.action_required_count} 名います。計画的付与をご検討ください。`;
      } else if (data.in_progress_count > 0) {
        bannerClass = 'bg-amber-50 border-amber-200 text-amber-800';
        bannerIcon = 'clock';
        bannerMsg = `有休取得進行中（現在 ${data.in_progress_count} 名が計画的取得中）`;
      }

      let html = `
        <div class="p-3 rounded-2xl border ${bannerClass} flex items-center space-x-2 text-xs font-bold mb-4">
          <i data-lucide="${bannerIcon}" class="w-4 h-4 shrink-0"></i>
          <span>${bannerMsg}</span>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      `;

      data.staff.forEach(s => {
        const isAchieved = s.status === 'ACHIEVED';
        const isAction = s.status === 'ACTION_REQUIRED';
        const statusBadge = isAchieved
          ? '<span class="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-bold">達成 🟢</span>'
          : (isAction
            ? '<span class="px-2 py-0.5 rounded-full bg-rose-100 text-rose-800 text-[10px] font-bold">要取得 🔴</span>'
            : '<span class="px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 text-[10px] font-bold">進行中 🟡</span>');

        const barColor = isAchieved ? 'bg-emerald-500' : (isAction ? 'bg-rose-500' : 'bg-amber-500');

        html += `
          <div class="p-3 rounded-2xl border border-slate-100 bg-slate-50/50 space-y-2">
            <div class="flex items-center justify-between">
              <div class="font-bold text-xs text-slate-800">${s.full_name}</div>
              ${statusBadge}
            </div>
            <div>
              <div class="flex items-center justify-between text-[11px] text-slate-500 mb-1">
                <span>取得: <strong class="text-slate-800">${s.used_days}日</strong> / 5日</span>
                <span>有休残: <strong>${s.remaining_days}日</strong></span>
              </div>
              <div class="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                <div class="${barColor} h-1.5 rounded-full transition-all duration-300" style="width: ${s.legal_progress_percent}%"></div>
              </div>
            </div>
            <div class="text-[10px] text-slate-500 truncate">${s.warning_message || ''}</div>
          </div>
        `;
      });

      html += '</div>';
      container.innerHTML = html;
      if (window.lucide) lucide.createIcons();
    } catch (e) {
      console.error(e);
    }
  }
