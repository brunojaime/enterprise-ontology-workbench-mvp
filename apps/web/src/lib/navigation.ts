export interface NavigationItem {
  href: string;
  label: string;
  marker: string;
}

export const primaryNavigation: NavigationItem[] = [
  { href: '/', label: 'Dashboard', marker: 'DB' },
  { href: '/graph', label: 'Grafo', marker: 'GR' },
  { href: '/modules', label: 'Módulos', marker: 'MO' },
  { href: '/validation', label: 'Validación y diff', marker: 'VD' },
  { href: '/queries', label: 'Consultas', marker: 'CQ' },
  { href: '/agents', label: 'Agentes', marker: 'AG' }
];

export function graphHref(iri: string, module = ''): string {
  const params = new URLSearchParams({ focus: iri });
  if (module) params.set('module', module);
  return `/graph?${params.toString()}`;
}
