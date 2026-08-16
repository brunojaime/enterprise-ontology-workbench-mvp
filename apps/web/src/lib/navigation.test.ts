import { describe, expect, it } from 'vitest';

import { graphHref, primaryNavigation } from './navigation';

describe('primary navigation', () => {
  it('exposes the six principal workbench areas with unique routes', () => {
    expect(primaryNavigation).toHaveLength(6);
    expect(new Set(primaryNavigation.map((item) => item.href)).size).toBe(6);
    expect(primaryNavigation.map((item) => item.label)).toEqual([
      'Dashboard',
      'Grafo',
      'Módulos',
      'Validación y diff',
      'Consultas',
      'Agentes'
    ]);
  });

  it('builds an encoded graph focus without losing the module filter', () => {
    expect(graphHref('https://example.test/vocab#A B', 'software')).toBe(
      '/graph?focus=https%3A%2F%2Fexample.test%2Fvocab%23A+B&module=software'
    );
  });
});
