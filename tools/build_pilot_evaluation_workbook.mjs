import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const experimentsDir = path.join(repoRoot, "experiments");
const pilotDir = path.join(experimentsDir, "pilot_evaluation");
const outputDir = path.join(repoRoot, "outputs", "019f6b33-7d0e-7e03-a47a-562b2e1b697e");
const outputPath = path.join(outputDir, "stm32n6_pilot_evaluation.xlsx");

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
    } else if ((character === "\r" || character === "\n") && !quoted) {
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
  return {
    headers,
    rows: data.map((values) => Object.fromEntries(headers.map((header, index) => [header, values[index] ?? ""]))),
  };
}

function csvEscape(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function serializeObjects(rows, headers) {
  return [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(",")),
  ].join("\n") + "\n";
}

const manifestText = await fs.readFile(path.join(pilotDir, "pilot_manifest.csv"), "utf8");
const manifest = parseCsv(manifestText);
const runsText = await fs.readFile(path.join(experimentsDir, "runs.csv"), "utf8");
const framesText = await fs.readFile(path.join(experimentsDir, "frames.csv"), "utf8");
const allRuns = parseCsv(runsText);
const allFrames = parseCsv(framesText);
const pilotRuns = allRuns.rows.filter((row) => row.stimulus.startsWith("PILOT-"));
const runToTrial = new Map(pilotRuns.map((row) => [row.run_id, row.stimulus.slice(0, 9)]));
const pilotFrames = allFrames.rows.filter((row) => runToTrial.has(row.run_id));

const pilotRunsHeaders = ["trial_id", ...allRuns.headers];
const pilotFramesHeaders = ["trial_id", ...allFrames.headers];
const pilotRunsText = serializeObjects(
  pilotRuns.map((row) => ({ trial_id: row.stimulus.slice(0, 9), ...row })),
  pilotRunsHeaders,
);
const pilotFramesText = serializeObjects(
  pilotFrames.map((row) => ({ trial_id: runToTrial.get(row.run_id), ...row })),
  pilotFramesHeaders,
);

const workbook = await Workbook.fromCSV(manifestText, { sheetName: "Trial Plan" });
await workbook.fromCSV(pilotRunsText, { sheetName: "Pilot Runs" });
await workbook.fromCSV(pilotFramesText, { sheetName: "Pilot Frames" });
const overview = workbook.worksheets.add("Overview");
const results = workbook.worksheets.add("Results");
const protocol = workbook.worksheets.add("Protocol");

const colors = {
  navy: "#102A43",
  blue: "#176B87",
  teal: "#2A9D8F",
  green: "#DDF3E4",
  greenText: "#166534",
  amber: "#FFF3CD",
  amberText: "#8A4B08",
  red: "#FDE2E2",
  redText: "#991B1B",
  paleBlue: "#EAF4F8",
  light: "#F7FAFC",
  line: "#D6E1E8",
  ink: "#243B53",
  muted: "#627D98",
  white: "#FFFFFF",
};

function title(sheet, address, text) {
  const range = sheet.getRange(address);
  range.merge();
  range.values = [[text]];
  range.format = {
    fill: colors.navy,
    font: { name: "Aptos Display", size: 18, bold: true, color: colors.white },
    verticalAlignment: "center",
  };
  range.format.rowHeight = 36;
}

function header(range) {
  range.format = {
    fill: colors.blue,
    font: { name: "Aptos", size: 10, bold: true, color: colors.white },
    verticalAlignment: "center",
    wrapText: true,
    borders: { preset: "outside", style: "thin", color: colors.navy },
  };
  range.format.rowHeight = 32;
}

function styleFlatSheet(sheet, usedRange, tableName) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getRange(usedRange);
  used.format.font = { name: "Aptos", size: 10, color: colors.ink };
  used.format.verticalAlignment = "center";
  used.format.borders = {
    insideHorizontal: { style: "thin", color: colors.line },
    bottom: { style: "thin", color: colors.line },
  };
  header(used.getRow(0));
  const table = sheet.tables.add(usedRange, true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
}

const trialPlan = workbook.worksheets.getItem("Trial Plan");
const pilotRunsSheet = workbook.worksheets.getItem("Pilot Runs");
const pilotFramesSheet = workbook.worksheets.getItem("Pilot Frames");
const trialLastRow = manifest.rows.length + 1;
const runsLastRow = Math.max(2, pilotRuns.length + 1);
const framesLastRow = Math.max(2, pilotFrames.length + 1);

