// PS Focus feedback endpoint (Google Apps Script web app)
//
// Collects feedback posted by the app and emails everything received in each
// six-hour period as a single message. See README.md for deployment steps.

const FEEDBACK_RECIPIENT = 'giltyworks@gmail.com';
const DIGEST_HOURS = 6;
const ENTRY_PREFIX = 'feedback_';
const MAX_ENTRIES_PER_REQUEST = 20;
const MAX_MESSAGE_LENGTH = 4000;
// Update check: when publishing a build, set its version and the page people download it from.
// The app shows "update available" only when this version is newer than its own and the link is https.
const LATEST_VERSION = '1.1.0';
const DOWNLOAD_URL = 'https://github.com/giltyworks/ps-focus/releases/latest';
// Caps what can accumulate between digests so repeated requests cannot exhaust script storage
const MAX_STORED_ENTRIES = 100;

// Run once from the Apps Script editor to grant permissions and schedule the digest
function setup() {
  ScriptApp.getProjectTriggers()
    .filter((trigger) => trigger.getHandlerFunction() === 'sendDigest')
    .forEach((trigger) => ScriptApp.deleteTrigger(trigger));
  ScriptApp.newTrigger('sendDigest').timeBased().everyHours(DIGEST_HOURS).create();
}

function doPost(e) {
  try {
    const payload = JSON.parse(e.postData.contents);
    const entries = Array.isArray(payload.entries) ? payload.entries.slice(0, MAX_ENTRIES_PER_REQUEST) : [];
    // Serialise requests so concurrent submissions cannot exceed the storage cap
    const lock = LockService.getScriptLock();
    lock.waitLock(10000);
    let stored = 0;
    try {
      const properties = PropertiesService.getScriptProperties();
      const storedKeys = new Set(properties.getKeys().filter((key) => key.indexOf(ENTRY_PREFIX) === 0));
      entries.forEach((entry) => {
        const rating = Math.round(Number(entry.rating));
        const id = String(entry.id || '').replace(/[^A-Za-z0-9-]/g, '').slice(0, 64) || Utilities.getUuid();
        const key = ENTRY_PREFIX + id;
        // A retried entry replaces its stored copy, so it is accepted even when storage is full
        if (!storedKeys.has(key) && storedKeys.size >= MAX_STORED_ENTRIES) {
          return;
        }
        const record = {
          submitted_at: String(entry.submitted_at || '').slice(0, 40),
          received_at: new Date().toISOString(),
          rating: rating >= 1 && rating <= 5 ? rating : null,
          message: String(entry.message || '').slice(0, MAX_MESSAGE_LENGTH),
        };
        // Keyed by entry id so a retried request does not duplicate feedback
        properties.setProperty(key, JSON.stringify(record));
        storedKeys.add(key);
        stored += 1;
      });
    } finally {
      lock.releaseLock();
    }
    // The app keeps undelivered feedback queued and retries after the next digest frees space
    if (stored < entries.length) {
      return respond({ ok: false, stored: stored, error: 'Feedback storage is full; try again later' });
    }
    return respond({ ok: true, stored: stored });
  } catch (error) {
    return respond({ ok: false, error: String(error) });
  }
}

// Answers the app's daily update check; it receives nothing from the app and stores nothing
function doGet() {
  return respond({ ok: true, latest_version: LATEST_VERSION, download_url: DOWNLOAD_URL });
}

function sendDigest() {
  const properties = PropertiesService.getScriptProperties();
  const stored = properties.getProperties();
  const keys = Object.keys(stored).filter((key) => key.indexOf(ENTRY_PREFIX) === 0);
  if (!keys.length) {
    return;
  }
  const records = keys
    .map((key) => JSON.parse(stored[key]))
    .sort((first, second) => first.received_at.localeCompare(second.received_at));
  const sections = records.map((record, index) => {
    const stars = record.rating ? '★'.repeat(record.rating) + '☆'.repeat(5 - record.rating) + ' (' + record.rating + '/5)' : 'No rating';
    return [
      'Feedback ' + (index + 1) + ' of ' + records.length,
      'Rating: ' + stars,
      'Submitted (user local time): ' + (record.submitted_at || 'unknown'),
      'Received (UTC): ' + record.received_at,
      '',
      record.message || '(no message)',
    ].join('\n');
  });
  const subject = 'PS Focus feedback: ' + records.length + (records.length === 1 ? ' submission' : ' submissions');
  MailApp.sendEmail(FEEDBACK_RECIPIENT, subject, sections.join('\n\n----------------------------------------\n\n'));
  // Delete only after the email is sent so a failed send is retried in the next period
  keys.forEach((key) => properties.deleteProperty(key));
}

function respond(result) {
  return ContentService.createTextOutput(JSON.stringify(result)).setMimeType(ContentService.MimeType.JSON);
}
