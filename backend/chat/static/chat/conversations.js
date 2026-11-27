(() => {
  const thread = document.querySelector('.thread[data-url]');
  if (!thread) return;

  const panel = document.querySelector('#thread-messages');
  const log = document.querySelector('#thread-log');
  const older = document.querySelector('#thread-older');
  const mode = document.querySelector('#thread-mode');
  const feedback = document.querySelector('#thread-feedback');
  const form = document.querySelector('#thread-reply');
  const modeButton = document.querySelector('#thread-mode-change');
  const messages = new Map();
  const date = new Intl.DateTimeFormat('th-TH', {
    dateStyle: 'short', timeStyle: 'short', timeZone: 'Asia/Bangkok',
  });
  let reading = false;
  let sending = false;

  function render(rows, prepend) {
    const nearBottom = panel.scrollHeight - panel.clientHeight - panel.scrollTop < 55;
    const previousHeight = panel.scrollHeight;
    const fragment = document.createDocumentFragment();
    for (const row of rows) {
      if (messages.has(row.id)) continue;
      const item = document.createElement('li');
      item.className = `thread-message ${row.role}`;
      const author = document.createElement('header');
      const name = {
        user: thread.dataset.reporter || 'ผู้แจ้ง',
        assistant: 'BEM Care',
        staff: row.author_name || 'เจ้าหน้าที่',
      }[row.role];
      author.textContent = `${name} · ${date.format(new Date(row.created_at))}`;
      const content = document.createElement('p');
      content.textContent = row.content;
      item.append(author, content);
      fragment.append(item);
      messages.set(row.id, item);
    }
    if (prepend) {
      log.prepend(fragment);
      panel.scrollTop += panel.scrollHeight - previousHeight;
    } else {
      log.append(fragment);
      if (nearBottom) panel.scrollTop = panel.scrollHeight;
    }
  }

  async function load(before = 0) {
    if (reading) return;
    reading = true;
    try {
      const params = new URLSearchParams();
      if (before) params.set('before', before);
      else if (messages.size) params.set('after', Math.max(...messages.keys()));
      const response = await fetch(`${thread.dataset.url}?${params}`);
      if (!response.ok || response.redirected) throw new Error('โหลดข้อความไม่สำเร็จ');
      const data = await response.json();
      render(data.messages, Boolean(before));
      if (!params.has('after')) older.hidden = !data.has_older;
      mode.textContent = data.closed ? 'ปิดเคสแล้ว' : data.human_mode ? 'เจ้าหน้าที่ดูแล' : 'Agent ดูแล';
      if (form) {
        form.hidden = data.closed;
        modeButton.value = data.human_mode ? 'resume' : 'take_over';
        modeButton.textContent = data.human_mode ? 'ส่งกลับให้ Agent' : 'รับช่วงสนทนา';
      }
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      reading = false;
    }
  }

  async function send(action) {
    if (sending) return;
    sending = true;
    form.querySelectorAll('button').forEach(button => { button.disabled = true; });
    const values = new FormData(form);
    values.set('action', action);
    feedback.textContent = '';
    try {
      const response = await fetch(thread.dataset.url, {method: 'POST', body: values});
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'บันทึกไม่สำเร็จ');
      if (action === 'reply') form.elements.message.value = '';
      await load();
    } catch (error) {
      feedback.textContent = error.message;
    } finally {
      sending = false;
      form.querySelectorAll('button').forEach(button => { button.disabled = false; });
    }
  }

  older.addEventListener('click', () => load(Math.min(...messages.keys())));
  if (form) {
    form.addEventListener('submit', event => {
      event.preventDefault();
      send('reply');
    });
    modeButton.addEventListener('click', () => send(modeButton.value));
  }
  load();
  setInterval(() => load(), 4000);
})();
