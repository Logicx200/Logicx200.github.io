/**
 * Host-only balance route for the DSH Mood Eyes widget.
 *
 * The browser never sees the API key: this route reads
 * `$DSH_HOME/.credentials.yaml`, calls DeepSeek's `/user/balance` endpoint, and
 * returns only the projected money fields. Every failure is a value, never a
 * throw, so the widget can render a dash with a safe reason.
 */

import { readFile } from 'node:fs/promises';
import { homedir } from 'node:os';
import { join } from 'node:path';

const BALANCE_URL = 'https://api.deepseek.com/user/balance';
const API_KEY_PATTERN = /^\s*DEEPSEEK_API_KEY\s*:\s*(\S+)\s*$/m;
const REQUEST_TIMEOUT_MS = 10_000;
const CREDENTIALS_FILE_NAME = '.credentials.yaml';

function resolveHome() {
  const configured = typeof process.env.DSH_HOME === 'string' ? process.env.DSH_HOME.trim() : '';
  return configured || join(homedir(), '.dsh');
}

async function readApiKey() {
  const path = join(resolveHome(), CREDENTIALS_FILE_NAME);
  const text = await readFile(path, 'utf8');
  const match = API_KEY_PATTERN.exec(text);
  if (match === null) throw new Error(`no DEEPSEEK_API_KEY ref in ${path}`);
  return match[1];
}

function messageOf(error) {
  if (error instanceof Error) {
    if (error.name === 'AbortError' || error.name === 'TimeoutError') {
      return `balance request timed out after ${REQUEST_TIMEOUT_MS}ms`;
    }
    return error.message;
  }
  return String(error);
}

function money(value) {
  if (typeof value === 'string' && value.length > 0) return value;
  if (typeof value === 'number' && Number.isFinite(value)) return String(value);
  return '0.00';
}

function projectBalance(body, fetchedAt) {
  if (body === null || typeof body !== 'object') {
    return { ok: false, error: 'balance response was not a JSON object' };
  }
  const infos = Array.isArray(body.balance_infos) ? body.balance_infos : [];
  if (infos.length === 0) {
    return { ok: false, error: 'balance response carried no balance_infos' };
  }
  const entry = infos.find((info) =>
    info !== null &&
    typeof info === 'object' &&
    typeof info.currency === 'string' &&
    info.currency.toUpperCase() === 'CNY'
  ) ?? infos[0];
  if (entry === null || typeof entry !== 'object') {
    return { ok: false, error: 'balance response carried an unusable balance_infos entry' };
  }
  return {
    ok: true,
    currency: typeof entry.currency === 'string' ? entry.currency : '',
    total: money(entry.total_balance),
    granted: money(entry.granted_balance),
    toppedUp: money(entry.topped_up_balance),
    fetchedAt
  };
}

async function fetchBalance() {
  const fetchedAt = Date.now();
  let key;
  try {
    key = await readApiKey();
  } catch (error) {
    return { ok: false, error: `credentials: ${messageOf(error)}` };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(BALANCE_URL, {
      method: 'GET',
      headers: {
        authorization: `Bearer ${key}`,
        accept: 'application/json'
      },
      signal: controller.signal
    });
    if (!response.ok) {
      return { ok: false, error: `balance request failed: HTTP ${response.status}` };
    }
    let body;
    try {
      body = await response.json();
    } catch {
      return { ok: false, error: 'balance response was not valid JSON' };
    }
    return projectBalance(body, fetchedAt);
  } catch (error) {
    return { ok: false, error: messageOf(error) };
  } finally {
    clearTimeout(timer);
  }
}

export const inject = ['connection'];

export function apply(ctx) {
  ctx.effect(() => ctx.connection.fetch.register({
    path: '/api/mood-eyes/balance',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async () => {
      const value = await fetchBalance();
      return new Response(JSON.stringify(value), {
        status: 200,
        headers: {
          'content-type': 'application/json; charset=utf-8',
          'cache-control': 'no-store'
        }
      });
    }
  }), 'dsh-mood-balance: account balance route');
}
