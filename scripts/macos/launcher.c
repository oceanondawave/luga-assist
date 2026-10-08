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

#define BASE_DIR "/Volumes/DATA/CAREER/Projects/luga-assist"
#define PYTHON_EXEC "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
#define LOG_FILE "/Volumes/DATA/CAREER/Projects/luga-assist/logs/luga_assist.log"

int main(int argc, char *argv[]) {
    // 1. Check if Luga Assist is already running on port 8000
    int status_check = system("curl -s -m 1 http://127.0.0.1:8000/api/status >/dev/null 2>&1");
    if (status_check == 0) {
        // Already running: Trigger Spotlight window to appear
        system("curl -s -m 1 -X POST http://127.0.0.1:8000/api/spotlight/show >/dev/null 2>&1");
        system("osascript -e 'display notification \"Luga Assist đang hoạt động. Nhấn F7 để Chat Nổi, F8 để Nói, F9 để Đổi chế độ.\" with title \"Luga Assist\"' >/dev/null 2>&1");
        return 0;
    }

    // 2. Set environment variables
    setenv("PYTHONPATH", BASE_DIR, 1);
    chdir(BASE_DIR);

    // 3. Ensure logs directory exists and redirect standard streams
    mkdir(BASE_DIR "/logs", 0755);
    mkdir(BASE_DIR "/temp", 0755);
    int log_fd = open(LOG_FILE, O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (log_fd >= 0) {
        dup2(log_fd, STDOUT_FILENO);
        dup2(log_fd, STDERR_FILENO);
        close(log_fd);
    }

    // 4. Execute python3 -m app.main inside this bundle process image
    char *args[] = {
        PYTHON_EXEC,
        "-m",
        "app.main",
        NULL
    };

    execv(PYTHON_EXEC, args);

    // If execv fails (e.g. custom python path), try fallback python3 from PATH
    perror("execv failed on primary python3 path, trying PATH fallback");
    char *fallback_args[] = {
        "python3",
        "-m",
        "app.main",
        NULL
    };
    execvp("python3", fallback_args);

    return 1;
}
