// Saves in flight across every reader instance, so a view that opens after the reader closes
// (browser Back) can wait for the save before it reads the progress.
const inflight = new Set<Promise<unknown>>();

export function savesPending(): boolean {
	return inflight.size > 0;
}

// Wait for every save in flight, at most maxMs; never rejects.
export async function settleSaves(maxMs = 2000): Promise<void> {
	if (inflight.size === 0) return;
	let timer: ReturnType<typeof setTimeout> | undefined;
	const cap = new Promise<void>((resolve) => {
		timer = setTimeout(resolve, maxMs);
	});
	const landed = Promise.all([...inflight]).then(() => true);
	const done = await Promise.race([landed, cap.then(() => false)]);
	clearTimeout(timer);
	// A save that hung past the cap is given up, so it cannot delay every later view.
	if (!done) inflight.clear();
}

export function createProgress(
	save: (bookId: string, page: number, opts?: { keepalive?: boolean }) => Promise<unknown>,
	delayMs = 800,
	onFailing?: () => void,
) {
	let pending: { bookId: string; page: number } | null = null;
	let timer: ReturnType<typeof setTimeout> | null = null;
	let failCount = 0;
	let failingFired = false;

	function countFailure(): void {
		failCount++;
		if (failCount >= 3 && !failingFired) {
			failingFired = true;
			onFailing?.();
		}
	}

	function doSave(bookId: string, page: number, keepalive?: boolean): void {
		const opts = keepalive ? { keepalive: true } : undefined;
		let result: Promise<unknown>;
		try {
			result = save(bookId, page, opts);
		} catch {
			// sync throw: count it, swallow
			countFailure();
			return;
		}
		const tracked = Promise.resolve(result)
			.then(
				() => {
					failCount = 0;
				},
				() => {
					countFailure();
				},
			)
			.catch(() => {});
		inflight.add(tracked);
		void tracked.finally(() => inflight.delete(tracked));
	}

	function clearTimer(): void {
		if (timer !== null) {
			clearTimeout(timer);
			timer = null;
		}
	}

	function performFlush(keepalive?: boolean): void {
		clearTimer();
		if (pending) {
			const { bookId, page } = pending;
			pending = null;
			doSave(bookId, page, keepalive);
		}
	}

	return {
		set(bookId: string, page: number): void {
			if (pending && pending.bookId !== bookId) {
				performFlush();
			}
			pending = { bookId, page };
			if (timer !== null) clearTimeout(timer);
			timer = setTimeout(() => {
				timer = null;
				if (pending) {
					const { bookId: b, page: p } = pending;
					pending = null;
					doSave(b, p);
				}
			}, delayMs);
		},
		flush(keepalive = false): void {
			performFlush(keepalive);
		},
		// Send the pending page and wait for every save in flight, at most maxMs; never rejects.
		async flushAsync(maxMs = 2000): Promise<void> {
			performFlush();
			await settleSaves(maxMs);
		},
		cancel(): void {
			clearTimer();
			pending = null;
		},
	};
}
