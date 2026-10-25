#define _GNU_SOURCE
#include <errno.h>
#include <linux/futex.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static int futex6(uint32_t *uaddr, int op, uint32_t val,
                  const struct timespec *to, uint32_t *uaddr2, uint32_t val3) {
    return (int)syscall(SYS_futex, uaddr, op, val, to, uaddr2, val3);
}

int main(void) {
    uint32_t a = 0, b = 0;
    int r;

    errno = 0;
    r = futex6(&a, FUTEX_CMP_REQUEUE_PI, 1, NULL, &b, 0);
    printf("FUTEX_CMP_REQUEUE_PI (sans waiter) : r=%d errno=%d (%s)\n",
           r, errno, strerror(errno));

    errno = 0;
    r = futex6(&a, FUTEX_LOCK_PI, 0, NULL, NULL, 0);
    printf("FUTEX_LOCK_PI                       : r=%d errno=%d (%s)\n",
           r, errno, strerror(errno));

    if (r == 0) {
        errno = 0;
        r = futex6(&a, FUTEX_UNLOCK_PI, 0, NULL, NULL, 0);
        printf("FUTEX_UNLOCK_PI                     : r=%d errno=%d (%s)\n",
               r, errno, strerror(errno));
    }

    errno = 0;
    r = futex6(&a, FUTEX_CMP_REQUEUE_PI, 1, NULL, &a, 0);
    printf("FUTEX_CMP_REQUEUE_PI (memes adresses): r=%d errno=%d (%s)\n",
           r, errno, strerror(errno));

    return 0;
}
