import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repo = path.resolve(process.argv[2] ?? ".");
const results = path.join(repo, "experiments", "results", "hazard_candidate_selection");
const preliminary = path.join(results, "provisional_final5_dev");
const expanded = path.join(results, "expanded_dev");
const data = path.join(repo, "ml", "data", "hazard_candidates");
const outputDir = path.join(repo, "outputs", "hazard_candidate_selection");
const archivePath = path.join(results, "hazard_candidate_selection.xlsx");
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(results, { recursive: true });

function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

const summaryCsv = await fs.readFile(path.join(data, "hazard_candidate_summary.csv"), "utf8");
const metricsCsv = await fs.readFile(path.join(preliminary, "candidate_metrics_preliminary.csv"), "utf8");
const similarityCsv = await fs.readFile(path.join(preliminary, "class_similarity_cosine.csv"), "utf8");
const confusionCsv = await fs.readFile(path.join(preliminary, "candidate_confusion_validation.csv"), "utf8");
const expandedMetricsCsv = await fs.readFile(path.join(expanded, "candidate_metrics_preliminary.csv"), "utf8");

const workbook = await Workbook.fromCSV(summaryCsv, { sheetName: "Candidate Audit" });
await workbook.fromCSV(metricsCsv, { sheetName: "Prelim Metrics" });
await workbook.fromCSV(similarityCsv, { sheetName: "Similarity" });
await workbook.fromCSV(confusionCsv, { sheetName: "Confusion" });
await workbook.fromCSV(expandedMetricsCsv, { sheetName: "Expanded 7" });
const overview = workbook.worksheets.add("Overview");
const scoring = workbook.worksheets.add("Scoring");
const trials = workbook.worksheets.add("Playback Trials");
const protocol = workbook.worksheets.add("Protocol");

function coerceNumericRange(sheet, address) {
  const range = sheet.getRange(address);
  range.values = range.values.map((row) => row.map((value) => {
    if (value === null || value === "") return null;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : value;
  }));
}

const navy = "#10243E";
const blue = "#1E5AA8";
const cyan = "#2A9DCC";
const paleBlue = "#EAF2FA";
const paleGreen = "#E8F5E9";
const paleAmber = "#FFF4D6";
const paleRed = "#FCE8E6";
const gray = "#64748B";
const lightGray = "#E2E8F0";
const white = "#FFFFFF";

function styleTitle(sheet, range, title) {
  sheet.getRange(range).merge();
  sheet.getRange(range).values = [[title]];
  sheet.getRange(range).format = {
    fill: navy,
    font: { bold: true, color: white, size: 18 },
    verticalAlignment: "center",
  };
  sheet.getRange(range).format.rowHeight = 34;
}

function styleHeader(range) {
  range.format = {
    fill: blue,
    font: { bold: true, color: white },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: navy },
  };
  range.format.rowHeight = 28;
}

function styleDataSheet(sheet, usedAddress) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  styleHeader(sheet.getRange(usedAddress.split(":")[0].replace(/\d+$/, "1") + ":" + usedAddress.split(":")[1].replace(/\d+$/, "1")));
  const used = sheet.getRange(usedAddress);
  used.format.font = { name: "Aptos", size: 10 };
  used.format.autofitColumns();
  used.format.autofitRows();
}

// Candidate source audit.
styleDataSheet(workbook.worksheets.getItem("Candidate Audit"), "A1:K9");
const audit = workbook.worksheets.getItem("Candidate Audit");
coerceNumericRange(audit, "C2:J9");
audit.getRange("A1:K9").format.wrapText = true;
audit.getRange("A1:K1").format.rowHeight = 44;
audit.getRange("A:A").format.columnWidth = 20;
audit.getRange("B:B").format.columnWidth = 22;
audit.getRange("C:I").format.columnWidth = 13;
audit.getRange("J:J").format.columnWidth = 15;
audit.getRange("K:K").format.columnWidth = 21;
audit.getRange("C2:J9").format.numberFormat = "#,##0";
audit.tables.add("A1:K9", true, "CandidateAuditTable").style = "TableStyleMedium2";
audit.getRange("K2:K9").conditionalFormats.add("containsText", {
  text: "missing",
  format: { fill: paleRed, font: { color: "#9C1C1C", bold: true } },
});

