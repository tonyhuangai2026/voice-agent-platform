/**
 * Minimal SIP message parser and generator.
 * Handles the subset of SIP needed for Voice Connector integration:
 * INVITE, ACK, BYE, and their responses.
 */

export interface SipMessage {
  // Request fields (only for requests)
  method?: string;
  requestUri?: string;
  // Response fields (only for responses)
  statusCode?: number;
  reasonPhrase?: string;
  // Common - single-value headers (lowercase key)
  headers: Record<string, string>;
  // Raw header lines preserved in order (for Via, Record-Route, etc.)
  rawHeaders: string[];
  body: string;
}

export function parseSipMessage(raw: string): SipMessage {
  const headerEnd = raw.indexOf('\r\n\r\n');
  const headerSection = headerEnd >= 0 ? raw.substring(0, headerEnd) : raw;
  const body = headerEnd >= 0 ? raw.substring(headerEnd + 4) : '';

  const lines = headerSection.split('\r\n');
  const firstLine = lines[0];

  let method: string | undefined;
  let requestUri: string | undefined;
  let statusCode: number | undefined;
  let reasonPhrase: string | undefined;

  // Determine if request or response
  if (firstLine.startsWith('SIP/')) {
    // Response: SIP/2.0 200 OK
    const parts = firstLine.split(' ');
    statusCode = parseInt(parts[1], 10);
    reasonPhrase = parts.slice(2).join(' ');
  } else {
    // Request: INVITE sip:... SIP/2.0
    const parts = firstLine.split(' ');
    method = parts[0];
    requestUri = parts[1];
  }

  // Parse headers (handle multi-line headers with leading whitespace)
  const headers: Record<string, string> = {};
  const rawHeaders: string[] = [];
  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (line.startsWith(' ') || line.startsWith('\t')) {
      // Continuation of previous header
      if (rawHeaders.length > 0) {
        rawHeaders[rawHeaders.length - 1] += ' ' + line.trim();
      }
      const lastKey = Object.keys(headers).pop();
      if (lastKey) headers[lastKey] += ' ' + line.trim();
      continue;
    }
    const colonIdx = line.indexOf(':');
    if (colonIdx < 0) continue;
    const key = line.substring(0, colonIdx).trim();
    const value = line.substring(colonIdx + 1).trim();
    // Preserve raw header line (keeps original casing and order)
    rawHeaders.push(line);
    // Store with lowercase key for easy lookup (last value wins for single-value headers)
    headers[key.toLowerCase()] = value;
  }

  return { method, requestUri, statusCode, reasonPhrase, headers, rawHeaders, body };
}

/**
 * Extract phone number from SIP From/To header value.
 * Examples:
 *   <sip:+14155551234@host> -> +14155551234
 *   "Display" <sip:+14155551234@host>;tag=xyz -> +14155551234
 *   sip:+14155551234@host -> +14155551234
 */
export function extractPhoneFromHeader(headerValue: string): string {
  // Try to extract from <sip:...@...>
  const sipMatch = headerValue.match(/sip:([^@>]+)@/);
  if (sipMatch) return sipMatch[1];
  // Try to extract from <tel:...>
  const telMatch = headerValue.match(/tel:([^>]+)/);
  if (telMatch) return telMatch[1];
  return '';
}

/**
 * Extract tag parameter from From/To header.
 */
export function extractTag(headerValue: string): string {
  const match = headerValue.match(/;tag=([^\s;>]+)/);
  return match ? match[1] : '';
}

/**
 * Extract the URI inside angle brackets, e.g. from
 *   "Display" <sip:user@host:5060;param>;tag=abc
 * returns "sip:user@host:5060;param".
 * Falls back to the trimmed input if no angle brackets are present.
 */
export function extractUriFromAngle(headerValue: string): string {
  const m = headerValue.match(/<([^>]+)>/);
  if (m) return m[1];
  // Strip trailing header params (after first `;` outside angle brackets) just in case.
  const semi = headerValue.indexOf(';');
  return (semi >= 0 ? headerValue.substring(0, semi) : headerValue).trim();
}

/**
 * Pull host and port out of a `sip:user@host:port;params` style URI.
 * Returns null if the URI does not contain a recognizable host.
 */
