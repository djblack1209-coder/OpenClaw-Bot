use std::fs::{self, File, OpenOptions};
use std::io;
use std::path::Path;
use std::time::Duration;

#[derive(Debug)]
pub struct ExclusiveFileLock {
    _file: File,
}

impl ExclusiveFileLock {
    pub fn acquire(path: &Path, attempts: usize, delay_ms: u64) -> io::Result<Self> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        for _ in 0..attempts.max(1) {
            match try_open_exclusive_lock(path)? {
                Some(file) => return Ok(Self { _file: file }),
                None => std::thread::sleep(Duration::from_millis(delay_ms)),
            }
        }
        Err(io::Error::new(
            io::ErrorKind::WouldBlock,
            "另一个应用实例正在执行同一操作",
        ))
    }
}

#[cfg(unix)]
fn try_open_exclusive_lock(path: &Path) -> io::Result<Option<File>> {
    use std::os::fd::AsRawFd;

    const LOCK_EX: i32 = 2;
    const LOCK_NB: i32 = 4;
    extern "C" {
        fn flock(fd: i32, operation: i32) -> i32;
    }

    let file = OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(path)?;
    // 安全性：fd 来自仍存活的 File，operation 仅使用 flock 公共常量。
    let result = unsafe { flock(file.as_raw_fd(), LOCK_EX | LOCK_NB) };
    if result == 0 {
        Ok(Some(file))
    } else {
        let error = io::Error::last_os_error();
        if error.kind() == io::ErrorKind::WouldBlock {
            Ok(None)
        } else {
            Err(error)
        }
    }
}

#[cfg(windows)]
fn try_open_exclusive_lock(path: &Path) -> io::Result<Option<File>> {
    use std::os::windows::fs::OpenOptionsExt;

    match OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .share_mode(0)
        .open(path)
    {
        Ok(file) => Ok(Some(file)),
        Err(error)
            if matches!(
                error.kind(),
                io::ErrorKind::PermissionDenied | io::ErrorKind::WouldBlock
            ) =>
        {
            Ok(None)
        }
        Err(error) => Err(error),
    }
}

/// 读取文件内容
pub fn read_file(path: &str) -> io::Result<String> {
    fs::read_to_string(path)
}

/// 写入文件内容
pub fn write_file(path: &str, content: &str) -> io::Result<()> {
    // 确保父目录存在
    if let Some(parent) = Path::new(path).parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(path, content)
}

