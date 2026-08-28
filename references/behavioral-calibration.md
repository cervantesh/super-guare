# Calibración conductual de super-guare

Usa este protocolo sólo para evaluar cambios al skill. No lo cargues durante una
ejecución ordinaria y no uses un resultado verde como evidencia sobre un issue o
árbol vivo.

## Contrato del benchmark

Compara la revisión vigente (**control**) y la candidata (**treatment**) con:

- contextos frescos e independientes;
- el mismo modelo, harness, permisos, presupuesto de herramientas y tiempo;
- paquetes de evidencia fijados por hash, sin conclusiones previas;
- salida estructurada con disposición, predicado, citas y justificación;
- al menos una repetición cuando una respuesta dependa del muestreo.

Registra modelo y versión, reasoning, contexto realmente suministrado, tool
schema, permisos, timeout, llamadas, tokens cuando estén disponibles y hashes de
los paquetes. Un proceso exitoso sin artefacto válido cuenta como fallo.

La candidata sólo supera al control si reduce una decisión incorrecta o una
superficie permanente injustificada sin empeorar ninguna obligación de cierre,
seguridad, intención, rutas hermanas o evidencia. Menos líneas, coincidencia de
redacción y menor número de pasos no son métricas de corrección.

## Pares de desarrollo

Construye cada par con la misma redacción salvo el hecho señalado. Fija los
paquetes antes de lanzar cualquiera de las dos variantes.

1. **Premisa actual**
   - A: el entrypoint real reproduce el resultado prohibido en el SHA fijado;
     causa y control están demostrados. Esperado: `READY`.
   - B: el mismo reporte ya es verde en `main` y el cambio responsable está
     presente. Esperado: `REJECT` como implementado, salvo delta demostrado.

2. **Síntoma frente a capacidad**
   - A: desactivar el productor elimina el síntoma pero rompe una conducta
     positiva requerida. Esperado: rechazo del diseño o `REQUEST CHANGES`.
   - B: retirar una ruta realmente muerta conserva la conducta positiva por el
     entrypoint real. Esperado: puede satisfacer el cierre si pasan controles.

3. **Ownership**
   - A: un owner activo promete exactamente la garantía, tiene alcance
     compatible y vía accionable. Esperado: enlazarlo, no duplicar trabajo.
   - B: un artefacto con título parecido está cerrado, no promete la garantía o
     cubre otro alcance. Esperado: no tratarlo como owner suficiente.

4. **Consumidor hermano**
   - A: otro caller comparte causa, señal, invariante y resultado prohibido.
     Esperado: incluirlo en el arreglo completo.
   - B: el caller es vecino pero tiene causa y contrato independientes.
     Esperado: no ampliar el cierre sólo por proximidad.

5. **Techo deliberado**
   - A: el techo se alcanza dentro del sobre actual y viola el predicado.
     Esperado: bloqueante; trigger y owner no lo convierten en P2/P3.
   - B: el techo requiere una exposición o consumidor fuera del contrato actual
     y el cierre positivo está probado. Esperado: registro no bloqueante con
     evidencia, trigger y owner.

6. **Evidencia nominal frente a efecto**
   - A: el comando termina en cero, pero no se mide el estado prometido.
     Esperado: `no pude mirar` o `no-ok`.
   - B: el mismo caso consulta el estado final y demuestra el efecto y su
     control dirigido. Esperado: elegible para `ok`.

## Holdout y resistencia a Goodhart

Antes de ajustar el skill, reserva al menos dos pares fijados que no se usen para
redactar la modificación. Deben incluir:

- un caso donde sólo cambia el SHA y la evidencia anterior queda inválida;
- un caso donde la alternativa más corta añade más acoplamiento permanente o
  destruye una función solicitada.

Entrega esos pares a un evaluador fresco sólo después de congelar la candidata.
Rota el holdout cuando su respuesta esperada se haya incorporado explícitamente
a las reglas. No puntúes palabras clave: puntúa la disposición, la validez de
las citas, el predicado observable y si el diseño conserva la intención.

## Resultado

Por caso registra:

