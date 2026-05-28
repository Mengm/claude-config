const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

// Cookie store: skill 目录下的 cookies.json（通过 SKILL_DIR 环境变量定位）
// 如果未设置则回退到 ~/.gpm/
const SKILL_DIR = process.env.SKILL_DIR || path.join(process.env.HOME || process.env.USERPROFILE, ".gpm");
const COOKIES_FILE = path.join(SKILL_DIR, "cookies.json");

async function login() {
  if (!fs.existsSync(SKILL_DIR)) fs.mkdirSync(SKILL_DIR, { recursive: true });

  console.log("[*] Opening browser for GPM SSO login...");
  console.log("[*] Cookies will be saved to:", COOKIES_FILE);

  const browser = await chromium.launch({
    headless: false,
    args: ["--disable-blink-features=AutomationControlled"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
  });
  const page = await context.newPage();

  await page.goto("https://gpm.bytedance.com", {
    waitUntil: "domcontentloaded",
    timeout: 0,
  });

  console.log("[*] Please complete SSO login in the browser...\n");

  // Wait for successful GPM API call (means login succeeded)
  await page.waitForResponse(
    (r) => r.url().includes("gpm.bytedance.com/v2/api/user/info") && r.status() === 200,
    { timeout: 300000 }
  );

  console.log("[*] Login successful! Saving cookies...");

  const cookies = await context.cookies();
  const gpmCookies = cookies.filter(
    (c) =>
      c.domain.includes("bytedance.com") ||
      c.domain.includes("feishu.cn") ||
      c.domain.includes("larkoffice.com")
  );

  const state = await context.storageState();

  const saved = {
    cookies: gpmCookies,
    storageState: state,
    savedAt: new Date().toISOString(),
    expiresHint: "Cookies typically expire in 15-30 days. Re-run login if API returns 401.",
  };

  fs.writeFileSync(COOKIES_FILE, JSON.stringify(saved, null, 2), "utf-8");

  console.log(`[*] Saved ${gpmCookies.length} cookies to ${COOKIES_FILE}`);
  console.log("[*] Domains:", [...new Set(gpmCookies.map((c) => c.domain))].join(", "));
  console.log("\n[*] Done! Future GPM API calls will use these cookies.");

  await browser.close();
}

login().catch((err) => {
  console.error("[ERROR]", err);
  process.exit(1);
});
