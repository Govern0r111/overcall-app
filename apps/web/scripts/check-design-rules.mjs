import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = fileURLToPath(new URL("../", import.meta.url));
const sourceRoot = path.join(appRoot, "src");
const errors = [];

async function visit(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await visit(filename);
      continue;
    }

    if (!/\.(?:css|ts|tsx|js|jsx)$/.test(entry.name)) continue;
    const source = await readFile(filename, "utf8");
    const relative = path.relative(appRoot, filename).replaceAll(path.sep, "/");

    if (relative !== "src/styles/tokens.css" && /#[\da-f]{3,8}\b/i.test(source)) {
      errors.push(`${relative}: hard-coded hex colors belong in styles/tokens.css`);
    }
    if (/bg-gradient-to-|(?:linear|radial|conic)-gradient\s*\(/i.test(source)) {
      errors.push(`${relative}: gradients are not allowed`);
    }
    if (/\bshadow-(?!none\b)[\w-]+/i.test(source)) {
      errors.push(`${relative}: use flat surfaces instead of shadow utilities`);
    }
    if (!/(?:features\/issues|pages\/(?:Issues|Logs|Overview)|components\/(?:Issue|Badges))/i.test(relative) &&
        /\b(?:text|bg|border|ring|fill|stroke)-(?:critical|warning)(?:\/\d+)?\b/i.test(source)) {
      errors.push(`${relative}: severity colors are reserved for flagged issues`);
    }
  }
}

await visit(sourceRoot);
for (const filename of ["index.html", "public/favicon.svg"]) {
  const source = await readFile(path.join(appRoot, filename), "utf8");
  if (filename !== "src/styles/tokens.css" && /#[\da-f]{3,8}\b/i.test(source)) {
    errors.push(`${filename}: hard-coded hex colors belong in src/styles/tokens.css`);
  }
  if (/bg-gradient-to-|(?:linear|radial|conic)-gradient\s*\(/i.test(source)) {
    errors.push(`${filename}: gradients are not allowed`);
  }
}
if (errors.length > 0) {
  console.error(errors.map((error) => `- ${error}`).join("\n"));
  process.exitCode = 1;
} else {
  console.log("Design rules passed.");
}
