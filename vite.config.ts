import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
export default defineConfig({
  plugins: [react()],
  server: {
    port: Number(process.env.AMNESIA_WEB_PORT || 5173),
    strictPort: true,
    proxy: {
      "/api": `http://127.0.0.1:${process.env.AMNESIA_API_PORT || 8787}`,
    },
  },
});
