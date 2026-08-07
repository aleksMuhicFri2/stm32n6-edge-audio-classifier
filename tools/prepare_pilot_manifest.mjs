import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const workspaceRoot = path.resolve(repoRoot, "..");
const outputDir = path.join(repoRoot, "experiments", "pilot_evaluation");
const seed = 120;
const samplesPerClass = 5;
const modelClasses = [
  "dog_bark",
  "glass_breaking",
  "gunshot_gunfire",
  "siren",
  "speech",
  "thunderstorm",
];
const oodCategories = [
  "clapping",
  "door_wood_knock",
  "rain",
  "crying_baby",
  "clock_tick",
];
const excludedSmokeFiles = new Set([
  "dog_bark__fsd50k__dev__266603__0041__r0.wav",
  "glass_breaking__fsd50k__dev__233586__0040__r0.wav",
  "gunshot_gunfire__fsd50k__dev__128981__0003__r0.wav",
  "gunshot_gunfire__fsd50k__dev__197322__0024__r0.wav",
  "gunshot_gunfire__fsd50k__dev__353093__0042__r0.wav",
  "gunshot_gunfire__fsd50k__dev__35800__0044__r0.wav",
  "gunshot_gunfire__fsd50k__dev__36815__0045__r0.wav",
  "siren__fsd50k__dev__62878__0019__r0.wav",
  "thunderstorm__esc50__fold_4__125071__0001__r0.wav",
  "thunderstorm__esc50__fold_4__161519__0005__r0.wav",
  "thunderstorm__fsd50k__dev__124587__0008__r0.wav",
]);

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;
  const pushField = () => {
    row.push(field);
    field = "";
  };
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    if (character === '"') {
      if (quoted && text[index + 1] === '"') {
        field += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === "," && !quoted) {
      pushField();
    } else if ((character === "\n" || character === "\r") && !quoted) {
      if (character === "\r" && text[index + 1] === "\n") index += 1;
      pushField();
      if (row.some((value) => value !== "")) rows.push(row);
      row = [];
    } else {
      field += character;
    }
  }
  if (field !== "" || row.length > 0) {
    pushField();
    rows.push(row);
  }
  const [headers, ...data] = rows;
  return data.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""])));
}

function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function serializeCsv(rows, headers) {
  return [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")),
  ].join("\n") + "\n";
}

