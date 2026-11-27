const pinPicker = document.querySelector('#pin-picker');
const pinOpen = document.querySelector('#pin-open');
const pinForm = document.querySelector('#pin-form');
const pinFeedback = document.querySelector('#pin-feedback');
const reportMapContainer = document.querySelector('#report-map');
let reportMap, reportMarker, pinTicket, selectionVersion = 0;

function pinUrl() {
  return `${pinCard.dataset.url}?ticket_id=${encodeURIComponent(pinTicket)}`;
}

function showReportMarker(point) {
  if (!reportMap) return;
  if (reportMarker) {
    reportMarker.setLatLng(point);
  } else {
    reportMarker = L.marker(point, {draggable: true}).addTo(reportMap);
    reportMarker.on('dragend', () => {
      const point = reportMarker.getLatLng();
      pickReportPoint([point.lat, point.lng]);
    });
  }
}

function pickReportPoint(point) {
  selectionVersion++;
  const lng = ((point[1] + 180) % 360 + 360) % 360 - 180;
  const longitude = point[1] >= -180 && point[1] <= 180 ? point[1] : lng;
  pinForm.elements.latitude.value = point[0].toFixed(6);
  pinForm.elements.longitude.value = longitude.toFixed(6);
  showReportMarker([point[0], longitude]);
  pinFeedback.textContent = '';
  pinForm.querySelector('[type=submit]').disabled = false;
}

pinOpen.onclick = async () => {
  if (!pinCase || !pinPicker.hidden) return;
  const currentCase = pinCase;
  pinTicket = currentCase.ticket_id;
  pinForm.reset();
  const initial = currentCase.pin || currentCase.pin_hint;
  pinForm.querySelector('[type=submit]').disabled = true;
  pinForm.querySelector('details').open = false;
  pinPicker.hidden = false;
  pinOpen.hidden = true;
  pinOpen.setAttribute('aria-expanded', 'true');
  reportMapContainer.hidden = !window.L || !pinCard.dataset.tiles;
  if (!reportMapContainer.hidden) {
    reportMap = L.map(reportMapContainer, {scrollWheelZoom: false})
      .setView(initial || [13.7563, 100.5018], initial ? 16 : 11);
    const tiles = L.tileLayer(pinCard.dataset.tiles, {
      attribution: pinCard.dataset.attribution, maxZoom: 19,
      referrerPolicy: 'strict-origin-when-cross-origin',
    }).addTo(reportMap);
    let loaded = false;
    tiles.on('tileload', () => { loaded = true; });
    tiles.on('load', () => {
      if (loaded || !reportMap) return;
      reportMap.remove();
      reportMap = reportMarker = null;
      reportMapContainer.hidden = true;
      pinFeedback.textContent = 'แผนที่โหลดไม่ได้ ใช้ GPS หรือกรอกพิกัดได้';
    });
    reportMap.on('click', ({latlng}) => pickReportPoint([latlng.lat, latlng.lng]));
  }
  if (initial) {
    pickReportPoint(initial);
    pinFeedback.textContent = 'ตรวจจุดเกิดเหตุ แล้วกดบันทึกหมุด';
    return;
  }
  const version = ++selectionVersion;
  pinFeedback.textContent = currentCase.location ? 'กำลังหาตำแหน่งจากสถานที่ที่แจ้ง…' : '';
  try {
    const response = await chatFetch(pinUrl());
    const data = await response.json();
    if (!response.ok) throw new Error(data.error);
    if (pinPicker.hidden || version !== selectionVersion) return;
    if (data.hint) {
      pickReportPoint(data.hint);
      reportMap?.setView(data.hint, 16);
      pinFeedback.textContent = 'ตรวจตำแหน่งที่แนะนำ แล้วเลื่อนหมุดให้ตรงจุดเกิดเหตุ';
    } else {
      pinFeedback.textContent = 'เลือกจุดเกิดเหตุเองบนแผนที่ หรือกรอกพิกัด';
    }
  } catch {
    if (!pinPicker.hidden && version === selectionVersion) {
      pinFeedback.textContent = 'ค้นตำแหน่งไม่สำเร็จ กรุณาเลือกจุดเกิดเหตุเองหรือกรอกพิกัด';
    }
  }
};

pinForm.addEventListener('input', () => {
  selectionVersion++;
  const {latitude, longitude} = pinForm.elements;
  const valid = latitude.validity.valid && longitude.validity.valid;
  pinForm.querySelector('[type=submit]').disabled = !valid;
  if (valid) {
    showReportMarker([latitude.valueAsNumber, longitude.valueAsNumber]);
    reportMap?.panTo([latitude.valueAsNumber, longitude.valueAsNumber]);
  }
});
document.querySelector('#pin-gps').onclick = () => {
  if (!navigator.geolocation) {
    pinFeedback.textContent = 'เบราว์เซอร์นี้ใช้ GPS ไม่ได้';
    return;
  }
  const version = ++selectionVersion;
  navigator.geolocation.getCurrentPosition(({coords}) => {
    if (pinPicker.hidden || version !== selectionVersion) return;
    const point = [coords.latitude, coords.longitude];
    pickReportPoint(point);
    reportMap?.setView(point, 16);
  }, () => {
    if (!pinPicker.hidden && version === selectionVersion) {
      pinFeedback.textContent = 'อ่านตำแหน่งไม่ได้ กรุณาเลือกจุดเอง';
    }
  }, {timeout: 8000});
};
function closePinPicker() {
  selectionVersion++;
  reportMap?.remove();
  reportMap = reportMarker = null;
  pinPicker.hidden = true;
  pinOpen.hidden = false;
  pinOpen.setAttribute('aria-expanded', 'false');
}
document.querySelector('#pin-cancel').onclick = closePinPicker;
pinForm.addEventListener('submit', async event => {
  event.preventDefault();
  const button = event.submitter;
  if (button.disabled || !pinForm.checkValidity()) return;
  button.disabled = true;
  selectionVersion++;
  try {
    const response = await chatFetch(pinUrl(), {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf()},
      body: JSON.stringify(Object.fromEntries(new FormData(pinForm))),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'บันทึกหมุดไม่สำเร็จ');
    if (pinCase?.ticket_id === data.case.ticket_id) renderCase(data.case);
    closePinPicker();
    pinOpen.focus();
  } catch (error) {
    pinFeedback.textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
