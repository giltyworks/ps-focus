// PS Focus friends server (Cloudflare Worker with a D1 database)
//
// Each copy of PS Focus with friends turned on checks in every few minutes with its owner's figures and gets its
// friends' figures back. People are known by their Google account, proved with a Google ID token the app signs in for;
// only the account's id is kept, never its email. See README.md for deploying.

const GOOGLE_CERTS = 'https://www.googleapis.com/oauth2/v3/certs';
const GOOGLE_ISSUERS = ['accounts.google.com', 'https://accounts.google.com'];
// Friend codes: eight characters without the easily confused 0, O, 1 and I, shown as two groups of four
const CODE_ALPHABET = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
const CODE_LENGTH = 8;
const MAX_FRIENDS = 100;
const MAX_PENDING = 50;
const NAME_MAX_LENGTH = 32;
const PROGRAMS = ['Photoshop', 'Krita', 'Clip Studio Paint'];
// Most requests one person may make in a minute, counted per server instance, against runaway loops
const REQUESTS_PER_MINUTE = 30;
// Upper limits of each figure, in hours or counts, so nothing absurd is passed on to friends
const FIGURE_LIMITS = { two_weeks: 336, total: 1000000, today: 24, week: 168, level: 99, streak: 100000 };
// Someone not heard from in this long, such as after uninstalling with friends on, is deleted by the daily clean-up
const FORGET_AFTER_DAYS = 180;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let certificates = { keys: new Map(), expires: 0 };
const recentRequests = new Map();

export default {
  async fetch(request, env) {
    try {
      return await handle(request, env);
    } catch (error) {
      if (error instanceof HttpError) return json({ error: error.message }, error.status);
      console.error(error);
      return json({ error: 'The friends server had a problem, try again later' }, 500);
    }
  },

  // Daily, see triggers in wrangler.toml
  async scheduled(_controller, env) {
    const cutoff = Math.floor(Date.now() / 1000) - FORGET_AFTER_DAYS * 86400;
    const db = env.DB;
    const gone = 'SELECT sub FROM users WHERE updated_at < ?';
    await db.batch([
      db.prepare(`DELETE FROM friends WHERE user IN (${gone}) OR friend IN (${gone})`).bind(cutoff, cutoff),
      db.prepare(`DELETE FROM requests WHERE sender IN (${gone}) OR recipient IN (${gone})`).bind(cutoff, cutoff),
      db.prepare('DELETE FROM users WHERE updated_at < ?').bind(cutoff),
    ]);
  },
};

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

async function handle(request, env) {
  const path = new URL(request.url).pathname;
  const actions = { '/v1/sync': sync, '/v1/add': add, '/v1/accept': accept, '/v1/decline': decline, '/v1/remove': remove, '/v1/leave': leave };
  const action = actions[path];
  if (!action) throw new HttpError(404, 'Not found');
  if (request.method !== 'POST') throw new HttpError(405, 'Use POST');
  const sub = await authenticate(request, env);
  throttle(sub);
  let body;
  try {
    body = await request.json();
  } catch {
    throw new HttpError(400, 'The request was not JSON');
  }
  if (typeof body !== 'object' || body === null) throw new HttpError(400, 'The request was not an object');
  return json(await action(env, sub, body));
}

// ----- Who is asking -----

