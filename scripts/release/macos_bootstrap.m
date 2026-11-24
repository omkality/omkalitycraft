#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static int show_error(NSString *message) {
    [NSApplication sharedApplication];
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"OmkalityCraft";
    alert.informativeText = message;
    [alert runModal];
    return 2;
}

static BOOL make_private_directory(NSURL *url) {
    const char *path = url.fileSystemRepresentation;
    if (mkdir(path, 0700) == 0) {
        return YES;
    }
    struct stat info;
    return errno == EEXIST && lstat(path, &info) == 0 && S_ISDIR(info.st_mode);
}

int main(int argc, char **argv) {
    @autoreleasepool {
        NSBundle *bundle = NSBundle.mainBundle;
        NSURL *root = bundle.bundleURL.URLByResolvingSymlinksInPath.URLByDeletingLastPathComponent;
        // Versioned updates have an explicit root from the running launcher.
        for (int index = 1; index < argc; index++) {
            const char *argument = argv[index];
            if (strcmp(argument, "--root") == 0 && index + 1 < argc) {
                root = [NSURL fileURLWithPath:@(argv[++index]) isDirectory:YES].URLByResolvingSymlinksInPath;
            } else if (strncmp(argument, "--root=", 7) == 0) {
                root = [NSURL fileURLWithPath:@(argument + 7) isDirectory:YES].URLByResolvingSymlinksInPath;
            }
        }
        NSURL *data = [root URLByAppendingPathComponent:@"userdata" isDirectory:YES];
        NSURL *scratch = [data URLByAppendingPathComponent:@"tmp" isDirectory:YES];
        if (!make_private_directory(data) || !make_private_directory(scratch) ||
            chdir(root.fileSystemRepresentation) != 0 ||
            access(scratch.fileSystemRepresentation, W_OK | X_OK) != 0) {
            return show_error(@"Переместите приложение в папку, доступную для записи, и откройте его снова.");
        }
        // PyInstaller uses this working directory for its configured runtime-tmpdir.
        const char *local_tmp = scratch.fileSystemRepresentation;
        if (setenv("TMPDIR", local_tmp, 1) || setenv("TEMP", local_tmp, 1) ||
            setenv("TMP", local_tmp, 1)) {
            return show_error(@"Не удалось подготовить папку временных файлов.");
        }
        NSURL *program = [bundle.executableURL.URLByDeletingLastPathComponent
            URLByAppendingPathComponent:@"OmkalityCraftRuntime"];
        argv[0] = (char *)program.fileSystemRepresentation;
        execv(argv[0], argv);
        return show_error(@"Не удалось запустить лаунчер. Распакуйте архив целиком.");
    }
}
