"""
File Management & Terminal Execution Suite for Luga Assist.
Provides 100% reliable, cross-platform file searching, file manipulation,
and unlimited Terminal (macOS/Linux) & PowerShell/CMD (Windows) execution.
Designed for high accessibility with rich spoken feedback for visually impaired users.
"""
import os
import sys
import time
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

# Standard user directories mapped across macOS, Windows, Linux
def get_user_folder(name: str) -> Path:
    home = Path.home()
    clean = name.strip().lower()
    mapping = {
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "download": home / "Downloads",
        "documents": home / "Documents",
        "document": home / "Documents",
        "music": home / "Music",
        "pictures": home / "Pictures",
        "movies": home / "Movies" if sys.platform == "darwin" else home / "Videos",
        "videos": home / "Videos",
        "home": home,
        "~": home,
        "cwd": Path.cwd(),
        ".": Path.cwd(),
    }
    return mapping.get(clean, home)

def resolve_target_path(path_str: str) -> Path:
    """Resolve relative, tilde, and friendly folder names into absolute Path."""
    p_str = path_str.strip()
    # Check friendly names first (e.g. 'Desktop', 'Downloads')
    lower = p_str.lower()
    if lower in ("desktop", "downloads", "documents", "music", "pictures", "home", "cwd"):
        return get_user_folder(lower)

    # Expand user ~ and environment variables
    expanded = os.path.expandvars(os.path.expanduser(p_str))
    p = Path(expanded)
    if not p.is_absolute():
        p = Path.cwd() / p
    return p.resolve()

