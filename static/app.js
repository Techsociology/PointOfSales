(function () {
  const products    = window.__PRODUCTS__    || [];
  const currentUser = window.__CURRENT_USER__ || "";

  // ---- State ----
  let currentCategory = "all";
  let paymentMethod   = "cash";
  let tipAmount       = 0;
  let discountAmount  = 0;   // flat dollar discount / comp
  let splits          = [];   // [{method, amount}] — only used when split mode is on
  let splitMode       = false;
  let modalProduct    = null;
  let modalSelectedMods = new Set();
  let modalQty        = 1;

  // Multi-ticket state
  // Each ticket: { id: null|<server id>, label, note, items: [], paymentMethod, tipAmount }
  let tickets   = [];
  let activeIdx = 0;

  // ---- DOM refs ----
  const grid          = document.getElementById("productGrid");
  const tabs          = document.getElementById("catTabs");
  const ticketItemsEl = document.getElementById("ticketItems");
  const ticketTotalEl = document.getElementById("ticketTotal");
  const ticketTitleEl = document.getElementById("ticketTitle");
  const modal         = document.getElementById("modifierModal");
  const tipDisplayEl  = document.getElementById("tipDisplay");
  const tipCustomEl   = document.getElementById("tipCustom");
  const ticketTabsEl  = document.getElementById("ticketTabs");
  const newTicketModal   = document.getElementById("newTicketModal");
  const noteModal        = document.getElementById("noteModal");
  const renameModal      = document.getElementById("renameModal");
  const splitModal       = document.getElementById("splitModal");
  const cardNamesModal   = document.getElementById("cardNamesModal");

  // ---- Helpers ----
  function money(n) { return "$" + parseFloat(n).toFixed(2); }
  function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }
  function activeTicket() { return tickets[activeIdx]; }

  // ---- Init tickets from server ----
  // "Quick Order" is now always persisted to the server (as a tab labelled
  // "Quick Order") so items survive a page refresh.  If one already exists in
  // __OPEN_TICKETS__ we reuse it; otherwise we create one on the server now.
  async function initTickets() {
    const serverTabs  = window.__OPEN_TICKETS__ || [];
    const quickServer = serverTabs.find(t => t.label === "Quick Order");

    // Build the local ticket list: Quick Order first, then all other named tabs
    tickets   = [];
    activeIdx = 0;

    if (quickServer) {
      tickets.push({ id: quickServer.id, label: "Quick Order", note: "", items: [], paymentMethod: "cash", tipAmount: 0 });
    } else {
      // Create a fresh Quick Order tab on the server
      const created = await createServerTicket("Quick Order");
      tickets.push({ id: created ? created.ticket_id : null, label: "Quick Order", note: "", items: [], paymentMethod: "cash", tipAmount: 0 });
    }

    serverTabs.forEach(t => {
      if (t.label !== "Quick Order") {
        tickets.push({ id: t.id, label: t.label, note: t.note || "", items: [], paymentMethod: "cash", tipAmount: 0 });
      }
    });

    // Load items for all server-backed tabs
    tickets.forEach((t, i) => { if (t.id) loadTicketItems(t, i); });

    renderTicketTabs();
    syncTicketPaymentUI();
    renderGrid();
    renderTicket();
  }

  async function createServerTicket(label) {
    try {
      const res  = await fetch("/api/ticket/create", {
        method:  "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body:    JSON.stringify({ label }),
      });
      return await res.json();
    } catch (e) { return null; }
  }

  function getCSRFToken() {
    // Flask-WTF puts the token in a meta tag we inject via base.html
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
  }

  async function loadTicketItems(ticket, idx) {
    try {
      const res  = await fetch("/api/ticket/" + ticket.id);
      const data = await res.json();
      if (data.items) {
        ticket.items = data.items;
        ticket.note  = data.note || "";
        ticket.color = data.color || "";
        if (idx === activeIdx) renderTicket();
        renderTicketTabs();
      }
    } catch (e) {}
  }

  // ---- Ticket tab bar ----
  function renderTicketTabs() {
    ticketTabsEl.innerHTML = "";
    tickets.forEach((t, i) => {
      const btn = document.createElement("button");
      btn.type      = "button";
      btn.className = "ticket-tab" + (i === activeIdx ? " active" : "");
      if (t.id) btn.dataset.id = t.id;
      if (t.color) btn.dataset.color = t.color;
      const noteIcon = t.note ? ' <span class="tab-note-dot" title="Has note">●</span>' : "";
      btn.innerHTML = escapeHtml(t.label) + noteIcon;
      if (i > 0) {
        const x = document.createElement("span");
        x.className   = "tab-close";
        x.textContent = "×";
        x.title       = "Close tab";
        x.addEventListener("click", (e) => { e.stopPropagation(); confirmCloseTab(i); });
        btn.appendChild(x);
      }
      btn.addEventListener("click", () => switchTab(i));
      ticketTabsEl.appendChild(btn);
    });
  }

  function switchTab(idx) {
    activeIdx = idx;
    splitMode = false;
    splits    = [];
    renderTicketTabs();
    syncTicketPaymentUI();
    renderTicket();
  }

  function syncTicketPaymentUI() {
    const t = activeTicket();
    paymentMethod = t.paymentMethod || "cash";
    tipAmount     = t.tipAmount || 0;
    document.querySelectorAll(".pay-opt").forEach(b => {
      b.classList.toggle("active", b.dataset.pay === paymentMethod);
    });
    document.querySelectorAll(".tip-preset").forEach(b => b.classList.remove("active"));
    if (tipCustomEl) tipCustomEl.value = tipAmount > 0 ? tipAmount.toFixed(2) : "";
    if (tipDisplayEl) tipDisplayEl.textContent = money(tipAmount);
    if (ticketTitleEl) {
      ticketTitleEl.textContent = t.id ? "TAB: " + t.label.toUpperCase() : "QUICK ORDER";
    }
    // Show Rename button only for saved tabs (those with a server id)
    const renameBtn = document.getElementById("renameTabBtn");
    if (renameBtn) renameBtn.style.display = t.id ? "" : "none";
    updateNoteBtn();
    // Sync discount / comp state when switching tabs
    discountAmount = t.discountAmount || 0;
    const _compPanel   = document.getElementById("compPanel");
    const _compDisplay = document.getElementById("compDisplay");
    const _compCustom  = document.getElementById("compCustom");
    if (_compPanel) _compPanel.style.display = "none";
    if (_compDisplay) {
      if (discountAmount > 0) {
        _compDisplay.textContent  = "Discount: -$" + discountAmount.toFixed(2);
        _compDisplay.style.display = "block";
      } else {
        _compDisplay.style.display = "none";
      }
    }
    if (_compCustom) _compCustom.value = discountAmount > 0 ? discountAmount.toFixed(2) : "";
    document.querySelectorAll(".comp-preset").forEach(b => b.classList.remove("active"));
  }

  function updateNoteBtn() {
    const noteBtn = document.getElementById("noteBtn");
    if (!noteBtn) return;
    const t = activeTicket();
    noteBtn.textContent = t.note ? "📝 Note ✓" : "📝 Note";
    noteBtn.classList.toggle("has-note", !!t.note);
  }

  async function confirmCloseTab(idx) {
    const t = tickets[idx];
    if (t.items.length > 0) {
      if (!confirm('Close "' + t.label + '"? Items will be discarded (not charged).')) return;
    }
    if (t.id) {
      try { await fetch("/api/ticket/" + t.id + "/delete", { method: "POST", headers: { "X-CSRFToken": getCSRFToken() } }); } catch(e) {}
    }
    tickets.splice(idx, 1);
    if (activeIdx >= tickets.length) activeIdx = tickets.length - 1;
    renderTicketTabs();
    syncTicketPaymentUI();
    renderTicket();
  }

  // ---- New tab modal ----
  document.getElementById("newTicketBtn").addEventListener("click", () => {
    document.getElementById("newTicketLabel").value = "";
    document.getElementById("newTicketFromCard").value = "";
    newTicketModal.classList.add("show");
    setTimeout(() => document.getElementById("newTicketLabel").focus(), 80);
  });
  document.getElementById("newTicketCancel").addEventListener("click", () => {
    newTicketModal.classList.remove("show");
  });
  newTicketModal.addEventListener("click", (e) => {
    if (e.target === newTicketModal) newTicketModal.classList.remove("show");
  });

  // Populate saved card names in the new-tab modal
  async function loadCardNamesForNewTab() {
    try {
      const res   = await fetch("/api/card-names");
      const names = await res.json();
      const sel   = document.getElementById("newTicketFromCard");
      sel.innerHTML = '<option value="">— pick from card on file —</option>';
      names.forEach(n => {
        const opt = document.createElement("option");
        opt.value       = n;
        opt.textContent = n;
        sel.appendChild(opt);
      });
    } catch(e) {}
  }
  document.getElementById("newTicketBtn").addEventListener("click", loadCardNamesForNewTab, { once: false });

  document.getElementById("newTicketFromCard").addEventListener("change", function() {
    if (this.value) document.getElementById("newTicketLabel").value = this.value;
  });

  document.getElementById("newTicketConfirm").addEventListener("click", async () => {
    const label = document.getElementById("newTicketLabel").value.trim() || "Tab";
    newTicketModal.classList.remove("show");
    try {
      const res  = await fetch("/api/ticket/create", {
        method:  "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body:    JSON.stringify({ label }),
      });
      const data = await res.json();
      if (data.success) {
        tickets.push({ id: data.ticket_id, label: data.label, note: "", items: [], paymentMethod: "cash", tipAmount: 0 });
        activeIdx = tickets.length - 1;
        renderTicketTabs();
        syncTicketPaymentUI();
        renderTicket();
      }
    } catch (e) { alert("Could not create tab."); }
  });

  // ---- Edit Tab modal (rename + colour) ----
  let _editTabPendingColor = null;   // tracks colour selected in the modal

  function openEditTabModal() {
    const t = activeTicket();
    if (!t.id) return;

    document.getElementById("renameTabInput").value = t.label;
    _editTabPendingColor = t.color || "";

    // Sync colour swatches to current tab colour
    document.querySelectorAll("#editTabColorRow .color-swatch").forEach(sw => {
      sw.classList.toggle("selected", sw.dataset.color === _editTabPendingColor);
    });

    // Populate saved card names
    (async () => {
      const sel = document.getElementById("renameFromCard");
      try {
        const res   = await fetch("/api/card-names");
        const names = await res.json();
        sel.innerHTML = '<option value="">— pick from card on file —</option>';
        names.forEach(n => {
          const opt = document.createElement("option");
          opt.value = n; opt.textContent = n;
          sel.appendChild(opt);
        });
      } catch(e) {}
    })();

    renameModal.classList.add("show");
    setTimeout(() => document.getElementById("renameTabInput").focus(), 80);
  }

  document.getElementById("renameTabBtn").addEventListener("click", openEditTabModal);
  document.getElementById("renameTabCancel").addEventListener("click", () => renameModal.classList.remove("show"));
  renameModal.addEventListener("click", (e) => { if (e.target === renameModal) renameModal.classList.remove("show"); });

  document.getElementById("renameFromCard").addEventListener("change", function() {
    if (this.value) document.getElementById("renameTabInput").value = this.value;
  });

  // Colour swatch click in the modal
  document.getElementById("editTabColorRow").addEventListener("click", (e) => {
    const sw = e.target.closest(".color-swatch");
    if (!sw) return;
    _editTabPendingColor = sw.dataset.color;
    document.querySelectorAll("#editTabColorRow .color-swatch").forEach(s => {
      s.classList.toggle("selected", s === sw);
    });
  });

  document.getElementById("renameTabConfirm").addEventListener("click", async () => {
    const t     = activeTicket();
    if (!t.id) return;
    const label = document.getElementById("renameTabInput").value.trim() || t.label;
    const color = _editTabPendingColor ?? (t.color || "");
    renameModal.classList.remove("show");

    try {
      // Save label
      const res  = await fetch("/api/ticket/" + t.id + "/rename", {
        method:  "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body:    JSON.stringify({ label }),
      });
      const data = await res.json();
      if (data.success) t.label = data.label;

      // Save colour (only if changed)
      if (color !== (t.color || "")) {
        const cres  = await fetch("/api/ticket/" + t.id + "/color", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify({ color }),
        });
        const cdata = await cres.json();
        if (cdata.success) t.color = cdata.color;
      }

      renderTicketTabs();
      syncTicketPaymentUI();
    } catch(e) { alert("Could not save tab."); }
  });

  // ---- Order note modal ----
  document.getElementById("noteBtn").addEventListener("click", () => {
    const t = activeTicket();
    document.getElementById("noteInput").value = t.note || "";
    document.getElementById("noteModalTitle").textContent =
      t.id ? `Note for "${t.label}"` : "Note for this order";
    noteModal.classList.add("show");
    setTimeout(() => document.getElementById("noteInput").focus(), 80);
  });
  document.getElementById("noteCancel").addEventListener("click", () => noteModal.classList.remove("show"));
  noteModal.addEventListener("click", (e) => { if (e.target === noteModal) noteModal.classList.remove("show"); });
  document.getElementById("noteSave").addEventListener("click", async () => {
    const t    = activeTicket();
    const note = document.getElementById("noteInput").value.trim();
    t.note     = note;
    noteModal.classList.remove("show");
    updateNoteBtn();
    renderTicketTabs();
    // Persist note to server if saved tab
    if (t.id) {
      try {
        await fetch("/api/ticket/" + t.id + "/note", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify({ note }),
        });
      } catch(e) {}
    }
  });

  // ---- Split payment modal ----
  document.getElementById("splitBtn").addEventListener("click", () => {
    const t = activeTicket();
    if (t.items.length === 0) { alert("Add items before splitting payment."); return; }
    const total = getSubtotal() + tipAmount;
    openSplitModal(total);
  });

  function redistributeEvenly() {
    const total = parseFloat(document.getElementById("splitTotal").textContent.replace("$","")) || 0;
    const allRows = document.querySelectorAll("#splitRows .split-row");
    if (!allRows.length) return;
    const share = (total / allRows.length).toFixed(2);
    let distributed = 0;
    allRows.forEach((r, i) => {
      const input = r.querySelector(".split-amount");
      if (i < allRows.length - 1) {
        input.value = share;
        distributed += parseFloat(share);
      } else {
        input.value = (total - distributed).toFixed(2);
      }
    });
    updateSplitBalance(total);
  }

  function openSplitModal(total) {
    document.getElementById("splitTotal").textContent = money(total);
    const splitRows = document.getElementById("splitRows");
    splitRows.innerHTML = "";
    addSplitRow(splitRows, "cash", "0.00");
    addSplitRow(splitRows, "card", "0.00");
    redistributeEvenly();
    splitModal.classList.add("show");
  }

  function addSplitRow(container, method, amount) {
    const row = document.createElement("div");
    row.className = "split-row";
    row.innerHTML = `
      <select class="split-method">
        <option value="cash"  ${method==="cash"  ? "selected":""}>Cash</option>
        <option value="card"  ${method==="card"  ? "selected":""}>Card</option>
        <option value="other" ${method==="other" ? "selected":""}>Other</option>
      </select>
      <input type="number" class="split-amount" min="0" step="0.01" value="${amount}" placeholder="0.00">
      <button type="button" class="btn btn-ghost btn-sm split-remove" title="Remove">×</button>
    `;
    row.querySelector(".split-remove").addEventListener("click", () => {
      row.remove();
      redistributeEvenly();
    });
    row.querySelector(".split-amount").addEventListener("input", () => {
      const total = parseFloat(document.getElementById("splitTotal").textContent.replace("$","")) || 0;
      updateSplitBalance(total);
    });
    container.appendChild(row);
  }

  function updateSplitBalance(total) {
    const rows = document.querySelectorAll(".split-amount");
    const sum  = Array.from(rows).reduce((a, el) => a + (parseFloat(el.value) || 0), 0);
    const diff = total - sum;
    const el   = document.getElementById("splitBalance");
    el.textContent = Math.abs(diff) < 0.005 ? "✓ Balanced" : `Remaining: ${money(diff)}`;
    el.className   = Math.abs(diff) < 0.005 ? "split-balance ok" : "split-balance bad";
  }

  document.getElementById("splitAddRow").addEventListener("click", () => {
    addSplitRow(document.getElementById("splitRows"), "cash", "0.00");
    redistributeEvenly();
  });
  document.getElementById("splitRefresh").addEventListener("click", redistributeEvenly);
  document.getElementById("splitCancel").addEventListener("click", () => splitModal.classList.remove("show"));
  splitModal.addEventListener("click", (e) => { if (e.target === splitModal) splitModal.classList.remove("show"); });
  document.getElementById("splitConfirm").addEventListener("click", () => {
    const total  = parseFloat(document.getElementById("splitTotal").textContent.replace("$","")) || 0;
    const rows   = document.querySelectorAll("#splitRows .split-row");
    const result = [];
    let sum = 0;
    rows.forEach(r => {
      const method = r.querySelector(".split-method").value;
      const amount = parseFloat(r.querySelector(".split-amount").value) || 0;
      result.push({ method, amount });
      sum += amount;
    });
    if (Math.abs(sum - total) > 0.02) {
      alert(`Split amounts ($${sum.toFixed(2)}) don't match the total ($${total.toFixed(2)}). Adjust the amounts.`);
      return;
    }
    splits    = result;
    splitMode = true;
    splitModal.classList.remove("show");
    // Show split summary in ticket
    renderSplitIndicator();
  });

  function renderSplitIndicator() {
    const el = document.getElementById("splitIndicator");
    if (!el) return;
    if (splitMode && splits.length) {
      el.style.display = "";
      el.innerHTML = "Split: " + splits.map(s => `${s.method} ${money(s.amount)}`).join(" + ");
    } else {
      el.style.display = "none";
      el.innerHTML = "";
    }
  }

  // ---- Manage saved names modal ----
  async function openSavedNamesModal() {
    await refreshCardNamesList();
    cardNamesModal.classList.add("show");
  }
  document.getElementById("manageCardNamesBtn").addEventListener("click", openSavedNamesModal);
  const manageCardNamesBtnRename = document.getElementById("manageCardNamesBtnRename");
  if (manageCardNamesBtnRename) {
    manageCardNamesBtnRename.addEventListener("click", openSavedNamesModal);
  }
  document.getElementById("cardNamesClose").addEventListener("click", () => cardNamesModal.classList.remove("show"));
  cardNamesModal.addEventListener("click", (e) => { if (e.target === cardNamesModal) cardNamesModal.classList.remove("show"); });

  document.getElementById("cardNameAdd").addEventListener("click", async () => {
    const input = document.getElementById("cardNameInput");
    const name  = input.value.trim();
    if (!name) return;
    try {
      await fetch("/api/card-names", {
        method:  "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body:    JSON.stringify({ action: "add", name }),
      });
      input.value = "";
      await refreshCardNamesList();
    } catch(e) { alert("Could not save name."); }
  });

  async function refreshCardNamesList() {
    const list = document.getElementById("cardNamesList");
    list.innerHTML = "<em>Loading…</em>";
    try {
      const res   = await fetch("/api/card-names");
      const names = await res.json();
      list.innerHTML = "";
      if (!names.length) {
        list.innerHTML = '<em style="color:var(--text-dim);font-size:13px;">No names saved yet.</em>';
        return;
      }
      names.forEach(n => {
        const row = document.createElement("div");
        row.className = "card-name-row";
        row.innerHTML = `<span>${escapeHtml(n)}</span>
          <button type="button" class="btn btn-ghost btn-sm" data-name="${escapeHtml(n)}">Remove</button>`;
        row.querySelector("button").addEventListener("click", async () => {
          await fetch("/api/card-names", {
            method:  "POST",
            headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
            body:    JSON.stringify({ action: "remove", name: n }),
          });
          await refreshCardNamesList();
        });
        list.appendChild(row);
      });
    } catch(e) {
      list.innerHTML = '<em style="color:var(--danger)">Could not load names.</em>';
    }
  }

  // ---- Product grid ----
  function renderGrid() {
    grid.innerHTML = "";
    const filtered = products.filter(
      (p) => currentCategory === "all" || String(p.category_id) === String(currentCategory)
    );
    if (filtered.length === 0) {
      grid.innerHTML = '<p class="empty-msg">No products in this category yet.</p>';
      return;
    }
    filtered.forEach((p) => {
      const card = document.createElement("button");
      card.type          = "button";
      card.className     = "product-card";
      card.dataset.name  = p.name;           // for search filter
      card.innerHTML = `
        <span class="pname pc-name">${escapeHtml(p.name)}</span>
        <span class="pprice">${money(p.price)}</span>
        ${p.modifiers.length ? `<span class="pmods">${p.modifiers.length} option${p.modifiers.length > 1 ? "s" : ""}</span>` : ""}
      `;
      card.addEventListener("click", () => openModifierModal(p));
      grid.appendChild(card);
    });
    // Re-apply search filter after grid re-render
    const searchEl = document.getElementById("drinkSearch");
    if (searchEl && searchEl.value.trim()) {
      searchEl.dispatchEvent(new Event("input"));
    }
  }

  tabs.addEventListener("click", (e) => {
    const btn = e.target.closest(".cat-tab");
    if (!btn) return;
    tabs.querySelectorAll(".cat-tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentCategory = btn.dataset.cat;
    renderGrid();
  });

  // ---- Modifier modal ----
  function openModifierModal(product) {
    modalProduct      = product;
    modalSelectedMods = new Set();
    modalQty          = 1;
    document.getElementById("modProductName").textContent = product.name;
    document.getElementById("modBasePrice").textContent   = "Base price " + money(product.price);
    document.getElementById("qtyValue").textContent       = "1";

    const list = document.getElementById("modList");
    list.innerHTML = "";
    if (product.modifiers.length === 0) {
      list.innerHTML = '<p class="login-sub">No options for this item — just add it straight to the ticket.</p>';
    } else {
      product.modifiers.forEach((m) => {
        const row = document.createElement("div");
        row.className = "mod-option";
        row.innerHTML = `
          <span>${escapeHtml(m.name)}</span>
          <span class="mo-price">${m.price_delta >= 0 ? "+" : ""}${money(m.price_delta)}</span>
        `;
        row.addEventListener("click", () => {
          if (modalSelectedMods.has(m.id)) {
            modalSelectedMods.delete(m.id);
            row.classList.remove("checked");
          } else {
            modalSelectedMods.add(m.id);
            row.classList.add("checked");
          }
        });
        list.appendChild(row);
      });
    }
    modal.classList.add("show");
  }

  document.getElementById("modCancel").addEventListener("click", () => modal.classList.remove("show"));
  document.getElementById("qtyMinus").addEventListener("click", () => {
    modalQty = Math.max(1, modalQty - 1);
    document.getElementById("qtyValue").textContent = modalQty;
  });
  document.getElementById("qtyPlus").addEventListener("click", () => {
    modalQty += 1;
    document.getElementById("qtyValue").textContent = modalQty;
  });
  document.getElementById("modAdd").addEventListener("click", async () => {
    if (!modalProduct) return;
    const chosenMods = modalProduct.modifiers.filter((m) => modalSelectedMods.has(m.id));
    const modsTotal  = chosenMods.reduce((sum, m) => sum + m.price_delta, 0);
    const unitPrice  = modalProduct.price + modsTotal;
    const lineTotal  = unitPrice * modalQty;
    const newItem    = {
      product_id:   modalProduct.id,
      product_name: modalProduct.name,
      base_price:   modalProduct.price,
      quantity:     modalQty,
      modifiers:    chosenMods.map((m) => ({ id: m.id, name: m.name, price_delta: m.price_delta })),
      line_total:   lineTotal,
    };
    modal.classList.remove("show");

    const t = activeTicket();
    t.items.push(newItem);

    if (t.id) {
      try {
        await fetch("/api/ticket/" + t.id + "/items", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify({ items: [newItem] }),
        });
        await loadTicketItems(t, activeIdx);
      } catch (e) {}
    }
    renderTicket();
    // Reset split if items changed
    if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
  });
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("show"); });

  // ---- Tip ----
  function getSubtotal() {
    return activeTicket().items.reduce((sum, i) => sum + i.line_total, 0);
  }

  function updateTip(amount) {
    tipAmount = Math.max(0, parseFloat(amount) || 0);
    activeTicket().tipAmount = tipAmount;
    if (tipDisplayEl) tipDisplayEl.textContent = money(tipAmount);
    const disc = activeTicket().discountAmount || 0;
    ticketTotalEl.textContent = money(Math.max(0, getSubtotal() - disc + tipAmount));
    if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
  }

  if (tipCustomEl) {
    tipCustomEl.addEventListener("input", () => {
      document.querySelectorAll(".tip-preset").forEach((b) => b.classList.remove("active"));
      updateTip(tipCustomEl.value);
    });
  }

  document.querySelectorAll(".tip-preset").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tip-preset").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const pct      = parseFloat(btn.dataset.pct) / 100;
      const subtotal = getSubtotal();
      const computed = pct === 0 ? 0 : Math.round(subtotal * pct * 100) / 100;
      if (tipCustomEl) tipCustomEl.value = computed > 0 ? computed.toFixed(2) : "";
      updateTip(computed);
    });
  });

  // ---- Ticket / cart ----
  function renderTicket() {
    const t = activeTicket();
    if (t.items.length === 0) {
      ticketItemsEl.innerHTML = '<div class="ticket-empty">No items yet — tap a drink to add it.</div>';
    } else {
      ticketItemsEl.innerHTML = "";
      t.items.forEach((item, idx) => {
        const div      = document.createElement("div");
        div.className  = "ticket-item";
        const modLines = item.modifiers
          .map((m) => `<div class="ti-mod">+ ${escapeHtml(m.name)}${m.price_delta ? " (" + money(m.price_delta) + ")" : ""}</div>`)
          .join("");
        div.innerHTML = `
          <div class="ti-row">
            <span>${item.quantity}&times; ${escapeHtml(item.product_name)}</span>
            <span>${money(item.line_total)}</span>
          </div>
          ${modLines}
          <div class="ti-remove" data-idx="${idx}" data-item-id="${item.id || ""}">remove</div>
        `;
        ticketItemsEl.appendChild(div);
      });
    }

    // Recalculate tip presets
    const activePct = document.querySelector(".tip-preset.active");
    if (activePct) {
      const pct      = parseFloat(activePct.dataset.pct) / 100;
      const subtotal = getSubtotal();
      const computed = pct === 0 ? 0 : Math.round(subtotal * pct * 100) / 100;
      if (tipCustomEl) tipCustomEl.value = computed > 0 ? computed.toFixed(2) : "";
      updateTip(computed);
    } else {
      updateTip(tipAmount);
    }
    updateNoteBtn();
    renderSplitIndicator();
  }

  ticketItemsEl.addEventListener("click", async (e) => {
    const el = e.target.closest(".ti-remove");
    if (!el) return;
    const idx    = Number(el.dataset.idx);
    const itemId = el.dataset.itemId;
    const t      = activeTicket();
    t.items.splice(idx, 1);
    if (t.id && itemId) {
      try {
        await fetch("/api/ticket/" + t.id + "/item/" + itemId + "/remove", { method: "POST", headers: { "X-CSRFToken": getCSRFToken() } });
      } catch (e) {}
    }
    if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
    renderTicket();
  });

  document.querySelectorAll(".pay-opt").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".pay-opt").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      paymentMethod = btn.dataset.pay;
      activeTicket().paymentMethod = paymentMethod;
      if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
    });
  });

  document.getElementById("clearCartBtn").addEventListener("click", async () => {
    const t = activeTicket();
    if (t.items.length && !confirm("Clear all items from this ticket?")) return;
    if (t.id && t.items.length) {
      try {
        await fetch("/api/ticket/" + t.id + "/delete", { method: "POST", headers: { "X-CSRFToken": getCSRFToken() } });
        const res  = await fetch("/api/ticket/create", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify({ label: t.label }),
        });
        const data = await res.json();
        if (data.success) t.id = data.ticket_id;
      } catch(e) {}
    }
    t.items  = [];
    tipAmount = 0; t.tipAmount = 0;
    splitMode = false; splits = [];
    if (tipCustomEl) tipCustomEl.value = "";
    document.querySelectorAll(".tip-preset").forEach((b) => b.classList.remove("active"));
    renderTicket();
  });

  // ---- Card Reader flow ----
  async function runCardReaderCharge(amount) {
    return new Promise((resolve, reject) => {
      const modal    = document.getElementById("cardReaderModal");
      const statusEl = document.getElementById("cardReaderStatus");
      const spinner  = document.getElementById("cardReaderSpinner");
      const testBtns = document.getElementById("cardReaderTestBtns");
      const cancelBtn= document.getElementById("cardReaderCancel");
      const simOk    = document.getElementById("crSimSuccess");
      const simFail  = document.getElementById("crSimDecline");

      statusEl.textContent = "Sending $" + amount.toFixed(2) + " to reader…";
      spinner.textContent  = "⏳";
      testBtns.style.display = "none";
      modal.style.display  = "flex";

      let settled = false;
      function done(ok, err) {
        if (settled) return;
        settled = true;
        modal.style.display = "none";
        if (ok) resolve(); else reject(err || "Card reader cancelled.");
      }

      cancelBtn.onclick = () => done(false, "Cancelled.");

      fetch("/api/stripe/create-payment-intent", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
        body: JSON.stringify({ amount }),
      })
      .then(r => r.json())
      .then(data => {
        if (data.error) { done(false, data.error); return; }

        statusEl.textContent = "Waiting for card tap…";
        spinner.textContent  = "💳";

        // Show simulate buttons only for the simulated reader (test mode)
        const isSimulated = window.__CARD_READER_TYPE__ === "stripe";
        if (isSimulated) {
          testBtns.style.display = "block";
          simOk.onclick = () => {
            fetch("/api/stripe/simulate-present", {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
              body: JSON.stringify({}),
            })
            .then(r => r.json())
            .then(d => {
              if (d.error) { done(false, d.error); return; }
              statusEl.textContent = "✅ Payment approved!";
              spinner.textContent  = "✅";
              setTimeout(() => done(true), 800);
            })
            .catch(() => done(false, "Network error during simulate."));
          };
          simFail.onclick = () => {
            fetch("/api/stripe/simulate-present", {
              method: "POST",
              headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
              body: JSON.stringify({ card_number: "4000000000000002" }),
            })
            .then(r => r.json())
            .then(() => {
              statusEl.textContent = "❌ Card declined.";
              spinner.textContent  = "❌";
              setTimeout(() => done(false, "Card declined."), 1000);
            })
            .catch(() => done(false, "Network error during simulate."));
          };
        }
      })
      .catch(err => done(false, "Network error: " + err));
    });
  }

  document.getElementById("chargeBtn").addEventListener("click", async () => {
    const t = activeTicket();
    if (t.items.length === 0) { alert("Add at least one item first."); return; }

    const btn = document.getElementById("chargeBtn");
    const usingReader = !splitMode && paymentMethod === "card" && window.__CARD_READER_LIVE__;

    // --- Card Reader path ---
    if (usingReader) {
      const subtotal = t.items.reduce((s, i) => s + i.line_total, 0);
      const disc  = t.discountAmount || 0;
      const total = Math.max(0, subtotal - disc + tipAmount);
      btn.disabled = true; btn.textContent = "Processing…";
      try {
        await runCardReaderCharge(total);
      } catch (err) {
        alert(err || "Card reader charge failed.");
        btn.disabled = false; btn.textContent = "Charge & Print Ticket";
        return;
      }
      // fall through to save the order normally after reader succeeds
    }

    btn.disabled    = true;
    btn.textContent = "Processing…";

    try {
      const payload = {
        payment_method: splitMode ? (splits[0]?.method || "cash") : paymentMethod,
        tip:      tipAmount,
        discount: discountAmount || 0,
        note:     t.note || "",
        splits:   splitMode ? splits : [],
      };

      let orderId;

      if (t.id) {
        const res  = await fetch("/api/ticket/" + t.id + "/checkout", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || "Something went wrong.");
          btn.disabled = false; btn.textContent = "Charge & Print Ticket"; return;
        }
        orderId = data.order_id;
        tickets.splice(activeIdx, 1);
        if (activeIdx >= tickets.length) activeIdx = tickets.length - 1;
        renderTicketTabs();
      } else {
        const res  = await fetch("/api/order", {
          method:  "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": getCSRFToken() },
          body:    JSON.stringify({ items: t.items, ...payload }),
        });
        const data = await res.json();
        if (!res.ok) {
          alert(data.error || "Something went wrong.");
          btn.disabled = false; btn.textContent = "Charge & Print Ticket"; return;
        }
        orderId = data.order_id;
        t.items = []; tipAmount = 0; t.tipAmount = 0; t.note = "";
        discountAmount = 0; t.discountAmount = 0;
        splitMode = false; splits = [];
        if (tipCustomEl) tipCustomEl.value = "";
        if (compCustomEl) compCustomEl.value = "";
        if (compDisplay) compDisplay.style.display = "none";
        if (compPanel) compPanel.style.display = "none";
        document.querySelectorAll(".tip-preset").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".comp-preset").forEach((b) => b.classList.remove("active"));
        renderTicket();
      }

      window.location.href = "/history/" + orderId;
    } catch (err) {
      alert("Network error — order was not saved.");
      btn.disabled    = false;
      btn.textContent = "Charge & Print Ticket";
    }
  });

  // ---- Comp / Discount ----
  const compPanel    = document.getElementById("compPanel");
  const compCustomEl = document.getElementById("compCustom");
  const compDisplay  = document.getElementById("compDisplay");

  function applyDiscount(amount) {
    const subtotal = getSubtotal();
    discountAmount = Math.min(Math.max(0, parseFloat(amount) || 0), subtotal);
    activeTicket().discountAmount = discountAmount;
    if (discountAmount > 0) {
      compDisplay.textContent = "Discount: -$" + discountAmount.toFixed(2);
      compDisplay.style.display = "block";
    } else {
      compDisplay.style.display = "none";
    }
    // Recompute total display
    const total = Math.max(0, subtotal - discountAmount + tipAmount);
    ticketTotalEl.textContent = money(total);
    if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
  }

  function clearDiscount() {
    discountAmount = 0;
    if (activeTicket()) activeTicket().discountAmount = 0;
    if (compCustomEl) compCustomEl.value = "";
    if (compDisplay) compDisplay.style.display = "none";
    document.querySelectorAll(".comp-preset").forEach(b => b.classList.remove("active"));
    const subtotal = getSubtotal();
    ticketTotalEl.textContent = money(Math.max(0, subtotal + tipAmount));
    if (splitMode) { splitMode = false; splits = []; renderSplitIndicator(); }
  }

  document.getElementById("compBtn").addEventListener("click", () => {
    const visible = compPanel.style.display !== "none";
    compPanel.style.display = visible ? "none" : "block";
  });

  document.querySelectorAll(".comp-preset").forEach(btn => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".comp-preset").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      const pct      = parseFloat(btn.dataset.val) / 100;
      const subtotal = getSubtotal();
      const amount   = Math.round(subtotal * pct * 100) / 100;
      if (compCustomEl) compCustomEl.value = amount > 0 ? amount.toFixed(2) : "";
      applyDiscount(amount);
    });
  });

  document.getElementById("compApplyBtn").addEventListener("click", () => {
    document.querySelectorAll(".comp-preset").forEach(b => b.classList.remove("active"));
    applyDiscount(compCustomEl ? compCustomEl.value : 0);
  });

  document.getElementById("compClearBtn").addEventListener("click", clearDiscount);

  // ---- Bootstrap ----
  initTickets();
})();

