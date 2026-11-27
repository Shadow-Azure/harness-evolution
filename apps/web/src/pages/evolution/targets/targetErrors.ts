import { ApiError } from "../../../api/http";
import { formatApiError } from "../../../app/apiError";

/** Shared target fields that can carry a structured save failure. */
export type TargetTopField =
  | "repoUrl"
  | "defaultRef"
  | "validationProjectId"
  | "testProjectId"
  | "primaryMetricKey";

/** Member fields addressable through `members[i].field`. */
export type TargetMemberFieldName = "objectType" | "objectName" | "subDir";

/** Backend field path of one member row, e.g. `members[0].objectName`. */
export type TargetMemberField =
  `members[${number}].${TargetMemberFieldName}`;

/** Form fields that can carry a structured save failure. */
export type TargetFormField = TargetTopField | TargetMemberField;

/** Bounded git command metadata returned with a remote validation failure. */
export interface TargetCommandDetails {
  name: string;
  exitCode?: number;
}

/** Structured target save failure rendered by the form and its summary. */
export interface TargetServerError {
  summary: string;
  field?: TargetFormField;
  reason?: string;
  message?: string;
  suggestion?: string;
  command?: TargetCommandDetails;
  output?: string;
}

const TARGET_FIELDS = new Set<TargetTopField>([
  "repoUrl",
  "defaultRef",
  "validationProjectId",
  "testProjectId",
  "primaryMetricKey",
]);

const MEMBER_FIELD_PATTERN =
  /^members\[(\d+)\]\.(objectType|objectName|subDir)$/u;

/** Copy shown when one member already belongs to another configuration. */
const MEMBER_ALREADY_CONFIGURED_COPY = {
  summary: "该成员已属于另一条配置",
  message: "该成员已属于另一条配置",
  suggestion: "同一对象只能属于一条配置；调整成员名称或先移除原配置。",
};

const REASON_COPY: Record<string, { message: string; suggestion: string }> = {
  object_name_invalid: {
    message: "对象名称不符合规则",
    suggestion: "填写 1–128 个字符的名称，不能包含控制字符。",
  },
  member_duplicated: {
    message: "同一配置里成员重复",
    suggestion: "同一配置中每个成员的类型和名称不能重复；移除或修改重复行。",
  },
  repo_url_format: {
    message: "仓库地址格式不正确",
    suggestion:
      "使用无凭据的 HTTPS（https://…）或 SSH（git@…）地址；不能带 query、fragment 或非法端口。",
  },
  repo_url_credentials: {
    message: "仓库地址不能包含用户名或密码",
    suggestion: "移除 URL 中的凭据，改用 SSH agent 或凭据助手。",
  },
  sub_dir_format: {
    message: "子目录必须是仓库内的相对路径",
    suggestion:
      "使用如 skills/deep-research 的相对路径；不要以 / 开头，也不要包含 ..、反斜杠或以 . 结尾。",
  },
  ref_format: {
    message: "基线格式不正确",
    suggestion:
      "填写分支或 tag，例如 main、v2.0.0；不能包含 ..、空格或以 .、/ 结尾。",
  },
  ref_not_found: {
    message: "仓库可达，但找不到该 ref",
    suggestion: "确认分支或 tag 存在；可点输入框右侧按钮查看仓库标签。",
  },
  repo_unreachable: {
    message: "无法访问仓库",
    suggestion: "确认地址、网络与读取权限；下方是脱敏后的 git 输出。",
  },
  git_timeout: {
    message: "访问仓库超时",
    suggestion: "检查网络或代理后重试；下方是脱敏后的 git 输出。",
  },
  git_unavailable: {
    message: "无法启动 git 命令",
    suggestion: "确认服务端已安装 git，且可从 PATH 调用。",
  },
};

const PROJECT_ID_COPY = {
  message: "测试工程 ID 无效",
  suggestion: "去掉空格或控制字符，或填写 1–128 个字符的工程 ID。",
};

const PROJECT_ID_REASONS = {
  project_id_required: PROJECT_ID_COPY,
  project_id_format: PROJECT_ID_COPY,
};

const PRIMARY_METRIC_KEY_COPY = {
  message: "主指标 key 无效",
  suggestion: "去掉空格或控制字符，或填写 1–128 个字符的指标 key，如 resolved_rate。",
};

const PRIMARY_METRIC_KEY_REASONS = {
  metric_key_required: PRIMARY_METRIC_KEY_COPY,
  metric_key_format: PRIMARY_METRIC_KEY_COPY,
};

