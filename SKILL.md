---
name: super-guare
description: "Orquesta una investigación, implementación y revisión independiente para cambios de alto riesgo o con una premisa disputada. El SUPER no implementa: decide con evidencia actual, una revisión ciega del diff y una adjudicación propia."
---

# SUPER guare

Un **SUPER guare** orquesta y adjudica; sus guares hacen el reconocimiento,
la implementación y la revisión. **El SUPER no implementa.** Si modifica el
diff, no puede adjudicarlo independientemente.

Úsalo cuando el error pueda ser costoso o silencioso —datos, permisos,
concurrencia, recuperación, migraciones o un cambio ancho— o cuando la
premisa sea discutible. Para un cambio pequeño, mecánico y ya reproducido,
trabaja directamente: esta ceremonia no añade garantía proporcional.

## Puerta de premisa

Antes de repartir código, el SUPER fija el árbol exacto y comprueba que el
encargo sigue vivo contra él. Un issue, plan o arreglo propuesto es una
hipótesis, no autoridad.

Mantén un ledger mínimo:

| Estado | Contenido |
|---|---|
| **Observed** | Síntoma, entorno y salida obtenida. |
| **Confirmed** | Entrypoint real y límite causal demostrado. |
| **Control** | Caso limpio o vecino que descarta una explicación simple. |
| **Inference** | Explicación plausible aún no demostrada. |
| **Decision** | Alcance, no-objetivos y alternativa descartada. |

La investigación debe alcanzar el entrypoint de producción; un helper no
prueba lo que un caller exterior puede capturar, transformar o reparar. Añade
un control negativo que desafíe la explicación principal. Define antes de
implementar un **predicado de cierre observable**: qué efecto externo demuestra
la corrección y qué resultado queda prohibido. Ajusta el rigor al riesgo; no
impongas análisis de recuperación distribuida a un bug local ordinario.

Mantén una tarjeta provisional con revisión, síntoma/sobre de alcance, causa
como hipótesis, efecto observable, regresiones prohibidas y no-objetivos. Cada
paso de reconocimiento debe trazar a esa tarjeta o a una hipótesis falsificable.
Congélala sólo en `READY`, cuando la causa esté demostrada; si cambia después,
versiona la tarjeta y declara qué evidencia quedó invalidada.

La disposición previa es `READY` (evidencia y contrato suficientes), `HOLD`
(falta evidencia obtenible) o `REJECT` (premisa refutada o trabajo
incompatible; terminal salvo reframing). Si la premisa, el entrypoint o el
predicado no se pueden establecer, emite `HOLD`; no mandes a implementar una
conjetura. `no pude mirar` detiene el flujo: nunca se redondea a éxito ni a
ausencia de problema. Si el árbol, la base o el diff cambian, refresca la
evidencia afectada antes de decidir.

## Congelar alcance y presupuesto de esfuerzo

Antes de diseñar o repartir, busca primero duplicados e implementaciones activas
del cierre estricto. Busca ownership arquitectónico sólo para una objeción fuera
de alcance que haya sobrevivido y necesite destino. Un owner válido tiene
enlace y estado verificados, garantía explícita, alcance compatible y una vía
accionable de cierre. Al encontrarlo, registra owner, solape, delta no cubierto
y evidencia, y detén esa búsqueda; no hagas un inventario exhaustivo. Un owner
existente recibe un enlace, no una tarea duplicada.

Clasifica todo requisito u objeción en tres carriles:

1. **cierre estricto:** falsifica el predicado actual o introduce una regresión
   alcanzable dentro de su alcance;
2. **hardening proporcional:** reduce un riesgo vecino sin ser necesario para
   cerrar el caso actual;
3. **arquitectura más amplia:** promete una garantía nueva de durabilidad,
   portabilidad, recuperación, observabilidad o generalidad.

Sólo el primer carril entra automáticamente al encargo de implementación. Los
otros se enlazan a su owner o quedan como propuestas separadas; requieren un
caso alcanzable, un consumidor concreto o adopción explícita antes de crear
trabajo nuevo. El riesgo aumenta la profundidad de la prueba, no la superficie
de la solución.

No descartes P2/P3 al sacarlos del cierre estricto. Antes de entregar el
slice, regístralos de forma durable en el issue de seguimiento ya acordado o,
si no hay tracker en alcance, en ADR/handoff: severidad, evidencia
`fichero:línea` o reproducción, alcance afectado, owner/destino y condición
concreta que obliga a reevaluarlo. El veredicto debe separar “no bloquea este
predicado” de “no existe”. Un P2/P3 puede subir a P1 si cambia el consumidor,
la exposición o el contrato; su registro es precisamente lo que permite
evaluarlo después. Si el P2/P3 documenta una simplificación deliberada, añade
su techo aceptado y evidencia positiva de que ese techo no puede falsificar el
predicado actual; nombrar un trigger u owner nunca convierte en deuda futura una
violación ya alcanzable dentro del cierre estricto.

