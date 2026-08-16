# ADR 002: Ontologías modulares sin entidad raíz empresarial

- Estado: Aceptado
- Fecha: 2026-08-11
- Alcance: MVP

## Contexto

La base debe conectar conocimiento de organización, procesos, activos, datos,
software y futuros dominios sin suponer que uno de ellos organiza a todos los
demás. Elegir `Application`, `Solution`, `Pump`, `Well` u otra clase como raíz
empresarial introduciría una jerarquía artificial y favorecería una ontología
monolítica.

El producto también debe permitir que dominios acotados evolucionen a ritmos
distintos, con responsables identificables y sin redefiniciones accidentales.

## Decisión

La ontología empresarial se organiza en módulos pequeños, relacionados mediante
IRIs e imports explícitos, y no tiene una única entidad raíz empresarial.

Para el MVP se aplican estas reglas:

1. Cada clase o propiedad tiene exactamente un módulo responsable que la
   define.
2. Otros módulos pueden referenciarla o importarla, pero no redefinirla.
3. Los imports forman dependencias explícitas y no pueden contener ciclos.
4. Un módulo nuevo se justifica con una necesidad real y preguntas de
   competencia, no con una taxonomía empresarial anticipada.
5. Modelo ontológico, hechos y propuestas se mantienen separados.
6. Los vínculos entre dominios usan relaciones con significado preciso; no crean
   una jerarquía raíz implícita.

La selección de módulos concretos del piloto no forma parte de este ADR.

## Consecuencias

- Los módulos pueden evolucionar y revisarse con un alcance comprensible.
- Deben existir metadata de módulo, ownership, imports y validaciones contra
  redefiniciones y ciclos.
- Las consultas transversales recorrerán relaciones entre módulos en lugar de
  depender de una clase universal.
- La modularidad agrega trabajo de diseño sobre límites e imports; ese costo se
  acepta para evitar mezcla semántica y acoplamiento global.
- Los fixtures de los primeros módulos serán ejemplos mínimos, no una ontología
  empresarial definitiva.

## Alternativas consideradas

- Una ontología monolítica: descartada por su ownership difuso y mayor riesgo de
  conflictos y acoplamiento.
- Un modelo centrado en software: descartado porque software es solo un dominio
  del conocimiento empresarial.
- Módulos sin responsable único: descartados porque permiten definiciones
  divergentes del mismo término.

## Trazabilidad

- Especificación: secciones 3.4, 6.1, 6.4, 6.5, 6.11, 10, 11 y 16.
- Backlog: `P00_T02`, ADR 002.
