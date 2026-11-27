(() => {
  const byId = (id) => document.getElementById(id);
  const view = document.body.dataset.view;
  const filters = byId('filters');
  const refresh = byId('refresh');
  const dialog = byId('case-dialog');
  const editor = byId('case-editor');
  const editButton = byId('open-editor');
  const bangkok = [13.7563, 100.5018];
  const priorityLabels = {HIGH: 'สูง', MEDIUM: 'ปานกลาง', LOW: 'ต่ำ', UNKNOWN: 'ไม่ระบุ'};
  const priorities = Object.keys(priorityLabels);
  const date = new Intl.DateTimeFormat('th-TH', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Bangkok',
  });
  const time = new Intl.DateTimeFormat('th-TH', {
    timeStyle: 'medium', timeZone: 'Asia/Bangkok',
  });

  let cases = [];
  let snapshot;
  let currentRequest;
  let refreshTimer;
  let searchTimer;
  let mapView;
  let editedCase;
  let pinMap;
  let saving = false;
  let dragging;

  function escape(value) {
    const entities = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
    return String(value ?? '').replace(/[&<>"']/g, (character) => entities[character]);
  }

  const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const title = (incident) => incident.title || 'กำลังรับรายละเอียด';
  const priority = (incident) => priorities.includes(incident.urgency) ? incident.urgency : 'UNKNOWN';
  const location = (incident) => incident.location || incident.service_area || 'ยังไม่ระบุสถานที่';
  const priorityPill = (incident) => `<span class="priority ${priority(incident)}"><i class="dot"></i>${priorityLabels[priority(incident)]}</span>`;

  function card(incident, index, board) {
    const draggable = view === 'board' && incident.update_url;
    return `
      <button type="button" class="${board ? 'card' : 'feed-case'}" data-case="${index}" ${draggable ? 'draggable="true"' : ''}>
        <span class="card-top"><span class="ticket-id">${escape(incident.ticket_id)}</span>${priorityPill(incident)}</span>
        <span class="card-title">${escape(title(incident))}</span>
        <span class="location">${icon('pin')}<span>${escape(location(incident))}</span></span>
        ${board
          ? `<span class="card-bottom"><time datetime="${escape(incident.updated_at)}">อัปเดต ${date.format(new Date(incident.updated_at))}</time>${icon('arrow')}</span>`
          : `<span class="feed-status">${escape(incident.status_label)}${incident.coordinates ? '' : ' · ไม่มีพิกัดบนแผนที่'}</span>`}
      </button>`;
  }

  const formatDate = (value) => value ? date.format(new Date(value)) : '';
  function slaState(incident) {
    if (!incident.sla_due_at) return 'รอจับคู่หมวด';
    const due = Date.parse(incident.sla_due_at);
    if (incident.resolved_at) return Date.parse(incident.resolved_at) <= due ? 'ทันกำหนด' : 'แก้ไขเสร็จเกินกำหนด';
    return due < Date.now() ? 'เกินกำหนด · ยังไม่บันทึกผล' : 'อยู่ในกำหนด';
  }

  function showCase(incident, openEditor = false) {
    if (editor) {
      editedCase = incident;
      editor.hidden = true;
      editButton.hidden = !incident.update_url;
      editButton.setAttribute('aria-expanded', 'false');
    }
    byId('case-id').textContent = incident.ticket_id;
    byId('case-title').textContent = title(incident);
    const fields = [
      ['สถานที่', location(incident)],
      ['เวลาที่เกิดเหตุ', formatDate(incident.occurred_at_normalized) || incident.occurred_at],
      ['รับแจ้งครั้งแรก', formatDate(incident.received_at)],
      ['ยืนยันส่งเรื่อง', formatDate(incident.submitted_at)],
      ['รหัสหมวดที่จับคู่', [incident.routing_category, incident.routing_level].filter(Boolean).join(' · ')],
      ['ทีมรับผิดชอบ', [incident.assigned_team, incident.assigned_team_label !== incident.assigned_team ? incident.assigned_team_label : ''].filter(Boolean).join(' · ') || 'รอมอบหมาย'],
      ['เวลามอบหมาย', formatDate(incident.assigned_at)],
      ['ครบกำหนด SLA', formatDate(incident.sla_due_at)],
      ['สถานะ SLA', slaState(incident)],
      ['แก้ไขเสร็จ', formatDate(incident.resolved_at)],
      ['เลขเคส GRC', incident.grc_case_id],
      ['สถานะส่งต่อ GRC', incident.grc_handoff_label],
      ['พื้นที่บริการ', incident.service_area],
      ['อัปเดตล่าสุด', date.format(new Date(incident.updated_at))],
      ['หมวดหมู่', [incident.category_level_1, incident.category_level_2].filter(Boolean).join(' / ')],
      ['ผู้ติดต่อ', incident.contact],
    ];
    const demoInbox = document.body.dataset.demoInboxUrl;
    byId('case-details').innerHTML = `
      <div class="detail-status"><span>${escape(incident.status_label)}</span>${priorityPill(incident)}</div>
      <dl class="detail-fields">${fields.map(([label, value]) => `<div><dt>${label}</dt><dd>${escape(value || '—')}</dd></div>`).join('')}</dl>
      <section class="detail-section"><h3>รายละเอียดเหตุ</h3><p>${escape(incident.description || 'ยังไม่มีรายละเอียด')}</p></section>
      ${incident.impact ? `<section class="detail-section"><h3>ผลกระทบ</h3><p>${escape(incident.impact)}</p></section>` : ''}
      ${incident.resolution_summary ? `<section class="detail-section"><h3>ผลการแก้ไข</h3><p>${escape(incident.resolution_summary)}</p></section>` : ''}
      ${incident.events.length ? `<section class="detail-section"><h3>ประวัติสถานะ</h3><ol class="detail-events">${incident.events.map((event) => `
        <li><time datetime="${escape(event.created_at)}">${date.format(new Date(event.created_at))}</time><br>
        <strong>${escape(event.status_label)}</strong> · ${escape(event.message)}</li>`).join('')}</ol></section>` : ''}
      ${demoInbox ? `<a class="button" href="${escape(demoInbox)}?ticket=${encodeURIComponent(incident.ticket_id)}">เปิดบทสนทนา</a>` : ''}`;
    dialog.showModal();
    if (openEditor && editor && incident.update_url) editButton.click();
  }

  function mapTiles(leaflet) {
    return leaflet.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      referrerPolicy: 'strict-origin-when-cross-origin',
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    });
  }

  function openPinMap(initial) {
    const leaflet = window.L;
    const fields = editor.elements;
    const container = byId('pin-map');
    const feedback = byId('pin-feedback');
    const gps = byId('device-location');
    const setFeedback = (text) => {
      feedback.textContent = text;
      feedback.hidden = !text;
    };
    container.hidden = !leaflet;
    setFeedback(leaflet ? '' : 'โหลดแผนที่ไม่สำเร็จ กรุณาใช้ GPS หรือกรอกพิกัดเอง');

    const map = leaflet?.map(container, {scrollWheelZoom: false}).setView(initial || bangkok, initial ? 15 : 11);
    if (map) {
      mapTiles(leaflet).on('tileerror', () => {
        setFeedback('โหลดภาพแผนที่ไม่สำเร็จ ยังสามารถใช้ GPS หรือกรอกพิกัดได้');
      }).addTo(map);
    }
    let marker;
    let active = true;
    function syncMarker() {
      const lat = fields.latitude.valueAsNumber;
      const lon = fields.longitude.valueAsNumber;
      if (!map || !(Math.abs(lat) <= 90 && Math.abs(lon) <= 180)) {
        marker?.remove();
        marker = undefined;
        return;
      }
      if (marker) marker.setLatLng([lat, lon]);
      else {
        marker = leaflet.marker([lat, lon], {draggable: true, title: 'จุดเกิดเหตุ'}).addTo(map);
        marker.on('dragend', () => choosePoint(marker.getLatLng()));
      }
    }
    function choosePoint({lat, lng}) {
      if (saving) {
        syncMarker();
        return;
      }
      fields.latitude.value = lat.toFixed(6);
      fields.longitude.value = lng.toFixed(6);
      syncMarker();
    }
    map?.on('click', (event) => choosePoint(map.wrapLatLng(event.latlng)));
    function coordinateChanged() {
      syncMarker();
      if (marker) map.panTo(marker.getLatLng());
    }
    fields.latitude.onchange = coordinateChanged;
    fields.longitude.onchange = coordinateChanged;
    syncMarker();
    gps.disabled = false;
    gps.onclick = () => {
      if (!navigator.geolocation) {
        setFeedback('อุปกรณ์นี้ไม่สามารถระบุตำแหน่งได้ กรุณาเลือกพิกัดเอง');
        return;
      }
      gps.disabled = true;
      setFeedback('กำลังหาตำแหน่งของอุปกรณ์…');
      navigator.geolocation.getCurrentPosition(({coords}) => {
        if (!active) return;
        gps.disabled = false;
        if (saving) {
          setFeedback('');
          return;
        }
        choosePoint({lat: coords.latitude, lng: coords.longitude});
        map?.setView([coords.latitude, coords.longitude], 16);
        setFeedback('เลือกตำแหน่งอุปกรณ์แล้ว กรุณาตรวจสอบว่าเป็นจุดเกิดเหตุ');
      }, () => {
        if (!active) return;
        gps.disabled = false;
        setFeedback('ไม่สามารถอ่าน GPS ได้ กรุณาตรวจสอบสิทธิ์ตำแหน่งหรือเลือกพิกัดเอง');
      }, {enableHighAccuracy: true, timeout: 10000});
    };
    return () => {
      active = false;
      map?.remove();
    };
  }

  async function saveCase(incident, values) {
    const response = await fetch(incident.update_url, {method: 'POST', body: values});
    if (response.redirected) throw new Error('เซสชันหมดอายุ กรุณาเข้าสู่ระบบอีกครั้ง');
    const result = await response.json().catch(() => null);
    if (!response.ok || !result?.ok) {
      throw new Error(result?.error || 'บันทึกเคสไม่สำเร็จ กรุณาลองใหม่');
    }
  }

  function caseFeedback(message, failed = false) {
    const feedback = byId('case-feedback');
    feedback.textContent = message;
    feedback.classList.toggle('error', failed);
    feedback.hidden = false;
  }

  if (editor) {
    const fields = editor.elements;
    const fieldset = editor.querySelector('fieldset');
    const error = byId('editor-error');
    editButton.addEventListener('click', () => {
      const initial = editedCase.saved_coordinates || editedCase.coordinates;
      fields.status.value = editedCase.status;
      fields.urgency.value = priority(editedCase) === 'UNKNOWN' ? '' : editedCase.urgency;
      fields.location.value = editedCase.location;
      fields.routing_category.value = editedCase.routing_category || '';
      fields.assigned_team.querySelector('[data-legacy-team]')?.remove();
      if (editedCase.assigned_team && !Array.from(fields.assigned_team.options).some(option => option.value === editedCase.assigned_team)) {
        const option = new Option(editedCase.assigned_team, editedCase.assigned_team);
        option.dataset.legacyTeam = '';
        fields.assigned_team.add(option);
      }
      fields.assigned_team.value = editedCase.assigned_team || '';
      fields.resolution_summary.value = editedCase.resolution_summary || '';
      fields.grc_case_id.value = editedCase.grc_case_id || '';
      fields.grc_handoff_status.value = editedCase.grc_handoff_status || '';
      fields.latitude.value = initial ? initial[0].toFixed(6) : '';
      fields.longitude.value = initial ? initial[1].toFixed(6) : '';
      fields.version.value = editedCase.updated_at;
      error.hidden = true;
      editor.hidden = false;
      editButton.setAttribute('aria-expanded', 'true');
      editButton.hidden = true;
      pinMap = openPinMap(initial);
      fields.status.focus();
    });
    dialog.addEventListener('close', () => {
      pinMap?.();
      pinMap = undefined;
    });
    dialog.addEventListener('cancel', (event) => {
      if (saving) event.preventDefault();
    });
    dialog.querySelector('form[method="dialog"]').addEventListener('submit', (event) => {
      if (saving) event.preventDefault();
    });
    editor.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (saving) return;
      const values = new FormData(editor);
      const statusChanged = values.get('status') !== editedCase.status;
      saving = true;
      fieldset.disabled = true;
      error.hidden = true;
      try {
        await saveCase(editedCase, values);
        caseFeedback(statusChanged
          ? 'บันทึกเคสแล้ว ส่งข้อความอัปเดตไปยังแชต BEM Care'
          : 'บันทึกข้อมูลเคสแล้ว');
        dialog.close();
        load();
      } catch (failure) {
        error.textContent = failure.message;
        error.hidden = false;
      } finally {
        saving = false;
        fieldset.disabled = false;
      }
    });

  }

  if (editor && view === 'board') {
    const board = document.querySelector('.board');
    const csrfToken = editor.elements.csrfmiddlewaretoken;
    function highlightLane(lane) {
      board.querySelector('.drop-target')?.classList.remove('drop-target');
      lane?.classList.add('drop-target');
    }

    function dropLane(event) {
      const lane = event.target.closest('[data-drop-status]');
      return dragging && lane?.dataset.dropStatus !== dragging.incident.status ? lane : null;
    }

    function clearDrag() {
      dragging?.card.classList.remove('dragging');
      dragging = undefined;
      highlightLane(null);
    }

    board.addEventListener('dragstart', (event) => {
      const source = event.target.closest('[draggable="true"][data-case]');
      if (!source || saving) {
        event.preventDefault();
        return;
      }
      const incident = cases[Number(source.dataset.case)];
      dragging = {incident, card: source};
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', incident.ticket_id);
      source.classList.add('dragging');
    });
    board.addEventListener('dragover', (event) => {
      const lane = dropLane(event);
      highlightLane(lane);
      if (!lane) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
    });
    board.addEventListener('dragleave', (event) => {
      if (!board.contains(event.relatedTarget)) highlightLane(null);
    });
    board.addEventListener('dragend', clearDrag);
    board.addEventListener('drop', async (event) => {
      const lane = dropLane(event);
      if (!lane) return;
      event.preventDefault();
      const {incident} = dragging;
      const status = lane.dataset.dropStatus;
      clearDrag();
      saving = true;
      board.setAttribute('aria-busy', 'true');
      byId('case-feedback').hidden = true;
      const values = new URLSearchParams({
        action: 'move', status, version: incident.updated_at,
        csrfmiddlewaretoken: csrfToken.value,
      });
      try {
        await saveCase(incident, values);
        caseFeedback('ย้ายเคสแล้ว ส่งข้อความอัปเดตไปยังแชต BEM Care');
      } catch (failure) {
        caseFeedback(failure.message, true);
      } finally {
        saving = false;
        board.removeAttribute('aria-busy');
        load();
      }
    });
  }

  function renderBoard() {
    const lanes = {OPEN: [], IN_PROGRESS: [], CLOSED: []};
    cases.forEach((incident, index) => lanes[incident.status]?.push(card(incident, index, true)));
    for (const [status, cards] of Object.entries(lanes)) {
      document.querySelector(`[data-count="${status}"]`).textContent = cards.length;
      document.querySelector(`[data-lane="${status}"]`).innerHTML = cards.join('') || '<p class="empty">ไม่มีเคสในสถานะนี้</p>';
    }
  }

  function renderDashboard() {
    byId('recent-cases').innerHTML = cases.slice(0, 6)
      .map((incident, index) => card(incident, index, true)).join('')
      || '<p class="empty">ยังไม่มีเคสที่แจ้ง</p>';
  }

  function renderStats(stats) {
    for (const key of ['total', 'open', 'in_progress', 'urgent']) {
      byId(key).textContent = stats[key];
    }
    if (view === 'dashboard') {
      for (const row of document.querySelectorAll('[data-summary]')) {
        const count = stats[row.dataset.summary];
        row.querySelector('strong').textContent = count;
        const progress = row.querySelector('progress');
        progress.max = Math.max(stats.total, 1);
        progress.value = count;
      }
    }
  }

  function initializeMap() {
    const message = byId('map-message');
    const reset = byId('map-reset');
    const leaflet = window.L;
    if (!leaflet) {
      message.textContent = 'โหลดแผนที่ไม่สำเร็จ ยังสามารถเปิดเคสจากรายการได้';
      message.hidden = false;
      reset.disabled = true;
      return null;
    }

    const map = leaflet.map('case-map', {scrollWheelZoom: false}).setView(bangkok, 11);
    const tiles = mapTiles(leaflet);
    tiles.on('tileerror', () => {
      message.textContent = 'โหลดภาพแผนที่บางส่วนไม่สำเร็จ';
      message.hidden = false;
    });
    tiles.on('loading', () => { message.hidden = true; });
    tiles.addTo(map);

    const layer = leaflet.layerGroup().addTo(map);
    const markerByCase = new Map();
    let markerSnapshot;
    function fit() {
      const points = layer.getLayers().map((marker) => marker.getLatLng());
      if (points.length) {
        map.fitBounds(points, {maxZoom: 15, padding: [38, 38]});
      } else {
        map.setView(bangkok, 11);
      }
    }
    reset.addEventListener('click', fit);

    return {
      render() {
        const plotted = cases.filter((incident) => incident.coordinates);
        // Preserve open popups and marker focus when a refresh leaves the map unchanged.
        const nextSnapshot = JSON.stringify(plotted.map((incident) => [
          incident.ticket_id, incident.coordinates, incident.title, incident.location,
          incident.service_area, incident.urgency, incident.status_label,
        ]));
        if (nextSnapshot === markerSnapshot) return;
        const firstRender = markerSnapshot === undefined || markerSnapshot === '[]';
        markerSnapshot = nextSnapshot;

        const groups = new Map();
        plotted.forEach((incident) => {
          const key = incident.coordinates.join(',');
          if (!groups.has(key)) groups.set(key, []);
          groups.get(key).push(incident);
        });

        layer.clearLayers();
        markerByCase.clear();
        for (const group of groups.values()) {
          group.sort((a, b) => priorities.indexOf(priority(a)) - priorities.indexOf(priority(b)));
          const incident = group[0];
          const label = group.length === 1
            ? `${title(incident)} · ${priorityLabels[priority(incident)]}`
            : `${group.length} เคส · ความเร่งด่วนสูงสุด ${priorityLabels[priority(incident)]}`;
          const marker = leaflet.marker(incident.coordinates, {
            icon: leaflet.divIcon({
              className: `case-marker ${priority(incident)}`,
              html: group.length > 1 ? String(group.length) : '',
              iconSize: [28, 28],
            }),
            zIndexOffset: (priorities.length - priorities.indexOf(priority(incident))) * 10,
          }).addTo(layer);
          marker.getElement().setAttribute('aria-label', label);
          marker.bindTooltip(
            `<strong>${escape(label)}</strong><span class="${priority(incident)}">${escape(location(incident))}</span>`,
            {direction: 'top', offset: [0, -13], className: 'map-tip'},
          );
          const popup = document.createElement('div');
          popup.className = 'map-popover';
          for (const entry of group) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'button';
            button.textContent = `${title(entry)} · ${priorityLabels[priority(entry)]} · ${entry.status_label}`;
            button.addEventListener('click', () => {
              const latest = cases.find((candidate) => candidate.ticket_id === entry.ticket_id);
              if (latest) showCase(latest);
            });
            popup.append(button);
            markerByCase.set(entry.ticket_id, marker);
          }
          marker.bindPopup(popup);
        }
        if (firstRender) fit();
      },
      locate(incident) {
        const marker = markerByCase.get(incident.ticket_id);
        if (!marker) return;
        map.setView(marker.getLatLng(), Math.max(15, map.getZoom()));
        marker.openPopup();
        marker.getElement().focus({preventScroll: true});
        if (window.matchMedia('(max-width: 650px)').matches) {
          byId('case-map').scrollIntoView({block: 'nearest'});
        }
      },
    };
  }

  function renderMap() {
    const count = cases.filter((incident) => incident.coordinates).length;
    byId('case-count').textContent = cases.length;
    byId('map-count').textContent = `${count} เคสมีพิกัด · ${cases.length - count} เคสยังไม่มีพิกัด`;
    byId('map-empty').hidden = count > 0;
    byId('map-empty-title').textContent = cases.length ? 'เคสในรายการยังไม่มีพิกัด' : 'ไม่พบเคสตามตัวกรอง';
    byId('map-empty-hint').textContent = cases.length
      ? editor ? 'เลือก «ปักหมุด» จากรายการเพื่อเพิ่มตำแหน่งจุดเกิดเหตุ' : 'เคสจะแสดงเป็นหมุดเมื่อเจ้าหน้าที่บันทึกพิกัด'
      : 'ลองตรวจสอบตัวกรองหรือคำค้นหา';
    byId('case-list').innerHTML = cases.map((incident, index) => `
      <div class="feed-entry">
        ${card(incident, index, false)}
        ${mapView && incident.coordinates ? `<button type="button" class="button locate" data-locate="${index}" aria-label="แสดงบนแผนที่ ${escape(incident.ticket_id)}">${icon('pin')}</button>` : ''}
        ${editor && incident.update_url && !incident.coordinates ? `<button type="button" class="button pin-case" data-pin-case="${index}" aria-label="ปักหมุด ${escape(incident.ticket_id)}">${icon('pin')}ปักหมุด</button>` : ''}
      </div>`).join('') || '<p class="empty">ไม่พบเคสตามตัวกรอง</p>';
    mapView?.render();
  }

  async function load() {
    clearTimeout(refreshTimer);
    clearTimeout(searchTimer);
    currentRequest?.abort();
    const request = new AbortController();
    currentRequest = request;
    refresh.disabled = true;
    const params = filters ? new URLSearchParams(new FormData(filters)) : '';
    const errorBox = byId('load-error');
    try {
      const endpoint = new URL(document.body.dataset.casesUrl, document.baseURI);
      endpoint.search = params;
      const response = await fetch(endpoint, {signal: request.signal});
      if (response.redirected) throw new Error('เซสชันหมดอายุ กรุณาโหลดหน้านี้ใหม่เพื่อเข้าสู่ระบบ');
      if (!response.ok) throw new Error();
      const data = await response.json();
      if (dragging) return;
      renderStats(data.stats);
      const nextSnapshot = JSON.stringify(data.cases);
      if (nextSnapshot !== snapshot) {
        cases = data.cases;
        if (view === 'dashboard') renderDashboard();
        else if (view === 'map') renderMap();
        else renderBoard();
        snapshot = nextSnapshot;
      }
      byId('updated').textContent = `อัปเดตล่าสุด ${time.format(new Date())}`;
      errorBox.hidden = true;
    } catch (error) {
      if (request.signal.aborted) return;
      errorBox.textContent = error.message.startsWith('เซสชัน')
        ? error.message : 'โหลดข้อมูลเคสไม่สำเร็จ กรุณากดรีเฟรชเพื่อลองใหม่';
      errorBox.hidden = false;
      byId('updated').textContent = 'อัปเดตไม่สำเร็จ';
      if (snapshot === undefined) {
        byId('map-count')?.replaceChildren('ยังไม่มีข้อมูลตำแหน่งเคส');
        document.querySelectorAll('.empty').forEach((element) => {
          element.textContent = 'ยังไม่มีข้อมูลเคส';
        });
      }
    } finally {
      if (currentRequest === request) {
        refresh.disabled = false;
        refreshTimer = setTimeout(load, 15000);
      }
    }
  }

  if (view === 'map') mapView = initializeMap();
  document.querySelector('main').addEventListener('click', (event) => {
    const detail = event.target.closest('[data-case]');
    const locate = event.target.closest('[data-locate]');
    const pin = event.target.closest('[data-pin-case]');
    if (detail) showCase(cases[Number(detail.dataset.case)]);
    if (locate) mapView?.locate(cases[Number(locate.dataset.locate)]);
    if (pin) showCase(cases[Number(pin.dataset.pinCase)], true);
  });
  filters?.addEventListener('submit', (event) => {
    event.preventDefault();
    load();
  });
  filters?.addEventListener('change', (event) => {
    if (event.target.matches('select')) load();
  });
  filters?.elements.q.addEventListener('input', () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(load, 300);
  });
  refresh.addEventListener('click', load);
  load();
})();
