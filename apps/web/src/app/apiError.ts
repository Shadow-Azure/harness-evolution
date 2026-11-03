import { ApiError } from "../api/http";

const PAGE_HANDLED_CONFLICT_CODES: ReadonlySet<string> = new Set([
  "BAD_CASE_SESSION_MISMATCH",
  "TARGET_EXISTS",
  "TARGET_IN_USE",
]);

const FIELD_LABELS: Readonly<Record<string, string>> = {
  defaultRef: "基线分支或标签",
  from: "起始时间",
  mode: "运行模式",
  password: "密码",
  objectName: "对象名称",
  repoUrl: "仓库地址",
  sessionId: "Session ID",
  status: "状态筛选",
  subDir: "子目录",
  targetType: "对象类型",
  username: "用户名",
  testProjectId: "测试集测试工程 ID",
  to: "结束时间",
  validationProjectId: "验证集测试工程 ID",
  version: "目标版本",
};

const LOCATION_LABELS: Readonly<Record<string, string>> = {
  body: "请求体字段",
  path: "路径参数",
  query: "查询参数",
};

const VALIDATION_REASONS: Readonly<Record<string, string>> = {
  enum: "不在可选范围内，请选择有效选项",
  int_parsing: "应为有效数字，请修改格式",
  missing: "不能为空，请检查输入",
  number_inclusive_maximum: "超出允许上限，请降低数值",
  number_inclusive_minimum: "低于允许下限，请提高数值",
  string_pattern_mismatch: "格式不正确，请按字段要求修改",
  string_too_long: "长度超出限制，请缩短内容",
  string_too_short: "不能为空，请填写",
  value_error: "格式不正确，请按字段要求修改",
};

/** User-facing result derived from a normalized API failure. */
export type FormattedApiError = {
  message: string;
  fieldErrors: Record<string, string>;
};

type ValidationDetail = {
  loc?: unknown;
  type?: unknown;
};

function safeText(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function fieldKey(detail: ValidationDetail): string {
  const loc = Array.isArray(detail.loc) ? detail.loc : [];
  const last = loc.at(-1);
  return typeof last === "string" && last ? last : "input";
}

function fieldLabel(detail: ValidationDetail, key: string): string {
  const knownLabel = FIELD_LABELS[key];
  if (knownLabel) {
    return knownLabel;
  }

  const loc = Array.isArray(detail.loc) ? detail.loc : [];
  const location = safeText(loc.at(0));
  return location in LOCATION_LABELS
    ? (LOCATION_LABELS[location] ?? "输入")
    : "输入";
}

function validationReason(type: string): string {
  return VALIDATION_REASONS[type] ?? "无效，请检查输入";
}

/**
 * Turn sanitized request-validation details into field-local fixes.
 * @param details Unknown error details transported by `ApiError`.
 * @returns Field errors keyed by the final request location segment.
 */
export function formatValidationDetails(
  details: unknown,
): Record<string, string> {
  const errors =
    details && typeof details === "object" && "errors" in details
      ? (details as { errors?: unknown }).errors
      : null;
  if (!Array.isArray(errors)) {
    return {};
  }

  return errors.reduce<Record<string, string>>((fieldErrors, item) => {
    if (!item || typeof item !== "object") {
      return fieldErrors;
    }
    const detail = item as ValidationDetail;
    const key = fieldKey(detail);
    const type = safeText(detail.type) || "invalid";
    const label = key === "input" ? "输入" : fieldLabel(detail, key);
    const separator = /[A-Za-z0-9]$/.test(label) ? " " : "";
    fieldErrors[key] = `${label}${separator}${validationReason(type)}后再试。`;
    return fieldErrors;
  }, {});
}

function stableMessage(error: ApiError, fallback?: string): string {
  switch (error.code) {
    case "AUTH_REQUIRED":
    case "AUTH_FORBIDDEN":
    case "PERMISSION_DENIED":
      return "当前账号没有执行此操作的权限，请联系管理员。";
    case "INTERNAL":
    case "SERVICE_UNAVAILABLE":
      return "服务暂时不可用，请稍后重试；若持续失败请联系管理员。";
    case "NETWORK_ERROR":
      return "网络连接不可用，请检查网络后重试。";
    case "RUN_BUSY":
      return "已有任务正在运行，请等待当前任务结束后重试。";
    case "NO_PROBES_MATCHED":
      return "筛选条件没有匹配轨迹，请放宽对象、版本或时间范围后重试。";
    case "VALIDATION_INVALID":
      return fallback
        ? `${fallback}，请检查输入后重试。`
        : "请求参数无效，请检查输入后重试。";
    default:
      return "";
  }
}

/**
 * Format an operation failure into actionable user-facing copy.
 * @param error Failure raised by the shared API transport or application code.
 * @param fallback Optional operation-specific sentence root.
 * @returns A summary message and optional field-local messages.
 */
export function formatApiError(
  error: unknown,
  fallback?: string,
): FormattedApiError {
  if (error instanceof ApiError) {
    const fieldErrors =
      error.code === "VALIDATION_INVALID"
        ? formatValidationDetails(error.details)
        : {};
    const reasons = Object.values(fieldErrors).map((reason) =>
      reason.replace(/。$/u, ""),
    );
    if (reasons.length > 0) {
      return {
        message: `请检查以下输入：${reasons.join("；")}。`,
        fieldErrors,
      };
    }

    const knownMessage =
      stableMessage(error, fallback) ||
      (/[\p{Script=Han}]/u.test(error.message) ? error.message : "");
    return {
      message:
        knownMessage ||
        (fallback ? `${fallback}，请稍后重试。` : "操作失败，请稍后重试。"),
      fieldErrors,
    };
  }

  return {
    message: fallback ? `${fallback}，请稍后重试。` : "操作失败，请稍后重试。",
    fieldErrors: {},
  };
}

/**
 * Present a non-blocking 409 conflict through the application notification seam.
 * @param error Failure raised by the shared API transport.
 * @param notify User-facing notification callback.
 * @returns Whether the error was handled as a conflict.
 */
export function presentConflict(
  error: unknown,
  notify: (message: string) => void,
): boolean {
  if (!(error instanceof ApiError) || error.status !== 409) {
    return false;
  }
  if (PAGE_HANDLED_CONFLICT_CODES.has(error.code)) {
    return false;
  }
  notify(error.message || "当前有任务正在运行");
  return true;
}
