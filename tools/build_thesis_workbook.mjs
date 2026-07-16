import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const experimentsDir = path.join(repoRoot, "experiments");
const outputDir = path.join(
  repoRoot,
  "outputs",
  "019f6b33-7d0e-7e03-a47a-562b2e1b697e",
);
const outputPath = path.join(outputDir, "stm32n6_thesis_experiment_log.xlsx");
const previewPaths = {
  dashboard: path.join(outputDir, "dashboard_preview.png"),
  runs: path.join(outputDir, "runs_preview.png"),
  frames: path.join(outputDir, "frames_preview.png"),
  projectLog: path.join(outputDir, "project_log_preview.png"),
  protocol: path.join(outputDir, "protocol_preview.png"),
};

const workbook = Workbook.create();

function parseCsv(text) {
  const rows = [];
  let row = [];
  let field = "";
  let quoted = false;

  const pushField = () => {
    if (field === "") {
      row.push(null);
    } else if (/^-?(?:\d+\.?\d*|\.\d+)$/.test(field)) {
      row.push(Number(field));
    } else if (/^(true|false)$/i.test(field)) {
      row.push(field.toLowerCase() === "true");
    } else {
      row.push(field);
    }
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
      rows.push(row);
      row = [];
    } else {
      field += character;
    }
  }
  if (field !== "" || row.length > 0) {
    pushField();
    rows.push(row);
  }
  return rows;
}

for (const [fileName, sheetName] of [
  ["runs.csv", "Runs"],
  ["frames.csv", "Frames"],
  ["project_log.csv", "Project Log"],
]) {
  const csvText = await fs.readFile(path.join(experimentsDir, fileName), "utf8");
  const values = parseCsv(csvText);
  const sheet = workbook.worksheets.add(sheetName);
  sheet.getRangeByIndexes(0, 0, values.length, values[0].length).values = values;
}

const dashboard = workbook.worksheets.add("Dashboard");
const protocol = workbook.worksheets.add("Protocol");

const colors = {
  navy: "#16324F",
  teal: "#2A9D8F",
  paleTeal: "#E5F4F1",
  orange: "#F4A261",
  paleOrange: "#FFF1E6",
  ink: "#243447",
  muted: "#64748B",
  light: "#F8FAFC",
  line: "#D7E0E8",
  white: "#FFFFFF",
};

function styleDataSheet(sheet, tableName) {
  sheet.showGridLines = false;
  sheet.freezePanes.freezeRows(1);
  const used = sheet.getUsedRange();
  used.format.font = { name: "Aptos", size: 10, color: colors.ink };
  used.format.verticalAlignment = "center";
  used.format.borders = {
    insideHorizontal: { style: "thin", color: colors.line },
    bottom: { style: "thin", color: colors.line },
  };
  const header = used.getRow(0);
  header.format = {
    fill: colors.navy,
    font: { name: "Aptos", size: 10, bold: true, color: colors.white },
    wrapText: true,
    verticalAlignment: "center",
  };
  header.format.rowHeight = 34;
  const table = sheet.tables.add(used, true, tableName);
  table.style = "TableStyleMedium2";
  table.showFilterButton = true;
  return used;
}

const runs = workbook.worksheets.getItem("Runs");
const frames = workbook.worksheets.getItem("Frames");
const projectLog = workbook.worksheets.getItem("Project Log");

styleDataSheet(runs, "ExperimentRuns");
styleDataSheet(frames, "FrameObservations");
styleDataSheet(projectLog, "EngineeringLog");

const runsLastRow = runs.getUsedRange().values.length;
const framesLastRow = frames.getUsedRange().values.length;
const projectLogLastRow = projectLog.getUsedRange().values.length;

runs.getRange(`A1:A${runsLastRow}`).format.columnWidth = 24;
runs.getRange(`B1:B${runsLastRow}`).format.columnWidth = 24;
runs.getRange("C:D").format.columnWidth = 13;
runs.getRange("E:I").format.columnWidth = 20;
runs.getRange("J:J").format.columnWidth = 12;
runs.getRange("K:M").format.columnWidth = 22;
runs.getRange("N:Z").format.columnWidth = 14;
runs.getRange("AA:AA").format.columnWidth = 18;
runs.getRange("AB:AB").format.columnWidth = 38;
runs.getRange("AC:AC").format.columnWidth = 55;
runs.getRange("AD:AD").format.columnWidth = 22;
runs.getRange("B2:B1000").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
runs.getRange("N2:Z1000").format.horizontalAlignment = "right";
runs.getRange("W2:W1000").format.numberFormat = "0.00";
runs.getRange("X2:Z1000").format.numberFormat = "0.000";
runs.getRange("AC2:AC1000").format.wrapText = true;

