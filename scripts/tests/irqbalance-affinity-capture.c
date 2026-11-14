/* Test-only LD_PRELOAD interposer. Run with /proc/irq mounted read-only. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <unistd.h>
struct capture { char *path; };
static ssize_t capture_write(void *arg, const char *data, size_t size)
{
    struct capture *c=arg;
    int fd=open(getenv("IRQBALANCE_TEST_TRACE"),O_WRONLY|O_APPEND|O_CREAT,0600);
    if(fd<0)return -1;
    dprintf(fd,"%s %.*s\n",c->path,(int)size,data);close(fd);return size;
}
static int capture_close(void *arg) {struct capture *c=arg;free(c->path);free(c);return 0;}
FILE *fopen(const char *path,const char *mode)
{
    static FILE *(*real_fopen)(const char *,const char *);
    if(!real_fopen)real_fopen=dlsym(RTLD_NEXT,"fopen");
    if(getenv("IRQBALANCE_TEST_TRACE") && !strncmp(path,"/proc/irq/",10) && strstr(path,"/smp_affinity") && strchr(mode,'w')) {
        struct capture *c=calloc(1,sizeof(*c));c->path=strdup(path);
        cookie_io_functions_t funcs={.write=capture_write,.close=capture_close};return fopencookie(c,"w",funcs);
    }
    return real_fopen(path,mode);
}
FILE *fopen64(const char *path,const char *mode) { return fopen(path,mode); }
