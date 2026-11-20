<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

import { resolveVersionLabel } from "./versionLabel";

const props = defineProps<{
  version: string | null | undefined;
  objectRef?: string | null | undefined;
  objectCommit?: string | null | undefined;
}>();

const display = computed(() =>
  resolveVersionLabel(props.version, props.objectRef, props.objectCommit),
);
const verRef = ref<HTMLElement | null>(null);
const tipRef = ref<HTMLElement | null>(null);
const tipVisible = ref(false);
const tipStyle = ref<Record<string, string>>({});
const copied = ref(false);
const copyFailed = ref(false);
let copyTimer: number | undefined;

const copyLabel = computed(() =>
  copied.value ? "已复制" : copyFailed.value ? "复制失败" : "复制完整版本",
);

function showTip(): void {
  if (!display.value.full) return;
  tipVisible.value = true;
  void nextTick(positionTip);
}

function positionTip(): void {
  const anchor = verRef.value;
  const tip = tipRef.value;
  if (!anchor || !tip) return;
  const rect = anchor.getBoundingClientRect();
  const width = tip.offsetWidth;
  const height = tip.offsetHeight;
  let left = rect.left + rect.width / 2;
  left = Math.max(width / 2 + 8, Math.min(left, window.innerWidth - width / 2 - 8));
  const above = rect.top - height - 6 >= 8;
  tipStyle.value = {
    left: `${left}px`,
    top: `${above ? rect.top - 6 : rect.bottom + 6}px`,
    transform: above ? "translate(-50%, -100%)" : "translate(-50%, 0)",
  };
}

function hideTip(): void {
  tipVisible.value = false;
}

/**
 * Copy the full identifier. The Clipboard API is preferred; the textarea
 * fallback keeps older browsers and non-secure contexts working.
 * @param value Full version identifier.
 * @returns Whether a clipboard write succeeded.
 */
function writeClipboard(value: string): boolean {
  const textarea = document.createElement("textarea");
  textarea.value = value;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.select();
  try {
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    textarea.remove();
  }
}

async function copyVersion(): Promise<void> {
  const value = display.value.copy;
  if (!value) return;
  let ok = false;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      ok = true;
    }
  } catch {
    ok = false;
  }
  if (!ok) ok = writeClipboard(value);
  copied.value = ok;
  copyFailed.value = !ok;
  window.clearTimeout(copyTimer);
  copyTimer = window.setTimeout(() => {
    copied.value = false;
    copyFailed.value = false;
  }, 2_000);
}

function hideOnViewportChange(): void {
  hideTip();
}

onMounted(() => {
  window.addEventListener("resize", hideOnViewportChange);
  window.addEventListener("scroll", hideOnViewportChange, true);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", hideOnViewportChange);
  window.removeEventListener("scroll", hideOnViewportChange, true);
  window.clearTimeout(copyTimer);
});

defineExpose({ showTip, hideTip });
</script>

<template>
  <span class="version-label">
    <span
      ref="verRef"
      class="ver"
      aria-hidden="true"
    >
      <span
        v-if="display.ref"
        class="ver-ref"
      >{{ display.ref }}</span>
      <span
        v-if="display.commit"
        class="ver-commit"
      >{{ display.commit }}</span>
      <span
        v-if="display.digest"
        class="ver-digest"
      >{{ display.digest }}</span>
      <span
        v-if="display.missing"
        class="ver-missing"
      >版本未固定</span>
    </span>
    <button
      v-if="display.copy"
      type="button"
      class="ver-copy"
      :class="{ copied, failed: copyFailed }"
      :title="copyLabel"
      :aria-label="`${copyLabel}：${display.full}`"
      @click.stop="copyVersion"
    >
      <svg
        v-if="!copied"
        width="10"
        height="10"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <rect
          x="5.2"
          y="5.2"
          width="8"
          height="8"
          rx="1.6"
          stroke="currentColor"
          stroke-width="1.3"
        />
        <path
          d="M3 10.8V3.9c0-.5.4-.9.9-.9h6.9"
          stroke="currentColor"
          stroke-width="1.3"
          stroke-linecap="round"
        />
      </svg>
      <svg
        v-else
        width="10"
        height="10"
        viewBox="0 0 16 16"
        fill="none"
        aria-hidden="true"
        focusable="false"
      >
        <path
          d="M3.2 8.5 6.4 11.7 12.8 4.6"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>
    <span
      class="sr-only"
      aria-live="polite"
    >{{ copied ? "已复制版本号" : copyFailed ? "复制版本号失败" : "" }}</span>
    <Teleport to="body">
      <div
        v-if="tipVisible"
        ref="tipRef"
        class="version-tip"
        :style="tipStyle"
        role="tooltip"
      >
        {{ display.full }}
      </div>
    </Teleport>
  </span>
</template>

<style scoped>
.version-label {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 2px;
  min-width: 0;
  max-width: 46%;
}

.ver {
  display: flex;
  align-items: baseline;
  gap: 3px;
  min-width: 0;
  overflow: hidden;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 9px;
}

.ver-ref {
  flex-shrink: 0;
  max-width: 64px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ver-commit {
  flex-shrink: 0;
  max-width: 44px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ver-digest {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ver-missing {
  white-space: nowrap;
}

.ver-copy {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  width: 15px;
  height: 15px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: transparent;
  color: var(--text-faint);
  cursor: pointer;
  pointer-events: auto;
}

.ver-copy:hover,
.ver-copy:focus-visible {
  outline: none;
  background: var(--bg-inset);
  color: var(--blue);
}

.ver-copy.copied {
  color: var(--green);
}

.ver-copy.failed {
  color: var(--orange);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>

<style>
/* The tooltip is teleported to <body>, so this rule must stay unscoped. */
.version-tip {
  position: fixed;
  z-index: 2500;
  max-width: 320px;
  padding: 5px 8px;
  border-radius: 6px;
  background: var(--text);
  color: var(--text-on-accent);
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  box-shadow: var(--shadow-popover);
  pointer-events: none;
  transform: translate(-50%, -100%);
}
</style>
