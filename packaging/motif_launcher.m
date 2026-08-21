/*
 * Motif.app executable. Embeds the project venv's CPython so CGEventTap /
 * Accessibility clients run inside this process. TCC then lists Motif, not
 * Terminal or .venv/bin/python.
 *
 * Layout: Motif.app sits next to start.py and .venv (project root).
 */
#define PY_SSIZE_T_CLEAN
#import <Cocoa/Cocoa.h>
#include <Python.h>
#include <libgen.h>
#include <limits.h>
#include <mach-o/dyld.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#ifndef MOTIF_BUILD_PYTHON
#define MOTIF_BUILD_PYTHON "/usr/bin/python3"
#endif

static int path_exists(const char *path) {
    struct stat st;
    return path && path[0] && stat(path, &st) == 0;
}

static void alert_error(const char *title, const char *detail) {
    @autoreleasepool {
        NSAlert *alert = [[NSAlert alloc] init];
        alert.alertStyle = NSAlertStyleCritical;
        alert.messageText = [NSString stringWithUTF8String:title];
        alert.informativeText = [NSString stringWithUTF8String:detail];
        [alert runModal];
    }
}

static int parent_dir(char *path) {
    char *slash = strrchr(path, '/');
    if (slash == NULL || slash == path) {
        return -1;
    }
    *slash = '\0';
    return 0;
}

static int read_first_line(const char *path, char *out, size_t out_n) {
    FILE *fp = fopen(path, "r");
    if (fp == NULL) {
        return -1;
    }
    if (fgets(out, (int)out_n, fp) == NULL) {
        fclose(fp);
        return -1;
    }
    fclose(fp);
    size_t n = strlen(out);
    while (n > 0 && (out[n - 1] == '\n' || out[n - 1] == '\r' || out[n - 1] == ' ' || out[n - 1] == '\t')) {
        out[--n] = '\0';
    }
    return n == 0 ? -1 : 0;
}

static int read_pyvenv_home(const char *cfg, char *home, size_t home_n) {
    FILE *fp = fopen(cfg, "r");
    if (fp == NULL) {
        return -1;
    }
    char line[PATH_MAX];
    int found = 0;
    while (fgets(line, sizeof(line), fp) != NULL) {
        if (strncmp(line, "home", 4) != 0) {
            continue;
        }
        char *eq = strchr(line, '=');
        if (eq == NULL) {
            continue;
        }
        eq++;
        while (*eq == ' ' || *eq == '\t') {
            eq++;
        }
        size_t n = strlen(eq);
        while (n > 0 && (eq[n - 1] == '\n' || eq[n - 1] == '\r' || eq[n - 1] == ' ')) {
            eq[--n] = '\0';
        }
        if (n == 0 || n >= home_n) {
            continue;
        }
        memcpy(home, eq, n + 1);
        found = 1;
        break;
    }
    fclose(fp);
    return found ? 0 : -1;
}

