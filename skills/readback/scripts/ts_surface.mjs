#!/usr/bin/env node
// Prints the public surface of TypeScript or JavaScript entry files: every export with its full type, one per line.
// usage: node ts_surface.mjs <entry file>...
import { createRequire } from "node:module";
import { relative, resolve } from "node:path";

const loadTypeScript = () => {
  try {
    return createRequire(resolve(process.cwd(), "package.json"))("typescript");
  } catch {
    return createRequire(resolve(process.env.READBACK_TYPESCRIPT_DIR ?? ".", "package.json"))("typescript");
  }
};

const ts = loadTypeScript();
const entryPaths = process.argv.slice(2).map((entryPath) => resolve(entryPath));
const program = ts.createProgram(entryPaths, {
  allowJs: true,
  strict: true,
  noEmit: true,
  skipLibCheck: true,
  allowImportingTsExtensions: true,
  target: ts.ScriptTarget.ES2022,
  module: ts.ModuleKind.ESNext,
  moduleResolution: ts.ModuleResolutionKind.Bundler,
});
const checker = program.getTypeChecker();
const fullTypeFlags = ts.TypeFormatFlags.NoTruncation | ts.TypeFormatFlags.InTypeAlias | ts.TypeFormatFlags.WriteArrowStyleSignature;

const typeText = (type) => checker.typeToString(type, undefined, fullTypeFlags);
const declarationOf = (symbol) => symbol.valueDeclaration ?? symbol.declarations?.[0];
const typeOfSymbol = (symbol) => checker.getTypeOfSymbolAtLocation(symbol, declarationOf(symbol));
const isHiddenMember = (symbol) =>
  (symbol.declarations ?? []).some((declaration) =>
    (ts.getCombinedModifierFlags(declaration) & (ts.ModifierFlags.Private | ts.ModifierFlags.Protected)) !== 0
    || (declaration.name && ts.isPrivateIdentifier(declaration.name)));
const optionalMark = (symbol) => ((symbol.flags & ts.SymbolFlags.Optional) !== 0 ? "?" : "");

const describeMembers = (ownerLabel, type, separator) =>
  checker.getPropertiesOfType(type)
    .filter((member) => !isHiddenMember(member) && "prototype" !== member.name)
    .map((member) => `${ownerLabel}${separator}${member.name}${optionalMark(member)}: ${typeText(typeOfSymbol(member))}`);

const describeExport = (exportName, exportedSymbol) => {
  const symbol = (exportedSymbol.flags & ts.SymbolFlags.Alias) !== 0 ? checker.getAliasedSymbol(exportedSymbol) : exportedSymbol;
  const lines = [];
  if ((symbol.flags & ts.SymbolFlags.TypeAlias) !== 0) {
    lines.push(`type ${exportName} = ${typeText(checker.getDeclaredTypeOfSymbol(symbol))}`);
  }
  if ((symbol.flags & ts.SymbolFlags.Interface) !== 0) {
    const declaredType = checker.getDeclaredTypeOfSymbol(symbol);
    lines.push(`interface ${exportName}`, ...describeMembers(`interface ${exportName}`, declaredType, "."));
  }
  if ((symbol.flags & ts.SymbolFlags.Class) !== 0) {
    const constructorType = typeOfSymbol(symbol);
    const constructSignatures = constructorType.getConstructSignatures().map((signature) => checker.signatureToString(signature));
    lines.push(`class ${exportName} new ${constructSignatures.join(" | ")}`);
    lines.push(...describeMembers(`class ${exportName}`, checker.getDeclaredTypeOfSymbol(symbol), "#"));
    lines.push(...describeMembers(`class ${exportName}`, constructorType, "."));
  } else if ((symbol.flags & (ts.SymbolFlags.Function | ts.SymbolFlags.Variable | ts.SymbolFlags.Enum)) !== 0) {
    lines.push(`value ${exportName}: ${typeText(typeOfSymbol(symbol))}`);
  }
  return 0 === lines.length ? [`export ${exportName}`] : lines;
};

// Type errors belong to the compile check; only a file that cannot be parsed stops the surface.
const diagnostics = program.getSyntacticDiagnostics();
if (0 < diagnostics.length) {
  for (const diagnostic of diagnostics.slice(0, 5)) {
    console.error(ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"));
  }
  process.exit(2);
}
for (const entryPath of entryPaths) {
  const sourceFile = program.getSourceFile(entryPath);
  const moduleSymbol = sourceFile && checker.getSymbolAtLocation(sourceFile);
  if (!moduleSymbol) {
    console.error(`no module at ${entryPath}`);
    process.exit(2);
  }
  const entryLabel = relative(process.cwd(), entryPath);
  const exportedSymbols = [...checker.getExportsOfModule(moduleSymbol)].sort((left, right) => left.name.localeCompare(right.name));
  for (const exportedSymbol of exportedSymbols) {
    for (const surfaceLine of describeExport(exportedSymbol.name, exportedSymbol)) {
      console.log(`${entryLabel}: ${surfaceLine}`);
    }
  }
}
