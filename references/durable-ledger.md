# Ledger durable de SUPER guare

Usa `scripts/runledger.py` cuando una ejecución de SUPER guare deba sobrevivir
otra sesión o coordinar implementación y revisión independientes. La utilidad
usa sólo la biblioteca estándar de Python, persiste atómicamente y nunca lanza
agentes ni modifica Git.

## Frontera de autoridad

El ledger hace cumplir consistencia del flujo; no establece la verdad de las
declaraciones que recibe.

Es **single-writer**: sólo el SUPER ejecuta comandos mutadores. Los guares
producen findings, pruebas y recibos para que el SUPER los verifique e ingrese.
Cada escritura toma un lock no bloqueante y compara la generación cargada con la
actual; una sesión concurrente u obsoleta se rechaza en vez de sobrescribir
trabajo reconocido.

- El hash del contrato se recalcula desde el fichero y sí detecta drift externo.
- La cobertura criterio→unidad prueba bookkeeping, no implementación.
- `repo`, `base`, `head`, engine y family son pines declarados; el SUPER debe
  verificarlos contra Git y el harness antes de registrarlos.
- Evidence debe ser una línea verificable y segura para publicar. No guardes
  tokens, secretos, datos personales ni logs sin redacción.
- `ok` significa demostrado; `not-ok`, refutado; `undetermined`, no se pudo
  establecer. `undetermined` devuelve código 2 y nunca se redondea a éxito.

El directorio predeterminado es `.super-guare/runs/`. Añádelo a `.gitignore` si
los recibos deben quedarse locales; exporta sólo snapshots redactados cuando el
proyecto necesite un handoff durable.

Al cargar un recibo, el ledger valida tanto los tipos como las relaciones entre
el finding y las rondas persistidas: un origen, confirmación o resolución que
afirme un `head` distinto de la ronda registrada se rechaza como
`Undetermined`. Los recibos v1 que simplemente no contienen ese modelo nuevo
siguen siendo legibles; lo que no pueden hacer es aportar evidencia severa que
el ledger no pueda reconstruir.

## Grafo

```text
premise ─┬─ ready → implement → review → adjudicate → verify → done
         ├─ hold → premise                 ├─ implement
         └─ reject                         ├─ ready
                                            └─ escalated
```

Las fases activas pueden entrar en `hold`. Los terminales son `reject`, `done`
y `escalated`.

## Inicio y contrato

Los argumentos globales van antes del comando:

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 init \
  --title "Repair session persistence" \
  --repo owner/repo --base <base-sha> --head <head-sha>

python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  pin-contract --file .local/super-guare/SG-001/contract.md

python scripts/runledger.py --dir .super-guare/runs --run SG-001 enter ready
```

`ready` requiere contrato legible y todos los checks conocidos en `ok`. Antes
de cada entrada a `implement`, `review`, `verify` o `done`, el contrato se vuelve
a leer. Si su SHA-256 cambió, la transición se rechaza hasta adjudicar y fijar la
nueva versión con `pin-contract`.

`pin-contract` sólo funciona en `premise` o `adjudicate`. Volver a fijarlo en
adjudicación invalida implementación y review: no se puede llegar a `verify`
hasta repetir ambos sobre el contrato nuevo.

## Roles y árbol revisado

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  assign-role --name implementer --engine codex --family openai
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  assign-role --name reviewer --engine claude --family anthropic
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  tree --base <base-sha> --head <exact-reviewed-head>
```

Entrar en `review` requiere ambas familias conocidas y diferentes, además de
repo/base/head no vacíos. El ledger no consulta el forge: el SUPER verifica esos
pines antes de registrarlos. Cambiar árbol o roles desde `adjudicate` invalida
el review anterior y exige otro ciclo `implement → review`.

## Criterios y unidades

La ruta plana no necesita unidades. Si se declara una sola unidad, se activa la
comprobación completa de cobertura:

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  add-criterion --id AC1 --text "Malformed state remains repairable"
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  add-criterion --id AC2 --text "Clean sessions remain unchanged"
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  add-unit --id persistence --covers AC1,AC2
```

Una unidad sin criterio, un criterio requerido sin unidad o una dependencia a
una unidad inexistente —incluido un ciclo— bloquean `implement`. Criterios,
deferrals y unidades sólo cambian en `premise` o `adjudicate`; un cambio en
adjudicación exige implementación y review nuevos. Diferir un criterio exige
razón:

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  defer-criterion --id AC2 --reason "Verified follow-up owns this independent boundary"
```

