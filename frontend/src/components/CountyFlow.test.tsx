/** Opt-in real frozen-data flow through React, direct /runs transport and the actual ASGI API. */
import { spawn } from 'node:child_process';
import { cpSync, mkdirSync, mkdtempSync, rmSync, symlinkSync } from 'node:fs';
import { createInterface } from 'node:readline';
import { resolve } from 'node:path';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import type { CandidateMapProps } from '../map/CandidateMap';
import { createMonteCarloApi } from '../api/monteCarlo';
import App from '../App';

const selected = vi.hoisted(() => ({ api: null as ReturnType<typeof createMonteCarloApi> | null }));
vi.mock('../api/client', () => ({ isDemoMode: false, locatorApi: {
  /** Delegate workspace operations to the actual county adapter selected by this test. */
  capabilities: (...args: Parameters<ReturnType<typeof createMonteCarloApi>['capabilities']>) => selected.api!.capabilities(...args),
  /** Keep submission on the production adapter; no model data is injected into React. */
  search: (...args: Parameters<ReturnType<typeof createMonteCarloApi>['search']>) => selected.api!.search(...args),
  /** Restore scenarios through the same backend run contract. */
  run: (...args: Parameters<ReturnType<typeof createMonteCarloApi>['run']>) => selected.api!.run(...args),
  /** Preserve explicit unavailable-layer behavior. */
  layer: (...args: Parameters<ReturnType<typeof createMonteCarloApi>['layer']>) => selected.api!.layer(...args),
} }));
// The sandbox cannot run WebGL/TCP; keep real geography props while isolating only the map renderer.
vi.mock('../map/CandidateMap', () => ({ CandidateMap: (props: CandidateMapProps) => <div aria-label="County map test transport">{props.regions.map(region => <button key={region.id} onClick={() => props.onSelect(region.id)}>County point {region.id}</button>)}</div> }));

afterEach(() => { cleanup(); vi.unstubAllGlobals(); selected.api = null; });

