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
		result
			.then(
				() => {
					failCount = 0;
				},
				() => {
					countFailure();
				},
			)
			.catch(() => {});
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
		cancel(): void {
			clearTimer();
			pending = null;
		},
	};
}
