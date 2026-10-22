import { useEffect, useState } from "react";
import { api } from "../services/api";
import { ConfirmDialog } from "../components/ConfirmDialog";

export default function Camera() {
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  // Comprobación facial manual contra la cámara activa
  const [result, setResult] = useState<{ category: string; display_name: string | null } | null>(null);

  useEffect(() => {
    if (!enabled) return;
    const t = setInterval(() => {
      api.get("/api/health").catch(() => {});
    }, 10000);
    return () => clearInterval(t);
  }, [enabled]);

  async function checkNow() {
    setError(null);
    setResult(null);
    try {
      const r = await api.post<{ category: string; decision: boolean; display_name: string | null; message?: string }>(
        "/api/access/check"
      );
      setResult({ category: r.category, display_name: r.display_name });
    } catch (e) {
      const err = e as { code?: string; message: string };
      if (err.code === "denied_model" || err.code === "denied_camera") {
        setResult({ category: err.code!, display_name: null });
      } else {
        setError(err.message);
      }
    }
  }

  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-2xl font-bold mb-4">Cámara en vivo</h1>
      {!enabled ? (
        <div className="rounded-xl border bg-white p-6">
          <p className="text-slate-600 text-sm mb-4">
            El flujo de la cámara está protegido con tu sesión administrativa y no queda
            abierto públicamente. Al activarlo se transmite solo a esta pantalla
            (MJPEG autenticado en cada fotograma).
          </p>
          <button
            onClick={() => setConfirm(true)}
            className="bg-brand-500 text-white px-4 py-2 rounded-lg text-sm"
          >
            Activar vista de cámara
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border bg-black overflow-hidden">
            {/* cada frame pasa por el servidor Flask, que valida la sesión */}
            <img
              src="/api/camera/stream"
              alt="Cámara en tiempo real"
              className="w-full"
              onError={(e) => {
                setError("No se pudo leer el flujo de la cámara (¿está conectada?)");
                (e.target as HTMLImageElement).style.display = "none";
              }}
            />
          </div>
          <div className="flex gap-2">
            <button
              onClick={checkNow}
              className="bg-brand-500 text-white px-4 py-2 rounded-lg text-sm"
            >
              Comprobar acceso ahora
            </button>
            <button
              onClick={() => setEnabled(false)}
              className="border rounded-lg px-4 py-2 text-sm"
            >
              Desactivar
            </button>
          </div>
          {result && (
            <div className={`rounded-lg p-4 text-sm ${
              result.category === "welcome" ? "bg-green-50 text-green-800" : "bg-red-50 text-red-700"
            }`}>
              {result.category === "welcome"
                ? `Reconocida: ${result.display_name}`
                : `Decisión: ${result.category}`}
            </div>
          )}
          {error && (
            <div className="bg-amber-50 text-amber-800 rounded-lg p-4 text-sm">{error}</div>
          )}
        </div>
      )}

      {confirm && (
        <ConfirmDialog
          title="Activar cámara en vivo"
          description="Solo se verá en esta sesión autenticada. ¿Continuar?"
          onConfirm={() => {
            setConfirm(false);
            setEnabled(true);
          }}
          onCancel={() => setConfirm(false)}
        />
      )}
    </div>
  );
}