trialPlan.getRange("R1:AJ1").values = [[
  "run_id", "captured_at", "run_result", "observed_frames",
  "expected_detected_frames", "hazard_frames", "unknown_frames",
  "max_expected_probability", "outcome", "dog_bark", "glass_breaking",
  "gunshot_gunfire", "siren", "speech", "thunderstorm", "unknown",
  "waiting", "dominant_active_prediction", "operator_note",
]];
trialPlan.getRange("R2").formulas = [["=IFERROR(INDEX('Pilot Runs'!$B$2:$B$100,MATCH($B2,'Pilot Runs'!$A$2:$A$100,0)),\"\")"]];
trialPlan.getRange(`R2:R${trialLastRow}`).fillDown();
trialPlan.getRange("S2").formulas = [["=IFERROR(INDEX('Pilot Runs'!$C$2:$C$100,MATCH($B2,'Pilot Runs'!$A$2:$A$100,0)),\"\")"]];
trialPlan.getRange(`S2:S${trialLastRow}`).fillDown();
trialPlan.getRange("T2").formulas = [["=IFERROR(INDEX('Pilot Runs'!$AB$2:$AB$100,MATCH($B2,'Pilot Runs'!$A$2:$A$100,0)),\"\")"]];
trialPlan.getRange(`T2:T${trialLastRow}`).fillDown();
trialPlan.getRange("U2").formulas = [["=COUNTIF('Pilot Frames'!$A$2:$A$5000,$B2)"]];
trialPlan.getRange(`U2:U${trialLastRow}`).fillDown();
trialPlan.getRange("V2").formulas = [["=COUNTIFS('Pilot Frames'!$A$2:$A$5000,$B2,'Pilot Frames'!$G$2:$G$5000,$D2)"]];
trialPlan.getRange(`V2:V${trialLastRow}`).fillDown();
trialPlan.getRange("W2").formulas = [["=AA2+AB2+AC2+AD2+AF2"]];
trialPlan.getRange(`W2:W${trialLastRow}`).fillDown();
trialPlan.getRange("X2").formulas = [["=AG2"]];
trialPlan.getRange(`X2:X${trialLastRow}`).fillDown();
trialPlan.getRange("Y2").formulas = [["=IF(U2=0,\"\",MAX(MAXIFS('Pilot Frames'!$Q$2:$Q$5000,'Pilot Frames'!$A$2:$A$5000,$B2,'Pilot Frames'!$P$2:$P$5000,$D2),MAXIFS('Pilot Frames'!$S$2:$S$5000,'Pilot Frames'!$A$2:$A$5000,$B2,'Pilot Frames'!$R$2:$R$5000,$D2),MAXIFS('Pilot Frames'!$U$2:$U$5000,'Pilot Frames'!$A$2:$A$5000,$B2,'Pilot Frames'!$T$2:$T$5000,$D2)))"]];
trialPlan.getRange(`Y2:Y${trialLastRow}`).fillDown();
trialPlan.getRange("Z2").formulas = [["=IF(R2=\"\",\"Pending\",IF(F2=\"positive\",IF(V2>0,\"Pass\",\"Miss\"),IF(W2=0,\"Pass\",\"False alert\")))"]];
trialPlan.getRange(`Z2:Z${trialLastRow}`).fillDown();

const decisionLabels = ["dog_bark", "glass_breaking", "gunshot_gunfire", "siren", "speech", "thunderstorm", "unknown", "waiting"];
for (let index = 0; index < decisionLabels.length; index += 1) {
  const column = String.fromCharCode("A".charCodeAt(0) + index);
  const excelColumn = index < 6 ? `A${column}` : index === 6 ? "AG" : "AH";
  trialPlan.getRange(`${excelColumn}2`).formulas = [[`=COUNTIFS('Pilot Frames'!$A$2:$A$5000,$B2,'Pilot Frames'!$G$2:$G$5000,${excelColumn}$1)`]];
  trialPlan.getRange(`${excelColumn}2:${excelColumn}${trialLastRow}`).fillDown();
}
trialPlan.getRange("AI2").formulas = [["=IF(SUM(AA2:AG2)=0,IF(AH2>0,\"waiting\",\"\"),INDEX($AA$1:$AG$1,1,MATCH(MAX(AA2:AG2),AA2:AG2,0)))"]];
trialPlan.getRange(`AI2:AI${trialLastRow}`).fillDown();

