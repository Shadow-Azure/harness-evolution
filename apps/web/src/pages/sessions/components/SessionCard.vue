<script setup lang="ts">
import type { SessionListItem } from "@harness/contracts";

import DensityBar from "../../../components/ui/DensityBar.vue";
import { formatDuration, formatStartedAt } from "../../../utils/sessionDisplay";

defineProps({
  item: {
    type: Object as () => SessionListItem,
    required: true,
  },
  selected: {
    type: Boolean,
    default: false,
  },
  focusable: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits<{
  focus: [];
  select: [sessionId: string];
}>();
</script>

<template>
  <div
    :id="`session-option-${item.id}`"
    data-testid="session-card"
    :data-session-id="item.id"
    :data-selected="selected"
    class="session-card"
    :class="{ selected }"
    role="option"
    :aria-selected="selected"
    :tabindex="focusable ? 0 : -1"
    @click="emit('select', item.id)"
    @focus="emit('focus')"
    @keydown.enter="emit('select', item.id)"
    @keydown.space.prevent="emit('select', item.id)"
  >
    <div class="card-title">
      <span
        class="status-dot"
        :class="item.status"
        aria-hidden="true"
      />
      <span class="sr-only">{{ item.status === "ok" ? "完成" : "有失败" }}</span>
      <strong>{{ item.short || item.title }}</strong>
      <time :datetime="item.startedAt">{{ formatStartedAt(item.startedAt) }}</time>
    </div>
    <div class="card-meta">
      <span class="repo-chip">{{ item.repo }}</span>
      <span>{{ formatDuration(item.durationSeconds) }}</span>
      <span>{{ item.stats.tools }} 工具</span>
      <span class="agents">{{ item.stats.agents }} 子 Agent</span>
    </div>
    <div
      class="card-session-id"
      data-testid="session-card-root-session-id"
      :title="`根会话 ID: ${item.id}`"
    >
      根会话 ID · {{ item.id }}
    </div>
    <dl class="card-stats">
      <div>
        <dt>用户轮次</dt>
        <dd>{{ item.stats.userTurns }}</dd>
      </div>
      <div>
        <dt>消息</dt>
        <dd>{{ item.stats.messages }}</dd>
      </div>
      <div>
        <dt>工具失败</dt>
        <dd class="bad">
          {{ item.stats.errors }}
        </dd>
      </div>
      <div>
        <dt>Skill</dt>
        <dd>{{ item.skills.length }}</dd>
      </div>
      <div>
        <dt>问题</dt>
        <dd class="warn">
          {{ item.stats.badCases }}
        </dd>
      </div>
    </dl>
    <div class="densities">
      <DensityBar
        label="失败"
        tone="fail"
        :value="item.stats.failPer100Messages"
      />
      <DensityBar
        label="问题"
        tone="problem"
        :value="item.stats.badCasesPer100Messages"
      />
    </div>
  </div>
</template>

<style scoped>
.session-card {
  display: grid;
  gap: 7px;
  padding: 10px 11px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-card);
  box-shadow: var(--shadow-card);
  cursor: pointer;
}

.session-card:hover {
  border-color: var(--border-strong);
}

.session-card:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--blue) 30%, transparent);
  outline-offset: 1px;
}

.session-card.selected {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 8%, var(--bg-card));
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.card-title strong {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--text);
  font-size: 12.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-title time {
  flex-shrink: 0;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10.5px;
}

.status-dot {
  width: 7px;
  height: 7px;
  flex-shrink: 0;
  border-radius: 50%;
}

.status-dot.ok {
  background: var(--green);
}

.status-dot.partial {
  background: var(--orange);
}

.status-dot.fail {
  background: var(--red);
}

.card-meta {
  display: flex;
  align-items: center;
  gap: 7px;
  overflow: hidden;
  color: var(--text-dim);
  font-size: 10.5px;
  white-space: nowrap;
}

.card-session-id {
  overflow: hidden;
  color: var(--text-faint);
  font-family: var(--mono);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.repo-chip {
  max-width: 108px;
  overflow: hidden;
  padding: 0 6px;
  border-radius: 5px;
  background: color-mix(in srgb, var(--cyan) 12%, transparent);
  color: var(--cyan);
  font-family: var(--mono);
  text-overflow: ellipsis;
}

.agents {
  color: var(--purple);
}

.card-stats {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin: 0;
}

.card-stats div {
  display: grid;
  gap: 1px;
}

.card-stats dt {
  overflow: hidden;
  color: var(--text-faint);
  font-size: 9.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-stats dd {
  margin: 0;
  color: var(--text);
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
}

.card-stats dd.bad {
  color: var(--red);
}

.card-stats dd.warn {
  color: var(--orange);
}

.densities {
  display: grid;
  gap: 3px;
}
</style>
