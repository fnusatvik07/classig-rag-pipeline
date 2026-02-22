import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/chat": "http://localhost:8000",
      "/upload": "http://localhost:8000",
      "/ingest": "http://localhost:8000",
      "/documents": "http://localhost:8000",
      "/health": "http://localhost:8000",
      "/cache": "http://localhost:8000",
      "/vectors": "http://localhost:8000",
    },
  },
});
