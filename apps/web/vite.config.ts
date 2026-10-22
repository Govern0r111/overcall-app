import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { fileURLToPath } from "node:url";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const siteUrl = env.VITE_SITE_URL || "https://overcall.app";

  return {
    plugins: [
      react(),
      {
        name: "site-url",
        transformIndexHtml(html) {
          return html.replaceAll("__VITE_SITE_URL__", siteUrl);
        },
      },
    ],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
  };
});