// ================================================================
// DRINK SEARCH (fuzzy filter)
// ================================================================
(function() {
  var searchEl = document.getElementById("drinkSearch");
  var clearBtn = document.getElementById("drinkSearchClear");
  if (!searchEl) return;

  function normalize(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ""); }

  function fuzzyMatch(query, text) {
    if (!query) return true;
    var q = normalize(query);
    var t = normalize(text);
    // Simple: all query chars must appear in order in text (subsequence match)
    var qi = 0;
    for (var i = 0; i < t.length && qi < q.length; i++) {
      if (t[i] === q[qi]) qi++;
    }
    return qi === q.length;
  }

  function doSearch() {
    var query = searchEl.value.trim();
    clearBtn.classList.toggle("visible", query.length > 0);

    var grid = document.getElementById("productGrid");
    if (!grid) return;
    var cards = grid.querySelectorAll(".product-card");
    var anyVisible = false;

    cards.forEach(function(card) {
      var name = card.dataset.name || card.querySelector(".pc-name")?.textContent || "";
      var match = !query || fuzzyMatch(query, name);
      card.classList.toggle("search-hidden", !match);
      if (match) anyVisible = true;
    });

    // No results message
    var noRes = grid.querySelector(".search-no-results");
    if (!noRes) {
      noRes = document.createElement("div");
      noRes.className = "search-no-results";
      noRes.textContent = 'No drinks match "' + query + '".';
      grid.appendChild(noRes);
    } else {
      noRes.textContent = 'No drinks match "' + query + '".';
    }
    noRes.style.display = (!anyVisible && query) ? "block" : "none";
  }

  searchEl.addEventListener("input", doSearch);
  clearBtn.addEventListener("click", function() {
    searchEl.value = "";
    doSearch();
    searchEl.focus();
  });
})();

// Colour-coded tabs: handled in the Edit Tab modal (see renameTabConfirm listener above)
