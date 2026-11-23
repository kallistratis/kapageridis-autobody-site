/*
 * Appointment form (/rantevou/), loaded with `defer`.
 *
 * - Draws a month calendar: the working days of the next 30 days are open (no weekends,
 *   no Greek public holidays — the Easter ones are calculated), with arrows between months.
 * - Shows the half-hour slots inside the opening hours (data-opens / data-closes, from
 *   data/business.json) and a line with the chosen day and time.
 * - Checks the answers and shows a clear Greek message next to the first problem.
 * - Sends everything as JSON to the Google Apps Script of the requests sheet
 *   (data-endpoint, from data/business.json → appointmentForm.endpoint). The script adds
 *   one row; the Make scenario sends it to the shop's Telegram; the shop sends the
 *   customer a confirmation text message. The body is plain text on purpose: no CORS "preflight".
 */
(() => {
  const form = document.querySelector('[data-appointment-form]');
  if (!form) return;

  const DAYS_AHEAD = 30; // calendar days offered, starting tomorrow
  const openedAt = Date.now();
  const endpoint = form.dataset.endpoint;
  const phoneLabel = form.dataset.phone || '';
  const [openH, openM] = (form.dataset.opens || '09:00').split(':').map(Number);
  const [closeH, closeM] = (form.dataset.closes || '18:00').split(':').map(Number);
  const calTitle = form.querySelector('[data-cal-title]');
  const calGrid = form.querySelector('[data-cal-grid]');
  const prevBtn = form.querySelector('[data-cal-prev]');
  const nextBtn = form.querySelector('[data-cal-next]');
  const dateInput = form.elements.date; // hidden: keeps the day while another month is shown
  const timesBox = form.querySelector('[data-times]');
  const picked = form.querySelector('[data-picked]');
  const insurerField = form.querySelector('[data-insurer]');
  const errorBox = form.querySelector('[data-error]');
  const submitBtn = form.querySelector('.ef-submit');
  const done = document.querySelector('[data-done]');
  const submitText = submitBtn.textContent;

  const MONTHS = ['Ιανουάριος', 'Φεβρουάριος', 'Μάρτιος', 'Απρίλιος', 'Μάιος', 'Ιούνιος',
    'Ιούλιος', 'Αύγουστος', 'Σεπτέμβριος', 'Οκτώβριος', 'Νοέμβριος', 'Δεκέμβριος'];
  const MONTHS_OF = ['Ιανουαρίου', 'Φεβρουαρίου', 'Μαρτίου', 'Απριλίου', 'Μαΐου', 'Ιουνίου',
    'Ιουλίου', 'Αυγούστου', 'Σεπτεμβρίου', 'Οκτωβρίου', 'Νοεμβρίου', 'Δεκεμβρίου'];
  const WEEKDAYS = ['Κυριακή', 'Δευτέρα', 'Τρίτη', 'Τετάρτη', 'Πέμπτη', 'Παρασκευή', 'Σάββατο'];

  /* ---------- open days: working days of the next DAYS_AHEAD days ---------- */
  const pad = (n) => String(n).padStart(2, '0');
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const fromIso = (value) => { const [y, m, d] = value.split('-').map(Number); return new Date(y, m - 1, d); };
  const dayName = (d) => `${WEEKDAYS[d.getDay()]} ${d.getDate()} ${MONTHS_OF[d.getMonth()]}`;

  // Orthodox Easter (Meeus' Julian algorithm + 13 days, valid 1900–2099)
  function orthodoxEaster(year) {
    const a = year % 4, b = year % 7, c = year % 19;
    const d = (19 * c + 15) % 30;
    const e = (2 * a + 4 * b - d + 34) % 7;
    const month = Math.floor((d + e + 114) / 31);
    const day = ((d + e + 114) % 31) + 1;
    return new Date(year, month - 1, day + 13);
  }
  const holidayCache = {};
  function holidays(year) {
    if (holidayCache[year]) return holidayCache[year];
    const fixed = ['01-01', '01-06', '03-25', '05-01', '08-15', '10-28', '12-25', '12-26']
      .map((md) => `${year}-${md}`);
    const easter = orthodoxEaster(year);
    const shifted = [-48, -2, 1, 50].map((days) => {   // Καθαρά Δευτέρα, Μ. Παρασκευή, Δευτέρα Πάσχα, Αγ. Πνεύματος
      const d = new Date(easter); d.setDate(d.getDate() + days); return iso(d);
    });
    return (holidayCache[year] = new Set([...fixed, ...shifted]));
  }

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const openDays = new Set();
  for (let i = 1; i <= DAYS_AHEAD; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() + i);
    const weekday = d.getDay();
    if (weekday !== 0 && weekday !== 6 && !holidays(d.getFullYear()).has(iso(d))) openDays.add(iso(d));
  }
  const openList = [...openDays];
  const monthKey = (d) => d.getFullYear() * 12 + d.getMonth();
  const firstMonth = monthKey(fromIso(openList[0]));
  const lastMonth = monthKey(fromIso(openList[openList.length - 1]));
  let shownMonth = firstMonth;

  /* ---------- month calendar ---------- */
  function cell(className, text) {
    const span = document.createElement('span');
    span.className = className;
    span.textContent = text;
    return span;
  }

  function renderMonth() {
    const year = Math.floor(shownMonth / 12);
    const month = shownMonth % 12;
    const strong = document.createElement('strong');
    strong.textContent = MONTHS[month];
    calTitle.replaceChildren(strong, ` ${year}`);
    prevBtn.disabled = shownMonth <= firstMonth;
    nextBtn.disabled = shownMonth >= lastMonth;

    const cells = [];
    const blanks = (new Date(year, month, 1).getDay() + 6) % 7; // the week starts on Monday
    for (let i = 0; i < blanks; i++) cells.push(cell('ef-cal-day is-empty', ''));
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    for (let day = 1; day <= daysInMonth; day++) {
      const d = new Date(year, month, day);
      const value = iso(d);
      const todayClass = d.getTime() === today.getTime() ? ' is-today' : '';
      if (!openDays.has(value)) {
        const off = cell(`ef-cal-day is-off${todayClass}`, String(day));
        off.setAttribute('aria-hidden', 'true');
        cells.push(off);
        continue;
      }
      const label = document.createElement('label');
      label.className = `ef-cal-day is-open${todayClass}`;
      const input = document.createElement('input');
      input.type = 'radio';
      input.name = 'day';
      input.value = value;
      input.checked = value === dateInput.value;
      input.setAttribute('aria-label', dayName(d));
      label.append(input, cell('ef-cal-num', String(day)));
      cells.push(label);
    }
    calGrid.replaceChildren(...cells);
  }

  function moveMonth(step, btn) {
    shownMonth = Math.min(lastMonth, Math.max(firstMonth, shownMonth + step));
    renderMonth();
    if (btn.disabled) (btn === prevBtn ? nextBtn : prevBtn).focus(); // keep the focus on a usable arrow
  }
  prevBtn.addEventListener('click', () => moveMonth(-1, prevBtn));
  nextBtn.addEventListener('click', () => moveMonth(1, nextBtn));
  renderMonth();

  /* ---------- times: every half hour inside the opening hours ---------- */
  const slots = [];
  for (let minutes = openH * 60 + openM; minutes <= closeH * 60 + closeM - 30; minutes += 30) {
    slots.push(`${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`);
  }
  timesBox.replaceChildren(...slots.map((slot) => {
    const label = document.createElement('label');
    label.className = 'ef-choice ef-time';
    label.innerHTML = `<input type="radio" name="time" value="${slot}"><span>${slot}</span>`;
    return label;
  }));

  const checked = (name) => form.querySelector(`input[name="${name}"]:checked`);

  // "Επιλογή: Τρίτη 24 Νοεμβρίου, 10:30" under the calendar
  function showPicked() {
    const time = checked('time');
    if (!dateInput.value && !time) { picked.hidden = true; return; }
    const parts = [];
    if (dateInput.value) parts.push(dayName(fromIso(dateInput.value)));
    if (time) parts.push(time.value);
    picked.replaceChildren('Επιλογή: ', Object.assign(document.createElement('strong'), { textContent: parts.join(', ') }));
    picked.hidden = false;
  }

  /* ---------- answers: day, time, "Ποια ασφαλιστική;" only when "Ναι" ---------- */
  form.addEventListener('change', (e) => {
    const group = e.target.closest('[data-group]');
    if (group) clearInvalid(group);
    if (e.target.name === 'day') dateInput.value = e.target.value;
    if (e.target.name === 'day' || e.target.name === 'time') showPicked();
    if (e.target.name === 'insurance') insurerField.hidden = e.target.value !== 'Ναι';
  });
  form.addEventListener('input', (e) => {
    if (e.target.classList.contains('ef-input')) clearInvalid(e.target);
  });

  /* ---------- checks ---------- */
  // Phone → digits with country code, no "+" (Make adds it): "6944 123 456" → "306944123456".
  // The confirmation is a text message, so Greek numbers must be mobiles (10 digits, 69…),
  // with or without 30/+30/0030. Other countries only when written with "+" or "00".
  function phoneDigits(value) {
    const raw = String(value || '').trim();
    let digits = raw.replace(/\D/g, '');
    const international = raw.startsWith('+') || digits.startsWith('00');
    if (digits.startsWith('00')) digits = digits.slice(2);
    const greekMobile = (d) => /^69\d{8}$/.test(d);
    if (digits.length === 10) return greekMobile(digits) ? `30${digits}` : '';
    if (digits.startsWith('30')) return greekMobile(digits.slice(2)) ? digits : '';
    return international && digits.length >= 10 && digits.length <= 15 ? digits : '';
  }

  function clearInvalid(el) {
    if (!el) return;
    el.removeAttribute('aria-invalid');
    el.classList.remove('is-invalid');
    if (!form.querySelector('.is-invalid')) errorBox.hidden = true;
  }

  function check() {
    form.querySelectorAll('.is-invalid').forEach(clearInvalid);
    const value = (name) => (form.elements[name] ? form.elements[name].value.trim() : '');
    const group = (name) => form.querySelector(`[data-group="${name}"]`);
    const problems = [];
    if (!value('car')) problems.push([form.elements.car, 'Γράψτε το αυτοκίνητο (μάρκα, μοντέλο, χρονιά).']);
    if (!value('damage')) problems.push([form.elements.damage, 'Γράψτε με λίγα λόγια τι έπαθε το αυτοκίνητο.']);
    if (!checked('insurance')) problems.push([group('insurance'), 'Διαλέξτε αν θα πάει μέσω ασφαλιστικής.']);
    if (!openDays.has(dateInput.value)) problems.push([group('date'), 'Διαλέξτε μέρα για το ραντεβού στο ημερολόγιο.']);
    if (!checked('time')) problems.push([group('time'), 'Διαλέξτε ώρα για το ραντεβού.']);
    if (!value('name')) problems.push([form.elements.name, 'Γράψτε το ονοματεπώνυμό σας.']);
    if (!phoneDigits(value('phone'))) problems.push([form.elements.phone, 'Γράψτε ένα σωστό κινητό, π.χ. 6944 123 456.']);
    if (!form.elements.consent.checked) problems.push([group('consent'), 'Χρειάζεται η συμφωνία σας για να στείλουμε το αίτημα.']);
    problems.forEach(([el]) => {
      el.classList.add('is-invalid');
      if (el.matches('input, textarea')) el.setAttribute('aria-invalid', 'true');
    });
    if (problems.length) {
      const [first, message] = problems[0];
      errorBox.textContent = message;
      errorBox.hidden = false;
      const focusable = first.matches('input, textarea') ? first : first.querySelector('input:not([type="hidden"])');
      if (focusable) focusable.focus();
      first.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    return !problems.length;
  }

  /* ---------- send ---------- */
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (submitBtn.disabled || !check()) return;
    const insurance = checked('insurance').value;
    const payload = {
      car: form.elements.car.value.trim(),
      damage: form.elements.damage.value.trim(),
      insurance,
      insurer: insurance === 'Ναι' ? form.elements.insurer.value.trim() : '',
      date: dateInput.value,
      time: checked('time').value,
      name: form.elements.name.value.trim(),
      phone: phoneDigits(form.elements.phone.value),
      consent: true,
      website: form.elements.website.value, // empty for people (hidden field)
      elapsed: Date.now() - openedAt,
    };
    submitBtn.disabled = true;
    submitBtn.textContent = 'Αποστολή…';
    errorBox.hidden = true;
    try {
      const response = await fetch(endpoint, { method: 'POST', body: JSON.stringify(payload) });
      const result = await response.json();
      if (!result.ok) throw new Error(result.error || 'not ok');
      form.hidden = true;
      done.hidden = false;
      done.focus();
      done.scrollIntoView({ block: 'center' });
    } catch (err) {
      errorBox.textContent = `Το αίτημα δεν στάλθηκε. Ελέγξτε τη σύνδεσή σας και δοκιμάστε ξανά${phoneLabel ? `, ή καλέστε μας στο ${phoneLabel}` : ''}.`;
      errorBox.hidden = false;
      submitBtn.disabled = false;
      submitBtn.textContent = submitText;
    }
  });
})();
