class ArchiveError(Exception):
    """Base class for archive operation failures."""

    user_message = "解压失败。"

    def __init__(self, message: str | None = None):
        super().__init__(message or self.user_message)


class SevenZipMissing(ArchiveError):
    user_message = "未找到 7-Zip 后端，请安装 7-Zip 或使用 --sevenzip 指定 7z.exe 路径。"


class ArchiveNotFound(ArchiveError):
    user_message = "找不到压缩包。"


class OutputPermissionDenied(ArchiveError):
    user_message = "没有写入目标目录的权限。"


class PathTraversalBlocked(ArchiveError):
    user_message = "已阻止不安全的压缩包路径。"


class ArchiveCancelled(ArchiveError):
    user_message = "解压任务已取消。"


class UnsupportedFormat(ArchiveError):
    user_message = "暂不支持该压缩包格式。"


class PasswordRequired(ArchiveError):
    user_message = "该压缩包需要密码。"


class WrongPassword(ArchiveError):
    user_message = "密码错误。"


class CorruptedArchive(ArchiveError):
    user_message = "压缩包可能已损坏。"


class UnknownArchiveError(ArchiveError):
    user_message = "解压失败，请检查压缩包是否损坏或格式是否受支持。"