function base64UrlBytes(text) {
  const binary = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - (text.length % 4)) % 4));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function googleKey(kid) {
  if (Date.now() >= certificates.expires || !certificates.keys.has(kid)) {
    const response = await fetch(GOOGLE_CERTS);
    if (!response.ok) throw new HttpError(503, 'Could not check your Google sign-in, try again later');
    const maxAge = Number((response.headers.get('Cache-Control') || '').match(/max-age=(\d+)/)?.[1] || 3600);
    const keys = new Map();
    for (const jwk of (await response.json()).keys) {
      keys.set(jwk.kid, await crypto.subtle.importKey('jwk', jwk, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']));
    }
    certificates = { keys, expires: Date.now() + maxAge * 1000 };
  }
  return certificates.keys.get(kid);
}

async function authenticate(request, env) {
  const token = (request.headers.get('Authorization') || '').replace(/^Bearer /, '');
  // Local testing only: wrangler dev --var DEV_AUTH:1 accepts "dev:<id>" in place of a Google token
  if (env.DEV_AUTH === '1' && token.startsWith('dev:')) return token.slice(4);
  const parts = token.split('.');
  if (parts.length !== 3) throw new HttpError(401, 'Sign in with Google to use friends');
  let header, payload;
  try {
    header = JSON.parse(new TextDecoder().decode(base64UrlBytes(parts[0])));
    payload = JSON.parse(new TextDecoder().decode(base64UrlBytes(parts[1])));
  } catch {
    throw new HttpError(401, 'Your Google sign-in could not be read, reconnect your account');
  }
  const key = header.alg === 'RS256' ? await googleKey(header.kid) : null;
  const signed = new TextEncoder().encode(`${parts[0]}.${parts[1]}`);
  if (!key || !(await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, base64UrlBytes(parts[2]), signed))) {
    throw new HttpError(401, 'Your Google sign-in could not be confirmed, reconnect your account');
  }
  const now = Date.now() / 1000;
  if (!GOOGLE_ISSUERS.includes(payload.iss) || payload.aud !== env.GOOGLE_CLIENT_ID || typeof payload.sub !== 'string') {
    throw new HttpError(401, 'That sign-in is not for PS Focus');
  }
  // A minute's leeway for a PC clock running slightly fast or slow
  if (!(payload.exp > now - 60)) throw new HttpError(401, 'Your Google sign-in has expired, try again');
  return payload.sub;
}

function throttle(sub) {
  const minute = Math.floor(Date.now() / 60000);
  const entry = recentRequests.get(sub);
  if (!entry || entry.minute !== minute) {
    if (recentRequests.size > 10000) recentRequests.clear();
    recentRequests.set(sub, { minute, count: 1 });
    return;
  }
  entry.count += 1;
  if (entry.count > REQUESTS_PER_MINUTE) throw new HttpError(429, 'Too many requests, wait a minute');
}

// ----- What is kept -----

function cleanName(name) {
  const text = typeof name === 'string' ? name.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, NAME_MAX_LENGTH) : '';
  return text || 'PS Focus user';
}

function cleanStats(stats) {
  const result = {};
  if (typeof stats !== 'object' || stats === null) stats = {};
  for (const [field, limit] of Object.entries(FIGURE_LIMITS)) {
    const value = Number(stats[field]);
    result[field] = Number.isFinite(value) ? Math.min(Math.max(value, 0), limit) : 0;
    // Hours to a tenth; counts whole
    result[field] = ['level', 'streak'].includes(field) ? Math.round(result[field]) : Math.round(result[field] * 10) / 10;
  }
  result.active = PROGRAMS.includes(stats.active) ? stats.active : null;
  return result;
}

function normalCode(code) {
  return typeof code === 'string' ? code.toUpperCase().replace(/[^0-9A-Z]/g, '') : '';
}

function newCode() {
  const bytes = crypto.getRandomValues(new Uint8Array(CODE_LENGTH));
  return Array.from(bytes, (byte) => CODE_ALPHABET[byte % CODE_ALPHABET.length]).join('');
}

async function userByCode(env, code) {
  const normal = normalCode(code);
  if (normal.length !== CODE_LENGTH) throw new HttpError(400, 'A friend code has 8 letters and numbers');
  const user = await env.DB.prepare('SELECT sub, name FROM users WHERE code = ?').bind(normal).first();
  if (!user) throw new HttpError(404, 'No one has that friend code');
  return user;
}

async function requireUser(env, sub) {
  const user = await env.DB.prepare('SELECT code FROM users WHERE sub = ?').bind(sub).first();
  if (!user) throw new HttpError(409, 'Turn friends on first');
  return user;
}

async function count(env, sql, sub) {
  return (await env.DB.prepare(sql).bind(sub).first('n')) || 0;
}

async function state(env, sub) {
  const db = env.DB;
  const [me, friends, incoming, outgoing] = await db.batch([
    db.prepare('SELECT code, name FROM users WHERE sub = ?').bind(sub),
    db.prepare('SELECT u.code, u.name, u.stats, u.updated_at FROM friends f JOIN users u ON u.sub = f.friend WHERE f.user = ?').bind(sub),
    db.prepare('SELECT u.code, u.name FROM requests r JOIN users u ON u.sub = r.sender WHERE r.recipient = ? ORDER BY r.created_at').bind(sub),
    db.prepare('SELECT u.code, u.name FROM requests r JOIN users u ON u.sub = r.recipient WHERE r.sender = ? ORDER BY r.created_at').bind(sub),
  ]);
  return {
    now: Math.floor(Date.now() / 1000),
    me: me.results[0] || null,
    friends: friends.results.map((row) => ({ code: row.code, name: row.name, stats: JSON.parse(row.stats), updated_at: row.updated_at })),
    incoming: incoming.results,
    outgoing: outgoing.results,
  };
}

// ----- Actions -----

