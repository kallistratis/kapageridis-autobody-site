/**
 * Receiver for the site's free estimate form (/dorean-ektimisi/).
 *
 * It lives INSIDE the Google Sheet «Δωρεάν εκτίμηση ζημιάς με φωτογραφία»
 * (Extensions → Apps Script) and is published as a Web app
 * (Execute as: Me, Who has access: Anyone). The site sends the form here.
 *
 * For every request it:
 *   1. saves the photos (already made smaller by the visitor's browser) as JPEG files
 *      in a Google Drive folder, viewable by link, like the form tool did before;
 *   2. adds ONE row to the sheet in exactly the same columns A–L as before,
 *      so the Make scenario keeps working without any change.
 *
 * Columns: A Submission ID, B Respondent ID, C Submitted at, D Αυτοκίνητο,
 * E Τι έπαθε, F Ασφαλιστική (Ναι / Όχι, ιδιωτικά / Δεν ξέρω ακόμα), G Ποια ασφαλιστική,
 * H Φωτογραφίες (one link per line), I Ονοματεπώνυμο, J Κινητό (digits with country
 * code, no "+": Make adds it), K Συμφωνία, L Συμφωνία (TRUE).
 *
 * Copy of the file in the site's folder: scripts/estimate-apps-script.gs
 */

const SHEET_NAME = 'Sheet1';                       // the tab Make watches
const FOLDER_NAME = 'Δωρεάν εκτίμηση – φωτογραφίες'; // Drive folder for the photos
const MAX_PHOTOS = 6;
const MAX_PHOTO_BYTES = 3 * 1024 * 1024;           // per photo, after the browser shrank it
const MIN_FILL_MS = 3000;                          // faster than this = a bot
const INSURANCE = ['Ναι', 'Όχι, ιδιωτικά', 'Δεν ξέρω ακόμα'];
const CONSENT = 'Συμφωνώ να χρησιμοποιηθούν τα στοιχεία μου μόνο για την εκτίμηση';

/** Opening the Web app link in a browser just says it is alive (handy for testing). */
function doGet() {
  return json({ ok: true, service: 'estimate-form' });
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
    const photos = Array.isArray(data.photos) ? data.photos.slice(0, MAX_PHOTOS) : [];

    if (!car || !damage || !insurance || !name || !phone || data.consent !== true || !photos.length) {
      return json({ ok: false, error: 'missing' });
    }

    const id = Utilities.getUuid().replace(/-/g, '').slice(0, 8);
    const tz = Session.getScriptTimeZone() || 'Europe/Athens';
    const submittedAt = Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm:ss');

    // 1. photos → Drive, viewable by link
    const folder = photoFolder();
    const links = [];
    photos.forEach(function (photo, i) {
      const bytes = Utilities.base64Decode(String(photo).replace(/^data:image\/\w+;base64,/, ''));
      if (!bytes.length || bytes.length > MAX_PHOTO_BYTES) return;
      const blob = Utilities.newBlob(bytes, 'image/jpeg', submittedAt.replace(/[: ]/g, '-') + '_' + id + '_' + (i + 1) + '.jpg');
      const file = folder.createFile(blob);
      file.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);
      links.push('https://lh3.googleusercontent.com/d/' + file.getId()); // the image itself, no Drive page
    });
    if (!links.length) return json({ ok: false, error: 'photos' });

    // 2. one row, same columns as before. The apostrophe keeps the phone as text.
    const sheet = SpreadsheetApp.getActive().getSheetByName(SHEET_NAME) || SpreadsheetApp.getActive().getSheets()[0];
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);
    try {
      sheet.appendRow([id, id, submittedAt, car, damage, insurance, insurer, links.join('\n'), name, "'" + phone, CONSENT, 'TRUE']);
    } finally {
      lock.releaseLock();
    }
    return json({ ok: true });
  } catch (err) {
    console.error(err);
    return json({ ok: false, error: 'server' });
  }
}

/** Text without control characters, at most `max` characters. */
function clean(value, max) {
  return String(value || '').replace(/[\u0000-\u0009\u000B-\u001F\u007F]/g, '').trim().slice(0, max);
}

/** "694 420 9870", "+30 6944209870", "0030..." → "306944209870". Other countries kept as typed. */
function phoneDigits(value) {
  let digits = String(value || '').replace(/\D/g, '');
  if (digits.indexOf('00') === 0) digits = digits.slice(2);
  if (digits.length === 10) digits = '30' + digits;
  return digits.length >= 10 && digits.length <= 15 ? digits : '';
}

function photoFolder() {
  const props = PropertiesService.getScriptProperties();
  const savedId = props.getProperty('FOLDER_ID');
  if (savedId) {
    try { return DriveApp.getFolderById(savedId); } catch (e) { /* deleted: make a new one */ }
  }
  const found = DriveApp.getFoldersByName(FOLDER_NAME);
  const folder = found.hasNext() ? found.next() : DriveApp.createFolder(FOLDER_NAME);
  props.setProperty('FOLDER_ID', folder.getId());
  return folder;
}

function json(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
