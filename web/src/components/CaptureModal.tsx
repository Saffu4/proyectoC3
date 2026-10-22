import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";

interface Props {
  personId: string;
  onClose: () => void;
  /** llamado al terminar con éxito (cuántos rostros quedaron guardados) */
  onDone: (saved: number) => void;
}

const COUNTS = [10, 15, 20, 30, 40, 60];

interface Snap {
  session_id: string;
  target: number;
  saved: number;
  status: "running" | "done" | "cancelled" | "error";
  guidance: string;
  error: string | null;
}

/** Mini-flujo de captura con vista en vivo: contador X/N, guía de calidad
 *  (nitidez/luz/distancia) y boton de detener. El preview es MJPEG abierto
 *  con token efímero; el estado va por polling autenticado. */
export default function CaptureModal({ personId, onClose, onDone }: Props) {
  const [count, setCount] = useState(20);
  const [snap, setSnap] = useState<Snap | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [busy, setBusy] = useState(true);
  const [starting, setStarting] = useState(false);
  const snapRef = useRef<Snap | null>(null);
  snapRef.current = snap;

  async function start() {
    setStarting(true);
    setFatalError(null);
    try {
      // 1) sesión de captura; 2) token efímero para el MJPEG
      const s = await api.post<{ session_id: string; target: number }>(
        `/api/people/${personId}/capture-session`,
        { count }
      );
      const t = await api.post<{ token: string }>("/api/camera/stream-token");
      setSnap({
        session_id: s.session_id,
        target: s.target,
        saved: 0,
        status: "running",
        guidance: "Adaptando cámara…",
        error: null,
      });
      setPreviewUrl(
        `/api/capture/${s.session_id}/preview?t=${t.token}#ocache_to_reset_${Date.now()}`
      );
      setBusy(false);
    } catch (e) {
      setFatalError(e instanceof Error ? e.message : "No se pudo iniciar la captura");
    } finally {
      setStarting(false);
    }
  }

  useEffect(() => {
    if (!previewUrl) return;
    const pull = setInterval(async () => {
      const s = snapRef.current;
      if (!s) return;
      try {
        const st = await api.get<Snap>(`/api/capture/${s.session_id}/status`);
        setSnap(st);
        if (st.status === "done") {
          clearInterval(pull);
          setTimeout(() => onDone(st.saved), 1200);
        } else if (st.status === "error" || st.status === "cancelled") {
          clearInterval(pull);
        }
      } catch {
        /* reintenta en el próximo tick */
      }
    }, 600);
    return () => clearInterval(pull);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewUrl]);

  async function stop() {
    if (!snap) return;
    setBusy(true);
    try {
      await api.post(`/api/capture/${snap.session_id}/stop`);
    } catch {
      /* la sesión puede haber terminado ya */
    }
  }

  const done = snap?.status === "done";
  const ended = done || snap?.status === "cancelled" || snap?.status === "error";

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl max-w-xl w-full p-5 shadow-2xl">
        <h2 className="text-lg font-bold">Captura facial en vivo</h2>

        {!previewUrl && !fatalError && (
          <div className="mt-4 space-y-3">
            <p className="text-sm text-slate-600">
              La persona debe estar frente a la cámara. Con buena luz, de frente,
              sin salirse del encuadre. El sistema solo guarda tomas nítidas.
            </p>
            <label className="block text-sm">
              Rostros a capturar:
              <select
                value={count}
                onChange={(e) => setCount(Number(e.target.value))}
                disabled={starting}
                className="ml-2 border rounded px-2 py-1"
              >
                {COUNTS.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </label>
            <div className="flex gap-2 justify-end">
              <button className="border rounded-lg px-4 py-2 text-sm" onClick={onClose}>
                Cancelar
              </button>
              <button
                onClick={start}
                disabled={starting}
                className="bg-brand-500 text-white rounded-lg px-4 py-2 text-sm disabled:opacity-50"
              >
                {starting ? "Iniciando…" : "Comenzar captura"}
              </button>
            </div>
          </div>
        )}

        {fatalError && (
          <div className="mt-4 bg-red-50 text-red-700 rounded-lg p-3 text-sm space-y-3">
            {fatalError}
            <div className="flex gap-2 justify-end">
              <button className="border rounded-lg px-3 py-1.5 text-sm" onClick={start}>
                Reintentar
              </button>
              <button className="border rounded-lg px-3 py-1.5 text-sm" onClick={onClose}>
                Cerrar
              </button>
            </div>
          </div>
        )}

        {previewUrl && snap && (
          <div className="mt-4 space-y-3">
            <div className="relative bg-black rounded-xl overflow-hidden">
              <img
                src={previewUrl}
                alt="Vista en vivo de captura"
                className="w-full"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.opacity = "0.2";
                }}
              />
              <div className="absolute top-2 right-2 bg-black/70 text-white text-sm px-3 py-1 rounded-full">
                {snap.saved} / {snap.target}
              </div>
            </div>
            <div
              className={`text-sm rounded-lg p-3 ${
                snap.guidance.startsWith("Posición") || snap.guidance.startsWith("Cámara")
                  ? "bg-green-50 text-green-800"
                  : "bg-amber-50 text-amber-800"
              }`}
            >
              💡 {snap.guidance}
            </div>
            {snap.status === "error" && (
              <div className="bg-red-50 text-red-700 rounded-lg p-3 text-sm">
                {snap.error ?? "Error durante la captura"}
              </div>
            )}
            {ended || snap.status === "done" ? (
              <div className="flex gap-2 justify-end">
                <button className="border rounded-lg px-4 py-2 text-sm" onClick={onClose}>
                  Cerrar
                </button>
              </div>
            ) : (
              <div className="flex gap-2 justify-end">
                <button
                  onClick={stop}
                  disabled={busy}
                  className="border border-red-300 text-red-700 rounded-lg px-4 py-2 text-sm"
                >
                  Detener captura
                </button>
              </div>
            )}
            <p className="text-xs text-slate-500">
              Gira la cabeza lento de lado a lado, acerca/aleja un poco y varía gesto
              sutilmente para tener tomas variadas.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