styleFlatSheet(trialPlan, `A1:AJ${trialLastRow}`, "PilotTrialPlan");
trialPlan.freezePanes.freezeColumns(2);
trialPlan.getRange("A:A").format.columnWidth = 10;
trialPlan.getRange("B:B").format.columnWidth = 14;
trialPlan.getRange("C:F").format.columnWidth = 18;
trialPlan.getRange("G:G").format.columnWidth = 46;
trialPlan.getRange("H:H").format.columnWidth = 58;
trialPlan.getRange("I:K").format.columnWidth = 18;
trialPlan.getRange("L:L").format.columnWidth = 20;
trialPlan.getRange("M:O").format.columnWidth = 13;
trialPlan.getRange("P:P").format.columnWidth = 12;
trialPlan.getRange("Q:Q").format.columnWidth = 45;
trialPlan.getRange("R:T").format.columnWidth = 22;
trialPlan.getRange("U:X").format.columnWidth = 16;
trialPlan.getRange("Y:Y").format.columnWidth = 20;
trialPlan.getRange("Z:Z").format.columnWidth = 15;
trialPlan.getRange("AA:AI").format.columnWidth = 18;
trialPlan.getRange("AJ:AJ").format.columnWidth = 36;
trialPlan.getRange(`Y2:Y${trialLastRow}`).format.numberFormat = "0.0%";
trialPlan.getRange(`S2:S${trialLastRow}`).format.numberFormat = "yyyy-mm-dd hh:mm:ss";
trialPlan.getRange(`Q2:Q${trialLastRow}`).format.wrapText = true;
trialPlan.getRange(`Z2:Z${trialLastRow}`).conditionalFormats.add("containsText", { text: "Pass", format: { fill: colors.green, font: { color: colors.greenText, bold: true } } });
trialPlan.getRange(`Z2:Z${trialLastRow}`).conditionalFormats.add("containsText", { text: "Pending", format: { fill: colors.amber, font: { color: colors.amberText } } });
trialPlan.getRange(`Z2:Z${trialLastRow}`).conditionalFormats.add("containsText", { text: "Miss", format: { fill: colors.red, font: { color: colors.redText, bold: true } } });
trialPlan.getRange(`Z2:Z${trialLastRow}`).conditionalFormats.add("containsText", { text: "False alert", format: { fill: colors.red, font: { color: colors.redText, bold: true } } });

styleFlatSheet(pilotRunsSheet, `A1:AE${runsLastRow}`, "PilotRunRecords");
pilotRunsSheet.getRange("A:B").format.columnWidth = 23;
pilotRunsSheet.getRange("C:C").format.columnWidth = 24;
pilotRunsSheet.getRange("D:K").format.columnWidth = 18;
pilotRunsSheet.getRange("L:N").format.columnWidth = 42;
pilotRunsSheet.getRange("O:AB").format.columnWidth = 15;
pilotRunsSheet.getRange("AC:AE").format.columnWidth = 42;

styleFlatSheet(pilotFramesSheet, `A1:V${framesLastRow}`, "PilotFrameRecords");
pilotFramesSheet.getRange("A:B").format.columnWidth = 23;
pilotFramesSheet.getRange("C:D").format.columnWidth = 16;
pilotFramesSheet.getRange("E:G").format.columnWidth = 21;
pilotFramesSheet.getRange("H:N").format.columnWidth = 16;
pilotFramesSheet.getRange("O:V").format.columnWidth = 19;
pilotFramesSheet.getRange(`O2:O${framesLastRow}`).format.numberFormat = "0.0%";
for (const column of ["Q", "S", "U"]) pilotFramesSheet.getRange(`${column}2:${column}${framesLastRow}`).format.numberFormat = "0.0%";

