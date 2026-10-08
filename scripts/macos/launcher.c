/*
 * Luga Assist Native macOS Mach-O App Launcher
 * Replaces bash/terminal scripts so the app runs as a 100% native macOS GUI application.
 * Retains bundle identifier (com.luga.assist) so macOS Microphone & Accessibility permissions work permanently.
 */
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <string.h>
#include <mach-o/dyld.h>
#include <libgen.h>

#define DEFAULT_BASE_DIR "/Volumes/DATA/CAREER/Projects/luga-assist"
#define DEFAULT_PYTHON_EXEC "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"

int file_exists(const char *path) {
    struct stat buffer;
    return (stat(path, &buffer) == 0);
}

int main(int argc, char *argv[]) {
    // 1. Check if Luga Assist is already running on port 8000
    int status_check = system("curl -s -m 1 http://127.0.0.1:8000/api/status >/dev/null 2>&1");
    if (status_check == 0) {
        // Already running: Trigger Spotlight window to appear
        system("curl -s -m 1 -X POST http://127.0.0.1:8000/api/spotlight/show >/dev/null 2>&1");
        system("osascript -e 'display notification \"Luga Assist đang hoạt động. Nhấn F7 để Chat Nổi, F8 để Nói, F9 để Đổi chế độ, F10 để Ngắt.\" with title \"Luga Assist\"' >/dev/null 2>&1");
        return 0;
    }

    // 2. Discover Project Directory dynamically
    char base_dir[1024];
    const char *env_base = getenv("LUGA_BASE_DIR");
    if (env_base && strlen(env_base) > 0) {
        strncpy(base_dir, env_base, sizeof(base_dir) - 1);
    } else {
        // Try resolving from executable location
        char exec_path[1024];
        uint32_t size = sizeof(exec_path);
        if (_NSGetExecutablePath(exec_path, &size) == 0) {
            char dir1[1024], dir2[1024], dir3[1024], test_file[1024];
            // exec_path = .../Luga Assist.app/Contents/MacOS/launcher
            strncpy(dir1, exec_path, sizeof(dir1) - 1);
            char *p1 = dirname(dir1); // Contents/MacOS
            strncpy(dir2, p1, sizeof(dir2) - 1);
            char *p2 = dirname(dir2); // Contents
            strncpy(dir3, p2, sizeof(dir3) - 1);
            char *bundle_dir = dirname(dir3); // .../Luga Assist.app
            char *parent_dir = dirname(bundle_dir); // folder containing .app

            snprintf(test_file, sizeof(test_file), "%s/app/main.py", parent_dir);
            if (file_exists(test_file)) {
                strncpy(base_dir, parent_dir, sizeof(base_dir) - 1);
            } else if (file_exists(DEFAULT_BASE_DIR "/app/main.py")) {
                strncpy(base_dir, DEFAULT_BASE_DIR, sizeof(base_dir) - 1);
            } else {
                getcwd(base_dir, sizeof(base_dir) - 1);
            }
        } else {
            strncpy(base_dir, DEFAULT_BASE_DIR, sizeof(base_dir) - 1);
        }
    }

    // 3. Set environment variables
    setenv("PYTHONPATH", base_dir, 1);
    chdir(base_dir);

    // 4. Ensure logs and temp directories exist
    char logs_dir[1024], temp_dir[1024], log_file[1024];
    snprintf(logs_dir, sizeof(logs_dir), "%s/logs", base_dir);
    snprintf(temp_dir, sizeof(temp_dir), "%s/temp", base_dir);
    snprintf(log_file, sizeof(log_file), "%s/logs/luga_assist.log", base_dir);

    mkdir(logs_dir, 0755);
    mkdir(temp_dir, 0755);

    int log_fd = open(log_file, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (log_fd >= 0) {
        dup2(log_fd, STDOUT_FILENO);
        dup2(log_fd, STDERR_FILENO);
        close(log_fd);
    }

    // 5. Discover Python 3 executable
    const char *python_exec = getenv("PYTHON_EXEC");
    if (!python_exec || strlen(python_exec) == 0) {
        if (file_exists(DEFAULT_PYTHON_EXEC)) {
            python_exec = DEFAULT_PYTHON_EXEC;
        } else if (file_exists("/opt/homebrew/bin/python3")) {
            python_exec = "/opt/homebrew/bin/python3";
        } else if (file_exists("/usr/local/bin/python3")) {
            python_exec = "/usr/local/bin/python3";
        } else {
            python_exec = "python3";
        }
    }

    char *args[] = {
        (char *)python_exec,
        "-m",
        "app.main",
        NULL
    };

    execv(python_exec, args);

    // If execv fails (e.g. not absolute path or custom venv), try PATH lookup
    execvp("python3", args);

    perror("Failed to launch python3 -m app.main");
    return 1;
}