## Checks ternarios

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  check --name reproduction --verdict ok --evidence "test_x: RED on <base-sha>"
```

Cualquier `not-ok` o `undetermined` bloquea las entradas protegidas. El comando
que registra `undetermined` persiste el recibo y devuelve código 2. Repite el
mismo nombre para sustituir el estado actual cuando exista evidencia nueva; el
historial conserva todos los resultados anteriores.

El check reservado `effect` sólo puede registrarse dentro de la fase `verify`.
Cada nueva entrada a `verify` elimina el anterior, evitando cerrar con evidencia
de una entrega previa. Salir de `verify` hacia `adjudicate` o `hold` también
limpia el estado actual para permitir corrección o reanudación; el recibo fallido
permanece en el historial.

## Findings, identidad y convergencia

Cada aparición tiene `id`; el defecto estable entre rondas tiene `defect-id`:

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  add-finding --id F1 --defect-id DB-LOSS --severity P0 \
  --summary "Committed write can disappear"
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  decide-finding --id F1 --decision confirmed
```

La ronda no es un dato del revisor: el ledger la incrementa al entrar en
`review` y fija el `head` que esa ronda revisó. Al crear un finding guarda por
separado el `head` de su ronda de origen; al confirmarlo guarda la ronda de
confirmación; y al resolverlo guarda el `head` y la ronda que aportaron la
evidencia de resolución. Un P0/P1 no resuelto o no adjudicado bloquea `verify`.

Para un P0/P1 confirmado, `verify` sólo lo considera cerrado si el origen y la
confirmación son conocidos, una revisión posterior a la confirmación revisó un
`head` distinto del origen y el árbol actual sigue siendo exactamente el
`head` al que se ligó la resolución. Cambiar árbol, plan o roles después de
revisar invalida esa evidencia hasta otra revisión; volver después al `head`
de origen reabre el finding. La obligación persiste si el finding pasa de
`confirmed` a `suspected`; sólo `rejected` la deja sin efecto y una nueva
confirmación fija un nuevo momento de confirmación. Un recibo v1 heredado sin
origen, momento o historial de confirmación reconstruible continúa cargando,
pero no puede resolver un P0/P1: queda `Undetermined` en vez de inferir una
prueba ausente.
Después de corregirlo:

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  resolve-finding --id F1 --evidence "regression passes and mutation fails"
```

Por defecto hay dos rondas: entrega inicial y una corrección. Si el mismo
`defect-id` reaparece hasta consumirlas, o se agota el presupuesto con defectos
severos, otra entrada a `implement` se rechaza aunque se intente pasar por
`ready`. Corresponde reespecificar, particionar o escalar.

## Verificación y cierre

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 enter verify
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  check --name effect --verdict ok \
  --evidence "real entrypoint returns durable repaired state on <head-sha>"
python scripts/runledger.py --dir .super-guare/runs --run SG-001 enter done
```

`done` exige contrato vigente, ningún P0/P1 abierto y `effect=ok` obtenido en la
fase `verify` actual.

## Estado y snapshot

```bash
python scripts/runledger.py --dir .super-guare/runs --run SG-001 show
python scripts/runledger.py --dir .super-guare/runs --run SG-001 \
  snapshot --out .local/super-guare/SG-001/snapshot.json
```

El snapshot separa estructura —nodo, camino, próximos edges y presupuesto— de
contenido —árbol, hash del contrato, roles, criterios, unidades, checks,
findings severos y rondas—. Es el artefacto preferido para reanudar o auditar.
El destino no puede ser el `run.json` activo. Los nodos terminales son
inmutables; snapshot y `show` continúan disponibles porque son sólo lectura.

## Relación con Lider

El diseño adopta conceptos públicos de
[T50-Systems/lider](https://github.com/T50-Systems/lider): ledger como árbitro,
drift del spec, findings con identidad, checks ternarios y snapshot. No copia su
código ni sustituye su runtime.

Si Lider está instalado y se necesita supervisar CLIs externos —heartbeat,
watchdogs, process-tree teardown o retry desde checkpoint limpio— usa su runtime
en lugar de recrear esas garantías aquí. `runledger.py` permanece como guard
portable del contrato específico de SUPER guare.
