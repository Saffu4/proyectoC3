import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite SOLO para el panel web; nunca ejecuta el reconocimiento facial ni toca la webcam.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      // en desarrollo delega la API al servicio Flask de la Pi / localhost:5000
      "/api": {
        target: process.env.VITE_API_TARGET || "http://127.0.0.1:5000",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist" },
});