// Provisional final-five validation metrics.
const metrics = workbook.worksheets.getItem("Prelim Metrics");
coerceNumericRange(metrics, "B2:F6");
styleDataSheet(metrics, "A1:F6");
metrics.getRange("A:A").format.columnWidth = 22;
metrics.getRange("B:D").format.columnWidth = 14;
metrics.getRange("E:F").format.columnWidth = 18;
metrics.getRange("A1:F1").format.rowHeight = 38;
metrics.getRange("B2:D6").format.numberFormat = "0.0%";
metrics.getRange("B:D").conditionalFormats.add("colorScale", {
  colors: ["#F8696B", "#FFEB84", "#63BE7B"],
  thresholds: ["min", "50%", "max"],
});
metrics.tables.add("A1:F6", true, "PrelimMetricsTable").style = "TableStyleMedium2";

const expandedMetrics = workbook.worksheets.getItem("Expanded 7");
coerceNumericRange(expandedMetrics, "B2:F8");
styleDataSheet(expandedMetrics, "A1:F8");
expandedMetrics.getRange("A:A").format.columnWidth = 22;
expandedMetrics.getRange("B:D").format.columnWidth = 14;
expandedMetrics.getRange("E:F").format.columnWidth = 18;
expandedMetrics.getRange("B2:D8").format.numberFormat = "0.0%";
expandedMetrics.getRange("B2:D8").conditionalFormats.add("colorScale", {
  colors: ["#F8696B", "#FFEB84", "#63BE7B"],
  thresholds: ["min", "50%", "max"],
});
expandedMetrics.tables.add("A1:F8", true, "ExpandedMetricsTable").style = "TableStyleMedium2";

// Similarity and confusion matrices.
const similarity = workbook.worksheets.getItem("Similarity");
coerceNumericRange(similarity, "B2:F6");
styleDataSheet(similarity, "A1:F6");
similarity.getRange("A:A").format.columnWidth = 22;
similarity.getRange("B:F").format.columnWidth = 17;
similarity.getRange("B2:F6").format.numberFormat = "0.00";
similarity.getRange("B2:F6").conditionalFormats.add("colorScale", {
  colors: ["#E8F5E9", "#FFE082", "#EF5350"],
  thresholds: ["min", "50%", "max"],
});
similarity.getRange("A2:A6").format.font = { bold: true, color: navy };

const confusion = workbook.worksheets.getItem("Confusion");
coerceNumericRange(confusion, "B2:F6");
styleDataSheet(confusion, "A1:F6");
confusion.getRange("A2:A6").values = [
  ["chainsaw"],
  ["gunshot_gunfire"],
  ["screaming"],
  ["siren"],
  ["thunderstorm"],
];
confusion.getRange("A:A").format.columnWidth = 22;
confusion.getRange("B:F").format.columnWidth = 17;
confusion.getRange("B2:F6").format.numberFormat = "0";
confusion.getRange("B2:F6").conditionalFormats.add("colorScale", {
  colors: [white, "#9CC2E5", blue],
  thresholds: ["min", "50%", "max"],
});
confusion.getRange("A2:A6").format = { fill: paleBlue, font: { bold: true, color: navy } };

