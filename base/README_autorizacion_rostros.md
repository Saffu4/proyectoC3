# Sistema de reconocimiento facial con Raspberry Pi 5

Guía rápida para registrar y autorizar a una persona nueva en el
sistema.

> **Importante:** el reconocimiento facial es una demostración y puede
> equivocarse. No lo uses como único control para proteger una puerta,
> dinero, información sensible o la seguridad de una persona. Antes de
> usarlo en un entorno real, añade controles de seguridad y un método
> alternativo de acceso.

## 1. Cómo funciona la autorización

El proceso tiene dos partes:

1.  **Registrar el rostro:** capturar varias imágenes de la persona.
2.  **Entrenar el modelo:** incorporar las imágenes registradas al
    modelo de reconocimiento.

Después se reinicia el detector y se comprueba que la persona aparezca
como autorizada.

## 2. Conectarse a la Raspberry Pi desde Visual Studio Code

1.  En Windows, abre Visual Studio Code.

2.  Conéctate a la Raspberry Pi mediante la extensión **Remote - SSH**.

3.  Abre la carpeta donde están los scripts del proyecto. En la
    configuración actual, los archivos se han trabajado en el Escritorio
    del usuario `saffu1`:

    ``` bash
    cd ~/Desktop
    ```

4.  Abre una terminal integrada en VS Code: **Terminal → New Terminal**.

5.  Comprueba que los archivos existen:

    ``` bash
    ls
    ```

    Deberías ver archivos como `detector.py`, `registrar_rostro.py` y
    `entrenar_modelo.py`.

Si tus scripts están en otra carpeta, entra en esa carpeta en lugar de
`~/Desktop`.

## 3. Preparar las carpetas para las personas autorizadas

La carpeta de imágenes debe contener una subcarpeta por persona. Por
ejemplo:

``` text
rostros/
└── autorizado/
    ├── persona_01/
    ├── persona_02/
    └── persona_03/
```

Crea la carpeta base si no existe:

``` bash
mkdir -p ~/Desktop/rostros/autorizado
```

**No uses el nombre de una persona como único dato de seguridad.**
Utiliza un identificador sencillo, por ejemplo `persona_04`, y guarda
por separado quién corresponde a ese identificador.

## 4. Registrar a una persona nueva

1.  Pide permiso a la persona para capturar y almacenar sus imágenes
    biométricas.

2.  Asegúrate de que haya buena iluminación, que la cámara esté estable
    y que el rostro se vea de frente.

3.  Ejecuta el script de registro:

    ``` bash
    cd ~/Desktop
    python3 registrar_rostro.py
    ```

4.  Sigue las instrucciones que aparezcan en pantalla. Si el script
    solicita un nombre o identificador, usa uno único, por ejemplo
    `persona_04`.

5.  Si el script no solicita el identificador, revisa su configuración
    para asegurarte de que guarde las capturas en la carpeta
    correspondiente a esa persona. No mezcles las fotos de varias
    personas en una misma carpeta.

6.  Captura varias imágenes nítidas con ligeras variaciones de ángulo e
    iluminación. Evita imágenes borrosas, rostros tapados o personas
    adicionales en el encuadre.

7.  Cierra el registro cuando termine y verifica que las imágenes se
    guardaron en la carpeta correcta.

Comprueba las carpetas:

``` bash
find ~/Desktop/rostros -maxdepth 3 -type f
```

Si no aparecen imágenes nuevas en la carpeta de la persona, **no
continúes con el entrenamiento**: primero corrige la ruta de guardado
del script.

## 5. Entrenar de nuevo el modelo

Después de registrar a una persona, vuelve a entrenar el modelo para
incluir sus imágenes:

``` bash
cd ~/Desktop
python3 entrenar_modelo.py
```

El proyecto se configuró para guardar el modelo en:

``` text
~/Desktop/modelos/lbph.yml
```

Comprueba que el archivo exista y que su fecha de modificación sea
reciente:

``` bash
ls -lh ~/Desktop/modelos/lbph.yml
```

**Advertencia:** el entrenamiento normalmente reconstruye el modelo a
partir de las imágenes que encuentra en las carpetas configuradas por el
script. Asegúrate de que las imágenes de todas las personas que deban
seguir autorizadas estén presentes antes de entrenar. Si el script está
configurado para leer una sola carpeta, habrá que adaptarlo para leer
todas las subcarpetas de personas.

## 6. Reiniciar el detector y probar