/// 在目标目录写临时文件后原子替换，避免配置写到一半被其他进程读取。
pub fn write_file_atomic(path: &str, content: &str) -> io::Result<()> {
    let target = Path::new(path);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut pending = None;
    for sequence in 0..100 {
        let temp_path = target.with_extension(format!("tmp-{}-{}", std::process::id(), sequence));
        let mut options = fs::OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&temp_path) {
            Ok(temp) => {
                pending = Some((temp_path, temp));
                break;
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    let (temp_path, mut temp) = pending.ok_or_else(|| {
        io::Error::new(io::ErrorKind::AlreadyExists, "无法创建唯一的配置临时文件")
    })?;
    let write_result = (|| {
        use std::io::Write;
        temp.write_all(content.as_bytes())?;
        temp.sync_all()?;
        replace_file(&temp_path, target)
    })();
    if write_result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    write_result
}

#[cfg(not(windows))]
fn replace_file(source: &Path, target: &Path) -> io::Result<()> {
    fs::rename(source, target)
}

#[cfg(windows)]
fn replace_file(source: &Path, target: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;

    const MOVEFILE_REPLACE_EXISTING: u32 = 0x1;
    const MOVEFILE_WRITE_THROUGH: u32 = 0x8;
    #[link(name = "Kernel32")]
    extern "system" {
        fn MoveFileExW(existing: *const u16, replacement: *const u16, flags: u32) -> i32;
    }

    let source_wide: Vec<u16> = source.as_os_str().encode_wide().chain(Some(0)).collect();
    let target_wide: Vec<u16> = target.as_os_str().encode_wide().chain(Some(0)).collect();
    // 安全性：两个 UTF-16 缓冲区均以 NUL 结尾，并在系统调用返回前保持存活。
    let replaced = unsafe {
        MoveFileExW(
            source_wide.as_ptr(),
            target_wide.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    };
    if replaced != 0 {
        Ok(())
    } else {
        Err(io::Error::last_os_error())
    }
}

/// 检查文件是否存在
pub fn file_exists(path: &str) -> bool {
    Path::new(path).exists()
}

/// 从环境变量文件读取值
pub fn read_env_value(env_file: &str, key: &str) -> Option<String> {
    let content = read_file(env_file).ok()?;

    content
        .lines()
        .filter_map(parse_env_assignment)
        .filter(|(parsed_key, _)| parsed_key == key)
        .map(|(_, value)| value)
        .last()
}

/// 解析由桌面端维护的 dotenv/export 行，供读取配置和注入子进程环境共用。
pub fn parse_env_assignment(line: &str) -> Option<(String, String)> {
    let line = line.trim();
    if line.is_empty() || line.starts_with('#') {
        return None;
    }
    let line = line.strip_prefix("export ").unwrap_or(line);
    let (key, raw_value) = line.split_once('=')?;
    let key = key.trim();
    if !is_valid_env_key(key) {
        return None;
    }
    let raw_value = raw_value.trim();
    let value = if raw_value.starts_with('"') && raw_value.ends_with('"') && raw_value.len() >= 2 {
        unescape_double_quoted_env_value(&raw_value[1..raw_value.len() - 1])
    } else if raw_value.starts_with('\'') && raw_value.ends_with('\'') && raw_value.len() >= 2 {
        raw_value[1..raw_value.len() - 1].to_string()
    } else {
        raw_value.to_string()
    };
    Some((key.to_string(), value))
}

/// 设置环境变量文件中的值
pub fn set_env_value(env_file: &str, key: &str, value: &str) -> io::Result<()> {
    let content = read_file(env_file).unwrap_or_default();
    let new_line = format_env_assignment(key, value, true)?;
    let mut replaced = false;
    let mut lines = Vec::new();

    for line in content.lines() {
        let matches_key =
            parse_env_assignment(line).is_some_and(|(parsed_key, _)| parsed_key == key);
        if matches_key {
            if !replaced {
                lines.push(new_line.clone());
                replaced = true;
            }
        } else {
            lines.push(line.to_string());
        }
    }

    if !replaced {
        lines.push(new_line);
    }

    write_file_atomic(env_file, &lines.join("\n"))
}

pub fn format_env_assignment(key: &str, value: &str, export: bool) -> io::Result<String> {
    if !is_valid_env_key(key) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "环境变量名格式无效",
        ));
    }
    if value.contains(['\r', '\n', '\0']) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "环境变量值不能包含换行符或 NUL",
        ));
    }
    Ok(format!(
        "{}{}=\"{}\"",
        if export { "export " } else { "" },
        key,
        escape_double_quoted_env_value(value)
    ))
}

fn is_valid_env_key(key: &str) -> bool {
    let mut chars = key.chars();
    matches!(chars.next(), Some(first) if first == '_' || first.is_ascii_alphabetic())
        && chars.all(|ch| ch == '_' || ch.is_ascii_alphanumeric())
}

fn escape_double_quoted_env_value(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for ch in value.chars() {
        if matches!(ch, '\\' | '"' | '$' | '`') {
            escaped.push('\\');
        }
        escaped.push(ch);
    }
    escaped
}

fn unescape_double_quoted_env_value(value: &str) -> String {
    let mut unescaped = String::with_capacity(value.len());
    let mut chars = value.chars();
    while let Some(ch) = chars.next() {
        if ch == '\\' {
            if let Some(next) = chars.next() {
                if matches!(next, '\\' | '"' | '$' | '`') {
                    unescaped.push(next);
                } else {
                    unescaped.push('\\');
                    unescaped.push(next);
                }
            } else {
                unescaped.push('\\');
            }
        } else {
            unescaped.push(ch);
        }
    }
    unescaped
}

/// 从环境变量文件中删除指定的值
pub fn remove_env_value(env_file: &str, key: &str) -> io::Result<()> {
    if !is_valid_env_key(key) {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "环境变量名格式无效",
        ));
    }
    let content = read_file(env_file).unwrap_or_default();
    let lines: Vec<String> = content
        .lines()
        .filter(|line| {
            parse_env_assignment(line)
                .map(|(parsed_key, _)| parsed_key != key)
                .unwrap_or(true)
        })
        .map(|s| s.to_string())
        .collect();

    write_file_atomic(env_file, &lines.join("\n"))
}

#[cfg(test)]
mod tests {
    use super::{
        escape_double_quoted_env_value, format_env_assignment, is_valid_env_key,
        parse_env_assignment, read_env_value, read_file, remove_env_value, set_env_value,
        unescape_double_quoted_env_value, write_file_atomic,
    };