frames.getRange(`A1:A${framesLastRow}`).format.columnWidth = 24;
frames.getRange("B:C").format.columnWidth = 16;
frames.getRange("D:F").format.columnWidth = 22;
frames.getRange("G:G").format.columnWidth = 12;
frames.getRange("H:K").format.columnWidth = 16;
frames.getRange("L:L").format.columnWidth = 28;
frames.getRange("B2:B5000").format.numberFormat = "0.000";
frames.getRange("H2:H5000").format.numberFormat = "0.00";
frames.getRange("I2:K5000").format.numberFormat = "0.000";
frames.getRange("G2:G5000").conditionalFormats.addCustom("=G2=TRUE", {
  fill: "#DCFCE7",
  font: { color: "#166534", bold: true },
});
frames.getRange("G2:G5000").conditionalFormats.addCustom("=G2=FALSE", {
  fill: "#FEE2E2",
  font: { color: "#991B1B" },
});

projectLog.getRange(`A1:A${projectLogLastRow}`).format.columnWidth = 14;
projectLog.getRange(`B1:B${projectLogLastRow}`).format.columnWidth = 24;
projectLog.getRange(`C1:C${projectLogLastRow}`).format.columnWidth = 18;
projectLog.getRange("D:E").format.columnWidth = 42;
projectLog.getRange("F:F").format.columnWidth = 55;
projectLog.getRange("G:G").format.columnWidth = 14;
projectLog.getRange("H:H").format.columnWidth = 55;
projectLog.getRange("B2:B1000").format.numberFormat = "yyyy-mm-dd hh:mm:ss";
projectLog.getRange("D2:H1000").format.wrapText = true;

dashboard.showGridLines = false;
dashboard.getRange("A1:N2").merge();
dashboard.getRange("A1").values = [["STM32N6 Edge Audio Classifier — Experimental Dashboard"]];
dashboard.getRange("A1").values = [["STM32N6 Edge Audio Classifier - Experimental Dashboard"]];
dashboard.getRange("A1:N2").format = {
  fill: colors.navy,
  font: { name: "Aptos Display", size: 20, bold: true, color: colors.white },
  horizontalAlignment: "left",
  verticalAlignment: "center",
};
dashboard.getRange("A3:N3").merge();
dashboard.getRange("A3").values = [["Formula-driven summary of committed run and frame evidence. Preliminary data is retained but clearly separated from controlled thesis measurements."]];
dashboard.getRange("A3:N3").format = {
  fill: colors.light,
  font: { name: "Aptos", size: 10, italic: true, color: colors.muted },
  wrapText: true,
  verticalAlignment: "center",
};
dashboard.getRange("A3:N3").format.rowHeight = 32;

dashboard.getRange("A5:B5").values = [["KPI", "Value"]];
dashboard.getRange("A6:A11").values = [
  ["Recorded runs"],
  ["Controlled runs"],
  ["Mean CPU load (%)"],
  ["Mean preprocessing (ms)"],
  ["Mean NPU inference (ms)"],
  ["Observed dog detections"],
];
dashboard.getRange("B6:B11").formulas = [
  ["=COUNTA('Runs'!$A$2:$A$1000)"],
  ["=COUNTIF('Runs'!$C$2:$C$1000,\"controlled\")"],
  ["=AVERAGE('Runs'!$W$2:$W$1000)"],
  ["=AVERAGE('Runs'!$X$2:$X$1000)"],
  ["=AVERAGE('Runs'!$Y$2:$Y$1000)"],
  ["=COUNTIF('Frames'!$F$2:$F$5000,\"dog\")"],
];
dashboard.getRange("A5:B5").format = {
  fill: colors.teal,
  font: { bold: true, color: colors.white },
};
dashboard.getRange("A6:A11").format = {
  fill: colors.paleTeal,
  font: { color: colors.ink },
};
dashboard.getRange("B6:B11").format = {
  fill: colors.white,
  font: { bold: true, color: colors.navy, size: 12 },
  horizontalAlignment: "right",
};
dashboard.getRange("B8:B10").format.numberFormat = "0.000";
dashboard.getRange("A5:B11").format.borders = {
  preset: "outside",
  style: "thin",
  color: colors.line,
};

