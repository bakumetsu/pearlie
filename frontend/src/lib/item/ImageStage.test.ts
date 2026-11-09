// @vitest-environment jsdom
import { describe, it, expect, afterEach } from 'vitest';
import { render, fireEvent, cleanup } from '@testing-library/svelte';
import ImageStage from './ImageStage.svelte';
import itemSrc from "../../routes/Item.svelte?raw";
import stageSrc from "./ImageStage.svelte?raw";

afterEach(cleanup);

describe('ImageStage', () => {
  it('renders img; clicking .imgbtn toggles "zoomed" on .stage and img', async () => {
    const { container } = render(ImageStage, { props: { src: '/f/1', alt: 'x' } });

    const img = container.querySelector('img')!;
    expect(img).not.toBeNull();
    expect(img.getAttribute('src')).toBe('/f/1');
    expect(img.getAttribute('alt')).toBe('x');

    const stage = container.querySelector('.stage')!;
    const btn = container.querySelector('.imgbtn')!;

    // initial: not zoomed
    expect(stage.classList.contains('zoomed')).toBe(false);
    expect(img.classList.contains('zoomed')).toBe(false);

    // click → zoomed
    await fireEvent.click(btn);
    expect(stage.classList.contains('zoomed')).toBe(true);
    expect(img.classList.contains('zoomed')).toBe(true);

    // click again → unzoomed
    await fireEvent.click(btn);
    expect(stage.classList.contains('zoomed')).toBe(false);
    expect(img.classList.contains('zoomed')).toBe(false);
  });

  it('CSS guard: grid-template in Item.svelte; .imgbtn constraints + object-fit in ImageStage.svelte', () => {
    expect(itemSrc).toContain('grid-template: minmax(0, 1fr) / minmax(0, 1fr)');

    expect(stageSrc).toContain('.stage:not(.zoomed) .imgbtn');
    expect(stageSrc).toContain('max-height: 100%');
    expect(stageSrc).toContain('object-fit: contain');
  });

  it('mouse drag past 4px while zoomed does not toggle', async () => {
    const { container } = render(ImageStage, { props: { src: '/f/1', alt: 'x' } });
    const stage = container.querySelector('.stage')!;
    const btn = container.querySelector('.imgbtn')!;

    // zoom in
    await fireEvent.click(btn);
    expect(stage.classList.contains('zoomed')).toBe(true);

    // helper: dispatch pointer events with pointerType (jsdom lacks PointerEvent)
    const firePointer = (type: string, opts: { pointerType?: string; clientX?: number; clientY?: number; buttons?: number }) => {
      const ev = new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        clientX: opts.clientX ?? 0,
        clientY: opts.clientY ?? 0,
        buttons: opts.buttons ?? 0,
      });
      Object.defineProperty(ev, 'pointerType', { value: opts.pointerType ?? 'mouse' });
      stage.dispatchEvent(ev);
    };

    // simulate drag (20px > 4px threshold)
    firePointer('pointerdown', { pointerType: 'mouse', clientX: 10, clientY: 10, buttons: 1 });
    firePointer('pointermove', { pointerType: 'mouse', clientX: 30, clientY: 30, buttons: 1 });
    firePointer('pointerup', { pointerType: 'mouse', buttons: 0 });

    // click after drag should be suppressed — still zoomed
    await fireEvent.click(btn);
    expect(stage.classList.contains('zoomed')).toBe(true);

    // clean click toggles back
    await fireEvent.click(btn);
    expect(stage.classList.contains('zoomed')).toBe(false);
  });

  it('CSS guard: fit mode gives imgbtn and img definite width/height 100%', () => {
    expect(stageSrc).toContain('.stage:not(.zoomed) .imgbtn');
    expect(stageSrc).toContain('width: 100%');
    expect(stageSrc).toContain('height: 100%');
    expect(stageSrc).toContain('.stage:not(.zoomed) img');
  });
});
