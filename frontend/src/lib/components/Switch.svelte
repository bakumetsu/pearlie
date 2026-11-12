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
		border: 0;
		background: transparent;
		cursor: pointer;
		padding: 0;
		min-height: 44px;
		min-width: 56px;
	}
	.switch::before {
		content: "";
		position: absolute;
		top: 50%;
		left: 4px;
		width: 48px;
		height: 26px;
		margin-top: -13px;
		box-sizing: border-box;
		border: 1px solid var(--line-strong, #34343b);
		border-radius: 999px;
		background: var(--accent-bg, #22324f);
	}
	.switch::after {
		content: "";
		position: absolute;
		top: 50%;
		left: 9px;
		width: 18px;
		height: 18px;
		margin-top: -9px;
		border-radius: 50%;
		background: var(--muted, #a3a3ad);
		transition: transform 0.15s;
	}
	.switch[aria-checked="true"]::before {
		background: var(--accent, #7fb0ff);
	}
	.switch[aria-checked="true"]::after {
		transform: translateX(22px);
		background: #fff;
	}
</style>
