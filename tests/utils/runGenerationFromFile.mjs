#!/usr/bin/env node
import fs from "fs";
import path from "path";
import axios from "axios";

const DEFAULT_REQUEST_FILE = "tests/generation/feature_requests.json";

function usage() {
  console.log("Usage:");
  console.log("  npm run gen:testcases");
  console.log("  node tests/utils/runGenerationFromFile.mjs --file tests/generation/feature_requests.json");
}

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const key = argv[i];
    if (!key.startsWith("--")) continue;
    const next = argv[i + 1];
    if (!next || next.startsWith("--")) {
      args[key.slice(2)] = true;
      continue;
    }
    args[key.slice(2)] = next;
    i += 1;
  }
  return args;
}

function loadJson(filePath) {
  const absolute = path.resolve(process.cwd(), filePath);
  const raw = fs.readFileSync(absolute, "utf-8");
  return JSON.parse(raw);
}

function scenarioText(scenarios = []) {
  if (!Array.isArray(scenarios) || scenarios.length === 0) return "";
  const lines = [];
  scenarios.forEach((sc, index) => {
    lines.push(`Scenario ${index + 1}: ${sc.title || "Untitled"}`);
    (sc.steps || []).forEach((step, idx) => lines.push(`  Step ${idx + 1}: ${step}`));
    (sc.assertions || []).forEach((as, idx) => lines.push(`  Assert ${idx + 1}: ${as}`));
  });
  return lines.join("\n");
}

async function createJob(backendUrl, globalBaseUrl, globalCreatedBy, job) {
  const scenarioOutline = scenarioText(job.scenarios || []);
  const description = scenarioOutline
    ? `${job.feature_description}\n\nScenario Outline (manual file):\n${scenarioOutline}`
    : job.feature_description;

  const payload = {
    feature_name: job.feature_name,
    feature_description: description,
    seed_urls: job.seed_urls || ["/"],
    coverage_mode: job.coverage_mode || "SMOKE_NEGATIVE",
    max_scenarios: job.max_scenarios ?? 8,
    max_routes: job.max_routes ?? 20,
    base_url: job.base_url || globalBaseUrl || "http://localhost:3000",
    intent_hints: job.intent_hints || [],
    created_by: job.created_by || globalCreatedBy || "manual-file-runner",
    manual_scenarios: Array.isArray(job.scenarios) ? job.scenarios : [],
  };

  const createUrl = `${backendUrl.replace(/\/$/, "")}/test-generation/jobs/`;
  const createResp = await axios.post(createUrl, payload, {
    headers: { "Content-Type": "application/json" },
    timeout: 120000,
  });
  const created = createResp.data;
  const jobId = created.job_id;

  const detailUrl = `${backendUrl.replace(/\/$/, "")}/test-generation/jobs/${jobId}/`;
  const detailResp = await axios.get(detailUrl, { timeout: 120000 });
  const detail = detailResp.data;

  return {
    jobId,
    status: created.status || detail.status,
    detail,
  };
}

async function run() {
  const args = parseArgs(process.argv);
  if (args.help || args.h) {
    usage();
    process.exit(0);
  }

  const file = args.file || DEFAULT_REQUEST_FILE;
  let config;
  try {
    config = loadJson(file);
  } catch (err) {
    console.error(`Failed to load request file: ${file}`);
    console.error(String(err));
    process.exit(1);
  }

  const backendUrl = config.backend_url || "http://127.0.0.1:8000";
  const jobs = config.jobs || [];
  if (!Array.isArray(jobs) || jobs.length === 0) {
    console.error("No jobs found in request file. Add at least one job under `jobs`.");
    process.exit(1);
  }

  console.log(`Using request file: ${file}`);
  console.log(`Backend: ${backendUrl}`);
  console.log(`Total jobs: ${jobs.length}\n`);

  const results = [];
  for (const job of jobs) {
    console.log(`Creating generation job for feature: ${job.feature_name}`);
    try {
      const result = await createJob(
        backendUrl,
        config.base_url,
        config.created_by,
        job
      );
      results.push(result);
      const warnings = result.detail?.crawl_summary?.warnings || [];
      const validation = result.detail?.validation_summary || {};

      console.log(`  job_id: ${result.jobId}`);
      console.log(`  status: ${result.status}`);
      if (warnings.length) {
        console.log(`  warnings: ${warnings.length}`);
      }
      console.log(`  valid_artifacts: ${validation.valid_artifacts ?? "NA"}`);
      console.log(`  invalid_artifacts: ${validation.invalid_artifacts ?? "NA"}`);
      console.log("");
    } catch (err) {
      const responseBody = err?.response?.data;
      console.error(`  failed: ${job.feature_name}`);
      if (responseBody) {
        console.error(`  response: ${JSON.stringify(responseBody)}`);
      } else {
        console.error(`  error: ${String(err)}`);
      }
      console.error("");
    }
  }

  if (results.length === 0) {
    console.error("No generation jobs were created successfully.");
    process.exit(1);
  }

  console.log("Next steps:");
  console.log(`1. Open admin: ${backendUrl.replace(/\/$/, "")}/admin/test_generation/generationjob/`);
  console.log("2. Review generated draft for each job.");
  console.log("3. Approve from admin action/link.");
  console.log("4. Materialize from admin action/link (files will be written to tests/generated and tests/pages/generated).");
  console.log("");
  console.log("Created jobs:");
  results.forEach((r) => {
    console.log(`- ${r.jobId} (${r.status})`);
    console.log(`  Detail API: ${backendUrl.replace(/\/$/, "")}/test-generation/jobs/${r.jobId}/`);
  });
}

run().catch((err) => {
  console.error("Runner crashed:");
  console.error(String(err));
  process.exit(1);
});
