"""Cross-platform helpers (Linux lab workstations + Windows dev laptops)."""

import subprocess
import sys


def is_windows() -> bool:
    return sys.platform == "win32"


def detached_process_kwargs() -> dict:
    """Start a background process detached from the GUI process."""
    if is_windows():
        flags = subprocess.CREATE_NEW_PROCESS_GROUP
        if hasattr(subprocess, "DETACHED_PROCESS"):
            flags |= subprocess.DETACHED_PROCESS
        return {"creationflags": flags}
    return {"start_new_session": True}


def terminate_process(pid: int) -> None:
    """Stop a process by PID on Linux or Windows."""
    if is_windows():
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
        )
    else:
        import os
        import signal
        os.kill(pid, signal.SIGTERM)


def notify_user(title: str, message: str) -> None:
    """Best-effort desktop notification (optional — failures are ignored)."""
    try:
        if is_windows():
            # PowerShell toast (Windows 10+). Requires WinRT; fallback is silent skip.
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, "
                "Windows.UI.Notifications, ContentType = WindowsRuntime] "
                "| Out-Null; "
                "$t = [Windows.UI.Notifications.ToastNotificationManager]::"
                "CreateToastNotifier('Lab Sharing'); "
                "$x = [Windows.UI.Notifications.ToastNotification]::"
                "new([Windows.Data.Xml.Dom.XmlDocument]::new()); "
                "$x.Content.LoadXml("
                f"'<toast><visual><binding template=\"ToastText02\">"
                f"<text id=\"1\">{title}</text>"
                f"<text id=\"2\">{message}</text>"
                f"</binding></visual></toast>'); "
                "$t.Show($x)"
            )
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                ["notify-send", title, message],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except Exception:
        pass


def git_daemon_base_path(path: str) -> str:
    """Git daemon accepts forward slashes on Windows."""
    return path.replace("\\", "/")