overview.showGridLines = false;
title(overview, "A1:H1", "STM32N6 physical pilot evaluation");
overview.getRange("A3:B10").values = [
  ["Experiment", "STM32N6-HAZARD6-PILOT-001"],
  ["Flashed firmware", "9a614d2"],
  ["Model", "YAMNet-256 Hazard-5 + Speech int8"],
  ["Planned trials", 35],
  ["Captured trials", null],
  ["Positive detection rate", null],
  ["OOD hazard-rejection rate", null],
  ["Pilot gate", null],
];
overview.getRange("B7").formulas = [[`=COUNTIF('Trial Plan'!$Z$2:$Z$${trialLastRow},"<>Pending")`]];
overview.getRange("B8").formulas = [[`=IFERROR(COUNTIFS('Trial Plan'!$F$2:$F$${trialLastRow},"positive",'Trial Plan'!$Z$2:$Z$${trialLastRow},"Pass")/COUNTIFS('Trial Plan'!$F$2:$F$${trialLastRow},"positive",'Trial Plan'!$Z$2:$Z$${trialLastRow},"<>Pending"),"")`]];
overview.getRange("B9").formulas = [[`=IFERROR(COUNTIFS('Trial Plan'!$F$2:$F$${trialLastRow},"ood",'Trial Plan'!$Z$2:$Z$${trialLastRow},"Pass")/COUNTIFS('Trial Plan'!$F$2:$F$${trialLastRow},"ood",'Trial Plan'!$Z$2:$Z$${trialLastRow},"<>Pending"),"")`]];
overview.getRange("B10").formulas = [["=IF(B7<35,\"Pending\",IF(COUNTIF('Results'!$G$4:$G$10,\"Review\")=0,\"Pass\",\"Review\"))"]];
overview.getRange("A3:A10").format = { fill: colors.paleBlue, font: { bold: true, color: colors.ink } };
overview.getRange("A3:B10").format.borders = { preset: "outside", style: "thin", color: colors.line };
overview.getRange("A3:A10").format.columnWidth = 28;
overview.getRange("B3:B10").format.columnWidth = 48;
overview.getRange("B8:B9").format.numberFormat = "0.0%";
overview.getRange("A12:H15").merge();
overview.getRange("A12:H15").values = [["Current status: the workbook is ready for capture. Thirty development positives and five development hard negatives are randomized with seed 120. Prior smoke-test clips are excluded. ESC-50 fold 5 and the FSD50K evaluation split remain untouched. Rebuild this workbook after the pilot to populate results and charts."]];
overview.getRange("A12:H15").format = { fill: colors.light, font: { color: colors.muted, italic: true }, wrapText: true, verticalAlignment: "top", borders: { preset: "outside", style: "thin", color: colors.line } };

results.showGridLines = false;
title(results, "A1:G1", "Pilot results and gates");
results.getRange("A3:G3").values = [["Expected class", "Planned", "Completed", "Passed", "Pass rate", "Mean peak expected probability", "Gate"]];
results.getRange("A4:A10").values = [["dog_bark"], ["glass_breaking"], ["gunshot_gunfire"], ["siren"], ["speech"], ["thunderstorm"], ["out_of_distribution"]];
for (let row = 4; row <= 10; row += 1) {
  results.getRange(`B${row}`).formulas = [[`=COUNTIF('Trial Plan'!$D$2:$D$${trialLastRow},A${row})`]];
  results.getRange(`C${row}`).formulas = [[`=COUNTIFS('Trial Plan'!$D$2:$D$${trialLastRow},A${row},'Trial Plan'!$Z$2:$Z$${trialLastRow},"<>Pending")`]];
  results.getRange(`D${row}`).formulas = [[`=COUNTIFS('Trial Plan'!$D$2:$D$${trialLastRow},A${row},'Trial Plan'!$Z$2:$Z$${trialLastRow},"Pass")`]];
  results.getRange(`E${row}`).formulas = [[`=IF(C${row}=0,"",D${row}/C${row})`]];
  results.getRange(`F${row}`).formulas = [[`=IF(A${row}="out_of_distribution","",IFERROR(AVERAGEIFS('Trial Plan'!$Y$2:$Y$${trialLastRow},'Trial Plan'!$D$2:$D$${trialLastRow},A${row},'Trial Plan'!$Z$2:$Z$${trialLastRow},"<>Pending"),""))`]];
  results.getRange(`G${row}`).formulas = [[`=IF(C${row}=0,"Pending",IF(E${row}>=0.8,"Pass","Review"))`]];
}
header(results.getRange("A3:G3"));
results.getRange("A3:G10").format.borders = { insideHorizontal: { style: "thin", color: colors.line }, bottom: { style: "thin", color: colors.line } };
results.getRange("A:A").format.columnWidth = 25;
results.getRange("B:D").format.columnWidth = 13;
results.getRange("E:F").format.columnWidth = 25;
results.getRange("G:G").format.columnWidth = 14;
results.getRange("E4:F10").format.numberFormat = "0.0%";
results.getRange("G4:G10").conditionalFormats.add("containsText", { text: "Pass", format: { fill: colors.green, font: { color: colors.greenText, bold: true } } });
results.getRange("G4:G10").conditionalFormats.add("containsText", { text: "Pending", format: { fill: colors.amber, font: { color: colors.amberText } } });
results.getRange("G4:G10").conditionalFormats.add("containsText", { text: "Review", format: { fill: colors.red, font: { color: colors.redText, bold: true } } });