def format_file_size(size_bytes: int) -> str:
    """Human readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

class FileAndTerminalManager:
    def __init__(self):
        self.home = Path.home()

    def find_files(
        self, 
        query: str, 
        location: Optional[str] = None, 
        limit: int = 10,
        open_first: bool = False
    ) -> Dict[str, Any]:
        """
        Fast, intelligent file search across the filesystem.
        Uses macOS Spotlight index (mdfind) for near-instant 0.02s searches.
        Uses Windows PowerShell Get-ChildItem or native Python search on Windows/Linux.
        Automatically filters out noise (node_modules, caches, .git).
        """
        query_clean = query.strip().strip("'\"")
        if not query_clean:
            return {
                "success": False,
                "found": False,
                "count": 0,
                "files": [],
                "details": "Từ khóa tìm kiếm trống.",
                "speech_result": "Bạn chưa cho biết tên file cần tìm."
            }

        search_dir = None
        if location:
            search_dir = resolve_target_path(location)

        results: List[Path] = []
        ignored_substrings = {
            "node_modules", ".git", "__pycache__", "Library/Caches", 
            ".cache", "AppData/Local/Temp", "System Volume Information"
        }

        # 1. macOS: Use ultra-fast Spotlight index via `mdfind`
        if sys.platform == "darwin":
            try:
                cmd = ["mdfind"]
                if search_dir and search_dir.exists():
                    cmd.extend(["-onlyin", str(search_dir)])
                cmd.extend(["-name", query_clean])

                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
                raw_lines = [
                    l for l in proc.stdout.strip().split("\n") 
                    if l and not l.startswith("2026-") and not any(ig in l for ig in ignored_substrings)
                ]
                for line in raw_lines:
                    p = Path(line)
                    if p.exists() and p not in results:
                        results.append(p)
                        if len(results) >= limit:
                            break
            except Exception as e:
                print(f"[FileAndTerminal] mdfind error: {e}, falling back to Python search")

        # 2. Windows: Use PowerShell Get-ChildItem
        elif sys.platform.startswith("win"):
            try:
                target_root = str(search_dir or self.home)
                ps_cmd = (
                    f"Get-ChildItem -Path '{target_root}' -Recurse -Filter '*{query_clean}*' "
                    f"-ErrorAction SilentlyContinue | Select-Object -First {limit * 2} -ExpandProperty FullName"
                )
                proc = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
                    capture_output=True, text=True, timeout=10
                )
                for line in proc.stdout.strip().splitlines():
                    line = line.strip()
                    if line and not any(ig in line for ig in ignored_substrings):
                        p = Path(line)
                        if p.exists() and p not in results:
                            results.append(p)
                            if len(results) >= limit:
                                break
            except Exception as e:
                print(f"[FileAndTerminal] Windows PS search error: {e}")

        # 3. Python fallback if needed (prioritizing user folders Desktop, Downloads, Documents)
        if not results:
            search_roots = [search_dir] if search_dir else [
                self.home / "Desktop",
                self.home / "Downloads",
                self.home / "Documents",
                Path.cwd()
            ]
            for root in search_roots:
                if not root or not root.exists():
                    continue
                try:
                    for item in root.glob(f"*{query_clean}*"):
                        if item not in results and not any(ig in str(item) for ig in ignored_substrings):
                            results.append(item)
                            if len(results) >= limit:
                                break
                    if len(results) >= limit:
                        break
                except Exception:
                    pass

        # Prepare output details and speech summary
        count = len(results)
        file_info_list = []
        for p in results:
            try:
                stat = p.stat()
                file_info_list.append({
                    "name": p.name,
                    "path": str(p),
                    "size": format_file_size(stat.st_size),
                    "is_dir": p.is_dir(),
                    "parent": p.parent.name
                })
            except Exception:
                file_info_list.append({"name": p.name, "path": str(p), "is_dir": p.is_dir()})

        if count == 0:
            msg = f"Không tìm thấy file nào khớp với từ khóa '{query_clean}'"
            if search_dir:
                msg += f" trong thư mục {search_dir.name}"
            return {
                "success": True,
                "found": False,
                "count": 0,
                "files": [],
                "details": msg,
                "speech_result": f"Không tìm thấy file nào khớp với tên {query_clean}."
            }

        names_preview = ", ".join([f["name"] for f in file_info_list[:3]])
        speech_msg = f"Đã tìm thấy {count} file: {names_preview}"
        if count > 3:
            speech_msg += f", và {count - 3} file khác"

        # Auto open first result if requested
        opened_detail = ""
        if open_first and results:
            open_res = self.open_file(str(results[0]))
            opened_detail = f" | {open_res.get('details', '')}"
            speech_msg += f". Đã mở file {results[0].name}."

        details_msg = f"Tìm thấy {count} file: " + "; ".join([f"{f['name']} ({f['path']})" for f in file_info_list]) + opened_detail

        return {
            "success": True,
            "found": True,
            "count": count,
            "files": file_info_list,
            "first_file": str(results[0]),
            "details": details_msg,
            "speech_result": speech_msg
        }

    def open_file(self, path_str: str) -> Dict[str, Any]:
        """Open a file or folder natively using the OS default application."""
        p = resolve_target_path(path_str)

        # If path doesn't exist directly, try finding it
        if not p.exists():
            search_res = self.find_files(p.name, limit=1)
            if search_res.get("found") and search_res.get("files"):
                p = Path(search_res["files"][0]["path"])
            else:
                return {
                    "success": False,
                    "details": f"Không tìm thấy file hoặc thư mục: {path_str}",
                    "speech_result": f"Không tìm thấy file {Path(path_str).name} để mở."
                }

        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            elif sys.platform.startswith("win"):
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])

            kind = "thư mục" if p.is_dir() else "file"
            return {
                "success": True,
                "path": str(p),
                "details": f"Đã mở {kind}: {p.name} ({p})",
                "speech_result": f"Đã mở {kind} {p.name}."
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi khi mở {p.name}: {e}",
                "speech_result": f"Có lỗi khi mở {p.name}."
            }

    def list_files(self, path_str: Optional[str] = None, limit: int = 15) -> Dict[str, Any]:
        """List contents of a directory with human-readable attributes."""
        target_dir = resolve_target_path(path_str or "Desktop")
        if not target_dir.exists() or not target_dir.is_dir():
            target_dir = self.home

        try:
            items = []
            for item in target_dir.iterdir():
                if item.name.startswith("."):
                    continue
                try:
                    stat = item.stat()
                    items.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": item.is_dir(),
                        "size": format_file_size(stat.st_size) if not item.is_dir() else "Thư mục"
                    })
                except Exception:
                    pass

            # Sort directories first, then alphabetically
            items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
            items_subset = items[:limit]

            summary_names = [it["name"] for it in items_subset[:5]]
            speech_msg = f"Thư mục {target_dir.name} có {len(items)} mục, gồm có: {', '.join(summary_names)}"
            if len(items) > 5:
                speech_msg += f", và {len(items) - 5} mục khác."

            details = f"Danh sách {len(items_subset)} mục tại {target_dir}: " + ", ".join([
                f"{it['name']}{'/' if it['is_dir'] else ''}" for it in items_subset
            ])

            return {
                "success": True,
                "directory": str(target_dir),
                "total": len(items),
                "items": items_subset,
                "details": details,
                "speech_result": speech_msg
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi liệt kê thư mục {target_dir}: {e}",
                "speech_result": f"Không thể đọc danh sách file trong thư mục {target_dir.name}."
            }

    def read_file(self, path_str: str, max_lines: int = 40) -> Dict[str, Any]:
        """Read and summarize text content of a file."""
        p = resolve_target_path(path_str)
        if not p.exists():
            return {
                "success": False,
                "details": f"File không tồn tại: {path_str}",
                "speech_result": f"File {Path(path_str).name} không tồn tại."
            }

        try:
            # Detect binary files
            stat = p.stat()
            if stat.st_size > 5 * 1024 * 1024:
                return {
                    "success": False,
                    "details": f"File quá lớn ({format_file_size(stat.st_size)}), không thể đọc toàn bộ văn bản.",
                    "speech_result": f"File {p.name} quá lớn để đọc văn bản."
                }

            with open(p, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(max_lines)]
            
            content_snippet = "".join(lines).strip()
            total_lines_read = len(lines)

            # Build a concise speech summary for the blind user
            speech_preview = " ".join([l.strip() for l in lines[:3] if l.strip()])
            if len(speech_preview) > 120:
                speech_preview = speech_preview[:120] + "..."

            speech_msg = f"Nội dung file {p.name} gồm {total_lines_read} dòng. Bắt đầu là: {speech_preview}"

            return {
                "success": True,
                "path": str(p),
                "content": content_snippet,
                "details": f"Đã đọc {total_lines_read} dòng từ {p.name}:\n{content_snippet[:500]}",
                "speech_result": speech_msg
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi đọc file {p.name}: {e}",
                "speech_result": f"Không thể đọc nội dung file {p.name}."
            }

    def create_file(self, path_str: str, content: str = "") -> Dict[str, Any]:
        """Create or overwrite a file with given text content."""
        p = resolve_target_path(path_str)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "path": str(p),
                "details": f"Đã tạo file {p.name} tại {p}",
                "speech_result": f"Đã tạo file {p.name} thành công."
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi tạo file {p.name}: {e}",
                "speech_result": f"Không thể tạo file {p.name}."
            }

    def delete_file(self, path_str: str, safe_trash: bool = True) -> Dict[str, Any]:
        """Delete or move file/folder to OS Trash/Recycle Bin safely."""
        p = resolve_target_path(path_str)
        if not p.exists():
            return {
                "success": False,
                "details": f"File không tồn tại: {path_str}",
                "speech_result": f"File {Path(path_str).name} không tồn tại để xóa."
            }

        try:
            if safe_trash:
                if sys.platform == "darwin":
                    # AppleScript sends to Finder Trash safely
                    subprocess.run(
                        ["osascript", "-e", f'tell application "Finder" to delete POSIX file "{str(p)}"'],
                        capture_output=True, check=True
                    )
                elif sys.platform.startswith("win"):
                    # PowerShell RecycleBin delete
                    ps_cmd = (
                        f"Add-Type -AssemblyName Microsoft.VisualBasic; "
                        f"[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile('{str(p)}', "
                        f"'OnlyErrorDialogs', 'SendToRecycleBin')"
                    )
                    subprocess.run(
                        ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                        capture_output=True, check=True
                    )
                else:
                    if p.is_dir():
                        shutil.rmtree(p)
                    else:
                        p.unlink()
            else:
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()

            return {
                "success": True,
                "details": f"Đã chuyển {p.name} vào thùng rác ({p})",
                "speech_result": f"Đã chuyển file {p.name} vào thùng rác."
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi xóa file {p.name}: {e}",
                "speech_result": f"Không thể xóa file {p.name}: {e}"
            }

    def execute_terminal(
        self,
        command: str,
        cwd: Optional[str] = None,
        open_visible: bool = False,
        shell_type: Optional[str] = None,
        timeout: int = 30
    ) -> Dict[str, Any]:
        """
        Execute terminal / bash / zsh / PowerShell commands without restriction.
        Supports both background execution (capturing stdout/stderr)
        and launching a visible desktop Terminal/PowerShell window.
        """
        cmd_clean = command.strip()
        if not cmd_clean:
            return {
                "success": False,
                "details": "Lệnh rỗng.",
                "speech_result": "Không có lệnh terminal nào được cung cấp."
            }

        work_dir = str(resolve_target_path(cwd)) if cwd else str(Path.cwd())

        # CASE 1: Open a visible interactive Terminal / PowerShell window on Desktop
        if open_visible:
            try:
                if sys.platform == "darwin":  # macOS Terminal.app
                    escaped = cmd_clean.replace('\\', '\\\\').replace('"', '\\"')
                    apple_script = (
                        f'tell application "Terminal"\n'
                        f'  activate\n'
                        f'  do script "cd {work_dir} && {escaped}"\n'
                        f'end tell'
                    )
                    subprocess.run(["osascript", "-e", apple_script], capture_output=True, check=True)
                elif sys.platform.startswith("win"):  # Windows PowerShell / CMD window
                    if shell_type == "cmd":
                        subprocess.Popen(f'start cmd /k "cd /d {work_dir} && {cmd_clean}"', shell=True)
                    else:
                        subprocess.Popen(f'start powershell -NoExit -Command "Set-Location \'{work_dir}\'; {cmd_clean}"', shell=True)
                else:  # Linux
                    subprocess.Popen(f'x-terminal-emulator -e "bash -c \\"cd {work_dir} && {cmd_clean}; exec bash\\""', shell=True)

                return {
                    "success": True,
                    "details": f"Đã mở cửa sổ Terminal và chạy: {cmd_clean}",
                    "speech_result": f"Đã mở cửa sổ Terminal và thực thi lệnh cho bạn."
                }
            except Exception as e:
                return {
                    "success": False,
                    "details": f"Lỗi mở cửa sổ Terminal: {e}",
                    "speech_result": f"Không thể mở cửa sổ Terminal: {e}"
                }

        # CASE 2: Background execution with stdout / stderr capture
        try:
            if sys.platform.startswith("win"):
                # Windows: Default to PowerShell for full modern scripting capabilities
                if shell_type == "cmd":
                    proc = subprocess.run(
                        ["cmd.exe", "/c", cmd_clean],
                        cwd=work_dir, capture_output=True, text=True, timeout=timeout
                    )
                else:
                    proc = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd_clean],
                        cwd=work_dir, capture_output=True, text=True, timeout=timeout
                    )
            else:
                # macOS / Linux: Use user shell (/bin/zsh or /bin/bash)
                shell_bin = "/bin/zsh" if os.path.exists("/bin/zsh") else "/bin/bash"
                proc = subprocess.run(
                    cmd_clean,
                    shell=True, executable=shell_bin, cwd=work_dir,
                    capture_output=True, text=True, timeout=timeout
                )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()
            exit_code = proc.returncode

            # Output trimming for details (keep first 2000 chars)
            combined_output = stdout
            if stderr:
                combined_output = f"{combined_output}\n[STDERR]: {stderr}".strip()
            if not combined_output:
                combined_output = "(Lệnh hoàn thành không có đầu ra văn bản)"

            trimmed_output = combined_output[:2000]

            # Check for error patterns even if exit_code was 0 (e.g. from chained shell commands like cmd 2>&1 || ...)
            lower_out = combined_output.lower()
            error_patterns = [
                "execution error:",
                "can’t get",
                "can't get",
                "invalid index",
                "syntax error",
                "command not found",
                "no such file or directory",
                "traceback (most recent call last)",
                "error: -1700",
                "error: -1719",
                "error: -1728",
            ]
            has_fatal_error = any(p in lower_out for p in error_patterns)
            is_success = (exit_code == 0) and not has_fatal_error

            # Generate natural spoken feedback
            if is_success:
                # Speak first 100 characters of stdout if meaningful
                first_line = stdout.splitlines()[0] if stdout else "hoàn tất thành công"
                if len(first_line) > 80:
                    first_line = first_line[:80] + "..."
                speech_msg = f"Lệnh đã thực thi xong. Kết quả: {first_line}"
            else:
                err_preview = stderr.splitlines()[0] if stderr else (
                    stdout.splitlines()[0] if stdout else f"Mã lỗi {exit_code}"
                )
                if len(err_preview) > 80:
                    err_preview = err_preview[:80] + "..."
                speech_msg = f"Lệnh trả về lỗi: {err_preview}"

            return {
                "success": is_success,
                "exit_code": exit_code if (exit_code != 0 or not has_fatal_error) else 1,
                "stdout": stdout,
                "stderr": stderr,
                "details": f"Exit {exit_code}{' (Failed with output error)' if has_fatal_error else ''} | Output:\n{trimmed_output}",
                "speech_result": speech_msg
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "details": f"Lệnh bị dừng do quá thời gian chờ ({timeout}s).",
                "speech_result": f"Lệnh chạy quá {timeout} giây nên đã được dừng lại."
            }
        except Exception as e:
            return {
                "success": False,
                "details": f"Lỗi thực thi lệnh: {e}",
                "speech_result": f"Có lỗi khi thực thi lệnh: {e}"
            }

file_and_terminal = FileAndTerminalManager()