const FALLBACK_SUMMARY = "仓库或 ref 无效，请检查地址、子目录与基线";
const FALLBACK_SUGGESTION =
  "逐项检查仓库地址、子目录与基线；若确认无误，请联系管理员查看服务端日志。";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Split a member-anchored field path into its row and member field.
 * @param field Backend field path such as `members[2].subDir`.
 * @returns Parsed row index and field name, or null for shared target fields.
 */
export function parseTargetMemberField(
  field: TargetFormField | undefined,
): { index: number; field: TargetMemberFieldName } | null {
  if (!field) return null;
  const match = MEMBER_FIELD_PATTERN.exec(field);
  if (!match) return null;
  const [, rawIndex, rawField] = match;
  const index = Number(rawIndex);
  const fieldName = rawField as TargetMemberFieldName | undefined;
  if (!fieldName || !Number.isSafeInteger(index) || index < 0) return null;
  return { index, field: fieldName };
}

function parseField(value: unknown): TargetFormField | null {
  if (typeof value !== "string") return null;
  if (TARGET_FIELDS.has(value as TargetTopField)) {
    return value as TargetTopField;
  }
  return parseTargetMemberField(value as TargetFormField)
    ? (value as TargetFormField)
    : null;
}

function parseCommand(value: unknown): TargetCommandDetails | undefined {
  if (!isRecord(value) || typeof value.name !== "string" || !value.name) {
    return undefined;
  }
  const command: TargetCommandDetails = { name: value.name };
  if (typeof value.exitCode === "number" && Number.isFinite(value.exitCode)) {
    command.exitCode = value.exitCode;
  }
  return command;
}

function structuredError(
  details: unknown,
  copy: Record<string, { message: string; suggestion: string }>,
  fallback: TargetServerError,
): TargetServerError {
  if (!isRecord(details)) return fallback;
  const field = parseField(details.field);
  const reason = typeof details.reason === "string" ? details.reason : undefined;
  if (!field || !reason) return fallback;
  const reasonCopy = copy[reason];
  if (!reasonCopy) return fallback;
  const error: TargetServerError = {
    summary: reasonCopy.message,
    field,
    reason,
    message: reasonCopy.message,
    suggestion: reasonCopy.suggestion,
  };
  const command = parseCommand(details.command);
  if (command) error.command = command;
  if (typeof details.output === "string" && details.output) {
    error.output = details.output;
  }
  return error;
}

/**
 * Map one save failure into field-level form guidance.
 * @param errorValue Failure thrown by the shared API transport.
 * @returns Structured summary, optional field anchor, suggestion, and git details.
 */
export function targetServerError(errorValue: unknown): TargetServerError {
  if (errorValue instanceof ApiError) {
    if (errorValue.code === "REPO_INVALID") {
      return structuredError(errorValue.details, REASON_COPY, {
        summary: FALLBACK_SUMMARY,
        suggestion: FALLBACK_SUGGESTION,
      });
    }
    if (errorValue.code === "PROJECT_ID_INVALID") {
      return structuredError(errorValue.details, PROJECT_ID_REASONS, {
        summary: PROJECT_ID_COPY.message,
        suggestion: PROJECT_ID_COPY.suggestion,
      });
    }
    if (errorValue.code === "PRIMARY_METRIC_KEY_INVALID") {
      return structuredError(errorValue.details, PRIMARY_METRIC_KEY_REASONS, {
        summary: PRIMARY_METRIC_KEY_COPY.message,
        suggestion: PRIMARY_METRIC_KEY_COPY.suggestion,
      });
    }
    if (errorValue.code === "MEMBER_ALREADY_CONFIGURED") {
      const field = isRecord(errorValue.details)
        ? parseField(errorValue.details.field)
        : null;
      const error: TargetServerError = { ...MEMBER_ALREADY_CONFIGURED_COPY };
      if (field) error.field = field;
      return error;
    }
    if (errorValue.code === "TARGET_EXISTS") {
      return { summary: "同类型的对象名称已经配置" };
    }
    if (errorValue.code === "TARGET_CONTENT_UNRESOLVED") {
      return {
        summary: "无法读取该基线下的目标文件内容",
        suggestion:
          "服务端未能按基线读取 SKILL.md / AGENT.md 并解析 body hash；请确认仓库地址、子目录与默认基线，或换一个可用版本后重试。",
      };
    }
    return { summary: formatApiError(errorValue, "保存配置失败").message };
  }
  return { summary: formatApiError(errorValue, "保存配置失败").message };
}