it.skipIf(!process.env.DATACLOCATOR_TEST_PYTHON)('submits a real county run, renders frozen evidence, restores its scenario and shows a valid empty verified set', async () => {
  // Vitest rewrites import.meta.url to HTTP; the npm test command owns this frontend cwd.
  const script = resolve(process.cwd(), 'scripts/asgi_test_bridge.py');
  const backend = resolve(process.cwd(), '../backend/dataclocator');
  const scratch = resolve(process.cwd(), '../.pytest-work/pr1-frontend');
  mkdirSync(scratch, { recursive: true });
  const temporary = mkdtempSync(resolve(scratch, 'county-flow-'));
  // Freeze real official inputs into a fresh test root; no synthetic or precompleted runs are used.
  symlinkSync(resolve(backend, 'data'), resolve(temporary, 'data'), process.platform === 'win32' ? 'junction' : 'dir');
  // Preserve every derived artifact named by the checksum-bound preprocessing manifest.
  cpSync(resolve(backend, 'outputs/task2'), resolve(temporary, 'outputs/task2'), { recursive: true });
  symlinkSync(resolve(backend, 'configs'), resolve(temporary, 'configs'), process.platform === 'win32' ? 'junction' : 'dir');
  const child = spawn(process.env.DATACLOCATOR_TEST_PYTHON!, [script], {
    stdio: ['pipe', 'pipe', 'pipe'], env: { ...process.env, DATACLOCATOR_TEST_ROOT: temporary },
  });
  const lines = createInterface({ input: child.stdout });
  let logs = '';
  child.stderr.on('data', chunk => { logs += String(chunk); });
  const queue: string[] = [];
  const readers: ((line: string) => void)[] = [];
  const shutdown = new Promise<void>(resolve => child.on('close', () => resolve()));
  lines.on('line', line => { const reader = readers.shift(); if (reader) reader(line); else queue.push(line); });

  /** Consume one protocol response with a timeout, retaining server logs on failure. */
  const next = () => new Promise<string>((resolve, reject) => {
    if (queue.length) { resolve(queue.shift()!); return; }
    const timer = setTimeout(() => reject(new Error(`ASGI test transport timed out: ${logs}`)), 30000);
    readers.push(line => { clearTimeout(timer); resolve(line); });
  });
  let serial = Promise.resolve();
  try {
    expect(JSON.parse(await next())).toEqual({ ready: true });
    // Serialize test IPC while preserving the adapter's four-request bounded snapshot fan-out.
    vi.stubGlobal('fetch', (url: string, options: RequestInit = {}) => {
      const operation = serial.then(async () => {
        if (options.signal?.aborted) throw new DOMException('Canceled', 'AbortError');
        child.stdin.write(JSON.stringify({ path: new URL(url).pathname, method: options.method ?? 'GET', body: options.body }) + '\n');
        const response = JSON.parse(await next());
        return new Response(JSON.stringify(response.body), { status: response.status, headers: { 'Content-Type': 'application/json' } });
      });
      serial = operation.then(() => undefined, () => undefined);
      return operation;
    });
    selected.api = createMonteCarloApi('http://asgi.test', 10);
    window.history.replaceState({}, '', '/?model=county');
    window.matchMedia = vi.fn().mockImplementation(query => ({ matches: false, media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
    render(<App />);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Find locations' })).toBeEnabled(), { timeout: 30000 });
    await userEvent.click(screen.getByText('More options'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Screening policy' }), 'EXPLORATORY');
    // Use a 32-draw debugging workload on all official counties, with explicit audit skips.
    await userEvent.click(screen.getByText('Review / edit complete model JSON'));
    const editor = screen.getByRole('textbox', { name: 'Monte Carlo model settings' });
    const config = JSON.parse((editor as HTMLTextAreaElement).value);
    config.simulation_count = 32;
    config.bootstrap_resamples = 20;
    config.scenario_set = [config.scenario_set[4]];
    fireEvent.change(editor, { target: { value: JSON.stringify(config) } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Operating lifetime years' }), { target: { value: '3' } });
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run sensitivity audit' }));
    await userEvent.click(screen.getByRole('checkbox', { name: 'Run 1k / 5k / 10k convergence audit' }));
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    expect(screen.getByRole('status', { name: 'Evaluation status' })).toHaveTextContent('Preparing request');
    const point = await screen.findByRole('button', { name: 'County point 01089' }, { timeout: 45000 });
    expect(screen.getAllByRole('button', { name: /County point/ })).toHaveLength(45);
    expect(screen.getByRole('status', { name: 'Evaluation status' })).not.toHaveTextContent('Configuration edited');
    await userEvent.click(point);
    const drawer = screen.getByRole('complementary', { name: /Details for Madison.*AL/ });
    expect(within(drawer).getByText(/^No scalar rank or score/)).toBeInTheDocument();
    expect(within(drawer).getAllByText('CONDITIONAL').length).toBeGreaterThan(0);
    expect(within(drawer).getByText('Power capacity:')).toBeInTheDocument();
    expect(within(drawer).getAllByText(/Lifetime electricity cost.*Mean/).length).toBeGreaterThan(0);
    expect(within(drawer.querySelector('.raw-metrics') as HTMLElement).getAllByText(/Upper-tail CVaR α=/).length).toBe(3);
    expect([...drawer.querySelectorAll('a')].some(link => link.getAttribute('href')?.includes('eia.gov'))).toBe(true);
    const runId = new URLSearchParams(window.location.search).get('run')!;
    await act(async () => { const restored = await selected.api!.run(runId, config.scenario_set[0].id); expect(restored.regions).toHaveLength(45); });
    // Verified mode returns actual exclusions, not an invented winner or an API error.
    await userEvent.click(screen.getByRole('button', { name: 'Close region details' }));
    await userEvent.click(screen.getByRole('button', { name: 'Edit facility' }));
    await userEvent.click(screen.getByText('More options'));
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Screening policy' }), 'STRICT');
    await userEvent.click(screen.getByRole('button', { name: 'Find locations' }));
    await screen.findByRole('heading', { name: 'No regions satisfied the current hard constraints.' }, { timeout: 30000 });
    expect(screen.queryByRole('button', { name: 'County point 01089' })).not.toBeInTheDocument();
  } finally {
    cleanup();
    child.stdin.write(JSON.stringify({ close: true }) + '\n');
    child.stdin.end();
    await shutdown;
    lines.close();
    rmSync(temporary, { recursive: true, force: true });
  }
}, 90000);
