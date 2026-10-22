import { useLocation } from "react-router-dom";

/** Acceso denegado: desconocidos, suspendidos, revocados o permisos vencidos.
 *  Ofrece alternativa manual y no muestra información de la persona. */
export default function Denied() {
  const location = useLocation();
  const category =
    (location.state as { category?: string } | null)?.category ?? "denied_unknown";

  const messages: Record<string, string> = {
    denied_unknown: "Rostro no reconocido por el sistema",
    denied_suspended: "Este permiso está suspendido temporalmente",
    denied_revoked: "Este permiso fue revocado",
    denied_expired: "Este permiso está vencido",
    denied_no_role: "La persona reconocida no tiene permiso de acceso",
    denied_model: "El sistema de reconocimiento no está disponible",
    denied_camera: "La cámara no está disponible",
    denied_internal_error: "Error temporal del sistema",
  };

  return (
    <div className="h-full flex items-center justify-center bg-red-700 p-6">
      <div className="text-center text-white">
        <div className="text-6xl mb-6">⛔</div>
        <h1 className="text-3xl font-bold">Acceso denegado</h1>
        <p className="mt-3 text-red-100 text-sm max-w-md mx-auto">
          {messages[category] ?? "No se puede otorgar acceso con este reconocimiento"}
        </p>
        <p className="mt-6 text-red-100 text-xs">
          Si piensas que se trata de un error, solicita asistencia al administrador o usa
          la alternativa manual de acceso.
        </p>
      </div>
    </div>
  );
}
