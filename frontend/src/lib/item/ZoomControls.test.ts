// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/svelte';
import { tick } from "svelte";
import ZoomControls from './ZoomControls.svelte';
import { createZoom } from './zoomModel.svelte';
import src from "./ZoomControls.svelte?raw";

afterEach(cleanup);

function mountControls() {
  const zoom = createZoom();
  const onhide = vi.fn();
  const { container } = render(ZoomControls, { props: { zoom, onhide } });
  zoom.setSizes(1000, 500, 2000, 1000);
  return { zoom, onhide, container };
}

describe('ZoomControls', () => {
  it('no zoombar at fit; present after zoomAt', async () => {
    const { zoom, container } = mountControls();
    expect(container.querySelector('[data-zoombar]')).toBeNull();

    zoom.zoomAt(1, 0, 0);
    await tick();
    expect(container.querySelector('[data-zoombar]')).not.toBeNull();
  });

  it('button labels and percent text', async () => {
    const { zoom, container } = mountControls();
    zoom.zoomAt(1, 0, 0);
    await tick();

    const bar = container.querySelector('[data-zoombar]')!;
    const btns = bar.querySelectorAll('button');
    expect(btns[0].getAttribute('aria-label')).toBe('Zoom out');
    expect(btns[1].getAttribute('aria-label')).toBe('Fit to screen, now 100%');
    expect(btns[2].getAttribute('aria-label')).toBe('Zoom in');
    expect((btns[1] as HTMLElement).textContent!.trim()).toBe('100%');
  });

  it('44px min targets in source', () => {
    expect(src).toMatch(/min-width:\s*44px/);
    expect(src).toMatch(/min-height:\s*44px/);
  });

  it('Zoom in disabled at max; Zoom out disabled at min', async () => {
    const { zoom, container } = mountControls();

    zoom.zoomAt(2, 0, 0);
    await tick();
    const zoomIn = container.querySelector('[aria-label="Zoom in"]') as HTMLButtonElement;
    expect(zoomIn.disabled).toBe(true);

    zoom.zoomAt(0.25, 0, 0);
    await tick();
    const zoomOut = container.querySelector('[aria-label="Zoom out"]') as HTMLButtonElement;
    expect(zoomOut.disabled).toBe(true);
  });

  it('Zoom in steps to 1.5; Fit to screen deactivates', async () => {
    const { zoom, container } = mountControls();
    zoom.zoomAt(1, 0, 0);
    await tick();

    const zoomInBtn = container.querySelector('[aria-label="Zoom in"]')!;
    await fireEvent.click(zoomInBtn);
    expect(zoom.scale).toBeCloseTo(1.5);
    expect(container.querySelector('[data-zoombar]')).not.toBeNull();

    const fitBtn = container.querySelector('[aria-label^="Fit to screen"]')!;
    await fireEvent.click(fitBtn);
    expect(zoom.active).toBe(false);
  });

  it('live region announces zoom percent', async () => {
    vi.useFakeTimers();
    const { zoom, container } = mountControls();
    zoom.zoomAt(1, 0, 0);
    await tick();
    vi.advanceTimersByTime(400);
    await tick();

    const live = container.querySelector('[role="status"]')!;
    expect(live.textContent!.trim()).toBe('Zoom 100 percent');

    zoom.zoomAt(1.5, 0, 0);
    await tick();
    vi.advanceTimersByTime(400);
    await tick();
    expect(live.textContent!.trim()).toBe('Zoom 150 percent');

    vi.useRealTimers();
  });

  it('focus return: onhide called when zoom resets while focus in bar', async () => {
    const { zoom, onhide, container } = mountControls();
    zoom.zoomAt(1, 0, 0);
    await tick();

    const bar = container.querySelector('[data-zoombar]')!;
    const zoomInBtn = bar.querySelector('[aria-label="Zoom in"]') as HTMLButtonElement;
    zoomInBtn.focus();

    zoom.reset();
    await tick();

    expect(onhide).toHaveBeenCalledTimes(1);
  });

});