dashboard.getRange("D5:E5").values = [["Pipeline stage", "Mean time (ms)"]];
dashboard.getRange("D6:D9").values = [
  ["Preprocessing"],
  ["Neural-ART inference"],
  ["Postprocessing"],
  ["Measured compute total"],
];
dashboard.getRange("E6:E9").formulas = [
  ["=AVERAGE('Runs'!$X$2:$X$1000)"],
  ["=AVERAGE('Runs'!$Y$2:$Y$1000)"],
  ["=AVERAGE('Runs'!$Z$2:$Z$1000)"],
  ["=SUM(E6:E8)"],
];
dashboard.getRange("D5:E5").format = {
  fill: colors.orange,
  font: { bold: true, color: colors.white },
};
dashboard.getRange("D6:E9").format.borders = {
  preset: "inside",
  style: "thin",
  color: colors.line,
};
dashboard.getRange("E6:E9").format.numberFormat = "0.000";

const timingChart = dashboard.charts.add("bar", dashboard.getRange("D5:E9"));
timingChart.title = "Mean embedded compute time by stage (ms)";
timingChart.hasLegend = false;
timingChart.yAxis = { numberFormatCode: "0.000" };
timingChart.setPosition("G5", "N16");

const classes = [
  "dog",
  "chainsaw",
  "clock_tick",
  "crackling_fire",
  "crying_baby",
  "helicopter",
  "rain",
  "rooster",
  "sea_waves",
  "sneezing",
  "unknown",
  "no_output",
];
dashboard.getRange("A14:B14").values = [["Predicted class", "Recorded events"]];
dashboard.getRange(`A15:A${14 + classes.length}`).values = classes.map((value) => [value]);
dashboard.getRange(`B15:B${14 + classes.length}`).formulas = classes.map((_, index) => [
  `=COUNTIF('Frames'!$F$2:$F$5000,A${15 + index})`,
]);
dashboard.getRange("A14:B14").format = {
  fill: colors.teal,
  font: { bold: true, color: colors.white },
};
dashboard.getRange(`B15:B${14 + classes.length}`).format.numberFormat = "0";

const detectionChart = dashboard.charts.add(
  "bar",
  dashboard.getRange(`A14:B${14 + classes.length}`),
);
detectionChart.title = "Prediction events currently recorded";
detectionChart.hasLegend = false;
detectionChart.yAxis = { numberFormatCode: "0" };
detectionChart.setPosition("D14", "N31");

dashboard.getRange("A33:N35").merge();
dashboard.getRange("A33").values = [[
  "Interpret preliminary results cautiously: the first playback trials did not control volume, distance, source file, or onset time. Controlled experiments will replace these engineering observations in final thesis statistics.",
]];
dashboard.getRange("A33:N35").format = {
  fill: colors.paleOrange,
  font: { color: "#8A4B08", italic: true },
  wrapText: true,
  verticalAlignment: "center",
  borders: { preset: "outside", style: "thin", color: colors.orange },
};
dashboard.getRange("A1:A35").format.columnWidth = 28;
dashboard.getRange("B1:B35").format.columnWidth = 16;
dashboard.getRange("C1:C35").format.columnWidth = 3;
dashboard.getRange("D1:D35").format.columnWidth = 23;
dashboard.getRange("E1:E35").format.columnWidth = 17;
dashboard.getRange("F1:F35").format.columnWidth = 3;
dashboard.getRange("G1:N35").format.columnWidth = 13;
dashboard.freezePanes.freezeRows(3);