// Protocol and visible assumptions.
styleTitle(protocol, "A1:F1", "Hazard Candidate Selection Protocol");
protocol.showGridLines = false;
protocol.getRange("A3:B8").values = [
  ["Scoring component", "Weight"],
  ["Board playback recall", 0.35],
  ["Inter-danger separation", 0.25],
  ["Hard-negative resistance", 0.20],
  ["Offline test performance", 0.10],
  ["Confidence/latency stability", 0.10],
];
styleHeader(protocol.getRange("A3:B3"));
protocol.getRange("B4:B8").format.numberFormat = "0%";
protocol.getRange("A10:B14").values = [
  ["Selection gate", "Target"],
  ["Minimum offline recall", 0.85],
  ["Maximum pairwise confusion", 0.15],
  ["Minimum board playback recall", 0.80],
  ["Maximum hard-negative trigger rate", 0.10],
];
styleHeader(protocol.getRange("A10:B10"));
protocol.getRange("B11:B14").format.numberFormat = "0%";
protocol.getRange("D3:F8").values = [
  ["Source", "Purpose", "URL"],
  ["ESC-50", "Source-separated public baseline", "https://github.com/karolpiczak/esc-50"],
  ["FSD50K", "Screaming/gunshot and additional diversity", "https://zenodo.org/records/4060432"],
  ["YAMNet", "Pretrained embedding backbone", "https://github.com/tensorflow/models/tree/master/research/audioset/yamnet"],
  ["Project catalog", "Auditable source-item mapping", "ml/data/hazard_candidates/hazard_candidate_catalog.csv"],
  ["Hard negatives", "Confuser test plan", "ml/data/hazard_candidates/hard_negative_plan.csv"],
];
styleHeader(protocol.getRange("D3:F3"));
protocol.getRange("A16:F23").values = [
  ["Workflow step", "Owner", "Status", "Input", "Output", "Stop/go condition"],
  ["Freeze baseline", "Codex", "Complete", "Validated dashboard", "Hashes and source commit", "Rollback is reproducible"],
  ["Audit candidate data", "Codex", "Complete", "ESC-50 plus FSD50K metadata", "Catalog and counts", "Sources are explicit"],
  ["Preliminary embedding study", "Codex", "Complete", "Available ESC-50 candidates", "Metrics and plots", "Reserved test untouched"],
  ["Acquire development audio", "Codex", "Complete", "Official FSD50K development archive", "40,966 verified WAV files", "All six MD5 hashes pass"],
  ["Seven-candidate study", "Codex", "Complete", "ESC-50 and FSD50K development", "Full similarity and confusion", "Weak candidates identified"],
  ["Five-class ablation", "Codex", "Complete", "Provisional class set", "97.16% validation accuracy", "Every offline recall gate passes"],
  ["Board playback pilot", "User + Codex", "Pending", "Deployed five-class firmware", "UART trial log", "Playback and hard-negative gates pass"],
];
styleHeader(protocol.getRange("A16:F16"));
protocol.getRange("C17:C23").conditionalFormats.add("containsText", {
  text: "Complete",
  format: { fill: paleGreen, font: { color: "#1B5E20", bold: true } },
});
protocol.getRange("C17:C23").conditionalFormats.add("containsText", {
  text: "Blocked",
  format: { fill: paleAmber, font: { color: "#8A4B00", bold: true } },
});
protocol.getRange("A:F").format.columnWidth = 24;
protocol.getRange("D:D").format.columnWidth = 31;
protocol.getRange("E:F").format.columnWidth = 33;
protocol.getRange("A3:F23").format.wrapText = true;
protocol.getRange("A3:F23").format.autofitRows();