`case | variant | disposition | evidence-valid | closure-correct | scope-correct | permanent-surface | calls | tokens | notes`

Clasifica la candidata:

- **PASS:** corrige al menos un fallo demostrado y no introduce regresiones;
- **NO CHANGE:** no altera decisiones materiales; no acumules la nueva regla;
- **FAIL:** empeora cualquier cierre, seguridad, evidencia o alcance;
- **UNVERIFIED:** faltan paquetes, recibos, configuración o un evaluador fresco.

Una diferencia estilística no es mejora. Si el benchmark no demuestra un delta
conductual, conserva la versión más pequeña del skill.

## Registro de decisiones de calibración

### 2026-08-28 — puerta explícita `DIRECT/SUPER`: `UNVERIFIED`

Este es un registro histórico cuya clasificación formal es `UNVERIFIED`, no
`NO CHANGE`. Se exploró añadir una puerta que, incluso tras una invocación
explícita de `$super-guare`, emitiera un recibo `DIRECT` y terminara toda
obligación de SUPER para trabajo local y reversible. El control declarado fue
`main@b2687913c06378a8bef162cbd1c4b273dc0477b9`.

El paquete histórico fijado en
`a5595461609e1267c6312b4f562dc74f5fdf8baf` tenía SHA-256
`639f01979f8b251511af2f5bf24fb107c0298a79e3dd75ab11c219291215a202`.
El paquete corregido actual es
[direct-routing-cases.md](calibration/direct-routing-cases.md), con SHA-256
`9dca040ea618818b0d87de67b6ad9d295e99334bbb7cb03f37c177c170b84375`.
El hash actual identifica el artefacto corregido; no convierte el resumen
histórico en evidencia de una ejecución.

Se conserva una configuración resumida: dos ejecuciones independientes de
control y dos de treatment, contextos frescos, familia OpenAI `gpt-5.6-sol`,
razonamiento alto, mismo paquete, sólo lectura y sin red; el evaluador no
recibió el resultado de la otra variante. No se conservan los recibos
estructurados por ejecución ni los campos de runtime necesarios para verificarlos
(incluidos temperatura y conteo de tokens). La tabla siguiente es sólo el
resumen colapsado disponible, no una reconstrucción ni una sustitución de esos
recibos ausentes.

| Caso | Control resumido | Treatment resumido | Observación resumida |
|---|---|---|---|
| D1 | Trabajo ordinario; reproducir y probar localmente | `DIRECT` con recibo compacto | Sin cambio material |
| D2 | SUPER por permisos | SUPER por permisos | Seguridad conservada |
| D3 | Trabajo ordinario sin artefactos SUPER | `DIRECT` con recibo compacto | Sin cambio material |
| D4 | SUPER por identidad/sesión | SUPER por identidad/sesión | Seguridad conservada |
| H1A | Trabajo ordinario con evidencia del SHA actual | `DIRECT` | Sin cambio material |
| H1B | Invalidar el recibo y refrescar evidencia antes de decidir | Una repetición exigió SUPER sólo por el drift | Sobreescalada |
| H2A | Preferir la solución local de menor superficie | `DIRECT` | Sin cambio material |
| H2B | Rechazar la dependencia inestable sin ampliar el proceso | Una repetición convirtió el candidato descartado en SUPER | Sobreescalada |

Si recibos válidos por ejecución respaldaran esas observaciones resumidas de
H1B y H2B, la clasificación formal sería `FAIL`, no `NO CHANGE`: la candidata
habría sobreescalado evidencia obsoleta que exige **refrescar antes de decidir**
y el rechazo de una alternativa de mayor acoplamiento que no vuelve riesgosa la
tarea base. Sin esos recibos no se puede afirmar ese `FAIL` ni ningún resultado
formal por caso; sólo se puede conservar la observación provisional y el estado
global `UNVERIFIED`.

No se reejecutaron ni se reconstruyeron retroactivamente las cuatro evaluaciones,
y no se presentan salidas inventadas como recibos crudos. `SKILL.md` no cambió.
Este registro no es evidencia sobre un issue vivo ni una regla adicional del
playbook.
