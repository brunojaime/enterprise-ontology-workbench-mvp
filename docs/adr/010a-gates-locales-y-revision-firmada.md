# ADR 010A: Gates locales y revisión humana firmada

- Estado: Aceptado
- Fecha: 2026-08-16
- Alcance: gobierno vigente del MVP y P12
- Reemplaza: ADR 010

## Contexto

El gobierno original dependía de pull requests, GitHub Actions y un ruleset
remoto. En el piloto P12 los jobs no llegaron a un runner por una restricción
de billing, aunque las mismas validaciones aprobaron localmente. El responsable
del producto decidió que el proceso no debe depender de GitHub Actions y que
los gates deben ejecutarse localmente.

La sustitución no puede rebajar controles, confundir validación técnica con
aprobación humana ni habilitar escrituras del agente sobre `main`.

## Decisión

1. Git y RDF continúan siendo las fuentes canónicas.
2. Toda autoría ocurre en `proposal/*`; el gate exige worktree limpio y fija
   branch, HEAD, base commit y fingerprint RDF.
3. Tests, lint, formato, type checks, builds, RDF/SHACL, contrato de agentes,
   diff semántico y gates específicos se ejecutan mediante scripts locales.
4. El gate conserva logs, artifacts y hashes en un bundle auditable; un cambio
   concurrente de branch, HEAD o dirty state aborta.
5. La revisión del especialista y la aprobación de publicación son artifacts
   humanos distintos, ligados al snapshot y verificables mediante firma.
6. Sólo una persona integra `main` y repite los checks post-merge aplicables.
7. GitHub, un remoto y los pull requests son opcionales para colaboración o
   backup. GitHub Actions no participa de la aceptación vigente.

## Consecuencias

- El piloto puede avanzar sin runners ni servicios pagos.
- La reproducibilidad depende de los lockfiles y scripts multiplataforma del
  repositorio.
- Los receipts técnicos bajo `.eow/` deben respaldarse en el handoff si el host
  no es durable.
- La identidad y autoridad humanas no se infieren del usuario Git. Se requiere
  una firma verificable y una declaración de rol/alcance.
- Las workflows históricas dejan de estar activas; Git conserva su historia.

## Alternativas consideradas

- Mantener Actions como gate obligatorio: descartado por la dependencia externa
  demostrada en P12.
- Aceptar una afirmación del agente o un JSON sin firma: descartado porque no
  demuestra autoridad humana.
- Permitir merge automático después de checks locales: descartado porque una
  validación técnica no decide corrección semántica.

## Trazabilidad

- Especificación: secciones 3.1, 4, 9.6, 18.6, 30.3, 34 y Plan 12.
- Backlog: P12_T05 y P12_T06.
- Operación: `docs/local-governance.md` y `scripts/run_local_gate.py`.
