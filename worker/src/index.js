const json = (data, status = 200, env) => new Response(JSON.stringify(data), {
  status,
  headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' },
});

const now = () => new Date().toISOString();
const text = async (request) => request.json().catch(() => null);

function httpsOrigin(value) {
  if (typeof value !== 'string') return null;
  try {
    const url = new URL(value.trim());
    if (url.protocol !== 'https:' || url.username || url.password) return null;
    return url.origin;
  } catch {
    return null;
  }
}

function optionalInteger(value) {
  if (value === null || value === undefined || value === '') return null;
  const number = Number(value);
  return Number.isSafeInteger(number) ? number : null;
}

function getDb(env) {
  return env?.Check || env?.DB || env?.D1 || env?.CHECK || null;
}

function missingDbError() {
  return json({
    error: 'D1 未绑定：请确认 Cloudflare 部署已完成自动资源配置，且 Worker Settings → Bindings 中存在名为 Check 的 D1 绑定。',
    code: 'D1_BINDING_MISSING',
  }, 503);
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

function tokenFrom(request) {
  const value = request.headers.get('authorization') || '';
  return value.startsWith('Bearer ') ? value.slice(7) : '';
}

async function requireRunner(request, env) {
  return tokenFrom(request) && tokenFrom(request) === env.RUNNER_TOKEN;
}

async function requireSession(request, env) {
  const token = tokenFrom(request);
  if (!token) return false;
  const db = getDb(env);
  if (!db) return false;
  const hash = await sha256(token);
  const row = await db.prepare('SELECT token_hash FROM sessions WHERE token_hash = ? AND expires_at > ?')
    .bind(hash, now()).first();
  return Boolean(row);
}

async function encrypt(value, env) {
  if (!env.DATA_ENCRYPTION_KEY) throw new Error('缺少 DATA_ENCRYPTION_KEY Secret');
  const keyBytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(env.DATA_ENCRYPTION_KEY)));
  const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['encrypt']);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const encrypted = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, new TextEncoder().encode(value));
  return `${btoa(String.fromCharCode(...iv))}.${btoa(String.fromCharCode(...new Uint8Array(encrypted)))}`;
}

async function decrypt(value, env) {
  if (!env.DATA_ENCRYPTION_KEY) throw new Error('缺少 DATA_ENCRYPTION_KEY Secret');
  const [ivText, dataText] = value.split('.');
  const keyBytes = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(env.DATA_ENCRYPTION_KEY)));
  const key = await crypto.subtle.importKey('raw', keyBytes, 'AES-GCM', false, ['decrypt']);
  const iv = Uint8Array.from(atob(ivText), (char) => char.charCodeAt(0));
  const data = Uint8Array.from(atob(dataText), (char) => char.charCodeAt(0));
  const result = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, data);
  return new TextDecoder().decode(result);
}

function accountView(row) {
  return {
    id: row.id, name: row.name, url: row.url, enabled: Boolean(row.enabled),
    failure_count: row.failure_count, last_status: row.last_status,
    last_message: row.last_message, last_checkin_at: row.last_checkin_at,
  };
}

let tablesReady = false;

async function ensureTables(env) {
  const db = getDb(env);
  if (tablesReady || !db) return;
  await db.batch([
    db.prepare(`CREATE TABLE IF NOT EXISTS accounts (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT NOT NULL,
      url TEXT NOT NULL,
      secret TEXT NOT NULL,
      enabled INTEGER NOT NULL DEFAULT 1,
      failure_count INTEGER NOT NULL DEFAULT 0,
      last_status TEXT,
      last_message TEXT,
      last_checkin_at TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS runs (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      execution_time TEXT NOT NULL,
      total INTEGER NOT NULL,
      success_count INTEGER NOT NULL,
      fail_count INTEGER NOT NULL,
      created_at TEXT NOT NULL
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS run_results (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id INTEGER NOT NULL,
      account_id INTEGER,
      name TEXT NOT NULL,
      success INTEGER NOT NULL,
      message TEXT,
      quota_awarded INTEGER,
      checkin_count INTEGER,
      session_expired INTEGER NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      FOREIGN KEY (run_id) REFERENCES runs(id),
      FOREIGN KEY (account_id) REFERENCES accounts(id)
    )`),
    db.prepare(`CREATE TABLE IF NOT EXISTS sessions (
      token_hash TEXT PRIMARY KEY,
      expires_at TEXT NOT NULL,
      created_at TEXT NOT NULL
    )`),
    db.prepare(`CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at DESC)`),
    db.prepare(`CREATE INDEX IF NOT EXISTS idx_results_run_id ON run_results(run_id)`),
  ]);
  tablesReady = true;
}

