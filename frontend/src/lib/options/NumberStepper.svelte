<script lang="ts">
	import type { Snippet } from "svelte";
	import Icon from "../components/Icon.svelte";

	let {
		label,
		disabled = false,
		children
	}: { label: string; disabled?: boolean; children: Snippet } = $props();

	let root: HTMLSpanElement | undefined = $state();

	// Steps the wrapped input, then fires its change event so the card's own handler runs.
	function step(dir: 1 | -1) {
		const input = root?.querySelector("input");
		if (!input || input.disabled) return;
		const before = input.value;
		if (dir > 0) input.stepUp();
		else input.stepDown();
		if (input.value !== before) input.dispatchEvent(new Event("change", { bubbles: true }));
	}
</script>

<span class="stepper" bind:this={root}>
	<button
		type="button"
		class="step-btn"
		aria-label={`Decrease ${label}`}
		{disabled}
		onclick={() => step(-1)}
	>
		<Icon name="minus" size={16} />
	</button>
	<button
		type="button"
		class="step-btn"
		aria-label={`Increase ${label}`}
		{disabled}
		onclick={() => step(1)}
	>
		<Icon name="plus" size={16} />
	</button>
	{@render children()}
</span>

<style>
	.stepper {
		display: inline-flex;
		align-items: center;
		gap: var(--s-1, 4px);
	}

	.step-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 44px;
		min-height: 44px;
		border: 1px solid var(--line-strong);
		border-radius: var(--r-sm);
		background: var(--bg);
		color: var(--text);
		cursor: pointer;
	}

	.step-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
