import { config as loadEnvFile } from "@dotenvx/dotenvx";
import fs from "fs";
import path from "path";

// Goal: ensure .env.local has a good VITE_CONVEX_URL for dev without clobbering a valid existing one.

const appDir = process.cwd();
const outPath = path.resolve(appDir, ".env.local");

// 1) If .env.local already has a non-placeholder VITE_CONVEX_URL, keep it (normalize to .convex.cloud if needed)
try {
  if (fs.existsSync(outPath)) {
    const cur = fs.readFileSync(outPath, "utf-8");
    const m = cur.match(/^[ \t]*VITE_CONVEX_URL\s*=\s*(.+)$/m);
    if (m) {
      let val = m[1].trim();
      // Normalize existing value if needed
      if (val.endsWith(".convex.site")) {
        const norm = val.replace(/\.convex\.site$/, ".convex.cloud");
        fs.writeFileSync(outPath, `VITE_CONVEX_URL=${norm}\n`, { encoding: "utf-8" });
        console.log(`Normalized existing ${outPath} to VITE_CONVEX_URL=${norm}`);
        process.exit(0);
      }
      if (val && !val.includes("<your-deployment>")) {
        console.log(`Keeping existing ${outPath} VITE_CONVEX_URL=${val}`);
        process.exit(0);
      }
    }
  }
} catch {}

// 2) Prefer env var from the running process (PowerShell Ensure-ConvexHttpUrl sets HTTP .convex.site)
let candidate = process.env.CONVEX_HTTP_URL;

// 3) Fallback to repo root .env (decrypt with dotenvx)
if (!candidate) {
  const rootEnvPath = path.resolve(appDir, "../.env");
  const injected = {};
  try {
    loadEnvFile({ path: rootEnvPath, processEnv: injected });
    candidate = injected.CONVEX_HTTP_URL;
  } catch {}
}

// Treat placeholder as not configured
if (candidate && candidate.includes("<your-deployment>")) {
  candidate = undefined;
}

if (!candidate) {
  // 4) Fallback: parse deployment slug from README and construct convex.site URL
  try {
    const readme = fs.readFileSync(path.resolve(appDir, "README.md"), "utf-8");
    const m = readme.match(/https:\/\/dashboard\.convex\.dev\/d\/([a-z0-9-]+)/i);
    if (m && m[1]) {
      candidate = `https://${m[1]}.convex.cloud`;
      console.log(`Derived VITE_CONVEX_URL from README: ${candidate}`);
    }
  } catch {}
}

if (!candidate) {
  console.error("No Convex URL found via env, ../.env, or README; not writing .env.local");
  process.exit(0);
}

// If candidate came from CONVEX_HTTP_URL (.convex.site), convert to .convex.cloud for Convex JS client
if (candidate.endsWith(".convex.site")) {
  candidate = candidate.replace(/\.convex\.site$/, ".convex.cloud");
}

const out = `VITE_CONVEX_URL=${candidate}\n`;
fs.writeFileSync(outPath, out, { encoding: "utf-8" });
console.log(`Wrote ${outPath} with VITE_CONVEX_URL=${candidate}`);
