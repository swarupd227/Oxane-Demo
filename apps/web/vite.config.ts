import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // The deal pack uses standard PDF fonts, so PDF.js needs their data to draw them.
    viteStaticCopy({
      targets: [
        {
          src: "node_modules/pdfjs-dist/standard_fonts/*",
          dest: "pdfjs/standard_fonts",
          rename: { stripBase: true },
        },
      ],
    }),
  ],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    // The browser tests reach this server by its Compose service name.
    allowedHosts: ["web"],
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
    proxy: {
      "/api": process.env.API_TARGET ?? "http://localhost:8010",
    },
  },
});
