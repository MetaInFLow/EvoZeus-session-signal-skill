import { createHash } from "node:crypto";
import { access, readFile } from "node:fs/promises";
import path from "node:path";

const PACK_ID = /^[a-z0-9]+(-[a-z0-9]+)*$/;
const VERSION = /^v[0-9]+\.[0-9]+\.[0-9]+(-[A-Za-z0-9.-]+)?$/;
const REVIEW_STATES = new Set(["promoted", "deprecated", "yanked"]);
const ARTIFACT_TYPES = new Set(["pack", "scanner-pack", "manifest-only"]);
const REVIEWED_LAB_PATH = /(?:^|\/)evozeus-factor-lab\/reviewed\//;

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasText(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function safeJoin(root, relativePath) {
  const normalized = path.normalize(relativePath);

  if (path.isAbsolute(normalized) || normalized.startsWith("..")) {
    return null;
  }

  return path.join(root, normalized);
}

async function fileExists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

export async function validateReleaseManifest(manifest, options = {}) {
  const root = options.root ?? process.cwd();
  const issues = [];

  if (!isPlainObject(manifest)) {
    return ["release manifest must be an object"];
  }

  if (!hasText(manifest.schema_version)) {
    issues.push("schema_version is required");
  }

  if (!PACK_ID.test(String(manifest.pack_id ?? ""))) {
    issues.push("pack_id must use lower kebab-case");
  }

  if (!VERSION.test(String(manifest.version ?? ""))) {
    issues.push("version must use semver tag format like v0.1.0");
  }

  if (manifest.git_tag !== manifest.version) {
    issues.push("git_tag must equal version");
  }

  validateSourceReview(manifest.source_review, issues);
  const artifactPath = validateArtifact(manifest.artifact, root, issues);
  const checksumPath = validateChecksumDeclaration(manifest.checksum, root, issues);
  validateCompatibility(manifest.compatibility, issues);
  validateRegistryPublicationPlan(manifest.registry_publication_plan, issues);
  validateSecurityReview(manifest.security_review, issues);

  if (!REVIEW_STATES.has(manifest.review_state)) {
    issues.push("review_state must be promoted, deprecated, or yanked");
  }

  await validateAttestation(manifest.attestation, root, issues);
  await validateSbom(manifest.sbom, root, issues);

  if (artifactPath && checksumPath) {
    await validateChecksumFile({ artifactPath, checksumPath, expectedArtifactPath: manifest.artifact.path, issues });
  }

  return issues;
}

function validateSourceReview(sourceReview, issues) {
  if (!isPlainObject(sourceReview)) {
    issues.push("source_review is required");
    return;
  }

  if (!hasText(sourceReview.lab_path)) {
    issues.push("source_review.lab_path is required");
  } else if (!REVIEWED_LAB_PATH.test(sourceReview.lab_path)) {
    issues.push("source_review.lab_path must point to evozeus-factor-lab/reviewed");
  }

  if (!hasText(sourceReview.reviewer)) {
    issues.push("source_review.reviewer is required");
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(sourceReview.review_date ?? ""))) {
    issues.push("source_review.review_date must use YYYY-MM-DD");
  }
}

function validateArtifact(artifact, root, issues) {
  if (!isPlainObject(artifact)) {
    issues.push("artifact is required");
    return null;
  }

  if (!hasText(artifact.path)) {
    issues.push("artifact.path is required");
    return null;
  }

  if (!ARTIFACT_TYPES.has(artifact.type)) {
    issues.push("artifact.type must be pack, scanner-pack, or manifest-only");
  }

  const artifactPath = safeJoin(root, artifact.path);

  if (!artifactPath) {
    issues.push("artifact.path must be a relative path inside the repo");
    return null;
  }

  return artifactPath;
}

function validateChecksumDeclaration(checksum, root, issues) {
  if (!isPlainObject(checksum)) {
    issues.push("checksum is required");
    return null;
  }

  if (checksum.algorithm !== "sha256") {
    issues.push("checksum.algorithm must be sha256");
  }

  if (!hasText(checksum.path)) {
    issues.push("checksum.path is required");
    return null;
  }

  const checksumPath = safeJoin(root, checksum.path);

  if (!checksumPath) {
    issues.push("checksum.path must be a relative path inside the repo");
    return null;
  }

  return checksumPath;
}

