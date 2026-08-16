# Gobierno local de propuestas

Git y RDF siguen siendo canónicos. El gate operativo se ejecuta en el checkout
local y no depende de GitHub Actions, runners, billing ni conectividad. Un pull
request es opcional para colaboración remota; no es un gate de aceptación.

## Gate técnico

El gate sólo acepta una rama `proposal/*`, un `HEAD` fijo y un worktree limpio.
En Bash:

```bash
./scripts/local_gate.sh --include-smoke --record-git-note
```

En PowerShell:

```powershell
./scripts/local_gate.ps1 --include-smoke --record-git-note
```

El perfil completo ejecuta tests Python y frontend, lint, formato, type checks,
builds, RDF/SHACL, sincronización del contrato, evaluación de agentes, smoke de
contenedores y el reporte semántico contra `main`. Si la rama, el `HEAD` o el
dirty state cambian durante la ejecución, el gate falla cerrado.

Cada ejecución queda bajo `.eow/local-gates/` con logs, artifacts semánticos y
un `receipt.json`. El receipt fija branch, HEAD, base commit, fingerprint de
`knowledge/` + `config/`, comandos, códigos de salida y SHA-256 de todos los
archivos. `.eow/` no es fuente canónica y debe respaldarse junto con el handoff
si se necesita conservar la ejecución fuera del host.

Con `--record-git-note`, un gate conforme agrega bajo
`refs/notes/eow-local-gates` el path y SHA-256 del receipt ligados al commit sin
modificar el tree validado. Se inspecciona con:

```bash
git notes --ref=eow-local-gates show HEAD
```

La note no contiene ni reemplaza una firma humana.

Pasar el gate es únicamente evidencia técnica. Nunca constituye revisión de
dominio, aprobación de publicación ni autorización para fusionar `main`.

## Revisión humana local

La revisión del especialista de dominio y la aprobación de publicación son dos
actos distintos. Cada una debe identificar:

1. Nombre, rol y autoridad ejercida.
2. Rama, commit y fingerprint RDF revisados.
3. Decisiones, correcciones y rationale.
4. Timestamp y digest del receipt técnico aplicable.
5. Una firma verificable, por ejemplo un tag Git firmado que apunte al commit
   exacto y cuyo mensaje contenga esos campos.

La identidad criptográfica debe corresponder a una autoridad conocida por el
proyecto. Un owner RDF, el autor textual de un commit o un JSON generado por el
agente no prueban por sí solos que el especialista aprobó la semántica.

Flujo de referencia para una persona con firma Git ya configurada:

```bash
git tag -s review/p12-domain-<commit-corto> <commit> -m '<decisiones y autoridad>'
git verify-tag review/p12-domain-<commit-corto>
git tag -s review/p12-publication-<commit-corto> <commit> -m '<receipt y autorización>'
git verify-tag review/p12-publication-<commit-corto>
```

La herramienta sólo prepara artifacts. La persona verifica las firmas,
inspecciona el diff y realiza la integración local. El agente nunca fusiona `main`
ni presenta una firma técnica como aprobación humana.

## Integración y recuperación

La integración local requiere gate conforme, revisión de dominio verificable y
aprobación de publicación separada. Después del merge humano se repiten
validación, pregunta de competencia y smoke sobre `main`. Un remoto Git puede
usarse para backup o colaboración, pero no altera estas condiciones.

Ante un fallo se conserva la rama de propuesta, el receipt fallido y sus logs.
No se omiten checks ni se modifica `main` para “destrabar” la publicación.