Antes de abrir worktrees escritores, publica un contrato durable que incluya:

- SHA/base fijados y predicado de cierre;
- invariantes y entrypoints/consumidores alcanzables;
- alcance, no-objetivos y contratos compartidos;
- artefactos permitidos y evidencia requerida;
- un único issue de seguimiento para trabajo no bloqueante.

El diseño adjudicado debe presentarse como el **arreglo completo de menor
footprint**, dividido sólo en las partes necesarias para satisfacer el
predicado. Cada parte debe indicar qué obligación de cierre cumple y qué
superficie existente reutiliza. Menor footprint significa menos superficie y
acoplamiento permanentes, no necesariamente menos líneas: no acepta un parche
local que deje consumidores hermanos alcanzables ni justifica una abstracción
nueva cuando un owner existente puede extenderse. Elimina toda parte que sólo
aporte hardening o arquitectura más amplia y envíala a su carril y owner
correspondientes. Cuando el contrato esté `READY`, resume públicamente la
decisión como **“Proposed fix (N parts, smallest-footprint)”** si ese formato
ayuda a hacer auditable la partición.

La implementación no empieza mientras ese contrato siga viviendo sólo en el
razonamiento del SUPER o en mensajes dispersos. Si cambia, congela una nueva
versión y explica qué evidencia anterior quedó invalidada.

Usa un presupuesto como señal de partición, no como sustituto del juicio. Si el
trabajo previsto supera aproximadamente **25 archivos o 3 contratos
compartidos**, intenta dividirlo en slices que puedan implementarse, probarse,
revertirse y cerrarse de forma independiente. Si la atomicidad del cambio hace
imposible dividirlo, registra esa excepción antes de implementar.

La revisión formal ocurre en tres hitos como máximo:

1. premisa/contrato congelado;
2. diff funcional congelado;
3. SHA exacto final.

No abras otra ronda general por cada commit. Entre hitos, sólo reabre el código
por evidencia nueva y falsificable que sea bloqueante para el predicado —por
defecto un P0/P1 reproducible y alcanzable causado por el diff—, por evidencia
invalidada o porque cambió el contrato. Deuda preexistente, P2, observabilidad y
hardening adicional van al issue de seguimiento. Dos rondas sin una objeción
material nueva son una señal de parada, no una invitación a buscar alcance.

La señal de parada limita rondas, no sustituye la prueba positiva. Para cerrar,
el SUPER debe comprobar que el caso base reproduce por el entrypoint real, el
diff actúa sobre la causa demostrada, el resultado observable satisface el
predicado, la regresión muerde y un control negativo dirigido conserva la
intención relevante en el límite modificado.

Haz la matriz requisito → evidencia → estado antes de presentar el PR como
terminado, no después. Un requisito sin evidencia directa queda pendiente o
fuera de alcance de forma explícita.

## Entrega cerrada y presupuesto de rondas

Para un slice de alto riesgo con contrato cerrado, convierte la matriz antes
de implementar en un **manifiesto ejecutable de aceptación**. Cada fila debe
tener: invariante o diagnóstico, escenario mínimo, prueba prevista (archivo y
nombre), motor requerido (SQLite, PostgreSQL, navegador u otro), evidencia de
efecto y estado. Incluye explícitamente las rutas negativas, mutaciones de
fuentes prohibidas y la propagación de diagnósticos cuando sean parte del
contrato. No uses una lista narrativa como sustituto de esas filas.

El implementador hace una autoauditoría fila por fila antes de congelar el
diff. Una entrega no está lista si alguna fila contractual sólo tiene una idea
de prueba, una prueba omitida o una afirmación no ejecutada. Los checkpoints
son para bloqueos reales; no se presentan como entregas ni disparan revisiones
formales. El revisor ciego compara el manifiesto contra el diff y los tests,
no sólo contra el código de producto.

Presupuesta **una entrega funcional congelada y una corrección P0/P1**. Si la
revisión descubre en esa corrección una fila que debió estar en el manifiesto,
no encadenes micro-entregas: vuelve el slice a `READY`, corrige el manifiesto
una vez y exige una nueva entrega completa. Si vuelve a ocurrir, adjudica una
partición del slice o eleva una decisión de alcance; no conviertas la misma
rama en revisión continua. Esta regla no impide arreglar un P0/P1 real, pero
evita que deuda de evidencia se disfrace de progreso.

La suite integrada se ejecuta una sola vez, sobre el SHA que ya pasó la
revisión ciega y cuya matriz está completa. No la uses para descubrir filas
de aceptación faltantes.

## Reparto y aislamiento