static int bootstrap_venv(const char *python, const char *start_py) {
    pid_t pid = fork();
    if (pid < 0) {
        return -1;
    }
    if (pid == 0) {
        execl(python, python, start_py, "setup", (char *)NULL);
        _exit(127);
    }
    int status = 0;
    if (waitpid(pid, &status, 0) < 0) {
        return -1;
    }
    if (WIFEXITED(status) && WEXITSTATUS(status) == 0) {
        return 0;
    }
    return -1;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        [NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];
    }

    char exe[PATH_MAX];
    uint32_t exe_n = sizeof(exe);
    if (_NSGetExecutablePath(exe, &exe_n) != 0) {
        alert_error("Motif", "Could not resolve Motif.app’s executable path.");
        return 1;
    }
    char motif_exe[PATH_MAX];
    if (realpath(exe, motif_exe) == NULL) {
        strncpy(motif_exe, exe, sizeof(motif_exe) - 1);
        motif_exe[sizeof(motif_exe) - 1] = '\0';
    }

    char macos[PATH_MAX], contents[PATH_MAX], app[PATH_MAX], root[PATH_MAX];
    strncpy(macos, motif_exe, sizeof(macos) - 1);
    macos[sizeof(macos) - 1] = '\0';
    if (parent_dir(macos) != 0) {
        alert_error("Motif", "Motif.app is in an unexpected place.");
        return 1;
    }
    strncpy(contents, macos, sizeof(contents) - 1);
    contents[sizeof(contents) - 1] = '\0';
    if (parent_dir(contents) != 0) {
        alert_error("Motif", "Motif.app is in an unexpected place.");
        return 1;
    }
    strncpy(app, contents, sizeof(app) - 1);
    app[sizeof(app) - 1] = '\0';
    if (parent_dir(app) != 0) {
        alert_error("Motif", "Motif.app is in an unexpected place.");
        return 1;
    }
    strncpy(root, app, sizeof(root) - 1);
    root[sizeof(root) - 1] = '\0';
    if (parent_dir(root) != 0) {
        alert_error("Motif", "Motif.app is in an unexpected place.");
        return 1;
    }

    /* /Applications/Motif.app stores the project path in Contents/Resources/MotifProject.
     * The copy next to start.py has no bookmark and uses the parent folder. */
    char bookmark[PATH_MAX], bookmarked[PATH_MAX];
    snprintf(bookmark, sizeof(bookmark), "%s/Contents/Resources/MotifProject", app);
    if (read_first_line(bookmark, bookmarked, sizeof(bookmarked)) == 0 && path_exists(bookmarked)) {
        char marked_start[PATH_MAX];
        snprintf(marked_start, sizeof(marked_start), "%s/start.py", bookmarked);
        if (path_exists(marked_start)) {
            strncpy(root, bookmarked, sizeof(root) - 1);
            root[sizeof(root) - 1] = '\0';
        }
    }

    char start_py[PATH_MAX], venv[PATH_MAX], venv_py[PATH_MAX], pyvenv_cfg[PATH_MAX];
    snprintf(start_py, sizeof(start_py), "%s/start.py", root);
    snprintf(venv, sizeof(venv), "%s/.venv", root);
    snprintf(venv_py, sizeof(venv_py), "%s/bin/python", venv);
    snprintf(pyvenv_cfg, sizeof(pyvenv_cfg), "%s/pyvenv.cfg", venv);

    if (!path_exists(start_py)) {
        char msg[PATH_MAX + 160];
        snprintf(
            msg,
            sizeof(msg),
            "Motif.app must stay in the project folder, or be installed with:\n\n"
            "python3 start.py install\n\nLooked in:\n%s",
            root
        );
        alert_error("Motif", msg);
        return 1;
    }

    if (chdir(root) != 0) {
        alert_error("Motif", "Could not open the Motif project folder.");
        return 1;
    }

    if (!path_exists(venv_py) || !path_exists(pyvenv_cfg)) {
        const char *bootstrap = MOTIF_BUILD_PYTHON;
        if (!path_exists(bootstrap)) {
            bootstrap = "/usr/bin/python3";
        }
        if (!path_exists(bootstrap) || bootstrap_venv(bootstrap, start_py) != 0 || !path_exists(venv_py)) {
            alert_error(
                "Motif",
                "The Python environment is missing. In Terminal, run:\n\n"
                "python3 start.py setup\npython3 start.py app\n\n"
                "Then open Motif.app again."
            );
            return 1;
        }
    }

    char home_bin[PATH_MAX];
    if (read_pyvenv_home(pyvenv_cfg, home_bin, sizeof(home_bin)) != 0) {
        alert_error("Motif", "Could not read .venv/pyvenv.cfg.");
        return 1;
    }
    char base_prefix[PATH_MAX];
    strncpy(base_prefix, home_bin, sizeof(base_prefix) - 1);
    base_prefix[sizeof(base_prefix) - 1] = '\0';
    if (parent_dir(base_prefix) != 0 || !path_exists(base_prefix)) {
        alert_error("Motif", "The Python install recorded in .venv is missing. Run: python3 start.py setup && python3 start.py app");
        return 1;
    }

    setenv("MOTIF_BUNDLE", "1", 1);
    setenv("MOTIF_ROOT", root, 1);
    setenv("VIRTUAL_ENV", venv, 1);
    setenv("PWD", root, 1);

    /* sys.argv[0] is this binary; extra Finder/user args follow. Do not put
     * start.py in argv — start.py treats argv[1] as the command name. */
    char *py_argv[64];
    int py_argc = 0;
    py_argv[py_argc++] = motif_exe;
    for (int i = 1; i < argc && py_argc < 62; i++) {
        if (strncmp(argv[i], "-psn_", 5) == 0) {
            continue;
        }
        py_argv[py_argc++] = argv[i];
    }
    py_argv[py_argc] = NULL;

    PyStatus status;
    PyConfig config;
    PyConfig_InitPythonConfig(&config);
    config.install_signal_handlers = 1;
    config.parse_argv = 0;
    config.configure_c_stdio = 1;
    config.use_environment = 1;

    status = PyConfig_SetBytesString(&config, &config.program_name, motif_exe);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.executable, motif_exe);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.home, base_prefix);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.prefix, venv);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.exec_prefix, venv);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.base_prefix, base_prefix);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesString(&config, &config.base_exec_prefix, base_prefix);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }
    status = PyConfig_SetBytesArgv(&config, py_argc, py_argv);
    if (PyStatus_Exception(status)) {
        goto py_fail;
    }

    status = Py_InitializeFromConfig(&config);
    PyConfig_Clear(&config);
    if (PyStatus_Exception(status)) {
        goto py_fail_cleared;
    }

    /* Project root + venv site-packages must be on sys.path. Editable
     * installs and PySide6 live there; PyConfig prefix alone is not enough. */
    if (PyRun_SimpleString(
            "import os, sys, site\n"
            "root = os.environ.get('MOTIF_ROOT') or ''\n"
            "venv = os.environ.get('VIRTUAL_ENV') or ''\n"
            "ver = f'python{sys.version_info[0]}.{sys.version_info[1]}'\n"
            "sp = os.path.join(venv, 'lib', ver, 'site-packages') if venv else ''\n"
            "if venv:\n"
            "    sys.prefix = venv\n"
            "    sys.exec_prefix = venv\n"
            "for p in (root, sp):\n"
            "    if p and p not in sys.path:\n"
            "        sys.path.insert(0, p)\n"
            "if sp and os.path.isdir(sp):\n"
            "    site.addsitedir(sp)\n"
        ) != 0) {
        alert_error("Motif", "Could not attach the project virtualenv.");
        Py_FinalizeEx();
        return 1;
    }

    {
        PyObject *list = PyList_New(py_argc);
        if (list == NULL) {
            alert_error("Motif", "Could not build sys.argv.");
            Py_FinalizeEx();
            return 1;
        }
        for (int i = 0; i < py_argc; i++) {
            PyObject *item = PyUnicode_FromString(py_argv[i]);
            if (item == NULL || PyList_SetItem(list, i, item) != 0) {
                Py_DECREF(list);
                alert_error("Motif", "Could not build sys.argv.");
                Py_FinalizeEx();
                return 1;
            }
        }
        if (PySys_SetObject("argv", list) != 0) {
            Py_DECREF(list);
            alert_error("Motif", "Could not set sys.argv.");
            Py_FinalizeEx();
            return 1;
        }
        Py_DECREF(list);
    }

    FILE *fp = fopen(start_py, "r");
    if (fp == NULL) {
        alert_error("Motif", "Could not open start.py.");
        Py_FinalizeEx();
        return 1;
    }
    int run = PyRun_SimpleFileEx(fp, start_py, 1);
    int fin = Py_FinalizeEx();
    if (run != 0 || fin < 0) {
        return 1;
    }
    return 0;

py_fail:
    PyConfig_Clear(&config);
py_fail_cleared:
    {
        const char *err = PyStatus_IsError(status) ? status.err_msg : "Python failed to start.";
        alert_error("Motif", err ? err : "Python failed to start. Run: python3 start.py setup && python3 start.py app");
    }
    return 1;
}
