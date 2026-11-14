#!/usr/bin/env python3
"""Compile/run real irqbalance code with synthetic topology and captured procfs writes."""
from pathlib import Path
import argparse, os, subprocess, tempfile
ROOT = Path(__file__).resolve().parents[2]
SOURCE = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <glib/gstdio.h>
#include "irqbalance.h"
cpumask_t cpu_online_map, unbanned_cpus, banned_cpus;
GList *numa_nodes, *packages, *cache_domains, *cpus;
int numa_avail, debug_mode, journal_logging;
unsigned int log_mask;
const char *log_indent;
static GList *all_irqs;
void force_rebalance_irq(struct irq_info *info, void *data) { assert(0); }
void sort_irq_list(GList **list) { (void)list; }
void for_each_irq(GList *list, void (*cb)(struct irq_info *, void *), void *data) {
    GList *e, *next;
    for (e = list ? list : all_irqs; e; e = next) { next=e->next; cb(e->data,data); }
}
void migrate_irq_obj(struct topo_obj *from, struct topo_obj *to, struct irq_info *info) {
    if (from) from->interrupts=g_list_remove(from->interrupts,info);
    else rebalance_irq_list=g_list_remove(rebalance_irq_list,info);
    to->interrupts=g_list_append(to->interrupts,info); info->assigned_obj=to; info->moved=1;
}
#include "placement.c"
static cpumask_t current;
int process_one_line(char *p, void (*cb)(char *, void *), void *data) { *(cpumask_t *)data=current; return 0; }
void get_mask_from_bitmap(char *s, void *p) { (void)s;(void)p; }
static int writes;
static char *written;
static size_t written_len;
static FILE *capture_fopen(const char *path, const char *mode) {
    assert(g_str_has_prefix(path,"/proc/irq/")); assert(!strcmp(mode,"w"));
    free(written);written=NULL;written_len=0;writes++;return open_memstream(&written,&written_len);
}
#define fopen capture_fopen
#include "activate.c"
#undef fopen
static cpumask_t mask(const char *s) { cpumask_t m;cpus_clear(m);assert(!cpulist_parse(s,strlen(s),m));return m; }
static int equal(cpumask_t a,cpumask_t b) { return cpus_equal(a,b); }
static void defaults(void) { cpu_online_map=mask("0-11,64,256,1023,4095");cpus_setall(unbanned_cpus);cpus_clear(banned_cpus);cpus_clear(current);free_netdev_cpu_rules(); }
static void netdir(const char *root,const char *name) { char *p=g_build_filename(root,"net",name,NULL);assert(!g_mkdir_with_parents(p,0700));g_free(p); }
static void test_rules(const char *root) {
    const char *invalid[]={"",":0","foo:","foo:4096","foo:3-1","foo:1,,2","foo:1a","foo:1-","foo:-1","foo:0,","foo:1:2"};
    struct irq_info irq={0},other={0},fresh={0};size_t i;
    defaults();netdir(root,"uplink-red");
    for(i=0;i<G_N_ELEMENTS(invalid);i++){int rc=add_netdev_cpu_rule(invalid[i]);if(rc>=0)fprintf(stderr,"Unexpected acceptance: %s\n",invalid[i]);assert(rc<0);}
    apply_netdev_cpu_rules(&irq,root);assert(!(irq.flags&IRQ_FLAG_CPUSET));
    assert(!add_netdev_cpu_rule("uplink-*:0-3,8-11,64,256,1023,4095"));
    apply_netdev_cpu_rules(&irq,root);assert(irq.flags&IRQ_FLAG_CPUSET);
    assert(cpu_isset(4095,irq.allowed_cpus)&&cpu_isset(256,irq.allowed_cpus)&&!cpu_isset(4,irq.allowed_cpus));
    apply_netdev_cpu_rules(&other,"/nonexistent");assert(!(other.flags&IRQ_FLAG_CPUSET));
    assert(!add_netdev_cpu_rule("uplink-red:2,8,256"));apply_netdev_cpu_rules(&irq,root);
    assert(equal(irq.allowed_cpus,mask("2,8,256")));
    netdir(root,"uplink-blue");assert(!add_netdev_cpu_rule("uplink-blue:8,64"));apply_netdev_cpu_rules(&irq,root);
    assert(equal(irq.allowed_cpus,mask("8")));
    fresh.irq=987;apply_netdev_cpu_rules(&fresh,root);assert(equal(fresh.allowed_cpus,mask("8")));
    other.flags=IRQ_FLAG_BANNED;apply_netdev_cpu_rules(&other,root);assert(!(other.flags&IRQ_FLAG_CPUSET));
    assert(!add_netdev_cpu_rule("uplink-blue:64"));apply_netdev_cpu_rules(&fresh,root);assert(cpus_empty(fresh.allowed_cpus));
    assert(!irq_object_allowed(&fresh,&cpu_online_map));
    puts("PASS parsing, wildcard/overlap/shared-device intersection, >64 CPUs, unmatched/default and banned IRQs");
}
static void test_activation(void) {
    struct irq_info irq={.irq=999,.level=BALANCE_CORE,.moved=1,.flags=IRQ_FLAG_CPUSET};
    struct topo_obj obj={.obj_type=OBJ_TYPE_PACKAGE};cpumask_t applied;int previous;
    defaults();obj.mask=mask("0-11,64,256");irq.assigned_obj=&obj;irq.allowed_cpus=mask("0-3,8-11,64,256");
    cpu_clear(0,unbanned_cpus);cpu_clear(64,cpu_online_map);
    activate_mapping(&irq,NULL);assert(!irq.moved);assert(!cpumask_parse_user(written,strlen(written),applied));
    assert(equal(applied,mask("1-3,8-11,256")));
    current=applied;irq.moved=1;previous=writes;activate_mapping(&irq,NULL);assert(writes==previous&&!irq.moved);
    irq.moved=1;irq.allowed_cpus=mask("4");cpu_clear(4,cpu_online_map);activate_mapping(&irq,NULL);
    assert(writes==previous&&irq.moved&&irq.level==BALANCE_CORE);
    cpu_set(4,cpu_online_map);cpus_clear(current);activate_mapping(&irq,NULL);assert(writes==previous+1&&!irq.moved);
    assert(!cpumask_parse_user(written,strlen(written),applied));assert(equal(applied,mask("4")));
    /* No rule retains upstream behavior, including CPUs outside the network pool. */
    irq.flags=0;irq.moved=1;obj.mask=mask("5");activate_mapping(&irq,NULL);
    assert(!cpumask_parse_user(written,strlen(written),applied));assert(cpu_isset(5,applied));
    puts("PASS actual activation writes: pool/online/global-ban intersection, idempotency, empty-pool recovery, default behavior");
}
static void test_placement(void) {
    struct topo_obj node={.number=0,.obj_type=OBJ_TYPE_NODE,.slots_left=INT_MAX};
    struct topo_obj pkg={.obj_type=OBJ_TYPE_PACKAGE,.slots_left=INT_MAX};
    struct topo_obj cache={.obj_type=OBJ_TYPE_CACHE,.slots_left=INT_MAX};
    struct topo_obj cores[4]={0};struct irq_info irqs[3]={0};int i;
    defaults();cpu_online_map=mask("0-3");node.mask=pkg.mask=cache.mask=cpu_online_map;
    numa_nodes=g_list_append(NULL,&node);packages=g_list_append(NULL,&pkg);cache_domains=g_list_append(NULL,&cache);
    node.children=packages;pkg.children=cache_domains;
    for(i=0;i<4;i++){cores[i].mask=mask(i==0?"0":i==1?"1":i==2?"2":"3");cores[i].obj_type=OBJ_TYPE_CPU;cores[i].slots_left=INT_MAX;cache.children=g_list_append(cache.children,&cores[i]);}
    cpus=cache.children;
    for(i=0;i<3;i++){
        irqs[i].irq=100+i;irqs[i].level=BALANCE_CORE;irqs[i].moved=1;irqs[i].numa_node=&node;
        if(i<2){irqs[i].flags=IRQ_FLAG_CPUSET;irqs[i].allowed_cpus=mask("0,2");}
        rebalance_irq_list=g_list_append(rebalance_irq_list,&irqs[i]);calculate_placement();
    }
    assert(irqs[0].assigned_obj==&cores[0]);assert(irqs[1].assigned_obj==&cores[2]);assert(irqs[2].assigned_obj==&cores[1]);
    puts("PASS actual topology placement: matching IRQs spread within pool; unrelated IRQ may use excluded CPU");
}
int main(void) {
    char *root=g_dir_make_tmp("irqbalance-pool-test-XXXXXX",NULL);assert(root);
    test_rules(root);test_activation();test_placement();free_netdev_cpu_rules();free(written);
    char *red=g_build_filename(root,"net","uplink-red",NULL), *blue=g_build_filename(root,"net","uplink-blue",NULL), *net=g_build_filename(root,"net",NULL);
    g_rmdir(red);g_rmdir(blue);g_rmdir(net);g_rmdir(root);g_free(red);g_free(blue);g_free(net);g_free(root);return 0;
}
'''
def integration_checks(src, native=False):
    binary=src/'openwrt-build/irqbalance'
    subprocess.run([str(binary),'--netdev-cpus','uplink*:0,2','--netdev-cpus','backup*:64,256','--version'],check=True,capture_output=True)
    bad=subprocess.run([str(binary),'--netdev-cpus','uplink:1,,2','--version'],capture_output=True,text=True)
    assert bad.returncode and 'Invalid netdev CPU rule' in bad.stdout
    init=ROOT/'feeds/packages/utils/irqbalance/files/irqbalance.init'
    mock=r"""
config_load() { :; }
config_get_bool() { eval "$1=1"; }
config_get() { eval "$1=\${4:-}"; }
config_list_foreach() {
    if [ "$2" = netdev_cpus ]; then
        "$3" 'uplink*:0,2'
        "$3" 'backup*:64,256'
    fi
}
procd_open_instance() { :; }
procd_close_instance() { :; }
procd_add_jail_mount_rw() { :; }
procd_set_param() { :; }
procd_append_param() {
    if [ "$2" = --netdev-cpus ]; then printf '%s|%s|%s\n' "$#" "$2" "$3"; fi
}
start_service
"""
    result=subprocess.run(['sh','-c',init.read_text()+mock],check=True,capture_output=True,text=True)
    assert result.stdout.splitlines()==['3|--netdev-cpus|uplink*:0,2','3|--netdev-cpus|backup*:64,256'],result.stdout
    print('PASS built-daemon CLI and quoted/repeated UCI arguments')
    if not native:return
    devices=[p for p in sorted(Path('/sys/class/net').iterdir()) if (p/'device/msi_irqs').is_dir()]
    if not devices:raise SystemExit('Native check requires a PCI network device with MSI IRQs')
    dev=devices[0];irqs={int(p.name) for p in (dev/'device/msi_irqs').iterdir()}
    with tempfile.TemporaryDirectory(prefix='irqbalance-native-') as d:
        p=Path(d);trace=p/'writes';trace.touch();library=p/'capture.so'
        subprocess.run(['gcc','-shared','-fPIC','-Wall','-Wextra',str(Path(__file__).with_name('irqbalance-affinity-capture.c')),'-ldl','-o',str(library)],check=True)
        env=dict(os.environ,LD_PRELOAD=str(library),IRQBALANCE_TEST_TRACE=str(trace))
        # The read-only bind mount is a backstop if interposition ever fails.
        cmd=['unshare','-Urnm','sh','-c','mount --bind /proc/irq /proc/irq && mount -o remount,bind,ro /proc/irq && exec "$@"','sandbox',str(binary),'-f','-d','-t','1','--netdev-cpus',dev.name+':0,2']
        proc=subprocess.Popen(cmd,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        try:
            output=proc.communicate(timeout=6)[0]
        except subprocess.TimeoutExpired:
            proc.terminate();output=proc.communicate(timeout=5)[0]
        assert proc.returncode in (0,-15),output
        writes=[]
        for line in trace.read_text().splitlines():
            name,mask=line.split();writes.append((int(name.split('/')[3]),int(mask.replace(',',''),16)))
        selected=[m for irq,m in writes if irq in irqs]
        assert selected and all(m and not m&~5 for m in selected),(selected,output)
        assert any(irq not in irqs and m&~5 for irq,m in writes),'No unconstrained IRQ outside the pool observed'
        print(f'PASS isolated built daemon: {dev.name} IRQs {sorted(irqs)}, captured masks {selected}; other IRQs still use other CPUs')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--native',action='store_true');args=parser.parse_args()
    sources=list(ROOT.glob('build_dir/target-*/irqbalance-*/netdev.c'))
    if len(sources)!=1: raise SystemExit('Prepare the patched irqbalance package first')
    src=sources[0].parent
    host=ROOT/'staging_dir/hostpkg'
    with tempfile.TemporaryDirectory(prefix='irqbalance-netdev-test-') as d:
        p=Path(d);(p/'config.h').write_text('/* Host unit harness; optional daemon integrations disabled. */\n')
        (p/'test.c').write_text(SOURCE)
        cmd=['gcc','-D_GNU_SOURCE','-std=gnu99','-Wall','-Wextra','-Wno-unused-parameter','-Wno-sign-compare','-I'+str(src),'-I'+d,'-I'+str(host/'include/glib-2.0'),'-I'+str(host/'lib/glib-2.0/include'),str(p/'test.c'),str(src/'netdev.c'),str(src/'bitmap.c'),'-l:libglib-2.0.so.0','-lm','-o',str(p/'test')]
        subprocess.run(cmd,check=True)
        subprocess.run([str(p/'test')],check=True)
    integration_checks(src,args.native)
if __name__=='__main__':main()