1.  Si el detector está ejecutándose en la terminal, detenlo con
    `Ctrl + C`.

2.  Inícialo otra vez:

    ``` bash
    cd ~/Desktop
    python3 detector.py
    ```

3.  Desde el navegador de tu PC, abre:

    ``` text
    http://192.168.1.11:5000
    ```

4.  Comprueba la imagen de la cámara y prueba con la persona recién
    registrada.

5.  Comprueba también con una persona que **no** esté registrada. Debe
    aparecer como desconocida o no autorizada, según el texto
    implementado en el script.

No consideres a alguien autorizado solo porque el detector dibuje un
rectángulo sobre su cara: eso indica detección, no necesariamente
reconocimiento. Confirma que la aplicación muestra la identidad o el
estado correcto.

## 7. Si no reconoce a la persona

Revisa en este orden:

-   **¿Se guardaron las imágenes?** Inspecciona `~/Desktop/rostros/`.
-   **¿Se entrenó el modelo después del registro?** Ejecuta de nuevo
    `python3 entrenar_modelo.py`.
-   **¿Cambió el modelo?** Comprueba la fecha con
    `ls -lh ~/Desktop/modelos/lbph.yml`.
-   **¿El detector carga ese mismo archivo?** Revisa la ruta del modelo
    en `detector.py`.
-   **¿La cámara tiene buena iluminación?** Prueba con luz frontal
    uniforme, sin contraluz.
-   **¿La persona aparece como desconocida?** El umbral de similitud de
    LBPH puede necesitar ajuste. No lo cambies a ciegas: valida con
    varias personas autorizadas y no autorizadas para evitar aceptar
    rostros incorrectos.

Si aparece un error en la terminal, copia el mensaje completo y
consérvalo para diagnosticarlo.

## 8. Retirar la autorización de una persona

Eliminar a una persona de la carpeta no siempre la elimina del modelo
que ya está entrenado. Para retirar su autorización:

1.  Detén `detector.py` con `Ctrl + C`.

2.  Haz una copia de seguridad privada si necesitas conservar los datos
    y tienes permiso para hacerlo.

3.  Elimina la carpeta de imágenes de esa persona, identificando con
    cuidado la carpeta correcta. Ejemplo:

    ``` bash
    rm -r ~/Desktop/rostros/autorizado/persona_04
    ```

    Cambia `persona_04` por el identificador correcto. Este comando
    elimina archivos; verifica la ruta antes de ejecutarlo.

4.  Vuelve a entrenar:

    ``` bash
    cd ~/Desktop
    python3 entrenar_modelo.py
    ```

5.  Reinicia el detector y prueba que esa persona ya no se reconozca
    como autorizada.

Si el script guarda etiquetas o datos de usuarios en otros archivos o
bases de datos, elimina o desactiva también ese registro. El modelo debe
reconstruirse sin las imágenes de la persona retirada.

## 9. Privacidad y seguridad

-   Solicita consentimiento antes de tomar y guardar imágenes faciales.
-   Guarda las fotos y el archivo `lbph.yml` de forma privada; son datos
    biométricos.
-   **No subas** `rostros/`, `modelos/lbph.yml` ni fotografías a un
    repositorio público de GitHub.
-   No expongas el servidor Flask directamente a Internet. La dirección
    `http://192.168.1.11:5000` es una dirección local de la red y el
    servidor de demostración puede no tener autenticación.
-   Limita quién puede acceder por SSH y quién puede modificar los
    scripts o el modelo.
-   Mantén una alternativa manual de acceso y revisa los falsos
    positivos y negativos.

## 10. Lista rápida para cada alta

-   [ ] Consentimiento obtenido.
-   [ ] Carpeta única creada para la persona.
-   [ ] Imágenes claras capturadas y guardadas en la carpeta correcta.
-   [ ] Modelo reentrenado sin errores.
-   [ ] Detector reiniciado.
-   [ ] Persona reconocida correctamente en varias pruebas.
-   [ ] Persona no registrada comprobada como desconocida/no autorizada.
-   [ ] Fotos y modelo guardados de forma privada.

------------------------------------------------------------------------

**Comandos principales**

``` bash
cd ~/Desktop
python3 registrar_rostro.py
python3 entrenar_modelo.py
python3 detector.py
```

Esta guía supone que los scripts utilizan esos nombres y que el modelo
se guarda en `~/Desktop/modelos/lbph.yml`. Si las rutas o el
comportamiento de los scripts son diferentes, actualiza este README para
que coincida con el código real.
