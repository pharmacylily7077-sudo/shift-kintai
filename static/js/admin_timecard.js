  function initTimecardTabs(users) {
    const tabsContainer = document.getElementById('timecard-staff-tabs');
    if (!tabsContainer || !users) return;

    const kobayashi = users.find(u => u.username === 'kobayashi' || (u.full_name && u.full_name.includes('小林')));
    const honma = users.find(u => u.username === 'honma' || (u.full_name && u.full_name.includes('本間')));
    const others = users.filter(u => u !== kobayashi && u !== honma);

    if (!currentTimecardUserId) {
      currentTimecardUserId = kobayashi ? kobayashi.id : (honma ? honma.id : (users[0] ? users[0].id : null));
    }

    let html = '';
    if (kobayashi) {
      const isAct = currentTimecardUserId === kobayashi.id;
      html += `
        <button onclick="selectTimecardStaff(${kobayashi.id})" id="tc-tab-${kobayashi.id}"
          class="px-3.5 py-1.5 rounded-xl border text-xs font-bold transition flex items-center space-x-1.5 ${isAct ? 'bg-purple-600 border-purple-600 text-white shadow-2xs' : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'}">
          <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${kobayashi.color}"></span>
          <span>小林 彩乃</span>
          <span class="text-[10px] opacity-80">(調剤補助)</span>
        </button>
      `;
    }

    if (honma) {
      const isAct = currentTimecardUserId === honma.id;
      html += `
        <button onclick="selectTimecardStaff(${honma.id})" id="tc-tab-${honma.id}"
          class="px-3.5 py-1.5 rounded-xl border text-xs font-bold transition flex items-center space-x-1.5 ${isAct ? 'bg-rose-500 border-rose-500 text-white shadow-2xs' : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100'}">
          <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color: ${honma.color}"></span>
          <span>本間 まや</span>
          <span class="text-[10px] opacity-80">(調剤補助)</span>
        </button>
      `;
    }

    html += `
      <select onchange="selectTimecardStaff(parseInt(this.value, 10))" class="px-2.5 py-1.5 rounded-xl border border-slate-200 text-xs font-semibold bg-white text-slate-700 focus:outline-none">
        <option value="">他のスタッフのタイムカード...</option>
        ${others.map(u => `<option value="${u.id}" ${u.id === currentTimecardUserId ? 'selected' : ''}>${u.full_name} (${u.position_label})</option>`).join('')}
      </select>
    `;

    tabsContainer.innerHTML = html;
    if (currentTimecardUserId) {
      loadTimecard(currentTimecardUserId);
    }
  }

  function selectTimecardStaff(userId) {
    currentTimecardUserId = userId;
    if (adminData && adminData.users) {
      initTimecardTabs(adminData.users);
    }
    loadTimecard(userId);
  }

  async function loadTimecard(userId) {
    const tbody = document.getElementById('timecard-table-body');
    const summaryBadges = document.getElementById('timecard-summary-badges');
    try {
      const res = await fetch(`/api/admin/time-records/monthly?user_id=${userId}&year=${adminYear}&month=${adminMonth}`);
      if (!res.ok) return;
      currentTimecardData = await res.json();

      const s = currentTimecardData.summary;
      const backupKey = `kintai_tc_backup_${userId}_${adminYear}_${adminMonth}`;

      if (s.worked_days > 0) {
        // 実働データがある場合は端末LocalStorageに自動二重保存（消失を完全防止）
        try {
          localStorage.setItem(backupKey, JSON.stringify(currentTimecardData));
        } catch (err) {
          console.warn('LocalStorage save error:', err);
        }

        summaryBadges.innerHTML = `
          <span class="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700">実働: <strong>${s.worked_days}日</strong></span>
          <span class="px-2.5 py-1 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800">総労働: <strong>${s.total_work_hours_str}</strong></span>
          ${s.overtime_minutes > 0 ? `<span class="px-2.5 py-1 rounded-lg bg-rose-50 border border-rose-200 text-rose-700">残業: <strong>${s.overtime_hours_str}</strong></span>` : ''}
        `;
      } else {
        // 未打刻の場合、端末内にバックアップがあるかチェック
        let localBackup = null;
        try {
          const raw = localStorage.getItem(backupKey);
          if (raw) localBackup = JSON.parse(raw);
        } catch (err) {}

        if (localBackup && localBackup.summary && localBackup.summary.worked_days > 0) {
          summaryBadges.innerHTML = `
            <span class="px-2.5 py-1 rounded-lg bg-amber-50 border border-amber-200 text-amber-800 text-xs font-bold">
              ⚠️ 未打刻（端末内に${localBackup.summary.worked_days}日分の保存データあり）
            </span>
            <button onclick="restoreTimecardFromLocalBackup(${userId})"
              class="px-3 py-1.5 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-700 hover:to-teal-700 text-white font-bold text-xs shadow-xs transition flex items-center space-x-1.5">
              <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
              <span>💾 端末の保存データから復元</span>
            </button>
          `;
        } else {
          summaryBadges.innerHTML = `
            <span class="px-2.5 py-1 rounded-lg bg-slate-100 text-slate-500">実働: 0日（未打刻）</span>
            <span class="text-xs text-purple-600 font-bold">※右上の「⏱️ 一括勤務時間・打刻調節」で出勤（5分刻み）・退勤（10分刻み）を一括設定できます</span>
          `;
        }
      }

      let bodyHtml = '';
      currentTimecardData.days.forEach(d => {
        const isSun = d.weekday === 6;
        const isSat = d.weekday === 5;
        const dayClass = isSun ? 'text-rose-500 bg-rose-50/20' : (isSat ? 'text-blue-500 bg-blue-50/20' : '');
        const hasClock = d.clock_in && d.clock_out;

        bodyHtml += `
          <tr class="hover:bg-slate-50/80 transition ${dayClass}">
            <td class="p-2.5 text-center font-bold">${adminMonth}/${d.day}</td>
            <td class="p-2.5 text-center font-bold">${d.weekday_label}</td>
            <td class="p-2.5 text-center">
              <span class="px-2 py-0.5 rounded text-[11px] font-bold ${SHIFT_CLASSES[d.shift_type] || SHIFT_CLASSES.OFF}">
                ${d.shift_label}
              </span>
            </td>
            <td class="p-2.5 text-center">
              ${d.clock_in ? `<span class="font-mono font-black text-slate-900 text-sm tracking-tight">${d.clock_in}</span>` : '<span class="text-slate-300">-</span>'}
            </td>
            <td class="p-2.5 text-center">
              ${d.clock_out ? `<span class="font-mono font-black text-slate-900 text-sm tracking-tight">${d.clock_out}</span>` : '<span class="text-slate-300">-</span>'}
            </td>
            <td class="p-2.5 text-center text-slate-500">
              ${d.break_minutes > 0 ? `${d.break_minutes}分` : (hasClock ? '0分' : '-')}
            </td>
            <td class="p-2.5 text-center font-bold text-slate-800 font-mono">
              ${d.work_hours_str}
            </td>
            <td class="p-2.5 text-center">
              <button onclick="openTimecardModal('${d.date}', '${d.clock_in}', '${d.clock_out}', ${d.break_minutes}, '${d.shift_type}')"
                class="px-2 py-1 rounded-lg bg-white border border-slate-200 hover:border-purple-400 hover:text-purple-600 text-[11px] font-bold shadow-2xs transition">
                ✏️ 編集
              </button>
            </td>
          </tr>
        `;
      });

      tbody.innerHTML = bodyHtml;
      if (window.lucide) lucide.createIcons();
    } catch (e) {
      console.error(e);
      tbody.innerHTML = '<tr><td colspan="8" class="text-center py-6 text-rose-500">タイムカードの取得に失敗しました</td></tr>';
    }
  }

  // --- 💾 端末LocalStorageからのバックアップ復元 ---
  async function restoreTimecardFromLocalBackup(userId) {
    const backupKey = `kintai_tc_backup_${userId}_${adminYear}_${adminMonth}`;
    let localBackup = null;
    try {
      const raw = localStorage.getItem(backupKey);
      if (raw) localBackup = JSON.parse(raw);
    } catch (err) {}

    if (!localBackup || !localBackup.days) {
      showToast('端末内に有効なバックアップが見つかりませんでした', 'error');
      return;
    }

    const records = localBackup.days
      .filter(d => d.clock_in && d.clock_out)
      .map(d => ({
        date: d.date,
        clock_in: d.clock_in,
        clock_out: d.clock_out,
        break_minutes: d.break_minutes
      }));

    if (records.length === 0) {
      showToast('バックアップ内に有効な打刻データがありません', 'error');
      return;
    }

    showToast(`端末内の保存データ（${records.length}日分）を復元しています...`, 'info');

    try {
      const res = await fetch('/api/admin/time-records/batch-restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          year: adminYear,
          month: adminMonth,
          records: records
        })
      });
      const data = await res.json();
      if (res.ok) {
        showToast(data.message || '打刻データを完全復元しました！', 'success');
        loadTimecard(userId);
      } else {
        showToast('復元に失敗しました', 'error');
      }
    } catch (e) {
      console.error(e);
      showToast('復元中にエラーが発生しました', 'error');
    }
  }

  // --- ⏱️ 5分刻み出勤 ＆ 10分刻み退勤延長 一括調節制御 ---
  let batchInOffset = 0;   // 就業時間より5分刻み (例: 0, -5, -10, -15...)
  let batchOutOffset = 0;  // 10分刻みで増やす (例: 0, 10, 20, 30...)

  function openBatchTimeAdjustModal() {
    if (!currentTimecardData) return;
    const staffName = currentTimecardData.full_name;
    const targetLabel = document.getElementById('batch-adjust-target-label');
    if (targetLabel) {
      targetLabel.textContent = `【${staffName} 様】 ${adminYear}年${adminMonth}月分`;
    }
    setBatchInOffset(0);
    setBatchOutOffset(0);
    const chk = document.getElementById('batch-overwrite-check');
    if (chk) {
      chk.checked = (currentTimecardData.summary && currentTimecardData.summary.worked_days > 0);
    }
    document.getElementById('batch-time-adjust-modal').classList.remove('hidden');
    if (window.lucide) lucide.createIcons();
  }

  function closeBatchTimeAdjustModal() {
    document.getElementById('batch-time-adjust-modal').classList.add('hidden');
  }

  function setBatchInOffset(offset) {
    batchInOffset = offset;
    const sel = document.getElementById('batch-in-offset-select');
    if (sel) sel.value = String(offset);

    // ボタンスタイル更新
    const btns = document.querySelectorAll('#batch-in-btn-group .btn-batch-in');
    btns.forEach(b => {
      const isMatch = (offset === 0 && b.textContent.includes('定時')) ||
                      (offset < 0 && b.textContent.includes(`${offset}分`)) ||
                      (offset > 0 && b.textContent.includes(`+${offset}分`));
      if (isMatch) {
        b.className = 'btn-batch-in text-[10px] py-1.5 rounded-lg border border-purple-600 bg-purple-600 text-white font-bold transition';
      } else {
        b.className = 'btn-batch-in text-[10px] py-1.5 rounded-lg border border-slate-200 bg-white font-bold hover:bg-purple-50 transition';
      }
    });

    const preview = document.getElementById('batch-in-preview');
    if (preview) {
      if (offset < 0) {
        preview.textContent = `${Math.abs(offset)}分前出勤 (${offset}分)`;
      } else if (offset > 0) {
        preview.textContent = `${offset}分遅出勤 (+${offset}分)`;
      } else {
        preview.textContent = '定時ちょうど (0分)';
      }
    }
    updateBatchPreview();
  }

  function setBatchOutOffset(offset) {
    batchOutOffset = offset;
    const sel = document.getElementById('batch-out-offset-select');
    if (sel) sel.value = String(offset);

    // ボタンスタイル更新
    const btns = document.querySelectorAll('#batch-out-btn-group .btn-batch-out');
    btns.forEach(b => {
      const isMatch = (offset === 0 && b.textContent.includes('定時')) ||
                      (offset > 0 && b.textContent.includes(`+${offset}分`));
      if (isMatch) {
        b.className = 'btn-batch-out text-[10px] py-1.5 rounded-lg border border-amber-600 bg-amber-600 text-white font-bold transition';
      } else {
        b.className = 'btn-batch-out text-[10px] py-1.5 rounded-lg border border-slate-200 bg-white font-bold hover:bg-amber-50 transition';
      }
    });

    const preview = document.getElementById('batch-out-preview');
    if (preview) {
      if (offset > 0) {
        preview.textContent = `+${offset}分延長残業`;
      } else {
        preview.textContent = '定時退勤 (+0分)';
      }
    }
    updateBatchPreview();
  }

  function updateBatchPreview() {
    const samplesContainer = document.getElementById('batch-adjust-samples');
    if (!samplesContainer) return;

    const minuteJitter = document.getElementById('batch-minute-jitter-check') ? document.getElementById('batch-minute-jitter-check').checked : true;
    const secondJitter = document.getElementById('batch-jitter-check') ? document.getElementById('batch-jitter-check').checked : true;

    function formatTime(baseH, baseM, deltaM, jitterM, secStr) {
      const effectiveDelta = minuteJitter ? (deltaM + jitterM) : deltaM;
      const total = baseH * 60 + baseM + effectiveDelta;
      const h = Math.floor(total / 60) % 24;
      const m = total % 60;
      const ss = secondJitter ? secStr : '00';
      return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${ss}`;
    }

    if (minuteJitter) {
      // 分ゆらぎが有効な場合：日によって分・秒が自然に異なる様子をプレビュー
      const day1In = formatTime(9, 0, batchInOffset, -1, '24');
      const day1Out = formatTime(18, 0, batchOutOffset, 2, '41');
      const day2In = formatTime(9, 0, batchInOffset, 1, '12');
      const day2Out = formatTime(18, 0, batchOutOffset, -2, '53');
      const day3In = formatTime(9, 0, batchInOffset, -2, '48');
      const day3Out = formatTime(18, 0, batchOutOffset, 3, '19');

      samplesContainer.innerHTML = `
        <div class="bg-white p-2 rounded-xl border border-slate-200">
          <span class="text-indigo-700 font-bold block mb-0.5">出勤例（日ごとに分散）:</span>
          <span class="text-slate-800 font-bold text-[10px] block">${day1In} / ${day2In} / ${day3In}</span>
        </div>
        <div class="bg-white p-2 rounded-xl border border-slate-200">
          <span class="text-amber-700 font-bold block mb-0.5">退勤例（日ごとに分散）:</span>
          <span class="text-slate-800 font-bold text-[10px] block">${day1Out} / ${day2Out} / ${day3Out}</span>
        </div>
      `;
    } else {
      const firstIn = formatTime(9, 0, batchInOffset, 0, '14');
      const firstOut = formatTime(18, 0, batchOutOffset, 0, '38');
      const secondIn = formatTime(10, 0, batchInOffset, 0, '22');
      const secondOut = formatTime(19, 0, batchOutOffset, 0, '45');

      samplesContainer.innerHTML = `
        <div class="bg-white p-2 rounded-xl border border-slate-200">
          <span class="text-amber-700 font-bold block mb-0.5">前半 (9-18):</span>
          <span class="text-slate-800 font-bold">${firstIn} 〜 ${firstOut}</span>
        </div>
        <div class="bg-white p-2 rounded-xl border border-slate-200">
          <span class="text-indigo-700 font-bold block mb-0.5">後半 (10-19):</span>
          <span class="text-slate-800 font-bold">${secondIn} 〜 ${secondOut}</span>
        </div>
      `;
    }
  }

  async function handleExecuteBatchTimeAdjust(e) {
    e.preventDefault();
    if (!currentTimecardData || !currentTimecardUserId) return;
    const staffName = currentTimecardData.full_name;
    const overwrite = document.getElementById('batch-overwrite-check').checked;
    const secondJitter = document.getElementById('batch-jitter-check') ? document.getElementById('batch-jitter-check').checked : true;
    const minuteJitter = document.getElementById('batch-minute-jitter-check') ? document.getElementById('batch-minute-jitter-check').checked : true;

    const inDesc = batchInOffset < 0 ? `${Math.abs(batchInOffset)}分前出勤` : (batchInOffset > 0 ? `${batchInOffset}分遅出勤` : '定時出勤');
    const outDesc = batchOutOffset > 0 ? `+${batchOutOffset}分延長退勤` : '定時退勤';

    const msg = `【${staffName} 様】\n${adminYear}年${adminMonth}月の出勤シフトに対して、\n・出勤：${inDesc}（5分刻み）\n・退勤：${outDesc}（10分刻み）\nで一括適用しますか？\n\n${overwrite ? '※既存の打刻も含めて上書きされます。' : '※未打刻の出勤日のみ適用されます。'}\n${minuteJitter ? '※分は日ごとに自然に散らばります（分が全部一緒になるのを防止）。\n' : ''}${secondJitter ? '※秒は自然な電子打刻秒が付与されます（一括入力と疑われない生ログ）。' : '※秒は00で揃います。'}`;
    if (!confirm(msg)) return;

    const btn = document.getElementById('btn-batch-adjust-submit');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>一括適用中...</span>';
      if (window.lucide) lucide.createIcons();
    }

    try {
      const res = await fetch('/api/admin/time-records/batch-fill', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentTimecardUserId,
          year: adminYear,
          month: adminMonth,
          overwrite_existing: overwrite,
          in_offset_minutes: batchInOffset,
          out_offset_minutes: batchOutOffset,
          add_second_jitter: secondJitter,
          add_minute_jitter: minuteJitter
        })
      });
      const data = await res.json();

      if (res.ok) {
        if (data.filled_count === 0 && !overwrite) {
          showToast('⚠️ 既存の打刻があるため変更されませんでした。上書きする場合は「一括上書き」にチェックを入れてください。', 'info');
        } else {
          showToast(data.message || '一括勤務時間調節を適用しました！');
        }
        closeBatchTimeAdjustModal();
        loadTimecard(currentTimecardUserId);
      } else {
        showToast('一括調節に失敗しました', 'error');
      }
    } catch (e) {
      showToast('エラーが発生しました', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        if (window.lucide) lucide.createIcons();
      }
    }
  }

  // --- ✏️ 単日タイムカード手動編集制御 ---
  function openTimecardModal(dateStr, clockIn, clockOut, breakMins, shiftType) {
    if (!currentTimecardData) return;
    activeTimecardEditRow = { dateStr, shiftType: shiftType || 'FULL' };
    document.getElementById('tc-modal-staff-name').textContent = `${currentTimecardData.full_name} さんの打刻`;
    document.getElementById('tc-modal-date-label').textContent = `${dateStr} の勤務時間`;
    document.getElementById('tc-modal-date').value = dateStr;
    document.getElementById('tc-modal-in').value = clockIn || '';
    document.getElementById('tc-modal-out').value = clockOut || '';
    document.getElementById('tc-modal-break').value = (breakMins !== undefined && breakMins !== null) ? String(breakMins) : '60';

    document.getElementById('timecard-edit-modal').classList.remove('hidden');
  }

  function closeTimecardModal() {
    document.getElementById('timecard-edit-modal').classList.add('hidden');
    activeTimecardEditRow = null;
  }

  // 単日 5分刻み出勤クイック調節
  function adjustSingleInTime(deltaMin) {
    const input = document.getElementById('tc-modal-in');
    let val = input.value;
    if (!val) {
      val = (activeTimecardEditRow && activeTimecardEditRow.shiftType === 'SECOND') ? '10:00:00' : '09:00:00';
    }
    const parts = val.split(':');
    let total = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + deltaMin;
    if (total < 0) total += 24 * 60;
    const h = Math.floor(total / 60) % 24;
    const m = total % 60;
    const s = Math.floor(Math.random() * 52) + 4;
    input.value = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function resetSingleInTime() {
    const input = document.getElementById('tc-modal-in');
    const defaultH = (activeTimecardEditRow && activeTimecardEditRow.shiftType === 'SECOND') ? '10' : '09';
    const s = Math.floor(Math.random() * 52) + 4;
    input.value = `${defaultH}:00:${String(s).padStart(2, '0')}`;
  }

  // 単日 10分刻み退勤延長クイック調節
  function adjustSingleOutTime(deltaMin) {
    const input = document.getElementById('tc-modal-out');
    let val = input.value;
    if (!val) {
      if (activeTimecardEditRow && activeTimecardEditRow.shiftType === 'AM') val = '13:00:00';
      else if (activeTimecardEditRow && activeTimecardEditRow.shiftType === 'FIRST') val = '18:00:00';
      else val = '19:00:00';
    }
    const parts = val.split(':');
    let total = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10) + deltaMin;
    if (total < 0) total += 24 * 60;
    const h = Math.floor(total / 60) % 24;
    const m = total % 60;
    const s = Math.floor(Math.random() * 52) + 4;
    input.value = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  }

  function resetSingleOutTime() {
    const input = document.getElementById('tc-modal-out');
    let defaultH = '19';
    if (activeTimecardEditRow) {
      if (activeTimecardEditRow.shiftType === 'AM') defaultH = '13';
      else if (activeTimecardEditRow.shiftType === 'FIRST') defaultH = '18';
    }
    const s = Math.floor(Math.random() * 52) + 4;
    input.value = `${defaultH}:00:${String(s).padStart(2, '0')}`;
  }

  async function handleSaveTimecardRow(e) {
    e.preventDefault();
    if (!activeTimecardEditRow || !currentTimecardUserId) return;
    const dateStr = document.getElementById('tc-modal-date').value;
    const clockIn = document.getElementById('tc-modal-in').value;
    const clockOut = document.getElementById('tc-modal-out').value;
    const breakMins = parseInt(document.getElementById('tc-modal-break').value, 10);

    try {
      const res = await fetch('/api/admin/time-records/single', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentTimecardUserId,
          date: dateStr,
          clock_in: clockIn || null,
          clock_out: clockOut || null,
          break_minutes: breakMins,
          clear: false
        })
      });
      if (res.ok) {
        showToast('打刻時間を保存しました');
        closeTimecardModal();
        loadTimecard(currentTimecardUserId);
      } else {
        showToast('保存に失敗しました', 'error');
      }
    } catch (e) {
      showToast('エラーが発生しました', 'error');
    }
  }

  async function clearCurrentTimecardRow() {
    if (!activeTimecardEditRow || !currentTimecardUserId) return;
    if (!confirm(`${activeTimecardEditRow.dateStr} の打刻を消去しますか？`)) return;

    try {
      const res = await fetch('/api/admin/time-records/single', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentTimecardUserId,
          date: activeTimecardEditRow.dateStr,
          clear: true
        })
      });
      if (res.ok) {
        showToast('打刻を消去しました');
        closeTimecardModal();
        loadTimecard(currentTimecardUserId);
      }
    } catch (e) {
      showToast('消去に失敗しました', 'error');
    }
  }

  function buildTimecardExportElement() {
    const s = currentTimecardData.summary;
    const element = document.createElement('div');
    element.className = 'p-6 bg-white text-slate-900';
    element.style.width = '800px';
    element.style.backgroundColor = '#ffffff';

    element.innerHTML = `
      <div class="text-center mb-4 border-b-2 border-slate-900 pb-3">
        <h1 class="text-2xl font-black tracking-wider text-slate-900">リリー薬局 勤務実績出勤簿（タイムカード）</h1>
        <div class="flex items-center justify-between text-xs text-slate-600 mt-2 px-2">
          <span><strong>氏名:</strong> ${currentTimecardData.full_name} 様 (${currentTimecardData.position_label})</span>
          <span><strong>対象年月:</strong> ${adminYear}年${adminMonth}月分</span>
          <span><strong>発行日:</strong> ${new Date().toLocaleDateString('ja-JP')}</span>
        </div>
      </div>

      <div class="flex items-center justify-around p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs mb-4">
        <div>出勤日数: <strong class="text-sm font-black text-slate-900">${s.worked_days}日</strong></div>
        <div>総実労働時間: <strong class="text-sm font-black text-emerald-800">${s.total_work_hours_str}</strong> (${s.total_work_hours}時間)</div>
        <div>残業時間: <strong class="text-sm font-black text-rose-700">${s.overtime_hours_str}</strong></div>
      </div>
    `;

    const originalTable = document.querySelector('#timecard-print-container table');
    if (originalTable) {
      const tableClone = originalTable.cloneNode(true);
      tableClone.querySelectorAll('tr').forEach(row => {
        if (row.children.length >= 8) {
          row.removeChild(row.lastElementChild);
        }
      });
      tableClone.className = 'w-full text-xs border border-slate-300 border-collapse bg-white';
      element.appendChild(tableClone);
    }

    const container = document.createElement('div');
    container.id = 'timecard-export-render-container';
    container.style.position = 'fixed';
    container.style.left = '-9999px';
    container.style.top = '0px';
    container.style.zIndex = '9999';
    container.style.opacity = '1';
    container.style.pointerEvents = 'none';
    container.style.width = '800px';
    container.style.backgroundColor = '#ffffff';
    container.appendChild(element);

    return { container, element };
  }

  async function downloadTimecardPDF() {
    if (!currentTimecardData) return;
    if (currentTimecardData.summary.worked_days === 0) {
      showToast('⚠️ 打刻データが0件（未打刻）です。先に「⏱️ 一括勤務時間・打刻調節」で出勤・退勤時間を設定してください。', 'error');
      return;
    }

    const btn = document.getElementById('btn-timecard-pdf');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>PDF作成中...</span>';
      if (window.lucide) lucide.createIcons();
    }

    showToast('タイムカードPDFを作成しています...', 'info');

    const { container, element } = buildTimecardExportElement();
    document.body.appendChild(container);

    try {
      const filename = `リリー薬局_タイムカード_${currentTimecardData.full_name}_${adminYear}年${adminMonth}月.pdf`;
      const opt = {
        margin:       [8, 8, 8, 8],
        filename:     filename,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  {
          scale: 2,
          useCORS: true,
          logging: false,
          scrollX: 0,
          scrollY: 0,
          windowWidth: 900,
          backgroundColor: '#ffffff'
        },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'portrait' }
      };

      if (window.html2pdf) {
        await html2pdf().set(opt).from(element).save();
        showToast('タイムカードPDFをダウンロードしました！', 'success');
      } else {
        window.print();
      }
    } catch (e) {
      console.error(e);
      showToast('PDF生成エラー', 'error');
    } finally {
      if (document.body.contains(container)) {
        document.body.removeChild(container);
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        if (window.lucide) lucide.createIcons();
      }
    }
  }

  // --- 📸 LINE用 タイムカード画像保存 (PNG) ---
  async function downloadTimecardImage() {
    if (!currentTimecardData) return;
    if (currentTimecardData.summary.worked_days === 0) {
      showToast('⚠️ 打刻データが0件（未打刻）です。先に「⏱️ 一括勤務時間・打刻調節」で出勤・退勤時間を設定してください。', 'error');
      return;
    }

    const btn = document.getElementById('btn-timecard-img');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>画像作成中...</span>';
      if (window.lucide) lucide.createIcons();
    }

    showToast('LINE送信用のタイムカード画像を作成しています...', 'info');

    const { container, element } = buildTimecardExportElement();
    document.body.appendChild(container);

    try {
      if (window.html2canvas) {
        const canvas = await html2canvas(element, {
          scale: 2,
          useCORS: true,
          logging: false,
          scrollX: 0,
          scrollY: 0,
          windowWidth: 900,
          backgroundColor: '#ffffff'
        });
        const link = document.createElement('a');
        link.download = `リリー薬局_タイムカード_${currentTimecardData.full_name}_${adminYear}年${adminMonth}月.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();
        showToast('LINE用画像を保存しました！LINEでそのまま送信できます', 'success');
      } else {
        showToast('画像化ライブラリの読み込みに失敗しました', 'error');
      }
    } catch (err) {
      console.error('画像生成エラー:', err);
      showToast('画像の作成に失敗しました', 'error');
    } finally {
      if (document.body.contains(container)) {
        document.body.removeChild(container);
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = originalHtml;
        if (window.lucide) lucide.createIcons();
      }
    }
  }


  function printTimecard() {
    window.print();
  }

  function exportTimecardCSV() {
    if (!currentTimecardUserId) return;
    window.location.href = `/api/admin/time-records/export-csv?user_id=${currentTimecardUserId}&year=${adminYear}&month=${adminMonth}`;
  }

