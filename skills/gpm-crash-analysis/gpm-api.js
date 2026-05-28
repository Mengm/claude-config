const fs = require("fs");
const path = require("path");

// Cookie store: 优先从 skill 目录加载，回退到 ~/.gpm/
const SCRIPT_DIR = path.dirname(process.argv[1]);
const COOKIES_PATHS = [
  path.join(SCRIPT_DIR, "cookies.json"),
  path.join(process.env.HOME || process.env.USERPROFILE, ".gpm", "cookies.json"),
];
const GPM_BASE = "https://gpm.bytedance.com";

function findCookiesFile() {
  for (const p of COOKIES_PATHS) {
    if (fs.existsSync(p)) return p;
  }
  return null;
}

function loadCookieHeader() {
  const cookiesFile = findCookiesFile();
  if (!cookiesFile) {
    console.error("[ERROR] No saved cookies found.");
    console.error("Searched:", COOKIES_PATHS.join(", "));
    console.error("Run: node " + path.join(SCRIPT_DIR, "gpm-login.js") + " to login first.");
    process.exit(1);
  }
  const saved = JSON.parse(fs.readFileSync(cookiesFile, "utf-8"));
  console.log("[*] Using cookies from:", cookiesFile);
  const gpmCookies = saved.cookies.filter(
    (c) => c.domain.includes("bytedance.com") || c.domain.includes("gpm")
  );
  return gpmCookies.map((c) => `${c.name}=${c.value}`).join("; ");
}

async function gpmPost(apiPath, body = {}) {
  const cookie = loadCookieHeader();
  const res = await fetch(`${GPM_BASE}${apiPath}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookie,
      Referer: GPM_BASE,
      Origin: GPM_BASE,
    },
    body: JSON.stringify(body),
  });

  if (res.status === 401) {
    console.error("[ERROR] 401 Unauthorized - cookies expired.");
    console.error("Run: node " + path.join(SCRIPT_DIR, "gpm-login.js") + " to re-login.");
    process.exit(1);
  }

  return res.json();
}

// Suppress duplicate cookie log after first call
let cookieLogged = false;
const _origLoad = loadCookieHeader;
const loadCookieHeaderOnce = () => {
  if (cookieLogged) {
    const cookiesFile = findCookiesFile();
    const saved = JSON.parse(fs.readFileSync(cookiesFile, "utf-8"));
    return saved.cookies
      .filter((c) => c.domain.includes("bytedance.com") || c.domain.includes("gpm"))
      .map((c) => `${c.name}=${c.value}`)
      .join("; ");
  }
  cookieLogged = true;
  return _origLoad();
};

// Override for cleaner output
async function gpmPostQuiet(apiPath, body = {}) {
  const cookie = loadCookieHeaderOnce();
  const res = await fetch(`${GPM_BASE}${apiPath}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Cookie: cookie,
      Referer: GPM_BASE,
      Origin: GPM_BASE,
    },
    body: JSON.stringify(body),
  });

  if (res.status === 401) {
    console.error("[ERROR] 401 Unauthorized - cookies expired.");
    console.error("Run: node " + path.join(SCRIPT_DIR, "gpm-login.js") + " to re-login.");
    process.exit(1);
  }

  return res.json();
}

// === GPM Crash API ===

async function getCrashDetail(aid, os, issueId, filters = {}) {
  return gpmPostQuiet("/v2/api/app/crash/issue/detail", {
    crash_type: "crash",
    filters: { type: "and", sub_conditions: [] },
    issue_id: issueId,
    token: "",
    token_type: 0,
    aggregate_type: 0,
    aid,
    os,
    ...filters,
  });
}

async function getCrashEventList(aid, os, issueId, opts = {}) {
  return gpmPostQuiet("/v2/api/app/crash/event/list", {
    pgno: opts.pgno || 1,
    pgsz: opts.pgsz || 20,
    crash_type: "crash",
    filters: { type: "and", sub_conditions: [] },
    issue_id: issueId,
    aggregate_type: 0,
    token: "",
    token_type: 0,
    aid,
    os,
    ...opts,
  });
}

