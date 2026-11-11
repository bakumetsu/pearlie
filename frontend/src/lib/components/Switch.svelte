<script lang="ts">
	let { checked, label, onclick }: { checked: boolean; label: string; onclick: () => void } = $props();
</script>

<button
	role="switch"
	aria-checked={checked ? "true" : "false"}
	aria-label={label}
	class="switch"
	{onclick}
></button>

<style>
	.switch {
		position: relative;
		border: 1px solid var(--border, #333);
		border-radius: 999px;
		background: var(--accent-bg, #22324f);
		cursor: pointer;
		padding: 0;
		min-height: 44px;
		min-width: 56px;
	}
	.switch::after {
		content: "";
		position: absolute;
		top: 50%;
		left: 6px;
		width: 20px;
		height: 20px;
		margin-top: -10px;
		border-radius: 50%;
		background: var(--muted, #a3a3ad);
		transition: transform 0.15s;
	}
	.switch[aria-checked="true"] {
		background: var(--accent, #7fb0ff);
	}
	.switch[aria-checked="true"]::after {
		transform: translateX(24px);
		background: #fff;
	}
</style>
