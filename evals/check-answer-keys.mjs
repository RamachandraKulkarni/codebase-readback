#!/usr/bin/env node
// Checks that every answer key still points at exactly one line of its example, and uses groups the signs catalog has.
// usage: node evals/check-answer-keys.mjs
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const examplesDir = join(repoRoot, "examples");
const signsCatalogPath = join(repoRoot, "skills", "readback", "references", "signs.md");
const allowedActions = new Set(["fix", "report", "leave", "count"]);

const groupsInSignsCatalog = () =>
  new Set(
    readFileSync(signsCatalogPath, "utf8")
      .split("\n")
      .filter((line) => line.startsWith("## "))
      .map((heading) => heading.slice("## ".length).trim()),
  );

const lineNumbersContaining = (fileText, match) =>
  fileText
    .split("\n")
    .map((line, index) => (line.includes(match) ? index + 1 : 0))
    .filter((lineNumber) => 0 < lineNumber);

// Returns the entry's line number, or the reason the entry is wrong
const resolveEntry = (exampleDir, entry, knownGroups) => {
  const filePath = join(exampleDir, entry.file);
  if (!existsSync(filePath)) return { problem: `no file ${entry.file}` };
  if (!knownGroups.has(entry.group)) return { problem: `signs.md has no group "${entry.group}"` };
  if (!allowedActions.has(entry.action)) return { problem: `unknown action "${entry.action}"` };
  const lineNumbers = lineNumbersContaining(readFileSync(filePath, "utf8"), entry.match);
  if (1 !== lineNumbers.length) return { problem: `"${entry.match}" is on ${lineNumbers.length} lines, expected 1` };
  return { lineNumber: lineNumbers[0] };
};

const knownGroups = groupsInSignsCatalog();
let problemCount = 0;
for (const exampleName of readdirSync(examplesDir).sort()) {
  const exampleDir = join(examplesDir, exampleName);
  const answerKeyPath = join(exampleDir, "answer-key.json");
  if (!existsSync(answerKeyPath)) continue;
  const { entries } = JSON.parse(readFileSync(answerKeyPath, "utf8"));
  console.log(`${exampleName}: ${entries.length} entries`);
  for (const entry of entries) {
    const { lineNumber, problem } = resolveEntry(exampleDir, entry, knownGroups);
    if (undefined !== problem) {
      problemCount += 1;
      console.log(`  PROBLEM ${entry.file}: ${problem}`);
      continue;
    }
    console.log(`  ${entry.action.padEnd(6)} ${entry.group.padEnd(13)} ${entry.file.split("/").pop()}:${lineNumber}`);
  }
}
console.log(0 === problemCount ? "All answer keys resolve." : `${problemCount} problems.`);
process.exit(0 === problemCount ? 0 : 1);
