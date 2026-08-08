import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Prefer 8017 when 8007 is a stale process; override with VITE_DAQ_PROXY
        target: process.env.VITE_DAQ_PROXY || "http://127.0.0.1:8017",
        changeOrigin: true,
        rewrite: (p) => p.replace(/^\/api/, ""),
      },
    },
  },
});
