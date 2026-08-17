/** CRA 5 `npm run build` crashes if terser-webpack-plugin 5.6.x loads with a circular `memoize`. */
const fs = require("fs");
const path = require("path");

const indexPath = path.join(__dirname, "../node_modules/terser-webpack-plugin/dist/index.js");
if (!fs.existsSync(indexPath)) process.exit(0);

let source = fs.readFileSync(indexPath, "utf8");
if (source.includes("bedforgeMemoize")) process.exit(0);

const needle = "const getTraceMapping = memoize(() => require(\"@jridgewell/trace-mapping\"));\nconst getSerializeJavascript = memoize(() => require(\"./serialize-javascript\"));";
const patch = `const bedforgeMemoize = typeof memoize === "function" ? memoize : (fn) => {
  let cached = false;
  let value;
  return () => {
    if (!cached) {
      value = fn();
      cached = true;
    }
    return value;
  };
};
const getTraceMapping = bedforgeMemoize(() => require("@jridgewell/trace-mapping"));
const getSerializeJavascript = bedforgeMemoize(() => require("./serialize-javascript"));`;

if (!source.includes(needle)) {
  console.warn("[bedforge] terser-webpack-plugin index.js did not match expected memoize lines — skip patch");
  process.exit(0);
}
fs.writeFileSync(indexPath, source.replace(needle, patch));
console.log("[bedforge] patched terser-webpack-plugin memoize fallback");