// Formula-driven scoring sheet. User-entered fields remain blank until measured.
styleTitle(scoring, "A1:H1", "Candidate Selection Scorecard");
scoring.showGridLines = false;
scoring.freezePanes.freezeRows(3);
scoring.getRange("A3:H3").values = [[
  "Candidate",
  "Acoustic family",
  "Board playback recall",
  "Inter-danger separation",
  "Hard-negative resistance",
  "Offline test performance",
  "Confidence/latency stability",
  "Final weighted score",
]];
styleHeader(scoring.getRange("A3:H3"));
const candidates = [
  ["siren", "modulated_tonal"],
  ["chainsaw", "continuous_mechanical"],
  ["glass_breaking", "brittle_transient"],
  ["screaming", "voiced_distress"],
  ["gunshot_gunfire", "explosive_impulse"],
  ["fire_alarm", "periodic_alarm"],
  ["thunderstorm", "environmental_rumble"],
  ["crackling_fire", "stochastic_crackle"],
];
scoring.getRange("A4:B11").values = candidates;
for (let row = 4; row <= 11; row += 1) {
  scoring.getRange(`H${row}`).formulas = [[
    `=IF(COUNT(C${row}:G${row})<5,"",C${row}*'Protocol'!$B$4+D${row}*'Protocol'!$B$5+E${row}*'Protocol'!$B$6+F${row}*'Protocol'!$B$7+G${row}*'Protocol'!$B$8)`,
  ]];
}
const separationFormulas = {
  4: "=1-MAX('Similarity'!$B$5:$D$5,'Similarity'!$F$5)",
  5: "=1-MAX('Similarity'!$C$2:$F$2)",
  7: "=1-MAX('Similarity'!$B$4:$C$4,'Similarity'!$E$4:$F$4)",
  8: "=1-MAX('Similarity'!$B$3,'Similarity'!$D$3:$F$3)",
  10: "=1-MAX('Similarity'!$B$6:$E$6)",
};
for (const [row, formula] of Object.entries(separationFormulas)) {
  scoring.getRange(`D${row}`).formulas = [[formula]];
}
const offlineRecallFormulas = {
  4: "='Prelim Metrics'!$C$5",
  5: "='Prelim Metrics'!$C$2",
  7: "='Prelim Metrics'!$C$4",
  8: "='Prelim Metrics'!$C$3",
  10: "='Prelim Metrics'!$C$6",
};
for (const [row, formula] of Object.entries(offlineRecallFormulas)) {
  scoring.getRange(`F${row}`).formulas = [[formula]];
}
scoring.getRange("C4:H11").format.numberFormat = "0.0%";
scoring.getRange("C4:C11").format.fill = paleAmber;
scoring.getRange("E4:G11").format.fill = paleAmber;
scoring.getRange("D4:D11").format.fill = paleBlue;
scoring.getRange("F4:F11").format.fill = paleBlue;
scoring.getRange("H4:H11").format.fill = paleGreen;
scoring.getRange("C4:G11").dataValidation = {
  rule: { type: "decimal", operator: "between", formula1: 0, formula2: 1 },
};
scoring.getRange("A:A").format.columnWidth = 22;
scoring.getRange("B:B").format.columnWidth = 25;
scoring.getRange("C:H").format.columnWidth = 20;
scoring.getRange("A3:H11").format.wrapText = true;
scoring.getRange("A13:H15").merge();
scoring.getRange("A13:H15").values = [[
  "Amber cells are future physical measurements. Blue cells are formula-derived from the current final-five similarity and validation-recall evidence. The final score remains blank until every component has been measured; unknown values are never replaced with zero.",
]];
scoring.getRange("A13:H15").format = { fill: paleAmber, font: { color: "#6B4600" }, wrapText: true };

