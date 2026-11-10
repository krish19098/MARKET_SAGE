import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      registerType: "autoUpdate",
      injectRegister: false,
      manifest: {
        name: "MARKET SAGE",
        short_name: "MarketSage",
        description: "Evidence-driven Indian equity research and swing-trading decision support (advisory, paper trading).",
        start_url: "/",
        scope: "/",
        display: "standalone",
        orientation: "any",
        background_color: "#0f172a",
        theme_color: "#0f172a",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
        ],
      },
      injectManifest: { globPatterns: ["**/*.{js,css,html,png,svg}"] },
      devOptions: { enabled: false },
    }),
  ],
  server: { proxy: { "/api": { target: "http://127.0.0.1:8000", ws: true } } },
  test: { environment: "jsdom" },
} as never);