async function getCrashEventLog(aid, os, eventId, deviceId, eventTime, updateVersionCode) {
  return gpmPostQuiet("/v2/api/app/crash/event/log/get", {
    event_id: eventId,
    device_id: deviceId,
    event_time: eventTime,
    update_version_code: updateVersionCode,
    aid,
    os,
  });
}

// === Main ===

async function main() {
  const url = process.argv[2];
  if (!url) {
    console.log("Usage: node gpm-api.js <GPM_CRASH_URL>");
    console.log(
      "Example: node gpm-api.js 'https://gpm.bytedance.com/app/abnormal/detail/crash/<issue_id>?aid=2682&os=iOS'"
    );
    process.exit(0);
  }

  const parsed = new URL(url);
  const pathParts = parsed.pathname.split("/");
  const issueId = pathParts[pathParts.length - 1];
  const aid = parseInt(parsed.searchParams.get("aid"));
  const os = parsed.searchParams.get("os");
  const startTime = parseInt(parsed.searchParams.get("start_time")) || undefined;
  const endTime = parseInt(parsed.searchParams.get("end_time")) || undefined;

  console.log(`[*] Fetching crash: aid=${aid} os=${os} issue=${issueId}`);

  // 1. Issue detail
  const detail = await getCrashDetail(aid, os, issueId);
  console.log("\n=== Issue Detail ===");
  console.log("Status:", detail.data?.status);
  console.log("Comment:", detail.data?.comment);
  console.log("Title:", detail.data?.title);

  // 2. Event list (with symbolicated stacks)
  const filters = {};
  if (startTime) filters.start_time = startTime;
  if (endTime) filters.end_time = endTime;

  const events = await getCrashEventList(aid, os, issueId, { pgsz: 5, ...filters });
  const results = events.data?.result || [];
  console.log(`\n=== Events: ${events.data?.total || 0} total, fetched ${results.length} ===`);

  if (results.length === 0) {
    console.log("[!] No events found. Try adjusting time range (start_time/end_time).");
    process.exit(0);
  }

  // 3. Symbolicated stack
  const first = results[0];
  const eventDetail =
    typeof first.event_detail === "string" ? JSON.parse(first.event_detail) : first.event_detail;

  console.log("\n=== Crash (Symbolicated) ===");
  console.log("Event ID:", first.event_id);
  console.log("Device:", first.device_model, os, first.os_version);
  console.log("Version:", first.update_version_code);
  console.log("Reason:", first.reason?.trim());
  console.log("Scene:", first.last_game_scene || first.last_scene || "N/A");
  console.log("Crash Point:", eventDetail.detail);
  console.log("\n--- Crashed Thread Stack ---");
  eventDetail.main_thread?.backtrace?.forEach((f, i) => {
    console.log(`${String(i).padStart(3)}  ${f.unit}  ${f.method} + ${f.location}`);
  });

  // 4. Raw crash log
  const log = await getCrashEventLog(
    aid,
    os,
    first.event_id,
    first.device_id,
    first.event_time,
    first.update_version_code
  );

  // 5. Save outputs
  const outDir = path.join(process.cwd(), "gpm-output");
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  if (log.data?.data) {
    const outFile = path.join(outDir, `crash-${issueId.substring(0, 8)}.txt`);
    fs.writeFileSync(outFile, log.data.data, "utf-8");
    console.log(`\n[*] Raw crash log: ${outFile}`);
  }

  const jsonFile = path.join(outDir, `crash-${issueId.substring(0, 8)}-full.json`);
  fs.writeFileSync(
    jsonFile,
    JSON.stringify({ detail: detail.data, events: results, log: log.data }, null, 2),
    "utf-8"
  );
  console.log(`[*] Full data: ${jsonFile}`);
}

main().catch((err) => {
  console.error("[ERROR]", err);
  process.exit(1);
});
