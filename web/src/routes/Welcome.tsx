import { useLocation } from "react-router-dom";

/** Página de bienvenida: se muestra tras confirmar identidad autorizada con
 *  rol user. Nunca revela datos administrativos ni de otras personas. */
export default function Welcome() {
  const location = useLocation();
  const name = (location.state as { display_name?: string } | null)?.display_name;

  return (
    <div className="h-full flex items-center justify-center bg-green-700 p-6">
      <div className="text-center text-white">
        <div className="text-6xl mb-6">✅</div>
        <h1 className="text-3xl font-bold">
          {name ? `Bienvenido, ${name}` : "Acceso autorizado"}
        </h1>
        <p className="mt-3 text-green-100 text-sm max-w-md mx-auto">
          Puedes continuar. Esta pantalla no muestra información administrativa ni datos
          de otras personas.
        </p>
      </div>
    </div>
  );
}
