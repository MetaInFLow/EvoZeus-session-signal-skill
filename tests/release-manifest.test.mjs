import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash } from "node:crypto";
import { validateReleaseManifest } from "../scripts/validate-release-manifest.mjs";

async function createReleaseFixture({ checksumOverride, omitAttestation } = {}) {
  const root = await mkdtemp(join(tmpdir(), "evozeus-official-"));
  const packPath = "packs/evozeus-default-pack/pack.yaml";
  const checksumPath = "checksums/evozeus-default-pack/v0.1.0.sha256";
  const attestationPath = "attestations/evozeus-default-pack/v0.1.0.attestation.json";

  await mkdir(join(root, "packs/evozeus-default-pack"), { recursive: true });
  await mkdir(join(root, "checksums/evozeus-default-pack"), { recursive: true });
  await mkdir(join(root, "attestations/evozeus-default-pack"), { recursive: true });

  const packContent = "pack_id: evozeus-default-pack\nversion: v0.1.0\n";
  await writeFile(join(root, packPath), packContent);

  const checksum = checksumOverride ?? createHash("sha256").update(packContent).digest("hex");
  await writeFile(join(root, checksumPath), `${checksum}  ${packPath}\n`);

  if (!omitAttestation) {
    await writeFile(join(root, attestationPath), JSON.stringify({ sbom: "present" }));
  }

  return {
    root,
    manifest: {
      schema_version: "0.1.0",
      pack_id: "evozeus-default-pack",
      version: "v0.1.0",
      source_review: {
        lab_path: "evozeus-factor-lab/reviewed/tool-use/evozeus-default-pack",
        reviewer: "maintainer",
        review_date: "2026-06-18"
      },
      artifact: {
        path: packPath,
        type: "pack"
      },
      checksum: {
        algorithm: "sha256",
        path: checksumPath
      },
      compatibility: {
        evozeus_protocol: ">=0.1.0",
        runtime: ">=0.1.0"
      },
      review_state: "promoted",
      attestation: attestationPath
    }
  };
}

test("accepts a release unit with reviewed source, artifact, checksum, and attestation", async () => {
  const { root, manifest } = await createReleaseFixture();

  assert.deepEqual(await validateReleaseManifest(manifest, { root }), []);
});

test("rejects a release unit with a checksum mismatch", async () => {
  const { root, manifest } = await createReleaseFixture({ checksumOverride: "b".repeat(64) });
  const issues = await validateReleaseManifest(manifest, { root });

  assert.match(issues.join("\n"), /checksum/i);
});

test("rejects a release unit without attestation", async () => {
  const { root, manifest } = await createReleaseFixture({ omitAttestation: true });
  const issues = await validateReleaseManifest(manifest, { root });

  assert.match(issues.join("\n"), /attestation/i);
});

test("rejects source reviews that do not come from lab reviewed assets", async () => {
  const { root, manifest } = await createReleaseFixture();
  const issues = await validateReleaseManifest({
    ...manifest,
    source_review: {
      ...manifest.source_review,
      lab_path: "evozeus-factor-lab/submissions/tool-use/evozeus-default-pack"
    }
  }, { root });

  assert.match(issues.join("\n"), /reviewed/i);
});
