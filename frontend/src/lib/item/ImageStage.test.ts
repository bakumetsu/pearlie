// @vitest-environment jsdom
import { describe, it, expect, afterEach, vi } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/svelte';
import ImageStage from './ImageStage.svelte';
import { createZoom } from './zoomModel.svelte';
import itemSrc from "../../routes/Item.svelte?raw";
import stageSrc from "./ImageStage.svelte?raw";

afterEach(cleanup);

function mountStage(natW = 2000, natH = 1000, disabled = false) {
  const zoom = createZoom();
  const { container } = render(ImageStage, { props: { src: '/f/1', alt: 'x', zoom, disabled } });

  const stage = container.querySelector('.stage')!;
  const btn = container.querySelector('.imgbtn')!;
  const img = container.querySelector('img')!;

  Object.defineProperty(img, 'naturalWidth', { value: natW, configurable: true });
  Object.defineProperty(img, 'naturalHeight', { value: natH, configurable: true });
  Object.defineProperty(stage, 'clientWidth', { value: 1000, configurable: true });
  Object.defineProperty(stage, 'clientHeight', { value: 500, configurable: true });
  stage.getBoundingClientRect = () => ({
    left: 0,
    top: 0,
    width: 1000,
    height: 500,
    right: 1000,
    bottom: 500,
    x: 0,
    y: 0,
    toJSON() {},
  });

  return { zoom, stage, btn, img, container };
}

function firePointer(
  el: Element,
  type: string,
  opts: { pointerType?: string; clientX?: number; clientY?: number; buttons?: number; pointerId?: number } = {},
) {
  const ev = new MouseEvent(type, {
    bubbles: true,
    cancelable: true,
    clientX: opts.clientX ?? 0,
    clientY: opts.clientY ?? 0,
    buttons: opts.buttons ?? 0,
    button: 0,
  });
  Object.defineProperty(ev, 'pointerType', { value: opts.pointerType ?? 'mouse' });
  Object.defineProperty(ev, 'pointerId', { value: opts.pointerId ?? 1 });
  el.dispatchEvent(ev);
}

function raf() {
  return new Promise<void>((r) => requestAnimationFrame(() => r()));
}

