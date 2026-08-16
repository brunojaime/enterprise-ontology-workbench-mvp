export const productName = 'Enterprise Ontology Workbench';

export function workspaceStatus(apiBaseUrl: string): string {
  return apiBaseUrl.length > 0 ? 'ready' : 'configuration-required';
}