function mulberry32(initialSeed) {
  let state = initialSeed >>> 0;
  return () => {
    state += 0x6D2B79F5;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

function shuffled(values, random) {
  const result = [...values];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const swap = Math.floor(random() * (index + 1));
    [result[index], result[swap]] = [result[swap], result[index]];
  }
  return result;
}

function toManifestPath(absolutePath) {
  return path.relative(repoRoot, absolutePath).replaceAll("\\", "/");
}

async function sha256(filePath) {
  const data = await fs.readFile(filePath);
  return crypto.createHash("sha256").update(data).digest("hex");
}

const validationPath = path.join(repoRoot, "ml", "data", "hazard5v3s", "hazard6_validation.csv");
const provenancePath = path.join(repoRoot, "ml", "data", "hazard5v3s", "hazard6_training_provenance.csv");
const escMetadataPath = path.join(workspaceRoot, "ml-workspace", "datasets", "ESC-50", "meta", "esc50.csv");
const hazardAudioDir = path.join(workspaceRoot, "ml-workspace", "datasets", "hazard5v3s", "audio");
const escAudioDir = path.join(workspaceRoot, "ml-workspace", "datasets", "ESC-50", "audio");

const validation = parseCsv(await fs.readFile(validationPath, "utf8"));
const provenance = parseCsv(await fs.readFile(provenancePath, "utf8"));
const provenanceByFile = new Map(provenance.map((row) => [row.filename, row]));
const escMetadata = parseCsv(await fs.readFile(escMetadataPath, "utf8"));
const random = mulberry32(seed);
const selectedByClass = new Map();

for (const className of modelClasses) {
  const candidates = validation.filter((row) =>
    row.category === className &&
    !excludedSmokeFiles.has(row.filename) &&
    !row.filename.includes("fold_5"));
  if (candidates.length < samplesPerClass) {
    throw new Error(`Not enough development candidates for ${className}`);
  }
  selectedByClass.set(className, shuffled(candidates, random).slice(0, samplesPerClass));
}

const selectedOod = [];
for (const category of oodCategories) {
  const candidates = escMetadata.filter((row) => row.fold === "4" && row.category === category);
  if (candidates.length === 0) throw new Error(`No ESC-50 fold-4 OOD candidate for ${category}`);
  selectedOod.push(shuffled(candidates, random)[0]);
}

const orderedStimuli = [];
let previousExpected = "";
for (let round = 0; round < samplesPerClass; round += 1) {
  let roundClasses = shuffled(modelClasses, random);
  if (roundClasses[0] === previousExpected) {
    [roundClasses[0], roundClasses[1]] = [roundClasses[1], roundClasses[0]];
  }
  const roundRows = roundClasses.map((className) => ({
    kind: "positive",
    round: round + 1,
    className,
    row: selectedByClass.get(className)[round],
  }));
  const insertAt = Math.floor(random() * (roundRows.length + 1));
  roundRows.splice(insertAt, 0, {
    kind: "ood",
    round: round + 1,
    className: "out_of_distribution",
    row: selectedOod[round],
  });
  orderedStimuli.push(...roundRows);
  previousExpected = roundRows.at(-1).className;
}

const manifestRows = [];
for (let index = 0; index < orderedStimuli.length; index += 1) {
  const stimulus = orderedStimuli[index];
  const trialId = `PILOT-${String(index + 1).padStart(3, "0")}`;
  if (stimulus.kind === "positive") {
    const source = provenanceByFile.get(stimulus.row.filename);
    if (!source) throw new Error(`Missing provenance for ${stimulus.row.filename}`);
    const audioPath = path.join(hazardAudioDir, stimulus.row.filename);
    manifestRows.push({
      trial_order: index + 1,
      trial_id: trialId,
      round: stimulus.round,
      expected_class: stimulus.className,
      true_category: stimulus.className,
      test_type: "positive",
      stimulus_file: stimulus.row.filename,
      stimulus_path: toManifestPath(audioPath),
      source_dataset: source.source_dataset,
      source_partition: source.source_partition,
      source_id: source.source_id,
      sha256: await sha256(audioPath),
      distance_cm: 30,
      volume_percent: 50,
      capture_duration_s: 20,
      status: "pending",
      notes: "Development-only pilot; prior smoke-test clips excluded.",
    });
  } else {
    const audioPath = path.join(escAudioDir, stimulus.row.filename);
    manifestRows.push({
      trial_order: index + 1,
      trial_id: trialId,
      round: stimulus.round,
      expected_class: "out_of_distribution",
      true_category: stimulus.row.category,
      test_type: "ood",
      stimulus_file: stimulus.row.filename,
      stimulus_path: toManifestPath(audioPath),
      source_dataset: "ESC-50",
      source_partition: "fold_4",
      source_id: stimulus.row.filename.replace(/\.wav$/i, ""),
      sha256: await sha256(audioPath),
      distance_cm: 30,
      volume_percent: 50,
      capture_duration_s: 20,
      status: "pending",
      notes: `OOD hard negative: ${stimulus.row.category}.`,
    });
  }
}

const headers = [
  "trial_order", "trial_id", "round", "expected_class", "true_category",
  "test_type", "stimulus_file", "stimulus_path", "source_dataset",
  "source_partition", "source_id", "sha256", "distance_cm",
  "volume_percent", "capture_duration_s", "status", "notes",
];
await fs.mkdir(outputDir, { recursive: true });
await fs.writeFile(path.join(outputDir, "pilot_manifest.csv"), serializeCsv(manifestRows, headers));
await fs.writeFile(path.join(outputDir, "pilot_manifest.json"), JSON.stringify({
  experiment_id: "STM32N6-HAZARD6-PILOT-001",
  selection_seed: seed,
  firmware_commit: "9a614d2",
  model_name: "YAMNet-256 Hazard-5 + Speech int8",
  model_classes: modelClasses,
  samples_per_model_class: samplesPerClass,
  ood_categories: oodCategories,
  trial_count: manifestRows.length,
  excluded_prior_smoke_files: [...excludedSmokeFiles].sort(),
  reserved_test_policy: "ESC-50 fold 5 and FSD50K evaluation remain untouched.",
  manifest_sha256: crypto.createHash("sha256").update(serializeCsv(manifestRows, headers)).digest("hex"),
}, null, 2) + "\n");

console.log(`Prepared ${manifestRows.length} pilot trials in ${outputDir}`);