async function sync(env, sub, body) {
  const now = Math.floor(Date.now() / 1000);
  const name = cleanName(body.name);
  const stats = JSON.stringify(cleanStats(body.stats));
  const updated = await env.DB.prepare('UPDATE users SET name = ?, stats = ?, updated_at = ? WHERE sub = ?').bind(name, stats, now, sub).run();
  if (!updated.meta.changes) {
    // A first check-in: a new friend code, tried again in the unlikely case it is taken
    for (let attempt = 0; ; attempt++) {
      try {
        await env.DB.prepare('INSERT INTO users (sub, code, name, stats, updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?)')
          .bind(sub, newCode(), name, stats, now, now).run();
        break;
      } catch (error) {
        if (attempt >= 4 || !String(error).includes('UNIQUE')) throw error;
        // Two first check-ins at once: the other one made the row, so this one updates it
        const again = await env.DB.prepare('UPDATE users SET name = ?, stats = ?, updated_at = ? WHERE sub = ?').bind(name, stats, now, sub).run();
        if (again.meta.changes) break;
      }
    }
  }
  return state(env, sub);
}

async function befriend(env, a, b) {
  for (const sub of [a, b]) {
    if ((await count(env, 'SELECT COUNT(*) AS n FROM friends WHERE user = ?', sub)) >= MAX_FRIENDS) {
      throw new HttpError(409, `Friends are limited to ${MAX_FRIENDS} each`);
    }
  }
  const db = env.DB;
  await db.batch([
    db.prepare('INSERT OR IGNORE INTO friends (user, friend, created_at) VALUES (?, ?, ?), (?, ?, ?)').bind(a, b, Math.floor(Date.now() / 1000), b, a, Math.floor(Date.now() / 1000)),
    db.prepare('DELETE FROM requests WHERE (sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)').bind(a, b, b, a),
  ]);
}

async function add(env, sub, body) {
  await requireUser(env, sub);
  const target = await userByCode(env, body.code);
  if (target.sub === sub) throw new HttpError(400, "That's your own friend code");
  if (await env.DB.prepare('SELECT 1 FROM friends WHERE user = ? AND friend = ?').bind(sub, target.sub).first()) {
    throw new HttpError(409, `You and ${target.name} are already friends`);
  }
  // Two people adding each other become friends straight away
  if (await env.DB.prepare('SELECT 1 FROM requests WHERE sender = ? AND recipient = ?').bind(target.sub, sub).first()) {
    await befriend(env, sub, target.sub);
    return state(env, sub);
  }
  if ((await count(env, 'SELECT COUNT(*) AS n FROM requests WHERE sender = ?', sub)) >= MAX_PENDING) {
    throw new HttpError(409, 'Too many requests waiting, cancel some first');
  }
  if ((await count(env, 'SELECT COUNT(*) AS n FROM requests WHERE recipient = ?', target.sub)) >= MAX_PENDING) {
    throw new HttpError(409, `${target.name} has too many requests waiting`);
  }
  await env.DB.prepare('INSERT OR IGNORE INTO requests (sender, recipient, created_at) VALUES (?, ?, ?)').bind(sub, target.sub, Math.floor(Date.now() / 1000)).run();
  return state(env, sub);
}

async function accept(env, sub, body) {
  const sender = await userByCode(env, body.code);
  if (!(await env.DB.prepare('SELECT 1 FROM requests WHERE sender = ? AND recipient = ?').bind(sender.sub, sub).first())) {
    throw new HttpError(404, 'That request was cancelled');
  }
  await befriend(env, sub, sender.sub);
  return state(env, sub);
}

async function decline(env, sub, body) {
  const sender = await userByCode(env, body.code);
  await env.DB.prepare('DELETE FROM requests WHERE sender = ? AND recipient = ?').bind(sender.sub, sub).run();
  return state(env, sub);
}

// Unfriends, or cancels a request sent
async function remove(env, sub, body) {
  const other = await userByCode(env, body.code);
  const db = env.DB;
  await db.batch([
    db.prepare('DELETE FROM friends WHERE (user = ? AND friend = ?) OR (user = ? AND friend = ?)').bind(sub, other.sub, other.sub, sub),
    db.prepare('DELETE FROM requests WHERE sender = ? AND recipient = ?').bind(sub, other.sub),
  ]);
  return state(env, sub);
}

// Turning friends off deletes everything kept about the person
async function leave(env, sub) {
  const db = env.DB;
  await db.batch([
    db.prepare('DELETE FROM friends WHERE user = ? OR friend = ?').bind(sub, sub),
    db.prepare('DELETE FROM requests WHERE sender = ? OR recipient = ?').bind(sub, sub),
    db.prepare('DELETE FROM users WHERE sub = ?').bind(sub),
  ]);
  return { left: true };
}