function validateCompatibility(compatibility, issues) {
  if (!isPlainObject(compatibility)) {
    issues.push("compatibility is required");
    return;
  }

  if (!hasText(compatibility.evozeus_protocol)) {
    issues.push("compatibility.evozeus_protocol is required");
  }

  if (!hasText(compatibility.runtime)) {
    issues.push("compatibility.runtime is required");
  }
}

function validateRegistryPublicationPlan(plan, issues) {
  if (!isPlainObject(plan)) {
    issues.push("registry_publication_plan is required");
    return;
  }

  if (plan.target_repo !== "MetaInFLow/EvoZeus") {
    issues.push("registry_publication_plan.target_repo must be MetaInFLow/EvoZeus");
  }

  if (!hasText(plan.pointer_path)) {
    issues.push("registry_publication_plan.pointer_path is required");
  } else if (!plan.pointer_path.startsWith("factors/registry/")) {
    issues.push("registry_publication_plan.pointer_path must stay under factors/registry/");
  }

  if (plan.requires_pr !== true) {
    issues.push("registry_publication_plan.requires_pr must be true");
  }
}

function validateSecurityReview(review, issues) {
  if (!isPlainObject(review)) {
    issues.push("security_review is required");
    return;
  }

  if (!hasText(review.reviewer)) {
    issues.push("security_review.reviewer is required");
  }

  if (!/^\d{4}-\d{2}-\d{2}$/.test(String(review.review_date ?? ""))) {
    issues.push("security_review.review_date must use YYYY-MM-DD");
  }
}

async function validateAttestation(attestation, root, issues) {
  if (!hasText(attestation)) {
    issues.push("attestation path is required");
    return;
  }

  const attestationPath = safeJoin(root, attestation);

  if (!attestationPath) {
    issues.push("attestation path must be relative and inside the repo");
    return;
  }

  if (!(await fileExists(attestationPath))) {
    issues.push(`attestation file does not exist: ${attestation}`);
  }
}

async function validateSbom(sbom, root, issues) {
  if (!hasText(sbom)) {
    issues.push("sbom path is required");
    return;
  }

  const sbomPath = safeJoin(root, sbom);

  if (!sbomPath) {
    issues.push("sbom path must be relative and inside the repo");
    return;
  }

  if (!(await fileExists(sbomPath))) {
    issues.push(`sbom file does not exist: ${sbom}`);
  }
}

async function validateChecksumFile({ artifactPath, checksumPath, expectedArtifactPath, issues }) {
  if (!(await fileExists(artifactPath))) {
    issues.push("artifact path does not exist");
    return;
  }

  if (!(await fileExists(checksumPath))) {
    issues.push("checksum file does not exist");
    return;
  }

  const [artifact, checksumContent] = await Promise.all([
    readFile(artifactPath),
    readFile(checksumPath, "utf8")
  ]);
  const [expected, recordedPath] = checksumContent.trim().split(/\s+/);
  const actual = createHash("sha256").update(artifact).digest("hex");

  if (expected !== actual) {
    issues.push("checksum mismatch for artifact");
  }

  if (recordedPath !== expectedArtifactPath) {
    issues.push("checksum file artifact path must match manifest artifact.path");
  }
}

async function main() {
  const file = process.argv[2];

  if (!file) {
    console.error("Usage: node scripts/validate-release-manifest.mjs <manifest.json>");
    process.exitCode = 2;
    return;
  }

  const manifest = JSON.parse(await readFile(file, "utf8"));
  const issues = await validateReleaseManifest(manifest);

  if (issues.length > 0) {
    console.error(issues.join("\n"));
    process.exitCode = 1;
    return;
  }

  console.log("release manifest is valid");
}

if (import.meta.url === `file://${process.argv[1]}`) {
  await main();
}