export function extractHostPortFromUri(uri: string): { host: string; port: number } | null {
  // Strip surrounding < > if any.
  let s = uri.trim();
  if (s.startsWith('<') && s.endsWith('>')) s = s.substring(1, s.length - 1);
  // Drop leading "sip:" or "sips:".
  s = s.replace(/^sips?:/i, '');
  // Drop user@.
  const atIdx = s.indexOf('@');
  if (atIdx >= 0) s = s.substring(atIdx + 1);
  // Stop at first param (`;`) or header (`?`).
  const cut = s.search(/[;?]/);
  if (cut >= 0) s = s.substring(0, cut);
  if (!s) return null;
  // Split host:port (handle IPv6 in brackets).
  let host: string;
  let portStr = '';
  if (s.startsWith('[')) {
    const close = s.indexOf(']');
    if (close < 0) return null;
    host = s.substring(1, close);
    if (s[close + 1] === ':') portStr = s.substring(close + 2);
  } else {
    const colonIdx = s.lastIndexOf(':');
    if (colonIdx >= 0) {
      host = s.substring(0, colonIdx);
      portStr = s.substring(colonIdx + 1);
    } else {
      host = s;
    }
  }
  const port = portStr ? parseInt(portStr, 10) : 5060;
  if (!host || Number.isNaN(port)) return null;
  return { host, port };
}

/**
 * Pull every Record-Route header VALUE from the raw header lines,
 * preserving the order they were received in.
 * A single Record-Route line may carry multiple comma-separated entries.
 */
export function extractRecordRoutes(rawHeaders: string[]): string[] {
  const out: string[] = [];
  for (const line of rawHeaders) {
    const colonIdx = line.indexOf(':');
    if (colonIdx < 0) continue;
    const key = line.substring(0, colonIdx).trim().toLowerCase();
    if (key !== 'record-route') continue;
    const value = line.substring(colonIdx + 1).trim();
    // Split on commas that are NOT inside angle brackets.
    let depth = 0;
    let start = 0;
    for (let i = 0; i < value.length; i++) {
      const c = value[i];
      if (c === '<') depth++;
      else if (c === '>') depth--;
      else if (c === ',' && depth === 0) {
        const part = value.substring(start, i).trim();
        if (part) out.push(part);
        start = i + 1;
      }
    }
    const tail = value.substring(start).trim();
    if (tail) out.push(tail);
  }
  return out;
}

/**
 * Generate a SIP response message.
 * Use rawHeaderLines for headers that must preserve order/multiplicity (Via, Record-Route).
 * Use headers for single-value headers.
 */
export function buildSipResponse(opts: {
  statusCode: number;
  reasonPhrase: string;
  rawHeaderLines?: string[];
  headers?: Record<string, string>;
  body?: string;
}): string {
  const { statusCode, reasonPhrase, rawHeaderLines, headers, body } = opts;
  let msg = `SIP/2.0 ${statusCode} ${reasonPhrase}\r\n`;

  // Write raw header lines first (preserves Via, Record-Route order)
  if (rawHeaderLines) {
    for (const line of rawHeaderLines) {
      msg += `${line}\r\n`;
    }
  }

  // Write additional single-value headers
  if (headers) {
    for (const [key, value] of Object.entries(headers)) {
      msg += `${key}: ${value}\r\n`;
    }
  }

  const bodyStr = body || '';
  msg += `Content-Length: ${Buffer.byteLength(bodyStr)}\r\n`;
  msg += `\r\n`;
  msg += bodyStr;

  return msg;
}

/**
 * Generate a SIP request message (BYE, ACK, INVITE).
 * `rawHeaderLines` is written before `headers` and is used for headers that
 * can repeat (Route, Via). Each entry is a complete "Header: value" line.
 */
export function buildSipRequest(opts: {
  method: string;
  requestUri: string;
  rawHeaderLines?: string[];
  headers: Record<string, string>;
  body?: string;
}): string {
  const { method, requestUri, rawHeaderLines, headers, body } = opts;
  let msg = `${method} ${requestUri} SIP/2.0\r\n`;

  if (rawHeaderLines) {
    for (const line of rawHeaderLines) {
      msg += `${line}\r\n`;
    }
  }

  for (const [key, value] of Object.entries(headers)) {
    msg += `${key}: ${value}\r\n`;
  }

  const bodyStr = body || '';
  msg += `Content-Length: ${Buffer.byteLength(bodyStr)}\r\n`;
  msg += `\r\n`;
  msg += bodyStr;

  return msg;
}

/**
 * Generate a random SIP tag.
 */
export function generateTag(): string {
  return Math.random().toString(36).substring(2, 14);
}

/**
 * Generate a random SIP branch (must start with z9hG4bK per RFC 3261).
 */
export function generateBranch(): string {
  return 'z9hG4bK' + Math.random().toString(36).substring(2, 14);
}
