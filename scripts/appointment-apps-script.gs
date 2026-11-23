/**
 * Receiver for the site's appointment form (/rantevou/).
 *
 * It lives INSIDE the Google Sheet of the requests (Extensions → Apps Script) and is
 * published as a Web app (Execute as: Me, Who has access: Anyone). The site sends
 * the form here and the script adds ONE row to the sheet. The Make scenario watches
 * the sheet and sends the request to the shop's Telegram; the owner then sends the
 * customer a text message to confirm the day and time.
 *
 * Columns (A–L are the same as the old estimate form, so older rows still make sense):
 *   A Submission ID, B Respondent ID, C Submitted at, D Αυτοκίνητο, E Τι έπαθε,
 *   F Ασφαλιστική (Ναι / Όχι, ιδιωτικά / Δεν ξέρω ακόμα), G Ποια ασφαλιστική,
 *   H (photos – no longer used, left empty), I Ονοματεπώνυμο,
 *   J Κινητό (digits with country code, no "+": Make adds it), K Συμφωνία, L Συμφωνία (TRUE),
 *   M Ραντεβού ("Τρίτη 25/11/2026, 10:30"), N Ραντεβού ISO ("2026-11-25 10:30", for sorting)
 *
 * Copy of the file in the site's folder: scripts/appointment-apps-script.gs
 */

const SHEET_NAME = 'Sheet1';          // the tab Make watches
const MIN_FILL_MS = 3000;             // faster than this = a bot
const MAX_DAYS_AHEAD = 60;
const INSURANCE = ['Ναι', 'Όχι, ιδιωτικά', 'Δεν ξέρω ακόμα'];
const CONSENT = 'Συμφωνώ να χρησιμοποιηθούν τα στοιχεία μου μόνο για το ραντεβού';
const DAY_NAMES = ['Κυριακή', 'Δευτέρα', 'Τρίτη', 'Τετάρτη', 'Πέμπτη', 'Παρασκευή', 'Σάββατο'];

/** Opening the Web app link in a browser just says it is alive (handy for testing). */
function doGet() {
  return json({ ok: true, service: 'appointment-form' });
}

function doPost(e) {
  try {
    const data = JSON.parse((e && e.postData && e.postData.contents) || '{}');

    // Spam: a hidden field people never see, and forms filled in a few milliseconds.
    // Answer "ok" so bots do not retry, but store nothing.
    if (data.website || Number(data.elapsed || 0) < MIN_FILL_MS) return json({ ok: true });

    const car = clean(data.car, 200);
    const damage = clean(data.damage, 3000);
    const insurance = INSURANCE.indexOf(data.insurance) >= 0 ? data.insurance : '';
    const insurer = insurance === 'Ναι' ? clean(data.insurer, 200) : '';
    const name = clean(data.name, 200);
    const phone = phoneDigits(data.phone);
    const when = appointment(data.date, data.time);

    if (!car || !damage || !insurance || !name || !phone || !when || data.consent !== true) {
      return json({ ok: false, error: 'missing' });
    }

    const id = Utilities.getUuid().replace(/-/g, '').slice(0, 8);
    const tz = Session.getScriptTimeZone() || 'Europe/Athens';
    const submittedAt = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm:ss');

    const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME) || SpreadsheetApp.getActive().getSheets()[0];
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      // first time: name the two new columns
      if (!sheet.getRange(1, 13).getValue()) sheet.getRange(1, 13, 1, 2).setValues([['Ραντεβού', 'Ραντεβού (ISO)']]);
      // the apostrophes keep the phone and the ISO date as plain text
      sheet.appendRow([id, id, submittedAt, car, damage, insurance, insurer, '', name, "'" + phone,
        CONSENT, 'TRUE', when.label, "'" + when.iso]);
    } finally {
      lock.releaseLock();
    }
    return json({ ok: true });
  } catch (err) {
    console.error(err);
    return json({ ok: false, error: 'server' });
  }
}

/** "2026-11-25" + "10:30" → label and ISO text, or null if it is not a sensible weekday slot. */
function appointment(date, time) {
  const d = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(date || ''));
  const t = /^(\d{2}):(00|30)$/.exec(String(time || ''));
  if (!d || !t) return null;
  const day = new Date(Number(d[1]), Number(d[2]) - 1, Number(d[3]));
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const daysAhead = Math.round((day - today) / 86400000);
  const hour = Number(t[1]);
  if (day.getDay() === 0 || day.getDay() === 6) return null;      // weekends: closed
  if (daysAhead < 1 || daysAhead > MAX_DAYS_AHEAD) return null;    // from tomorrow, two months ahead
  if (hour < 9 || hour > 17) return null;                          // 09:00 – 17:30
  return {
    label: DAY_NAMES[day.getDay()] + ' ' + d[3] + '/' + d[2] + '/' + d[1] + ', ' + time,
    iso: date + ' ' + time,
  };
}

/** Text without control characters, at most `max` characters. */
function clean(value, max) {
  return String(value || '').replace(/[\u0000-\u0009\u000B-\u001F\u007F]/g, '').trim().slice(0, max);
}

/** "694 412 3456", "+30 6944123456", "0030..." → "306944123456". Other countries kept as typed. */
function phoneDigits(value) {
  let digits = String(value || '').replace(/\D/g, '');
  if (digits.indexOf('00') === 0) digits = digits.slice(2);
  if (digits.length === 10) digits = '30' + digits;
  return digits.length >= 10 && digits.length <= 15 ? digits : '';
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
