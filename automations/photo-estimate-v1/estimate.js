/*
 * Free estimate form (/dorean-ektimisi/), loaded with `defer`.
 *
 * - Photos are made smaller in the visitor's browser (longest side 1600px, JPEG),
 *   which also drops their hidden data (EXIF, e.g. GPS location).
 * - Checks the answers and shows a clear Greek message next to the first problem.
 * - Sends everything as JSON to the Google Apps Script in the estimates Google Sheet
 *   (data-endpoint, from data/business.json → estimateForm.endpoint). The script saves
 *   the photos in Google Drive and adds the same Sheet row the old Tally form added,
 *   so the Make scenario (→ Gemini → Telegram) works unchanged.
 * - The body is sent as plain text on purpose: no CORS "preflight", which Google's
 *   script hosting would not answer.
 */
(() => {
  const form = document.querySelector('[data-estimate-form]');
  if (!form) return;

  const MAX_PHOTOS = 6;
  const LONG_SIDE = 1600;
  const QUALITY = 0.8;
  const openedAt = Date.now();

  const endpoint = form.dataset.endpoint;
  const phoneLabel = form.dataset.phone || '';
  const fileInput = form.querySelector('#ef-photos');
  const dropText = form.querySelector('[data-drop-text]');
  const thumbs = form.querySelector('[data-thumbs]');
  const insurerField = form.querySelector('[data-insurer]');
  const errorBox = form.querySelector('[data-error]');
  const submitBtn = form.querySelector('.ef-submit');
  const done = document.querySelector('[data-done]');
  const photos = []; // { data: "data:image/jpeg;base64,..." }
  let busy = 0;      // photos still being prepared

  /* ---------- "Ποια ασφαλιστική;" only when the answer is "Ναι" ---------- */
  form.addEventListener('change', (e) => {
    if (e.target.name === 'insurance') {
      insurerField.hidden = e.target.value !== 'Ναι';
      clearInvalid(form.querySelector('[data-group="insurance"]'));
    }
    if (e.target.name === 'consent') clearInvalid(form.querySelector('[data-group="consent"]'));
  });
  form.addEventListener('input', (e) => {
    if (e.target.classList.contains('ef-input')) clearInvalid(e.target);
  });

  /* ---------- photos ---------- */
  const loadImage = (file) => new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error('decode')); };
    img.src = url;
  });

  async function shrink(file) {
    let source;
    try {
      source = await createImageBitmap(file, { imageOrientation: 'from-image' });
    } catch (e) {
      source = await loadImage(file); // older browsers; <img> follows the photo's rotation too
    }
    const scale = Math.min(1, LONG_SIDE / Math.max(source.width, source.height));
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(source.width * scale);
    canvas.height = Math.round(source.height * scale);
    canvas.getContext('2d').drawImage(source, 0, 0, canvas.width, canvas.height);
    if (source.close) source.close();
    return canvas.toDataURL('image/jpeg', QUALITY);
  }

  function renderThumbs() {
    thumbs.replaceChildren(...photos.map((photo, i) => {
      const li = document.createElement('li');
      const img = document.createElement('img');
      img.src = photo.data;
      img.alt = `Φωτογραφία ${i + 1}`;
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'ef-thumb-remove';
      remove.setAttribute('aria-label', `Αφαίρεση φωτογραφίας ${i + 1}`);
      remove.textContent = '×';
      remove.addEventListener('click', () => { photos.splice(i, 1); renderThumbs(); fileInput.focus(); });
      li.append(img, remove);
      return li;
    }));
    const left = MAX_PHOTOS - photos.length;
    dropText.textContent = busy
      ? 'Ετοιμάζουμε τις φωτογραφίες…'
      : photos.length === 0 ? 'Πατήστε για να προσθέσετε φωτογραφίες'
        : left > 0 ? `Προσθήκη κι άλλης (έως ${left} ακόμα)` : 'Φτάσατε τις 6 φωτογραφίες';
    fileInput.disabled = left <= 0;
  }

  fileInput.addEventListener('change', async () => {
    const files = Array.from(fileInput.files || []).slice(0, MAX_PHOTOS - photos.length);
    fileInput.value = ''; // so the same photo can be picked again after removing it
    if (!files.length) return;
    clearInvalid(form.querySelector('[data-group="photos"]'));
    busy += files.length;
    renderThumbs();
    let failed = 0;
    for (const file of files) {
      try {
        photos.push({ data: await shrink(file) });
      } catch (e) {
        failed += 1;
      }
      busy -= 1;
      renderThumbs();
    }
    if (failed) showError(form.querySelector('[data-group="photos"]'),
      failed === 1 ? 'Μία φωτογραφία δεν άνοιξε. Δοκιμάστε άλλη.' : `${failed} φωτογραφίες δεν άνοιξαν. Δοκιμάστε άλλες.`);
  });

  /* ---------- checks ---------- */
  // Phone → digits with country code, no "+" (Make adds it): "6944 123 456" → "306944123456".
  // Greek numbers have 10 digits starting with 69 (mobile) or 2 (landline), with or without
  // 30 / +30 / 0030 in front. Other countries only when written with "+" or "00".
  // Anything else (e.g. "3069947027": a 30 in front but digits missing) is refused.
  function phoneDigits(value) {
    const raw = String(value || '').trim();
    let digits = raw.replace(/\D/g, '');
    const international = raw.startsWith('+') || digits.startsWith('00');
    if (digits.startsWith('00')) digits = digits.slice(2);
    const greekLocal = (d) => /^(69\d{8}|2\d{9})$/.test(d);
    if (digits.length === 10) return greekLocal(digits) ? `30${digits}` : '';
    if (digits.startsWith('30')) return greekLocal(digits.slice(2)) ? digits : '';
    return international && digits.length >= 10 && digits.length <= 15 ? digits : '';
  }

  function clearInvalid(el) {
    if (!el) return;
    el.removeAttribute('aria-invalid');
    el.classList.remove('is-invalid');
    if (!form.querySelector('.is-invalid')) errorBox.hidden = true;
  }

  function showError(el, message) {
    el.classList.add('is-invalid');
    if (el.matches('input, textarea')) el.setAttribute('aria-invalid', 'true');
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function check() {
    form.querySelectorAll('.is-invalid').forEach(clearInvalid);
    const value = (name) => (form.elements[name] ? form.elements[name].value.trim() : '');
    const problems = [];
    if (!value('car')) problems.push([form.elements.car, 'Γράψτε το αυτοκίνητο (μάρκα, μοντέλο, χρονιά).']);
    if (!value('damage')) problems.push([form.elements.damage, 'Γράψτε με λίγα λόγια τι έπαθε το αυτοκίνητο.']);
    if (!form.querySelector('input[name="insurance"]:checked')) {
      problems.push([form.querySelector('[data-group="insurance"]'), 'Διαλέξτε αν θα πάει μέσω ασφαλιστικής.']);
    }
    if (busy) problems.push([form.querySelector('[data-group="photos"]'), 'Περιμένετε λίγο, ετοιμάζουμε τις φωτογραφίες.']);
    else if (!photos.length) problems.push([form.querySelector('[data-group="photos"]'), 'Προσθέστε τουλάχιστον μία φωτογραφία της ζημιάς.']);
    if (!value('name')) problems.push([form.elements.name, 'Γράψτε το ονοματεπώνυμό σας.']);
    if (!phoneDigits(value('phone'))) problems.push([form.elements.phone, 'Γράψτε ένα σωστό κινητό, π.χ. 6944 123 456.']);
    if (!form.elements.consent.checked) {
      problems.push([form.querySelector('[data-group="consent"]'), 'Χρειάζεται η συμφωνία σας για να στείλουμε το αίτημα.']);
    }
    problems.forEach(([el]) => {
      el.classList.add('is-invalid');
      if (el.matches('input, textarea')) el.setAttribute('aria-invalid', 'true');
    });
    if (problems.length) {
      const [first, message] = problems[0];
      showError(first, message);
      const focusable = first.matches('input, textarea') ? first : first.querySelector('input');
      if (focusable) focusable.focus();
      first.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    return !problems.length;
  }

  /* ---------- send ---------- */
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (submitBtn.disabled || !check()) return;
    const insurance = form.querySelector('input[name="insurance"]:checked').value;
    const payload = {
      car: form.elements.car.value.trim(),
      damage: form.elements.damage.value.trim(),
      insurance,
      insurer: insurance === 'Ναι' ? form.elements.insurer.value.trim() : '',
      name: form.elements.name.value.trim(),
      phone: phoneDigits(form.elements.phone.value),
      consent: true,
      photos: photos.map((p) => p.data),
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
      errorBox.textContent = `Η αποστολή δεν έγινε. Ελέγξτε τη σύνδεσή σας και δοκιμάστε ξανά${phoneLabel ? `, ή καλέστε μας στο ${phoneLabel}` : ''}.`;
      errorBox.hidden = false;
      submitBtn.disabled = false;
      submitBtn.textContent = 'Αποστολή';
    }
  });

  renderThumbs();
})();
