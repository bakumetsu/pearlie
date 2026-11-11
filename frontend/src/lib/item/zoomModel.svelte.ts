export const LADDER = [0.25, 0.5, 0.75, 1, 1.5, 2];
export const PAN_STEP = 80;
export const SNAP = 0.04;

export function wheelFactor(deltaY: number, deltaMode: number, ctrl: boolean): number {
  const dy = deltaMode === 1 ? deltaY * 16 : deltaY;
  return Math.exp(-dy * (ctrl ? 0.01 : 0.002));
}

export function createZoom() {
  const state = $state({
    mode: "fit" as "fit" | "zoom",
    scale: 1,
    tx: 0,
    ty: 0,
    stageW: 0,
    stageH: 0,
    natW: 0,
    natH: 0,
  });

  function fitScale(): number {
    if (state.natW <= 0 || state.natH <= 0 || state.stageW <= 0 || state.stageH <= 0) return 1;
    return Math.min(state.stageW / state.natW, state.stageH / state.natH);
  }

  function minScale(): number {
    return Math.min(0.25, fitScale());
  }

  function maxScale(): number {
    return Math.max(2, fitScale());
  }

  function clampPan(): void {
    if (state.natW <= 0 || state.natH <= 0 || state.stageW <= 0 || state.stageH <= 0) {
      state.tx = 0;
      state.ty = 0;
      return;
    }
    const mX = Math.max(0, (state.natW * state.scale - state.stageW) / 2);
    const mY = Math.max(0, (state.natH * state.scale - state.stageH) / 2);
    state.tx = Math.max(-mX, Math.min(mX, state.tx));
    state.ty = Math.max(-mY, Math.min(mY, state.ty));
  }

  function clampScale(): void {
    state.scale = Math.max(minScale(), Math.min(maxScale(), state.scale));
  }

  function reset(): void {
    state.mode = "fit";
    state.tx = 0;
    state.ty = 0;
    state.scale = fitScale();
  }

  function fit(): void {
    reset();
  }

  function zoomAt(newScale: number, px: number, py: number): void {
    newScale = Math.max(minScale(), Math.min(maxScale(), newScale));
    if (state.mode === "fit") {
      state.scale = fitScale();
      state.tx = 0;
      state.ty = 0;
      state.mode = "zoom";
    }
    const ratio = newScale / state.scale;
    state.tx = px - (px - state.tx) * ratio;
    state.ty = py - (py - state.ty) * ratio;
    state.scale = newScale;
    clampPan();
  }

  function toggleAt(px: number, py: number): boolean {
    if (state.mode === "fit") {
      const fv = fitScale();
      let target: number | null = null;
      if (fv < 0.95) {
        target = 1;
      } else {
        for (const rung of LADDER) {
          if (rung > fv) {
            target = rung;
            break;
          }
        }
      }
      if (target === null) return false;
      zoomAt(target, px, py);
      return true;
    } else {
      reset();
      return true;
    }
  }

  function stepIn(): boolean {
    const base = state.mode === "fit" ? fitScale() : state.scale;
    const fv = fitScale();
    const mn = minScale();
    const mx = maxScale();
    const rungs = [...LADDER, fv].sort((a, b) => a - b).filter((r, i, arr) => (i === 0 || r - arr[i - 1] > 1e-9) && r >= mn && r <= mx);
    const next = rungs.find((r) => r > base + 1e-6);
    if (next === undefined) return false;
    zoomAt(next, 0, 0);
    return true;
  }

  function stepOut(): boolean {
    if (state.mode === "fit") return false;
    const fv = fitScale();
    const mn = minScale();
    const mx = maxScale();
    const rungs = [...LADDER, fv].sort((a, b) => a - b).filter((r, i, arr) => (i === 0 || r - arr[i - 1] > 1e-9) && r >= mn && r <= mx);
    const prev = [...rungs].reverse().find((r) => r < state.scale - 1e-6);
    if (prev === undefined || prev <= fv + 1e-6) {
      reset();
      return true;
    }
    zoomAt(prev, 0, 0);
    return true;
  }

  function panBy(dx: number, dy: number): void {
    if (state.mode !== "zoom") return;
    state.tx += dx;
    state.ty += dy;
    clampPan();
  }

  function snap(): void {
    if (state.mode !== "zoom") return;
    const fv = fitScale();
    if (Math.abs(state.scale - fv) <= fv * SNAP) {
      reset();
    } else if (Math.abs(state.scale - 1) <= SNAP) {
      zoomAt(1, 0, 0);
    }
  }

  function setSizes(stageW: number, stageH: number, natW: number, natH: number): void {
    state.stageW = stageW;
    state.stageH = stageH;
    state.natW = natW;
    state.natH = natH;
    if (state.mode === "zoom") {
      clampScale();
      clampPan();
      if (Math.abs(state.scale - fitScale()) <= fitScale() * SNAP) {
        reset();
      }
    }
  }

  return {
    get mode() { return state.mode; },
    get scale() { return state.mode === "fit" ? fitScale() : state.scale; },
    get tx() { return state.tx; },
    get ty() { return state.ty; },
    get active() { return state.mode === "zoom"; },
    get percent(): number {
      if (state.mode === "fit") return Math.round(fitScale() * 100);
      return Math.round(state.scale * 100);
    },
    get f() { return fitScale(); },
    get min() { return minScale(); },
    get max() { return maxScale(); },
    setSizes,
    zoomAt,
    toggleAt,
    stepIn,
    stepOut,
    panBy,
    snap,
    reset,
    fit,
  };
}

export type Zoom = ReturnType<typeof createZoom>;

export function zoomKey(
  e: { key: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean; preventDefault(): void },
  zoom: Zoom,
): boolean {
  if (e.ctrlKey || e.metaKey || e.altKey) return false;

  switch (e.key) {
    case "+":
    case "=": {
      const changed = zoom.stepIn();
      if (changed) {
        e.preventDefault();
        return true;
      }
      return false;
    }
    case "-": {
      const changed = zoom.stepOut();
      if (changed) {
        e.preventDefault();
        return true;
      }
      return false;
    }
    case "0": {
      if (!zoom.active) return false;
      zoom.fit();
      e.preventDefault();
      return true;
    }
    case "z":
    case "Z": {
      const changed = zoom.toggleAt(0, 0);
      if (changed) {
        e.preventDefault();
        return true;
      }
      return false;
    }
    case "Escape": {
      if (!zoom.active) return false;
      zoom.reset();
      e.preventDefault();
      return true;
    }
    case "ArrowLeft":
    case "ArrowRight":
    case "ArrowUp":
    case "ArrowDown": {
      if (!e.shiftKey || !zoom.active) return false;
      if (e.key === "ArrowLeft") zoom.panBy(-PAN_STEP, 0);
      else if (e.key === "ArrowRight") zoom.panBy(PAN_STEP, 0);
      else if (e.key === "ArrowUp") zoom.panBy(0, -PAN_STEP);
      else zoom.panBy(0, PAN_STEP);
      e.preventDefault();
      return true;
    }
    default:
      return false;
  }
}
