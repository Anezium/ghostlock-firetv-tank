#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <unistd.h>

int main(void) {
    errno = 0;
    int fd = socket(AF_PACKET, SOCK_RAW, 0);
    printf("AF_PACKET/SOCK_RAW : fd=%d errno=%d (%s)\n", fd, errno, strerror(errno));
    if (fd >= 0) close(fd);

    errno = 0;
    int fd2 = socket(AF_PACKET, SOCK_DGRAM, 0);
    printf("AF_PACKET/SOCK_DGRAM: fd=%d errno=%d (%s)\n", fd2, errno, strerror(errno));
    if (fd2 >= 0) close(fd2);

    errno = 0;
    int fd3 = socket(AF_INET, SOCK_RAW, 0);
    printf("AF_INET/SOCK_RAW   : fd=%d errno=%d (%s)\n", fd3, errno, strerror(errno));
    if (fd3 >= 0) close(fd3);

    errno = 0;
    int fd4 = socket(AF_NETLINK, SOCK_RAW, 0);
    printf("AF_NETLINK/SOCK_RAW: fd=%d errno=%d (%s)\n", fd4, errno, strerror(errno));
    if (fd4 >= 0) close(fd4);

    return 0;
}
