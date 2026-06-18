import { readdir, readFile } from "node:fs/promises";
import path from "node:path";

const FIXED_FACTOR_ID = "fixed.repeated-request";

export async function runFixedOfficialFactor(options = {}) {
  return runOfficialFactorById(FIXED_FACTOR_ID, options);
}

export async function runOfficialFactorById(factorId, options = {}) {
  const packRoot =
    options.packRoot ?? path.join(process.cwd(), "tests", "fixtures", "official-packs");
  const sessionPath =
    options.sessionPath ?? path.join(process.cwd(), "tests", "fixtures", "sessions", "repeated-request.json");
  const [factorRecord, session] = await Promise.all([
    loadFactorFromPacks(packRoot, factorId),
    readJson(sessionPath)
  ]);

  return runFactor(factorRecord.factor, session, { packId: factorRecord.pack_id });
}

export function runFactor(factor, session, context = {}) {
  const matchedEvent = findMatchingEvent(factor.match?.any_event, session.events ?? []);
  const matched = Boolean(matchedEvent);

  return {
    pack_id: context.packId,
    factor_id: factor.factor_id,
    title: factor.title,
    version: factor.version,
    status: matched ? "matched" : "not_matched",
    tags: matched ? factor.outputs?.tags ?? [] : [],
    verdict_signals: matched ? factor.outputs?.verdict_signals ?? [] : [],
    evidence_refs: matched ? [`event:${matchedEvent.id}`] : []
  };
}

async function loadFactorFromPacks(packRoot, factorId) {
  const entries = await readdir(packRoot, { withFileTypes: true });

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const packDir = path.join(packRoot, entry.name);
    const pack = await readJson(path.join(packDir, "pack.json"));

    for (const factorPath of pack.factors ?? []) {
      const factor = await readJson(path.join(packDir, factorPath));

      if (factor.factor_id === factorId) {
        return {
          pack_id: pack.pack_id,
          factor
        };
      }
    }
  }

  throw new Error(`official factor not found: ${factorId}`);
}

async function readJson(file) {
  return JSON.parse(await readFile(file, "utf8"));
}

function findMatchingEvent(rule, events) {
  if (!rule) {
    return null;
  }

  return events.find((event) => {
    if (rule.role !== undefined && event.role !== rule.role) {
      return false;
    }
    if (rule.status !== undefined && event.status !== rule.status) {
      return false;
    }
    if (
      rule.text_includes !== undefined &&
      !String(event.text ?? "").toLowerCase().includes(String(rule.text_includes).toLowerCase())
    ) {
      return false;
    }
    return true;
  });
}

function parseArgs(argv) {
  const args = new Map();

  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];

    if (key === "--fixed") {
      args.set("fixed", true);
      continue;
    }
    if (key.startsWith("--")) {
      args.set(key.slice(2), argv[index + 1]);
      index += 1;
    }
  }

  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const options = {
    packRoot: args.get("pack-root"),
    sessionPath: args.get("session")
  };
  const result = args.get("fixed")
    ? await runFixedOfficialFactor(options)
    : await runOfficialFactorById(args.get("factor"), options);

  console.log(JSON.stringify(result, null, 2));
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