// Empty, structured physical playback trial sheet.
styleTitle(trials, "A1:N1", "Physical Playback Trial Log");
trials.showGridLines = false;
trials.freezePanes.freezeRows(3);
const trialHeaders = [
  "trial_id", "recorded_at", "candidate_class", "clip_id", "expected_class",
  "distance_m", "noise_condition", "speaker_volume_pct", "detected",
  "predicted_class", "peak_confidence", "latency_ms", "alert_triggered", "notes",
];
trials.getRange("A3:N3").values = [trialHeaders];
styleHeader(trials.getRange("A3:N3"));
trials.getRange("A4:N103").format.borders = {
  insideHorizontal: { style: "thin", color: lightGray },
};
trials.getRange("C4:C103").dataValidation = {
  rule: { type: "list", values: candidates.map((row) => row[0]) },
};
trials.getRange("G4:G103").dataValidation = {
  rule: { type: "list", values: ["quiet", "speech", "music", "room_noise", "hard_negative"] },
};
trials.getRange("I4:I103").dataValidation = { rule: { type: "list", values: [0, 1] } };
trials.getRange("M4:M103").dataValidation = { rule: { type: "list", values: [0, 1] } };
trials.getRange("F4:F103").dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0.1, formula2: 5 } };
trials.getRange("H4:H103").dataValidation = { rule: { type: "whole", operator: "between", formula1: 1, formula2: 100 } };
trials.getRange("K4:K103").dataValidation = { rule: { type: "decimal", operator: "between", formula1: 0, formula2: 1 } };
trials.getRange("K4:K103").format.numberFormat = "0.0%";
trials.getRange("B4:B103").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
trials.getRange("A:N").format.columnWidth = 17;
trials.getRange("D:E").format.columnWidth = 23;
trials.getRange("N:N").format.columnWidth = 34;
trials.getRange("A3:N103").format.wrapText = true;
trials.tables.add("A3:N103", true, "PlaybackTrialsTable").style = "TableStyleMedium2";

// Executive overview with formulas and one meaningful chart.
styleTitle(overview, "A1:H1", "STM32N6 Hazard Candidate Selection");
overview.showGridLines = false;
overview.getRange("A3:B8").values = [
  ["Current status", "Hazard-5 flashed; normal boot validation pending"],
  ["Candidate pool", null],
  ["Target final hazards", 5],
  ["Catalog records", null],
  ["Local candidate audio files", null],
  ["Reserved-test clips used", 0],
];
overview.getRange("B4").formulas = [["=COUNTA('Candidate Audit'!$A$2:$A$9)"]];
overview.getRange("B6").formulas = [["=SUM('Candidate Audit'!$J$2:$J$9)"]];
overview.getRange("B7").formulas = [["=SUM('Candidate Audit'!$I$2:$I$9)"]];
overview.getRange("A3:A8").format = { fill: paleBlue, font: { bold: true, color: navy } };
overview.getRange("B3:B8").format = { fill: white, font: { color: navy } };
overview.getRange("A3:B8").format.borders = { preset: "outside", style: "thin", color: lightGray };
overview.getRange("D3:H8").merge();
overview.getRange("D3:H8").values = [[
  "Deployment finding: the five-class int8 YAMNet-256 reached 95.60% development-validation clip accuracy with no clip-level quantization loss. Neural-ART uses 148,417 B weights and 147,456 B activations. Application and weights passed board read-back verification; reserved test data remains untouched.",
]];
overview.getRange("D3:H8").format = { fill: paleAmber, font: { color: "#6B4600", bold: true }, wrapText: true, verticalAlignment: "center" };
overview.getRange("A10:B16").values = [
  ["Candidate", "Validation recall"],
  [null, null],
  [null, null],
  [null, null],
  [null, null],
  [null, null],
  ["Macro average", null],
];
for (let row = 11; row <= 15; row += 1) {
  const sourceRow = row - 9;
  overview.getRange(`A${row}:B${row}`).formulas = [[
    `='Prelim Metrics'!A${sourceRow}`,
    `='Prelim Metrics'!C${sourceRow}`,
  ]];
}
overview.getRange("B16").formulas = [["=AVERAGE(B11:B15)"]];
styleHeader(overview.getRange("A10:B10"));
overview.getRange("B11:B16").format.numberFormat = "0.0%";
const recallChart = overview.charts.add("bar", overview.getRange("A10:B15"));
recallChart.title = "Provisional final-five validation recall";
recallChart.hasLegend = false;
recallChart.xAxis = { axisType: "textAxis" };
recallChart.yAxis = { numberFormatCode: "0%", min: 0, max: 1 };
recallChart.setPosition("D10", "H24");
overview.getRange("A18:B23").values = [
  ["Next blocking input", "Why it is needed"],
  ["Normal boot", "Confirms the signed Hazard-5 application starts through the existing FSBL"],
  ["LCD and UART smoke check", "Confirms the model/UI class order and continuous inference"],
  ["Fixed playback setup", "Measures speaker-to-board reliability and hard negatives"],
  ["User action now", "Return BOOT1 to normal boot and power-cycle or reset"],
  ["After boot", "Report the LCD state; prompted playback follows only after smoke validation"],
];
styleHeader(overview.getRange("A18:B18"));
overview.getRange("A:B").format.columnWidth = 27;
overview.getRange("B:B").format.columnWidth = 48;
overview.getRange("D:H").format.columnWidth = 16;
overview.getRange("A3:H23").format.wrapText = true;
overview.getRange("A3:H23").format.autofitRows();

