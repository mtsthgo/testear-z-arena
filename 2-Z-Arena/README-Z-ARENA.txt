# Z-Arena: matchmaking real con el online del juego

Esta versión empareja dos clientes mediante un Durable Object de Cloudflare. La sala de combate sigue siendo la sala oficial del juego: el jugador anfitrión crea un código en Dragon Net Battle y lo comparte desde Z-Arena; el rival lo copia y lo ingresa en Dragon Net Battle → Join. El Worker de Z-Arena solo guarda la cola, las aceptaciones y ese código de seis caracteres. No recibe tráfico del combate.

## Publicar la cola

Se necesita una cuenta de Cloudflare con Workers y Durable Objects y Node.js instalado.

1. Abrí una terminal en esta carpeta (`outputs`).
2. Ejecutá `npx wrangler login`.
3. Ejecutá `npx wrangler deploy --config wrangler-z-arena.toml`.
4. Copiá la URL `https://...workers.dev` que devuelve Wrangler.
5. Pegá esa URL en `z-arena-config.json` como valor de `queue_worker_url`.

## Ejecutar localmente

Abrí el juego y ejecutá `iniciar-z-arena.bat`. Conservá la ventana abierta y entrá a `http://127.0.0.1:8765`. El botón de buscar solo se activa cuando el puente puede confirmar que `Tenkaichi3Decomp.exe` está abierto y el Worker está configurado.

Cuando ambos aceptan, el anfitrión debe abrir Dragon Net Battle → Host. Después pega el código de sala real en Z-Arena y pulsa Compartir código. El rival recibe ese código y lo ingresa en Dragon Net Battle → Join. Ambos deben tener la misma versión del juego.

## Límites de esta entrega

- La web no puede comprobar el resultado del combate ni el rango del jugador; el online de la decompilación no expone esos datos al puente local.
- La web no fuerza el juego a entrar en Host/Join. Eso requeriría cambiar y recompilar el código C del juego o lanzarlo con `BT3_LOBBY`; el modo automático documentado en el repo está pensado para pruebas.
- El servicio de cola debe estar desplegado para que jugadores de distintas computadoras se encuentren. No se modificó ni desplegó el Worker oficial del juego.
- El código de sala de juego expira según el servicio oficial del juego (diez minutos en el código fuente actual).

## Flujo automático de partidas

Con la versión actualizada del sitio y del Worker, cuando ambos jugadores aceptan se inicia una cuenta regresiva de diez segundos. El puente local manda el rol al juego abierto: el anfitrión publica la sala y el otro cliente se une desde el juego, sin ingresar el código manualmente.

Al terminar la batalla, cada ejecutable reporta el ganador al Worker. El Worker aplica el cambio de ELO solo si los dos clientes informan el mismo ganador. El ELO está ligado al token guardado en el navegador; todavía no es una cuenta con contraseña y se puede perder si se borra el almacenamiento del navegador.

Para que funcione, todos deben actualizar el sitio publicado, desplegar z-arena-queue-worker.js, actualizar z-arena-server.py y usar la versión del ejecutable compilada con las modificaciones de port/src/gs/net.c y src/battle/battle.c.