protocol.showGridLines = false;
protocol.getRange("A1:F2").merge();
protocol.getRange("A1").values = [["Experimental protocol and data dictionary"]];
protocol.getRange("A1:F2").format = {
  fill: colors.navy,
  font: { name: "Aptos Display", size: 18, bold: true, color: colors.white },
  verticalAlignment: "center",
};
protocol.getRange("A4:B4").values = [["Evidence level", "Meaning"]];
protocol.getRange("A5:B7").values = [
  ["controlled", "Complete raw UART plus required stimulus and setup metadata."],
  ["preliminary", "Useful engineering evidence with uncontrolled or reconstructed elements."],
  ["derived", "Formula or calculation based on committed source measurements."],
];
protocol.getRange("A9:B9").values = [["Required field", "Rule for final thesis tests"]];
protocol.getRange("A10:B18").values = [
  ["Stimulus", "Use a fixed audio file and record its hash."],
  ["Expected class", "Use the exact model label or out_of_distribution."],
  ["Distance", "Measure source-to-microphone distance in centimetres."],
  ["Volume", "Record the playback-device setting and keep it fixed."],
  ["Duration", "Use the same clip and observation duration across platforms."],
  ["Repeats", "Use at least 30 clips per evaluated class when practical."],
  ["Raw evidence", "Save the complete UART or program output without editing."],
  ["Performance", "Report mean, median, standard deviation, min, max, and p95."],
  ["Accuracy", "Report precision, recall, F1, confusion matrix, false positives, and unknown rate."],
];
protocol.getRange("D4:F4").values = [["Dataset", "Granularity", "Purpose"]];
protocol.getRange("D5:F8").values = [
  ["Project Log", "one engineering event", "Chronology, decisions, failures, and evidence"],
  ["Runs", "one experiment", "Conditions and aggregate results"],
  ["Frames", "one processed frame", "Predictions, timings, and confusion analysis"],
  ["raw/*.txt", "one UART capture", "Immutable primary measurement evidence"],
];
for (const range of ["A4:B4", "A9:B9", "D4:F4"]) {
  protocol.getRange(range).format = {
    fill: colors.teal,
    font: { bold: true, color: colors.white },
  };
}
protocol.getRange("A5:B7").format.borders = { preset: "inside", style: "thin", color: colors.line };
protocol.getRange("A10:B18").format.borders = { preset: "inside", style: "thin", color: colors.line };
protocol.getRange("D5:F8").format.borders = { preset: "inside", style: "thin", color: colors.line };
protocol.getRange("A1:F18").format.font = { name: "Aptos", size: 10, color: colors.ink };
protocol.getRange("A1:A18").format.columnWidth = 22;
protocol.getRange("B1:B18").format.columnWidth = 62;
protocol.getRange("C1:C18").format.columnWidth = 4;
protocol.getRange("D1:D18").format.columnWidth = 20;
protocol.getRange("E1:E18").format.columnWidth = 22;
protocol.getRange("F1:F18").format.columnWidth = 44;
protocol.getRange("B5:B18").format.wrapText = true;
protocol.getRange("F5:F8").format.wrapText = true;
protocol.getRange("A1:F2").format.font = {
  name: "Aptos Display",
  size: 18,
  bold: true,
  color: colors.white,
};

await fs.mkdir(outputDir, { recursive: true });

const dashboardCheck = await workbook.inspect({
  kind: "table",
  sheetId: "Dashboard",
  range: "A1:N35",
  include: "values,formulas",
  tableMaxRows: 35,
  tableMaxCols: 14,
  maxChars: 9000,
});
const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
const drawings = await workbook.inspect({
  kind: "drawing",
  sheetId: "Dashboard",
  maxChars: 3000,
});

for (const [key, sheetName, range] of [
  ["dashboard", "Dashboard", "A1:N35"],
  ["runs", "Runs", `A1:AD${runsLastRow}`],
  ["frames", "Frames", `A1:L${framesLastRow}`],
  ["projectLog", "Project Log", `A1:H${projectLogLastRow}`],
  ["protocol", "Protocol", "A1:F18"],
]) {
  const preview = await workbook.render({ sheetName, range, scale: 1.25, format: "png" });
  await fs.writeFile(previewPaths[key], new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);

console.log("DASHBOARD_INSPECT");
console.log(dashboardCheck.ndjson);
console.log("FORMULA_ERRORS");
console.log(formulaErrors.ndjson);
console.log("DRAWINGS");
console.log(drawings.ndjson);
console.log(`OUTPUT=${outputPath}`);
console.log(`PREVIEWS=${Object.values(previewPaths).join(";")}`);
