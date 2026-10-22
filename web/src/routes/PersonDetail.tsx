import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../services/api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import type { PersonDetail } from "../types";

type Action = "activate" | "suspend" | "revoke" | "delete" | "train" | "capture";

export default function PersonDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [person, setPerson] = useState<PersonDetail | null>(null);
  const [captureCount, setCaptureCount] = useState(15);
  const [capturing, setCapturing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    api.get<PersonDetail>(`/api/people/${id}`).then(setPerson, (e) =>
      setError(e.message)
    );
  }, [id]);

  useEffect(load, [load]);

  async function execute(action: Action) {
    if (!id) return;
    setBusy(true);
    setError(null);
    setConfirm(null);
    if (action === "capture") setCapturing(true);
    try {
      if (action === "delete") {
        await api.delete(`/api/people/${id}`);
        navigate("/people", { replace: true });
        return;
      }
      if (action === "train") {
        const r = await api.post<{ images_used: number }>(`/api/people/${id}/train`);
        setMessage(
          `Modelo reentrenado con ${r.images_used} imágenes (todas las personas activas).`
        );
      } else if (action === "capture") {
        // ocupa hasta ~15 s mirando a la cámara; ritmo 0.4 s entre rostros
        const saved = await api.post<{ saved: number; model_label: number }>(
          `/api/people/${id}/capture`,
          { count: captureCount }
        );
        setMessage(
          `Capturados ${saved.saved} rostros (model_label=${saved.model_label}). Ahora pulsa "Reentrenar modelo".`
        );
      } else {
        await api.post(`/api/people/${id}/${action}`);
        setMessage(
          action === "activate" ? "Persona activada." :
          action === "suspend" ? "Persona suspendida." :
          "Permiso revocado: no podrá entrar ya en la siguiente comprobación."
        );
      }
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error");
    } finally {
      setBusy(false);
      setCapturing(false);
    }
  }

  if (error && !person) {
    return <div className="p-6 text-red-600">{error}</div>;
  }
  if (!person) {
    return <div className="p-6 text-slate-500">Cargando…</div>;
  }

  const dialogCopy: Record<Action, { title: string; description: string }> = {
    activate: { title: "Activar persona", description: "Se re-habilita el reconocimiento en la siguiente comprobación." },
    suspend: { title: "Suspender persona", description: "El acceso queda bloqueado temporalmente, sin reentrenar el modelo." },
    revoke: { title: "Revocar permiso", description: "Acceso bloqueado de forma persistente hasta reactivación explícita." },
    delete: { title: "Eliminar persona", description: "Se borran imágenes biométricas y perfil según la política de retención. Acción irreversible." },
    train: { title: "Reentrenar modelo", description: "Se reconstruye el modelo LBPH con todas las imágenes habilitadas." },
    capture: { title: "Capturar rostros", description: "La persona debe mirar a la cámara sin salirse. Dura varios segundos por imagen; confirma que ya está delante." },
  };

  return (
    <div className="p-6 max-w-2xl">
      <Link to="/people" className="text-sm text-brand-600 hover:underline">← Personas</Link>
      <div className="flex items-center gap-3 my-4">
        <h1 className="text-2xl font-bold">{person.full_name}</h1>
        <span className={`px-2 py-0.5 rounded-full text-xs ${
          person.status === "active" ? "bg-green-100 text-green-700" :
          person.status === "suspended" ? "bg-amber-100 text-amber-700" :
          "bg-red-100 text-red-700"}`}>
          {person.status}
        </span>
      </div>

      <dl className="text-sm grid grid-cols-3 gap-2 rounded-xl border bg-white p-4">
        <dt className="text-slate-500">Roles</dt>
        <dd className="col-span-2">{person.roles.join(", ") || "—"}</dd>
        <dt className="text-slate-500">Document</dt>
        <dd className="col-span-2">{person.document_id ?? "—"}</dd>
        <dt className="text-slate-500">Vence</dt>
        <dd className="col-span-2">{person.expires_at?.slice(0, 10) ?? "—"}</dd>
        <dt className="text-slate-500">Perfil facial</dt>
        <dd className="col-span-2">
          {person.face_profile
            ? `label ${person.face_profile.model_label} · ${person.face_images_count} imágenes`
            : "Sin rostros capturados"}
        </dd>
      </dl>

      {message && <div className="mt-4 text-sm bg-green-50 text-green-700 rounded-lg p-3">{message}</div>}
      {error && <div className="mt-4 text-sm bg-red-50 text-red-700 rounded-lg p-3">{error}</div>}

      <div className="mt-6 rounded-xl border bg-white p-4">
        <div className="font-semibold mb-1">Creación de modelo facial</div>
        <p className="text-xs text-slate-500 mb-3">
          La persona debe estar <em>activa</em>, mirar la cámara de frente, con buena
          iluminación. Se capturan rostros al ritmo del pipeline base (~0,4 s cada
          uno, cara más grande + margen 15% + 200×200).
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm">
            N° de rostros:
            <select
              value={captureCount}
              onChange={(e) => setCaptureCount(Number(e.target.value))}
              className="ml-2 border rounded px-2 py-1"
              disabled={busy || capturing}
            >
              {[10, 15, 20, 30, 40].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </label>
          <button
            disabled={busy || capturing || person.status !== "active"}
            onClick={() => setConfirm("capture")}
            className="border rounded-lg px-4 py-2 text-sm bg-brand-50"
          >
            {capturing ? "Capturando… no salgas de la cámara" : "Capturar rostros"}
          </button>
          <button
            disabled={busy || capturing || !person.face_profile}
            onClick={() => setConfirm("train")}
            className="border rounded-lg px-4 py-2 text-sm"
          >
            Reentrenar modelo
          </button>
          {person.face_profile && (
            <span className="text-xs text-slate-500">
              Etiqueta LBPH {person.face_profile.model_label} · {person.face_images_count} imágenes guardadas
            </span>
          )}
        </div>
        {person.status !== "active" && (
          <p className="text-xs text-amber-600 mt-2">
            Activa la persona antes de capturar datos biométricos.
          </p>
        )}
      </div>

      <div className="mt-6 flex flex-wrap gap-2">
        <button disabled={busy || capturing} onClick={() => setConfirm("activate")} className="border rounded-lg px-4 py-2 text-sm bg-green-50">Activar</button>
        <button disabled={busy || capturing} onClick={() => setConfirm("suspend")} className="border rounded-lg px-4 py-2 text-sm bg-amber-50">Suspender</button>
        <button disabled={busy || capturing} onClick={() => setConfirm("revoke")} className="border rounded-lg px-4 py-2 text-sm bg-red-50">Revocar</button>
        <button disabled={busy || capturing} onClick={() => setConfirm("delete")} className="border rounded-lg px-4 py-2 text-sm bg-red-100 text-red-800">Eliminar</button>
      </div>
      <p className="text-xs text-slate-500 mt-3">
        Suspensión, revocación y cambios de vigencia funcionan al instante sin volver a entrenar el modelo.
      </p>

      {confirm && (
        <ConfirmDialog
          title={dialogCopy[confirm].title}
          description={dialogCopy[confirm].description}
          danger={confirm === "delete" || confirm === "revoke"}
          onConfirm={() => execute(confirm)}
          onCancel={() => setConfirm(null)}
        />
      )}
    </div>
  );
}
