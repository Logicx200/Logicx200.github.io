#!/usr/bin/env node
/*!
 * ASCII Studio — zero-dependency static server.
 * Serves the app on localhost and supports HTTP range requests for video seeking.
 */
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

const ROOT = __dirname;
const HOST = '127.0.0.1';
const START_PORT = Number(process.env.PORT) || 4173;
const MAX_PORT_ATTEMPTS = 12;

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.md': 'text/markdown; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.avif': 'image/avif',
  '.ico': 'image/x-icon',
  '.mp4': 'video/mp4',
  '.m4v': 'video/mp4',
  '.webm': 'video/webm',
  '.mov': 'video/quicktime',
  '.ogv': 'video/ogg',
  '.ogg': 'video/ogg',
  '.mp3': 'audio/mpeg',
  '.wav': 'audio/wav',
  '.woff2': 'font/woff2'
};

function log(...args) {
  console.log(...args);
}

function setCommonHeaders(res) {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Cache-Control', 'no-cache');
}

function safeResolve(urlPath) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(urlPath, 'http://localhost').pathname);
  } catch (error) {
    return null;
  }

  if (pathname === '/' || pathname === '') pathname = '/index.html';
  if (pathname.endsWith('/')) pathname += 'index.html';

  const relative = pathname.replace(/^\/+/, '');
  const absolute = path.resolve(ROOT, relative);
  const rootWithSep = ROOT.endsWith(path.sep) ? ROOT : ROOT + path.sep;

  if (absolute !== ROOT && !absolute.startsWith(rootWithSep)) return null;
  return absolute;
}

function sendText(res, statusCode, text) {
  const body = Buffer.from(text, 'utf8');
  setCommonHeaders(res);
  res.writeHead(statusCode, {
    'Content-Type': 'text/plain; charset=utf-8',
    'Content-Length': body.length
  });
  res.end(body);
}

function notFound(res) {
  sendText(
    res,
    404,
    '404 — Not found\n\nASCII Studio: 这个路径不存在。\n返回 http://127.0.0.1/ 重新开始。'
  );
}

function parseRange(rangeHeader, size) {
  const match = /^bytes=(\d*)-(\d*)$/.exec(String(rangeHeader || '').trim());
  if (!match) return null;

  let start;
  let end;
  if (match[1] === '' && match[2] === '') return null;
  if (match[1] === '') {
    // suffix range: bytes=-500
    const suffix = Number(match[2]);
    if (!Number.isFinite(suffix) || suffix <= 0) return null;
    start = Math.max(0, size - suffix);
    end = size - 1;
  } else {
    start = Number(match[1]);
    end = match[2] === '' ? size - 1 : Number(match[2]);
  }

  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  if (start < 0 || end < start || start >= size) return null;
  return { start, end: Math.min(end, size - 1) };
}

function serveFile(req, res, filePath, stat) {
  const ext = path.extname(filePath).toLowerCase();
  const contentType = MIME[ext] || 'application/octet-stream';
  const isHead = req.method === 'HEAD';

  setCommonHeaders(res);
  res.setHeader('Content-Type', contentType);
  res.setHeader('Accept-Ranges', 'bytes');
  res.setHeader('Last-Modified', stat.mtime.toUTCString());

  const rangeHeader = req.headers.range;
  if (rangeHeader) {
    const range = parseRange(rangeHeader, stat.size);
    if (!range) {
      res.writeHead(416, {
        'Content-Range': 'bytes */' + stat.size,
        'Content-Length': 0
      });
      res.end();
      return;
    }

    const length = range.end - range.start + 1;
    res.writeHead(206, {
      'Content-Range': 'bytes ' + range.start + '-' + range.end + '/' + stat.size,
      'Content-Length': length
    });
    if (isHead) {
      res.end();
      return;
    }
    const stream = fs.createReadStream(filePath, { start: range.start, end: range.end });
    stream.on('error', (error) => {
      console.error('[ASCII Studio] read error', error.message);
      res.destroy(error);
    });
    stream.pipe(res);
    return;
  }

  res.writeHead(200, { 'Content-Length': stat.size });
  if (isHead) {
    res.end();
    return;
  }
  const stream = fs.createReadStream(filePath);
  stream.on('error', (error) => {
    console.error('[ASCII Studio] read error', error.message);
    res.destroy(error);
  });
  stream.pipe(res);
}

function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.setHeader('Allow', 'GET, HEAD');
    sendText(res, 405, 'Method not allowed');
    return;
  }

  const filePath = safeResolve(req.url || '/');
  if (!filePath) {
    sendText(res, 403, 'Forbidden');
    return;
  }

  fs.stat(filePath, (error, stat) => {
    if (error || !stat.isFile()) {
      notFound(res);
      return;
    }
    serveFile(req, res, filePath, stat);
  });
}

function openBrowser(url) {
  if (process.env.NO_OPEN === '1' || process.argv.includes('--no-open')) return;

  let command;
  let args;
  if (process.platform === 'win32') {
    command = 'cmd';
    args = ['/c', 'start', '', url];
  } else if (process.platform === 'darwin') {
    command = 'open';
    args = [url];
  } else {
    command = 'xdg-open';
    args = [url];
  }

  try {
    const child = spawn(command, args, { detached: true, stdio: 'ignore' });
    child.unref();
  } catch (error) {
    log('（无法自动打开浏览器，请手动访问上面的地址）');
  }
}

function listen(port, attempt) {
  const server = http.createServer(handler);

  server.once('error', (error) => {
    if (error.code === 'EADDRINUSE' && attempt + 1 < MAX_PORT_ATTEMPTS) {
      server.close(() => {});
      listen(port + 1, attempt + 1);
      return;
    }
    if (error.code === 'EADDRINUSE') {
      console.error('端口都被占用，请设置 PORT 环境变量后重试。');
    } else {
      console.error('启动失败：', error.message);
    }
    process.exitCode = 1;
  });

  server.listen(port, HOST, () => {
    const url = 'http://' + HOST + ':' + port + '/';
    log('');
    log('  █████  ASCII STUDIO');
    log('  ██     ██  ██  ██  ██  字符画实验室');
    log('  █████  ██  ██  ██  ██  local image / video → ascii');
    log('');
    log('  →  ' + url);
    log('');
    log('  按 Ctrl+C 停止服务');
    log('');
    openBrowser(url);
  });

  const shutdown = () => {
    log('\n正在关闭 ASCII Studio…');
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 1500).unref();
  };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);
}

listen(START_PORT, 0);