async function handler(request, env) {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  if (method === 'GET' && path === '/api/health') {
    const missing = [];
    if (!getDb(env)) missing.push('Check');
    if (!env.DASHBOARD_PASSWORD) missing.push('DASHBOARD_PASSWORD');
    if (!env.RUNNER_TOKEN) missing.push('RUNNER_TOKEN');
    if (!env.DATA_ENCRYPTION_KEY) missing.push('DATA_ENCRYPTION_KEY');
    if (missing.length) {
      return json({ ok: false, service: 'newapi-checkin-worker', missing, time: now() }, 503, env);
    }
    await getDb(env).prepare('SELECT 1').first();
    return json({ ok: true, service: 'newapi-checkin-worker', database: 'connected', time: now() }, 200, env);
  }

  if (method === 'POST' && path === '/api/auth/login') {
    const body = await text(request);
    if (!getDb(env)) return missingDbError();
    if (!env.DASHBOARD_PASSWORD) return json({ error: 'Worker 尚未配置 DASHBOARD_PASSWORD' }, 503, env);
    if (!body?.password || body.password !== env.DASHBOARD_PASSWORD) return json({ error: '访问口令错误' }, 401, env);
    const token = crypto.randomUUID();
    const expires = new Date(Date.now() + Number(env.SESSION_TTL_SECONDS || 86400) * 1000).toISOString();
    const createdAt = now();
    await getDb(env).batch([
      getDb(env).prepare('DELETE FROM sessions WHERE expires_at <= ?').bind(createdAt),
      getDb(env).prepare('INSERT INTO sessions (token_hash, expires_at, created_at) VALUES (?, ?, ?)')
        .bind(await sha256(token), expires, createdAt),
    ]);
    return json({ token, expires_at: expires }, 200, env);
  }

  if (method === 'POST' && path === '/api/auth/logout') {
    if (!getDb(env)) return missingDbError();
    const token = tokenFrom(request);
    if (!token) return json({ error: '缺少登录 Token' }, 401, env);
    await getDb(env).prepare('DELETE FROM sessions WHERE token_hash = ?').bind(await sha256(token)).run();
    return json({ ok: true }, 200, env);
  }

  if (path.startsWith('/api/runner/')) {
    if (!(await requireRunner(request, env))) return json({ error: 'Runner 未授权' }, 401, env);
    if (!getDb(env)) return missingDbError();
    if (method === 'GET' && path === '/api/runner/config') {
      const rows = await getDb(env).prepare('SELECT id, name, url, secret FROM accounts WHERE enabled = 1 ORDER BY id').all();
      if (rows.results.length > 40) return json({ error: '启用账号数量超过 40，请先停用部分账号' }, 409, env);
      const accounts = [];
      for (const row of rows.results) {
        const config = JSON.parse(await decrypt(row.secret, env));
        const origin = httpsOrigin(config.url);
        if (!origin) throw new Error(`账号 ${row.id} 的站点 URL 必须更新为 HTTPS 地址`);
        accounts.push({ ...config, url: origin, name: row.name, account_id: row.id });
      }
      return json({ accounts }, 200, env);
    }
    if (method === 'POST' && path === '/api/runner/report') {
      const body = await text(request);
      if (!body || !Array.isArray(body.results) || body.results.length > 40) {
        return json({ error: '结果格式错误或账号数量超过 40' }, 400);
      }

      const accountRows = await getDb(env).prepare('SELECT id FROM accounts').all();
      const accountMap = new Map(accountRows.results.map((account) => [account.id, account]));
      const seenAccounts = new Set();
      const results = [];
      for (const result of body.results) {
        const accountId = optionalInteger(result?.account_id);
        const account = accountMap.get(accountId);
        if (!account || accountId <= 0 || seenAccounts.has(accountId) || typeof result?.success !== 'boolean') {
          return json({ error: '结果包含无效或重复的账号 ID' }, 400);
        }
        seenAccounts.add(accountId);
        results.push({
          account,
          accountId,
          name: String(result.name || '未知账号').slice(0, 100),
          success: result.success,
          message: String(result.message || '').slice(0, 1000),
          quotaAwarded: optionalInteger(result.quota_awarded),
          checkinCount: optionalInteger(result.checkin_count),
          sessionExpired: result.session_expired === true,
        });
      }

      const createdAt = now();
      const successCount = results.filter((result) => result.success).length;
      const statements = [
        getDb(env).prepare('INSERT INTO runs (execution_time, total, success_count, fail_count, created_at) VALUES (?, ?, ?, ?, ?)')
          .bind(String(body.execution_time || createdAt).slice(0, 64), results.length, successCount, results.length - successCount, createdAt),
      ];
      if (results.length) {
        for (let offset = 0; offset < results.length; offset += 12) {
          const chunk = results.slice(offset, offset + 12);
          const values = chunk.map(() => '((SELECT MAX(id) FROM runs), ?, ?, ?, ?, ?, ?, ?, ?)').join(', ');
          const bindings = chunk.flatMap((result) => [
            result.accountId, result.name, result.success ? 1 : 0, result.message,
            result.quotaAwarded, result.checkinCount, result.sessionExpired ? 1 : 0, createdAt,
          ]);
          statements.push(getDb(env).prepare(`INSERT INTO run_results
            (run_id, account_id, name, success, message, quota_awarded, checkin_count, session_expired, created_at)
            VALUES ${values}`).bind(...bindings));
        }
        const accountUpdates = JSON.stringify(results.map((result) => ({
          id: result.accountId,
          success: result.success ? 1 : 0,
          message: result.message,
        })));
        statements.push(getDb(env).prepare(`WITH updates AS (
          SELECT CAST(json_extract(value, '$.id') AS INTEGER) AS id,
                 CAST(json_extract(value, '$.success') AS INTEGER) AS success,
                 json_extract(value, '$.message') AS message
          FROM json_each(?)
        )
        UPDATE accounts SET
          failure_count = CASE WHEN (SELECT success FROM updates WHERE updates.id = accounts.id) = 1 THEN 0 ELSE failure_count + 1 END,
          last_status = CASE WHEN (SELECT success FROM updates WHERE updates.id = accounts.id) = 1 THEN 'success' ELSE 'failed' END,
          last_message = COALESCE((SELECT message FROM updates WHERE updates.id = accounts.id), ''),
          last_checkin_at = ?, updated_at = ?
        WHERE id IN (SELECT id FROM updates)`).bind(accountUpdates, createdAt, createdAt));
      }
      const batch = await getDb(env).batch(statements);
      return json({ ok: true, run_id: batch[0].meta.last_row_id }, 201, env);
    }
  }

  if (!getDb(env)) return missingDbError();
  if (!(await requireSession(request, env))) return json({ error: '登录已过期' }, 401, env);
  if (method === 'GET' && path === '/api/dashboard/summary') {
    const latest = await getDb(env).prepare('SELECT * FROM runs ORDER BY id DESC LIMIT 1').first();
    const accounts = await getDb(env).prepare('SELECT * FROM accounts ORDER BY id').all();
    return json({ latest, accounts: accounts.results.map(accountView) }, 200, env);
  }
  if (method === 'GET' && path === '/api/dashboard/runs') {
    const rows = await getDb(env).prepare('SELECT * FROM runs ORDER BY id DESC LIMIT 30').all();
    return json({ runs: rows.results }, 200, env);
  }
  if (method === 'GET' && path.startsWith('/api/dashboard/runs/')) {
    const id = path.split('/').pop();
    const run = await getDb(env).prepare('SELECT * FROM runs WHERE id = ?').bind(id).first();
    const results = await getDb(env).prepare('SELECT * FROM run_results WHERE run_id = ? ORDER BY id').bind(id).all();
    return json({ run, results: results.results }, 200, env);
  }
  if (method === 'GET' && path === '/api/dashboard/accounts') {
    const rows = await getDb(env).prepare('SELECT * FROM accounts ORDER BY id').all();
    return json({ accounts: rows.results.map(accountView) }, 200, env);
  }
  if (method === 'POST' && path === '/api/dashboard/accounts') {
    const body = await text(request);
    const origin = httpsOrigin(body?.url);
    if (!body?.name || !origin || !body?.session || !body?.user_id) return json({ error: '请填写有效的名称、HTTPS URL、Session 和用户 ID' }, 400, env);
    const createdAt = now();
    const secret = await encrypt(JSON.stringify({ url: origin, session: body.session, user_id: body.user_id, cf_clearance: body.cf_clearance || undefined }), env);
    const inserted = await getDb(env).prepare(`INSERT INTO accounts (name, url, secret, created_at, updated_at)
      SELECT ?, ?, ?, ?, ? WHERE (SELECT COUNT(*) FROM accounts WHERE enabled = 1) < 40`)
      .bind(body.name, origin, secret, createdAt, createdAt).run();
    if (!inserted.meta.changes) return json({ error: '启用账号数量已达到 40 个上限' }, 409, env);
    return json({ ok: true }, 201, env);
  }
  if (method === 'PATCH' && path.startsWith('/api/dashboard/accounts/')) {
    const id = path.split('/').pop();
    const body = await text(request);
    if (!body) return json({ error: '请求格式错误' }, 400, env);
    if (body.session && typeof body.enabled === 'boolean') return json({ error: '凭据更新和启停操作请分别提交' }, 400, env);
    const account = await getDb(env).prepare('SELECT * FROM accounts WHERE id = ?').bind(id).first();
    if (!account) return json({ error: '账号不存在' }, 404, env);

    const updates = [];
    if (body.session) {
      const current = JSON.parse(await decrypt(account.secret, env));
      const nextUrl = httpsOrigin(body.url || current.url);
      if (!nextUrl) return json({ error: 'URL 必须是有效的 HTTPS Origin' }, 400, env);
      if (!body.user_id) return json({ error: '更新凭据时必须填写用户 ID' }, 400, env);
      const next = {
        ...current,
        url: nextUrl,
        session: body.session,
      };
      next.user_id = body.user_id;
      if ('cf_clearance' in body) next.cf_clearance = body.cf_clearance || undefined;
      const secret = await encrypt(JSON.stringify(next), env);
      updates.push(getDb(env).prepare('UPDATE accounts SET name = ?, url = ?, secret = ?, failure_count = 0, last_status = NULL, last_message = NULL, updated_at = ? WHERE id = ?')
        .bind(body.name || account.name, nextUrl, secret, now(), id));
    }
    if (typeof body.enabled === 'boolean') {
      if (body.enabled && !account.enabled) {
        updates.push(getDb(env).prepare(`UPDATE accounts SET enabled = 1, updated_at = ?
          WHERE id = ? AND (SELECT COUNT(*) FROM accounts WHERE enabled = 1) < 40`).bind(now(), id));
      } else {
        updates.push(getDb(env).prepare('UPDATE accounts SET enabled = ?, updated_at = ? WHERE id = ?')
          .bind(body.enabled ? 1 : 0, now(), id));
      }
    }

    if (typeof body.enabled !== 'boolean' && !body.session) {
      return json({ error: '请提供 enabled 或新的 Session' }, 400, env);
    }
    const updated = await getDb(env).batch(updates);
    if (body.enabled === true && !account.enabled && !updated[0].meta.changes) {
      return json({ error: '启用账号数量已达到 40 个上限' }, 409, env);
    }
    return json({ ok: true }, 200, env);
  }
  return json({ error: 'Not found' }, 404, env);
}

export default {
  async fetch(request, env) {
    try {
      await ensureTables(env);
      const url = new URL(request.url);
      if (url.pathname.startsWith('/api/')) return await handler(request, env);
      if (env.ASSETS) {
        const assetUrl = new URL(request.url);
        if (assetUrl.pathname === '/') assetUrl.pathname = '/index.html';
        return env.ASSETS.fetch(new Request(assetUrl, request));
      }
      return json({ error: '静态资源绑定未配置' }, 500, env);
    } catch (error) {
      return json({ error: error.message || 'Internal error' }, 500, env);
    }
  },
};
