/// 统一错误类型 — 所有 Tauri command 使用此类型替代 Result<T, String>
///
/// 设计原则:
/// 1. 前端通过 `kind` 字段程序化区分错误类型（网络/配置/权限等）
/// 2. `message` 提供人类可读的中文描述
/// 3. `Serialize` 让 Tauri 将结构体序列化为 JSON 传给前端
/// 4. 提供 From<String> 兼容旧代码逐步迁移
use serde::Serialize;

/// 错误分类 — 前端根据此字段决定展示策略（toast/弹窗/重试按钮等）
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {
    /// 文件/目录读写失败
    Io,
    /// JSON/TOML 等序列化/反序列化失败
    Serialization,
    /// HTTP 请求失败（网络不通、超时、ClawBot API 不可达等）
    Network,
    /// 配置文件缺失或格式错误
    Config,
    /// 子进程启动/终止失败
    Process,
    /// 权限不足（Sandbox 限制、文件权限等）
    Permission,
    /// 请求的资源不存在（插件/服务/文件等）
    NotFound,
    /// 操作超时
    Timeout,
    /// 参数校验失败
    Validation,
    /// 服务/功能状态冲突（如服务已在运行时再次启动）
    Conflict,
    /// 未知/未分类错误
    Unknown,
}

/// 结构化应用错误 — 替代所有 command 中的 String 错误
#[derive(Debug, Clone, Serialize)]
pub struct AppError {
    /// 错误分类，前端用于程序化判断
    pub kind: ErrorKind,
    /// 人类可读的描述（中文）
    pub message: String,
}

impl AppError {
    /// 创建指定类型的错误
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
        }
    }

    /// IO 错误快捷构造
    pub fn io(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Io, msg)
    }

    /// 序列化错误快捷构造
    pub fn serialization(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Serialization, msg)
    }

    /// 网络错误快捷构造
    pub fn network(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Network, msg)
    }

    /// 配置错误快捷构造
    pub fn config(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Config, msg)
    }

    /// 进程错误快捷构造
    pub fn process(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Process, msg)
    }

    /// 未找到错误快捷构造
    pub fn not_found(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::NotFound, msg)
    }

    /// 超时错误快捷构造
    pub fn timeout(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Timeout, msg)
    }

    /// 校验错误快捷构造
    pub fn validation(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Validation, msg)
    }

    /// 冲突错误快捷构造
    pub fn conflict(msg: impl Into<String>) -> Self {
        Self::new(ErrorKind::Conflict, msg)
    }
}

/// 兼容旧代码：String 可以直接转为 AppError（分类为 Unknown）
impl From<String> for AppError {
    fn from(msg: String) -> Self {
        Self::new(ErrorKind::Unknown, msg)
    }
}

/// std::io::Error → AppError
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self {
        match e.kind() {
            std::io::ErrorKind::NotFound => Self::not_found(format!("文件或目录不存在: {}", e)),
            std::io::ErrorKind::PermissionDenied => Self::new(ErrorKind::Permission, format!("权限不足: {}", e)),
            _ => Self::io(format!("IO 操作失败: {}", e)),
        }
    }
}

/// serde_json::Error → AppError
impl From<serde_json::Error> for AppError {
    fn from(e: serde_json::Error) -> Self {
        Self::serialization(format!("JSON 解析失败: {}", e))
    }
}

/// reqwest::Error → AppError
impl From<reqwest::Error> for AppError {
    fn from(e: reqwest::Error) -> Self {
        if e.is_timeout() {
            Self::timeout(format!("HTTP 请求超时: {}", e))
        } else if e.is_connect() {
            Self::network(format!("无法连接: {}", e))
        } else {
            Self::network(format!("网络请求失败: {}", e))
        }
    }
}

/// 实现 Display 用于日志输出
impl std::fmt::Display for AppError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{:?}] {}", self.kind, self.message)
    }
}

// 注意: Tauri 2 的 InvokeError 已有 blanket impl From<T: Serialize>，
// AppError 实现了 Serialize，因此 Tauri 会自动将 AppError 序列化为 JSON
// 传给前端（包含 kind + message 字段）。无需手动实现 From<AppError> for InvokeError。

/// 简化类型别名 — command 返回值直接用 AppResult<T>
pub type AppResult<T> = Result<T, AppError>;