results.getRange("A13:F13").values = [["Timing metric", "Mean", "Median", "Minimum", "Maximum", "95th percentile"]];
results.getRange("A14:A17").values = [["CPU load (%)"], ["Preprocessing (ms)"], ["Inference (ms)"], ["Postprocessing (ms)"]];
const timingColumns = ["I", "J", "K", "L"];
for (let row = 14; row <= 17; row += 1) {
  const sourceColumn = timingColumns[row - 14];
  results.getRange(`B${row}`).formulas = [[`=IF(COUNT('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000)=0,"",AVERAGE('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000))`]];
  results.getRange(`C${row}`).formulas = [[`=IF(COUNT('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000)=0,"",MEDIAN('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000))`]];
  results.getRange(`D${row}`).formulas = [[`=IF(COUNT('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000)=0,"",MIN('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000))`]];
  results.getRange(`E${row}`).formulas = [[`=IF(COUNT('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000)=0,"",MAX('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000))`]];
  results.getRange(`F${row}`).formulas = [[`=IF(COUNT('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000)=0,"",PERCENTILE.INC('Pilot Frames'!$${sourceColumn}$2:$${sourceColumn}$5000,0.95))`]];
}
header(results.getRange("A13:F13"));
results.getRange("A13:F17").format.borders = { insideHorizontal: { style: "thin", color: colors.line }, bottom: { style: "thin", color: colors.line } };
results.getRange("A13:A17").format.columnWidth = 25;
results.getRange("B13:F17").format.columnWidth = 17;
results.getRange("B14:F17").format.numberFormat = "0.000";

results.getRange("A20:I20").values = [["Actual / dominant active", "dog_bark", "glass_breaking", "gunshot_gunfire", "siren", "speech", "thunderstorm", "unknown", "waiting"]];
results.getRange("A21:A27").values = [["dog_bark"], ["glass_breaking"], ["gunshot_gunfire"], ["siren"], ["speech"], ["thunderstorm"], ["out_of_distribution"]];
for (let row = 21; row <= 27; row += 1) {
  for (let column = 2; column <= 9; column += 1) {
    const letter = String.fromCharCode(64 + column);
    results.getRange(`${letter}${row}`).formulas = [[`=COUNTIFS('Trial Plan'!$D$2:$D$${trialLastRow},$A${row},'Trial Plan'!$AI$2:$AI$${trialLastRow},${letter}$20)`]];
  }
}
header(results.getRange("A20:I20"));
results.getRange("A20:I27").format.borders = { insideHorizontal: { style: "thin", color: colors.line }, insideVertical: { style: "thin", color: colors.line }, bottom: { style: "thin", color: colors.line } };
results.getRange("A20:A27").format.columnWidth = 25;
results.getRange("B:I").format.columnWidth = 17;
results.getRange("B21:I27").conditionalFormats.add("colorScale", { colors: ["#FFFFFF", "#CFE8F3", "#2A9D8F"], thresholds: ["min", "50%", "max"] });

if (pilotRuns.length > 0) {
  results.getRange("K3:L3").values = [["Class", "Pass rate"]];
  results.getRange("K4:K10").formulas = [["=A4"], ["=A5"], ["=A6"], ["=A7"], ["=A8"], ["=A9"], ["=A10"]];
  results.getRange("L4:L10").formulas = [["=E4"], ["=E5"], ["=E6"], ["=E7"], ["=E8"], ["=E9"], ["=E10"]];
  const chart = results.charts.add("bar", results.getRange("K3:L10"));
  chart.title = "Pilot pass rate by class";
  chart.hasLegend = false;
  chart.xAxis = { axisType: "textAxis", textStyle: { fontSize: 9 } };
  chart.yAxis = { numberFormatCode: "0%", min: 0, max: 1 };
  chart.setPosition("K12", "R28");
}

