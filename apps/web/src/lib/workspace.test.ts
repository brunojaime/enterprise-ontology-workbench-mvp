import { describe, expect, it } from 'vitest';

import { workspaceStatus } from './workspace';

describe('workspaceStatus', () => {
  it('reports a configured API as ready', () => {
    expect(workspaceStatus('http://localhost:8000')).toBe('ready');
  });

  it('requires configuration when the API URL is empty', () => {
    expect(workspaceStatus('')).toBe('configuration-required');
  });
});
