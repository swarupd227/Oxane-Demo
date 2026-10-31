import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: { usePolling: process.env.VITE_USE_POLLING === "true" },
    proxy: {
      "/api": process.env.API_TARGET ?? "http://localhost:8010",
    },
  },
});