const exportBlob = await SpreadsheetFile.exportXlsx(workbook);
const outputPath = path.join(outputDir, "hazard_candidate_selection.xlsx");
await exportBlob.save(outputPath);
await exportBlob.save(archivePath);

const previewSheets = ["Overview", "Candidate Audit", "Prelim Metrics", "Expanded 7", "Similarity", "Confusion", "Scoring", "Playback Trials", "Protocol"];
for (const sheetName of previewSheets) {
  const rendered = await workbook.render({ sheetName, autoCrop: "all", scale: 1, format: "png" });
  const safeName = sheetName.toLowerCase().replaceAll(" ", "_");
  await fs.writeFile(path.join(outputDir, `${safeName}.png`), new Uint8Array(await rendered.arrayBuffer()));
}

const keyCheck = await workbook.inspect({
  kind: "table",
  range: "Overview!A1:H23",
  include: "values,formulas",
  tableMaxRows: 24,
  tableMaxCols: 8,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});

// Append idempotent experiment records through an artifact-tool CSV workbook.
const projectLogPath = path.join(repo, "experiments", "project_log.csv");
const projectLogCsv = await fs.readFile(projectLogPath, "utf8");
const projectLogBook = await Workbook.fromCSV(projectLogCsv, { sheetName: "Project Log" });
const projectLogSheet = projectLogBook.worksheets.getItem("Project Log");
const existingRows = projectLogSheet.getUsedRange().values;
const existingIds = new Set(existingRows.slice(1).map((row) => row[0]));
const newLogRows = [
  ["LOG-056", "2026-08-01T17:20:00+02:00", "baseline", "Froze the validated useful-ten dashboard before hazard specialization", "Recorded exact source commit firmware and model hashes flash addresses memory allocations display buffers and physical validation state", "experiments/results/hazard_baseline/baseline_summary.json", "", "The baseline remains restorable and its reserved artifacts are not overwritten"],
  ["LOG-057", "2026-08-01T17:35:00+02:00", "dataset", "Audited eight danger candidates against official ESC-50 and FSD50K metadata", "Cataloged 3542 source records with split roles and provenance; 200 ESC-50 audio files are local; Screaming and Gunshot require FSD50K audio; Fire alarm has no matching audited leaf class", "ml/data/hazard_candidates/hazard_candidate_catalog.csv and hazard_candidate_summary.csv", "", "FSD50K evaluation remains reserved and no large audio archive was downloaded"],
  ["LOG-058", "2026-08-01T17:45:00+02:00", "evaluation", "Ran the preliminary YAMNet-256 embedding separability study", "Five locally available candidates reached 95.0 percent validation accuracy on 40 ESC-50 fold-4 clips; siren and thunderstorm recall were 100 percent; reserved fold 5 was untouched", "experiments/results/hazard_candidate_selection/preliminary_esc50", "", "Crackling fire and thunderstorm were the closest centroid pair at cosine similarity 0.9369"],
  ["LOG-059", "2026-08-01T18:00:00+02:00", "reporting", "Prepared the hazard selection workbook acquisition script and physical playback protocol", "Created a formula-driven eight-sheet workbook with source audit metrics similarity confusion scoring and trial log; prepared verified resumable FSD50K acquisition and fixed playback procedures", "experiments/results/hazard_candidate_selection/hazard_candidate_selection.xlsx", "", "The next required decision is whether to download and extract the 17.15 GiB FSD50K development archive"],
  ["LOG-060", "2026-08-01T22:10:00+02:00", "dataset", "Acquired and extracted the official FSD50K development audio archive", "Downloaded 17.15 GiB across six resumable parts; every official MD5 matched; extraction produced exactly 40966 WAV files; evaluation audio remains unrequested and reserved", "ml/acquire_fsd50k.ps1", "", "The development archive adds 2507 locally available candidate recordings while preserving the final external test split"],
  ["LOG-061", "2026-08-01T22:20:00+02:00", "evaluation", "Ran the expanded seven-candidate YAMNet-256 embedding study", "Used 1093 training and 269 validation clips from ESC-50 and FSD50K development; excluded three recordings mapped to multiple danger candidates; achieved 87.73 percent validation accuracy", "experiments/results/hazard_candidate_selection/expanded_dev", "", "Crackling fire and glass breaking were the weakest well-supported candidates; reserved test usage remained zero"],
  ["LOG-062", "2026-08-01T22:25:00+02:00", "selection", "Selected a provisional five-class danger taxonomy from offline evidence", "Siren chainsaw gunshot or gunfire screaming and thunderstorm achieved 97.16 percent validation accuracy and 97.02 percent macro recall after five-class ablation; every offline recall gate passed", "experiments/results/hazard_candidate_selection/provisional_final5_dev", "", "Selection remains provisional until physical playback and hard-negative gates pass"],
  ["LOG-063", "2026-08-01T22:25:00+02:00", "training", "Trained and quantized the provisional five-class YAMNet-256 model", "Balanced 960 training entries through deterministic development-only oversampling; early stopping completed 30 epochs; float and int8 models both reached 95.60 percent clip accuracy on 182 development-validation clips", "experiments/results/hazard5_yamnet256_development", "", "The 184000-byte int8 model has SHA256 14d9a98267a16de742beab3166ff42d00cb8bda3992c373c1333028473ceade1 and reserved test usage is zero"],
  ["LOG-064", "2026-08-01T22:35:00+02:00", "deployment", "Generated built signed and flashed the Hazard-5 STM32N6 application", "ST Edge AI 4.0.1 generated 148417 bytes of Neural-ART weights and 147456 bytes of activations; clean BM build had zero errors; signed payload matched at offset 0x400; application and weights passed read-back verification", "experiments/results/hazard5_yamnet256_development/deployment_summary.json", "", "FSBL and OTP were untouched; normal-boot LCD and UART validation awaits returning BOOT1 to its run position"],
];
for (const row of newLogRows) {
  if (!existingIds.has(row[0])) existingRows.push(row);
}
projectLogSheet.getRangeByIndexes(0, 0, existingRows.length, existingRows[0].length).values = existingRows;
const projectLogCheck = await projectLogBook.inspect({
  kind: "table",
  range: `Project Log!A${Math.max(1, existingRows.length - 4)}:H${existingRows.length}`,
  include: "values",
  tableMaxRows: 6,
  tableMaxCols: 8,
});
const missingLogRows = newLogRows.filter((row) => !existingIds.has(row[0]));
const serializedLog = projectLogCsv.replace(/\s*$/, "\n")
  + missingLogRows.map((row) => row.map(csvEscape).join(",")).join("\n")
  + (missingLogRows.length ? "\n" : "");
await fs.writeFile(projectLogPath, serializedLog, "utf8");

await fs.rm(`${outputPath}.inspect.ndjson`, { force: true });
await fs.rm(`${archivePath}.inspect.ndjson`, { force: true });
console.log(keyCheck.ndjson);
console.log(formulaErrors.ndjson);
console.log(projectLogCheck.ndjson);
console.log(JSON.stringify({ outputPath, archivePath, previewSheets }, null, 2));