    #[test]
    fn env_keys_must_be_shell_identifiers() {
        assert!(is_valid_env_key("LLM_API_KEY"));
        assert!(!is_valid_env_key("BAD\nKEY"));
        assert!(!is_valid_env_key("1BAD"));
    }

    #[test]
    fn quoted_env_values_round_trip_without_shell_expansion() {
        let value = r#"secret\path"$HOME`whoami`"#;
        let escaped = escape_double_quoted_env_value(value);
        assert_eq!(unescape_double_quoted_env_value(&escaped), value);
        assert!(!escaped.contains("\"$HOME"));
        assert!(!escaped.contains("\"`whoami`"));
        let line = format!("export LLM_API_KEY=\"{}\"", escaped);
        assert_eq!(
            parse_env_assignment(&line),
            Some(("LLM_API_KEY".to_string(), value.to_string()))
        );
        assert!(format_env_assignment("LLM_API_KEY", "safe\ninjected=true", true).is_err());
    }

    #[test]
    fn env_remove_matches_the_parsed_key_exactly() {
        let path = std::env::temp_dir().join(format!(
            "openclaw-manager-env-remove-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        let path = path.to_str().expect("临时路径必须是 UTF-8");
        write_file_atomic(
            path,
            "export LLM_API_KEY=remove-me\nexport LLM_API_KEY_SUFFIX=keep-me\n",
        )
        .expect("应写入测试环境文件");

        remove_env_value(path, "LLM_API_KEY").expect("应删除精确匹配的环境变量");

        assert_eq!(read_env_value(path, "LLM_API_KEY"), None);
        assert_eq!(
            read_env_value(path, "LLM_API_KEY_SUFFIX"),
            Some("keep-me".to_string())
        );
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn env_set_replaces_assignment_without_export_prefix() {
        let path =
            std::env::temp_dir().join(format!("openclaw-manager-env-set-{}", std::process::id()));
        let _ = std::fs::remove_file(&path);
        let path = path.to_str().expect("临时路径必须是 UTF-8");
        write_file_atomic(path, "LLM_BASE_URL=https://old.example\nKEEP=value")
            .expect("应写入无 export 的环境变量");

        set_env_value(path, "LLM_BASE_URL", "https://new.example")
            .expect("应替换无 export 的同名环境变量");

        assert_eq!(
            read_env_value(path, "LLM_BASE_URL"),
            Some("https://new.example".to_string())
        );
        let content = read_file(path).expect("应读取更新后的环境文件");
        assert!(!content.contains("https://old.example"));
        assert!(content.contains("KEEP=value"));
        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn env_set_collapses_mixed_duplicate_assignments() {
        let path = std::env::temp_dir().join(format!(
            "openclaw-manager-env-deduplicate-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        let path = path.to_str().expect("临时路径必须是 UTF-8");
        write_file_atomic(
            path,
            "LLM_API_KEY=old-first\nexport KEEP=value\n  export LLM_API_KEY='old-last'",
        )
        .expect("应写入重复环境变量");

        assert_eq!(
            read_env_value(path, "LLM_API_KEY"),
            Some("old-last".to_string()),
            "桌面读取必须与子进程环境注入一致，后项覆盖前项"
        );

        set_env_value(path, "LLM_API_KEY", "new-secret").expect("应合并重复环境变量");

        let content = read_file(path).expect("应读取去重后的环境文件");
        let matching: Vec<_> = content
            .lines()
            .filter(|line| {
                parse_env_assignment(line)
                    .is_some_and(|(parsed_key, _)| parsed_key == "LLM_API_KEY")
            })
            .collect();
        assert_eq!(matching, vec!["export LLM_API_KEY=\"new-secret\""]);
        assert_eq!(
            read_env_value(path, "LLM_API_KEY"),
            Some("new-secret".to_string())
        );
        let _ = std::fs::remove_file(path);
    }

    #[cfg(unix)]
    #[test]
    fn atomic_secret_file_is_created_with_owner_only_permissions() {
        use std::os::unix::fs::PermissionsExt;

        let path = std::env::temp_dir().join(format!(
            "openclaw-manager-secret-file-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_file(&path);
        write_file_atomic(path.to_str().expect("临时路径必须是 UTF-8"), "secret")
            .expect("应原子写入临时密钥文件");
        let mode = std::fs::metadata(&path)
            .expect("密钥文件应存在")
            .permissions()
            .mode()
            & 0o777;
        assert_eq!(mode, 0o600);
        let _ = std::fs::remove_file(path);
    }
}
