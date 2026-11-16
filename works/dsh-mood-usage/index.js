/**
 * Host-only today-spend route for the DSH Mood Eyes widget.
 *
 * The accounting modules are copied from dsh-live-console so this plugin does not
 * depend on another plugin's private web routes or capability key. The sweep is
 * expensive, so the route memoizes its result for two minutes and single-flights
 * concurrent requests.
 */

import { homedir } from 'node:os';
import { join } from 'node:path';
import { collectUsage } from './usage-stats.mjs';

const CACHE_MS = 120_000;
const USD_TO_CNY = 7.1;

let cache = { at: 0, value: null };
let flight;

function resolveHome() {
  const configured = typeof process.env.DSH_HOME === 'string' ? process.env.DSH_HOME.trim() : '';
  return configured || join(homedir(), '.dsh');
}

async function readUsage() {
  const now = Date.now();
  if (cache.value !== null && now - cache.at < CACHE_MS) return cache.value;
  if (flight !== undefined) return flight;

  flight = (async () => {
    try {
      const usage = await collectUsage({ home: resolveHome(), now });
      const today = usage && usage.today ? usage.today : {};
      const costUsd = Number(today.cost) || 0;
      const value = {
        ok: true,
        at: now,
        peakNow: usage && usage.peakNow === true,
        rate: USD_TO_CNY,
        today: {
          costUsd,
          costCny: costUsd * USD_TO_CNY,
          calls: Number(today.calls) || 0,
          tokens: today.tokens ?? null
        }
      };
      cache = { at: now, value };
      return value;
    } catch (error) {
      const value = {
        ok: false,
        at: now,
        error: String(error && error.message ? error.message : error)
      };
      cache = { at: now, value };
      return value;
    } finally {
      flight = undefined;
    }
  })();

  return flight;
}

export const inject = ['connection'];

export function apply(ctx) {
  ctx.effect(() => ctx.connection.fetch.register({
    path: '/api/mood-eyes/usage',
    methods: ['GET'],
    requestBody: 'buffered',
    fetch: async () => {
      const value = await readUsage();
      return new Response(JSON.stringify(value), {
        status: 200,
        headers: {
          'content-type': 'application/json; charset=utf-8',
          'cache-control': 'no-store'
        }
      });
    }
  }), 'dsh-mood-usage: today spend route');
}
