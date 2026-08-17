// craco.config.js
// Load graceful-fs against the native fs object before any realpath.native
// guards. webpack-dev-server requires graceful-fs; if that first load happens
// after we replace fs.realpath with a getter, Node 20 can throw
// `TypeError: polyfills is not a function` from a circular CJS clone.
require("graceful-fs");

const fs = require("fs");
const Module = require("module");
const path = require("path");

function ensureRealpathNative(target) {
  if (!target) return;
  if (typeof target.realpath !== "function") {
    target.realpath = function bedforgeRealpath(p, options, cb) {
      if (typeof options === "function") {
        cb = options;
        options = {};
      }
      try {
        (cb || (() => {}))(null, target.realpathSync(p, options));
      } catch (err) {
        (cb || (() => {}))(err);
      }
    };
  }
  if (typeof target.realpath.native !== "function") {
    target.realpath.native = target.realpath;
  }
}

ensureRealpathNative(fs);
{
  let currentRealpath = fs.realpath;
  ensureRealpathNative({ realpath: currentRealpath, realpathSync: fs.realpathSync });
  Object.defineProperty(fs, "realpath", {
    configurable: true,
    enumerable: true,
    get() {
      return currentRealpath;
    },
    set(next) {
      currentRealpath = next;
      if (typeof next === "function" && typeof next.native !== "function") {
        next.native = typeof fs.realpathSync === "function" ? fs.realpathSync : next;
      }
    },
  });
}

class BedforgeNoopPlugin {
  apply() {}
}

function stubCjsModule(request, exports) {
  try {
    const resolved = require.resolve(request);
    if (require.cache[resolved] && require.cache[resolved].__bedforgeStub) {
      return;
    }
    const cached = new Module(resolved);
    cached.filename = resolved;
    cached.loaded = true;
    cached.exports = exports;
    cached.__bedforgeStub = true;
    require.cache[resolved] = cached;
  } catch (err) {
    console.warn("[bedforge] stub skipped for", request, err && err.message);
  }
}

// CRA always requires workbox + fork-ts-checker at webpack.config load time.
// Nested fs-extra/graceful-fs can crash Node 20 (`fs.realpath.native` undefined).
// BedForge uses IndexedDB offline queue, not a Workbox service worker.
// Do NOT wrap Module._load — a second wrap hangs `craco start`.
const workboxStub = require("./scripts/workbox-stub");
stubCjsModule("workbox-webpack-plugin", workboxStub);
stubCjsModule("fork-ts-checker-webpack-plugin", BedforgeNoopPlugin);
stubCjsModule("react-dev-utils/ForkTsCheckerWebpackPlugin", BedforgeNoopPlugin);
stubCjsModule("react-dev-utils/ForkTsCheckerWarningWebpackPlugin", BedforgeNoopPlugin);

require("dotenv").config();

const isDevServer = process.env.NODE_ENV !== "production";

const config = {
  enableHealthCheck: process.env.ENABLE_HEALTH_CHECK === "true",
};

function getWebpackDevServerMajor() {
  try {
    const version = require("webpack-dev-server/package.json").version;
    return Number.parseInt(String(version).split(".")[0], 10) || 4;
  } catch (err) {
    return 4;
  }
}

function makeDevServerV5Compatible(devServerConfig) {
  const {
    https,
    onAfterSetupMiddleware,
    onBeforeSetupMiddleware,
    onListening,
    setupMiddlewares,
    ...compatibleConfig
  } = devServerConfig;

  compatibleConfig.server =
    typeof https === "object"
      ? { type: "https", options: https }
      : https
        ? "https"
        : "http";
  compatibleConfig.headers = {
    ...compatibleConfig.headers,
    "Cross-Origin-Resource-Policy": "same-origin",
  };

  if (onBeforeSetupMiddleware || setupMiddlewares) {
    compatibleConfig.setupMiddlewares = (middlewares, devServer) => {
      if (onBeforeSetupMiddleware) {
        onBeforeSetupMiddleware(devServer);
      }

      return setupMiddlewares
        ? setupMiddlewares(middlewares, devServer)
        : middlewares;
    };
  }

  compatibleConfig.onListening = (devServer) => {
    devServer.close ??= (callback) => devServer.stopCallback(callback);

    if (onListening) {
      onListening(devServer);
    }
    if (onAfterSetupMiddleware) {
      onAfterSetupMiddleware(devServer);
    }
  };

  return compatibleConfig;
}

function withCorpHeader(devServerConfig) {
  return {
    ...devServerConfig,
    headers: {
      ...devServerConfig.headers,
      "Cross-Origin-Resource-Policy": "same-origin",
    },
  };
}

let WebpackHealthPlugin;
let setupHealthEndpoints;
let healthPluginInstance;

if (config.enableHealthCheck) {
  WebpackHealthPlugin = require("./plugins/health-check/webpack-health-plugin");
  setupHealthEndpoints = require("./plugins/health-check/health-endpoints");
  healthPluginInstance = new WebpackHealthPlugin();
}

let webpackConfig = {
  eslint: {
    configure: {
      extends: ["plugin:react-hooks/recommended"],
      rules: {
        "react-hooks/rules-of-hooks": "error",
        "react-hooks/exhaustive-deps": "warn",
      },
    },
  },
  webpack: {
    alias: {
      "@": path.resolve(__dirname, "src"),
      "workbox-webpack-plugin": path.resolve(__dirname, "scripts/workbox-stub.js"),
    },
    configure: (webpackConfig) => {
      if (process.env.NODE_ENV === "production") {
        webpackConfig.cache = false;
      }

      webpackConfig.watchOptions = {
        ...webpackConfig.watchOptions,
        ignored: [
          "**/node_modules/**",
          "**/.git/**",
          "**/build/**",
          "**/dist/**",
          "**/coverage/**",
          "**/public/**",
        ],
      };

      if (config.enableHealthCheck && healthPluginInstance) {
        webpackConfig.plugins.push(healthPluginInstance);
      }
      return webpackConfig;
    },
  },
};

webpackConfig.devServer = (devServerConfig) => {
  if (config.enableHealthCheck && setupHealthEndpoints && healthPluginInstance) {
    const originalSetupMiddlewares = devServerConfig.setupMiddlewares;

    devServerConfig.setupMiddlewares = (middlewares, devServer) => {
      if (originalSetupMiddlewares) {
        middlewares = originalSetupMiddlewares(middlewares, devServer);
      }

      setupHealthEndpoints(devServer, healthPluginInstance);

      return middlewares;
    };
  }

  return devServerConfig;
};

if (isDevServer) {
  try {
    const { withVisualEdits } = require("@emergentbase/visual-edits/craco");
    webpackConfig = withVisualEdits(webpackConfig);
  } catch (err) {
    if (err.code === "MODULE_NOT_FOUND" && err.message.includes("@emergentbase/visual-edits/craco")) {
      console.warn(
        "[visual-edits] @emergentbase/visual-edits not installed — visual editing disabled."
      );
    } else {
      throw err;
    }
  }
}

const configureDevServer = webpackConfig.devServer;
const webpackDevServerMajor = getWebpackDevServerMajor();
webpackConfig.devServer = (devServerConfig) => {
  const nextConfig = configureDevServer(devServerConfig);
  if (webpackDevServerMajor >= 5) {
    return makeDevServerV5Compatible(nextConfig);
  }
  return withCorpHeader(nextConfig);
};

module.exports = webpackConfig;
