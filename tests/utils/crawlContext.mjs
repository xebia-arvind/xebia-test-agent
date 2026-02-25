#!/usr/bin/env node
import { chromium } from "playwright";

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    const val = argv[i + 1];
    if (!key.startsWith("--")) continue;
    args[key.slice(2)] = val;
    i += 1;
  }
  return args;
}

function safeJsonParse(raw, fallback) {
  try {
    return JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function toAbsolute(baseUrl, raw) {
  if (!raw) return null;
  try {
    return new URL(raw, baseUrl).toString();
  } catch {
    return null;
  }
}

function normalizePath(url) {
  try {
    const u = new URL(url);
    return `${u.origin}${u.pathname}`;
  } catch {
    return url;
  }
}

function ignoreRoute(url) {
  const lower = (url || "").toLowerCase();
  return (
    lower.includes("/logout") ||
    lower.endsWith(".png") ||
    lower.endsWith(".jpg") ||
    lower.endsWith(".jpeg") ||
    lower.endsWith(".svg") ||
    lower.endsWith(".css") ||
    lower.endsWith(".js") ||
    lower.includes("/static/")
  );
}

async function extractRouteData(page, maxInteractables) {
  return page.evaluate((limit) => {
    const nodes = Array.from(
      document.querySelectorAll(
        'a, button, input, textarea, select, [role], [data-testid], [aria-label]'
      )
    );
    const interactables = nodes.slice(0, limit).map((el) => {
      const tag = (el.tagName || "").toLowerCase();
      const role = el.getAttribute("role") || "";
      const testId = el.getAttribute("data-testid") || "";
      const aria = el.getAttribute("aria-label") || "";
      const id = el.getAttribute("id") || "";
      const name = el.getAttribute("name") || "";
      const type = el.getAttribute("type") || "";
      const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 120);
      const href = el.getAttribute("href") || "";

      const selectorHints = [];
      if (testId) selectorHints.push(`[data-testid="${testId}"]`);
      if (id) selectorHints.push(`#${id}`);
      if (tag && role) selectorHints.push(`${tag}[role="${role}"]`);
      if (tag && aria) selectorHints.push(`${tag}[aria-label="${aria}"]`);
      if (tag && name) selectorHints.push(`${tag}[name="${name}"]`);
      if (tag && type) selectorHints.push(`${tag}[type="${type}"]`);
      if (tag && href) selectorHints.push(`${tag}[href="${href}"]`);
      if (tag && text) selectorHints.push(`${tag}:has-text("${text.slice(0, 40)}")`);

      return {
        tag,
        role,
        test_id: testId,
        aria_label: aria,
        id,
        name,
        type,
        text,
        href,
        selector_hints: selectorHints.slice(0, 6),
      };
    });

    const forms = Array.from(document.querySelectorAll("form")).map((form, index) => {
      const fields = Array.from(form.querySelectorAll("input, textarea, select")).map((field) => ({
        tag: (field.tagName || "").toLowerCase(),
        name: field.getAttribute("name") || "",
        id: field.getAttribute("id") || "",
        type: field.getAttribute("type") || "",
        placeholder: field.getAttribute("placeholder") || "",
      }));
      return {
        form_index: index,
        action: form.getAttribute("action") || "",
        method: form.getAttribute("method") || "get",
        fields: fields.slice(0, 40),
      };
    });

    const links = Array.from(document.querySelectorAll("a[href]")).map((a) => ({
      href: a.getAttribute("href") || "",
      text: (a.textContent || "").trim().replace(/\s+/g, " ").slice(0, 80),
    }));

    return {
      title: document.title || "",
      interactables,
      forms: forms.slice(0, 20),
      links: links.slice(0, 300),
    };
  }, maxInteractables);
}

async function run() {
  const args = parseArgs(process.argv);
  const baseUrl = args["base-url"] || "http://localhost:3000";
  const maxRoutes = Number(args["max-routes"] || 20);
  const maxDepth = Number(args["max-depth"] || 2);
  const maxInteractables = Number(args["max-interactables"] || 200);
  const seedUrls = safeJsonParse(args["seed-urls"] || "[]", []);

  const queue = [];
  const visited = new Set();
  const warnings = [];

  const initialSeeds = seedUrls.length ? seedUrls : ["/"];
  for (const seed of initialSeeds) {
    const abs = toAbsolute(baseUrl, seed);
    if (!abs) continue;
    queue.push({ url: abs, depth: 0 });
  }

  let browser;
  const routes = [];
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext();
    const page = await context.newPage();
    page.setDefaultTimeout(6000);

    while (queue.length > 0 && routes.length < maxRoutes) {
      const current = queue.shift();
      if (!current) break;
      const normalized = normalizePath(current.url);
      if (visited.has(normalized)) continue;
      if (ignoreRoute(current.url)) continue;
      visited.add(normalized);

      try {
        await page.goto(current.url, { waitUntil: "domcontentloaded" });
      } catch (err) {
        warnings.push(`Failed to open ${current.url}: ${String(err).slice(0, 180)}`);
        continue;
      }

      const data = await extractRouteData(page, maxInteractables);
      routes.push({
        url: page.url(),
        title: data.title,
        depth: current.depth,
        interactables: data.interactables,
        forms: data.forms,
      });

      if (current.depth >= maxDepth) continue;
      for (const link of data.links || []) {
        const abs = toAbsolute(baseUrl, link.href);
        if (!abs || ignoreRoute(abs)) continue;
        try {
          const asUrl = new URL(abs);
          const base = new URL(baseUrl);
          if (asUrl.origin !== base.origin) continue;
        } catch {
          continue;
        }
        queue.push({ url: abs, depth: current.depth + 1 });
      }
    }

    await context.close();
    await browser.close();
  } catch (err) {
    if (browser) {
      try {
        await browser.close();
      } catch {
        // ignore close errors
      }
    }
    warnings.push(`Crawler failed: ${String(err).slice(0, 240)}`);
  }

  const response = {
    base_url: baseUrl,
    seed_urls: initialSeeds,
    max_routes: maxRoutes,
    max_depth: maxDepth,
    routes_visited: routes.length,
    routes,
    warnings,
  };

  process.stdout.write(JSON.stringify(response));
}

run();