protocol.showGridLines = false;
title(protocol, "A1:H1", "Controlled pilot protocol");
const protocolRows = [
  ["Purpose", "Development-only physical pilot used to decide whether the current firmware can be frozen for final evaluation."],
  ["Design", "35 randomized trials with seed 120: five clips for every model output and five OOD hard negatives."],
  ["Setup", "STM32N6570-DK; onboard microphone; speaker 30 cm away; Windows volume 50%; quiet room; unchanged position."],
  ["Automation", "Each 20 s capture contains a 3 s silent lead-in, asynchronous WAV playback, and trailing observation time. UART AED_CSV rows are preserved."],
  ["Positive outcome", "Pass when the expected model class becomes a confirmed decision at least once during its trial."],
  ["OOD outcome", "Pass when clapping, wooden knock, rain, crying baby, or clock tick produces no confirmed hazard decision. Speech is informational and safe."],
  ["Pilot gate", "At least four of five trials must pass for every model output and for the combined OOD group. A failure triggers review before firmware freeze."],
  ["Data isolation", "Prior smoke clips are excluded. ESC-50 fold 5 and the FSD50K evaluation split remain untouched until the final evaluation."],
  ["Interruption", "If the board resets, the speaker moves, volume changes, or another sound masks a clip, stop and report the trial order. Preserve the captured run and resume later."],
  ["Interpretation", "This small pilot supports engineering decisions; it is not the final accuracy estimate and must not be presented as safety certification."],
];
protocol.getRange(`A3:A${protocolRows.length + 2}`).values = protocolRows.map((row) => [row[0]]);
protocol.getRange(`B3:H${protocolRows.length + 2}`).merge(true);
protocol.getRange(`B3:B${protocolRows.length + 2}`).values = protocolRows.map((row) => [row[1]]);
protocol.getRange(`A3:A${protocolRows.length + 2}`).format = { fill: colors.paleBlue, font: { bold: true, color: colors.ink }, verticalAlignment: "top" };
protocol.getRange(`B3:H${protocolRows.length + 2}`).format = { wrapText: true, verticalAlignment: "top", font: { color: colors.ink } };
protocol.getRange(`A3:H${protocolRows.length + 2}`).format.borders = { insideHorizontal: { style: "thin", color: colors.line }, bottom: { style: "thin", color: colors.line } };
protocol.getRange("A:A").format.columnWidth = 22;
protocol.getRange("B:H").format.columnWidth = 18;
protocol.getRange(`A3:H${protocolRows.length + 2}`).format.rowHeight = 44;

await fs.mkdir(outputDir, { recursive: true });

const previews = [
  ["Overview", "A1:H15", "pilot_overview_preview.png"],
  ["Trial Plan", "A1:Z14", "pilot_plan_preview.png"],
  ["Pilot Runs", `A1:N${Math.min(runsLastRow, 12)}`, "pilot_runs_preview.png"],
  ["Pilot Frames", `A1:V${Math.min(framesLastRow, 12)}`, "pilot_frames_preview.png"],
  ["Results", "A1:I27", "pilot_results_preview.png"],
  ["Protocol", `A1:H${protocolRows.length + 2}`, "pilot_protocol_preview.png"],
];
for (const [sheetName, range, fileName] of previews) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, fileName), new Uint8Array(await preview.arrayBuffer()));
}

const keyInspect = await workbook.inspect({
  kind: "table",
  range: "Overview!A1:H15",
  include: "values,formulas",
  tableMaxRows: 15,
  tableMaxCols: 8,
});
const resultInspect = await workbook.inspect({
  kind: "table",
  range: "Results!A1:I27",
  include: "values,formulas",
  tableMaxRows: 27,
  tableMaxCols: 9,
});
const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "pilot workbook formula error scan",
});
console.log(keyInspect.ndjson);
console.log(resultInspect.ndjson);
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(`Saved ${outputPath}`);