| Guare | Responsabilidad |
|---|---|
| **Reconocimiento** | Devuelve hechos verificables, incluido `fichero:línea`, entrypoint y controles. |
| **Adversario técnico** *(condicional)* | Intenta falsificar premisa, contrato o diseño antes del código. |
| **Implementador** | Implementa el alcance adjudicado y sus pruebas. |
| **Revisor ciego** | Ataca sólo el encargo y el diff resultante, sin el razonamiento del implementador. |

El implementador y el revisor ciego son personas/agentes distintos. Cada guare
que modifica usa su propio worktree aislado y preserva los cambios ajenos. El
SUPER tampoco convierte una respuesta de un modelo en evidencia: abre las
citas, ejecuta o inspecciona las comprobaciones necesarias y adjudica él mismo.

Activa `adversarial-technical-review` si la premisa está disputada o se cruza
durabilidad, identidad/generación, concurrencia, recuperación, seguridad,
migración o un efecto difícil de revertir. Esa skill contiene los prompts,
perfiles y protocolo detallado. Aquí basta una pregunta congelada, evidencia
actual, invariantes, no-objetivos y condición de cierre; sólo `READY` permite
la implementación. La revisión adversaria previa nunca reemplaza la revisión
ciega del diff.

## Secuencia

1. **Reconocer y decidir.** Aplica la puerta de premisa. Declara `READY`,
   `HOLD` o `REJECT` con el ledger y el predicado de cierre.
2. **Atacar si corresponde.** Da al adversario el mismo artefacto fijado. El
   SUPER verifica las objeciones, estrecha/corrige/rechaza y reemite `READY`,
   `HOLD` o `REJECT`; no despacha implementación salvo `READY`.
3. **Implementar.** El guare implementa sólo lo adjudicado. La prueba de
   regresión atraviesa el entrypoint real, falla antes del cambio cuando sea
   posible y contiene un control negativo; pruebas de snapshots de helpers no
   bastan. Comprueba que el test muerde degradando la conducta protegida cuando
   sea seguro hacerlo.
4. **Revisar a ciegas.** Entrega al revisor diff, contrato e identificadores
   inmutables de árbol/base/head, no la explicación del implementador. Debe
   verificarlos: discrepancia es `no pude mirar` y `HOLD`, no revisión. Luego
   busca rutas alcanzables y consumidores hermanos sólo cuando comparten causa,
   contrato/señal, límite de decisión, invariante autoritativo o el mismo
   resultado prohibido; luego contrasta el efecto prometido con el observado.
5. **Adjudicar.** El SUPER verifica citas, estado y resultados contra el árbol
   actual. Un comando sin error no prueba efecto: vuelve a consultar el estado
   o mide la consecuencia que exige el predicado. Clasifica cada objeción como
   `CONFIRMED`, `SUSPECTED` o `REJECTED`.

Si aparece una frontera independiente durante la ejecución, detén la expansión
del alcance. Registra la dependencia y deja ese incremento como seguimiento;
no lo disfraces como cierre del contrato original. Una mejora parcial debe
decirse parcial aunque deje el sistema mejor que antes.

## Trampas medidas

Todas costaron un incidente real. Comparten forma: **algo que parece una
respuesta y en realidad es `no pude mirar`**.

### Un revisor mudo y un revisor que aprueba son indistinguibles

La CLI de un motor externo puede **salir con código 0 habiendo fallado**. Se ha
visto con `402 balance exhausted`, con `Not signed in` y con `stopReason:
cancelled` + `max turns reached` — este último devolviendo **hallazgos
alucinados** y a medias, dentro del campo de razonamiento.

Antes de creerte una revisión, comprueba en su salida estructurada que **no hay
campo de error**, que **el texto no está vacío** y que **terminó limpiamente**.
Cualquiera de los tres es `no pude mirar`, nunca «no encontró nada». Y dale un
diff **acotado**: uno grande con pocos turnos se trunca en silencio.

### El aislamiento que no aísla

Un motor externo puede ignorar su propia opción de worktree, trabajar en el
directorio activo y **mover la rama** (se observó un `git reset` que sacó de la
rama un commit ya hecho; nada se perdió, pero el aislamiento no existió).

**Crea tú el worktree** y apúntale ahí. Deniega además los comandos que pueden
mover la rama —`reset`, `checkout`, `stash`, `push`—: valen como barrera y
documentan la intención. Comprueba el aislamiento **después** de lanzarlo, no
lo des por hecho.

Un worktree recién creado suele tener el árbol de dependencias vacío: la suite
falla por eso y **se lee como fallo de código**. Enlázalo o instálalo antes.

### Lo que el revisor no ve

Los **ficheros nuevos sin trackear no aparecen en el diff**, y suelen ser justo
los tests cuya solidez quieres juzgar. Pásale sus rutas explícitamente.

