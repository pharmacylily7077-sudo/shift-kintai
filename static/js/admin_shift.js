  async function loadAdminShifts() {
    try {
      const res = await fetch(`/api/admin/shifts/monthly?year=${adminYear}&month=${adminMonth}`);
      if (res.status === 401 || res.status === 403) {
        window.location.href = '/login';
        return;
      }
      adminData = await res.json();
      renderAdminTable(adminData);
      populateStaffSelect(adminData.users);
      initTimecardTabs(adminData.users);
    } catch (e) {
      console.error(e);
      showToast('シフト読込に失敗しました', 'error');
    }
  }

  function renderAdminTable(data) {
    document.getElementById('admin-month-label').textContent = `${data.year}年${data.month}月`;
    const tcMonth = document.getElementById('timecard-month-label');
    if (tcMonth) tcMonth.textContent = `${data.year}年${data.month}月分`;

    // ヘッダー（日付）
    const thead = document.getElementById('admin-table-head');
    let headHtml = '<tr><th class="p-3 w-28 sticky left-0 bg-slate-50 z-10">スタッフ</th>';
    for (let d = 1; d <= data.days_in_month; d++) {
      const dateObj = new Date(data.year, data.month - 1, d);
      const wd = dateObj.getDay();
      const wdLabel = ['日','月','火','水','木','金','土'][wd];
      const isSun = wd === 0;
      const isTue = wd === 2;
      const colClass = isSun ? 'text-rose-500 bg-rose-50/50' : (isTue ? 'text-amber-600 bg-amber-50/30' : '');
      headHtml += `<th class="p-2 text-center border-l border-slate-100 ${colClass}"><div class="font-black">${d}</div><div class="text-[10px] font-normal">${wdLabel}</div></th>`;
    }
    headHtml += '</tr>';
    thead.innerHTML = headHtml;

    // ボディ（スタッフ別行）
    const tbody = document.getElementById('admin-table-body');
    let bodyHtml = '';
    data.users.forEach(u => {
      bodyHtml += `<tr><td class="p-3 font-bold sticky left-0 bg-white z-10 border-r border-slate-100 flex items-center space-x-2">
        <span class="w-2.5 h-2.5 rounded-full" style="background-color: ${u.color}"></span>
        <span>${u.full_name}</span>
      </td>`;

      for (let d = 1; d <= data.days_in_month; d++) {
        const dateStr = `${data.year}-${String(data.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const key = `${dateStr}_${u.id}`;
        const s = data.shifts[key];
        const sType = s ? s.shift_type : 'OFF';
        const sClass = SHIFT_CLASSES[sType] || SHIFT_CLASSES.OFF;
        const sLabel = SHIFT_TEXT[sType] || '休';

        bodyHtml += `<td class="p-1 text-center border-l border-slate-100">
          <button onclick="openEditModal(${u.id}, '${u.full_name}', '${dateStr}', '${sType}')"
            class="w-full py-1.5 rounded-lg text-[11px] font-bold ${sClass} hover:opacity-80 transition">
            ${sLabel}
          </button>
        </td>`;
      }
      bodyHtml += '</tr>';
    });
    tbody.innerHTML = bodyHtml;
    if (window.lucide) lucide.createIcons();
  }

  function openEditModal(userId, userName, dateStr, currentType) {
    activeEdit = { userId, dateStr };
    document.getElementById('modal-staff-name').textContent = userName;
    document.getElementById('modal-shift-date').textContent = dateStr;
    document.getElementById('shift-edit-modal').classList.remove('hidden');
  }

  function closeModal() {
    document.getElementById('shift-edit-modal').classList.add('hidden');
    activeEdit = null;
  }

  async function setModalShift(shiftType) {
    if (!activeEdit) return;
    try {
      const res = await fetch('/api/admin/shifts/single', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: activeEdit.userId,
          date: activeEdit.dateStr,
          shift_type: shiftType,
        })
      });
      if (res.ok) {
        closeModal();
        loadAdminShifts();
        showToast('シフトを更新しました');
      }
    } catch (e) {
      showToast('更新失敗', 'error');
    }
  }

  async function runAutoGenerate() {
    if (!confirm(`${adminYear}年${adminMonth}月のシフトを一括生成しますか？\n（既存シフトは上書きされます）`)) return;
    const btn = document.getElementById('btn-auto-gen');
    btn.disabled = true;
    try {
      const res = await fetch('/api/admin/shifts/auto-generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ year: adminYear, month: adminMonth, overwrite: true })
      });
      const d = await res.json();
      showToast(d.message || 'シフトを一括生成しました');
      loadAdminShifts();
    } catch (e) {
      showToast('自動生成に失敗しました', 'error');
    } finally {
      btn.disabled = false;
    }
  }

  function changeAdminMonth(delta) {
    adminMonth += delta;
    if (adminMonth > 12) { adminMonth = 1; adminYear++; }
    if (adminMonth < 1) { adminMonth = 12; adminYear--; }
    loadAdminShifts();
    if (currentTimecardUserId) {
      loadTimecard(currentTimecardUserId);
    }
  }

  function populateStaffSelect(users) {
    const sel = document.getElementById('msg-to-user');
    const otSel = document.getElementById('admin-ot-user');
    if (sel) sel.innerHTML = '<option value="">選択してください</option>';
    if (otSel) otSel.innerHTML = '<option value="">スタッフを選択してください</option>';
    users.forEach(u => {
      if (!u.is_admin) {
        if (sel) {
          const opt = document.createElement('option');
          opt.value = u.id;
          opt.textContent = `${u.full_name} (${u.position_label})`;
          sel.appendChild(opt);
        }
        if (otSel) {
          const otOpt = document.createElement('option');
          otOpt.value = u.id;
          otOpt.textContent = `${u.full_name} (${u.position_label})`;
          otSel.appendChild(otOpt);
        }
      }
    });
  }

  function buildAdminExportElement() {
    const element = document.createElement('div');
    element.id = 'admin-shift-export-content';
    element.className = 'p-6 bg-white text-slate-900';
    element.style.width = '1120px';
    element.style.backgroundColor = '#ffffff';

    const title = document.createElement('div');
    title.className = 'text-center mb-4';
    title.innerHTML = `
      <h1 class="text-2xl font-black text-slate-900 tracking-wide">リリー薬局 月間シフト編成表（${adminYear}年${adminMonth}月）</h1>
      <p class="text-xs text-slate-500 mt-1">発行日: ${new Date().toLocaleDateString('ja-JP')} | A4横公式シフト表</p>
    `;
    element.appendChild(title);

    // 編成テーブルのクローン
    const originalTable = document.querySelector('#admin-shift-table-container table') || document.querySelector('.overflow-x-auto table');
    if (originalTable) {
      const tableClone = originalTable.cloneNode(true);
      tableClone.className = 'w-full text-xs border border-slate-300 border-collapse bg-white text-slate-900';
      element.appendChild(tableClone);
    }

    const container = document.createElement('div');
    container.id = 'admin-export-render-container';
    container.style.position = 'fixed';
    container.style.top = '0px';
    container.style.left = '0px';
    container.style.width = '100vw';
    container.style.height = '100vh';
    container.style.backgroundColor = 'rgba(15, 23, 42, 0.7)';
    container.style.zIndex = '999999';
    container.style.display = 'flex';
    container.style.alignItems = 'center';
    container.style.justifyContent = 'center';
    container.style.overflow = 'auto';

    const card = document.createElement('div');
    card.className = 'bg-white rounded-2xl shadow-2xl p-4 max-h-[95vh] overflow-auto';
    card.appendChild(element);
    container.appendChild(card);

    return { container, element };
  }

  // --- 2. シフト表 PDFワンクリック保存 ---
  async function downloadAdminPDF() {
    const btn = document.getElementById('btn-admin-pdf');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>PDF作成中...</span>';
      if (window.lucide) lucide.createIcons();
    }

    showToast('A4横向きシフト表PDFを作成しています...', 'info');

    const { container, element } = buildAdminExportElement();
    document.body.appendChild(container);

    try {
      // DOM描画を確実に待機
      await new Promise(r => setTimeout(r, 200));

      const filename = `リリー薬局_月間シフト表_${adminYear}年${adminMonth}月.pdf`;
      const opt = {
        margin:       [8, 8, 8, 8],
        filename:     filename,
        image:        { type: 'jpeg', quality: 0.98 },
        html2canvas:  {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: '#ffffff'
        },
        jsPDF:        { unit: 'mm', format: 'a4', orientation: 'landscape' }
      };

      if (window.html2pdf) {
        await html2pdf().set(opt).from(element).save();
        showToast('シフト表PDFをダウンロードしました！', 'success');
      } else {
        window.print();
      }
    } catch (err) {
      console.error('PDF生成エラー:', err);
      showToast('PDF生成に失敗したため、印刷画面を開きます', 'error');
      window.print();
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

  // --- 2-2. 📸 LINE用 シフト表画像保存 (PNG) ---
  async function downloadAdminImage() {
    const btn = document.getElementById('btn-admin-img');
    const originalHtml = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>画像作成中...</span>';
      if (window.lucide) lucide.createIcons();
    }

    showToast('LINE送信用の高画質画像を作成しています...', 'info');

    const { container, element } = buildAdminExportElement();
    document.body.appendChild(container);

    try {
      // DOM描画を確実に待機
      await new Promise(r => setTimeout(r, 200));

      if (window.html2canvas) {
        const canvas = await html2canvas(element, {
          scale: 2,
          useCORS: true,
          logging: false,
          backgroundColor: '#ffffff'
        });
        const link = document.createElement('a');
        link.download = `リリー薬局_月間シフト表_${adminYear}年${adminMonth}月.png`;
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


  // --- 3. LINE共有・連絡文コピー ---
  async function openShareTextModal() {
    const modal = document.getElementById('share-text-modal');
    modal.classList.remove('hidden');
    document.getElementById('share-text-area').value = 'シフト共有テキストを生成中...';

    try {
      const res = await fetch(`/api/admin/shifts/share-text?year=${adminYear}&month=${adminMonth}`);
      if (!res.ok) return;
      shareTextData = await res.json();

      // スタッフ選択肢を生成
      const sel = document.getElementById('share-staff-select');
      sel.innerHTML = '';
      (shareTextData.by_staff || []).forEach(st => {
        const opt = document.createElement('option');
        opt.value = st.user_id;
        opt.textContent = `${st.user_name} さん（出勤: ${st.days_count}日）`;
        sel.appendChild(opt);
      });

      selectShareTab(activeShareTab);
    } catch (e) {
      document.getElementById('share-text-area').value = 'テキストの生成に失敗しました';
    }
  }

  function closeShareTextModal() {
    document.getElementById('share-text-modal').classList.add('hidden');
  }

  function selectShareTab(tab) {
    activeShareTab = tab;
    const btnGroup = document.getElementById('tab-share-group');
    const btnStaff = document.getElementById('tab-share-staff');
    const staffWrapper = document.getElementById('share-staff-select-wrapper');

    if (tab === 'group') {
      btnGroup.className = 'px-3 py-1.5 rounded-xl bg-emerald-600 text-white shadow-2xs';
      btnStaff.className = 'px-3 py-1.5 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200';
      staffWrapper.classList.add('hidden');
      document.getElementById('share-text-area').value = shareTextData ? shareTextData.full_text : '';
    } else {
      btnStaff.className = 'px-3 py-1.5 rounded-xl bg-emerald-600 text-white shadow-2xs';
      btnGroup.className = 'px-3 py-1.5 rounded-xl bg-slate-100 text-slate-600 hover:bg-slate-200';
      staffWrapper.classList.remove('hidden');
      renderStaffShareText();
    }
  }

  function renderStaffShareText() {
    if (!shareTextData) return;
    const userId = parseInt(document.getElementById('share-staff-select').value, 10);
    const item = (shareTextData.by_staff || []).find(x => x.user_id === userId);
    document.getElementById('share-text-area').value = item ? item.text : '';
  }

  async function copyShareText() {
    const text = document.getElementById('share-text-area').value;
    if (!text) return;
    try {
      await navigator.clipboard.writeText(text);
      showToast('クリップボードにコピーしました！LINEへ貼り付けられます✨');
    } catch (e) {
      const area = document.getElementById('share-text-area');
      area.select();
      document.execCommand('copy');
      showToast('テキストをコピーしました');
    }
  }