describe('ImageStage', () => {
  it('renders img; click toggles zoom.active and .zoomed on stage and img', async () => {
    const { zoom, stage, btn, img } = mountStage(2000, 1000);

    expect(img.getAttribute('src')).toBe('/f/1');
    expect(img.getAttribute('alt')).toBe('x');
    expect(stage.classList.contains('zoomed')).toBe(false);
    expect(img.classList.contains('zoomed')).toBe(false);
    expect(zoom.active).toBe(false);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);
    expect(stage.classList.contains('zoomed')).toBe(true);
    expect(img.classList.contains('zoomed')).toBe(true);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(false);
    expect(stage.classList.contains('zoomed')).toBe(false);
    expect(img.classList.contains('zoomed')).toBe(false);
  });

  it('click at a corner keeps the point under the pointer', async () => {
    const { zoom, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 900, clientY: 100, detail: 1 });

    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBe(1);
    expect(zoom.tx).toBeCloseTo(-400);
    expect(zoom.ty).toBeCloseTo(150);
  });

  it('img gets a translate/scale transform while zoomed', async () => {
    const { btn, img } = mountStage(2000, 1000);

    expect(img.style.transform).toBe('');

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });

    expect(img.getAttribute('style')).toContain('scale(1)');
  });

  it('natural size 0: click and wheel are no-ops', async () => {
    const { zoom, stage, btn } = mountStage(0, 0);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(false);

    await raf();
    stage.dispatchEvent(new WheelEvent('wheel', { deltaY: -100, bubbles: true, cancelable: true }));
    expect(zoom.active).toBe(false);
  });

  it('wheel zooms at the cursor, preventDefault called, ctrl wheel too', async () => {
    const { zoom, stage } = mountStage(2000, 1000);
    await raf();

    const ev = new WheelEvent('wheel', { deltaY: -100, clientX: 500, clientY: 250, bubbles: true, cancelable: true });
    stage.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(true);
    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBeGreaterThan(0.5);

    const { zoom: z2, stage: s2 } = mountStage(2000, 1000);
    await raf();
    const ev2 = new WheelEvent('wheel', { deltaY: -100, clientX: 500, clientY: 250, ctrlKey: true, bubbles: true, cancelable: true });
    s2.dispatchEvent(ev2);
    expect(ev2.defaultPrevented).toBe(true);
    expect(z2.active).toBe(true);
  });

  it('horizontal wheel is not zoom and not prevented', async () => {
    const { zoom, stage } = mountStage(2000, 1000);
    await raf();

    const ev = new WheelEvent('wheel', { deltaX: 100, deltaY: 10, clientX: 500, clientY: 250, bubbles: true, cancelable: true });
    stage.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
    expect(zoom.active).toBe(false);
  });

  it('mouse drag over 4px pans and the click that follows does not toggle', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);
    const before = zoom.tx;

    firePointer(stage, 'pointerdown', { pointerType: 'mouse', clientX: 10, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'mouse', clientX: 30, clientY: 30, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'mouse', clientX: 30, clientY: 30, buttons: 0 });

    expect(zoom.tx).toBeCloseTo(20 + before);

    await fireEvent.click(btn, { detail: 1 });
    expect(zoom.active).toBe(true);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(false);
  });

  it('drag-click is swallowed in capture: ancestor click handler does not fire', async () => {
    const { zoom, stage, btn, container } = mountStage(2000, 1000);
    const spy = vi.fn();

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);
    container.addEventListener('click', spy);

    firePointer(stage, 'pointerdown', { pointerType: 'mouse', clientX: 10, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'mouse', clientX: 30, clientY: 30, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'mouse', clientX: 30, clientY: 30, buttons: 0 });

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(spy).not.toHaveBeenCalled();

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(spy).toHaveBeenCalled();
  });

  it('drag under 4px does not set the swallow flag', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);

    firePointer(stage, 'pointerdown', { pointerType: 'mouse', clientX: 10, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'mouse', clientX: 12, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'mouse', clientX: 12, clientY: 10, buttons: 0 });

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(false);
  });

  it('one finger touch drag pans while zoomed; at fit nothing happens', async () => {
    const { zoom, stage } = mountStage(2000, 1000);

    // at fit, touch drag is a no-op
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 10, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 30, clientY: 30, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 30, clientY: 30, buttons: 0 });
    await raf();
    expect(zoom.active).toBe(false);

    // zoom in, then touch-drag pans
    zoom.setSizes(1000, 500, 2000, 1000);
    zoom.toggleAt(0, 0);
    expect(zoom.active).toBe(true);
    const before = zoom.tx;

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 10, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 30, clientY: 10, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 30, clientY: 10, buttons: 0 });

    expect(zoom.tx).toBeCloseTo(20 + before);
  });

  it('Enter/Space style click (detail 0) uses the stage centre', async () => {
    const { zoom, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 900, clientY: 100, detail: 0 });

    expect(zoom.active).toBe(true);
    expect(zoom.tx).toBeCloseTo(0);
  });

  it('CSS guards from source', () => {
    expect(itemSrc).toContain('grid-template: minmax(0, 1fr) / minmax(0, 1fr)');

    expect(stageSrc).toContain('touch-action: none');
    expect(stageSrc).toContain('.stage:not(.zoomed) .imgbtn');
    expect(stageSrc).toContain('max-height: 100%');
    expect(stageSrc).toContain('object-fit: contain');
    expect(stageSrc).toContain('width: 100%');
    expect(stageSrc).toContain('height: 100%');
    expect(stageSrc).toContain('.stage:not(.zoomed) img');
    expect(stageSrc).toContain('prefers-reduced-motion: reduce');
    expect(stageSrc).toContain('passive: false');
  });

  it('two-finger pinch at fit starts zoom anchored at the midpoint', async () => {
    const { zoom, stage } = mountStage(2000, 1000);

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 400, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 600, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 300, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 700, clientY: 250, pointerId: 2, buttons: 1 });
    await raf();

    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBeCloseTo(1);
    expect(zoom.tx).toBeCloseTo(0);
    expect(zoom.ty).toBeCloseTo(0);
  });

  it('pinch keeps the point under the midpoint fixed', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBe(1);

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 800, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 900, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 775, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 925, clientY: 250, pointerId: 2, buttons: 1 });
    await raf();

    expect(zoom.scale).toBeCloseTo(1.5);
    expect(zoom.tx).toBeLessThan(0);
  });

  it('midpoint movement pans while pinching', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 450, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 470, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 570, clientY: 250, pointerId: 2, buttons: 1 });
    await raf();

    expect(zoom.tx).toBeCloseTo(20);
  });

  it('snap on release', async () => {
    const { zoom, stage } = mountStage(2000, 1000);

    vi.useFakeTimers();
    try {
      firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 400, clientY: 250, pointerId: 1, buttons: 1 });
      firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 600, clientY: 250, pointerId: 2, buttons: 1 });
      firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 298, clientY: 250, pointerId: 1, buttons: 1 });
      firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 702, clientY: 250, pointerId: 2, buttons: 1 });
      firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 298, clientY: 250, pointerId: 1, buttons: 0 });
      firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 702, clientY: 250, pointerId: 2, buttons: 0 });
      vi.advanceTimersByTime(200);

      expect(zoom.scale).toBe(1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('lifting one finger rebases the one-finger drag', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 450, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 450, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 2, buttons: 0 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 460, clientY: 250, pointerId: 1, buttons: 1 });
    await raf();

    expect(zoom.tx).toBeCloseTo(10);
  });

  it('pinch is ignored while disabled', async () => {
    const { zoom, stage, btn } = mountStage(2000, 1000, true);

    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 400, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerdown', { pointerType: 'touch', clientX: 600, clientY: 250, pointerId: 2, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 300, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 700, clientY: 250, pointerId: 2, buttons: 1 });
    await raf();

    expect(zoom.active).toBe(false);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(false);

    const ev = new WheelEvent('wheel', { deltaY: -100, ctrlKey: true, bubbles: true, cancelable: true });
    stage.dispatchEvent(ev);
    expect(ev.defaultPrevented).toBe(false);
    expect(zoom.active).toBe(false);
  });

  it('pointerdown on the zoom bar does not start a drag', async () => {
    const { zoom, stage, btn, container } = mountStage(2000, 1000);

    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);

    const zoomIn = container.querySelector('[aria-label="Zoom in"]') as HTMLElement;
    firePointer(zoomIn, 'pointerdown', { pointerType: 'touch', clientX: 500, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointermove', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 1, buttons: 1 });
    firePointer(stage, 'pointerup', { pointerType: 'touch', clientX: 550, clientY: 250, pointerId: 1, buttons: 0 });
    await raf();

    expect(zoom.tx).toBeCloseTo(0);

    await fireEvent.click(zoomIn);
    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBe(1.5);
  });

  it('full image load while zoomed keeps the displayed size', async () => {
    const { zoom, btn, img } = mountStage(2000, 1000);

    await fireEvent.load(img);
    await fireEvent.click(btn, { clientX: 500, clientY: 250, detail: 1 });
    expect(zoom.active).toBe(true);
    expect(zoom.scale).toBe(1);

    Object.defineProperty(img, 'naturalWidth', { value: 4000, configurable: true });
    Object.defineProperty(img, 'naturalHeight', { value: 2000, configurable: true });
    await fireEvent.load(img);
    await raf();

    expect(zoom.scale).toBeCloseTo(0.5);
  });
});