Y **no toques el árbol mientras el revisor lo lee**: verá un estado intermedio
y dictaminará sobre algo que ya no existe. Congélalo o dale un snapshot.

### Ruido de fondo: mide la línea base antes de tocar nada

En un entorno degradado (sin base de datos, sin credenciales) una suite amplia
puede salir masivamente roja **por el entorno**, y ese total no es señal de
nada por sí solo. Mide los rojos **antes** de empezar, y cuando dudes de si un
rojo es tuyo, haz el **diferencial contra la base**: mismo comando en un árbol
limpio y compara conjuntos. Una diferencia de un fichero localiza la causa que
tres hipótesis plausibles no encuentran.

Corolario: **verde en lo que miras no dice nada de lo que no miras.** Una
tanda dirigida puede pasar entera mientras un pin global —un inventario de
símbolos, un fichero generado, un contrato de esquema— se rompe por un método
nuevo. Si el cambio amplía una superficie pineada, regenera el pin y comprueba
que el diff es **sólo lo tuyo**.

### Citas y referencias inventadas

Un guare puede citar un `fichero:línea` que no dice eso, o **inventarse el
número de un issue**. Abre la cita; si referencia algo del tracker,
compruébalo contra el tracker. Ya ocurrió y sólo se detectó porque el número
chirrió contra los del encargo.

### Un hallazgo cierto puede venir con un encuadre falso

Adjudica las dos cosas por separado. Un adversario señaló correctamente un
riesgo de longitud en un identificador **y lo encuadró como «este cambio lo
rompe»**, cuando el sistema ya emitía identificadores mucho más largos por
otras vías: el defecto era preexistente y sistémico, no introducido. Aceptar el
encuadre habría bloqueado el trabajo correcto y dejado el problema real sin
registrar.

Igual de importante: **rechaza lo cierto pero fuera de alcance**, con razón
escrita y registrado como seguimiento. Un adversario que sólo suma trabajo al
contrato en curso deja de ser útil.

### El informe que llega al sitio equivocado

Si un guare dirige su entrega al **tipo** de agente en vez de a su
identificador, el envío falla y su informe **aparece en el padre del SUPER**.
No es trabajo perdido: reenvíalo al SUPER en vez de mandar rehacerlo.

## Repartir entre varios SUPER

Cuando el trabajo pendiente son varios frentes, **reparte por colisión de
ficheros, no por issue**. Dos frentes que tocan el mismo fichero no pueden ir
en paralelo: cada rama se verificaría contra una base sin la otra, y al
integrar la segunda los pines de la primera quedan **sin comprobar sobre el
código real**. En un fichero sensible eso es exactamente un verde que no
significa nada.

Antes de repartir, **verifica dónde vive de verdad cada arreglo**, no dónde
parece por el título del issue: un frente que parecía tocar una capa distinta
resultó vivir en el mismo fichero que el resto, y el reparto «en paralelo» era
inválido. Une esos frentes en un solo encargo y una sola entrega.

Vigila también los recursos con **numeración global compartida** —migraciones,
secuencias, ficheros generados—: dos frentes paralelos pueden reclamar el mismo
número sin que nada lo detecte. Asigna el número explícitamente en cada encargo
o serializa esos frentes.

Y separa lo que **no puede resolver ningún agente**: una decisión de producto,
o un hecho que sólo se establece contra un sistema externo. Eso se sube a quien
decide, no se delega disfrazado de tarea técnica.

## Salida del SUPER

Entrega una decisión breve y auditable:

- árbol/SHA y evidencia que el SUPER comprobó personalmente;
- ledger `Observed/Confirmed/Control/Inference/Decision`;
- predicado de cierre, alcance y no-objetivos;
- mapa de ownership y clasificación `cierre estricto / hardening / arquitectura`;
- hallazgos del adversario y del revisor ciego, con adjudicación;
- disposición previa: `READY`, `HOLD` o `REJECT`;
- veredicto final: `ok` (predicado satisfecho), `no-ok` (no satisfecho, aun
  con valor parcial) o `no pude mirar` (no verificable);
- si es parcial, qué valor añade y qué condición de cierre sigue pendiente;
- riesgos y verificaciones que quedaron como `no pude mirar`;
- veredicto separado para el cierre estricto y enlaces a follow-ups ya
  existentes, sin convertirlos en bloqueantes.

No declares terminado por votos, por una prueba auxiliar verde ni porque un
comando acabó sin error. Decláralo sólo cuando el efecto observable satisfaga
el predicado de cierre sobre el árbol que se está adjudicando.

## Calibración del skill

Esta sección no forma parte de una ejecución ordinaria. Al modificar las reglas
de decisión de `super-guare`, lee y ejecuta el protocolo offline de
[calibración conductual](references/behavioral-calibration.md). Sus resultados
detectan regresiones del playbook; nunca deciden hechos, ownership ni cierre de
un árbol vivo.
